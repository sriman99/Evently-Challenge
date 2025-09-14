"""
Security utilities for authentication and authorization
"""

from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
import logging
import time

from app.config import settings

logger = logging.getLogger(__name__)

# Password hashing context
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# OAuth2 scheme
oauth2_scheme = OAuth2PasswordBearer(tokenUrl=f"{settings.API_PREFIX}/auth/login")

# Create standalone functions for easier access
verify_password = lambda plain, hashed: pwd_context.verify(plain, hashed)
get_password_hash = lambda password: pwd_context.hash(password)


class SecurityManager:
    """
    Security manager for authentication and authorization
    """

    @staticmethod
    def verify_password(plain_password: str, hashed_password: str) -> bool:
        """
        Verify a plain password against a hashed password
        """
        return pwd_context.verify(plain_password, hashed_password)

    @staticmethod
    def hash_password(password: str) -> str:
        """
        Hash a password
        """
        return pwd_context.hash(password)

    @staticmethod
    def create_access_token(
        data: Dict[str, Any],
        expires_delta: Optional[timedelta] = None
    ) -> str:
        """
        Create a JWT access token
        """
        to_encode = data.copy()
        if expires_delta:
            expire = datetime.utcnow() + expires_delta
        else:
            expire = datetime.utcnow() + timedelta(
                minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES
            )

        # Add high precision timestamp to ensure token uniqueness
        to_encode.update({
            "exp": expire,
            "type": "access",
            "iat": time.time(),  # High precision issued at time
        })

        encoded_jwt = jwt.encode(
            to_encode,
            settings.JWT_SECRET_KEY,
            algorithm=settings.JWT_ALGORITHM
        )
        return encoded_jwt

    @staticmethod
    def create_refresh_token(
        data: Dict[str, Any],
        expires_delta: Optional[timedelta] = None
    ) -> str:
        """
        Create a JWT refresh token
        """
        to_encode = data.copy()
        if expires_delta:
            expire = datetime.utcnow() + expires_delta
        else:
            expire = datetime.utcnow() + timedelta(
                days=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS
            )

        # Add high precision timestamp to ensure token uniqueness
        to_encode.update({
            "exp": expire,
            "type": "refresh",
            "iat": time.time(),  # High precision issued at time
        })

        encoded_jwt = jwt.encode(
            to_encode,
            settings.JWT_SECRET_KEY,
            algorithm=settings.JWT_ALGORITHM
        )
        return encoded_jwt

    @staticmethod
    async def is_token_blacklisted(token: str) -> bool:
        """
        Check if token is blacklisted
        """
        try:
            from app.core.redis import redis_manager
            client = await redis_manager.get_client()
            token_hash = jwt.get_unverified_header(token).get('jti', token[-10:])  # Use last 10 chars as fallback
            is_blacklisted = await client.get(f"blacklist:{token_hash}")
            return is_blacklisted is not None
        except Exception as e:
            logger.error(f"Error checking token blacklist: {e}")
            return False  # Fail open for availability

    @staticmethod
    async def blacklist_token(token: str, expires_at: Optional[datetime] = None):
        """
        Add token to blacklist until expiration
        """
        try:
            from app.core.redis import redis_manager
            client = await redis_manager.get_client()

            # Extract expiration from token if not provided
            if not expires_at:
                payload = jwt.decode(token, options={"verify_signature": False})
                expires_at = datetime.fromtimestamp(payload.get('exp', 0))

            token_hash = jwt.get_unverified_header(token).get('jti', token[-10:])
            ttl = max(1, int((expires_at - datetime.utcnow()).total_seconds()))
            await client.setex(f"blacklist:{token_hash}", ttl, "1")
        except Exception as e:
            logger.error(f"Error blacklisting token: {e}")

    @staticmethod
    async def decode_token(token: str) -> Dict[str, Any]:
        """
        Decode and verify a JWT token, checking blacklist first
        """
        # Check blacklist first
        if await SecurityManager.is_token_blacklisted(token):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token has been invalidated",
                headers={"WWW-Authenticate": "Bearer"},
            )

        try:
            payload = jwt.decode(
                token,
                settings.JWT_SECRET_KEY,
                algorithms=[settings.JWT_ALGORITHM]
            )
            return payload
        except JWTError as e:
            logger.error(f"JWT decode error: {e}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Could not validate credentials",
                headers={"WWW-Authenticate": "Bearer"},
            )

    @staticmethod
    def verify_token_type(payload: Dict[str, Any], expected_type: str):
        """
        Verify token type (access or refresh)
        """
        token_type = payload.get("type")
        if token_type != expected_type:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Invalid token type. Expected {expected_type}",
                headers={"WWW-Authenticate": "Bearer"},
            )


