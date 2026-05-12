"""
Các endpoint quản lý thẻ RFID.
"""
from datetime import datetime, timezone
from app.utils import now_vn

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_admin, get_current_user, success_response
from app.database import get_db
from app.models.employee import Employee
from app.models.rfid_card import RFIDCard
from app.models.user import User
from app.schemas.rfid import (
    RFIDCardCreate,
    RFIDCardResponse,
    RFIDCardUpdate,
    RFIDScanRequest,
    RFIDStatusUpdate,
)

router = APIRouter()


def _card_to_response(card: RFIDCard) -> RFIDCardResponse:
    from app.schemas.rfid import EmployeeBrief

    emp_brief = None
    if card.employee:
        emp_brief = EmployeeBrief(
            id=card.employee.id,
            full_name=card.employee.full_name,
            employee_code=card.employee.employee_code,
        )
    return RFIDCardResponse(
        id=card.id,
        uid=card.uid,
        employee_id=card.employee_id,
        employee=emp_brief,
        status=card.status,
        assigned_at=card.assigned_at,
        created_at=card.created_at,
    )


@router.get("/", response_model=dict)
def list_rfid_cards(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    cards = db.query(RFIDCard).order_by(RFIDCard.id).all()
    return success_response(data=[_card_to_response(c).model_dump() for c in cards])


@router.post("/", response_model=dict, status_code=201)
def create_rfid_card(
    body: RFIDCardCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    if db.query(RFIDCard).filter(RFIDCard.uid == body.uid).first():
        raise HTTPException(status_code=400, detail="Mã UID thẻ RFID này đã được đăng ký.")

    if body.employee_id:
        emp = db.query(Employee).filter(Employee.id == body.employee_id).first()
        if not emp:
            raise HTTPException(status_code=404, detail="Không tìm thấy nhân viên.")
        existing = (
            db.query(RFIDCard)
            .filter(RFIDCard.employee_id == body.employee_id, RFIDCard.status == "active")
            .first()
        )
        if existing:
            raise HTTPException(
                status_code=400,
                detail=f"Nhân viên này đã có thẻ RFID đang hoạt động (UID: {existing.uid}). Vui lòng xóa hoặc vô hiệu hóa thẻ cũ trước.",
            )

    card = RFIDCard(
        uid=body.uid,
        employee_id=body.employee_id,
        status="active",
        assigned_at=now_vn() if body.employee_id else None,
    )
    db.add(card)
    db.commit()
    db.refresh(card)
    return success_response(data=_card_to_response(card).model_dump(), message="Đăng ký thẻ RFID thành công.")


@router.put("/{card_id}/assign", response_model=dict)
def assign_card(
    card_id: int,
    body: RFIDCardUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    card = db.query(RFIDCard).filter(RFIDCard.id == card_id).first()
    if not card:
        raise HTTPException(status_code=404, detail="Không tìm thấy thẻ RFID.")

    if body.employee_id:
        emp = db.query(Employee).filter(Employee.id == body.employee_id).first()
        if not emp:
            raise HTTPException(status_code=404, detail="Không tìm thấy nhân viên.")
        existing = (
            db.query(RFIDCard)
            .filter(
                RFIDCard.employee_id == body.employee_id,
                RFIDCard.status == "active",
                RFIDCard.id != card_id,
            )
            .first()
        )
        if existing:
            raise HTTPException(
                status_code=400,
                detail=f"Nhân viên này đã có thẻ RFID đang hoạt động (UID: {existing.uid}). Vui lòng xóa hoặc vô hiệu hóa thẻ cũ trước.",
            )

    card.employee_id = body.employee_id
    card.assigned_at = now_vn() if body.employee_id else None
    db.commit()
    db.refresh(card)
    return success_response(data=_card_to_response(card).model_dump(), message="Cập nhật gán thẻ thành công.")


@router.put("/{card_id}/status", response_model=dict)
def update_card_status(
    card_id: int,
    body: RFIDStatusUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    card = db.query(RFIDCard).filter(RFIDCard.id == card_id).first()
    if not card:
        raise HTTPException(status_code=404, detail="Không tìm thấy thẻ RFID.")

    if body.status not in ("active", "disabled"):
        raise HTTPException(status_code=400, detail="Trạng thái không hợp lệ. Chỉ chấp nhận: active hoặc disabled.")

    card.status = body.status
    db.commit()
    db.refresh(card)
    return success_response(data=_card_to_response(card).model_dump(), message="Cập nhật trạng thái thẻ thành công.")


@router.delete("/{card_id}", response_model=dict)
def delete_card(
    card_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    card = db.query(RFIDCard).filter(RFIDCard.id == card_id).first()
    if not card:
        raise HTTPException(status_code=404, detail="Không tìm thấy thẻ RFID.")

    db.delete(card)
    db.commit()
    return success_response(message="Xóa thẻ RFID thành công.")


@router.post("/scan", response_model=dict)
def scan_rfid(
    body: RFIDScanRequest,
    db: Session = Depends(get_db),
):
    card = db.query(RFIDCard).filter(RFIDCard.uid == body.uid).first()
    if not card:
        raise HTTPException(status_code=404, detail="Không tìm thấy thẻ RFID.")

    if card.status != "active":
        raise HTTPException(status_code=403, detail="Thẻ RFID này đã bị vô hiệu hóa.")

    if not card.employee_id:
        raise HTTPException(status_code=400, detail="Thẻ RFID chưa được gán cho nhân viên nào.")

    emp = db.query(Employee).filter(Employee.id == card.employee_id).first()
    if not emp:
        raise HTTPException(status_code=404, detail="Không tìm thấy nhân viên.")

    if emp.status != "active":
        raise HTTPException(status_code=403, detail="Tài khoản nhân viên đã bị vô hiệu hóa.")

    return success_response(
        data={
            "employee_id": emp.id,
            "employee_name": emp.full_name,
            "employee_code": emp.employee_code,
            "card_uid": card.uid,
        }
    )
