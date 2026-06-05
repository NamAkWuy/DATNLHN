"""
Client HTTP — gửi yêu cầu lên Backend API của hệ thống chấm công.

Mỗi hàm tương ứng với 1 endpoint backend:
    - verify_face:           xác thực khuôn mặt 1:1 với 1 nhân viên cụ thể
    - scan_rfid_card:        tra cứu nhân viên theo UID thẻ RFID
    - checkin_attendance:    ghi nhận chấm công vào / ra
    - register_face_from_kiosk: đăng ký khuôn mặt mới (cần quyền admin)
"""
import base64
import logging
import os
import sys
import threading
import time
import uuid
from datetime import datetime
from typing import Optional

import cv2
import httpx

from config import (
    API_BASE_URL,
    DEVICE_ID,
    LOCAL_OUTBOX_ENABLED,
    OUTBOX_BATCH_SIZE,
    OUTBOX_SYNC_INTERVAL,
    UPLOAD_WIDTH,
    UPLOAD_HEIGHT,
)

import local_store

logger = logging.getLogger(__name__)

# Dùng 1 client dùng chung — tái sử dụng kết nối TCP cho nhiều request liên tiếp
_client = httpx.Client(
    timeout=5.0,
    limits=httpx.Limits(max_keepalive_connections=3, max_connections=5),
)

# Cache token admin để khỏi đăng nhập lại mỗi lần đăng ký khuôn mặt
_admin_token: Optional[str] = None
_admin_token_issued_at: float = 0.0
_sync_stop = threading.Event()
_sync_thread: Optional[threading.Thread] = None
_sync_lock = threading.Lock()
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


# ---------------------------------------------------------------------------
# Pre-crop khuôn mặt (tối ưu hoá embedding ArcFace)
# ---------------------------------------------------------------------------

_FACE_DETECTOR: Optional[cv2.CascadeClassifier] = None


def _ascii_safe_path(path: str) -> str:
    """Workaround OpenCV không đọc được path Unicode trên Windows (ký tự Đ).
    Trả về Windows 8.3 short-name nếu path chứa non-ASCII."""
    if path.isascii() or sys.platform != "win32":
        return path
    try:
        import ctypes
        from ctypes import wintypes
        GetShortPathNameW = ctypes.windll.kernel32.GetShortPathNameW
        GetShortPathNameW.argtypes = [wintypes.LPCWSTR, wintypes.LPWSTR, wintypes.DWORD]
        GetShortPathNameW.restype = wintypes.DWORD
        buf = ctypes.create_unicode_buffer(260)
        n = GetShortPathNameW(path, buf, 260)
        if n and buf.value.isascii():
            return buf.value
    except Exception:
        pass
    return path


def _get_face_detector():
    """Lazy-load Haar cascade dùng để pre-crop face trước khi upload."""
    global _FACE_DETECTOR
    if _FACE_DETECTOR is not None:
        return _FACE_DETECTOR
    cascade_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "haarcascade_frontalface_default.xml",
    )
    if not os.path.exists(cascade_path):
        cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
    det = cv2.CascadeClassifier(_ascii_safe_path(cascade_path))
    if det.empty():
        logger.warning("Không load được Haar cascade cho pre-crop — sẽ gửi nguyên frame.")
        return None
    _FACE_DETECTOR = det
    return det


def _crop_face_for_upload(frame_bgr, padding_ratio: float = 0.6):
    """
    Tìm khuôn mặt lớn nhất trong frame rồi crop kèm padding rộng để gửi backend.

    Vì sao quan trọng:
      Backend nhận frame 1280×720 → Haar detect face ~200×200 px → MTCNN
      chỉ có 200²=40K pixel khuôn mặt để align landmark. Sau khi resize về
      112×112 cho ArcFace, mỗi pixel input mặt = ~3×3 pixel gốc → mất chi
      tiết. Pre-crop ở kiosk (face ~400×400 px chiếm phần lớn upload) →
      MTCNN có nhiều pixel hơn để align chuẩn → embedding ổn định hơn rõ
      rệt (+0.05-0.10 cosine với cùng người).

    Padding 60%: đủ context xung quanh (tóc, vai) cho MTCNN re-detect và
    align landmark; chặt hơn nữa thì MTCNN dễ fail vì không có khoảng đệm.

    Fallback: không detect được mặt → trả nguyên frame gốc, backend tự xử.
    """
    det = _get_face_detector()
    if det is None:
        return frame_bgr

    h_full, w_full = frame_bgr.shape[:2]
    gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
    faces = det.detectMultiScale(
        gray, scaleFactor=1.1, minNeighbors=4, minSize=(60, 60)
    )
    if len(faces) == 0:
        return frame_bgr

    # Mặt lớn nhất = mặt gần camera nhất = subject muốn verify
    x, y, w, h = max(faces, key=lambda f: f[2] * f[3])
    pad_w = int(w * padding_ratio)
    pad_h = int(h * padding_ratio)
    x1 = max(0, x - pad_w)
    y1 = max(0, y - pad_h)
    x2 = min(w_full, x + w + pad_w)
    y2 = min(h_full, y + h + pad_h)
    return frame_bgr[y1:y2, x1:x2]


