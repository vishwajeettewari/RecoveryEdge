from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
import time
from typing import Any, Dict, Iterable, Optional, Set

from passlib.context import CryptContext

ROLES = [
    "VIEWER",
    "CEO",
    "CFO",
    "COLLECTIONS_MANAGER",
    "CALLING_AGENT",
    "COMPLIANCE_OFFICER",
    "ADMIN",
]

VIEW_DASHBOARD = "VIEW_DASHBOARD"
PORTFOLIO_MANAGE = "PORTFOLIO_MANAGE"
WORKBENCH_VIEW = "WORKBENCH_VIEW"
WORKBENCH_MUTATE = "WORKBENCH_MUTATE"
ALERTS_VIEW = "ALERTS_VIEW"
ALERTS_MUTATE = "ALERTS_MUTATE"
ALERT_RULES_EDIT = "ALERT_RULES_EDIT"
REPORTS_VIEW = "REPORTS_VIEW"
REPORTS_SCHEDULE = "REPORTS_SCHEDULE"
INTEGRATIONS_VIEW = "INTEGRATIONS_VIEW"
INTEGRATIONS_RESOLVE_CONFLICTS = "INTEGRATIONS_RESOLVE_CONFLICTS"
USERS_MANAGE = "USERS_MANAGE"
SYSTEM_VIEW_BUILD_INFO = "SYSTEM_VIEW_BUILD_INFO"

ROLE_PERMISSIONS: Dict[str, Set[str]] = {
    "CEO": {VIEW_DASHBOARD, WORKBENCH_VIEW, ALERTS_VIEW, REPORTS_VIEW, INTEGRATIONS_VIEW, SYSTEM_VIEW_BUILD_INFO},
    "CFO": {VIEW_DASHBOARD, WORKBENCH_VIEW, REPORTS_VIEW, SYSTEM_VIEW_BUILD_INFO},
    "COLLECTIONS_MANAGER": {
        VIEW_DASHBOARD,
        PORTFOLIO_MANAGE,
        WORKBENCH_VIEW,
        WORKBENCH_MUTATE,
        ALERTS_VIEW,
        ALERTS_MUTATE,
        REPORTS_VIEW,
        REPORTS_SCHEDULE,
        INTEGRATIONS_VIEW,
        INTEGRATIONS_RESOLVE_CONFLICTS,
        SYSTEM_VIEW_BUILD_INFO,
    },
    "CALLING_AGENT": {WORKBENCH_VIEW, WORKBENCH_MUTATE, SYSTEM_VIEW_BUILD_INFO},
    "COMPLIANCE_OFFICER": {
        VIEW_DASHBOARD,
        WORKBENCH_VIEW,
        ALERTS_VIEW,
        ALERTS_MUTATE,
        ALERT_RULES_EDIT,
        REPORTS_VIEW,
        SYSTEM_VIEW_BUILD_INFO,
    },
    "ADMIN": {
        VIEW_DASHBOARD,
        PORTFOLIO_MANAGE,
        WORKBENCH_VIEW,
        WORKBENCH_MUTATE,
        ALERTS_VIEW,
        ALERTS_MUTATE,
        ALERT_RULES_EDIT,
        REPORTS_VIEW,
        REPORTS_SCHEDULE,
        INTEGRATIONS_VIEW,
        INTEGRATIONS_RESOLVE_CONFLICTS,
        USERS_MANAGE,
        SYSTEM_VIEW_BUILD_INFO,
    },
    # Legacy aliases for backward compatibility with existing bearer token setups.
    "SUPERVISOR": {
        VIEW_DASHBOARD,
        PORTFOLIO_MANAGE,
        WORKBENCH_VIEW,
        WORKBENCH_MUTATE,
        ALERTS_VIEW,
        ALERTS_MUTATE,
        REPORTS_VIEW,
        REPORTS_SCHEDULE,
        INTEGRATIONS_VIEW,
        INTEGRATIONS_RESOLVE_CONFLICTS,
        SYSTEM_VIEW_BUILD_INFO,
    },
    "VIEWER": {VIEW_DASHBOARD, WORKBENCH_VIEW, ALERTS_VIEW, REPORTS_VIEW, INTEGRATIONS_VIEW, SYSTEM_VIEW_BUILD_INFO},
}

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


PASSWORD_POLICY = {
    "min_length": 12,
    "require_upper": True,
    "require_lower": True,
    "require_digit": True,
    "require_special": True,
}


def password_policy_errors(password: str) -> list[str]:
    pwd = str(password or "")
    errs: list[str] = []
    if len(pwd) < int(PASSWORD_POLICY["min_length"]):
        errs.append("min_length")
    if bool(PASSWORD_POLICY["require_upper"]) and not re.search(r"[A-Z]", pwd):
        errs.append("require_upper")
    if bool(PASSWORD_POLICY["require_lower"]) and not re.search(r"[a-z]", pwd):
        errs.append("require_lower")
    if bool(PASSWORD_POLICY["require_digit"]) and not re.search(r"[0-9]", pwd):
        errs.append("require_digit")
    if bool(PASSWORD_POLICY["require_special"]) and not re.search(r"[^A-Za-z0-9]", pwd):
        errs.append("require_special")
    return errs


