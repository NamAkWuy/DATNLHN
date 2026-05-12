import os
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL: str = "sqlite:///./attendance.db"
    SECRET_KEY: str = "change-this-secret-key-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_HOURS: int = 8

    # Thư mục lưu trữ tải lên
    UPLOAD_DIR: str = "uploads/avatars"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()

# Đảm bảo thư mục tải lên tồn tại
os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
