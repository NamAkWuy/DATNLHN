"""
Dịch vụ nhận diện khuôn mặt.
Dùng DeepFace nếu có, ngược lại fall back sang embedding giả lập để test.
"""
import logging
import os
import shutil
import tempfile
import numpy as np

logger = logging.getLogger(__name__)


_HAAR_CASCADE = None


def _get_haar_cascade():
    """
    Trả về cv2.CascadeClassifier đã load (cache global).
    Trên Windows, cv2 KHÔNG đọc được path chứa ký tự non-ASCII (vd: "Đ" trong "ĐATNLHN")
    → cascade rỗng → mọi ảnh bị từ chối nhầm. Workaround: copy file cascade ra %TEMP%
    (path ASCII) rồi load từ đó.
    """
    global _HAAR_CASCADE
    if _HAAR_CASCADE is not None:
        return _HAAR_CASCADE

    import cv2  # type: ignore
    src = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
    path_to_load = src

    # Nếu path có ký tự non-ASCII → copy sang TEMP (ASCII) một lần
    if not src.isascii():
        try:
            dst = os.path.join(tempfile.gettempdir(), "haar_face_default.xml")
            if (not os.path.exists(dst)) or os.path.getsize(dst) != os.path.getsize(src):
                shutil.copyfile(src, dst)
            path_to_load = dst
            logger.info(f"Đã copy Haar cascade ra path ASCII: {dst}")
        except Exception as e:
            logger.error(f"Không copy được Haar cascade ra TEMP: {e}")

    cascade = cv2.CascadeClassifier(path_to_load)
    if cascade.empty():
        logger.error(f"Không load được Haar cascade từ: {path_to_load}")
        return None

    _HAAR_CASCADE = cascade
    return cascade

# Thử import DeepFace - nếu không có / không có GPU thì fall back nhẹ nhàng
DEEPFACE_AVAILABLE = False
try:
    from deepface import DeepFace  # type: ignore
    DEEPFACE_AVAILABLE = True
    logger.info("Đã tải DeepFace thành công.")
except Exception as _df_exc:
    logger.warning(
        "Không có DeepFace hoặc tải thất bại (%s: %s). "
        "Sẽ dùng embedding khuôn mặt giả lập để demo.",
        type(_df_exc).__name__, _df_exc,
        exc_info=True,
    )