# Create global security manager
security_manager = SecurityManager()


async def get_current_user_id(token: str = Depends(oauth2_scheme)) -> str:
    """
    Get current user ID from JWT token
    """
    try:
        payload = security_manager.decode_token(token)
        security_manager.verify_token_type(payload, "access")

        user_id = payload.get("sub")
        if user_id is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Could not validate credentials",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return user_id
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )


async def get_current_user(token: str = Depends(oauth2_scheme)):
    """
    Get current user from JWT token with blacklist checking
    """
    from sqlalchemy.ext.asyncio import AsyncSession
    from sqlalchemy import select
    from app.models.user import User
    from app.core.database import async_session

    try:
        payload = await SecurityManager.decode_token(token)
        user_id = payload.get("sub")

        if user_id is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Could not validate credentials",
                headers={"WWW-Authenticate": "Bearer"},
            )

        # Get user from database
        async with async_session() as session:
            stmt = select(User).where(User.id == user_id)
            result = await session.execute(stmt)
            user = result.scalar_one_or_none()

            if not user:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="User not found",
                    headers={"WWW-Authenticate": "Bearer"},
                )

            return user

    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )


async def require_admin(current_user: Dict = Depends(get_current_user)) -> Dict:
    """
    Require admin role for endpoint
    """
    if current_user.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )
    return current_user


def create_access_token(data: Dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
    """
    Create access token helper function
    """
    if expires_delta is None:
        expires_delta = timedelta(minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES)
    return security_manager.create_access_token(data, expires_delta)


def create_refresh_token(data: Dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
    """
    Create refresh token helper function
    """
    if expires_delta is None:
        expires_delta = timedelta(days=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS)
    return security_manager.create_refresh_token(data, expires_delta)


def decode_token(token: str) -> Dict[str, Any]:
    """
    Decode token helper function
    """
    return security_manager.decode_token(token)


async def require_organizer(current_user: Dict = Depends(get_current_user)) -> Dict:
    """
    Require organizer or admin role for endpoint
    """
    if current_user.get("role") not in ["admin", "organizer"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Organizer access required"
        )
    return current_user


class RateLimiter:
    """
    Rate limiter for API endpoints
    """

    def __init__(self, max_requests: int, window: int = 60):
        self.max_requests = max_requests
        self.window = window

    async def __call__(self, token: Optional[str] = Depends(oauth2_scheme)):
        """
        Check rate limit for user
        """
        if not settings.RATE_LIMIT_ENABLED:
            return

        from app.core.redis import redis_manager

        # Get user ID from token if provided
        user_id = "anonymous"
        if token:
            try:
                payload = security_manager.decode_token(token)
                user_id = payload.get("sub", "anonymous")
            except:
                pass

        # Check rate limit
        key = f"user:{user_id}:requests"
        is_limited, count = await redis_manager.is_rate_limited(
            key, self.max_requests, self.window
        )

        if is_limited:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Rate limit exceeded. Max {self.max_requests} requests per {self.window} seconds",
                headers={
                    "X-RateLimit-Limit": str(self.max_requests),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(self.window)
                }
            )