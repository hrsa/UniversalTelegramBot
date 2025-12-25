from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    BOT_TOKEN: str
    ADMIN_TELEGRAM_ID: int
    STRIPE_API_KEY: str
    STRIPE_SIGNING_SECRET: str
    WEBHOOK_URL: str
    WEBHOOK_SECRET: str
    DOMAIN: str

    DATABASE_URL: str

    REDIS_HOST: str
    REDIS_PORT: int

settings = Settings()