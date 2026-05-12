"""
Các endpoint báo cáo và thống kê.
"""
import calendar
from datetime import date, datetime, timedelta, timezone
from app.utils import now_vn, today_vn

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
import io
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.deps import get_current_admin, success_response
from app.database import get_db
from app.models.attendance_log import AttendanceLog
from app.models.employee import Employee
from app.models.leave_request import LeaveRequest
from app.models.user import User
from app.services.report_service import generate_attendance_excel, generate_attendance_pdf

router = APIRouter()

# Giờ bắt đầu làm việc (09:00) — dùng để xác định đi muộn
WORK_START_HOUR = 9
WORK_START_MINUTE = 0

# Giờ kết thúc làm việc (17:30) — dùng để xác định về sớm
WORK_END_HOUR = 17
WORK_END_MINUTE = 30


def _build_report_records(db: Session, month: int, year: int) -> list[dict]:
    """Logic lõi: tính thống kê chấm công theo từng nhân viên cho 1 tháng/năm."""
    employees = db.query(Employee).filter(Employee.status == "active").all()

    # Số ngày làm việc trong tháng (thứ 2 → thứ 6)
    _, num_days = calendar.monthrange(year, month)
    working_days = sum(
        1
        for d in range(1, num_days + 1)
        if date(year, month, d).weekday() < 5  # Mon=0 … Fri=4
    )

    records = []
    for emp in employees:
        logs = (
            db.query(AttendanceLog)
            .filter(
                AttendanceLog.employee_id == emp.id,
                AttendanceLog.date >= date(year, month, 1),
                AttendanceLog.date <= date(year, month, num_days),
            )
            .all()
        )

        # Số ngày nghỉ phép đã được duyệt
        leave_requests = (
            db.query(LeaveRequest)
            .filter(
                LeaveRequest.employee_id == emp.id,
                LeaveRequest.status == "da_duyet",
                LeaveRequest.type == "nghi_phep",
                LeaveRequest.start_datetime >= datetime(year, month, 1),
                LeaveRequest.start_datetime <= datetime(year, month, num_days, 23, 59, 59),
            )
            .all()
        )
        leave_days = len(leave_requests)

        dates_present = set(l.date for l in logs)
        total_days_worked = len(dates_present)

        # Đi muộn: giờ check_in > WORK_START_HOUR:WORK_START_MINUTE
        late_count = 0
        early_leave_count = 0
        total_work_seconds = 0.0
        for log in logs:
            ci = log.check_in
            if ci.hour > WORK_START_HOUR or (
                ci.hour == WORK_START_HOUR and ci.minute > WORK_START_MINUTE
            ):
                late_count += 1
            if log.check_out:
                co = log.check_out
                if co.hour < WORK_END_HOUR or (
                    co.hour == WORK_END_HOUR and co.minute < WORK_END_MINUTE
                ):
                    early_leave_count += 1
                delta = (co - ci).total_seconds()
                if delta > 0:
                    total_work_seconds += delta

        total_work_hours = round(total_work_seconds / 3600, 2)
        absent_count = max(0, working_days - total_days_worked - leave_days)

        records.append(
            {
                "employee_id": emp.id,
                "employee_code": emp.employee_code,
                "full_name": emp.full_name,
                "department": emp.department.name if emp.department else None,
                "total_days_worked": total_days_worked,
                "total_work_hours": total_work_hours,
                "late_count": late_count,
                "early_leave_count": early_leave_count,
                "absent_count": absent_count,
                "leave_days": leave_days,
            }
        )

    return records


