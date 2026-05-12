"""
Hàm phụ trợ để tạo thông báo cho người dùng.
Dùng các hàm này từ route handler khi cần đẩy thông báo
(VD: tạo đơn từ → báo cho admin; duyệt / từ chối → báo cho nhân viên).
"""
from typing import Optional, Iterable

from sqlalchemy.orm import Session

from app.models.notification import Notification
from app.models.user import User


def create_notification(
    db: Session,
    user_id: int,
    type: str,
    title: str,
    message: str,
    link: Optional[str] = None,
    commit: bool = True,
) -> Notification:
    n = Notification(
        user_id=user_id,
        type=type,
        title=title,
        message=message,
        link=link,
    )
    db.add(n)
    if commit:
        db.commit()
        db.refresh(n)
    else:
        db.flush()
    return n


def notify_users(
    db: Session,
    user_ids: Iterable[int],
    type: str,
    title: str,
    message: str,
    link: Optional[str] = None,
) -> int:
    count = 0
    for uid in user_ids:
        db.add(
            Notification(
                user_id=uid,
                type=type,
                title=title,
                message=message,
                link=link,
            )
        )
        count += 1
    if count:
        db.commit()
    return count


def notify_admins(
    db: Session,
    type: str,
    title: str,
    message: str,
    link: Optional[str] = None,
) -> int:
    admin_ids = [u.id for u in db.query(User.id).filter(User.role == "admin").all()]
    return notify_users(db, admin_ids, type, title, message, link)


def notify_employee(
    db: Session,
    employee_id: int,
    type: str,
    title: str,
    message: str,
    link: Optional[str] = None,
) -> Optional[Notification]:
    user = db.query(User).filter(User.employee_id == employee_id).first()
    if not user:
        return None
    return create_notification(db, user.id, type, title, message, link)
