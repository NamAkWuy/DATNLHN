from datetime import datetime
from typing import Optional
from sqlalchemy import String, DateTime, ForeignKey, Text, Boolean, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class Notification(Base):
    __tablename__ = "thong_bao"

    id: Mapped[int] = mapped_column("ma_thong_bao", primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(
        "ma_tai_khoan",
        ForeignKey("tai_khoan.ma_tai_khoan", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    type: Mapped[str] = mapped_column("loai", String(40), nullable=False)
    title: Mapped[str] = mapped_column("tieu_de", String(255), nullable=False)
    message: Mapped[str] = mapped_column("noi_dung", Text, nullable=False)
    link: Mapped[Optional[str]] = mapped_column("duong_dan", String(255), nullable=True)
    is_read: Mapped[bool] = mapped_column("da_doc", Boolean, default=False, nullable=False)
    read_at: Mapped[Optional[datetime]] = mapped_column("ngay_doc", DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        "ngay_tao", DateTime, default=func.now(), nullable=False
    )

    user: Mapped["User"] = relationship("User", back_populates="notifications")

    def __repr__(self) -> str:
        return f"<Notification id={self.id} user_id={self.user_id} type={self.type} read={self.is_read}>"