def _decode_image_bytes(image_bytes: bytes):
    """Giải mã bytes thô thành mảng numpy (BGR) bằng OpenCV."""
    import cv2  # type: ignore
    nparr = np.frombuffer(image_bytes, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    return img


# Ngưỡng đã nới mạnh sau khi (1) pipeline có thêm _enhance_face_region (CLAHE
# + unsharp mask) tự cứu được ảnh thiếu sáng/mờ nhẹ, và (2) kiosk pre-crop
# face trước khi upload nên backend luôn nhận frame mà face dominate. Quality
# gate hiện chỉ chặn các trường hợp cực đoan (ảnh đen, mặt rất nhỏ, mờ nặng).
# Nới gates → giảm mạnh false-reject ở tình huống điểm danh thực tế (đứng hơi
# xa, đèn không lý tưởng), false-accept không tăng vì còn 2 lớp bảo vệ phía
# sau (MTCNN align + cosine threshold).
_MIN_FACE_AREA_RATIO = 0.008  # khuôn mặt >= 0.8% diện tích ảnh (nới từ 2%)
_MIN_FACE_SIZE_PX    = 35     # cạnh ngắn nhất bbox >= 35px (nới từ 50px)
_MIN_BLUR_VAR        = 8.0    # variance Laplacian — chỉ reject ảnh mờ rất nặng (nới từ 15)
_MIN_BRIGHTNESS      = 15     # gần như đen mới reject (nới từ 20, CLAHE sẽ kéo lên sau)
_MAX_BRIGHTNESS      = 245    # gần trắng hoàn toàn — quá cháy sáng, không cứu được

# Ngưỡng để QUYẾT ĐỊNH có cần enhance hay không. Trên các ngưỡng này, ảnh đã
# đủ tốt cho ArcFace — CLAHE/unsharp chỉ thêm variance không cần thiết và làm
# embedding kém ổn định giữa các frame của cùng một người.
_ENHANCE_BRIGHTNESS_THRESHOLD = 70   # mean grayscale của face crop
_ENHANCE_BLUR_THRESHOLD       = 40   # Laplacian variance của face crop

# Padding quanh bbox Haar khi cắt vùng face để gửi MTCNN. Kiosk đã pre-crop
# với pad 60% (api_client._crop_face_for_upload) → backend không cần pad to
# nữa. Pad nhỏ → MTCNN crop về 112×112 chứa ít pixel nền/áo → ArcFace embedding
# bám sát đặc trưng KHUÔN MẶT, không bị bối cảnh kéo lệch khi user đổi áo /
# đổi background / vuốt tóc làm thay đổi vùng quanh mặt.
_FACE_CROP_PADDING_RATIO = 0.20


def _quality_check(face_crop_gray) -> str | None:
    """
    Trả về None nếu khuôn mặt đủ chất lượng để embed,
    hoặc thông báo lỗi tiếng Việt nếu cần reject.

    Lý do: embedding của ảnh mờ/tối/cháy sáng/quá nhỏ rất ít entropy
    → cosine similarity với ngẫu nhiên đều cao 0.5–0.7 → false positive.
    Loại bỏ ở cửa vào sẽ chính xác hơn nhiều so với chỉnh threshold.
    """
    import cv2  # type: ignore
    h, w = face_crop_gray.shape[:2]
    if min(h, w) < _MIN_FACE_SIZE_PX:
        return (
            f"Khuôn mặt quá nhỏ ({w}×{h}px). "
            "Hãy đứng gần camera hơn (cách ~50–80cm)."
        )

    blur_var = cv2.Laplacian(face_crop_gray, cv2.CV_64F).var()
    if blur_var < _MIN_BLUR_VAR:
        return (
            f"Ảnh quá mờ (Laplacian variance = {blur_var:.1f}, cần ≥ {_MIN_BLUR_VAR:.0f}). "
            "Hãy giữ yên, không lắc camera."
        )

    brightness = float(face_crop_gray.mean())
    if brightness < _MIN_BRIGHTNESS:
        return f"Ảnh quá tối (độ sáng {brightness:.0f}/255). Hãy bật thêm đèn."
    if brightness > _MAX_BRIGHTNESS:
        return f"Ảnh quá sáng (độ sáng {brightness:.0f}/255). Tránh ngược sáng / nắng gắt."

    return None


def _enhance_face_region(face_bgr: np.ndarray) -> np.ndarray:
    """
    Cải thiện chất lượng vùng khuôn mặt trước khi đưa vào ArcFace.

    Pipeline:
      1. CLAHE trên kênh Y của không gian YUV (luminance) — cân bằng tương phản
         cục bộ mà KHÔNG làm lệch màu da (nếu CLAHE trên cả RGB sẽ ám màu).
         Cứu được ảnh thiếu sáng đều, đèn không đều, ngược sáng nhẹ.
      2. Unsharp mask nhẹ (sigma=1.0, weight 1.5/-0.5) — bù độ nét bị mất do
         auto-focus chưa kịp / webcam laptop chất lượng kém. Sigma nhỏ chỉ làm
         nét cạnh, không khuếch đại noise tổng thể.

    Embedding ArcFace của ảnh enhanced vẫn cosine ~0.92–0.97 với embedding ảnh
    gốc (cùng identity cluster), nhưng ổn định hơn nhiều giữa các điều kiện
    sáng/nét khác nhau → giảm đáng kể false-reject trên webcam laptop, bỏ được
    yêu cầu phải gắn camera điện thoại ngoài.
    """
    import cv2  # type: ignore
    if face_bgr is None or face_bgr.size == 0:
        return face_bgr

    yuv = cv2.cvtColor(face_bgr, cv2.COLOR_BGR2YUV)
    clahe = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8))
    yuv[:, :, 0] = clahe.apply(yuv[:, :, 0])
    enhanced = cv2.cvtColor(yuv, cv2.COLOR_YUV2BGR)

    blurred = cv2.GaussianBlur(enhanced, (0, 0), sigmaX=1.0)
    sharpened = cv2.addWeighted(enhanced, 1.5, blurred, -0.5, 0)
    return sharpened


