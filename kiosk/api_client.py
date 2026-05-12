"""
Client HTTP — gửi yêu cầu lên Backend API của hệ thống chấm công.

Mỗi hàm tương ứng với 1 endpoint backend:
    - recognize_face:        nhận diện khuôn mặt 1:N
    - verify_face:           xác thực khuôn mặt 1:1 với 1 nhân viên cụ thể
    - scan_rfid_card:        tra cứu nhân viên theo UID thẻ RFID
    - checkin_attendance:    ghi nhận chấm công vào / ra
    - register_face_from_kiosk: đăng ký khuôn mặt mới (cần quyền admin)
"""
import base64
import logging
import time
from typing import Optional

import cv2
import httpx

from config import API_BASE_URL, UPLOAD_WIDTH, UPLOAD_HEIGHT

logger = logging.getLogger(__name__)

# Dùng 1 client dùng chung — tái sử dụng kết nối TCP cho nhiều request liên tiếp
_client = httpx.Client(
    timeout=5.0,
    limits=httpx.Limits(max_keepalive_connections=3, max_connections=5),
)

# Cache token admin để khỏi đăng nhập lại mỗi lần đăng ký khuôn mặt
_admin_token: Optional[str] = None
_admin_token_issued_at: float = 0.0
_TOKEN_TTL = 82800.0  # 23 giờ — JWT mặc định hết hạn sau 24h


# ---------------------------------------------------------------------------
# Hàm phụ trợ
# ---------------------------------------------------------------------------

def frame_to_base64(frame_bgr) -> str:
    """
    Chuyển ảnh từ camera (numpy BGR) → chuỗi base64 JPEG để gửi qua API.
    Resize về kích thước UPLOAD_WIDTH × UPLOAD_HEIGHT (mặc định 640×480),
    giữ tỉ lệ gốc bằng cách scale + crop ở giữa, nén JPEG chất lượng 85.
    """
    h, w = frame_bgr.shape[:2]
    target_w, target_h = UPLOAD_WIDTH, UPLOAD_HEIGHT

    scale = max(target_w / w, target_h / h)
    new_w, new_h = int(w * scale), int(h * scale)
    resized = cv2.resize(frame_bgr, (new_w, new_h), interpolation=cv2.INTER_AREA)

    x_off = (new_w - target_w) // 2
    y_off = (new_h - target_h) // 2
    cropped = resized[y_off:y_off + target_h, x_off:x_off + target_w]

    _, buffer = cv2.imencode(".jpg", cropped, [cv2.IMWRITE_JPEG_QUALITY, 85])
    return base64.b64encode(buffer.tobytes()).decode("utf-8")


def _post(path: str, payload: dict, headers: dict = None, timeout: float = None):
    """
    Gửi POST đến backend, trả về (status_code, data).

    Backend luôn trả JSON dạng: {"success": bool, "data": ..., "message": ...}
    - Nếu thành công (200 + success=True)  → trả về (200, data)
    - Nếu lỗi nghiệp vụ (400/401/403/...)  → trả về (status_code, None)
    - Nếu lỗi mạng / ngoại lệ              → trả về (None, None)
    """
    try:
        res = _client.post(f"{API_BASE_URL}{path}", json=payload,
                           headers=headers, timeout=timeout)
        if res.status_code == 200:
            body = res.json()
            if body.get("success"):
                return 200, body.get("data")
        logger.warning(f"POST {path} lỗi: {res.status_code} - {res.text[:120]}")
        return res.status_code, None
    except Exception as e:
        logger.error(f"Lỗi mạng khi gọi {path}: {e}")
        return None, None


# ---------------------------------------------------------------------------
# Các API chính dùng tại trạm chấm công
# ---------------------------------------------------------------------------

def recognize_face(frame_bgr) -> Optional[dict]:
    """Nhận diện khuôn mặt 1:N — backend tự tìm xem ảnh là ai."""
    image_base64 = frame_to_base64(frame_bgr)
    _, data = _post("/face/recognize", {"image_base64": image_base64})
    return data


