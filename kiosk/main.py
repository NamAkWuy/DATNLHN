"""
Trạm chấm công Kiosk — Điểm khởi chạy chính
============================================
Quy trình:
  1. Người dùng quẹt thẻ RFID → hệ thống xác định nhân viên
  2. Kiosk chụp ảnh và xác thực khuôn mặt với dữ liệu đã đăng ký
  3. Nếu khớp → ghi nhận chấm công (vào / ra)
  4. Nếu không khớp → thông báo lỗi

Phím điều khiển:
  Q / ESC  →  Thoát
  R        →  Chế độ đăng ký khuôn mặt (nhập mã NV bằng số, Enter để xác nhận)
"""
import logging
import os
import time
import sys
import threading
from datetime import datetime

import cv2
import numpy as np

import api_client
import display
from config import (
    CAMERA_INDEX, CAMERA_BACKEND, FRAME_WIDTH, FRAME_HEIGHT,
    FRAME_FPS, CAMERA_FOURCC, CAMERA_ROTATE, DETECT_WIDTH,
    DISPLAY_RESULT_DURATION, DISPLAY_SCALE,
    RFID_ENABLED, RFID_AUTO_SUBMIT_TIMEOUT, WINDOW_TITLE,
    VERIFY_SHOTS, VERIFY_SHOT_INTERVAL, VERIFY_QUALITY_RETRIES,
    BURST_FRAMES, BURST_INTERVAL,
    ENROLL_POSES, ENROLL_POSE_INTERVAL,
)


_ROTATE_MAP = {
    90:  cv2.ROTATE_90_CLOCKWISE,
    180: cv2.ROTATE_180,
    270: cv2.ROTATE_90_COUNTERCLOCKWISE,
}


_BACKEND_MAP = {
    "msmf":  cv2.CAP_MSMF,    # Media Foundation — mặc định Windows, ổn cho webcam laptop
    "dshow": cv2.CAP_DSHOW,   # DirectShow — fallback nếu MSMF không nhận camera
    "any":   cv2.CAP_ANY,
}


def _fmt_time(iso_str: str) -> str:
    """Hiển thị HH:MM từ ISO datetime do server trả về (đã có offset +07:00)."""
    if not iso_str:
        return ""
    try:
        return datetime.fromisoformat(iso_str).strftime("%H:%M")
    except Exception:
        return iso_str[11:16]

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Bộ phát hiện khuôn mặt (face detector)
# ---------------------------------------------------------------------------

def _ascii_safe_path(path: str) -> str:
    """Đổi sang Windows 8.3 short-name nếu path chứa ký tự ngoài ASCII.

    OpenCV trên Windows dùng ANSI API (cp1252) cho cv::FileStorage, không mở
    được file có ký tự Unicode trong path (vd: Đ, ă, ô...). GetShortPathNameW
    trả về dạng "DATNLH~1" đảm bảo ASCII-only.
    """
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


def load_face_detector():
    cascade_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "haarcascade_frontalface_default.xml",
    )
    safe_path = _ascii_safe_path(cascade_path)
    detector = cv2.CascadeClassifier(safe_path)
    if detector.empty():
        logger.error(f"Không tải được bộ phát hiện khuôn mặt: {cascade_path}")
        sys.exit(1)
    logger.info("Bộ phát hiện khuôn mặt sẵn sàng.")
    return detector


def detect_faces(frame_gray, detector, scale: float = 1.0):
    """Phát hiện khuôn mặt trên ảnh xám và scale lại tọa độ về frame gốc.

    `scale` = (chiều rộng frame gốc) / (chiều rộng ảnh đưa vào detector).
    Khi gọi với ảnh đã downscale, các tọa độ trả về sẽ tự nhân lên để vẽ
    đúng vị trí trên frame full-resolution.
    """
    faces = detector.detectMultiScale(
        frame_gray,
        scaleFactor=1.1,
        minNeighbors=3,
        minSize=(60, 60),
    )
    if len(faces) == 0:
        return []
    if scale == 1.0:
        return faces.tolist()
    return [[int(x * scale), int(y * scale), int(w * scale), int(h * scale)]
            for (x, y, w, h) in faces]


