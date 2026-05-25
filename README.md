# HỆ THỐNG QUẢN LÝ NHÂN SỰ VÀ CHẤM CÔNG NHẬN DIỆN KHUÔN MẶT

**Đồ án tốt nghiệp** - Lê Hoài Nam - Lớp KTPM K21A  
**Trường**: ĐH Công nghệ Thông tin và Truyền thông - ĐH Thái Nguyên  
**GVHD**: ThS. Nguyễn Văn Việt  

---

## Tổng quan dự án

Hệ thống quản lý nhân sự và chấm công tự động ứng dụng nhận diện khuôn mặt qua Camera.  
Kiến trúc **Client-Server**, gồm 2 thành phần chính:

1. **Trạm chấm công (Attendance Station)** - Client cứng tại cửa ra vào, trang bị Camera + đầu đọc thẻ RFID (USB HID), chạy Python.
2. **Web Admin/User** - Giao diện quản trị nhân sự, chấm công, đơn từ, báo cáo.

---

## Công nghệ sử dụng

### Backend (Server)
- **Python 3.11+** với **FastAPI** - API server chính
- **DeepFace** hoặc **InsightFace** - Engine nhận diện khuôn mặt (Face Recognition)
- **OpenCV** - Xử lý hình ảnh từ Camera
- **SQLAlchemy** - ORM cho database
- **MySQL 8** (utf8mb4) - Cơ sở dữ liệu chính (nhân viên, chấm công, đơn từ)
- **PyMySQL** - MySQL driver cho SQLAlchemy (`mysql+pymysql://`)
- **WebSocket** (via FastAPI) - Đẩy kết quả nhận diện real-time về Trạm chấm công
- **schema.sql** - Khởi tạo schema thủ công (không dùng Alembic)
- **bcrypt / passlib** - Mã hóa mật khẩu
- **JWT (python-jose)** - Xác thực token
- **openpyxl / reportlab** - Xuất báo cáo Excel/PDF

### Frontend (Web)
- **React 18** + **TypeScript**
- **Vite** - Build tool
- **Tailwind CSS** - Styling
- **shadcn/ui** - Component library
- **React Query (TanStack Query)** - Server state management
- **React Router v6** - Routing
- **Recharts** - Biểu đồ thống kê
- **date-fns** - Xử lý ngày tháng
- **react-webcam** - Tích hợp Camera trên web

### Trạm chấm công (Attendance Kiosk)
- **Python 3.11+**
- **OpenCV** - Điều khiển Camera
- **evdev / hid** - Đọc tín hiệu thẻ RFID (USB HID, Plug & Play)
- **httpx** - Giao tiếp với Backend API
- **websockets** - Nhận phản hồi real-time từ Server
- **tkinter** hoặc **pygame** - Giao diện hiển thị kết quả tại Trạm

---

## Cấu trúc thư mục

```
/
├── backend/                    # FastAPI backend
│   ├── app/
│   │   ├── api/               # Route handlers
│   │   │   ├── auth.py        # Login/logout
│   │   │   ├── employees.py   # Quản lý nhân viên
│   │   │   ├── departments.py # Quản lý phòng ban
│   │   │   ├── attendance.py  # Chấm công, lịch sử
│   │   │   ├── face.py        # Đăng ký/xóa khuôn mặt
│   │   │   ├── rfid.py        # Quản lý thẻ RFID
│   │   │   ├── requests.py    # Đơn từ (nghỉ phép, đi muộn)
│   │   │   ├── reports.py     # Báo cáo thống kê
│   │   │   └── ws.py          # WebSocket endpoint
│   │   ├── core/
│   │   │   ├── config.py      # Cấu hình (env vars)
│   │   │   ├── security.py    # JWT, bcrypt
│   │   │   └── deps.py        # FastAPI dependencies
│   │   ├── models/            # SQLAlchemy ORM models
│   │   ├── schemas/           # Pydantic schemas (request/response)
│   │   ├── services/
│   │   │   ├── face_service.py    # Logic nhận diện khuôn mặt
│   │   │   ├── attendance_service.py
│   │   │   └── report_service.py
│   │   └── main.py            # FastAPI app entry point
│   ├── schema.sql             # MySQL schema (chạy 1 lần để tạo DB)
│   ├── tests/
│   ├── requirements.txt
│   └── .env.example
├── frontend/                  # React frontend
│   ├── src/
│   │   ├── components/        # Reusable UI components
│   │   ├── pages/             # Page components
│   │   │   ├── auth/          # Login page
│   │   │   ├── employee/      # Nhân viên: công, đơn từ
│   │   │   └── admin/         # Admin: quản lý, báo cáo
│   │   ├── hooks/             # Custom React hooks
│   │   ├── services/          # API call functions
│   │   ├── stores/            # State management (Zustand)
│   │   └── types/             # TypeScript types
│   ├── package.json
│   └── vite.config.ts
├── kiosk/                     # Trạm chấm công (Python script)
│   ├── main.py                # Entry point
│   ├── camera.py              # OpenCV camera handler
│   ├── rfid_reader.py         # USB HID RFID reader
│   ├── api_client.py          # Giao tiếp với backend
│   └── display.py             # Giao diện hiển thị
├── docker-compose.yml
└── CLAUDE.md
```

