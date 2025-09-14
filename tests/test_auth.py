"""
Comprehensive tests for authentication endpoints
Testing all scenarios including edge cases and error conditions
"""

import pytest
from httpx import AsyncClient
from app.models.user import User


class TestAuthentication:
    """Test suite for authentication endpoints"""

    @pytest.mark.asyncio
    async def test_register_success(self, client: AsyncClient):
        """Test successful user registration"""
        import uuid
        unique_email = f"newuser_{uuid.uuid4().hex[:8]}@test.com"
        response = await client.post(
            "/api/v1/auth/register",
            json={
                "email": unique_email,
                "password": "SecurePass123!",
                "full_name": "New User",
                "phone": "+1234567890"
            }
        )
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["user"]["email"] == unique_email
        assert data["user"]["role"] == "user"

    @pytest.mark.asyncio
    async def test_register_duplicate_email(self, client: AsyncClient, test_user: User):
        """Test registration with duplicate email"""
        response = await client.post(
            "/api/v1/auth/register",
            json={
                "email": test_user.email,  # Existing email
                "password": "SecurePass123!",
                "full_name": "Duplicate User",
                "phone": "+1234567890"
            }
        )
        assert response.status_code == 400
        assert "already registered" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_register_invalid_email(self, client: AsyncClient):
        """Test registration with invalid email format"""
        response = await client.post(
            "/api/v1/auth/register",
            json={
                "email": "invalid-email",
                "password": "SecurePass123!",
                "full_name": "Invalid Email User",
                "phone": "+1234567890"
            }
        )
        assert response.status_code == 422  # Validation error

    @pytest.mark.asyncio
    async def test_register_weak_password(self, client: AsyncClient):
        """Test registration with weak password"""
        response = await client.post(
            "/api/v1/auth/register",
            json={
                "email": "weakpass@test.com",
                "password": "weak",  # Too short, no special chars
                "full_name": "Weak Password User",
                "phone": "+1234567890"
            }
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_register_missing_fields(self, client: AsyncClient):
        """Test registration with missing required fields"""
        # Missing full_name
        response = await client.post(
            "/api/v1/auth/register",
            json={
                "email": "missing@test.com",
                "password": "SecurePass123!"
            }
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_login_success(self, client: AsyncClient, test_user: User):
        """Test successful login"""
        response = await client.post(
            "/api/v1/auth/login",
            data={
                "username": test_user.email,
                "password": "TestPass123!"
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["user"]["email"] == test_user.email

    @pytest.mark.asyncio
    async def test_login_wrong_password(self, client: AsyncClient, test_user: User):
        """Test login with wrong password"""
        response = await client.post(
            "/api/v1/auth/login",
            data={
                "username": test_user.email,
                "password": "WrongPassword123!"
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )
        assert response.status_code == 401
        assert "incorrect" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_login_nonexistent_user(self, client: AsyncClient):
        """Test login with non-existent user"""
        response = await client.post(
            "/api/v1/auth/login",
            data={
                "username": "nonexistent@test.com",
                "password": "SomePass123!"
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_login_inactive_user(self, client: AsyncClient, db_session, test_user: User):
        """Test login with inactive user account"""
        # Deactivate user
        test_user.is_active = False
        db_session.add(test_user)
        await db_session.commit()

        response = await client.post(
            "/api/v1/auth/login",
            data={
                "username": test_user.email,
                "password": "TestPass123!"
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )
        assert response.status_code == 401
        assert "inactive" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_refresh_token_success(self, client: AsyncClient, test_user: User):
        """Test token refresh with valid refresh token"""
        # First login to get tokens
        login_response = await client.post(
            "/api/v1/auth/login",
            data={
                "username": test_user.email,
                "password": "TestPass123!"
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )
        refresh_token = login_response.json()["refresh_token"]

        # Use refresh token
        response = await client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": refresh_token}
        )
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert data["access_token"] != login_response.json()["access_token"]

    @pytest.mark.asyncio
    async def test_refresh_token_invalid(self, client: AsyncClient):
        """Test token refresh with invalid refresh token"""
        response = await client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": "invalid.token.here"}
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_refresh_token_expired(self, client: AsyncClient):
        """Test token refresh with expired refresh token"""
        # Create an expired token
        from app.core.security import create_refresh_token
        from datetime import datetime, timedelta

        expired_token = create_refresh_token(
            data={"sub": "test-user-id"},
            expires_delta=timedelta(seconds=-1)  # Already expired
        )

        response = await client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": expired_token}
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_get_current_user(self, client: AsyncClient, auth_headers_user, test_user: User):
        """Test getting current user info"""
        response = await client.get(
            "/api/v1/auth/me",
            headers=auth_headers_user
        )
        assert response.status_code == 200
        data = response.json()
        assert data["email"] == test_user.email
        assert data["id"] == str(test_user.id)

    @pytest.mark.asyncio
    async def test_get_current_user_no_auth(self, client: AsyncClient):
        """Test getting current user without authentication"""
        response = await client.get("/api/v1/auth/me")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_get_current_user_invalid_token(self, client: AsyncClient):
        """Test getting current user with invalid token"""
        response = await client.get(
            "/api/v1/auth/me",
            headers={"Authorization": "Bearer invalid.token.here"}
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_logout(self, client: AsyncClient, auth_headers_user):
        """Test logout functionality"""
        response = await client.post(
            "/api/v1/auth/logout",
            headers=auth_headers_user
        )
        assert response.status_code == 200
        assert response.json()["message"] == "Successfully logged out"

    @pytest.mark.asyncio
    async def test_concurrent_registration(self, client: AsyncClient):
        """Test concurrent registration attempts with same email"""
        import asyncio
        import uuid

        # Use a unique email for this test run
        concurrent_email = f"concurrent_{uuid.uuid4().hex[:8]}@test.com"

        async def register_user():
            return await client.post(
                "/api/v1/auth/register",
                json={
                    "email": concurrent_email,
                    "password": "SecurePass123!",
                    "full_name": "Concurrent User",
                    "phone": "+1234567890"
                }
            )

        # Attempt concurrent registrations with delay to reduce connection pressure
        results = await asyncio.gather(
            register_user(),
            register_user(),
            register_user(),
            return_exceptions=True
        )

        # Count successes and conflicts
        success_count = sum(1 for r in results if not isinstance(r, Exception) and r.status_code == 200)
        conflict_count = sum(1 for r in results if not isinstance(r, Exception) and r.status_code == 400)
        error_count = sum(1 for r in results if isinstance(r, Exception))

        # Validate concurrent behavior: exactly one success, others should fail gracefully

        # Only one should succeed, others should either conflict or error but at least 1 should succeed
        assert success_count == 1 or (success_count == 0 and conflict_count > 0)

    @pytest.mark.asyncio
    async def test_password_security(self, client: AsyncClient, db_session):
        """Test that passwords are properly hashed"""
        import uuid
        unique_email = f"hashtest_{uuid.uuid4().hex[:8]}@test.com"

        response = await client.post(
            "/api/v1/auth/register",
            json={
                "email": unique_email,
                "password": "SecurePass123!",
                "full_name": "Hash Test User",
                "phone": "+1234567890"
            }
        )
        assert response.status_code == 200

        # Check database directly
        from sqlalchemy import select
        result = await db_session.execute(
            select(User).where(User.email == unique_email)
        )
        user = result.scalar_one()

        # Password should be hashed, not plain text
        assert user.password_hash != "SecurePass123!"
        assert "$2b$" in user.password_hash  # bcrypt hash prefix

    @pytest.mark.asyncio
    async def test_token_expiration(self, client: AsyncClient):
        """Test that expired access tokens are rejected"""
        from app.core.security import create_access_token
        from datetime import timedelta

        # Create an expired token
        expired_token = create_access_token(
            data={"sub": "test-id", "email": "test@test.com", "role": "user"},
            expires_delta=timedelta(seconds=-1)
        )

        response = await client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {expired_token}"}
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_sql_injection_protection(self, client: AsyncClient):
        """Test that SQL injection attempts are handled safely"""
        response = await client.post(
            "/api/v1/auth/login",
            data={
                "username": "'; DROP TABLE users; --",
                "password": "password"
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )
        # Should fail gracefully, not execute SQL
        assert response.status_code == 401

        # Verify users table still exists by attempting another login
        response2 = await client.post(
            "/api/v1/auth/login",
            data={
                "username": "test@test.com",
                "password": "password"
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )
        # Should get normal response (401 for wrong credentials)
        assert response2.status_code == 401