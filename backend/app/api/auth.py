from datetime import datetime, timezone, timedelta
from app.utils import now_vn

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import create_access_token, get_current_user, success_response
from app.database import get_db
from app.models.user import User
from app.schemas.auth import LoginRequest, TokenResponse, UserInfo
from passlib.context import CryptContext

router = APIRouter()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

LOCK_ATTEMPTS = 5
LOCK_MINUTES = 15


@router.post("/login", response_model=dict)
def login(body: LoginRequest, db: Session = Depends(get_db)):
    user: User | None = db.query(User).filter(User.username == body.username).first()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Tên đăng nhập hoặc mật khẩu không đúng.",
        )

    # Kiểm tra tài khoản có đang bị khóa không
    now = now_vn()
    if user.locked_until:
        if now < user.locked_until:
            remaining = int((user.locked_until - now).total_seconds() / 60) + 1
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Tài khoản đang bị khóa. Vui lòng thử lại sau {remaining} phút.",
            )
        else:
            # Hết hạn khóa → mở khóa
            user.locked_until = None
            user.failed_attempts = 0
            db.commit()

    # Xác thực mật khẩu
    if not pwd_context.verify(body.password, user.password_hash):
        user.failed_attempts = (user.failed_attempts or 0) + 1
        if user.failed_attempts >= LOCK_ATTEMPTS:
            user.locked_until = now_vn() + timedelta(minutes=LOCK_MINUTES)
            user.failed_attempts = 0
            db.commit()
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Đăng nhập sai quá {LOCK_ATTEMPTS} lần. Tài khoản bị khóa {LOCK_MINUTES} phút.",
            )
        db.commit()
        remaining = LOCK_ATTEMPTS - user.failed_attempts
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Tên đăng nhập hoặc mật khẩu không đúng. Còn {remaining} lần thử trước khi bị khóa.",
        )

    # Đăng nhập thành công
    user.failed_attempts = 0
    user.locked_until = None
    user.last_login = now_vn()
    db.commit()

    token = create_access_token({"sub": str(user.id), "role": user.role})

    full_name = None
    if user.employee:
        full_name = user.employee.full_name

    user_info = UserInfo(
        id=user.id,
        username=user.username,
        role=user.role,
        employee_id=user.employee_id,
        full_name=full_name,
    )

    return success_response(
        data=TokenResponse(access_token=token, token_type="bearer", user=user_info).model_dump(),
        message="Đăng nhập thành công.",
    )


@router.post("/logout", response_model=dict)
def logout(current_user: User = Depends(get_current_user)):
    return success_response(message="Đăng xuất thành công.")


@router.get("/me", response_model=dict)
def get_me(current_user: User = Depends(get_current_user)):
    full_name = None
    if current_user.employee:
        full_name = current_user.employee.full_name

    user_info = UserInfo(
        id=current_user.id,
        username=current_user.username,
        role=current_user.role,
        employee_id=current_user.employee_id,
        full_name=full_name,
    )
    return success_response(data=user_info.model_dump())
