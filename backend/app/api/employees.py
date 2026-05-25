"""
Các endpoint quản lý nhân viên.
"""
import os
import math
import unicodedata
import re
from app.utils import now_vn
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query, status
from sqlalchemy.orm import Session
from passlib.context import CryptContext

from app.api.deps import get_current_admin, get_current_user, success_response
from app.config import settings
from app.database import get_db
from app.models.department import Department
from app.models.employee import Employee
from app.models.user import User
from app.schemas.employee import (
    EmployeeCreate,
    EmployeeCreateResponse,
    EmployeeListResponse,
    EmployeeResponse,
    EmployeeUpdate,
)

router = APIRouter()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def _remove_accents(text: str) -> str:
    nfkd = unicodedata.normalize("NFD", text)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def _generate_username(full_name: str, db: Session) -> str:
    parts = full_name.strip().split()
    if len(parts) >= 2:
        initials = "".join(p[0] for p in parts[:-1])
        last = parts[-1]
        base = (initials + last).lower()
    else:
        base = parts[0].lower() if parts else "user"

    base = _remove_accents(base)
    base = re.sub(r"[^a-z0-9]", "", base)
    if not base:
        base = "user"

    username = base
    counter = 1
    while db.query(User).filter(User.username == username).first():
        username = f"{base}{counter}"
        counter += 1
    return username


def _generate_employee_code(db: Session) -> str:
    last = db.query(Employee).order_by(Employee.id.desc()).first()
    next_num = (last.id + 1) if last else 1
    return f"EMP{next_num:03d}"


def _employee_to_response(emp: Employee) -> EmployeeResponse:
    face_template_count = len(emp.face_encodings) if emp.face_encodings else 0
    has_face = face_template_count > 0
    has_rfid = any(c.status == "active" for c in emp.rfid_cards) if emp.rfid_cards else False
    dept = None
    if emp.department:
        from app.schemas.employee import DepartmentBrief
        dept = DepartmentBrief(id=emp.department.id, name=emp.department.name)

    return EmployeeResponse(
        id=emp.id,
        employee_code=emp.employee_code,
        full_name=emp.full_name,
        email=emp.email,
        phone=emp.phone,
        position=emp.position,
        department_id=emp.department_id,
        department=dept,
        status=emp.status,
        avatar_url=emp.avatar_url,
        created_at=emp.created_at,
        updated_at=emp.updated_at,
        has_face=has_face,
        face_template_count=face_template_count,
        has_rfid=has_rfid,
        username=emp.user.username if emp.user else None,
        role=emp.user.role if emp.user else None,
    )


