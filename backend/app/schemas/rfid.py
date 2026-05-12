from datetime import datetime
from typing import Optional
from pydantic import BaseModel


class RFIDCardCreate(BaseModel):
    uid: str
    employee_id: Optional[int] = None


class RFIDCardUpdate(BaseModel):
    employee_id: Optional[int] = None


class RFIDStatusUpdate(BaseModel):
    status: str  # "active" or "disabled"


class EmployeeBrief(BaseModel):
    id: int
    full_name: str
    employee_code: str

    model_config = {"from_attributes": True}


class RFIDCardResponse(BaseModel):
    id: int
    uid: str
    employee_id: Optional[int] = None
    employee: Optional[EmployeeBrief] = None
    status: str
    assigned_at: Optional[datetime] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class RFIDScanRequest(BaseModel):
    uid: str


class RFIDScanResponse(BaseModel):
    employee_id: int
    employee_name: str
    employee_code: str
    card_uid: str