def detect_face_bbox(image_bytes: bytes):
    """
    Dùng OpenCV Haar cascade phát hiện khuôn mặt, có CLAHE để cải thiện
    độ tương phản trên webcam laptop chất lượng kém (thiếu sáng / mờ).

    Trả về bbox (x, y, w, h) của khuôn mặt LỚN NHẤT, hoặc None.
    Cân bằng:
      - Tham số Haar đủ lỏng để bắt được mặt thật trên ảnh 320×240 / 480×360.
      - Kiểm tra diện tích bbox >= _MIN_FACE_AREA_RATIO ảnh để chặn false-positive
        (cascade Haar đôi khi nhận nhầm cụm pixel nhỏ là khuôn mặt).
    """
    import cv2  # type: ignore
    img = _decode_image_bytes(image_bytes)
    if img is None:
        return None
    h_img, w_img = img.shape[:2]
    img_area = h_img * w_img

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    # CLAHE: cân bằng sáng cục bộ — giúp webcam thiếu sáng dễ detect hơn equalizeHist toàn cục
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    gray = clahe.apply(gray)

    cascade = _get_haar_cascade()
    if cascade is None:
        logger.warning("Không tải được Haar cascade — từ chối ảnh.")
        return None

    faces = cascade.detectMultiScale(
        gray, scaleFactor=1.1, minNeighbors=4, minSize=(40, 40)
    )
    if len(faces) == 0:
        return None

    # Lọc theo diện tích để tránh chấp nhận vật nhỏ bị nhận nhầm
    valid = [f for f in faces if (f[2] * f[3]) >= _MIN_FACE_AREA_RATIO * img_area]
    if not valid:
        return None
    return tuple(int(v) for v in max(valid, key=lambda f: f[2] * f[3]))


def detect_face_in_image(image_bytes: bytes) -> bool:
    """Bool wrapper — True nếu phát hiện được khuôn mặt rõ ràng."""
    return detect_face_bbox(image_bytes) is not None


def _mock_embedding_from_face(img_bgr, bbox) -> list[float]:
    """
    Embedding "giả" cho mock mode (khi DeepFace chưa cài).
    Crop khuôn mặt → grayscale → equalize histogram → resize 16x8 → zero-mean L2-normalize.
    Embedding 128-D này tương đối ổn định cho cùng một người dưới điều kiện ánh sáng/góc tương tự,
    đủ để demo nghiệp vụ. Production NÊN dùng DeepFace.
    """
    import cv2  # type: ignore
    x, y, w, h = bbox
    face = img_bgr[y:y + h, x:x + w]
    if face.size == 0:
        raise ValueError("Vùng khuôn mặt rỗng.")
    gray = cv2.cvtColor(face, cv2.COLOR_BGR2GRAY)
    eq = cv2.equalizeHist(gray)
    small = cv2.resize(eq, (16, 8), interpolation=cv2.INTER_AREA)
    arr = small.astype(np.float64).flatten()
    arr = arr - arr.mean()
    norm = float(np.linalg.norm(arr))
    if norm > 0:
        arr = arr / norm
    return arr.tolist()


def mock_encoding_for_employee(employee_id: int) -> list[float]:
    """Deterministic 128-D unit vector for service tests and mock fixtures."""
    rng = np.random.default_rng(int(employee_id))
    arr = rng.normal(size=128).astype(np.float64)
    norm = float(np.linalg.norm(arr))
    if norm == 0.0:
        return [0.0] * 128
    return (arr / norm).tolist()


def extract_face_encoding(image_bytes: bytes) -> list[float]:
    """Thin wrapper trả về encoding list — dùng cho register/test/back-compat.

    Verify endpoint nên gọi `extract_face_with_meta_from_base64` để lấy thêm
    quality metrics (brightness, blur_var) phục vụ adaptive-learning 2-tier.
    """
    return _extract_face_full(image_bytes)["encoding"]


