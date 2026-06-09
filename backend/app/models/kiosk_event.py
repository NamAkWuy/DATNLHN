from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class KioskAttendanceEvent(Base):
    __tablename__ = "su_kien_cham_cong_kiosk"

    id: Mapped[int] = mapped_column("ma_su_kien", primary_key=True, index=True)
    event_id: Mapped[str] = mapped_column("ma_su_kien_client", String(64), unique=True, nullable=False, index=True)
    employee_id: Mapped[int] = mapped_column(
        "ma_nhan_vien",
        ForeignKey("nhan_vien.ma_nhan_vien", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    attendance_log_id: Mapped[int] = mapped_column(
        "ma_ban_ghi",
        ForeignKey("lich_su_cham_cong.ma_ban_ghi", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    action: Mapped[str] = mapped_column("hanh_dong", String(20), nullable=False)
    method: Mapped[str] = mapped_column("phuong_thuc", String(20), nullable=False, default="face")
    device_id: Mapped[Optional[str]] = mapped_column("ma_thiet_bi", String(100), nullable=True)
    occurred_at: Mapped[datetime] = mapped_column("thoi_diem_cham_cong", DateTime, nullable=False)
    synced_at: Mapped[datetime] = mapped_column("thoi_diem_dong_bo", DateTime, server_default=func.now(), nullable=False)

    def __repr__(self) -> str:
        return f"<KioskAttendanceEvent event_id={self.event_id} action={self.action}>"
