from datetime import datetime
from typing import Optional
from sqlalchemy import String, DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class Employee(Base):
    __tablename__ = "nhan_vien"

    id: Mapped[int] = mapped_column("ma_nhan_vien", primary_key=True, index=True)
    employee_code: Mapped[str] = mapped_column("ma_so", String(20), unique=True, nullable=False, index=True)
    full_name: Mapped[str] = mapped_column("ho_ten", String(150), nullable=False)
    email: Mapped[str] = mapped_column("email", String(150), unique=True, nullable=False, index=True)
    phone: Mapped[Optional[str]] = mapped_column("so_dien_thoai", String(20), nullable=True)
    position: Mapped[Optional[str]] = mapped_column("chuc_vu", String(100), nullable=True)
    department_id: Mapped[Optional[int]] = mapped_column(
        "ma_phong_ban",
        ForeignKey("phong_ban.ma_phong_ban", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[str] = mapped_column("trang_thai", String(20), default="active", nullable=False)
    avatar_url: Mapped[Optional[str]] = mapped_column("anh_dai_dien", String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column("ngay_tao", DateTime, default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        "ngay_cap_nhat", DateTime, default=func.now(), onupdate=func.now(), nullable=False
    )

    # Quan hệ với bảng khác
    department: Mapped[Optional["Department"]] = relationship("Department", back_populates="employees")
    user: Mapped[Optional["User"]] = relationship("User", back_populates="employee", uselist=False)
    face_encodings: Mapped[list["FaceEncoding"]] = relationship(
        "FaceEncoding",
        back_populates="employee",
        cascade="all, delete-orphan",
        order_by="FaceEncoding.id",
    )
    rfid_cards: Mapped[list["RFIDCard"]] = relationship("RFIDCard", back_populates="employee")
    attendance_logs: Mapped[list["AttendanceLog"]] = relationship(
        "AttendanceLog", back_populates="employee"
    )
    leave_requests: Mapped[list["LeaveRequest"]] = relationship(
        "LeaveRequest", back_populates="employee"
    )

    def __repr__(self) -> str:
        return f"<Employee id={self.id} code={self.employee_code} name={self.full_name}>"
