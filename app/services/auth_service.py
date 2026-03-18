"""
Auth service. Handles registration (atomic), login, JWT generation, refresh.
Registration = user + seed in ONE transaction. Partial state impossible.
"""

import uuid
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.user import User
from app.schemas.auth import AuthTokens, RegisterRequest
from app.services.seed_service import seed_user_defaults


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=12)).decode()


def verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode(), password_hash.encode())


def create_access_token(user_id: uuid.UUID) -> str:
    payload = {
        "sub": str(user_id),
        "type": "access",
        "exp": datetime.now(timezone.utc)
        + timedelta(minutes=settings.JWT_EXPIRY_MINUTES),
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def create_refresh_token(user_id: uuid.UUID) -> str:
    payload = {
        "sub": str(user_id),
        "type": "refresh",
        "exp": datetime.now(timezone.utc)
        + timedelta(days=settings.REFRESH_TOKEN_EXPIRY_DAYS),
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def decode_token(token: str) -> dict:
    try:
        return jwt.decode(
            token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM]
        )
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token has expired.")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token.")


def generate_tokens(user_id: uuid.UUID) -> AuthTokens:
    return AuthTokens(
        access_token=create_access_token(user_id),
        refresh_token=create_refresh_token(user_id),
    )


async def register_user(db: AsyncSession, data: RegisterRequest) -> tuple[User, AuthTokens]:
    """
    Atomic registration: user + seed defaults in ONE transaction.
    If seeding fails, user creation ROLLS BACK. No partial state ever.
    """
    # Check if email exists
    existing = await db.execute(select(User).where(User.email == data.email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Email already registered.")

    # BEGIN ATOMIC OPERATION
    async with db.begin_nested():
        # Create user
        user = User(
            email=data.email,
            password_hash=hash_password(data.password),
            name=data.name,
            is_seeded=False,
        )
        db.add(user)
        await db.flush()  # Get the user.id

        # Seed defaults (12 categories + 2 accounts)
        await seed_user_defaults(db, user.id)

        # Mark as seeded
        user.is_seeded = True

    await db.commit()
    await db.refresh(user)

    tokens = generate_tokens(user.id)
    return user, tokens


async def login_user(db: AsyncSession, email: str, password: str) -> tuple[User, AuthTokens]:
    """Login: verify credentials, check is_seeded, return tokens."""
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()

    if not user or not verify_password(password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password.")

    # V1 fix: if somehow user exists but isn't seeded, re-seed
    if not user.is_seeded:
        async with db.begin_nested():
            await seed_user_defaults(db, user.id)
            user.is_seeded = True
        await db.commit()
        await db.refresh(user)

    tokens = generate_tokens(user.id)
    return user, tokens


async def refresh_tokens(db: AsyncSession, refresh_token: str) -> tuple[User, AuthTokens]:
    """Exchange refresh token for new access + refresh tokens."""
    payload = decode_token(refresh_token)

    if payload.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Invalid token type. Expected refresh token.")

    user_id = uuid.UUID(payload["sub"])
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=401, detail="User not found.")

    tokens = generate_tokens(user.id)
    return user, tokens


async def get_user_by_id(db: AsyncSession, user_id: uuid.UUID) -> User:
    """Get user by ID. Used by get_current_user dependency."""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=401, detail="User not found.")
    return user
