from datetime import datetime
from sqlalchemy import Text, DateTime, ForeignKey, Boolean, Index, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class FaceEncoding(Base):
    """
    Một nhân viên có thể có nhiều bản ghi đặc trưng khuôn mặt (template gallery):
      - 1 bản ghi `is_primary=True` — template gốc do admin đăng ký
      - 0..N bản ghi `is_primary=False` — template tự học từ các lần verify thành công
        với độ tin cậy cao (adaptive enrollment). Cap số adaptive bởi tham số
        backend; FIFO khi đầy.
    """
    __tablename__ = "dac_trung_khuon_mat"

    id: Mapped[int] = mapped_column("ma_ban_ghi", primary_key=True, index=True)
    employee_id: Mapped[int] = mapped_column(
        "ma_nhan_vien",
        ForeignKey("nhan_vien.ma_nhan_vien", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    encoding_data: Mapped[str] = mapped_column("du_lieu_vector", Text, nullable=False)
    is_primary: Mapped[bool] = mapped_column(
        "la_template_chinh", Boolean, nullable=False, default=True,
    )
    created_at: Mapped[datetime] = mapped_column("ngay_tao", DateTime, default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        "ngay_cap_nhat", DateTime, default=func.now(), onupdate=func.now(), nullable=False
    )

    employee: Mapped["Employee"] = relationship("Employee", back_populates="face_encodings")

    __table_args__ = (
        Index("ix_face_emp_primary", "ma_nhan_vien", "la_template_chinh"),
    )

    def __repr__(self) -> str:
        flag = "primary" if self.is_primary else "adaptive"
        return f"<FaceEncoding id={self.id} employee_id={self.employee_id} {flag}>"
