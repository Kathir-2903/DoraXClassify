import time
from collections import defaultdict, deque
from typing import Deque, Dict

from fastapi import APIRouter, Depends, Request
from pymongo.errors import DuplicateKeyError

from app.config.settings import settings
from app.database.mongodb import Collections, get_db
from app.dependencies.auth import CurrentUser, get_current_user, require_admin
from app.middleware.error_handler import AppError
from app.models.user import new_user_document, public_user
from app.schemas.auth import LoginRequest, TokenResponse, UserCreate, UserOut
from app.services.audit_service import log_activity
from app.services.lead_service import list_sales_people
from app.utils.datetime_utils import utcnow
from app.utils.security import create_access_token, verify_password

router = APIRouter(tags=["Auth & Users"])

_attempts: Dict[str, Deque[float]] = defaultdict(deque)


def _rate_limited(key: str) -> bool:
    now = time.monotonic()
    window = _attempts[key]
    while window and now - window[0] > settings.login_window_seconds:
        window.popleft()
    return len(window) >= settings.login_max_attempts


@router.post("/api/auth/login", response_model=TokenResponse, summary="Sign in with email and password",
             responses={401: {"description": "Invalid credentials"}, 429: {"description": "Too many attempts"}})
async def login(body: LoginRequest, request: Request):
    key = f"{body.email}|{request.client.host if request.client else '-'}"
    if _rate_limited(key):
        raise AppError("Too many sign-in attempts. Please wait a few minutes.", 429, "rate_limited")
    user = await get_db()[Collections.USERS].find_one({"email": body.email})
    if not user or not user.get("is_active", True) or not verify_password(body.password, user.get("password_hash", "")):
        _attempts[key].append(time.monotonic())
        raise AppError("Invalid email or password", 401, "invalid_credentials")
    _attempts.pop(key, None)
    await get_db()[Collections.USERS].update_one({"_id": user["_id"]}, {"$set": {"last_login_at": utcnow()}})
    await log_activity(user, "auth.login", "user", user["_id"])
    return {
        "access_token": create_access_token(str(user["_id"]), user["role"]),
        "token_type": "bearer",
        "expires_in": settings.jwt_expire_minutes * 60,
        "user": public_user(user),
    }


@router.get("/api/auth/me", response_model=UserOut, summary="Current user")
async def me(user: CurrentUser = Depends(get_current_user)):
    return public_user(user)


@router.get("/api/users/sales-people", summary="Assignable sales people")
async def sales_people(user: CurrentUser = Depends(get_current_user)):
    people = await list_sales_people()
    if not user.is_admin:
        people = [p for p in people if p["_id"] == user["_id"]]
    return [public_user(p) for p in people]


@router.get("/api/admin/users", summary="List users (admin)")
async def list_users(admin: CurrentUser = Depends(require_admin)):
    users = await get_db()[Collections.USERS].find({}, {"password_hash": 0}).sort("name", 1).to_list(length=None)
    return [public_user(u) | {"last_login_at": u.get("last_login_at"), "is_demo": u.get("is_demo", False)} for u in users]


@router.post("/api/admin/users", response_model=UserOut, status_code=201, summary="Create a user (admin)")
async def create_user(body: UserCreate, admin: CurrentUser = Depends(require_admin)):
    doc = new_user_document(body.name, body.email, body.password, body.role, body.title)
    try:
        result = await get_db()[Collections.USERS].insert_one(doc)
    except DuplicateKeyError:
        raise AppError("A user with this email already exists", 409, "duplicate_user")
    doc["_id"] = result.inserted_id
    await log_activity(admin, "user.created", "user", doc["_id"], {"role": body.role})
    return public_user(doc)
