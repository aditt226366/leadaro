"""
Auth + the role/permission matrix from FRD §15.

Permissions are enforced here, in the API layer. The UI hides controls the user
can't use, but hiding a button is not access control — every mutating route
declares the permission it needs.
"""
import os
from datetime import datetime, timedelta, timezone

import bcrypt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt

import db

JWT_SECRET = os.environ.get("JWT_SECRET", "dev-secret-change-me")
JWT_ALG = "HS256"
TOKEN_TTL_HOURS = 12

bearer = HTTPBearer(auto_error=False)

# ── FRD §15: 7 roles × 9 permissions ────────────────────────────────────────

PERMISSIONS = (
    "create_campaign",
    "delete_campaign",
    "pause_campaign",
    "export_reports",
    "download_recordings",
    "modify_scripts",
    "access_analytics",
    "manage_numbers",
    "approve_campaigns",
)

ROLE_PERMS: dict[str, set[str]] = {
    "admin": set(PERMISSIONS),
    "manager": {
        "create_campaign", "pause_campaign", "export_reports",
        "download_recordings", "modify_scripts", "access_analytics",
        "approve_campaigns",
    },
    "campaign_operator": {
        "create_campaign", "pause_campaign", "modify_scripts", "access_analytics",
    },
    "sales_rep": {"access_analytics", "download_recordings"},
    "recruiter": {"access_analytics", "download_recordings"},
    "analyst": {"access_analytics", "export_reports"},
    "viewer": {"access_analytics"},
}


def hash_password(raw: str) -> str:
    # bcrypt hashes at most 72 bytes and silently ignores the rest, so long
    # passphrases would otherwise collide on their first 72 bytes. Truncating
    # explicitly makes that boundary visible rather than surprising.
    return bcrypt.hashpw(raw.encode()[:72], bcrypt.gensalt()).decode()


def verify_password(raw: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(raw.encode()[:72], hashed.encode())
    except ValueError:
        return False  # malformed stored hash


def make_token(user_id: str, org_id: str, role: str) -> str:
    now = datetime.now(timezone.utc)
    return jwt.encode(
        {
            "sub": user_id,
            "org": org_id,
            "role": role,
            "iat": now,
            "exp": now + timedelta(hours=TOKEN_TTL_HOURS),
        },
        JWT_SECRET,
        algorithm=JWT_ALG,
    )


class Principal:
    def __init__(self, user_id: str, org_id: str, role: str):
        self.user_id = user_id
        self.org_id = org_id
        self.role = role
        self.perms = ROLE_PERMS.get(role, set())

    def can(self, perm: str) -> bool:
        return perm in self.perms


async def current_user(
    cred: HTTPAuthorizationCredentials | None = Depends(bearer),
) -> Principal:
    if cred is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing bearer token")
    try:
        claims = jwt.decode(cred.credentials, JWT_SECRET, algorithms=[JWT_ALG])
    except JWTError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid or expired token")
    return Principal(claims["sub"], claims["org"], claims["role"])


def requires(perm: str):
    """Route dependency: `_=Depends(requires("create_campaign"))`."""
    if perm not in PERMISSIONS:
        raise ValueError(f"unknown permission: {perm}")

    async def guard(user: Principal = Depends(current_user)) -> Principal:
        if not user.can(perm):
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                f"role '{user.role}' lacks permission '{perm}'",
            )
        return user

    return guard


async def audit(
    org_id: str, actor_id: str | None, action: str,
    entity: str | None = None, entity_id: str | None = None, detail: dict | None = None,
) -> None:
    """Every state change that a regulator might ask about lands here."""
    await db.execute(
        """INSERT INTO audit_log (org_id, actor_id, action, entity, entity_id, detail)
           VALUES ($1,$2,$3,$4,$5,$6)""",
        org_id, actor_id, action, entity, entity_id, detail or {},
    )
