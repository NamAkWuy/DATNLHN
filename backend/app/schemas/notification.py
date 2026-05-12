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


class NotificationResponse(BaseModel):
    id: int
    type: str
    title: str
    message: str
    link: Optional[str] = None
    is_read: bool
    read_at: Optional[datetime] = None
    created_at: datetime

    model_config = {"from_attributes": True}

    @field_serializer("read_at", "created_at")
    def _ser_dt(self, dt: Optional[datetime]) -> Optional[str]:
        return _to_vn_iso(dt)
