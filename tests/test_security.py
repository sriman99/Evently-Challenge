"""
Unit tests for security module
"""

import pytest
from datetime import datetime, timedelta
from jose import jwt, JWTError

from app.core.security import security_manager
from app.config import settings


@pytest.mark.unit
class TestPasswordHashing:
    """Test password hashing functionality"""

    def test_hash_password(self):
        """Test password hashing"""
        password = "TestPassword123!"
        hashed = security_manager.hash_password(password)

        assert hashed != password
        assert len(hashed) > 0
        assert "$2b$" in hashed  # bcrypt hash prefix

    def test_verify_password_correct(self):
        """Test verifying correct password"""
        password = "TestPassword123!"
        hashed = security_manager.hash_password(password)

        assert security_manager.verify_password(password, hashed) is True

    def test_verify_password_incorrect(self):
        """Test verifying incorrect password"""
        password = "TestPassword123!"
        wrong_password = "WrongPassword123!"
        hashed = security_manager.hash_password(password)

        assert security_manager.verify_password(wrong_password, hashed) is False

    def test_hash_password_uniqueness(self):
        """Test that same password produces different hashes"""
        password = "TestPassword123!"
        hash1 = security_manager.hash_password(password)
        hash2 = security_manager.hash_password(password)

        assert hash1 != hash2
        assert security_manager.verify_password(password, hash1) is True
        assert security_manager.verify_password(password, hash2) is True


@pytest.mark.unit
class TestJWTTokens:
    """Test JWT token functionality"""

    def test_create_access_token(self):
        """Test creating access token"""
        data = {"sub": "user123", "email": "test@example.com"}
        token = security_manager.create_access_token(data)

        assert token is not None
        assert len(token) > 0
        assert isinstance(token, str)

    def test_create_refresh_token(self):
        """Test creating refresh token"""
        data = {"sub": "user123", "email": "test@example.com"}
        token = security_manager.create_refresh_token(data)

        assert token is not None
        assert len(token) > 0
        assert isinstance(token, str)

    def test_decode_valid_token(self):
        """Test decoding valid token"""
        data = {"sub": "user123", "email": "test@example.com"}
        token = security_manager.create_access_token(data)
        decoded = security_manager.decode_token(token)

        assert decoded["sub"] == data["sub"]
        assert decoded["email"] == data["email"]
        assert decoded["type"] == "access"
        assert "exp" in decoded

    def test_decode_expired_token(self):
        """Test decoding expired token"""
        data = {"sub": "user123", "email": "test@example.com"}
        # Create token with negative expiry
        token = security_manager.create_access_token(
            data, expires_delta=timedelta(seconds=-1)
        )

        with pytest.raises(Exception):  # HTTPException in actual use
            security_manager.decode_token(token)

    def test_decode_invalid_token(self):
        """Test decoding invalid token"""
        invalid_token = "invalid.token.here"

        with pytest.raises(Exception):  # HTTPException in actual use
            security_manager.decode_token(invalid_token)

    def test_token_expiration_time(self):
        """Test token expiration time"""
        data = {"sub": "user123"}
        expires_delta = timedelta(minutes=15)
        token = security_manager.create_access_token(data, expires_delta)

        decoded = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM]
        )

        exp_time = datetime.fromtimestamp(decoded["exp"])
        now = datetime.utcnow()
        time_diff = exp_time - now

        # Allow 1 second tolerance for test execution time
        assert 14 * 60 <= time_diff.total_seconds() <= 15 * 60 + 1

    def test_verify_token_type_access(self):
        """Test verifying access token type"""
        data = {"sub": "user123"}
        token = security_manager.create_access_token(data)
        decoded = security_manager.decode_token(token)

        # Should not raise exception
        security_manager.verify_token_type(decoded, "access")

        # Should raise exception for wrong type
        with pytest.raises(Exception):
            security_manager.verify_token_type(decoded, "refresh")

    def test_verify_token_type_refresh(self):
        """Test verifying refresh token type"""
        data = {"sub": "user123"}
        token = security_manager.create_refresh_token(data)
        decoded = security_manager.decode_token(token)

        # Should not raise exception
        security_manager.verify_token_type(decoded, "refresh")

        # Should raise exception for wrong type
        with pytest.raises(Exception):
            security_manager.verify_token_type(decoded, "access")


@pytest.mark.unit
class TestTokenData:
    """Test token data handling"""

    def test_token_with_complete_data(self):
        """Test token with all user data"""
        data = {
            "sub": "user123",
            "email": "test@example.com",
            "role": "admin",
            "custom_field": "value"
        }
        token = security_manager.create_access_token(data)
        decoded = security_manager.decode_token(token)

        assert decoded["sub"] == data["sub"]
        assert decoded["email"] == data["email"]
        assert decoded["role"] == data["role"]
        assert decoded["custom_field"] == data["custom_field"]

    def test_token_with_minimal_data(self):
        """Test token with minimal data"""
        data = {"sub": "user123"}
        token = security_manager.create_access_token(data)
        decoded = security_manager.decode_token(token)

        assert decoded["sub"] == data["sub"]
        assert decoded["type"] == "access"
        assert "exp" in decoded

    def test_token_data_integrity(self):
        """Test that token data cannot be tampered with"""
        data = {"sub": "user123", "role": "user"}
        token = security_manager.create_access_token(data)

        # Tamper with token (change a character)
        tampered_token = token[:-1] + "X"

        with pytest.raises(Exception):
            security_manager.decode_token(tampered_token)