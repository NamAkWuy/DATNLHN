from datetime import datetime, date, timezone, timedelta
from typing import Optional
from pydantic import BaseModel, field_serializer

# Múi giờ Việt Nam — gắn vào output để JSON luôn có offset rõ ràng,
# tránh việc trình duyệt parse "naive" datetime sai (lệch 7 tiếng).
_VN_TZ = timezone(timedelta(hours=7))


def _to_vn_iso(dt: Optional[datetime]) -> Optional[str]:
    if dt is None:
        return None
    if dt.tzinfo is None:
        # DB lưu naive theo giờ VN → đính kèm offset +07:00
        dt = dt.replace(tzinfo=_VN_TZ)
    return dt.isoformat()


class EmployeeBrief(BaseModel):
    id: int
    full_name: str
    employee_code: str

    model_config = {"from_attributes": True}



class CheckInRequest(BaseModel):
    employee_id: int  # employee_id từ nhận diện khuôn mặt
    rfid_uid: Optional[str] = None  # UID thẻ RFID (nếu có)
    method: str = "manual"  # "face", "rfid", "manual"
    note: Optional[str] = None
    occurred_at: Optional[datetime] = None
    client_event_id: Optional[str] = None
    device_id: Optional[str] = None


class AttendanceLogCreate(BaseModel):
    employee_id: int
    check_in: datetime
    check_out: Optional[datetime] = None
    method: str = "manual"
    note: Optional[str] = None


class AttendanceLogUpdate(BaseModel):
    check_in: Optional[datetime] = None
    check_out: Optional[datetime] = None
    method: Optional[str] = None
    note: Optional[str] = None


class AttendanceLogResponse(BaseModel):
    id: int
    employee_id: int
    employee: Optional[EmployeeBrief] = None
    check_in: datetime
    check_out: Optional[datetime] = None
    method: str
    note: Optional[str] = None
    date: date
    work_hours: Optional[float] = None
    created_at: datetime

    model_config = {"from_attributes": True}

    @field_serializer("check_in", "check_out", "created_at")
    def _ser_dt(self, dt: Optional[datetime]) -> Optional[str]:
        return _to_vn_iso(dt)


class AttendanceListResponse(BaseModel):
    items: list[AttendanceLogResponse]
    total: int
    page: int
    page_size: int
    total_pages: int
