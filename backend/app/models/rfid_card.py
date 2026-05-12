from datetime import datetime
from typing import Optional
from sqlalchemy import String, DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class RFIDCard(Base):
    __tablename__ = "the_rfid"

    id: Mapped[int] = mapped_column("ma_the", primary_key=True, index=True)
    uid: Mapped[str] = mapped_column("uid", String(100), unique=True, nullable=False, index=True)
    employee_id: Mapped[Optional[int]] = mapped_column(
        "ma_nhan_vien",
        ForeignKey("nhan_vien.ma_nhan_vien", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[str] = mapped_column("trang_thai", String(20), default="active", nullable=False)
    assigned_at: Mapped[Optional[datetime]] = mapped_column("ngay_cap_phat", DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column("ngay_tao", DateTime, default=func.now(), nullable=False)

    # Quan hệ với bảng khác
    employee: Mapped[Optional["Employee"]] = relationship("Employee", back_populates="rfid_cards")

    def __repr__(self) -> str:
        return f"<RFIDCard id={self.id} uid={self.uid} status={self.status}>"
