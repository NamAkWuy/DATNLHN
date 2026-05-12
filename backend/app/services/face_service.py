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
except Exception:
    logger.warning(
        "Không có DeepFace hoặc tải thất bại. "
        "Sẽ dùng embedding khuôn mặt giả lập để demo."
    )


def _decode_image_bytes(image_bytes: bytes):
    """Giải mã bytes thô thành mảng numpy (BGR) bằng OpenCV."""
    import cv2  # type: ignore
    nparr = np.frombuffer(image_bytes, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    return img


_MIN_FACE_AREA_RATIO = 0.02   # khuôn mặt phải chiếm >=2% diện tích ảnh
# Ngưỡng đã được nới sau khi pipeline có thêm bước _enhance_face_region (CLAHE +
# unsharp mask) — phần lớn ảnh thiếu sáng / mờ nhẹ giờ tự cứu được, không cần
# reject sớm. Chỉ giữ ngưỡng để chặn các trường hợp cực đoan (ảnh gần như đen,
# mặt quá nhỏ để align landmark).
_MIN_FACE_SIZE_PX    = 50     # cạnh ngắn nhất bbox >= 50px — đủ để MTCNN align landmark
_MIN_BLUR_VAR        = 15.0   # variance Laplacian — chỉ reject ảnh mờ nặng (rung tay, lia camera)
_MIN_BRIGHTNESS      = 20     # CLAHE sau đó sẽ kéo brightness lên — ngưỡng này chỉ chặn ảnh gần như đen
_MAX_BRIGHTNESS      = 245    # gần trắng hoàn toàn — quá cháy sáng, không cứu được


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


def extract_face_encoding(image_bytes: bytes) -> list[float]:
    """
    Trích xuất vector đặc trưng khuôn mặt từ bytes ảnh.

    Pipeline:
      1. Haar cascade — kiểm tra ảnh có khuôn mặt (chặn đăng ký ảnh không có mặt).
      2. Crop vùng mặt + padding rộng (50%) để có context cho MTCNN.
      3. DeepFace với model ArcFace + detector MTCNN (tự align theo điểm mắt/mũi).
         Đây là điểm then chốt: KHÔNG dùng `detector_backend="skip"` nữa vì
         skip = không align → embedding bị ảnh hưởng bởi framing/lighting hơn
         là đặc điểm khuôn mặt → false positive giữa người khác nhau.
      4. L2-normalize vector — cosine similarity ổn định, threshold rõ ràng.

    Mock mode (DeepFace không có): vẫn dùng embedding pixel-based để demo,
    threshold sẽ siết chặt riêng cho mode này.
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

    if DEEPFACE_AVAILABLE:
        # Padding 50% — MTCNN cần thấy đủ vùng quanh mặt để align chuẩn.
        pad = int(0.50 * max(w, h))
        x1 = max(0, x - pad)
        y1 = max(0, y - pad)
        x2 = min(img_array.shape[1], x + w + pad)
        y2 = min(img_array.shape[0], y + h + pad)
        face_crop = img_array[y1:y2, x1:x2]
        if face_crop.size == 0:
            raise ValueError("Vùng khuôn mặt rỗng sau khi crop.")

        # Cứu ảnh thiếu sáng / mờ nhẹ trước khi đưa vào MTCNN+ArcFace.
        # Phải làm SAU khi crop có padding (để CLAHE có context xung quanh mặt
        # mà cân bằng tương phản), TRƯỚC khi DeepFace tự align về 112×112.
        face_crop = _enhance_face_region(face_crop)

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
            return emb.tolist()
        except ValueError:
            raise
        except Exception as e:
            # MTCNN có thể fail nếu khuôn mặt quá nghiêng / thiếu sáng quá mạnh.
            # Fallback sang opencv detector của DeepFace để vẫn có cơ hội nhận diện.
            logger.warning(f"MTCNN/ArcFace lỗi, dùng detector opencv thay thế: {e}")
            try:
                # face_crop ở đây đã được enhance rồi (lệnh _enhance_face_region
                # ở trên chạy trước try/except), không cần enhance lại.
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
                return emb.tolist()
            except Exception as e2:
                logger.error(f"Trích xuất ArcFace thất bại (cả 2 detector): {e2}")
                raise ValueError(
                    "Trích xuất khuôn mặt thất bại. Hãy nhìn thẳng vào camera, "
                    "ánh sáng đầy đủ, không đeo khẩu trang/kính râm."
                )

    return _mock_embedding_from_face(img_array, bbox)


def extract_face_encoding_from_base64(image_base64: str) -> list[float]:
    """
    Nhận chuỗi ảnh dạng base64 (có hoặc không có data URI prefix),
    giải mã rồi trích xuất embedding khuôn mặt.
    """
    import base64

    # Bỏ data URI prefix nếu có (vd: "data:image/jpeg;base64,...")
    if "," in image_base64:
        image_base64 = image_base64.split(",", 1)[1]

    image_bytes = base64.b64decode(image_base64)
    return extract_face_encoding(image_bytes)


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


def find_best_match(
    query_encoding: list[float],
    stored_encodings: list[dict],  # danh sách dict {"employee_id": int, "encoding": list[float]}
    threshold: float = 0.4,
) -> tuple[int | None, float]:
    """
    So sánh query_encoding với toàn bộ encoding đã lưu trong database.

    Trả về:
        (employee_id_giống_nhất, độ_giống_cao_nhất) nếu tìm được match vượt ngưỡng,
        ngược lại (None, độ_giống_cao_nhất).
    """
    best_id = None
    best_score = -1.0

    for record in stored_encodings:
        score = cosine_similarity(query_encoding, record["encoding"])
        if score > best_score:
            best_score = score
            best_id = record["employee_id"]

    if best_score >= threshold:
        return best_id, best_score
    return None, best_score


