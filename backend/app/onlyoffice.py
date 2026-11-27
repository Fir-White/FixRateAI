"""Local transport for the ONLYOFFICE Docs integration."""
from base64 import urlsafe_b64decode, urlsafe_b64encode
from dataclasses import dataclass, field
from hashlib import sha256
import hmac
import json
import os
import re
from time import time
from urllib.parse import urlsplit

import httpx

from app.catalog_excel import MAX_FILE


class OfficeCommandRejected(ValueError):
    """A definitive rejection from the DocumentServer, rather than a lost reply."""


@dataclass(frozen=True)
class OfficeSettings:
    secret: str = field(repr=False)
    browser_origin: str
    internal_origin: str
    callback_origin: str

    @classmethod
    def configured(cls):
        names = ("SECRET", "BROWSER_ORIGIN", "INTERNAL_ORIGIN", "CALLBACK_ORIGIN")
        values = [os.getenv(f"FIXRATE_OFFICE_{name}", "").strip().rstrip("/") if name != "SECRET"
                  else os.getenv("FIXRATE_OFFICE_SECRET", "") for name in names]
        if not any(values):
            return None
        secret, browser, internal, callback = values
        for value, hosts in ((browser, {"127.0.0.1", "localhost", "::1"}), (internal, {"onlyoffice"}), (callback, {"app"})):
            parsed = urlsplit(value)
            if (parsed.scheme != "http" or parsed.hostname not in hosts or parsed.username is not None
                    or parsed.password is not None or parsed.path or parsed.query or parsed.fragment):
                raise ValueError("Invalid local ONLYOFFICE origin")
            _ = parsed.port
        if len(secret.encode()) < 32:
            raise ValueError("FIXRATE_OFFICE_SECRET must be at least 32 bytes")
        return cls(secret, browser, internal, callback)


def _encoded(value) -> str:
    return urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _decoded(value: str) -> bytes:
    return urlsafe_b64decode(value + "=" * (-len(value) % 4))


def _json(value: dict) -> bytes:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode()


def sign_office_token(secret: str, claims: dict) -> str:
    issued = int(time())
    body = ".".join((_encoded(_json({"alg": "HS256", "typ": "JWT"})),
                     _encoded(_json(dict(claims, iat=issued, exp=issued + 300)))))
    return body + "." + _encoded(hmac.digest(secret.encode(), body.encode("ascii"), sha256))


def signed_payload(settings: OfficeSettings, authorization: str, operation: str) -> dict:
    if not authorization.startswith("Bearer ") or len(authorization) > 24_000:
        raise ValueError("Missing ONLYOFFICE authorization")
    token = authorization.removeprefix("Bearer ")
    if not re.fullmatch(r"[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+", token):
        raise ValueError("Invalid ONLYOFFICE authorization")
    header, payload, signature = token.split(".")
    expected = hmac.digest(settings.secret.encode(), f"{header}.{payload}".encode("ascii"), sha256)
    if not hmac.compare_digest(_encoded(expected), signature):
        raise ValueError("Invalid ONLYOFFICE signature")
    decoded_header, claims = json.loads(_decoded(header)), json.loads(_decoded(payload))
    if not isinstance(decoded_header, dict) or decoded_header.get("alg") != "HS256" or not isinstance(claims, dict):
        raise ValueError("Invalid ONLYOFFICE token")
    expires = claims.get("exp")
    if type(expires) is not int or expires < time() or claims.get("operation") != operation:
        raise ValueError("Expired or incompatible ONLYOFFICE token")
    if not isinstance(claims.get("payload"), dict):
        raise ValueError("Invalid ONLYOFFICE payload")
    return claims["payload"]


def request_forcesave(settings: OfficeSettings, key: str, request_id: str) -> bool:
    payload = dict(c="forcesave", key=key, userdata=request_id)
    token = sign_office_token(settings.secret, {"operation": "command", **payload})
    with httpx.Client(timeout=10, trust_env=False) as client:
        response = client.post(settings.internal_origin + "/command", json=dict(payload, token=token))
        response.raise_for_status()
        result = response.json()
    code = result.get("error") if isinstance(result, dict) else None
    if code == 4:
        return False
    if type(code) is int and code != 0:
        raise OfficeCommandRejected("ONLYOFFICE rejected snapshot request")
    if type(code) is not int or result.get("key") != key:
        raise ValueError("Invalid snapshot reply from ONLYOFFICE")
    return True


def fetch_snapshot(settings: OfficeSettings, url: str) -> bytes:
    parsed = urlsplit(url)
    if (f"{parsed.scheme}://{parsed.netloc}" not in {settings.internal_origin, settings.browser_origin}
            or parsed.fragment or ".." in parsed.path.split("/")
            or not re.fullmatch(r"/cache/files/[A-Za-z0-9_./-]+\.xlsx", parsed.path, re.IGNORECASE)):
        raise ValueError("Unexpected ONLYOFFICE snapshot address")
    target = settings.internal_origin + parsed.path + ("?" + parsed.query if parsed.query else "")
    with httpx.Client(timeout=15, trust_env=False) as client:
        with client.stream("GET", target) as response:
            response.raise_for_status()
            content = bytearray()
            for chunk in response.iter_bytes(chunk_size=64 * 1024):
                content.extend(chunk)
                if len(content) > MAX_FILE:
                    raise ValueError("ONLYOFFICE snapshot exceeds limit")
    return bytes(content)