def verify_face(employee_id: int, frame_bgr) -> Optional[dict]:
    """Xác thực khuôn mặt 1:1 — so ảnh với encoding của 1 nhân viên cụ thể."""
    image_base64 = frame_to_base64(frame_bgr)
    _, data = _post(f"/face/verify/{employee_id}", {"image_base64": image_base64})
    return data


def scan_rfid_card(uid: str) -> Optional[dict]:
    """Tra cứu nhân viên theo UID thẻ RFID."""
    _, data = _post("/rfid/scan", {"uid": uid})
    return data


def checkin_attendance(employee_id: int, method: str = "face",
                       rfid_uid: str = None) -> Optional[dict]:
    """
    Ghi nhận chấm công (vào hoặc ra) cho nhân viên.

    Trả về:
        {"action": ..., "log": ...}        — thành công
        {"error": "already_checked_out"}   — đã chấm ra hôm nay (HTTP 400)
        {"error": "employee_inactive"}     — tài khoản bị khóa (HTTP 403)
        None                               — lỗi mạng / lỗi không xác định
    """
    payload = {"employee_id": employee_id, "method": method}
    if rfid_uid:
        payload["rfid_uid"] = rfid_uid

    status, data = _post("/attendance/checkin", payload)
    if status == 200:
        return data
    if status == 400:
        return {"error": "already_checked_out"}
    if status == 403:
        return {"error": "employee_inactive"}
    return None


# ---------------------------------------------------------------------------
# Đăng ký khuôn mặt từ kiosk (cần quyền admin)
# ---------------------------------------------------------------------------

def _get_admin_token() -> Optional[str]:
    """Lấy token admin (dùng cache, chỉ đăng nhập lại khi token hết hạn)."""
    global _admin_token, _admin_token_issued_at
    from config import ADMIN_USERNAME, ADMIN_PASSWORD

    # Token còn hạn → dùng lại
    if _admin_token and (time.time() - _admin_token_issued_at) < _TOKEN_TTL:
        return _admin_token

    logger.info("Đăng nhập lại để lấy admin token...")
    _, data = _post("/auth/login",
                    {"username": ADMIN_USERNAME, "password": ADMIN_PASSWORD})
    if data:
        _admin_token = data["access_token"]
        _admin_token_issued_at = time.time()
        logger.info("Đã có admin token.")
        return _admin_token

    logger.error("Đăng nhập admin thất bại.")
    return None


def register_face_from_kiosk(
    employee_id: int,
    frame_bgr,
    extra_frames: Optional[list] = None,
) -> Optional[dict]:
    """
    Đăng ký khuôn mặt cho nhân viên ngay tại kiosk (bấm phím R).
    Gọi POST /face/register/{employee_id} kèm token admin.

    `extra_frames` — danh sách frame phụ (góc khác / ánh sáng khác) để seed
    gallery multi-pose. Backend lưu ảnh chính làm primary template, các ảnh
    phụ làm adaptive template ngay từ lần đăng ký đầu.
    """
    global _admin_token, _admin_token_issued_at

    token = _get_admin_token()
    if not token:
        logger.error("Không thể lấy admin token để đăng ký khuôn mặt.")
        return None

    payload = {"image_base64": frame_to_base64(frame_bgr)}
    if extra_frames:
        payload["extra_images"] = [frame_to_base64(f) for f in extra_frames]

    # Multi-pose enrollment có thể tốn vài giây để extract embedding cho từng
    # ảnh extra (mỗi ảnh ~0.5-1s với MTCNN+ArcFace), tăng timeout cho an toàn.
    timeout = 10.0 + (3.0 * len(extra_frames or []))

    status, data = _post(
        f"/face/register/{employee_id}",
        payload,
        headers={"Authorization": f"Bearer {token}"},
        timeout=timeout,
    )

    if status == 200:
        logger.info(f"Đăng ký khuôn mặt thành công cho NV {employee_id}.")
        return data

    # Token bị từ chối → xóa cache để lần sau lấy lại
    if status == 401:
        _admin_token = None
        _admin_token_issued_at = 0.0
        logger.warning("Admin token bị từ chối (401), đã xóa khỏi cache.")

    return None
