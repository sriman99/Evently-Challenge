"""
Two-Factor Authentication Service
Handles TOTP and SMS-based 2FA
"""

import pyotp
import qrcode
from io import BytesIO
import base64
from typing import Dict, Optional
from datetime import datetime, timedelta
import secrets
import logging
from app.models.user import User
from app.services.sms_service import sms_service
from app.core.redis import redis_manager
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class TwoFactorService:
    """Service for handling two-factor authentication"""

    @staticmethod
    async def enable_totp(
        db: AsyncSession,
        user: User
    ) -> Dict:
        """Enable TOTP-based 2FA for user"""
        try:
            # Generate secret key
            secret = pyotp.random_base32()

            # Create TOTP URI for QR code
            totp_uri = pyotp.totp.TOTP(secret).provisioning_uri(
                name=user.email,
                issuer_name='Evently'
            )

            # Generate QR code
            qr = qrcode.QRCode(version=1, box_size=10, border=5)
            qr.add_data(totp_uri)
            qr.make(fit=True)

            img = qr.make_image(fill_color="black", back_color="white")
            buffer = BytesIO()
            img.save(buffer, format='PNG')
            buffer.seek(0)

            # Convert to base64 for frontend
            qr_code_base64 = base64.b64encode(buffer.getvalue()).decode()

            # Store secret temporarily in Redis
            await redis_manager.set(
                f"2fa_setup:{user.id}",
                secret,
                ttl=600  # 10 minutes to complete setup
            )

            return {
                "secret": secret,
                "qr_code": f"data:image/png;base64,{qr_code_base64}",
                "manual_entry_key": secret,
                "manual_entry_setup": f"Evently ({user.email})"
            }

        except Exception as e:
            logger.error(f"Error enabling TOTP: {str(e)}")
            raise

    @staticmethod
    async def verify_totp_setup(
        db: AsyncSession,
        user: User,
        token: str
    ) -> bool:
        """Verify TOTP setup with user-provided token"""
        try:
            # Get temporary secret from Redis
            secret = await redis_manager.get(f"2fa_setup:{user.id}")
            if not secret:
                raise ValueError("Setup session expired")

            # Verify token
            totp = pyotp.TOTP(secret)
            if not totp.verify(token, valid_window=1):
                return False

            # Save secret to user
            user.totp_secret = secret
            user.two_factor_enabled = True
            user.two_factor_method = "totp"

            # Generate backup codes
            backup_codes = TwoFactorService._generate_backup_codes()
            user.backup_codes = ",".join(backup_codes)  # In production, encrypt these

            await db.commit()

            # Clear temporary secret
            await redis_manager.delete(f"2fa_setup:{user.id}")

            return True

        except Exception as e:
            logger.error(f"Error verifying TOTP setup: {str(e)}")
            return False

    @staticmethod
    async def verify_totp(
        user: User,
        token: str
    ) -> bool:
        """Verify TOTP token for authentication"""
        try:
            if not user.totp_secret:
                return False

            totp = pyotp.TOTP(user.totp_secret)
            return totp.verify(token, valid_window=1)

        except Exception as e:
            logger.error(f"Error verifying TOTP: {str(e)}")
            return False

    @staticmethod
    async def send_sms_code(
        user: User
    ) -> bool:
        """Send SMS verification code"""
        try:
            # Generate 6-digit code
            code = str(secrets.randbelow(900000) + 100000)

            # Store in Redis with TTL
            await redis_manager.set(
                f"sms_code:{user.id}",
                code,
                ttl=300  # 5 minutes
            )

            # Send SMS
            result = await sms_service.send_otp(
                phone_number=user.phone_number,
                otp_code=code
            )

            return result.get("success", False)

        except Exception as e:
            logger.error(f"Error sending SMS code: {str(e)}")
            return False

    @staticmethod
    async def verify_sms_code(
        user: User,
        code: str
    ) -> bool:
        """Verify SMS verification code"""
        try:
            # Get code from Redis
            stored_code = await redis_manager.get(f"sms_code:{user.id}")
            if not stored_code:
                return False

            # Verify code
            if stored_code != code:
                return False

            # Clear code after successful verification
            await redis_manager.delete(f"sms_code:{user.id}")

            return True

        except Exception as e:
            logger.error(f"Error verifying SMS code: {str(e)}")
            return False

    @staticmethod
    async def enable_sms_2fa(
        db: AsyncSession,
        user: User,
        phone_number: str
    ) -> bool:
        """Enable SMS-based 2FA"""
        try:
            # Verify phone number format
            if not phone_number.startswith("+"):
                phone_number = f"+1{phone_number}"  # Default to US

            # Send verification code
            code = str(secrets.randbelow(900000) + 100000)
            await redis_manager.set(
                f"sms_verify:{user.id}",
                {"code": code, "phone": phone_number},
                ttl=600
            )

            # Send SMS
            result = await sms_service.send_sms(
                to_number=phone_number,
                message=f"Your Evently verification code is: {code}"
            )

            return result.get("success", False)

        except Exception as e:
            logger.error(f"Error enabling SMS 2FA: {str(e)}")
            return False

    @staticmethod
    async def verify_sms_setup(
        db: AsyncSession,
        user: User,
        code: str
    ) -> bool:
        """Verify SMS 2FA setup"""
        try:
            # Get verification data
            data = await redis_manager.get(f"sms_verify:{user.id}")
            if not data:
                return False

            if data["code"] != code:
                return False

            # Update user
            user.phone_number = data["phone"]
            user.two_factor_enabled = True
            user.two_factor_method = "sms"

            # Generate backup codes
            backup_codes = TwoFactorService._generate_backup_codes()
            user.backup_codes = ",".join(backup_codes)

            await db.commit()

            # Clear verification data
            await redis_manager.delete(f"sms_verify:{user.id}")

            return True

        except Exception as e:
            logger.error(f"Error verifying SMS setup: {str(e)}")
            return False

    @staticmethod
    async def disable_2fa(
        db: AsyncSession,
        user: User,
        password: str
    ) -> bool:
        """Disable 2FA for user"""
        try:
            # Verify password
            from app.core.security import security_manager
            if not security_manager.verify_password(password, user.password_hash):
                return False

            # Clear 2FA settings
            user.two_factor_enabled = False
            user.two_factor_method = None
            user.totp_secret = None
            user.backup_codes = None

            await db.commit()

            return True

        except Exception as e:
            logger.error(f"Error disabling 2FA: {str(e)}")
            return False

    @staticmethod
    async def verify_backup_code(
        db: AsyncSession,
        user: User,
        code: str
    ) -> bool:
        """Verify backup code for 2FA"""
        try:
            if not user.backup_codes:
                return False

            backup_codes = user.backup_codes.split(",")
            if code not in backup_codes:
                return False

            # Remove used code
            backup_codes.remove(code)
            user.backup_codes = ",".join(backup_codes) if backup_codes else None

            await db.commit()

            return True

        except Exception as e:
            logger.error(f"Error verifying backup code: {str(e)}")
            return False

    @staticmethod
    def _generate_backup_codes(count: int = 10) -> list:
        """Generate backup codes"""
        codes = []
        for _ in range(count):
            code = ''.join([str(secrets.randbelow(10)) for _ in range(8)])
            codes.append(f"{code[:4]}-{code[4:]}")
        return codes

    @staticmethod
    async def require_2fa(
        user: User,
        method: Optional[str] = None
    ) -> Dict:
        """Check if 2FA is required and return method"""
        if not user.two_factor_enabled:
            return {"required": False}

        method = method or user.two_factor_method

        if method == "sms":
            # Send SMS code
            success = await TwoFactorService.send_sms_code(user)
            return {
                "required": True,
                "method": "sms",
                "sent": success,
                "phone_masked": TwoFactorService._mask_phone(user.phone_number)
            }
        else:
            # TOTP
            return {
                "required": True,
                "method": "totp"
            }

    @staticmethod
    def _mask_phone(phone: str) -> str:
        """Mask phone number for display"""
        if len(phone) < 7:
            return "***"
        return f"{phone[:3]}****{phone[-3:]}"


# Initialize global 2FA service
two_factor_service = TwoFactorService()