"""Password hashing and opaque, revocable database sessions. No role headers."""
from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import HTTPException, Request
from sqlalchemy import text

SQL_ROLES = {role: role for role in ('director','chief_engineer','engineer','admin','dispatcher','executor')}
SQL_ROLES['technician'] = 'executor'
# Compatibility for previously provisioned data until migration 010 is applied.
SQL_ROLES['executive'] = 'director'
API_ROLES = {role: role for role in SQL_ROLES if role not in ('technician', 'executive')}


def has_role(role, roles):
    """Business hierarchy; technical administration is a separate capability."""
    effective = {role}
    if role == 'chief_engineer': effective.update(('engineer','dispatcher'))
    if role == 'engineer': effective.add('dispatcher')
    return bool(effective.intersection(roles))


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
        return dict(userId=str(self.user_id), siteId=str(self.site_id), role=self.role,
                    name=self.name, email=self.email, siteName=self.site_name, timezone=self.timezone)


def authenticate(request: Request, session) -> Principal:
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
    """), {"token": digest(token)}).mappings().first()
    if not row or row["role"] not in SQL_ROLES:
        raise HTTPException(401, "Сессия истекла или доступ отозван")
    if SQL_ROLES[row["role"]] == "director" and request.method not in ("GET", "HEAD", "OPTIONS") and not (((request.method == "PATCH" and request.url.path == "/api/v1/maintenance/users/me/email") or (request.method == "POST" and request.url.path == "/api/v1/maintenance/users/me/password")) or request.url.path in ("/api/v1/auth/logout", "/api/v1/maintenance/notifications/read-all", "/api/v1/maintenance/notifications/clear") or (request.url.path.startswith("/api/v1/maintenance/notifications/") and request.url.path.endswith(("/read", "/delete")))):
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
