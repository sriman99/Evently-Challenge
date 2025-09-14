"""
Authentication endpoints
"""

from datetime import timedelta
from typing import Any
from fastapi import APIRouter, Depends, HTTPException, status, Body
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_session
from app.core.security import (
    create_access_token,
    create_refresh_token,
    get_password_hash,
    verify_password,
    get_current_user,
    decode_token,
    oauth2_scheme
)
from app.models.user import User, UserRole
from app.schemas.user import UserCreate, UserResponse, Token, TokenRefresh
from app.config import settings

router = APIRouter()


@router.post("/register", response_model=Token)
async def register(
    user_data: UserCreate,
    db: AsyncSession = Depends(get_session)
) -> Any:
    """
    Register a new user
    """
    # Check if user already exists
    stmt = select(User).where(User.email == user_data.email)
    result = await db.execute(stmt)
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )

    # Create new user
    user = User(
        email=user_data.email,
        full_name=user_data.full_name,
        phone=user_data.phone,
        password_hash=get_password_hash(user_data.password),
        role=UserRole.USER,
        is_active=True
    )

    db.add(user)
    await db.commit()
    await db.refresh(user)

    # Create tokens
    access_token = create_access_token(
        data={"sub": str(user.id), "email": user.email, "role": user.role.value}
    )
    refresh_token = create_refresh_token(
        data={"sub": str(user.id)}
    )

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "user": UserResponse.model_validate(user)
    }


@router.post("/login", response_model=Token)
async def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_session)
) -> Any:
    """
    OAuth2 compatible token login
    """
    # Find user by email
    stmt = select(User).where(User.email == form_data.username)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()

    if not user or not verify_password(form_data.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password"
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account is inactive"
        )

    # Create tokens
    access_token = create_access_token(
        data={"sub": str(user.id), "email": user.email, "role": user.role.value}
    )
    refresh_token = create_refresh_token(
        data={"sub": str(user.id)}
    )

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "user": UserResponse.model_validate(user)
    }


@router.post("/refresh", response_model=Token)
async def refresh_token(
    token_data: TokenRefresh,
    db: AsyncSession = Depends(get_session)
) -> Any:
    """
    Refresh access token using refresh token
    """
    try:
        payload = decode_token(token_data.refresh_token)
        user_id = payload.get("sub")

        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid refresh token"
            )

        # Get user
        stmt = select(User).where(User.id == user_id)
        result = await db.execute(stmt)
        user = result.scalar_one_or_none()

        if not user or not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found or inactive"
            )

        # Create new tokens
        access_token = create_access_token(
            data={"sub": str(user.id), "email": user.email, "role": user.role.value}
        )
        new_refresh_token = create_refresh_token(
            data={"sub": str(user.id)}
        )

        return {
            "access_token": access_token,
            "refresh_token": new_refresh_token,
            "token_type": "bearer",
            "user": UserResponse.model_validate(user)
        }

    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token"
        )


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(
    current_user: User = Depends(get_current_user)
) -> Any:
    """
    Get current user information
    """
    return current_user


@router.post("/logout")
async def logout(
    current_user: User = Depends(get_current_user),
    token: str = Depends(oauth2_scheme)
) -> Any:
    """
    Logout user and blacklist token
    """
    from app.core.security import SecurityManager

    # Blacklist the current token
    await SecurityManager.blacklist_token(token)

    return {"message": "Successfully logged out"}