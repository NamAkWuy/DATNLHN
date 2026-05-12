from datetime import datetime
from typing import Optional
from sqlalchemy import String, DateTime, Integer, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class User(Base):
    __tablename__ = "tai_khoan"

    id: Mapped[int] = mapped_column("ma_tai_khoan", primary_key=True, index=True)
    employee_id: Mapped[Optional[int]] = mapped_column(
        "ma_nhan_vien",
        ForeignKey("nhan_vien.ma_nhan_vien", ondelete="CASCADE"), unique=True, nullable=True
    )
    username: Mapped[str] = mapped_column("ten_dang_nhap", String(50), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column("mat_khau_ma_hoa", String(255), nullable=False)
    role: Mapped[str] = mapped_column("vai_tro", String(20), default="employee", nullable=False)
    failed_attempts: Mapped[int] = mapped_column("so_lan_sai", Integer, default=0, nullable=False)
    locked_until: Mapped[Optional[datetime]] = mapped_column("khoa_den", DateTime, nullable=True)
    last_login: Mapped[Optional[datetime]] = mapped_column("lan_cuoi_dang_nhap", DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column("ngay_tao", DateTime, default=func.now(), nullable=False)

    # Quan hệ với bảng khác
    employee: Mapped[Optional["Employee"]] = relationship("Employee", back_populates="user")
    reviewed_requests: Mapped[list["LeaveRequest"]] = relationship(
        "LeaveRequest", back_populates="reviewer", foreign_keys="LeaveRequest.reviewed_by"
    )
    notifications: Mapped[list["Notification"]] = relationship(
        "Notification", back_populates="user", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<User id={self.id} username={self.username} role={self.role}>"
