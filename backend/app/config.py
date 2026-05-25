import os
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL: str = "sqlite:///./attendance.db"
    SECRET_KEY: str = "change-this-secret-key-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_HOURS: int = 8

    # Thư mục lưu trữ tải lên
    UPLOAD_DIR: str = "uploads/avatars"

    # Danh sách origin cho CORS, cách nhau bằng dấu phẩy.
    # Mặc định mở cho dev local; trên production set qua biến môi trường
    # CORS_ORIGINS="https://your-app.vercel.app".
    CORS_ORIGINS: str = "http://localhost:5173,http://localhost:3000,http://127.0.0.1:5173,http://127.0.0.1:3000"

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()

# Đảm bảo thư mục tải lên tồn tại
os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
