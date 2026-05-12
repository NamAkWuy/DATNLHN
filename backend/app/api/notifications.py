"""
Notification endpoints — danh sách thông báo của user hiện tại,
đếm chưa đọc, đánh dấu đã đọc, xóa.
"""
import math
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, success_response
from app.database import get_db
from app.models.notification import Notification
from app.models.user import User
from app.schemas.notification import NotificationResponse
from app.utils import now_vn

router = APIRouter()


@router.get("/", response_model=dict)
def list_notifications(
    unread_only: bool = Query(False),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = db.query(Notification).filter(Notification.user_id == current_user.id)
    if unread_only:
        q = q.filter(Notification.is_read == False)  # noqa: E712
    q = q.order_by(Notification.created_at.desc())

    total = q.count()
    total_pages = math.ceil(total / page_size) if total > 0 else 1
    items = q.offset((page - 1) * page_size).limit(page_size).all()

    return success_response(
        data={
            "items": [NotificationResponse.model_validate(n).model_dump() for n in items],
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
        }
    )


@router.get("/unread-count", response_model=dict)
def unread_count(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    count = (
        db.query(Notification)
        .filter(Notification.user_id == current_user.id, Notification.is_read == False)  # noqa: E712
        .count()
    )
    return success_response(data={"unread": count})


@router.put("/{notif_id}/read", response_model=dict)
def mark_read(
    notif_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    n = (
        db.query(Notification)
        .filter(Notification.id == notif_id, Notification.user_id == current_user.id)
        .first()
    )
    if not n:
        raise HTTPException(status_code=404, detail="Không tìm thấy thông báo.")
    if not n.is_read:
        n.is_read = True
        n.read_at = now_vn()
        db.commit()
        db.refresh(n)
    return success_response(data=NotificationResponse.model_validate(n).model_dump())


@router.put("/read-all", response_model=dict)
def mark_all_read(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    now = now_vn()
    updated = (
        db.query(Notification)
        .filter(Notification.user_id == current_user.id, Notification.is_read == False)  # noqa: E712
        .update({"is_read": True, "read_at": now}, synchronize_session=False)
    )
    db.commit()
    return success_response(data={"updated": updated}, message="Đã đánh dấu tất cả là đã đọc.")


@router.delete("/{notif_id}", response_model=dict)
def delete_notification(
    notif_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    n = (
        db.query(Notification)
        .filter(Notification.id == notif_id, Notification.user_id == current_user.id)
        .first()
    )
    if not n:
        raise HTTPException(status_code=404, detail="Không tìm thấy thông báo.")
    db.delete(n)
    db.commit()
    return success_response(message="Đã xóa thông báo.")


@router.delete("/", response_model=dict)
def clear_all(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    deleted = (
        db.query(Notification)
        .filter(Notification.user_id == current_user.id)
        .delete(synchronize_session=False)
    )
    db.commit()
    return success_response(data={"deleted": deleted}, message="Đã xóa tất cả thông báo.")
