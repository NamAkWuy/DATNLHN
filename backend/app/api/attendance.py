"""
Các endpoint cho lịch sử chấm công.
"""
import math
from datetime import datetime, date
from app.utils import now_vn, today_vn
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_admin, get_current_user, success_response
from app.database import get_db
from app.models.attendance_log import AttendanceLog
from app.models.employee import Employee
from app.models.user import User
from app.schemas.attendance import (
    AttendanceListResponse,
    AttendanceLogCreate,
    AttendanceLogResponse,
    AttendanceLogUpdate,
    CheckInRequest,
    EmployeeBrief,
)

router = APIRouter()

_broadcast_fn = None


def set_broadcast_fn(fn):
    global _broadcast_fn
    _broadcast_fn = fn


def _log_to_response(log: AttendanceLog) -> AttendanceLogResponse:
    emp_brief = None
    if log.employee:
        emp_brief = EmployeeBrief(
            id=log.employee.id,
            full_name=log.employee.full_name,
            employee_code=log.employee.employee_code,
        )

    work_hours: Optional[float] = None
    if log.check_in and log.check_out:
        delta = log.check_out - log.check_in
        work_hours = round(delta.total_seconds() / 3600, 2)

    return AttendanceLogResponse(
        id=log.id,
        employee_id=log.employee_id,
        employee=emp_brief,
        check_in=log.check_in,
        check_out=log.check_out,
        method=log.method,
        note=log.note,
        date=log.date,
        work_hours=work_hours,
        created_at=log.created_at,
    )


