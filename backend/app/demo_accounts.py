"""Explicit local demo credentials; settings parsing needs only the standard library."""
from __future__ import annotations

import json
import re

# Stable IDs preserve assignments, reports and the role of each demo account.
DEMO_ACCOUNTS = {
    "FIXRATE_DEMO_EXECUTIVE_EMAIL": ("executive","executive","fixrate-demo-executive@example.test"),
    "FIXRATE_DEMO_CHIEF_EMAIL": ("chief_engineer","chief-engineer","fixrate-demo-chief_engineer@example.test"),
    "FIXRATE_DEMO_LOGIN": ("dispatcher", "dispatcher", "fixrate-demo-dispatcher@example.test"),
    "FIXRATE_DEMO_ADMIN_EMAIL": ("admin", "admin", "fixrate-demo-admin@example.test"),
    "FIXRATE_DEMO_ENGINEER_EMAIL": ("engineer", "engineer", "fixrate-demo-engineer@example.test"),
    "FIXRATE_DEMO_EXECUTOR_EMAIL": ("executor", "user-1", "fixrate-demo-1@example.test"),
}
DEMO_KEYS = (*DEMO_ACCOUNTS, "FIXRATE_DEMO_PASSWORD")


def read_demo_environment(path, environ):
    """Read only demo keys, literally: no expansion of $ in passwords."""
    values = {}
    if path.is_file():
        for line in path.read_text(encoding="utf-8-sig").splitlines():
            line = line.strip()
            if line.startswith("export "):
                line = line[7:].lstrip()
            key, sep, raw = line.partition("=")
            key = key.strip()
            if not sep or key not in DEMO_KEYS:
                continue
            raw = raw.strip()
            try:
                if raw.startswith('"'):
                    value, end = json.JSONDecoder().raw_decode(raw)
                    tail = raw[end:].strip()
                    if not isinstance(value, str) or (tail and not tail.startswith("#")):
                        raise ValueError
                elif raw.startswith("'"):
                    end = raw.index("'", 1)
                    value, tail = raw[1:end], raw[end+1:].strip()
                    if tail and not tail.startswith("#"):
                        raise ValueError
                else:
                    value = re.split(r"\s+#", raw, maxsplit=1)[0].rstrip()
                values[key] = value
            except (ValueError, TypeError):
                raise ValueError("Invalid .env value for " + key) from None
    for key in DEMO_KEYS:
        if key in environ:
            values[key] = environ[key]
    return values


def validate_demo_credentials(password, values):
    if not isinstance(password, str) or len(password) < 12 or any(c in password for c in "\r\n\x00"):
        raise ValueError("FIXRATE_DEMO_PASSWORD must have 12+ characters and no line breaks")
    accounts = {}
    for variable, (_, identity, default) in DEMO_ACCOUNTS.items():
        email = values.get(variable, default).strip().lower()
        if len(email) > 320 or not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email):
            raise ValueError(variable + " must be an email address")
        accounts[identity] = email
    for number in (1, 2, 3):
        accounts[f"assignment-worker-{number}"] = f"fixrate-assignment-{number}@example.test"
    if len(set(accounts.values())) != len(accounts):
        raise ValueError("Demo email addresses must be distinct")
    return accounts


def configure_demo_accounts(engine, password, values):
    """Atomically update only known demo users; never rewrite business records."""
    from sqlalchemy import bindparam, text
    from app.integration.demo import demo_id
    from app.security.sessions import hash_password, verify_password

    accounts = {demo_id(key): email for key, email in validate_demo_credentials(password, values).items()}
    with engine.begin() as conn:
        rows = conn.execute(text("SELECT user_id,email,password_hash FROM users WHERE user_id IN :ids FOR UPDATE")
                            .bindparams(bindparam("ids", expanding=True)), {"ids": list(accounts)}).mappings().all()
        if len(rows) != len(accounts):
            raise ValueError("Demo accounts are missing; run seed-demo first")
        owners = conn.execute(text("SELECT user_id,lower(email) AS email FROM users WHERE lower(email) IN :emails")
                              .bindparams(bindparam("emails", expanding=True)), {"emails": list(accounts.values())}).mappings().all()
        if any(accounts.get(row["user_id"]) != row["email"] for row in owners):
            raise ValueError("A configured demo email already belongs to another account")
        changed = 0
        encoded = None
        for row in rows:
            password_changed = not verify_password(password, row["password_hash"])
            if row["email"] == accounts[row["user_id"]] and not password_changed:
                continue
            if password_changed and encoded is None:
                encoded = hash_password(password)
            conn.execute(text("UPDATE users SET email=:email,password_hash=:hash WHERE user_id=:id"),
                         dict(id=row["user_id"], email=accounts[row["user_id"]],
                              hash=encoded if password_changed else row["password_hash"]))
            conn.execute(text("DELETE FROM fixrate_sessions WHERE user_id=:id"), {"id": row["user_id"]})
            changed += 1
    return changed
