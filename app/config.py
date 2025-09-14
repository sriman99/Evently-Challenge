"""
Application configuration management
"""

from typing import List, Optional
from pydantic_settings import BaseSettings
from pydantic import field_validator
import os
from pathlib import Path


class Settings(BaseSettings):
    # Application
    APP_NAME: str = "Evently"
    APP_VERSION: str = "1.0.0"
    APP_ENV: str = "development"
    DEBUG: bool = False  # Default to production-safe
    SECRET_KEY: str  # Must be provided via environment
    API_PREFIX: str = "/api/v1"

    @field_validator('SECRET_KEY')
    @classmethod
    def validate_secret_key(cls, v: str) -> str:
        if not v or v == "your-secret-key-change-this-in-production":
            raise ValueError("SECRET_KEY must be set to a secure value in production")
        if len(v) < 32:
            raise ValueError("SECRET_KEY must be at least 32 characters long")
        return v

    # Server
    HOST: str = "0.0.0.0"
    PORT: int = 8000

    # Database
    DATABASE_URL: str  # Must be provided via environment

    @field_validator('DATABASE_URL')
    @classmethod
    def validate_database_url(cls, v: str) -> str:
        if v.startswith('postgresql://'):
            v = v.replace('postgresql://', 'postgresql+asyncpg://', 1)
        return v
    DB_POOL_SIZE: int = 20
    DB_MAX_OVERFLOW: int = 40
    DB_POOL_TIMEOUT: int = 30
    DB_POOL_RECYCLE: int = 3600
    DB_ECHO: bool = False

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"
    REDIS_TTL: int = 300
    REDIS_MAX_CONNECTIONS: int = 50

    # RabbitMQ
    RABBITMQ_URL: str = "amqp://guest:guest@localhost:5672/"
    RABBITMQ_EXCHANGE: str = "evently_events"
    RABBITMQ_QUEUE_PREFIX: str = "evently_"

    # JWT
    JWT_SECRET_KEY: str  # Must be provided via environment
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # Email
    SMTP_HOST: str = "smtp.gmail.com"
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM_EMAIL: str = "noreply@evently.com"
    SMTP_FROM_NAME: str = "Evently"

    # Payment
    PAYMENT_GATEWAY_URL: str = "https://api.stripe.com"
    PAYMENT_API_KEY: str = ""
    PAYMENT_WEBHOOK_SECRET: str = ""

    # Rate Limiting
    RATE_LIMIT_ENABLED: bool = True
    RATE_LIMIT_PUBLIC_PER_MINUTE: int = 100
    RATE_LIMIT_AUTH_PER_MINUTE: int = 200
    RATE_LIMIT_BOOKING_PER_MINUTE: int = 10

    # CORS
    CORS_ORIGINS: List[str] = ["http://localhost:3000", "http://localhost:8080", "http://localhost:5173"]
    CORS_ALLOW_CREDENTIALS: bool = True
    CORS_ALLOW_METHODS: List[str] = ["GET", "POST", "PUT", "DELETE", "OPTIONS"]
    CORS_ALLOW_HEADERS: List[str] = ["*"]

    # Monitoring
    SENTRY_DSN: Optional[str] = None
    PROMETHEUS_ENABLED: bool = True
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: str = "json"

    # Booking
    BOOKING_EXPIRATION_MINUTES: int = 5
    SEAT_LOCK_TTL_SECONDS: int = 300
    MAX_SEATS_PER_BOOKING: int = 10

    # Cache
    CACHE_TTL_EVENTS: int = 300
    CACHE_TTL_SEATS: int = 10
    CACHE_TTL_USER_SESSION: int = 1800

    # WebSocket
    WS_HEARTBEAT_INTERVAL: int = 30
    WS_CONNECTION_TIMEOUT: int = 60

    # Admin
    ADMIN_EMAIL: str = "admin@evently.com"
    ADMIN_PASSWORD: str = "AdminPass123!"

    @field_validator("CORS_ORIGINS", mode="before")
    def parse_cors_origins(cls, v):
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",")]
        return v

    @property
    def is_production(self) -> bool:
        return self.APP_ENV == "production"

    @property
    def is_development(self) -> bool:
        return self.APP_ENV == "development"

    @property
    def is_testing(self) -> bool:
        return self.APP_ENV == "testing"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True


# Create global settings instance
settings = Settings()

# Configuration validation is now handled by Pydantic validators