def validate_password_policy(password: str) -> bool:
    return not password_policy_errors(password)


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return pwd_context.verify(password, password_hash)
    except Exception:
        return False


def role_permissions(role: str) -> Set[str]:
    return set(ROLE_PERMISSIONS.get((role or "").upper(), set()))


def has_permissions(role: str, required: Iterable[str]) -> bool:
    perms = role_permissions(role)
    for p in required:
        if p not in perms:
            return False
    return True


def issue_access_token(
    *,
    user_id: str,
    username: str,
    role: str,
    secret: str,
    expires_in_seconds: int = 8 * 3600,
    tenant_id: Optional[str] = None,
    session_id: Optional[str] = None,
    jti: Optional[str] = None,
) -> str:
    now = int(time.time())
    payload = {
        "sub": user_id,
        "username": username,
        "role": role,
        "token_type": "access",
        "aud": "access",
        "iat": now,
        "exp": now + max(60, int(expires_in_seconds)),
    }
    if tenant_id:
        payload["tenant_id"] = tenant_id
    if session_id:
        payload["sid"] = session_id
    if jti:
        payload["jti"] = jti
    return _jwt_encode_hs256(payload=payload, secret=secret)


def issue_refresh_token(
    *,
    user_id: str,
    username: str,
    role: str,
    secret: str,
    expires_in_seconds: int,
    tenant_id: Optional[str] = None,
    session_id: Optional[str] = None,
    jti: Optional[str] = None,
) -> str:
    now = int(time.time())
    payload = {
        "sub": user_id,
        "username": username,
        "role": role,
        "token_type": "refresh",
        "aud": "refresh",
        "iat": now,
        "exp": now + max(300, int(expires_in_seconds)),
    }
    if tenant_id:
        payload["tenant_id"] = tenant_id
    if session_id:
        payload["sid"] = session_id
    if jti:
        payload["jti"] = jti
    return _jwt_encode_hs256(payload=payload, secret=secret)


def issue_ws_token(
    *,
    user_id: str,
    username: str,
    role: str,
    secret: str,
    tenant_id: str,
    expires_in_seconds: int = 60,
    session_id: Optional[str] = None,
    jti: Optional[str] = None,
) -> str:
    now = int(time.time())
    payload = {
        "sub": user_id,
        "username": username,
        "role": role,
        "tenant_id": tenant_id,
        "token_type": "ws",
        "aud": "voice_ws",
        "iat": now,
        "exp": now + max(30, int(expires_in_seconds)),
    }
    if session_id:
        payload["sid"] = session_id
    if jti:
        payload["jti"] = jti
    return _jwt_encode_hs256(payload=payload, secret=secret)


def decode_access_token(token: str, secret: str) -> Optional[Dict[str, Any]]:
    return decode_token(token, secret, expected_token_type="access", expected_aud="access")


def decode_token(
    token: str,
    secret: str,
    *,
    expected_token_type: Optional[str] = None,
    expected_aud: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    if not token:
        return None
    try:
        payload = _jwt_decode_hs256(token=token, secret=secret)
        if not isinstance(payload, dict):
            return None
        exp = int(payload.get("exp") or 0)
        if exp and exp < int(time.time()):
            return None
        if expected_token_type and str(payload.get("token_type") or "").strip().lower() != expected_token_type.strip().lower():
            return None
        if expected_aud and str(payload.get("aud") or "").strip().lower() != expected_aud.strip().lower():
            return None
        return payload
    except Exception:
        return None


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _b64url_decode(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode((data + padding).encode("ascii"))


def _jwt_encode_hs256(*, payload: Dict[str, Any], secret: str) -> str:
    header = {"alg": "HS256", "typ": "JWT"}
    header_b64 = _b64url_encode(json.dumps(header, separators=(",", ":"), sort_keys=True).encode("utf-8"))
    payload_b64 = _b64url_encode(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8"))
    signing_input = f"{header_b64}.{payload_b64}".encode("ascii")
    sig = hmac.new(secret.encode("utf-8"), signing_input, hashlib.sha256).digest()
    return f"{header_b64}.{payload_b64}.{_b64url_encode(sig)}"


def _jwt_decode_hs256(*, token: str, secret: str) -> Dict[str, Any]:
    parts = token.split(".")
    if len(parts) != 3:
        raise ValueError("invalid_jwt_format")
    header_b64, payload_b64, sig_b64 = parts
    signing_input = f"{header_b64}.{payload_b64}".encode("ascii")
    expected_sig = hmac.new(secret.encode("utf-8"), signing_input, hashlib.sha256).digest()
    got_sig = _b64url_decode(sig_b64)
    if not hmac.compare_digest(expected_sig, got_sig):
        raise ValueError("invalid_jwt_signature")
    header = json.loads(_b64url_decode(header_b64).decode("utf-8"))
    if header.get("alg") != "HS256":
        raise ValueError("invalid_jwt_alg")
    payload = json.loads(_b64url_decode(payload_b64).decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("invalid_jwt_payload")
    return payload
