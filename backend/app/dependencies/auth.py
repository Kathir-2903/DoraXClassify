"""Authentication and role-based access control dependencies."""
from typing import Any, Dict, Optional

import jwt
from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.constants.analysis_status import Role
from app.database.mongodb import Collections, get_db
from app.middleware.error_handler import AppError, ForbiddenError
from app.utils.security import decode_token
from app.utils.validators import maybe_object_id

bearer = HTTPBearer(auto_error=False, description="JWT from POST /api/auth/login")


class CurrentUser(dict):
    """The authenticated user document (dict) with convenience accessors."""

    @property
    def id(self) -> str:
        return str(self["_id"])

    @property
    def role(self) -> str:
        return self.get("role", Role.SALES.value)

    @property
    def is_admin(self) -> bool:
        return self.role == Role.ADMIN.value

    @property
    def name(self) -> str:
        return self.get("name", "")


def _unauthorized(message: str = "Authentication required") -> AppError:
    return AppError(message, status_code=401, code="unauthorized")


async def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer),
) -> CurrentUser:
    if credentials is None or not credentials.credentials:
        raise _unauthorized()
    try:
        payload = decode_token(credentials.credentials, "access")
    except jwt.ExpiredSignatureError:
        raise _unauthorized("Your session has expired. Please sign in again.")
    except jwt.InvalidTokenError:
        raise _unauthorized("Invalid authentication token")
    user_id = maybe_object_id(payload.get("sub"))
    if user_id is None:
        raise _unauthorized("Invalid authentication token")
    user = await get_db()[Collections.USERS].find_one({"_id": user_id}, {"password_hash": 0})
    if not user or not user.get("is_active", True):
        raise _unauthorized("Account is disabled or no longer exists")
    request.state.user_id = str(user_id)
    return CurrentUser(user)


async def require_admin(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
    if not user.is_admin:
        raise ForbiddenError("Administrator access required")
    return user


async def require_sales(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
    if user.is_admin:
        raise ForbiddenError("This action is only available to sales users")
    return user


def scope_filter(user: CurrentUser, field: str = "sales_person_id", requested: Optional[str] = None) -> Dict[str, Any]:
    """Mongo filter restricting sales users to their own records.

    Admins see everything, optionally narrowed to `requested` sales person."""
    if user.is_admin:
        oid = maybe_object_id(requested)
        return {field: oid} if oid else {}
    return {field: user["_id"]}


def ensure_owner(user: CurrentUser, doc: Dict[str, Any], field: str = "sales_person_id") -> None:
    if user.is_admin:
        return
    if doc.get(field) != user["_id"]:
        raise ForbiddenError()