@router.get("/summary", response_model=dict)
def get_summary(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    today = today_vn()
    now = now_vn()

    total_employees = db.query(Employee).filter(Employee.status == "active").count()

    # Có mặt hôm nay: có ít nhất 1 bản ghi chấm công cho ngày hôm nay
    present_today = (
        db.query(AttendanceLog.employee_id)
        .filter(AttendanceLog.date == today)
        .distinct()
        .count()
    )

    # Đang trong kỳ nghỉ phép đã duyệt (theo nghiệp vụ, sẽ trừ khỏi số "vắng")
    day_start = datetime.combine(today, datetime.min.time())
    day_end = datetime.combine(today, datetime.max.time())
    on_leave_today = (
        db.query(LeaveRequest.employee_id)
        .filter(
            LeaveRequest.status == "da_duyet",
            LeaveRequest.type == "nghi_phep",
            LeaveRequest.start_datetime <= day_end,
            LeaveRequest.end_datetime >= day_start,
        )
        .distinct()
        .count()
    )

    absent_today = max(0, total_employees - present_today - on_leave_today)

    pending_requests = (
        db.query(LeaveRequest).filter(LeaveRequest.status == "cho_duyet").count()
    )

    # Số lần đi muộn trong tháng này
    month_start = date(now.year, now.month, 1)
    late_logs = (
        db.query(AttendanceLog)
        .filter(AttendanceLog.date >= month_start, AttendanceLog.date <= today)
        .all()
    )
    late_this_month = sum(
        1
        for log in late_logs
        if log.check_in.hour > WORK_START_HOUR
        or (log.check_in.hour == WORK_START_HOUR and log.check_in.minute > WORK_START_MINUTE)
    )

    return success_response(
        data={
            "total_employees": total_employees,
            "present_today": present_today,
            "absent_today": absent_today,
            "pending_requests": pending_requests,
            "late_this_month": late_this_month,
        }
    )


@router.get("/chart/weekly", response_model=dict)
def get_weekly_chart(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    """Xu hướng chấm công 7 ngày gần nhất tính đến hôm nay (theo giờ Việt Nam)."""
    today = today_vn()
    start_date = today - timedelta(days=6)

    total_employees = db.query(Employee).filter(Employee.status == "active").count()

    # Số nhân viên có mặt (không trùng) trong từng ngày
    rows = (
        db.query(AttendanceLog.date, func.count(func.distinct(AttendanceLog.employee_id)))
        .filter(AttendanceLog.date >= start_date, AttendanceLog.date <= today)
        .group_by(AttendanceLog.date)
        .all()
    )
    present_by_date = {d: int(c) for d, c in rows}

    # Các đơn nghỉ phép đã duyệt giao thoa với từng ngày trong khoảng
    leave_rows = (
        db.query(LeaveRequest.employee_id, LeaveRequest.start_datetime, LeaveRequest.end_datetime)
        .filter(
            LeaveRequest.status == "da_duyet",
            LeaveRequest.type == "nghi_phep",
            LeaveRequest.start_datetime <= datetime.combine(today, datetime.max.time()),
            LeaveRequest.end_datetime >= datetime.combine(start_date, datetime.min.time()),
        )
        .all()
    )

    points = []
    for i in range(7):
        d = start_date + timedelta(days=i)
        present = present_by_date.get(d, 0)

        on_leave_ids = {
            emp_id
            for emp_id, sdt, edt in leave_rows
            if sdt.date() <= d <= edt.date()
        }
        on_leave = len(on_leave_ids)

        absent = max(0, total_employees - present - on_leave)
        points.append(
            {
                "date": d.strftime("%d/%m"),
                "present": present,
                "absent": absent,
            }
        )

    return success_response(data=points)


@router.get("/attendance", response_model=dict)
def get_attendance_report(
    month: int = Query(default=None),
    year: int = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    now = now_vn()
    month = month or now.month
    year = year or now.year

    if month < 1 or month > 12:
        raise HTTPException(status_code=400, detail="Tháng không hợp lệ, vui lòng nhập từ 1 đến 12.")

    records = _build_report_records(db, month, year)

    return success_response(
        data={
            "month": month,
            "year": year,
            "records": records,
            "total_employees": len(records),
        }
    )


@router.get("/export/excel")
def export_excel(
    month: int = Query(default=None),
    year: int = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    now = now_vn()
    month = month or now.month
    year = year or now.year

    records = _build_report_records(db, month, year)
    excel_bytes = generate_attendance_excel(month, year, records)

    filename = f"attendance_{year}_{month:02d}.xlsx"
    return StreamingResponse(
        io.BytesIO(excel_bytes),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.get("/export/pdf")
def export_pdf(
    month: int = Query(default=None),
    year: int = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    now = now_vn()
    month = month or now.month
    year = year or now.year

    records = _build_report_records(db, month, year)
    pdf_bytes = generate_attendance_pdf(month, year, records)

    filename = f"attendance_{year}_{month:02d}.pdf"
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
