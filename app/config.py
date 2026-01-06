from typing import Optional

from pydantic import computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    ENV: str
    BOT_TOKEN: str
    ADMIN_TELEGRAM_ID: int
    STRIPE_API_KEY: str
    STRIPE_SIGNING_SECRET: str
    WEBHOOK_URL: str
    WEBHOOK_SECRET: str
    DOMAIN: str

    POSTGRES_USER: str
    POSTGRES_PASSWORD: str
    POSTGRES_DB: str
    POSTGRES_HOST: str
    POSTGRES_PORT: Optional[int] = 5432

    @computed_field
    @property
    def DATABASE_URL(self) -> str:
        return f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"

    REDIS_HOST: str
    REDIS_PORT: int

    AWS_ACCESS_KEY_ID: str
    AWS_SECRET_ACCESS_KEY: str
    AWS_S3_BUCKET_NAME: str
    AWS_S3_REGION: str
    BACKUP_DIR: str

    AI_PROVIDER: str = "openai"
    AI_MODEL: str = "gpt-4.1-mini"
    AI_TEMPERATURE: float = 0.3
    AI_MAX_TOKENS: int = 512
    OPENAI_API_KEY: str | None = None
    OLLAMA_URL: str | None = None

settings = Settings()