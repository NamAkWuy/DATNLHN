from datetime import datetime, date
from typing import Optional
from sqlalchemy import String, DateTime, Date, ForeignKey, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class AttendanceLog(Base):
    __tablename__ = "lich_su_cham_cong"

    id: Mapped[int] = mapped_column("ma_ban_ghi", primary_key=True, index=True)
    employee_id: Mapped[int] = mapped_column(
        "ma_nhan_vien",
        ForeignKey("nhan_vien.ma_nhan_vien", ondelete="CASCADE"), nullable=False, index=True
    )
    check_in: Mapped[datetime] = mapped_column("gio_vao", DateTime, nullable=False)
    check_out: Mapped[Optional[datetime]] = mapped_column("gio_ra", DateTime, nullable=True)
    note: Mapped[Optional[str]] = mapped_column("ghi_chu", Text, nullable=True)
    date: Mapped[date] = mapped_column("ngay_lam_viec", Date, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column("ngay_tao", DateTime, default=func.now(), nullable=False)

    # Quan hệ với bảng khác
    employee: Mapped["Employee"] = relationship("Employee", back_populates="attendance_logs")

    def __repr__(self) -> str:
        return f"<AttendanceLog id={self.id} employee_id={self.employee_id} date={self.date}>"