@router.get("/", response_model=dict)
def list_attendance_logs(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    date_filter: Optional[str] = Query(None, alias="date"),
    employee_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    q = db.query(AttendanceLog)

    if date_filter:
        try:
            d = datetime.strptime(date_filter, "%Y-%m-%d").date()
            q = q.filter(AttendanceLog.date == d)
        except ValueError:
            raise HTTPException(status_code=400, detail="Định dạng ngày không hợp lệ, dùng YYYY-MM-DD.")

    if employee_id:
        q = q.filter(AttendanceLog.employee_id == employee_id)

    total = q.count()
    total_pages = math.ceil(total / page_size) if total > 0 else 1
    logs = q.order_by(AttendanceLog.check_in.desc()).offset((page - 1) * page_size).limit(page_size).all()

    return success_response(
        data=AttendanceListResponse(
            items=[_log_to_response(l) for l in logs],
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
        ).model_dump()
    )


@router.get("/my", response_model=dict)
def my_attendance(
    month: Optional[int] = Query(None),
    year: Optional[int] = Query(None),
    from_date: Optional[str] = Query(None),
    to_date: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not current_user.employee_id:
        raise HTTPException(status_code=400, detail="Tài khoản chưa được liên kết với hồ sơ nhân viên.")

    q = db.query(AttendanceLog).filter(AttendanceLog.employee_id == current_user.employee_id)

    if from_date:
        try:
            q = q.filter(AttendanceLog.date >= datetime.strptime(from_date, "%Y-%m-%d").date())
        except ValueError:
            raise HTTPException(status_code=400, detail="Định dạng from_date không hợp lệ, dùng YYYY-MM-DD.")
    if to_date:
        try:
            q = q.filter(AttendanceLog.date <= datetime.strptime(to_date, "%Y-%m-%d").date())
        except ValueError:
            raise HTTPException(status_code=400, detail="Định dạng to_date không hợp lệ, dùng YYYY-MM-DD.")
    if month:
        import calendar
        y = year or datetime.now().year
        last_day = calendar.monthrange(y, month)[1]
        q = q.filter(AttendanceLog.date >= date(y, month, 1))
        q = q.filter(AttendanceLog.date <= date(y, month, last_day))

    logs = q.order_by(AttendanceLog.check_in.desc()).all()
    return success_response(data=[_log_to_response(l).model_dump() for l in logs])


@router.post("/checkin", response_model=dict)
def checkin(
    body: CheckInRequest,
    db: Session = Depends(get_db),
):
    # Lấy nhân viên dựa trên kết quả nhận diện khuôn mặt
    emp = db.query(Employee).filter(Employee.id == body.employee_id).first()
    if not emp:
        raise HTTPException(status_code=404, detail="Không tìm thấy nhân viên.")
    if emp.status != "active":
        raise HTTPException(status_code=403, detail="Tài khoản nhân viên đã bị vô hiệu hóa.")

    # Nếu có rfid_uid, kiểm tra chủ thẻ RFID có trùng với người được nhận diện khuôn mặt không
    if body.rfid_uid:
        from app.models.rfid_card import RFIDCard
        rfid_card = db.query(RFIDCard).filter(RFIDCard.uid == body.rfid_uid, RFIDCard.status == "active").first()
        if not rfid_card:
            raise HTTPException(status_code=404, detail="Thẻ RFID không hợp lệ hoặc đã bị khóa.")
        if rfid_card.employee_id != body.employee_id:
            raise HTTPException(status_code=400, detail="Khuôn mặt và thẻ RFID không khớp. Vui lòng thử lại.")

    today = today_vn()
    existing = (
        db.query(AttendanceLog)
        .filter(
            AttendanceLog.employee_id == body.employee_id,
            AttendanceLog.date == today,
        )
        .first()
    )

    now = now_vn()

    if existing is None:
        log = AttendanceLog(
            employee_id=body.employee_id,
            check_in=now,
            method=body.method,
            note=body.note,
            date=today,
        )
        db.add(log)
        db.commit()
        db.refresh(log)
        action = "check_in"
        msg = f"Chấm công vào cho {emp.full_name} thành công."
    elif existing.check_out is None:
        existing.check_out = now
        if body.note:
            existing.note = body.note
        db.commit()
        db.refresh(existing)
        log = existing
        action = "check_out"
        msg = f"Chấm công ra cho {emp.full_name} thành công."
    else:
        raise HTTPException(
            status_code=400,
            detail="Nhân viên đã chấm công ra hôm nay rồi.",
        )

    response_data = {
        "action": action,
        "log": _log_to_response(log).model_dump(),
    }

    import asyncio
    if _broadcast_fn:
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.ensure_future(_broadcast_fn({
                    "event": "attendance",
                    "action": action,
                    "employee_id": emp.id,
                    "employee_name": emp.full_name,
                    "employee_code": emp.employee_code,
                }))
        except Exception:
            pass

    return success_response(data=response_data, message=msg)


@router.post("/manual", response_model=dict, status_code=201)
def manual_attendance(
    body: AttendanceLogCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    emp = db.query(Employee).filter(Employee.id == body.employee_id).first()
    if not emp:
        raise HTTPException(status_code=404, detail="Không tìm thấy nhân viên.")

    log = AttendanceLog(
        employee_id=body.employee_id,
        check_in=body.check_in,
        check_out=body.check_out,
        method=body.method,
        note=body.note,
        date=body.check_in.date() if hasattr(body.check_in, "date") else body.check_in,
    )
    db.add(log)
    db.commit()
    db.refresh(log)
    return success_response(data=_log_to_response(log).model_dump(), message="Thêm bản ghi chấm công thành công.")


@router.put("/{log_id}", response_model=dict)
def update_attendance(
    log_id: int,
    body: AttendanceLogUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    log = db.query(AttendanceLog).filter(AttendanceLog.id == log_id).first()
    if not log:
        raise HTTPException(status_code=404, detail="Không tìm thấy bản ghi chấm công.")

    if body.check_in is not None:
        log.check_in = body.check_in
        log.date = body.check_in.date() if hasattr(body.check_in, "date") else body.check_in
    if body.check_out is not None:
        log.check_out = body.check_out
    if body.method is not None:
        log.method = body.method
    if body.note is not None:
        log.note = body.note

    db.commit()
    db.refresh(log)
    return success_response(data=_log_to_response(log).model_dump(), message="Cập nhật bản ghi chấm công thành công.")


@router.delete("/{log_id}", response_model=dict)
def delete_attendance(
    log_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    log = db.query(AttendanceLog).filter(AttendanceLog.id == log_id).first()
    if not log:
        raise HTTPException(status_code=404, detail="Không tìm thấy bản ghi chấm công.")

    db.delete(log)
    db.commit()
    return success_response(message="Xóa bản ghi chấm công thành công.")
