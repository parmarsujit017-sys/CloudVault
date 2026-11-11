"""Application configuration loaded from environment / .env file."""

from functools import lru_cache
from pathlib import Path
from typing import List

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent  # backend/


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    APP_ENV: str = "development"
    SECRET_KEY: str = "dev-secret-change-me"
    ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 1440

    DATABASE_URL: str = "sqlite:///./cloud_storage.db"

    UPLOAD_DIR: str = "uploads"
    MAX_FILE_SIZE_MB: int = 100
    DEFAULT_STORAGE_LIMIT_MB: int = 25600  # 25 GB, the Free plan allowance

    TRASH_RETENTION_DAYS: int = 30

    # ---- Plans and billing -------------------------------------------------
    # Prices are display-only: this app records what an administrator assigned,
    # it does not take payments.
    CURRENCY_CODE: str = "INR"
    CURRENCY_SYMBOL: str = "\u20b9"

    # ---- Bootstrap administrator ------------------------------------------
    # Created on first startup if it does not exist, so /admin is reachable on
    # a fresh database. Change these in .env for anything but local use.
    ADMIN_USERNAME: str = "vandit77"
    ADMIN_PASSWORD: str = "123456@Vk"
    # Reserved TLDs such as .local are rejected by email validation.
    ADMIN_EMAIL: str = "vandit77@example.com"
    ADMIN_FULLNAME: str = "Vandit"

    CORS_ORIGINS: str = "*"

    SERVE_FRONTEND: bool = True
    FRONTEND_DIR: str = ".."

    @property
    def cors_origin_list(self) -> List[str]:
        if self.CORS_ORIGINS.strip() == "*":
            return ["*"]
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    @property
    def upload_path(self) -> Path:
        p = Path(self.UPLOAD_DIR)
        if not p.is_absolute():
            p = BASE_DIR / p
        return p.resolve()

    @property
    def frontend_path(self) -> Path:
        p = Path(self.FRONTEND_DIR)
        if not p.is_absolute():
            p = BASE_DIR / p
        return p.resolve()

    @property
    def max_file_size_bytes(self) -> int:
        return self.MAX_FILE_SIZE_MB * 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    s.upload_path.mkdir(parents=True, exist_ok=True)
    return s


settings = get_settings()