# ---------------------------------------------------------------------------
# Xử lý chấm công
# ---------------------------------------------------------------------------

def _laplacian_variance(frame_bgr) -> float:
    """Đo độ nét của frame — cao = nhiều cạnh sắc, thấp = mờ."""
    gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


# Cache detector dành riêng cho _wait_for_face (tránh load lại mỗi lần quẹt thẻ).
_WAIT_DETECTOR = None


def _get_wait_detector():
    global _WAIT_DETECTOR
    if _WAIT_DETECTOR is None:
        _WAIT_DETECTOR = load_face_detector()
    return _WAIT_DETECTOR


def _wait_for_face(get_latest_frame, timeout: float = 2.0,
                   poll_interval: float = 0.08,
                   downscale_to: int = 480):
    """
    Đợi đến khi camera thấy khuôn mặt người dùng, tối đa `timeout` giây.

    Vì sao tồn tại:
      Sau khi user quẹt RFID, hệ thống thường chụp NGAY — user còn đang đưa
      tay xuống, chưa nhìn vào camera → backend Haar không thấy mặt → fail
      "Không phát hiện khuôn mặt". Kiosk retry burst nhưng burst chỉ cách
      nhau 50ms × 8 frame = 400ms, không đủ để user kịp ổn định.

      Hàm này detect face NGAY TẠI KIOSK (không gửi backend) trong vòng lặp
      poll mỗi 80ms, chỉ trả về khi local detector thấy mặt — coi như tín
      hiệu "user đã sẵn sàng". Sau đó mới gọi burst để chụp frame nét nhất.

    Trade-off:
      • Thêm tối đa 2 giây trễ trong trường hợp xấu nhất, nhưng cắt được
        hầu hết các lần retry "không phát hiện" nên trung bình nhanh hơn.
      • Detect local dùng ảnh downscale 480px + minSize=60 → ~5-15ms/frame
        trên Ryzen 7000, không gây lag UI.
    """
    if get_latest_frame is None:
        return None
    detector = _get_wait_detector()
    if detector is None or detector.empty():
        return None

    start = time.time()
    last_frame = None
    while time.time() - start < timeout:
        frame = get_latest_frame()
        if frame is None:
            time.sleep(poll_interval)
            continue
        last_frame = frame
        h, w = frame.shape[:2]
        if w > downscale_to:
            scale = downscale_to / w
            small = cv2.resize(
                frame, (downscale_to, int(h * scale)), interpolation=cv2.INTER_AREA
            )
        else:
            small = frame
        gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
        faces = detector.detectMultiScale(
            gray, scaleFactor=1.1, minNeighbors=4, minSize=(60, 60)
        )
        if len(faces) > 0:
            logger.debug(
                f"_wait_for_face: thấy mặt sau {(time.time() - start) * 1000:.0f}ms"
            )
            return frame
        time.sleep(poll_interval)

    logger.info(f"_wait_for_face: timeout {timeout}s — fall back chụp luôn")
    return last_frame


def _pick_sharpest_frame(get_latest_frame, n: int = BURST_FRAMES,
                         interval: float = BURST_INTERVAL,
                         seed_frame=None):
    """
    Burst capture: lấy `n` frame liên tiếp cách nhau `interval` giây, chọn frame
    có Laplacian variance cao nhất (nét nhất) để gửi lên backend.

    `seed_frame` = frame chụp ngay lúc trigger (không tốn thời gian chờ); nếu
    có thì được tính như frame đầu của burst, các frame sau đọc từ camera.

    Khi camera laptop chậm hoặc tay người dùng hơi run, frame "may mắn nét"
    có thể chỉ là 1 trong 3-5 frame liên tiếp — lấy ngẫu nhiên dễ rơi vào
    frame mờ → false-reject. Burst rồi pick max(variance) loại bỏ vấn đề này
    với chi phí ~150ms/shot.
    """
    candidates = []
    if seed_frame is not None:
        try:
            candidates.append((_laplacian_variance(seed_frame), seed_frame))
        except cv2.error:
            pass
        start_idx = 1
    else:
        start_idx = 0

    for _ in range(start_idx, n):
        time.sleep(interval)
        f = get_latest_frame() if get_latest_frame else None
        if f is None:
            continue
        try:
            candidates.append((_laplacian_variance(f), f))
        except cv2.error:
            continue

    if not candidates:
        return seed_frame
    best_var, best_frame = max(candidates, key=lambda x: x[0])
    logger.debug(
        f"Burst: chọn frame nét nhất (variance={best_var:.1f}) "
        f"trong {len(candidates)} ứng viên"
    )
    return best_frame


