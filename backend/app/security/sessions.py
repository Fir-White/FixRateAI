"""Password hashing and opaque, revocable database sessions. No role headers."""
from __future__ import annotations

import hashlib
import hmac
import os
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import HTTPException, Request
from sqlalchemy import text
from .permissions import has_role, public_permissions

SQL_ROLES = {role: role for role in ('director','chief_engineer','engineer','admin','dispatcher','executor')}
SQL_ROLES['technician'] = 'executor'
# Compatibility for previously provisioned data until migration 010 is applied.
SQL_ROLES['executive'] = 'director'
API_ROLES = {role: role for role in SQL_ROLES if role not in ('technician', 'executive')}
SITE_ACCESS_MANAGERS = ("admin", "chief_engineer")


def role_is_enabled(role: str) -> bool:
    configured = {
        value.strip()
        for value in os.environ.get("FIXRATE_ACTIVE_ROLES", "").split(",")
        if value.strip()
    }
    return not configured or role in configured


COOKIE = "fixrate_session"


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def hash_password(password: str) -> str:
    if len(password) < 12:
        raise ValueError("Password must have at least 12 characters")
    salt = secrets.token_hex(16)
    key = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 600_000)
    return f"pbkdf2_sha256$600000${salt}${key.hex()}"


def verify_password(password: str, encoded: str | None) -> bool:
    try:
        algorithm, rounds, salt, expected = (encoded or "").split("$")
        if algorithm != "pbkdf2_sha256" or not 100_000 <= int(rounds) <= 2_000_000:
            return False
        actual = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), int(rounds)).hex()
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False


@dataclass(frozen=True)
class Principal:
    user_id: UUID
    site_id: UUID
    role: str
    name: str
    email: str
    site_name: str
    timezone: str

    def profile(self):
        payload = dict(userId=str(self.user_id), siteId=str(self.site_id), role=self.role,
                       name=self.name, email=self.email, siteName=self.site_name, timezone=self.timezone,
                       **public_permissions(self.role))
        if self.role == "chief_engineer":
            from app.onlyoffice import OfficeSettings

            try:
                office = OfficeSettings.configured()
            except ValueError:
                office = None
            if office and office.browser_origin.partition("//")[2].split(":")[0].lower() == "localhost":
                payload["workbookEditorOrigin"] = office.browser_origin
        return payload


def authenticate(request: Request, session, *, lock: bool = False) -> Principal:
    token = request.cookies.get(COOKIE)
    if not token:
        raise HTTPException(401, "Сессия отсутствует")
    row = session.execute(text("""
        SELECT u.user_id,u.full_name,u.email,m.site_id,m.role,s.name,s.timezone,x.csrf_hash
        FROM fixrate_sessions x JOIN users u USING(user_id)
        JOIN site_memberships m ON m.user_id=x.user_id AND m.site_id=x.site_id
        JOIN sites s ON s.site_id=m.site_id
        WHERE x.token_hash=:token AND x.expires_at>now()
          AND u.is_active AND m.is_active AND s.is_active
    """ + (' FOR SHARE OF x,u,m,s' if lock else '')), {"token": digest(token)}).mappings().first()
    if not row or row["role"] not in SQL_ROLES or not role_is_enabled(SQL_ROLES.get(row["role"], row["role"])):
        raise HTTPException(401, "Сессия истекла или доступ отозван")
    # Personal chat lifecycle is not a write to the operational domain. Ownership
    # and CSRF are still checked by the ordinary auth/assistant dependencies.
    chat_prefix='/api/v1/assistant/conversations/'
    private_chat_mutation=(request.method in ('PATCH','DELETE') and request.url.path.startswith(chat_prefix)
                           and bool(request.url.path[len(chat_prefix):]) and '/' not in request.url.path[len(chat_prefix):])
    if SQL_ROLES[row["role"]] == "director" and not private_chat_mutation and request.method not in ("GET", "HEAD", "OPTIONS") and not (((request.method == "PATCH" and request.url.path == "/api/v1/maintenance/users/me/email") or (request.method == "POST" and request.url.path == "/api/v1/maintenance/users/me/password")) or request.url.path in ("/api/v1/auth/logout", "/api/v1/auth/site", "/api/v1/maintenance/notifications/read-all", "/api/v1/maintenance/notifications/clear") or (request.method == 'POST' and request.url.path.startswith('/api/v1/assistant/')) or (request.url.path.startswith("/api/v1/maintenance/notifications/") and request.url.path.endswith(("/read", "/delete")))):
        raise HTTPException(403, "Руководитель имеет доступ только для чтения")
    if request.method not in ("GET", "HEAD", "OPTIONS"):
        csrf = request.headers.get("x-csrf-token", "")
        if not csrf or not hmac.compare_digest(digest(csrf), row["csrf_hash"]):
            raise HTTPException(403, "Недействительный CSRF токен")
    return Principal(row["user_id"], row["site_id"], SQL_ROLES[row["role"]],
                     row["full_name"], row["email"], row["name"], row["timezone"])


def create_session(session, user_id, site_id):
    token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    session.execute(text("""INSERT INTO fixrate_sessions(token_hash,csrf_hash,user_id,site_id,expires_at)
        VALUES (:token,:csrf,:user,:site,:expires)"""),
        dict(token=digest(token), csrf=digest(csrf), user=user_id, site=site_id,
             expires=datetime.now(timezone.utc) + timedelta(hours=8)))
    return token, csrf
