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

    DATABASE_URL: str

    REDIS_HOST: str
    REDIS_PORT: int

    AWS_ACCESS_KEY_ID: str
    AWS_SECRET_ACCESS_KEY: str
    AWS_S3_BUCKET_NAME: str
    AWS_S3_REGION: str
    BACKUP_DIR: str

settings = Settings()