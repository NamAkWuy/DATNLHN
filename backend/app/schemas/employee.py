from datetime import datetime
from typing import Optional
from pydantic import BaseModel, EmailStr


class DepartmentBrief(BaseModel):
    id: int
    name: str

    model_config = {"from_attributes": True}


class EmployeeCreate(BaseModel):
    full_name: str
    email: EmailStr
    phone: Optional[str] = None
    position: Optional[str] = None
    department_id: Optional[int] = None
    status: str = "active"
    password: Optional[str] = None      # None → mặc định "123456"
    role: str = "employee"              # "employee" hoặc "admin"


class EmployeeUpdate(BaseModel):
    full_name: Optional[str] = None
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    position: Optional[str] = None
    department_id: Optional[int] = None
    status: Optional[str] = None
    role: Optional[str] = None          # đổi quyền: "employee" hoặc "admin"


class EmployeeResponse(BaseModel):
    id: int
    employee_code: str
    full_name: str
    email: str
    phone: Optional[str] = None
    position: Optional[str] = None
    department_id: Optional[int] = None
    department: Optional[DepartmentBrief] = None
    status: str
    avatar_url: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    has_face: bool = False
    face_template_count: int = 0   # tổng số template trong gallery (primary + adaptive)
    has_rfid: bool = False
    username: Optional[str] = None      # tên đăng nhập liên kết
    role: Optional[str] = None          # quyền: employee / admin

    model_config = {"from_attributes": True}


class EmployeeListResponse(BaseModel):
    items: list[EmployeeResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


class EmployeeCreateResponse(BaseModel):
    employee: EmployeeResponse
    username: str
    temp_password: str
