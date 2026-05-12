from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_admin, get_current_user, success_response
from app.database import get_db
from app.models.department import Department
from app.models.employee import Employee
from app.models.user import User
from app.schemas.department import DepartmentCreate, DepartmentResponse, DepartmentUpdate

router = APIRouter()


def _dept_to_response(dept: Department, db: Session) -> DepartmentResponse:
    count = db.query(Employee).filter(
        Employee.department_id == dept.id,
        Employee.status == "active",
    ).count()
    return DepartmentResponse(
        id=dept.id,
        name=dept.name,
        created_at=dept.created_at,
        employee_count=count,
    )


@router.get("/", response_model=dict)
def list_departments(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    depts = db.query(Department).order_by(Department.name).all()
    data = [_dept_to_response(d, db).model_dump() for d in depts]
    return success_response(data=data)


@router.post("/", response_model=dict, status_code=status.HTTP_201_CREATED)
def create_department(
    body: DepartmentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    existing = db.query(Department).filter(Department.name == body.name).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Phòng ban '{body.name}' đã tồn tại.",
        )
    dept = Department(name=body.name)
    db.add(dept)
    db.commit()
    db.refresh(dept)
    return success_response(
        data=_dept_to_response(dept, db).model_dump(),
        message="Tạo phòng ban thành công.",
    )


@router.put("/{dept_id}", response_model=dict)
def update_department(
    dept_id: int,
    body: DepartmentUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    dept = db.query(Department).filter(Department.id == dept_id).first()
    if not dept:
        raise HTTPException(status_code=404, detail="Không tìm thấy phòng ban.")

    conflict = (
        db.query(Department)
        .filter(Department.name == body.name, Department.id != dept_id)
        .first()
    )
    if conflict:
        raise HTTPException(
            status_code=400,
            detail=f"Tên phòng ban '{body.name}' đã được sử dụng.",
        )

    dept.name = body.name
    db.commit()
    db.refresh(dept)
    return success_response(
        data=_dept_to_response(dept, db).model_dump(),
        message="Cập nhật phòng ban thành công.",
    )


@router.delete("/{dept_id}", response_model=dict)
def delete_department(
    dept_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    dept = db.query(Department).filter(Department.id == dept_id).first()
    if not dept:
        raise HTTPException(status_code=404, detail="Không tìm thấy phòng ban.")

    has_employees = (
        db.query(Employee)
        .filter(Employee.department_id == dept_id, Employee.status == "active")
        .count()
    ) > 0
    if has_employees:
        raise HTTPException(
            status_code=400,
            detail="Không thể xóa phòng ban vì vẫn còn nhân viên đang hoạt động.",
        )

    db.delete(dept)
    db.commit()
    return success_response(message="Xóa phòng ban thành công.")
