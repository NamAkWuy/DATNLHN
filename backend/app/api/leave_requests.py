"""
Các endpoint quản lý đơn từ (nghỉ phép, đi muộn, về sớm).
"""
import math
from app.utils import now_vn
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_admin, get_current_user, success_response
from app.database import get_db
from app.models.leave_request import LeaveRequest
from app.models.user import User
from app.schemas.leave_request import (
    LeaveRequestCreate,
    LeaveRequestReject,
    LeaveRequestResponse,
    LeaveRequestUpdate,
    EmployeeBrief,
    ReviewerBrief,
)
from app.services.notification_service import notify_admins, notify_employee

LEAVE_TYPE_LABELS = {
    "nghi_phep": "nghỉ phép",
    "di_muon": "đi muộn",
    "ve_som": "về sớm",
}

router = APIRouter()

VALID_TYPES = {"nghi_phep", "di_muon", "ve_som"}
VALID_TYPES_DISPLAY = "nghi_phep, di_muon, ve_som"


def _req_to_response(req: LeaveRequest) -> LeaveRequestResponse:
    emp_brief = None
    if req.employee:
        emp_brief = EmployeeBrief(
            id=req.employee.id,
            full_name=req.employee.full_name,
            employee_code=req.employee.employee_code,
        )
    reviewer_brief = None
    if req.reviewer:
        reviewer_brief = ReviewerBrief(id=req.reviewer.id, username=req.reviewer.username)

    return LeaveRequestResponse(
        id=req.id,
        employee_id=req.employee_id,
        employee=emp_brief,
        type=req.type,
        start_datetime=req.start_datetime,
        end_datetime=req.end_datetime,
        reason=req.reason,
        status=req.status,
        reject_reason=req.reject_reason,
        reviewed_by=req.reviewed_by,
        reviewer=reviewer_brief,
        reviewed_at=req.reviewed_at,
        created_at=req.created_at,
        updated_at=req.updated_at,
    )


def _paginate(query, page: int, page_size: int) -> dict:
    total = query.count()
    total_pages = math.ceil(total / page_size) if total > 0 else 1
    items = query.offset((page - 1) * page_size).limit(page_size).all()
    return {
        "items": [_req_to_response(r).model_dump() for r in items],
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages,
    }


