"""
Điểm khởi chạy của ứng dụng FastAPI.
Hệ thống Quản lý Nhân sự & Chấm công bằng Nhận diện Khuôn mặt.
"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api import auth, departments, employees, face, rfid, attendance, leave_requests, reports, ws, notifications
from app.api.attendance import set_broadcast_fn
from app.api.ws import broadcast_attendance_event
from app.config import settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Khởi động
    logger.info("Đang khởi động Hệ thống Chấm công...")

    # Tạo các bảng database
    from app.database import create_tables
    create_tables()
    logger.info("Đã tạo / kiểm tra các bảng database.")

    # Chạy seed nếu database còn trống
    from app.database import SessionLocal
    from app.seed import run_seed
    db = SessionLocal()
    try:
        run_seed(db)
    finally:
        db.close()

    # Gắn hàm broadcast WebSocket vào module attendance
    set_broadcast_fn(broadcast_attendance_event)

    logger.info("Ứng dụng sẵn sàng. Tài liệu API: http://localhost:8000/docs")
    yield

    # Tắt
    logger.info("Đang tắt ứng dụng...")


app = FastAPI(
    title="Hệ thống Quản lý Nhân sự & Chấm công",
    description=(
        "Hệ thống chấm công và quản lý nhân sự bằng nhận diện khuôn mặt. "
        "Hỗ trợ nhận diện khuôn mặt, thẻ RFID, chấm công thủ công, "
        "đơn từ và báo cáo thống kê."
    ),
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# ---------------------------------------------------------------------------
# Cấu hình CORS
# ---------------------------------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# File tĩnh (ảnh đại diện)
# ---------------------------------------------------------------------------
import os
os.makedirs("uploads/avatars", exist_ok=True)
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")

# ---------------------------------------------------------------------------
# Khai báo các router của API
# ---------------------------------------------------------------------------
API_PREFIX = "/api/v1"

app.include_router(auth.router,          prefix=f"{API_PREFIX}/auth",        tags=["Xác thực"])
app.include_router(departments.router,   prefix=f"{API_PREFIX}/departments",  tags=["Phòng ban"])
app.include_router(employees.router,     prefix=f"{API_PREFIX}/employees",    tags=["Nhân viên"])
app.include_router(face.router,          prefix=f"{API_PREFIX}/face",         tags=["Nhận diện khuôn mặt"])
app.include_router(rfid.router,          prefix=f"{API_PREFIX}/rfid",         tags=["Thẻ RFID"])
app.include_router(attendance.router,    prefix=f"{API_PREFIX}/attendance",   tags=["Chấm công"])
app.include_router(leave_requests.router,prefix=f"{API_PREFIX}/requests",     tags=["Đơn từ"])
app.include_router(reports.router,       prefix=f"{API_PREFIX}/reports",      tags=["Báo cáo"])
app.include_router(notifications.router, prefix=f"{API_PREFIX}/notifications", tags=["Thông báo"])
app.include_router(ws.router,            prefix="/ws",                        tags=["WebSocket"])


# ---------------------------------------------------------------------------
# Kiểm tra tình trạng dịch vụ
# ---------------------------------------------------------------------------
@app.get("/health", tags=["Tình trạng"])
def health_check():
    return {"status": "ok", "service": "HR Attendance System"}


@app.get("/", tags=["Tình trạng"])
def root():
    return {
        "message": "HR Attendance & Management System API",
        "version": "1.0.0",
        "docs": "/docs",
        "health": "/health",
    }
