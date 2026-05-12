from datetime import datetime
from sqlalchemy import String, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class Department(Base):
    __tablename__ = "phong_ban"

    id: Mapped[int] = mapped_column("ma_phong_ban", primary_key=True, index=True)
    name: Mapped[str] = mapped_column("ten_phong_ban", String(100), unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column("ngay_tao", DateTime, default=func.now(), nullable=False)

    # Quan hệ với bảng khác
    employees: Mapped[list["Employee"]] = relationship("Employee", back_populates="department")

    def __repr__(self) -> str:
        return f"<Department id={self.id} name={self.name}>"
