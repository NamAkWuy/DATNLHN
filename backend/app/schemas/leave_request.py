from datetime import datetime, timezone, timedelta
from typing import Optional
from pydantic import BaseModel, field_serializer

_VN_TZ = timezone(timedelta(hours=7))


def _to_vn_iso(dt: Optional[datetime]) -> Optional[str]:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=_VN_TZ)
    return dt.isoformat()


class EmployeeBrief(BaseModel):
    id: int
    full_name: str
    employee_code: str

    model_config = {"from_attributes": True}


class ReviewerBrief(BaseModel):
    id: int
    username: str

    model_config = {"from_attributes": True}


class LeaveRequestCreate(BaseModel):
    type: str  # "nghi_phep", "di_muon", "ve_som"
    start_datetime: datetime
    end_datetime: datetime
    reason: str


class LeaveRequestUpdate(BaseModel):
    type: Optional[str] = None
    start_datetime: Optional[datetime] = None
    end_datetime: Optional[datetime] = None
    reason: Optional[str] = None


class LeaveRequestReject(BaseModel):
    reason: str


class LeaveRequestResponse(BaseModel):
    id: int
    employee_id: int
    employee: Optional[EmployeeBrief] = None
    type: str
    start_datetime: datetime
    end_datetime: datetime
    reason: str
    status: str
    reject_reason: Optional[str] = None
    reviewed_by: Optional[int] = None
    reviewer: Optional[ReviewerBrief] = None
    reviewed_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

    @field_serializer(
        "start_datetime", "end_datetime", "reviewed_at", "created_at", "updated_at"
    )
    def _ser_dt(self, dt: Optional[datetime]) -> Optional[str]:
        return _to_vn_iso(dt)