def _extract_face_full(image_bytes: bytes) -> dict:
    """
    Pipeline đầy đủ: detect → quality check → enhance → ArcFace embedding.

    Trả về dict gồm:
      - encoding:    list[float], 512-D nếu DeepFace có, 128-D nếu mock
      - brightness:  mean grayscale của vùng mặt chặt (15–245 sau quality gate)
      - blur_var:    Laplacian variance — proxy độ nét
      - face_size_px: cạnh ngắn nhất bbox Haar — proxy khoảng cách camera

    Quality metrics dùng để:
      • quyết định có cần enhance hay không (đã có)
      • quyết định adapt tier (mới — verify endpoint phân loại frame "easy" /
        "hard" / "reject" để biết có nên học vào gallery hay không)
    """
    import cv2  # type: ignore
    bbox = detect_face_bbox(image_bytes)
    if bbox is None:
        raise ValueError(
            "Không phát hiện khuôn mặt trong ảnh. "
            "Hãy nhìn thẳng vào camera, đảm bảo đủ ánh sáng và khuôn mặt nằm trong khung hình."
        )

    img_array = _decode_image_bytes(image_bytes)
    if img_array is None:
        raise ValueError("Không giải mã được ảnh.")

    # ── Kiểm tra chất lượng ảnh ─────────────────────────────────────────────
    # Chạy trước khi embed: tiết kiệm thời gian + tránh tạo embedding rác.
    x, y, w, h = bbox
    face_only = img_array[y:y + h, x:x + w]
    face_gray = cv2.cvtColor(face_only, cv2.COLOR_BGR2GRAY) if face_only.size else None
    if face_gray is None or face_gray.size == 0:
        raise ValueError("Vùng khuôn mặt rỗng.")
    quality_err = _quality_check(face_gray)
    if quality_err:
        raise ValueError(quality_err)

    # Tính brightness/blur một lần duy nhất, dùng chung cho enhance decision
    # và adapt-tier decision phía verify endpoint.
    brightness = float(face_gray.mean())
    blur_var = float(cv2.Laplacian(face_gray, cv2.CV_64F).var())
    face_size_px = int(min(h, w))

    if DEEPFACE_AVAILABLE:
        # ── Enhance có điều kiện, chỉ trên vùng MẶT (không gồm padding) ─────
        # Vì sao:
        #   1. Nếu ảnh đã đủ sáng/nét → SKIP CLAHE+unsharp. Áp dụng enhance
        #      lên frame chất lượng tốt chỉ thêm variance giữa các lần verify
        #      (mỗi frame có nhiễu khác nhau → LUT khác nhau → embedding lệch
        #      nhẹ). Demo conditions thường rơi vào nhánh skip này → embedding
        #      ổn định, cosine match cao.
        #   2. Nếu cần enhance (ảnh tối/mờ thật) → áp dụng CHỈ trên crop chặt
        #      face_only (không bao padding). Trước đây CLAHE chạy trên crop
        #      đã pad 50% (gồm cả background + áo) → tile histogram bị driven
        #      bởi pixel ngoài khuôn mặt → LUT của tile mặt phụ thuộc vào bối
        #      cảnh → user đổi áo/background → cùng khuôn mặt cho ra embedding
        #      khác. Apply CLAHE trên tight face thì LUT chỉ học từ pixel da
        #      khuôn mặt, hoàn toàn bất biến với mọi thay đổi bên ngoài.
        needs_enhance = (
            brightness < _ENHANCE_BRIGHTNESS_THRESHOLD
            or blur_var < _ENHANCE_BLUR_THRESHOLD
        )
        face_tight = _enhance_face_region(face_only) if needs_enhance else face_only

        # Padding nhỏ (20%) — kiosk đã pre-crop pad 60% rồi nên backend không
        # cần pad to nữa. Pad nhỏ → MTCNN crop tới 112x112 chứa nhiều pixel
        # mặt hơn, ít pixel nền/áo hơn → ArcFace embedding tập trung vào đặc
        # trưng khuôn mặt thật (mắt, mũi, miệng, cấu trúc xương), giảm tối đa
        # ảnh hưởng của bối cảnh.
        pad = int(_FACE_CROP_PADDING_RATIO * max(w, h))
        x1 = max(0, x - pad)
        y1 = max(0, y - pad)
        x2 = min(img_array.shape[1], x + w + pad)
        y2 = min(img_array.shape[0], y + h + pad)
        if needs_enhance:
            # Ghép vùng mặt đã enhance vào đúng vị trí trong crop có padding.
            # Pixel padding xung quanh là pixel gốc — MTCNN dùng để tìm
            # landmarks; pixel mặt là đã được enhance để bù sáng/nét.
            face_crop = img_array[y1:y2, x1:x2].copy()
            fx, fy = x - x1, y - y1
            face_crop[fy:fy + h, fx:fx + w] = face_tight
        else:
            face_crop = img_array[y1:y2, x1:x2]
        if face_crop.size == 0:
            raise ValueError("Vùng khuôn mặt rỗng sau khi crop.")

        try:
            # MTCNN tự detect lại + align mặt theo landmark (mắt, mũi, miệng).
            # Sau khi align, embedding ArcFace mã hóa IDENTITY thật của khuôn mặt
            # (mắt to/nhỏ, mũi cao/thấp...), không bị ảnh hưởng góc nghiêng nữa.
            results = DeepFace.represent(
                img_path=face_crop,
                model_name="ArcFace",
                enforce_detection=True,    # bắt buộc detect — fail-fast nếu không có mặt
                detector_backend="mtcnn",
                align=True,
                normalization="ArcFace",
            )
            if not results:
                raise ValueError("ArcFace không tạo được embedding.")
            emb = np.array(results[0]["embedding"], dtype=np.float64)

            # L2-normalize → cosine sim = dot product, threshold dễ điều chỉnh.
            norm = float(np.linalg.norm(emb))
            if norm == 0.0:
                raise ValueError("Embedding rỗng.")
            emb = emb / norm
            return {
                "encoding": emb.tolist(),
                "brightness": brightness,
                "blur_var": blur_var,
                "face_size_px": face_size_px,
            }
        except ValueError:
            raise
        except Exception as e:
            # MTCNN có thể fail nếu khuôn mặt quá nghiêng / thiếu sáng quá mạnh.
            # Fallback sang opencv detector của DeepFace để vẫn có cơ hội nhận diện.
            logger.warning(f"MTCNN/ArcFace lỗi, dùng detector opencv thay thế: {e}")
            try:
                # face_crop đã chứa face_tight (raw hoặc đã enhance tùy needs_enhance)
                # ở đúng vị trí — không cần xử lý gì thêm.
                results = DeepFace.represent(
                    img_path=face_crop,
                    model_name="ArcFace",
                    enforce_detection=False,
                    detector_backend="opencv",
                    align=True,
                    normalization="ArcFace",
                )
                if not results:
                    raise ValueError("ArcFace fallback không tạo được embedding.")
                emb = np.array(results[0]["embedding"], dtype=np.float64)
                norm = float(np.linalg.norm(emb))
                if norm == 0.0:
                    raise ValueError("Embedding rỗng.")
                emb = emb / norm
                return {
                    "encoding": emb.tolist(),
                    "brightness": brightness,
                    "blur_var": blur_var,
                    "face_size_px": face_size_px,
                }
            except Exception as e2:
                logger.error(f"Trích xuất ArcFace thất bại (cả 2 detector): {e2}")
                raise ValueError(
                    "Trích xuất khuôn mặt thất bại. Hãy nhìn thẳng vào camera, "
                    "ánh sáng đầy đủ, không đeo khẩu trang/kính râm."
                )

    return {
        "encoding": _mock_embedding_from_face(img_array, bbox),
        "brightness": brightness,
        "blur_var": blur_var,
        "face_size_px": face_size_px,
    }


