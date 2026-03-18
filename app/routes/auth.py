"""
Auth routes. Register, login, refresh, verify, me.
Routes only handle HTTP. All logic in auth_service.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_current_user, get_db
from app.models.user import User
from app.schemas.auth import (
    AuthResponse,
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    UserResponse,
)
from app.services.auth_service import (
    decode_token,
    login_user,
    refresh_tokens,
    register_user,
)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register")
async def register(data: RegisterRequest, db: AsyncSession = Depends(get_db)) -> dict:
    user, tokens = await register_user(db, data)
    return {
        "success": True,
        "data": AuthResponse(
            user=UserResponse.model_validate(user),
            tokens=tokens,
        ).model_dump(),
    }


@router.post("/login")
async def login(data: LoginRequest, db: AsyncSession = Depends(get_db)) -> dict:
    user, tokens = await login_user(db, data.email, data.password)
    return {
        "success": True,
        "data": AuthResponse(
            user=UserResponse.model_validate(user),
            tokens=tokens,
        ).model_dump(),
    }


@router.post("/refresh")
async def refresh(data: RefreshRequest, db: AsyncSession = Depends(get_db)) -> dict:
    user, tokens = await refresh_tokens(db, data.refresh_token)
    return {
        "success": True,
        "data": AuthResponse(
            user=UserResponse.model_validate(user),
            tokens=tokens,
        ).model_dump(),
    }


@router.get("/verify")
async def verify(current_user: User = Depends(get_current_user)) -> dict:
    return {
        "success": True,
        "data": {"valid": True, "user_id": str(current_user.id)},
    }


@router.get("/me")
async def me(current_user: User = Depends(get_current_user)) -> dict:
    return {
        "success": True,
        "data": UserResponse.model_validate(current_user).model_dump(),
    }