@router.get("/", response_model=dict)
def list_employees(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=500),
    search: Optional[str] = Query(None),
    department_id: Optional[int] = Query(None),
    status: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = db.query(Employee)

    if search:
        like = f"%{search}%"
        query = query.filter(
            Employee.full_name.ilike(like)
            | Employee.employee_code.ilike(like)
            | Employee.email.ilike(like)
        )
    if department_id:
        query = query.filter(Employee.department_id == department_id)
    if status:
        query = query.filter(Employee.status == status)

    total = query.count()
    total_pages = math.ceil(total / page_size) if total > 0 else 1
    employees = (
        query.order_by(Employee.id)
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    return success_response(
        data=EmployeeListResponse(
            items=[_employee_to_response(e) for e in employees],
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
        ).model_dump()
    )


@router.post("/", response_model=dict, status_code=201)
def create_employee(
    body: EmployeeCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    if db.query(Employee).filter(Employee.email == body.email).first():
        raise HTTPException(status_code=400, detail="Email này đã được sử dụng.")

    if body.department_id:
        if not db.query(Department).filter(Department.id == body.department_id).first():
            raise HTTPException(status_code=404, detail="Không tìm thấy phòng ban.")

    emp_code = _generate_employee_code(db)

    emp = Employee(
        employee_code=emp_code,
        full_name=body.full_name,
        email=body.email,
        phone=body.phone,
        position=body.position,
        department_id=body.department_id,
        status=body.status,
    )
    db.add(emp)
    db.flush()

    # Mật khẩu: dùng mật khẩu admin nhập, nếu để trống thì mặc định "123456"
    actual_password = body.password.strip() if body.password and body.password.strip() else "123456"

    # Tên đăng nhập: luôn dùng mã NV (emp001, emp002...) — đảm bảo duy nhất tuyệt đối
    username = emp_code.lower()   # "EMP001" → "emp001"

    # Quyền: chỉ cho phép "employee" hoặc "admin"
    role = body.role if body.role in ("employee", "admin") else "employee"

    user = User(
        employee_id=emp.id,
        username=username,
        password_hash=pwd_context.hash(actual_password),
        role=role,
    )
    db.add(user)
    db.commit()
    db.refresh(emp)

    return success_response(
        data=EmployeeCreateResponse(
            employee=_employee_to_response(emp),
            username=username,
            temp_password=actual_password,
        ).model_dump(),
        message="Thêm nhân viên thành công.",
    )


@router.get("/{employee_id}", response_model=dict)
def get_employee(
    employee_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != "admin":
        if current_user.employee_id != employee_id:
            raise HTTPException(status_code=403, detail="Bạn không có quyền xem thông tin này.")

    emp = db.query(Employee).filter(Employee.id == employee_id).first()
    if not emp:
        raise HTTPException(status_code=404, detail="Không tìm thấy nhân viên.")

    return success_response(data=_employee_to_response(emp).model_dump())


@router.put("/{employee_id}", response_model=dict)
def update_employee(
    employee_id: int,
    body: EmployeeUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    is_admin = current_user.role == "admin"
    is_self = current_user.employee_id == employee_id
    if not is_admin and not is_self:
        raise HTTPException(status_code=403, detail="Bạn không có quyền thực hiện thao tác này.")

    emp = db.query(Employee).filter(Employee.id == employee_id).first()
    if not emp:
        raise HTTPException(status_code=404, detail="Không tìm thấy nhân viên.")

    if body.email and body.email != emp.email:
        if db.query(Employee).filter(Employee.email == body.email, Employee.id != employee_id).first():
            raise HTTPException(status_code=400, detail="Email này đã được sử dụng.")
        emp.email = body.email

    if body.phone is not None:
        emp.phone = body.phone

    # Các trường còn lại chỉ admin mới được sửa
    if is_admin:
        if body.department_id is not None:
            if body.department_id and not db.query(Department).filter(Department.id == body.department_id).first():
                raise HTTPException(status_code=404, detail="Không tìm thấy phòng ban.")
            emp.department_id = body.department_id

        for field in ("full_name", "position", "status"):
            val = getattr(body, field, None)
            if val is not None:
                setattr(emp, field, val)

        if body.role and body.role in ("employee", "admin"):
            user_acc = db.query(User).filter(User.employee_id == employee_id).first()
            if user_acc:
                user_acc.role = body.role

    emp.updated_at = now_vn()
    db.commit()
    db.refresh(emp)
    return success_response(data=_employee_to_response(emp).model_dump(), message="Cập nhật thông tin thành công.")


@router.delete("/{employee_id}", response_model=dict)
def deactivate_employee(
    employee_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    emp = db.query(Employee).filter(Employee.id == employee_id).first()
    if not emp:
        raise HTTPException(status_code=404, detail="Không tìm thấy nhân viên.")

    emp.status = "inactive"
    emp.updated_at = now_vn()
    db.commit()
    return success_response(message="Đã vô hiệu hóa tài khoản nhân viên.")


@router.post("/{employee_id}/avatar", response_model=dict)
async def upload_avatar(
    employee_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != "admin" and current_user.employee_id != employee_id:
        raise HTTPException(status_code=403, detail="Bạn không có quyền thực hiện thao tác này.")

    emp = db.query(Employee).filter(Employee.id == employee_id).first()
    if not emp:
        raise HTTPException(status_code=404, detail="Không tìm thấy nhân viên.")

    allowed = {"image/jpeg", "image/png", "image/gif", "image/webp"}
    if file.content_type not in allowed:
        raise HTTPException(status_code=400, detail="Chỉ chấp nhận file ảnh (JPEG, PNG, GIF, WEBP).")

    ext = file.filename.rsplit(".", 1)[-1] if "." in file.filename else "jpg"
    filename = f"emp_{employee_id}.{ext}"
    filepath = os.path.join(settings.UPLOAD_DIR, filename)

    contents = await file.read()
    with open(filepath, "wb") as f:
        f.write(contents)

    emp.avatar_url = f"/uploads/avatars/{filename}"
    emp.updated_at = now_vn()
    db.commit()

    return success_response(
        data={"avatar_url": emp.avatar_url},
        message="Tải ảnh đại diện thành công.",
    )
