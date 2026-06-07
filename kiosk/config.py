"""Cấu hình cho trạm chấm công (Kiosk)."""

# ─── Backend ───────────────────────────────────────────────────────────────
import os


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000/api/v1").rstrip("/")
WS_URL = os.getenv("WS_URL", "http://localhost:8000/ws/kiosk").rstrip("/")
DEVICE_ID = os.getenv("DEVICE_ID", "kiosk-001")

# Local outbox: lưu sự kiện chấm công chưa đồng bộ vào SQLite trên máy kiosk.
LOCAL_OUTBOX_ENABLED = _env_bool("LOCAL_OUTBOX_ENABLED", True)
LOCAL_OUTBOX_DB = os.getenv(
    "LOCAL_OUTBOX_DB",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "attendance_outbox.sqlite3"),
)
OUTBOX_SYNC_INTERVAL = float(os.getenv("OUTBOX_SYNC_INTERVAL", "10"))
OUTBOX_BATCH_SIZE = int(os.getenv("OUTBOX_BATCH_SIZE", "20"))

# ─── Camera ─────────────────────────────────────────────────────────────
# CAMERA_SOURCE — nguồn camera:
#   • 0  = webcam tích hợp của laptop (mặc định)
#   • 1+ = webcam USB ngoài / virtual camera (Iriun, OBS, ...) nếu có
# Chạy `python list_cameras.py` nếu muốn liệt kê các camera đang có.
# Đặt 1 cho iPhone qua Iriun Webcam — virtual cam thường ở index 1 (sau
# webcam laptop ở index 0). Nếu mở kiosk thấy nhầm webcam laptop, đổi sang 2.
CAMERA_SOURCE = 0

# CAMERA_BACKEND — backend OpenCV dùng để mở camera (Windows).
#   • "msmf"  → cv2.CAP_MSMF    (mặc định Windows, ổn định cho hầu hết webcam laptop)
#   • "dshow" → cv2.CAP_DSHOW   (DirectShow, dùng khi msmf không nhận được camera)
#   • "any"   → cv2.CAP_ANY     (để OpenCV tự chọn)
CAMERA_BACKEND = "dshow"

# Độ phân giải khung hình. Iriun Webcam (bản free) khoá tối đa 720p, set
# 1080p sẽ bị driver từ chối hoặc rớt FPS. Webcam laptop 480p sẽ tự fallback.
FRAME_WIDTH = 1280
FRAME_HEIGHT = 720
FRAME_FPS = 30

# FOURCC codec yêu cầu camera trả về.
#   • "MJPG" — JPEG nén/frame, decode nhanh, giảm trễ với virtual cam như
#     Iriun (raw YUY2 ở 720p vẫn ~1.4 MB/frame, MJPG xuống còn ~80 KB).
#   • Để rỗng nếu dùng webcam laptop tích hợp (driver thường tự chọn ổn).
CAMERA_FOURCC = "MJPG"

# Xoay frame sau khi đọc từ camera (độ): 0, 90, 180, 270.
# Mặc định 0 = giữ nguyên frame Iriun/camera gửi tới (không xoay). Chỉ đổi
# nếu thực sự cần — set qua biến môi trường: CAMERA_ROTATE=90 trước khi chạy.
CAMERA_ROTATE = int(os.getenv("CAMERA_ROTATE", "0"))

# Phát hiện khuôn mặt trên ảnh đã thu nhỏ về DETECT_WIDTH px (giữ nguyên
# tỷ lệ). CascadeClassifier chạy trên 1920×1080 tốn ~16× CPU so với 480px,
# trong khi mục đích chỉ để vẽ khung lên màn hình. Ảnh gửi backend vẫn là
# frame gốc đầy đủ chi tiết.
# 640px: phát hiện được khuôn mặt nhỏ/xa hơn (ngưỡng minSize=60px tương
# đương khuôn mặt cách camera ~1.2m), Ryzen 5 7000 dư sức xử lý mỗi frame.
DETECT_WIDTH = 640

# ─── Xác thực nhiều lần (multi-shot) ────────────────────────────────────────
# Số lần chụp xác thực sau khi quẹt RFID — cả N lần đều phải khớp thì mới ghi
# nhận chấm công. Giúp giảm mạnh trường hợp người khác qua mặt (false positive).
# Mỗi shot đã là 1 burst BURST_FRAMES frame chọn frame nét nhất → tăng SHOTS
# chủ yếu để chặn impersonation.
#   1 → nhanh nhất, ưu tiên UX (mặc định demo)
#   2 → cân bằng
#   3 → an toàn nhất, +0.5-0.7s trễ happy path
VERIFY_SHOTS = int(os.getenv("VERIFY_SHOTS", "2"))
VERIFY_SHOT_INTERVAL = float(os.getenv("VERIFY_SHOT_INTERVAL", "0.4"))   # giây giữa mỗi lần chụp