def process_rfid(uid: str, frame_bgr, get_latest_frame=None) -> display.ResultOverlay:
    """
    Quy trình đầy đủ: quẹt RFID + xác thực khuôn mặt nhiều lần.
      1. Tra cứu nhân viên theo UID thẻ RFID
      2. Xác thực khuôn mặt VERIFY_SHOTS lần (cách nhau VERIFY_SHOT_INTERVAL giây) —
         CẢ N lần chụp đều phải khớp thì mới ghi nhận chấm công.
         → Giảm mạnh false positive: kẻ qua mặt phải duy trì độ giống ≥ ngưỡng
           liên tục qua nhiều khung hình, không chỉ một frame may mắn.
      3. Nếu cả N lần đều khớp → ghi nhận chấm công vào / ra
    """
    logger.info(f"UID thẻ RFID: {uid}")
    emp_info = api_client.scan_rfid_card(uid)

    if emp_info is None:
        return display.ResultOverlay(
            message="Thẻ không hợp lệ",
            submessage=f"UID: {uid}  •  Liên hệ quản trị viên",
            success=False,
            show_until=time.time() + DISPLAY_RESULT_DURATION,
        )

    emp_name = emp_info.get("employee_name", "?")
    emp_id   = emp_info.get("employee_id")
    logger.info(f"Thẻ của: {emp_name} (id={emp_id})")

    # ── Đợi user vào khung hình trước khi chụp ──────────────────────────────
    # Sau khi quẹt thẻ, user thường còn đang đưa tay xuống → nếu chụp ngay,
    # backend Haar không thấy mặt → nhiều retry "Không phát hiện khuôn mặt".
    # Detect tại kiosk (cheap) và đợi tới khi thấy face, tối đa 2s rồi mới
    # bắt đầu burst. Frame trả về dùng làm seed thay cho `frame_bgr` ban đầu.
    ready_frame = _wait_for_face(get_latest_frame, timeout=2.0)
    if ready_frame is not None:
        frame_bgr = ready_frame

    # ── Xác thực khuôn mặt nhiều lần ────────────────────────────────────────
    sims: list[float] = []
    quality_errors: list[str] = []

    for shot_idx in range(VERIFY_SHOTS):
        # Mỗi shot là 1 burst BURST_FRAMES frame — chọn frame nét nhất gửi backend.
        # Lần đầu dùng frame chụp ngay lúc quẹt RFID làm seed (đỡ tốn 1 chu kỳ
        # interval), các lần sau chờ VERIFY_SHOT_INTERVAL rồi mới burst.
        if shot_idx == 0:
            seed = frame_bgr
        else:
            time.sleep(VERIFY_SHOT_INTERVAL)
            seed = get_latest_frame() if get_latest_frame else frame_bgr
            if seed is None:
                seed = frame_bgr

        # Inner retry CHỈ cho lỗi chất lượng (frame mờ/tối/quá nhỏ): burst lại
        # frame mới rồi gọi backend, tránh user phải quẹt thẻ lại chỉ vì 1
        # frame xấu. Các lỗi khác (no-face, no-match, network) vẫn fail-fast
        # vì retry không giải quyết được — cần user thao tác lại.
        verify = None
        for attempt in range(VERIFY_QUALITY_RETRIES + 1):
            if attempt > 0 and get_latest_frame:
                fresh = get_latest_frame()
                if fresh is not None:
                    seed = fresh

            shot_frame = _pick_sharpest_frame(get_latest_frame, seed_frame=seed) \
                if get_latest_frame else seed

            attempt_tag = f" (retry {attempt})" if attempt else ""
            logger.info(
                f"Lần chụp {shot_idx + 1}/{VERIFY_SHOTS} cho {emp_name}{attempt_tag}..."
            )
            verify = api_client.verify_face(emp_id, shot_frame)

            if verify is None:
                return display.ResultOverlay(
                    message="Lỗi kết nối máy chủ",
                    submessage=f"{emp_name}  •  Vui lòng thử lại",
                    success=False,
                    show_until=time.time() + DISPLAY_RESULT_DURATION,
                )

            # Quality fail = backend phát hiện được mặt nhưng từ chối embed
            # (mờ/tối/nhỏ) → vẫn còn cơ hội cứu với frame khác.
            is_quality_fail = (
                verify.get("has_face", False)
                and verify.get("error")
                and not verify.get("match", False)
            )
            if not is_quality_fail:
                break
            logger.info(
                f"  Retry {attempt + 1}/{VERIFY_QUALITY_RETRIES} "
                f"do quality fail: {verify.get('error', '')[:50]}"
            )

        has_face   = verify.get("has_face", False)
        face_match = verify.get("match", False)
        confidence = verify.get("confidence", 0.0)
        err        = verify.get("error")

        if not has_face:
            logger.warning(f"{emp_name} chưa đăng ký khuôn mặt")
            return display.ResultOverlay(
                message="Chưa đăng ký khuôn mặt",
                submessage=f"{emp_name}  •  Liên hệ quản trị viên để đăng ký",
                success=False,
                show_until=time.time() + DISPLAY_RESULT_DURATION,
            )

        # Lỗi chất lượng ảnh (mờ/tối/nhỏ/encoding cũ) → báo cụ thể, dừng ngay
        if err and not face_match:
            logger.warning(f"Lần chụp {shot_idx + 1} lỗi chất lượng: {err}")
            return display.ResultOverlay(
                message="Ảnh không đạt chất lượng",
                submessage=err[:60],
                success=False,
                show_until=time.time() + DISPLAY_RESULT_DURATION,
            )

        sims.append(confidence)
        logger.info(f"  độ giống={confidence:.4f}  khớp={face_match}")

        # Chỉ cần 1 lần chụp không khớp → từ chối ngay, không cần chụp tiếp
        if not face_match:
            avg_sim = sum(sims) / len(sims)
            logger.warning(
                f"Lần chụp {shot_idx + 1} KHÔNG khớp cho {emp_name} "
                f"(độ giống={confidence:.3f}, trung bình={avg_sim:.3f})"
            )
            return display.ResultOverlay(
                message="Xác thực khuôn mặt thất bại",
                submessage=f"{emp_name}  •  Độ khớp {confidence:.0%} (cần ≥ ngưỡng)",
                success=False,
                show_until=time.time() + DISPLAY_RESULT_DURATION,
            )

    avg_sim = sum(sims) / len(sims)
    logger.info(
        f"Cả {VERIFY_SHOTS} lần chụp đều khớp cho {emp_name} "
        f"(độ giống={[f'{s:.3f}' for s in sims]}, trung bình={avg_sim:.3f})"
    )

    # ── Ghi nhận chấm công ────────────────────────────────────────────────
    result = api_client.checkin_attendance(emp_id, method="rfid", rfid_uid=uid)

    if result is None:
        return display.ResultOverlay(
            message="Lỗi ghi nhận chấm công",
            submessage=f"{emp_name}  •  Liên hệ IT",
            success=False,
            show_until=time.time() + DISPLAY_RESULT_DURATION,
        )

    error = result.get("error")
    if error == "queued_offline":
        logger.warning(f"{emp_name} đã được lưu tạm trên kiosk, chờ đồng bộ online.")
        return display.ResultOverlay(
            message="Đã lưu tạm chấm công",
            submessage=f"{emp_name}  •  Sẽ tự động đồng bộ khi có mạng",
            success=True,
            show_until=time.time() + DISPLAY_RESULT_DURATION,
        )
    if error == "already_checked_out":
        logger.info(f"{emp_name} đã chấm công ra trước đó hôm nay.")
        return display.ResultOverlay(
            message="Đã chấm công xong hôm nay",
            submessage=f"{emp_name}  •  Đã có cả vào và ra",
            success=False,
            show_until=time.time() + DISPLAY_RESULT_DURATION,
        )
    if error == "employee_inactive":
        logger.warning(f"Tài khoản {emp_name} đã bị vô hiệu hóa.")
        return display.ResultOverlay(
            message="Tài khoản bị vô hiệu hóa",
            submessage=f"{emp_name}  •  Liên hệ quản trị viên",
            success=False,
            show_until=time.time() + DISPLAY_RESULT_DURATION,
        )

    action = result.get("action", "")
    log    = result.get("log", {})
    t_in   = log.get("check_in", "")
    t_out  = log.get("check_out")

    if action == "check_out" and t_out:
        main_msg = f"Tạm biệt, {emp_name}!"
        submsg   = f"Giờ ra: {_fmt_time(t_out)}"
    else:
        main_msg = f"Xin chào, {emp_name}!"
        submsg   = f"Giờ vào: {_fmt_time(t_in)}" if t_in else "Đã ghi nhận giờ vào"

    return display.ResultOverlay(
        message=main_msg,
        submessage=submsg,
        success=True,
        show_until=time.time() + DISPLAY_RESULT_DURATION,
    )