---

## Database Schema (các bảng chính)

| Bảng | Mô tả |
|------|-------|
| `departments` | Phòng ban |
| `employees` | Nhân viên (tên, email, phone, department_id, role, status) |
| `face_encodings` | Vector đặc trưng khuôn mặt (liên kết employee_id) |
| `rfid_cards` | Thẻ RFID (uid, employee_id, status: active/disabled) |
| `attendance_logs` | Lịch sử chấm công (employee_id, check_in, check_out, method) |
| `leave_requests` | Đơn từ (employee_id, type, start_date, end_date, reason, status) |
| `users` | Tài khoản đăng nhập (employee_id, password_hash, role, failed_attempts, locked_until) |

---

## Actors & Roles

| Actor | Quyền |
|-------|-------|
| **Nhân viên** | Xem thông tin cá nhân, tra cứu lịch sử chấm công, tạo/sửa/hủy đơn từ |
| **Quản lý / Admin** | Toàn bộ quyền nhân viên + quản lý nhân sự, khuôn mặt, thẻ RFID, duyệt đơn, báo cáo |

---

## Use Cases

| ID | Chức năng | Actor |
|----|-----------|-------|
| UC-1 | Đăng nhập | Tất cả |
| UC-2 | Đăng xuất | Tất cả |
| UC-3 | Điểm danh (khuôn mặt + RFID) | Nhân viên (tại Trạm) |
| UC-4 | Tra cứu lịch sử chấm công | Nhân viên |
| UC-5 | Quản lý đơn từ (tạo/sửa/hủy) | Nhân viên |
| UC-6 | Quản lý nhân viên (CRUD) | Quản lý |
| UC-7 | Quản lý phòng ban | Quản lý |
| UC-8 | Quản lý khuôn mặt (đăng ký/xóa) | Quản lý |
| UC-9 | Quản lý thẻ RFID (cấp phát/khóa) | Quản lý |
| UC-10 | Duyệt đơn từ (chấp thuận/từ chối) | Quản lý |
| UC-11 | Báo cáo thống kê + xuất Excel/PDF | Quản lý |

---

## Yêu cầu nghiệp vụ quan trọng

- Nhận diện khuôn mặt phải trả kết quả **< 2 giây/người**.
- Mật khẩu mã hóa bằng **bcrypt** (không dùng MD5).
- Tự động **khóa tài khoản tạm thời** sau **5 lần đăng nhập sai**.
- Tự động **đăng xuất sau 30 phút** không hoạt động (idle timeout).
- Hệ thống chỉ lưu **face encoding vector**, không lưu ảnh thô.
- Một thẻ RFID chỉ được gán cho **một nhân viên** tại một thời điểm.
- Chỉ được sửa/hủy đơn từ khi trạng thái là **"Chờ duyệt"**.
- Không thể xóa phòng ban khi còn nhân viên thuộc phòng ban đó.
- Đơn từ đã duyệt/từ chối không thể quay lại "Chờ duyệt".
- Số liệu báo cáo phải **trừ đi các ngày nghỉ phép đã được phê duyệt**.
- Phân trang: **20 bản ghi/trang**.

---

## API Conventions

- Tất cả API trả về JSON với format: `{ "success": bool, "data": any, "message": str }`
- Auth dùng **Bearer JWT token** trong header `Authorization`.
- Prefix API: `/api/v1/`
- WebSocket endpoint: `/ws/kiosk/{device_id}`
- HTTP status codes chuẩn: 200, 201, 400, 401, 403, 404, 422, 500.

---

## Hướng dẫn chạy dự án

### Backend
```bash
cd backend
pip install -r requirements.txt
cp .env.example .env                              # Cấu hình DATABASE_URL (MySQL), secret key
mysql -u root -p < schema.sql                     # Khởi tạo DB attendance_db (utf8mb4) + bảng
uvicorn app.main:app --reload --port 8000
```

> Ghi chú: `DATABASE_URL` có dạng `mysql+pymysql://<user>:<pass>@localhost:3306/attendance_db?charset=utf8mb4`. Yêu cầu MySQL 8 đang chạy trên máy.

### Frontend
```bash
cd frontend
npm install
npm run dev                   # http://localhost:5173
```

### Kiosk (Trạm chấm công)
```bash
cd kiosk
pip install -r requirements.txt
python main.py
```

### Docker (toàn bộ hệ thống)
```bash
docker-compose up -d
```

---

## Coding Guidelines

- Backend: **PEP 8**, type hints bắt buộc, dùng Pydantic v2 cho schemas.
- Frontend: **ESLint + Prettier**, functional components + React hooks.
- Commit message: tiếng Anh, dạng `feat:`, `fix:`, `refactor:` theo Conventional Commits.
- Không commit file `.env`, model weights, hoặc dữ liệu khuôn mặt thật.
- Test API với **pytest** cho backend; **Vitest** cho frontend.