# Tự retry khi backend trả lỗi chất lượng (mờ/tối/nhỏ) — burst lại tối đa N
# lần trước khi báo lỗi cho user. Mỗi lần là 1 burst BURST_FRAMES frame mới,
# user đứng yên thường chỉ cần 1-2 retry là có frame đủ tốt.
VERIFY_QUALITY_RETRIES = int(os.getenv("VERIFY_QUALITY_RETRIES", "2"))

# ─── Burst capture (chọn frame nét nhất) ────────────────────────────────────
# Mỗi "shot" thực chất gồm BURST_FRAMES frame chụp liên tiếp; kiosk so sánh
# Laplacian variance (độ nét) của từng frame và chỉ gửi frame nét nhất lên
# backend. Giảm trường hợp gửi nhằm frame lúc đang chớp mắt / đang chuyển động.
# Trade-off: thêm ~BURST_FRAMES * BURST_INTERVAL giây độ trễ mỗi shot.
# 8 frame × 50ms = 400ms — chấp nhận trễ ~150ms để xác suất có frame nét cao
# hơn nhiều. Quan trọng khi user vừa quẹt RFID xong còn đang ngẩng đầu, cử
# động vài chục ms đầu → cần đủ window để chộp lúc đứng yên.
BURST_FRAMES   = 8
BURST_INTERVAL = 0.05  # giây — đủ để OpenCV lấy được frame mới từ camera

# ─── Multi-pose enrollment (đăng ký nhiều góc) ──────────────────────────────
# Khi bấm R, kiosk sẽ chụp ENROLL_POSES ảnh cách nhau ENROLL_POSE_INTERVAL giây
# rồi gửi lên backend làm 1 template chính + (ENROLL_POSES-1) template phụ.
# Người đăng ký được hướng dẫn "nhìn thẳng → quay nhẹ trái → quay nhẹ phải" để
# gallery seed có sẵn nhiều góc nhìn → giảm false-reject từ lần verify đầu.
#
# Lưu ý: luồng đăng ký chính của hệ thống là trên web admin (có hướng dẫn pose
# có/không kính chi tiết hơn). Phím R trên kiosk chỉ là fallback khi cần đăng
# ký nhanh tại trạm — giữ ở 3 pose đơn giản, không có hướng dẫn kính.
ENROLL_POSES         = 3
ENROLL_POSE_INTERVAL = 1.0  # giây giữa mỗi lần chụp khi đăng ký

# Tương thích ngược — main.py phiên bản cũ vẫn import CAMERA_INDEX
CAMERA_INDEX = CAMERA_SOURCE

# ─── Hiển thị kết quả ───────────────────────────────────────────────────────
DISPLAY_RESULT_DURATION = 3.0    # Giây hiển thị kết quả trên màn hình

# DISPLAY_SCALE — hệ số phóng frame trước khi vẽ overlay & gửi cv2.imshow.
#   1.0 = vẽ ở native cam res (1280×720) → OpenCV tự bilinear lên fullscreen → mờ
#   1.5 = vẽ ở 1920×1080 → fullscreen 1080p không cần upscale thêm → sắc nét
#   2.0 = vẽ ở 2560×1440 → cho màn 2K, tốn ~2× CPU vẽ
# Pipeline: Lanczos4 upscale frame → vẽ overlay (text Pillow render ở high-res
# → sắc) → imshow. Hơi tốn ~5-10ms/frame trên Ryzen 7000, đáng giá cho demo.
DISPLAY_SCALE = float(os.getenv("DISPLAY_SCALE", "2.0"))

# Độ phân giải gửi lên backend — đây là đòn bẩy CHÍNH cho độ chính xác:
# detector trong DeepFace/InsightFace crop khuôn mặt rồi resize về 112×112
# cho ArcFace, nên ảnh upload càng nét → vùng crop càng nhiều pixel gốc →
# embedding càng ổn định.
#   • 800×600   — tiết kiệm băng thông, đủ cho webcam laptop chỉ 480p.
#   • 1280×720  — khớp với Iriun free / webcam laptop 720p; gửi nguyên frame
#                 gốc không phải upscale → không tạo pixel giả.
#   • 1600×1200 — chỉ hữu ích khi camera gốc thực sự cao hơn 720p.
UPLOAD_WIDTH = 1280
UPLOAD_HEIGHT = 720

# ─── Đầu đọc RFID (giả lập bàn phím USB HID) ────────────────────────────────
RFID_ENABLED = True
RFID_AUTO_SUBMIT_TIMEOUT = 0.12  # giây im lặng → tự động gửi UID

# ─── Tài khoản admin (để kiosk tự đăng ký khuôn mặt qua phím R) ─────────────
ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "admin123"

# ─── Hiển thị ───────────────────────────────────────────────────────────────
# Lưu ý: dùng tiếng Việt không dấu vì OpenCV không render được dấu Unicode
# trên thanh tiêu đề cửa sổ.
WINDOW_TITLE = "Tram Cham Cong - Nhan Dien Khuon Mat"