def _b64_to_bytes(image_base64: str) -> bytes:
    """Giải mã base64 (có/không có data URI prefix) sang bytes ảnh thô."""
    import base64
    if "," in image_base64:
        image_base64 = image_base64.split(",", 1)[1]
    return base64.b64decode(image_base64)


def extract_face_encoding_from_base64(image_base64: str) -> list[float]:
    """Backward-compat: trả encoding list. Verify endpoint dùng `_with_meta` ở dưới."""
    return extract_face_encoding(_b64_to_bytes(image_base64))


def extract_face_with_meta_from_base64(image_base64: str) -> dict:
    """
    Trả về dict {encoding, brightness, blur_var, face_size_px}.

    Verify endpoint dùng hàm này (thay vì `extract_face_encoding_from_base64`)
    để có đủ thông tin chất lượng frame phục vụ quyết định adaptive learning
    2-tier — xem `_decide_adapt_tier` trong [app/api/face.py].
    """
    return _extract_face_full(_b64_to_bytes(image_base64))


def cosine_similarity(vec1: list[float], vec2: list[float]) -> float:
    """Tính độ tương đồng cosine giữa 2 vector."""
    a = np.array(vec1, dtype=np.float64)
    b = np.array(vec2, dtype=np.float64)
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(np.dot(a, b) / (norm_a * norm_b))


def compare_faces(
    encoding1: list[float],
    encoding2: list[float],
    threshold: float = 0.4,
) -> tuple[bool, float]:
    """
    So sánh 2 vector đặc trưng khuôn mặt.

    Trả về:
        (khớp: bool, độ_tin_cậy: float)
        độ tin cậy là điểm cosine similarity trong [-1, 1]; càng cao càng giống.
    """
    similarity = cosine_similarity(encoding1, encoding2)
    is_match = similarity >= threshold
    return is_match, similarity

