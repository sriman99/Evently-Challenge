"""
OAuth2 Service for Social Login
Handles Google, Facebook, and GitHub authentication
"""

from authlib.integrations.starlette_client import OAuth, OAuthError
from typing import Dict, Optional
import httpx
import logging
from app.core.config import settings
from app.models.user import User
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.core.security import security_manager
import uuid

logger = logging.getLogger(__name__)


class OAuth2Service:
    """Service for handling OAuth2 authentication"""

    def __init__(self):
        self.oauth = OAuth()
        self._setup_providers()

    def _setup_providers(self):
        """Setup OAuth2 providers"""

        # Google OAuth2
        self.oauth.register(
            name='google',
            client_id=settings.GOOGLE_CLIENT_ID,
            client_secret=settings.GOOGLE_CLIENT_SECRET,
            server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
            client_kwargs={
                'scope': 'openid email profile'
            }
        )

        # Facebook OAuth2
        self.oauth.register(
            name='facebook',
            client_id=settings.FACEBOOK_CLIENT_ID,
            client_secret=settings.FACEBOOK_CLIENT_SECRET,
            authorize_url='https://www.facebook.com/dialog/oauth',
            access_token_url='https://graph.facebook.com/oauth/access_token',
            client_kwargs={
                'scope': 'email public_profile'
            }
        )

        # GitHub OAuth2
        self.oauth.register(
            name='github',
            client_id=settings.GITHUB_CLIENT_ID,
            client_secret=settings.GITHUB_CLIENT_SECRET,
            authorize_url='https://github.com/login/oauth/authorize',
            access_token_url='https://github.com/login/oauth/access_token',
            client_kwargs={
                'scope': 'user:email'
            }
        )

    async def get_authorization_url(
        self,
        provider: str,
        redirect_uri: str
    ) -> str:
        """Get OAuth2 authorization URL"""
        try:
            client = self.oauth.create_client(provider)
            if not client:
                raise ValueError(f"Invalid provider: {provider}")

            authorization_url = await client.create_authorization_url(redirect_uri)
            return authorization_url

        except Exception as e:
            logger.error(f"Error getting authorization URL: {str(e)}")
            raise

    async def handle_callback(
        self,
        provider: str,
        code: str,
        redirect_uri: str,
        db: AsyncSession
    ) -> Dict:
        """Handle OAuth2 callback and create/login user"""
        try:
            client = self.oauth.create_client(provider)
            if not client:
                raise ValueError(f"Invalid provider: {provider}")

            # Exchange code for token
            token = await client.fetch_token(
                code=code,
                redirect_uri=redirect_uri
            )

            # Get user info based on provider
            user_info = await self._get_user_info(provider, token['access_token'])

            # Create or update user
            user = await self._create_or_update_user(
                db,
                provider,
                user_info
            )

            # Generate JWT token
            access_token = security_manager.create_access_token(
                data={
                    "sub": str(user.id),
                    "email": user.email,
                    "provider": provider
                }
            )

            return {
                "access_token": access_token,
                "token_type": "bearer",
                "user": {
                    "id": str(user.id),
                    "email": user.email,
                    "full_name": user.full_name,
                    "provider": provider
                }
            }

        except OAuthError as e:
            logger.error(f"OAuth error: {str(e)}")
            raise Exception(f"Authentication failed: {str(e)}")
        except Exception as e:
            logger.error(f"Error handling OAuth callback: {str(e)}")
            raise

    async def _get_user_info(
        self,
        provider: str,
        access_token: str
    ) -> Dict:
        """Get user information from OAuth provider"""
        async with httpx.AsyncClient() as client:
            headers = {"Authorization": f"Bearer {access_token}"}

            if provider == "google":
                response = await client.get(
                    "https://www.googleapis.com/oauth2/v2/userinfo",
                    headers=headers
                )
                data = response.json()
                return {
                    "email": data.get("email"),
                    "full_name": data.get("name"),
                    "picture": data.get("picture"),
                    "provider_id": data.get("id")
                }

            elif provider == "facebook":
                response = await client.get(
                    "https://graph.facebook.com/me",
                    params={"fields": "id,email,name,picture"},
                    headers=headers
                )
                data = response.json()
                return {
                    "email": data.get("email"),
                    "full_name": data.get("name"),
                    "picture": data.get("picture", {}).get("data", {}).get("url"),
                    "provider_id": data.get("id")
                }

            elif provider == "github":
                # Get user data
                response = await client.get(
                    "https://api.github.com/user",
                    headers=headers
                )
                user_data = response.json()

                # Get email if not public
                if not user_data.get("email"):
                    email_response = await client.get(
                        "https://api.github.com/user/emails",
                        headers=headers
                    )
                    emails = email_response.json()
                    primary_email = next(
                        (e["email"] for e in emails if e["primary"]),
                        None
                    )
                    user_data["email"] = primary_email

                return {
                    "email": user_data.get("email"),
                    "full_name": user_data.get("name") or user_data.get("login"),
                    "picture": user_data.get("avatar_url"),
                    "provider_id": str(user_data.get("id"))
                }

            else:
                raise ValueError(f"Unsupported provider: {provider}")

    async def _create_or_update_user(
        self,
        db: AsyncSession,
        provider: str,
        user_info: Dict
    ) -> User:
        """Create or update user from OAuth data"""
        try:
            # Check if user exists by email
            result = await db.execute(
                select(User).where(User.email == user_info["email"])
            )
            user = result.scalar_one_or_none()

            if user:
                # Update existing user
                user.oauth_provider = provider
                user.oauth_provider_id = user_info["provider_id"]
                if user_info.get("picture"):
                    user.profile_picture = user_info["picture"]

            else:
                # Create new user
                user = User(
                    email=user_info["email"],
                    full_name=user_info["full_name"],
                    oauth_provider=provider,
                    oauth_provider_id=user_info["provider_id"],
                    profile_picture=user_info.get("picture"),
                    # Set a random password for OAuth users
                    password_hash=security_manager.hash_password(str(uuid.uuid4())),
                    is_verified=True  # OAuth users are pre-verified
                )
                db.add(user)

            await db.commit()
            await db.refresh(user)

            return user

        except Exception as e:
            await db.rollback()
            logger.error(f"Error creating/updating OAuth user: {str(e)}")
            raise

    async def unlink_provider(
        self,
        db: AsyncSession,
        user_id: str,
        provider: str
    ) -> bool:
        """Unlink OAuth provider from user account"""
        try:
            user = await db.get(User, user_id)
            if not user:
                raise ValueError("User not found")

            if user.oauth_provider == provider:
                user.oauth_provider = None
                user.oauth_provider_id = None
                await db.commit()
                return True

            return False

        except Exception as e:
            await db.rollback()
            logger.error(f"Error unlinking provider: {str(e)}")
            raise


# Initialize global OAuth service
oauth_service = OAuth2Service()