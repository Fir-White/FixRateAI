"""One-time installation infrastructure using the existing users, roles and sessions."""
from __future__ import annotations

import hashlib
import hmac
import os
import re
from uuid import uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import Header, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import text

from app.security.sessions import hash_password


class FirstAdministrator(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    organization_name: str = Field(min_length=1, max_length=200)
    site_name: str = Field(min_length=1, max_length=200)
    full_name: str = Field(min_length=1, max_length=200)
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=12, max_length=1024, repr=False)
    timezone: str = "Asia/Yekaterinburg"

    @field_validator("organization_name", "site_name", "full_name")
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError("Введите непустое значение")
        return value.strip()

    @field_validator("email")
    @classmethod
    def valid_email(cls, value):
        value = value.strip().lower()
        if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", value):
            raise ValueError("Введите email")
        return value

    @field_validator("timezone")
    @classmethod
    def valid_zone(cls, value):
        try:
            ZoneInfo(value)
        except (ValueError, ZoneInfoNotFoundError):
            raise ValueError("Неизвестный часовой пояс") from None
        return value


def arm_bootstrap(engine):
    """Explicit migration step. An existing account always seals first registration."""
    token_hash = os.environ.get("FIXRATE_BOOTSTRAP_TOKEN_SHA256", "")
    if token_hash and not re.fullmatch(r"[0-9a-f]{64}", token_hash):
        raise ValueError("Invalid installation token hash")
    with engine.begin() as conn:
        row = conn.execute(text("SELECT * FROM fixrate_installation WHERE singleton FOR UPDATE")).mappings().one()
        if row["completed_at"]:
            return
        if conn.scalar(text("SELECT EXISTS(SELECT 1 FROM users)")):
            conn.execute(text("UPDATE fixrate_installation SET completed_at=now(),bootstrap_token_hash=NULL WHERE singleton"))
        elif token_hash and row["bootstrap_token_hash"] is None:
            conn.execute(text("UPDATE fixrate_installation SET bootstrap_token_hash=:hash WHERE singleton"), {"hash": token_hash})


def create_first_administrator(engine, command: FirstAdministrator, token: str):
    # Reject an invalid token before expensive hashing; never record secrets in audit.
    presented = hashlib.sha256(token.encode()).hexdigest()
    with engine.begin() as conn:
        row = conn.execute(text("SELECT * FROM fixrate_installation WHERE singleton FOR UPDATE")).mappings().one()
        if row["completed_at"]:
            raise HTTPException(409, "Первоначальная настройка уже завершена")
        if not row["bootstrap_token_hash"] or not hmac.compare_digest(presented, row["bootstrap_token_hash"]):
            raise HTTPException(403, "Неверный установочный код")
        if conn.scalar(text("SELECT EXISTS(SELECT 1 FROM users)")):
            raise HTTPException(409, "База уже содержит пользователей; требуется защищённое восстановление")
        password_hash = hash_password(command.password)
        site_id, user_id = uuid4(), uuid4()
        conn.execute(text("INSERT INTO sites(site_id,name,timezone) VALUES (:id,:name,:zone)"),
                     {"id": site_id, "name": command.site_name, "zone": command.timezone})
        conn.execute(text("INSERT INTO users(user_id,full_name,email,password_hash) VALUES (:id,:name,:email,:hash)"),
                     {"id": user_id, "name": command.full_name, "email": command.email, "hash": password_hash})
        conn.execute(text("INSERT INTO site_memberships(site_id,user_id,role) VALUES (:site,:user,'admin')"),
                     {"site": site_id, "user": user_id})
        conn.execute(text("UPDATE fixrate_installation SET completed_at=now(),bootstrap_token_hash=NULL,organization_name=:org,first_admin_id=:user WHERE singleton"),
                     {"org": command.organization_name, "user": user_id})
        conn.execute(text("INSERT INTO audit_events(site_id,actor_type,actor_user_id,entity_type,entity_id,action) VALUES (:site,'system',:user,'installation',:user,'bootstrap_completed')"),
                     {"site": site_id, "user": user_id})
    return {"status": "created", "login_url": "/login"}


def register_installation_routes(app):
    @app.get("/api/setup")
    def installation_status():
        with app.state.engine.connect() as conn:
            row = conn.execute(text("SELECT completed_at,bootstrap_token_hash IS NOT NULL AS armed FROM fixrate_installation WHERE singleton")).mappings().one()
        return {"required": row["completed_at"] is None and row["armed"]}

    @app.post("/api/setup", status_code=201)
    def first_administrator(command: FirstAdministrator, x_fixrate_setup_token: str = Header(default="", max_length=256)):
        return create_first_administrator(app.state.engine, command, x_fixrate_setup_token)
