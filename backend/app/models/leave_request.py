from datetime import datetime
from typing import Optional
from sqlalchemy import String, DateTime, ForeignKey, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class LeaveRequest(Base):
    __tablename__ = "don_tu"

    id: Mapped[int] = mapped_column("ma_don", primary_key=True, index=True)
    employee_id: Mapped[int] = mapped_column(
        "ma_nhan_vien",
        ForeignKey("nhan_vien.ma_nhan_vien", ondelete="CASCADE"), nullable=False, index=True
    )
    type: Mapped[str] = mapped_column("loai_don", String(30), nullable=False)
    start_datetime: Mapped[datetime] = mapped_column("thoi_gian_bat_dau", DateTime, nullable=False)
    end_datetime: Mapped[datetime] = mapped_column("thoi_gian_ket_thuc", DateTime, nullable=False)
    reason: Mapped[str] = mapped_column("ly_do", Text, nullable=False)
    status: Mapped[str] = mapped_column("trang_thai", String(20), default="cho_duyet", nullable=False)
    reject_reason: Mapped[Optional[str]] = mapped_column("ly_do_tu_choi", Text, nullable=True)
    reviewed_by: Mapped[Optional[int]] = mapped_column(
        "nguoi_duyet",
        ForeignKey("tai_khoan.ma_tai_khoan", ondelete="SET NULL"), nullable=True
    )
    reviewed_at: Mapped[Optional[datetime]] = mapped_column("ngay_duyet", DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column("ngay_tao", DateTime, default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        "ngay_cap_nhat", DateTime, default=func.now(), onupdate=func.now(), nullable=False
    )

    # Quan hệ với bảng khác
    employee: Mapped["Employee"] = relationship("Employee", back_populates="leave_requests")
    reviewer: Mapped[Optional["User"]] = relationship(
        "User", back_populates="reviewed_requests", foreign_keys=[reviewed_by]
    )

    def __repr__(self) -> str:
        return f"<LeaveRequest id={self.id} employee_id={self.employee_id} status={self.status}>"
