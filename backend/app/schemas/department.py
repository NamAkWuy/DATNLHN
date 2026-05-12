from datetime import datetime
from pydantic import BaseModel, field_validator


class DepartmentCreate(BaseModel):
    name: str

    @field_validator("name")
    @classmethod
    def name_not_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Department name cannot be empty")
        return v


class DepartmentUpdate(BaseModel):
    name: str

    @field_validator("name")
    @classmethod
    def name_not_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Department name cannot be empty")
        return v


class DepartmentResponse(BaseModel):
    id: int
    name: str
    created_at: datetime
    employee_count: int = 0

    model_config = {"from_attributes": True}