def process_register(employee_id: int, frame_bgr,
                     get_latest_frame=None) -> display.ResultOverlay:
    """
    Đăng ký khuôn mặt trực tiếp tại kiosk qua camera (bấm phím R).

    Multi-pose enrollment: chụp ENROLL_POSES ảnh cách nhau ENROLL_POSE_INTERVAL
    giây, mỗi ảnh là 1 burst → chọn frame nét nhất. Người đăng ký nên xoay nhẹ
    đầu giữa các lần chụp để gallery có nhiều góc nhìn ngay từ đầu.
    """
    logger.info(
        f"Đăng ký khuôn mặt cho NV id={employee_id} "
        f"(multi-pose: {ENROLL_POSES} ảnh)..."
    )

    # Ảnh đầu = frame ngay lúc bấm Enter; các ảnh sau lấy sau interval
    primary_frame = _pick_sharpest_frame(get_latest_frame, seed_frame=frame_bgr) \
        if get_latest_frame else frame_bgr

    extra_frames = []
    if get_latest_frame and ENROLL_POSES > 1:
        for pose_idx in range(1, ENROLL_POSES):
            time.sleep(ENROLL_POSE_INTERVAL)
            seed = get_latest_frame()
            if seed is None:
                continue
            best = _pick_sharpest_frame(get_latest_frame, seed_frame=seed)
            if best is not None:
                extra_frames.append(best)
                logger.info(f"  Đã chụp pose {pose_idx + 1}/{ENROLL_POSES}")

    result = api_client.register_face_from_kiosk(
        employee_id, primary_frame, extra_frames=extra_frames or None
    )

    if result is None:
        return display.ResultOverlay(
            message="Đăng ký thất bại",
            submessage=f"NV #{employee_id}  •  Kiểm tra ID hoặc kết nối mạng",
            success=False,
            show_until=time.time() + DISPLAY_RESULT_DURATION,
        )

    emp_name = result.get("employee_name", f"NV #{employee_id}")
    extras_added = result.get("extras_added", 0)
    extras_failed = result.get("extras_failed", 0)

    submsg = f"{emp_name}  •  1 chính"
    if extras_added:
        submsg += f" + {extras_added} phụ"
    if extras_failed:
        submsg += f"  ({extras_failed} ảnh phụ kém)"

    return display.ResultOverlay(
        message="Đăng ký thành công!",
        submessage=submsg,
        success=True,
        show_until=time.time() + DISPLAY_RESULT_DURATION,
    )


