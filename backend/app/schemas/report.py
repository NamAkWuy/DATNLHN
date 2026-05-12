from typing import Optional
from pydantic import BaseModel


class SummaryResponse(BaseModel):
    total_employees: int
    present_today: int
    absent_today: int
    pending_requests: int
    late_this_month: int


class EmployeeAttendanceReport(BaseModel):
    employee_id: int
    employee_code: str
    full_name: str
    department: Optional[str] = None
    total_days_worked: int
    late_count: int
    early_leave_count: int
    absent_count: int
    leave_days: int


class AttendanceReportResponse(BaseModel):
    month: int
    year: int
    records: list[EmployeeAttendanceReport]
    total_employees: int
