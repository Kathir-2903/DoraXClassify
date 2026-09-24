from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator

from app.utils.validators import normalize_email


class LoginRequest(BaseModel):
    email: str = Field(..., examples=["admin@classify.demo"])
    password: str = Field(..., min_length=1, examples=["Admin@123"])

    @field_validator("email")
    @classmethod
    def _email(cls, v: str) -> str:
        return normalize_email(v)


class UserOut(BaseModel):
    id: str
    name: str
    email: str
    role: Literal["admin", "sales"]
    title: Optional[str] = None
    is_active: bool = True


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserOut


class UserCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=120)
    email: str
    password: str = Field(..., min_length=8, max_length=128)
    role: Literal["admin", "sales"] = "sales"
    title: Optional[str] = Field(None, max_length=120)

    @field_validator("email")
    @classmethod
    def _email(cls, v: str) -> str:
        return normalize_email(v)
