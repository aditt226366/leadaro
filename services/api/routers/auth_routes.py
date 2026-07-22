from fastapi import APIRouter, Depends, HTTPException, status

import db
from auth import Principal, current_user, make_token, verify_password
from schemas import LoginIn, TokenOut

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenOut)
async def login(body: LoginIn):
    u = await db.fetchrow(
        """SELECT id, org_id, name, email, role, password_hash, is_active
           FROM users WHERE lower(email) = lower($1)""",
        body.email,
    )
    # Same message for unknown user and wrong password — don't leak which.
    if not u or not verify_password(body.password, u["password_hash"]):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid credentials")
    if not u["is_active"]:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "account disabled")

    return TokenOut(
        token=make_token(str(u["id"]), str(u["org_id"]), u["role"]),
        user={
            "id": str(u["id"]), "name": u["name"],
            "email": u["email"], "role": u["role"],
        },
    )


@router.get("/me")
async def me(user: Principal = Depends(current_user)):
    u = await db.fetchrow(
        "SELECT id, name, email, role, department FROM users WHERE id = $1",
        user.user_id,
    )
    if not u:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "user not found")
    return {**{k: str(v) if k == "id" else v for k, v in u.items()},
            "permissions": sorted(user.perms)}