@router.get("/", response_model=dict)
def list_all_requests(
    status: Optional[str] = Query(None),
    employee_id: Optional[int] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    q = db.query(LeaveRequest)
    if status:
        q = q.filter(LeaveRequest.status == status)
    if employee_id:
        q = q.filter(LeaveRequest.employee_id == employee_id)
    q = q.order_by(LeaveRequest.created_at.desc())
    return success_response(data=_paginate(q, page, page_size))


@router.get("/my", response_model=dict)
def my_requests(
    status: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not current_user.employee_id:
        raise HTTPException(status_code=400, detail="Tài khoản chưa được liên kết với hồ sơ nhân viên.")

    q = db.query(LeaveRequest).filter(LeaveRequest.employee_id == current_user.employee_id)
    if status:
        q = q.filter(LeaveRequest.status == status)
    q = q.order_by(LeaveRequest.created_at.desc())
    return success_response(data=_paginate(q, page, page_size))


@router.post("/", response_model=dict, status_code=201)
def create_request(
    body: LeaveRequestCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not current_user.employee_id:
        raise HTTPException(status_code=400, detail="Tài khoản chưa được liên kết với hồ sơ nhân viên.")

    if body.type not in VALID_TYPES:
        raise HTTPException(status_code=400, detail=f"Loại đơn không hợp lệ. Các loại hợp lệ: {VALID_TYPES_DISPLAY}.")

    if body.end_datetime <= body.start_datetime:
        raise HTTPException(status_code=400, detail="Thời gian kết thúc phải sau thời gian bắt đầu.")

    req = LeaveRequest(
        employee_id=current_user.employee_id,
        type=body.type,
        start_datetime=body.start_datetime,
        end_datetime=body.end_datetime,
        reason=body.reason,
        status="cho_duyet",
    )
    db.add(req)
    db.commit()
    db.refresh(req)

    emp_name = req.employee.full_name if req.employee else "Nhân viên"
    type_label = LEAVE_TYPE_LABELS.get(req.type, req.type)
    notify_admins(
        db,
        type="leave_request_created",
        title="Đơn từ mới chờ duyệt",
        message=f"{emp_name} vừa gửi đơn {type_label}.",
        link="/admin/leave",
    )

    return success_response(data=_req_to_response(req).model_dump(), message="Gửi đơn thành công, đang chờ duyệt.")


@router.put("/{req_id}", response_model=dict)
def update_request(
    req_id: int,
    body: LeaveRequestUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    req = db.query(LeaveRequest).filter(LeaveRequest.id == req_id).first()
    if not req:
        raise HTTPException(status_code=404, detail="Không tìm thấy đơn từ.")

    if current_user.role != "admin" and req.employee_id != current_user.employee_id:
        raise HTTPException(status_code=403, detail="Bạn không có quyền chỉnh sửa đơn này.")

    if req.status != "cho_duyet":
        raise HTTPException(status_code=400, detail="Chỉ có thể chỉnh sửa đơn đang ở trạng thái chờ duyệt.")

    if body.type is not None:
        if body.type not in VALID_TYPES:
            raise HTTPException(status_code=400, detail=f"Loại đơn không hợp lệ. Các loại hợp lệ: {VALID_TYPES_DISPLAY}.")
        req.type = body.type
    if body.start_datetime is not None:
        req.start_datetime = body.start_datetime
    if body.end_datetime is not None:
        req.end_datetime = body.end_datetime
    if body.reason is not None:
        req.reason = body.reason

    req.updated_at = now_vn()
    db.commit()
    db.refresh(req)
    return success_response(data=_req_to_response(req).model_dump(), message="Cập nhật đơn thành công.")


@router.delete("/{req_id}", response_model=dict)
def cancel_request(
    req_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    req = db.query(LeaveRequest).filter(LeaveRequest.id == req_id).first()
    if not req:
        raise HTTPException(status_code=404, detail="Không tìm thấy đơn từ.")

    if current_user.role != "admin" and req.employee_id != current_user.employee_id:
        raise HTTPException(status_code=403, detail="Bạn không có quyền hủy đơn này.")

    if req.status != "cho_duyet":
        raise HTTPException(status_code=400, detail="Chỉ có thể hủy đơn đang ở trạng thái chờ duyệt.")

    req.status = "da_huy"
    req.updated_at = now_vn()
    db.commit()
    db.refresh(req)
    return success_response(data=_req_to_response(req).model_dump(), message="Hủy đơn thành công.")


@router.put("/{req_id}/approve", response_model=dict)
def approve_request(
    req_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    req = db.query(LeaveRequest).filter(LeaveRequest.id == req_id).first()
    if not req:
        raise HTTPException(status_code=404, detail="Không tìm thấy đơn từ.")

    if req.status != "cho_duyet":
        raise HTTPException(status_code=400, detail="Đơn này không ở trạng thái chờ duyệt.")

    req.status = "da_duyet"
    req.reviewed_by = current_user.id
    req.reviewed_at = now_vn()
    req.updated_at = now_vn()
    db.commit()
    db.refresh(req)

    type_label = LEAVE_TYPE_LABELS.get(req.type, req.type)
    notify_employee(
        db,
        employee_id=req.employee_id,
        type="leave_request_approved",
        title="Đơn từ đã được duyệt",
        message=f"Đơn {type_label} của bạn đã được phê duyệt.",
        link="/my/requests",
    )

    return success_response(data=_req_to_response(req).model_dump(), message="Duyệt đơn thành công.")


@router.put("/{req_id}/reject", response_model=dict)
def reject_request(
    req_id: int,
    body: LeaveRequestReject,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    req = db.query(LeaveRequest).filter(LeaveRequest.id == req_id).first()
    if not req:
        raise HTTPException(status_code=404, detail="Không tìm thấy đơn từ.")

    if req.status != "cho_duyet":
        raise HTTPException(status_code=400, detail="Đơn này không ở trạng thái chờ duyệt.")

    req.status = "tu_choi"
    req.reject_reason = body.reason
    req.reviewed_by = current_user.id
    req.reviewed_at = now_vn()
    req.updated_at = now_vn()
    db.commit()
    db.refresh(req)

    type_label = LEAVE_TYPE_LABELS.get(req.type, req.type)
    notify_employee(
        db,
        employee_id=req.employee_id,
        type="leave_request_rejected",
        title="Đơn từ đã bị từ chối",
        message=f"Đơn {type_label} của bạn đã bị từ chối. Lý do: {body.reason}",
        link="/my/requests",
    )

    return success_response(data=_req_to_response(req).model_dump(), message="Từ chối đơn thành công.")