# ---------------------------------------------------------------------------
# Hàm phụ trợ vẽ giao diện — gọi sang display.py để có giao diện hiện đại
# ---------------------------------------------------------------------------

def _draw_processing_badge(frame):
    display.draw_processing_badge(frame)


def _draw_register_mode(frame, emp_id_buf: str):
    display.draw_register_mode(frame, emp_id_buf)


def _draw_idle_rfid_prompt(frame):
    display.draw_idle_prompt(frame)


# ---------------------------------------------------------------------------
# Vòng lặp chính
# ---------------------------------------------------------------------------

def main():
    api_client.start_outbox_sync_worker()

    src = CAMERA_INDEX
    is_url = isinstance(src, str)

    if is_url:
        logger.info(f"Mở camera: URL {src}")
        cap = cv2.VideoCapture(src)
    else:
        backend_flag = _BACKEND_MAP.get(CAMERA_BACKEND.lower(), cv2.CAP_ANY)
        logger.info(f"Mở camera: index {src}  •  backend={CAMERA_BACKEND.upper()}")
        cap = cv2.VideoCapture(src, backend_flag)

    # Buffer 1 frame: cv2.VideoCapture mặc định đệm vài frame, gây trễ vài
    # trăm ms khi camera đẩy nhanh hơn vòng lặp xử lý — luôn đọc frame "cũ"
    # thay vì frame mới nhất.
    try:
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    except cv2.error:
        pass

    if not cap.isOpened():
        if is_url:
            logger.error(
                f"Không mở được camera từ URL: {src}\n"
                "  - Kiểm tra URL có truy cập được từ trình duyệt không.\n"
                "  - URL phải có đường dẫn stream (vd: http://192.168.1.5:8080/video)."
            )
        else:
            logger.error(
                f"Không mở được camera (index={src}, backend={CAMERA_BACKEND}).\n"
                "  - Webcam laptop có đang được app khác sử dụng không (Zoom, Teams)?\n"
                "  - Quyền truy cập camera đã bật trong Windows Settings chưa?\n"
                "  - Chạy `python list_cameras.py` để xem các camera khả dụng.\n"
                "  - Thử đổi CAMERA_BACKEND giữa 'msmf'/'dshow' trong config.py."
            )
        sys.exit(1)

    # Camera index: ép codec/độ phân giải/FPS.
    # Camera qua URL: server tự quyết định, set không tác dụng.
    if not is_url:
        # Set FOURCC trước width/height nếu có chỉ định codec — một số webcam
        # USB ngoài chỉ cho phép độ phân giải cao khi đang ở chế độ MJPG.
        if CAMERA_FOURCC:
            fourcc = cv2.VideoWriter_fourcc(*CAMERA_FOURCC)
            cap.set(cv2.CAP_PROP_FOURCC, fourcc)
        cap.set(cv2.CAP_PROP_FRAME_WIDTH,  FRAME_WIDTH)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, FRAME_HEIGHT)
        cap.set(cv2.CAP_PROP_FPS, FRAME_FPS)
    actual_w   = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    actual_h   = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    actual_fps = cap.get(cv2.CAP_PROP_FPS) or 0.0
    logger.info(
        f"Camera sẵn sàng: {actual_w}x{actual_h} @ {actual_fps:.1f}fps "
        f"(yêu cầu {FRAME_WIDTH}x{FRAME_HEIGHT} @ {FRAME_FPS}fps, codec={CAMERA_FOURCC or 'auto'})"
    )

    detector = load_face_detector()

    # WINDOW_KEEPRATIO: khi kéo cửa sổ, OpenCV thêm letterbox đen hai bên
    # thay vì stretch ảnh → khuôn mặt không bị méo dù tỉ lệ cửa sổ khác tỉ
    # lệ frame gốc.
    cv2.namedWindow(WINDOW_TITLE, cv2.WINDOW_NORMAL | cv2.WINDOW_KEEPRATIO)
    # Kích thước mặc định theo hướng frame sau khi xoay: dọc dùng 9:16,
    # ngang (mặc định, không xoay) dùng 16:9 — vừa laptop 1080p.
    if CAMERA_ROTATE in (90, 270):
        cv2.resizeWindow(WINDOW_TITLE, 540, 960)   # dọc
    else:
        cv2.resizeWindow(WINDOW_TITLE, 1600, 900)  # ngang

    # --- Trạng thái ---
    current_overlay: display.ResultOverlay | None = None
    is_processing   = False
    overlay_lock    = threading.Lock()

    # Frame mới nhất dùng chung — vòng lặp chính cập nhật, luồng xác thực multi-shot đọc.
    latest_frame_lock = threading.Lock()
    latest_frame: np.ndarray | None = None

    rfid_buffer         = ""
    rfid_last_char_time = 0.0

    register_mode   = False
    register_id_buf = ""

    def set_overlay(result: display.ResultOverlay):
        nonlocal current_overlay, is_processing
        with overlay_lock:
            current_overlay = result
            is_processing   = False

    def get_latest_frame():
        with latest_frame_lock:
            return None if latest_frame is None else latest_frame.copy()

    def launch(fn, *args):
        nonlocal is_processing
        with overlay_lock:
            is_processing = True
        # Cả process_rfid (multi-shot verify) và process_register (multi-pose
        # enrollment) đều cần get_latest_frame để burst capture qua nhiều
        # khung hình liên tiếp.
        full_args = (*args, get_latest_frame)
        threading.Thread(target=lambda: set_overlay(fn(*full_args)),
                         daemon=True).start()

    logger.info("Kiosk đã khởi động.  Q/ESC=thoát | R=đăng ký mặt | quẹt thẻ RFID=điểm danh")

    quit_flag = False

    while not quit_flag:
        ret, frame = cap.read()
        if not ret:
            time.sleep(0.05)
            continue

        # Xoay frame ngay sau khi đọc — mọi xử lý downstream (detect, burst,
        # gửi backend, hiển thị) đều thấy frame đã ở đúng chiều, không cần
        # quan tâm camera gốc nằm ngang/dọc.
        rotate_code = _ROTATE_MAP.get(CAMERA_ROTATE)
        if rotate_code is not None:
            frame = cv2.rotate(frame, rotate_code)

        # Cập nhật latest_frame để luồng xác thực có thể đọc lần chụp mới sau interval
        with latest_frame_lock:
            latest_frame = frame.copy()

        now = time.time()

        # Downscale rồi mới convert xám: detect trên ảnh nhỏ tốn ~1/(scale^2)
        # CPU. Frame gốc vẫn được giữ nguyên cho việc gửi backend & hiển thị.
        frame_h_full, frame_w_full = frame.shape[:2]
        if DETECT_WIDTH and frame_w_full > DETECT_WIDTH:
            detect_scale = frame_w_full / DETECT_WIDTH
            new_h = int(frame_h_full / detect_scale)
            small = cv2.resize(frame, (DETECT_WIDTH, new_h),
                               interpolation=cv2.INTER_AREA)
            gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
        else:
            detect_scale = 1.0
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

        # ── Lấy hết phím OpenCV trong hàng đợi (cả phím từ RFID lẫn phím thường) ──
        while True:
            k = cv2.pollKey()
            if k == -1:
                break
            k &= 0xFF

            # --- Chế độ đăng ký khuôn mặt ---
            if register_mode:
                if k == 27:
                    register_mode   = False
                    register_id_buf = ""
                elif k == 13:
                    if register_id_buf.isdigit() and register_id_buf:
                        emp_id = int(register_id_buf)
                        snap   = frame.copy()
                        register_mode   = False
                        register_id_buf = ""
                        launch(process_register, emp_id, snap)
                    else:
                        register_mode   = False
                        register_id_buf = ""
                elif k == 8:
                    register_id_buf = register_id_buf[:-1]
                elif ord('0') <= k <= ord('9'):
                    register_id_buf += chr(k)
                continue

            # --- Phím điều khiển chính ---
            if k in (ord('q'), ord('Q'), 27):
                quit_flag = True
                break

            if k == ord('r') or k == ord('R'):
                register_mode   = True
                register_id_buf = ""
                continue

            # --- Tích lũy ký tự từ đầu đọc RFID (chỉ ASCII in được) ---
            if RFID_ENABLED and 32 <= k <= 126:
                rfid_buffer         += chr(k)
                rfid_last_char_time  = now
                continue

            # --- Đầu đọc RFID gửi Enter để kết thúc UID ---
            if RFID_ENABLED and k == 13 and rfid_buffer.strip():
                uid         = rfid_buffer.strip()
                rfid_buffer = ""
                with overlay_lock:
                    ready = not is_processing and (
                        current_overlay is None or not current_overlay.is_active())
                if ready:
                    snap = frame.copy()
                    launch(process_rfid, uid, snap)

        if quit_flag:
            break

        # ── Tự động gửi UID khi đầu đọc im lặng (không cần Enter) ─────────────
        if (RFID_ENABLED
                and rfid_buffer.strip()
                and now - rfid_last_char_time >= RFID_AUTO_SUBMIT_TIMEOUT):
            uid         = rfid_buffer.strip()
            rfid_buffer = ""
            with overlay_lock:
                ready = not is_processing and (
                    current_overlay is None or not current_overlay.is_active())
            if ready:
                snap = frame.copy()
                launch(process_rfid, uid, snap)

        # ── Phát hiện khuôn mặt (chỉ để hiển thị khung, không xác thực) ──────
        faces = detect_faces(gray, detector, scale=detect_scale)

        # ── Phóng frame lên DISPLAY_SCALE trước khi vẽ overlay ────────────────
        # Lý do: cv2.imshow chỉ scale bằng bilinear → fullscreen mờ. Nếu ta
        # upscale frame lên 1.5x với LANCZOS4 trước khi vẽ, thì:
        #   • Camera image sắc hơn bilinear của driver
        #   • Quan trọng hơn — TEXT + FACE BOX được Pillow vẽ Ở ĐỘ PHÂN GIẢI
        #     CAO (1920×1080 thay vì 1280×720) → sắc nét rõ khi fullscreen
        # Face bbox cũng scale theo để vẽ đúng vị trí.
        if DISPLAY_SCALE != 1.0:
            new_w = int(frame.shape[1] * DISPLAY_SCALE)
            new_h = int(frame.shape[0] * DISPLAY_SCALE)
            display_frame = cv2.resize(
                frame, (new_w, new_h), interpolation=cv2.INTER_LANCZOS4
            )
            faces_disp = [
                (int(x * DISPLAY_SCALE), int(y * DISPLAY_SCALE),
                 int(w * DISPLAY_SCALE), int(h * DISPLAY_SCALE))
                for (x, y, w, h) in faces
            ]
        else:
            display_frame = frame
            faces_disp = faces

        # ── Vẽ giao diện ──────────────────────────────────────────────────────
        display.draw_header(display_frame)

        with overlay_lock:
            overlay_snap = current_overlay
            processing   = is_processing

        # Khung quanh khuôn mặt phát hiện được
        for (x, y, w, h) in faces_disp:
            if overlay_snap and overlay_snap.is_active():
                box_color = display.GREEN if overlay_snap.success else display.RED_BGR
            else:
                box_color = display.GREEN
            display.draw_face_box(display_frame, x, y, w, h, box_color)

        # Overlay chế độ đăng ký
        if register_mode:
            _draw_register_mode(display_frame, register_id_buf)
        elif overlay_snap and overlay_snap.is_active():
            display.draw_result_overlay(display_frame, overlay_snap)
        else:
            _draw_idle_rfid_prompt(display_frame)

        if processing and not register_mode:
            _draw_processing_badge(display_frame)

        cv2.imshow(WINDOW_TITLE, display_frame)

    cap.release()
    api_client.stop_outbox_sync_worker()
    cv2.destroyAllWindows()
    logger.info("Kiosk đã tắt.")


if __name__ == "__main__":
    main()
