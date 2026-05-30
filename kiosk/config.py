"""Cấu hình cho trạm chấm công (Kiosk)."""

# ─── Backend ───────────────────────────────────────────────────────────────
import os


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


API_BASE_URL = os.getenv("API_BASE_URL", "https://datnlhn.onrender.com/api/v1").rstrip("/")
WS_URL = os.getenv("WS_URL", "wss://datnlhn.onrender.com/ws/kiosk")
DEVICE_ID = os.getenv("DEVICE_ID", "kiosk-001")

# Local outbox: luu su kien cham cong chua dong bo vao SQLite tren may kiosk.
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
#   • 1+ = webcam USB ngoài nếu có cắm thêm
# Chạy `python list_cameras.py` nếu muốn liệt kê các camera đang có.
CAMERA_SOURCE = 0

# CAMERA_BACKEND — backend OpenCV dùng để mở camera (Windows).
#   • "msmf"  → cv2.CAP_MSMF    (mặc định Windows, ổn định cho hầu hết webcam laptop)
#   • "dshow" → cv2.CAP_DSHOW   (DirectShow, dùng khi msmf không nhận được camera)
#   • "any"   → cv2.CAP_ANY     (để OpenCV tự chọn)
CAMERA_BACKEND = "dshow"

# Độ phân giải khung hình. Webcam laptop tích hợp thường tối đa 720p (1280x720),
# một số máy chỉ 480p. Backend dù sao cũng resize ảnh xuống UPLOAD_WIDTH trước
# khi đẩy vào ArcFace, nên 720p là điểm cân bằng giữa nét & độ trễ. Nếu webcam
# laptop yếu (chỉ 480p) thì OpenCV sẽ tự fallback về độ phân giải lớn nhất hỗ trợ.
FRAME_WIDTH = 1280
FRAME_HEIGHT = 720
FRAME_FPS = 30

# FOURCC codec yêu cầu camera trả về. Để rỗng cho webcam laptop tích hợp
# (OpenCV tự chọn codec phù hợp). Chỉ đặt "MJPG" nếu webcam USB ngoài bị tụt FPS.
CAMERA_FOURCC = ""

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
VERIFY_SHOTS = int(os.getenv("VERIFY_SHOTS", "1"))
VERIFY_SHOT_INTERVAL = float(os.getenv("VERIFY_SHOT_INTERVAL", "0.4"))   # giây giữa mỗi lần chụp

# ─── Burst capture (chọn frame nét nhất) ────────────────────────────────────
# Mỗi "shot" thực chất gồm BURST_FRAMES frame chụp liên tiếp; kiosk so sánh
# Laplacian variance (độ nét) của từng frame và chỉ gửi frame nét nhất lên
# backend. Giảm trường hợp gửi nhằm frame lúc đang chớp mắt / đang chuyển động.
# Trade-off: thêm ~BURST_FRAMES * BURST_INTERVAL giây độ trễ mỗi shot.
BURST_FRAMES   = 3
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

# Độ phân giải gửi lên backend — đây là đòn bẩy CHÍNH cho độ chính xác:
# detector trong DeepFace/InsightFace crop khuôn mặt rồi resize về 112×112
# cho ArcFace, nên ảnh upload càng nét → vùng crop càng nhiều pixel gốc →
# embedding càng ổn định.
#   • 800×600   — tiết kiệm băng thông, đủ cho webcam laptop chỉ 480p.
#   • 1280×720  — khuyến nghị cho webcam laptop 720p (tỉ lệ 16:9 khớp với
#                 độ phân giải gốc, không bị crop mất rìa).
#   • 1600×1200 — gần như là giới hạn hữu ích; vượt mức này chỉ tốn băng
#                 thông & RAM mà không cải thiện embedding rõ rệt.
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