def face_crop_to_base64(frame_bgr, jpeg_quality: int = 92) -> str:
    """
    Pre-crop khuôn mặt + encode JPEG chất lượng cao cho verify/register.

    Khác frame_to_base64:
      - Crop quanh face thay vì center-crop fix size → face dominate upload
      - JPEG q=92 (vs 85) → giữ chi tiết da/mắt cho ArcFace (artifact JPEG
        có thể làm tụt cosine ~0.02-0.04)
      - Cap kích thước 1024px cạnh dài để tránh payload quá lớn

    Fallback: nếu local detector miss → dùng frame_to_base64 (path cũ).
    """
    crop = _crop_face_for_upload(frame_bgr)
    if crop is frame_bgr:
        return frame_to_base64(frame_bgr)

    h, w = crop.shape[:2]
    max_dim = 1024
    if max(h, w) > max_dim:
        scale = max_dim / max(h, w)
        crop = cv2.resize(crop, (int(w * scale), int(h * scale)),
                          interpolation=cv2.INTER_AREA)

    _, buffer = cv2.imencode(".jpg", crop, [cv2.IMWRITE_JPEG_QUALITY, jpeg_quality])
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

def _new_attendance_payload(employee_id: int, method: str, rfid_uid: str = None) -> dict:
    payload = {
        "employee_id": employee_id,
        "method": method,
        "occurred_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "client_event_id": str(uuid.uuid4()),
        "device_id": DEVICE_ID,
    }
    if rfid_uid:
        payload["rfid_uid"] = rfid_uid
    return payload


def _post_attendance_payload(payload: dict):
    return _post("/attendance/checkin", payload, timeout=8.0)


def _safe_store_call(fn, *args) -> bool:
    try:
        fn(*args)
        return True
    except Exception as exc:
        logger.error(f"Lỗi ghi SQLite outbox kiosk: {exc}")
        return False


def _handle_attendance_response(status, data, event_id: str,
                                outbox_saved: bool = True) -> Optional[dict]:
    if status == 200:
        if LOCAL_OUTBOX_ENABLED and outbox_saved:
            _safe_store_call(local_store.mark_synced, event_id)
        return data

    if status is None or status >= 500:
        if LOCAL_OUTBOX_ENABLED and outbox_saved:
            _safe_store_call(
                local_store.mark_pending,
                event_id,
                "network" if status is None else f"http_{status}",
            )
            return {"error": "queued_offline", "client_event_id": event_id}
        return None

    if LOCAL_OUTBOX_ENABLED and outbox_saved:
        _safe_store_call(local_store.mark_failed, event_id, f"http_{status}")

    if status == 400:
        return {"error": "already_checked_out"}
    if status == 403:
        return {"error": "employee_inactive"}
    return None


def sync_pending_attendance_events() -> int:
    if not LOCAL_OUTBOX_ENABLED:
        return 0

    synced = 0
    with _sync_lock:
        for item in local_store.pending_events(limit=OUTBOX_BATCH_SIZE):
            event_id = item["event_id"]
            payload = item["payload"]
            local_store.mark_sending(event_id)
            status, data = _post_attendance_payload(payload)
            if status == 200:
                local_store.mark_synced(event_id)
                synced += 1
                logger.info(f"Đã đồng bộ sự kiện chấm công offline: {event_id}")
            elif status is None or status >= 500:
                local_store.mark_pending(event_id, "network" if status is None else f"http_{status}")
            else:
                local_store.mark_failed(event_id, f"http_{status}")
                logger.warning(f"Sự kiện chấm công bị từ chối khi đồng bộ: {event_id} ({status})")
    return synced


def start_outbox_sync_worker() -> None:
    global _sync_thread
    if not LOCAL_OUTBOX_ENABLED:
        return
    if _sync_thread and _sync_thread.is_alive():
        return

    local_store.init_db()
    _sync_stop.clear()

    def _loop():
        while not _sync_stop.is_set():
            try:
                sync_pending_attendance_events()
            except Exception as exc:
                logger.error(f"Lỗi đồng bộ outbox kiosk: {exc}")
            _sync_stop.wait(OUTBOX_SYNC_INTERVAL)

    _sync_thread = threading.Thread(target=_loop, name="attendance-outbox-sync", daemon=True)
    _sync_thread.start()


def stop_outbox_sync_worker() -> None:
    _sync_stop.set()


def verify_face(employee_id: int, frame_bgr) -> Optional[dict]:
    """Xác thực khuôn mặt 1:1 — so ảnh với encoding của 1 nhân viên cụ thể."""
    image_base64 = face_crop_to_base64(frame_bgr)
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
        {"error": "queued_offline"}        — đã lưu tạm, sẽ đồng bộ lại
        None                               — lỗi không xác định
    """
    payload = _new_attendance_payload(employee_id, method, rfid_uid)
    event_id = payload["client_event_id"]

    outbox_saved = False
    if LOCAL_OUTBOX_ENABLED:
        outbox_saved = _safe_store_call(local_store.save_event, payload, "sending")

    status, data = _post_attendance_payload(payload)
    return _handle_attendance_response(status, data, event_id, outbox_saved)


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

    # Enroll cũng pre-crop face + JPEG q=92 — gallery template chất lượng cao
    # ngay từ đầu sẽ giúp mọi lần verify sau dễ match hơn rõ rệt.
    payload = {"image_base64": face_crop_to_base64(frame_bgr)}
    if extra_frames:
        payload["extra_images"] = [face_crop_to_base64(f) for f in extra_frames]

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
