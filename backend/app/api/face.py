"""
Các endpoint đăng ký và nhận diện khuôn mặt.
"""
import json
import logging
import os
from app.utils import now_vn

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_current_admin, get_current_user, success_response
from app.database import get_db
from app.models.employee import Employee
from app.models.face_encoding import FaceEncoding
from app.models.user import User
from app.schemas.face import FaceRecognizeRequest, FaceRegisterRequest
from app.services.face_service import (
    DEEPFACE_AVAILABLE,
    cosine_similarity,
    extract_face_encoding_from_base64,
    extract_face_with_meta_from_base64,
)

logger = logging.getLogger(__name__)
router = APIRouter()

# ArcFace + MTCNN align + cosine similarity trên vector đã L2-normalize.
# Trên embedding đã L2-normalize, theo tài liệu ArcFace:
#   - cùng một người:    ~0.55–0.85
#   - người khác nhau:   ~0.05–0.40
# 0.40 = biên trên của phân bố "người khác" — chấp nhận một chút overlap với
# nhóm intra-class biên thấp (ảnh chụp tệ, đeo kính, đổi tóc). Bộ NV nhỏ
# (10-50 NV) thì false-accept ở 0.40 vẫn rất hiếm trong thực tế (cần kẻ giả
# có khuôn mặt cấu trúc tương tự + ảnh đủ rõ → gần như không xảy ra).
# Trade-off: hạ từ 0.45 → 0.40 đổi an toàn lý thuyết lấy demo-ability thật.
VERIFY_THRESHOLD = float(os.getenv("FACE_VERIFY_THRESHOLD", "0.40"))
MOCK_VERIFY_THRESHOLD = float(os.getenv("FACE_MOCK_VERIFY_THRESHOLD", "0.86"))

# ─── Adaptive enrollment (online template gallery) ──────────────────────────
# Mỗi nhân viên có thể có tối đa MAX_GALLERY_SIZE template:
#   - 1 template chính (is_primary=True) — do admin đăng ký
#   - tối đa MAX_GALLERY_SIZE - 1 template phụ — gồm:
#       • Seed lúc đăng ký multi-pose (tối đa MAX_GALLERY_SIZE - 1 - ENROLL_RESERVED_SLOTS)
#       • Adaptive — tự học từ các lần verify thành công với độ giống
#         ≥ ADAPT_SIMILARITY (cao hơn ngưỡng accept để tránh "poison" gallery)
# Khi gallery đầy, dùng diversity-aware replacement (xem _add_adaptive_template).
#
# Vì sao 8 slot: 1 primary + 5 seed (3 không kính + 2 có kính) + 3 slot dành
# riêng cho adaptive học sau này (đeo khẩu trang, đổi kiểu tóc, lão hóa nhẹ…).
# Nếu fill cả 8 slot ngay từ enrollment, mọi adaptive sau đó đều phải kick một
# seed ra — mà seed đa pose là tài sản quý nhất → mất diversity.
MAX_GALLERY_SIZE       = 8
ENROLL_RESERVED_SLOTS  = 3   # số slot LUÔN để trống lúc đăng ký, dành cho adaptive evolution
ADAPT_SIMILARITY       = 0.70   # ngưỡng "rất chắc chắn" để được đưa vào gallery (tier EASY)
MOCK_ADAPT_SIMILARITY  = 0.95

# ─── Adaptive 2-tier (học từ frame "khó" — điều kiện khắc nghiệt) ───────────
# Mục tiêu: khi user đến trong điều kiện khó (ánh sáng kém, góc nghiêng nhẹ,
# đổi diện mạo dần…), cosine match có thể chỉ ~0.60–0.70 — VẪN xác thực được
# nhưng nếu không học vào gallery thì lần sau gặp đúng điều kiện đó lại fail.
# Tier HARD học chính những frame này để gallery "tiến hóa" theo điều kiện
# thực tế của user, không chỉ giữ baseline ngày đăng ký.
#
# Safeguards (để không phá gallery khi cosine sát ngưỡng verify):
#   • Quality gate stricter — frame phải đủ dùng được, không quá tối/mờ
#   • Diversity gate — embedding mới phải mang thông tin mới so với gallery
#     (max cosine đến template hiện có < DIVERSITY_MAX_SIM)
#   • Rate limit hàng ngày — mỗi user tối đa MAX_DAILY_HARD_ADAPTS frame
#     tier-HARD/ngày, chống case kẻ giả mạo lọt verify rồi spam adapt
ADAPT_SIMILARITY_HARD          = 0.60
HARD_ADAPT_MIN_BRIGHTNESS      = 50.0
HARD_ADAPT_MAX_BRIGHTNESS      = 220.0
HARD_ADAPT_MIN_BLUR_VAR        = 30.0
HARD_ADAPT_DIVERSITY_MAX_SIM   = 0.90  # max cosine cho phép với template gần nhất
HARD_ADAPT_DAILY_LIMIT         = 2


def _current_source() -> str:
    """Tag nhận dạng phiên bản encoding — chặn so khớp giữa các phiên bản encoding khác nhau."""
    return "arcface_mtcnn_v1" if DEEPFACE_AVAILABLE else "mock_v2"


def _verify_threshold_for(source: str) -> float:
    # Source "arcface_mtcnn_v1" = encoding ArcFace (cosine similarity range thực tế
    # 0.55–0.85 với cùng người, dùng VERIFY_THRESHOLD=0.50).
    # Source "mock_v2" = embedding pixel-based fallback khi DeepFace chưa cài,
    # phân bố đặc khác hẳn → cần MOCK_VERIFY_THRESHOLD=0.86.
    # Trước đây check "deepface" → SAI, vì _current_source trả "arcface_mtcnn_v1"
    # → mọi verify đều rơi vào nhánh mock 0.90, gây false-reject hàng loạt
    # (chính bug làm 0.85 vẫn fail).
    return MOCK_VERIFY_THRESHOLD if source == "mock_v2" else VERIFY_THRESHOLD


@router.post("/register/{employee_id}", response_model=dict)
def register_face(
    employee_id: int,
    body: FaceRegisterRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    emp = db.query(Employee).filter(Employee.id == employee_id).first()
    if not emp:
        raise HTTPException(status_code=404, detail="Không tìm thấy nhân viên.")

    try:
        encoding = extract_face_encoding_from_base64(body.image_base64)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Lưu kèm source để phân biệt encoding DeepFace vs mock_v2
    source = _current_source()
    payload = json.dumps({"encoding": encoding, "source": source})

    # Chỉ ảnh hưởng template chính. Các template phụ (adaptive) sẽ bị xóa vì
    # template chính đổi → toàn bộ gallery cần học lại từ baseline mới để
    # tránh trộn encoding cũ-mới có thể đại diện cho góc/ánh sáng khác xa nhau.
    existing_primary = (
        db.query(FaceEncoding)
        .filter(FaceEncoding.employee_id == employee_id,
                FaceEncoding.is_primary == True)  # noqa: E712
        .first()
    )
    now = now_vn()

    if existing_primary:
        existing_primary.encoding_data = payload
        existing_primary.updated_at = now
        # Reset gallery adaptive — template chính đã đổi, bắt đầu học lại
        db.query(FaceEncoding).filter(
            FaceEncoding.employee_id == employee_id,
            FaceEncoding.is_primary == False,  # noqa: E712
        ).delete(synchronize_session=False)
        db.commit()
        msg = "Cập nhật khuôn mặt thành công. Gallery adaptive đã được reset."
    else:
        face_enc = FaceEncoding(
            employee_id=employee_id,
            encoding_data=payload,
            is_primary=True,
        )
        db.add(face_enc)
        db.commit()
        msg = "Đăng ký khuôn mặt thành công."

    # ── Multi-pose seed: lưu thêm ảnh phụ như template phụ ──────────────────
    # Mỗi ảnh extra giúp gallery có sẵn embedding cho 1 góc/ánh sáng khác,
    # tăng độ ổn định ngay từ lần verify đầu tiên — không cần chờ adaptive
    # enrollment học dần qua hàng chục lần điểm danh thành công.
    extras_added = 0
    extras_failed = 0
    if body.extra_images:
        # Cap số seed: chừa ENROLL_RESERVED_SLOTS slot cho adaptive evolution
        # về sau (vd: sau này user đeo khẩu trang đi làm, hệ thống cần chỗ để
        # học thêm template "có khẩu trang" mà không phải đè lên seed đa pose).
        slots_left = MAX_GALLERY_SIZE - 1 - ENROLL_RESERVED_SLOTS
        for img_b64 in body.extra_images[:slots_left]:
            try:
                extra_enc = extract_face_encoding_from_base64(img_b64)
            except ValueError as e:
                logger.info(f"Bỏ qua ảnh extra (chất lượng kém): {e}")
                extras_failed += 1
                continue
            extra_payload = json.dumps({"encoding": extra_enc, "source": source})
            db.add(FaceEncoding(
                employee_id=employee_id,
                encoding_data=extra_payload,
                is_primary=False,
            ))
            extras_added += 1
        if extras_added:
            db.commit()
            msg += f" Đã seed {extras_added} template phụ"
            if extras_failed:
                msg += f" ({extras_failed} ảnh bị bỏ vì chất lượng kém)"
            msg += "."

    return success_response(
        data={
            "employee_id": employee_id,
            "employee_name": emp.full_name,
            "extras_added": extras_added,
            "extras_failed": extras_failed,
        },
        message=msg,
    )


@router.delete("/{employee_id}", response_model=dict)
def delete_face(
    employee_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    """Xóa toàn bộ template (cả primary lẫn adaptive) của một nhân viên."""
    deleted = (
        db.query(FaceEncoding)
        .filter(FaceEncoding.employee_id == employee_id)
        .delete(synchronize_session=False)
    )
    if deleted == 0:
        raise HTTPException(status_code=404, detail="Nhân viên này chưa đăng ký khuôn mặt.")

    db.commit()
    return success_response(
        message=f"Xóa dữ liệu khuôn mặt thành công ({deleted} template).",
    )


@router.get("/{employee_id}", response_model=dict)
def get_face_status(
    employee_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    emp = db.query(Employee).filter(Employee.id == employee_id).first()
    if not emp:
        raise HTTPException(status_code=404, detail="Không tìm thấy nhân viên.")

    encs = (
        db.query(FaceEncoding)
        .filter(FaceEncoding.employee_id == employee_id)
        .order_by(FaceEncoding.is_primary.desc(), FaceEncoding.created_at.asc())
        .all()
    )
    primary = next((e for e in encs if e.is_primary), None)
    adaptive_count = sum(1 for e in encs if not e.is_primary)
    return success_response(
        data={
            "employee_id": employee_id,
            "has_face": primary is not None,
            "registered_at": primary.created_at.isoformat() if primary else None,
            "gallery_size": len(encs),       # tổng số template (primary + adaptive)
            "adaptive_count": adaptive_count,  # số template tự học
            "max_gallery_size": MAX_GALLERY_SIZE,
        }
    )


@router.post("/verify/{employee_id}", response_model=dict)
def verify_face_for_employee(
    employee_id: int,
    body: FaceRegisterRequest,
    db: Session = Depends(get_db),
):
    """
    Xác thực khuôn mặt 1:1 — so khuôn mặt đang chụp với encoding đã lưu của
    một nhân viên cụ thể (kiosk gọi sau khi đã định danh qua thẻ RFID).
    Không yêu cầu xác thực để kiosk có thể gọi mà không cần token admin.
    """
    emp = db.query(Employee).filter(Employee.id == employee_id).first()
    if not emp:
        raise HTTPException(status_code=404, detail="Không tìm thấy nhân viên.")

    encodings = (
        db.query(FaceEncoding)
        .filter(FaceEncoding.employee_id == employee_id)
        .order_by(FaceEncoding.is_primary.desc(), FaceEncoding.created_at.asc())
        .all()
    )
    if not encodings:
        return success_response(
            data={"match": False, "has_face": False, "confidence": 0.0,
                  "employee_name": emp.full_name},
            message="Nhân viên chưa đăng ký khuôn mặt.",
        )

    try:
        query_meta = extract_face_with_meta_from_base64(body.image_base64)
    except ValueError as e:
        return success_response(
            data={
                "match": False,
                "has_face": True,
                "confidence": 0.0,
                "employee_name": emp.full_name,
                "error": str(e),
            }
        )
    query_encoding = query_meta["encoding"]
    query_brightness = query_meta["brightness"]
    query_blur_var = query_meta["blur_var"]

    from app.services.face_service import cosine_similarity

    current = _current_source()
    threshold = _verify_threshold_for(current)
    adapt_threshold = ADAPT_SIMILARITY if current == "arcface_mtcnn_v1" else MOCK_ADAPT_SIMILARITY

    # ── So khớp với toàn bộ gallery — chỉ giữ encoding cùng source và cùng kích thước ──
    # Đồng thời thu thập SIM với từng template (compatible_sims) để tier-HARD
    # check diversity (= max cosine với gallery hiện tại có nhỏ hơn ngưỡng không).
    best_sim = -1.0
    best_record: FaceEncoding | None = None
    skipped_legacy = 0
    compatible_sims: list[float] = []

    for fe in encodings:
        try:
            raw = json.loads(fe.encoding_data)
        except (json.JSONDecodeError, TypeError):
            continue
        if isinstance(raw, dict):
            enc = raw.get("encoding")
            src = raw.get("source", "legacy")
        else:
            enc = raw
            src = "legacy"
        if src != current or not isinstance(enc, list):
            skipped_legacy += 1
            continue
        if len(enc) != len(query_encoding):
            skipped_legacy += 1
            continue
        sim = cosine_similarity(query_encoding, enc)
        compatible_sims.append(sim)
        if sim > best_sim:
            best_sim = sim
            best_record = fe

    if best_record is None:
        # Tất cả template trong gallery đều không tương thích model hiện tại
        # (vd: encoding cũ length 128 của model deepface generic, trong khi
        # hiện tại dùng arcface_mtcnn_v1 length 512). Đối với kiosk, trạng
        # thái này = "chưa đăng ký dưới phiên bản encoding hiện tại" — báo
        # has_face=False để kiosk hiện thông báo "Chưa đăng ký khuôn mặt"
        # rõ ràng, user biết liên hệ admin đăng ký lại trên web.
        logger.warning(
            "FACE VERIFY  emp_id=%s  name=%s  gallery=%d nhưng TẤT CẢ template không tương thích "
            "(skipped %d) — yêu cầu đăng ký lại.",
            employee_id, emp.full_name, len(encodings), skipped_legacy,
        )
        return success_response(
            data={
                "match": False,
                "has_face": False,
                "confidence": 0.0,
                "employee_name": emp.full_name,
            },
            message="Khuôn mặt được đăng ký với phiên bản cũ. Vui lòng đăng ký lại.",
        )

    match = best_sim >= threshold

    # ── Adaptive enrollment 2-tier ──────────────────────────────────────────
    # Tier EASY (best_sim ≥ ADAPT_SIMILARITY=0.70): tự thêm template, gallery
    # tự dịch chuyển theo điều kiện thường gặp (logic cũ).
    # Tier HARD (ADAPT_SIMILARITY_HARD=0.60 ≤ best_sim < 0.70): học các frame
    # "khó" với 3 lớp safeguard (quality + diversity + daily rate-limit) để
    # gallery thực sự tiến hóa theo điều kiện khắc nghiệt mà không bị poison.
    # Dưới 0.60: không adapt — tránh dạy gallery học theo điểm sát ngưỡng
    # verify, làm impersonation dễ dần.
    adapted = False
    adapt_tier: str | None = None
    if match and current == "arcface_mtcnn_v1":
        adapt_tier = _decide_adapt_tier(
            db=db,
            employee_id=employee_id,
            best_sim=best_sim,
            compatible_sims=compatible_sims,
            query_brightness=query_brightness,
            query_blur_var=query_blur_var,
        )
        if adapt_tier:
            adapted = _add_adaptive_template(
                db, employee_id, query_encoding, current, tier=adapt_tier,
                quality_brightness=query_brightness, quality_blur=query_blur_var,
            )
    elif match and best_sim >= adapt_threshold:
        # Mock mode dùng threshold riêng, không có 2-tier.
        adapt_tier = "mock"
        adapted = _add_adaptive_template(
            db, employee_id, query_encoding, current, tier=adapt_tier,
            quality_brightness=query_brightness, quality_blur=query_blur_var,
        )

    logger.info(
        "FACE VERIFY  emp_id=%s  name=%s  best_sim=%.4f  threshold=%.2f  match=%s  "
        "gallery=%d  brightness=%.0f  blur=%.0f  adapt_tier=%s  adapted=%s",
        employee_id, emp.full_name, best_sim, threshold, match,
        len(encodings), query_brightness, query_blur_var, adapt_tier, adapted,
    )

    return success_response(
        data={
            "match": match,
            "has_face": True,
            "confidence": round(best_sim, 4),
            "threshold": threshold,
            "employee_name": emp.full_name,
            "gallery_size": len(encodings),
            "adapted": adapted,  # True nếu lần verify này thêm 1 template mới vào gallery
            "adapt_tier": adapt_tier,  # "easy" / "hard" / None — phục vụ logging và demo
        }
    )


def _count_today_hard_adapts(db: Session, employee_id: int) -> int:
    """Đếm số template tier-HARD đã thêm trong ngày hôm nay cho 1 user.

    Tier được mã hóa vào trường `tier` trong JSON encoding_data — chỉ có
    template tier='hard' mới tính vào rate-limit (easy không giới hạn vì đã
    yêu cầu cosine ≥ 0.70 và diversity-aware tự kiềm chế).
    """
    from sqlalchemy import func
    from app.utils import now_vn
    today_start = now_vn().replace(hour=0, minute=0, second=0, microsecond=0)
    rows = (
        db.query(FaceEncoding)
        .filter(
            FaceEncoding.employee_id == employee_id,
            FaceEncoding.is_primary == False,  # noqa: E712
            FaceEncoding.created_at >= today_start,
        )
        .all()
    )
    count = 0
    for fe in rows:
        try:
            raw = json.loads(fe.encoding_data)
            if isinstance(raw, dict) and raw.get("tier") == "hard":
                count += 1
        except (json.JSONDecodeError, TypeError):
            continue
    return count


def _decide_adapt_tier(
    db: Session,
    employee_id: int,
    best_sim: float,
    compatible_sims: list[float],
    query_brightness: float,
    query_blur_var: float,
) -> str | None:
    """
    Quyết định tier adapt cho query hiện tại (chỉ áp dụng cho arcface source).

    Trả về:
      - "easy" : best_sim ≥ ADAPT_SIMILARITY (0.70) — adapt tự do, gallery
                 tự cân bằng qua diversity-aware replacement.
      - "hard" : ADAPT_SIMILARITY_HARD ≤ best_sim < ADAPT_SIMILARITY, AND
                 quality đủ tốt (đủ sáng, đủ nét), AND diversity OK (chưa có
                 template nào trong gallery quá giống query), AND chưa
                 vượt rate-limit hôm nay → frame "khó" thực sự đáng học.
      - None   : các trường hợp còn lại — không adapt.

    Trả về None thay vì raise để verify endpoint vẫn match thành công ngay
    cả khi từ chối adapt — adapt là tối ưu sau verify, không phải điều kiện.
    """
    if best_sim >= ADAPT_SIMILARITY:
        return "easy"

    if best_sim < ADAPT_SIMILARITY_HARD:
        return None

    # Tier HARD candidate — kiểm tra 3 safeguards:
    # 1. Quality gate — frame phải đủ tốt để đại diện cho điều kiện thực
    #    user gặp, không phải frame rác. Cho phép khoảng rộng hơn quality
    #    check thông thường (vì user đang ở điều kiện khó, không nên kén).
    if not (HARD_ADAPT_MIN_BRIGHTNESS <= query_brightness <= HARD_ADAPT_MAX_BRIGHTNESS):
        logger.info(
            "ADAPT-HARD REJECT  emp_id=%s  sim=%.4f  brightness=%.0f ngoài "
            "khoảng [%.0f, %.0f] — skip.",
            employee_id, best_sim, query_brightness,
            HARD_ADAPT_MIN_BRIGHTNESS, HARD_ADAPT_MAX_BRIGHTNESS,
        )
        return None
    if query_blur_var < HARD_ADAPT_MIN_BLUR_VAR:
        logger.info(
            "ADAPT-HARD REJECT  emp_id=%s  sim=%.4f  blur=%.1f < %.0f — skip.",
            employee_id, best_sim, query_blur_var, HARD_ADAPT_MIN_BLUR_VAR,
        )
        return None

    # 2. Diversity gate — query phải mang thông tin MỚI so với gallery hiện
    #    có. Nếu max cosine query vs gallery ≥ 0.90 → đã có template gần
    #    giống → adapt thêm chỉ làm gallery chật, không cứu được case nào
    #    mới. Lưu ý đây dùng compatible_sims đã lọc cùng source/length.
    max_existing_sim = max(compatible_sims) if compatible_sims else 0.0
    if max_existing_sim >= HARD_ADAPT_DIVERSITY_MAX_SIM:
        logger.info(
            "ADAPT-HARD REJECT  emp_id=%s  sim=%.4f  max_existing=%.4f ≥ %.2f "
            "(đã có template tương tự) — skip.",
            employee_id, best_sim, max_existing_sim, HARD_ADAPT_DIVERSITY_MAX_SIM,
        )
        return None

    # 3. Rate-limit hôm nay — chống case impersonator lọt verify (cosine
    #    0.60-0.70) rồi spam check-in nhiều lần liên tiếp để adapt poison
    #    gallery dần thành mặt của họ.
    today_hard = _count_today_hard_adapts(db, employee_id)
    if today_hard >= HARD_ADAPT_DAILY_LIMIT:
        logger.info(
            "ADAPT-HARD REJECT  emp_id=%s  sim=%.4f  daily=%d/%d đã đạt — skip.",
            employee_id, best_sim, today_hard, HARD_ADAPT_DAILY_LIMIT,
        )
        return None

    return "hard"


def _add_adaptive_template(
    db: Session,
    employee_id: int,
    encoding: list[float],
    source: str,
    tier: str = "easy",
    quality_brightness: float | None = None,
    quality_blur: float | None = None,
) -> bool:
    """
    Thêm encoding của lần verify thành công (confidence cao) vào gallery như
    template phụ. Khi gallery đầy, dùng **diversity-aware replacement**:

      Với mỗi template phụ, tính độ giống cosine cao nhất với các template
      KHÁC trong gallery (kể cả template chính). Template phụ có max-cosine
      cao nhất là "redundant nhất" — đã có template khác đại diện gần như
      cùng góc/ánh sáng — sẽ bị xóa. Template chính không bao giờ bị động.

    Vì sao không dùng FIFO:
      Nếu user đăng ký 3 ảnh không kính + 2 ảnh có kính, rồi đi làm 100 lần
      không kính, FIFO sẽ xóa dần 2 seed có kính (vì chúng cũ hơn) → mất hết
      diversity, hệ thống lại reject khi user đeo kính. Diversity-aware sẽ
      giữ 2 seed có kính (chúng "khác" tất cả template không kính), chỉ thay
      thế các adaptive không kính trùng lặp lẫn nhau.

    Tác dụng cho "tiến hóa": khi user dần thay đổi (đeo khẩu trang, đổi tóc,
    lão hóa), embedding mới khác biệt với gallery cũ → KHÔNG bị xếp loại
    redundant → tự động thay thế các template "phiên bản cũ" đã trùng lặp,
    gallery dịch chuyển theo user một cách tự nhiên.

    Trả về True nếu thực sự đã thêm; False nếu lỗi (DB / parse).
    """
    try:
        all_for_emp = (
            db.query(FaceEncoding)
            .filter(FaceEncoding.employee_id == employee_id)
            .order_by(FaceEncoding.is_primary.desc(), FaceEncoding.created_at.asc())
            .all()
        )

        if len(all_for_emp) >= MAX_GALLERY_SIZE:
            victim = _pick_redundant_adaptive(all_for_emp)
            if victim is not None:
                db.delete(victim)
            else:
                # Edge case: chỉ có toàn primary (không thể) hoặc tất cả encoding
                # đều parse lỗi → không có gì xóa được, bỏ qua adaptive lần này
                # để không gây inconsistent state.
                logger.warning(
                    f"Gallery emp_id={employee_id} đầy nhưng không tìm được "
                    "template phụ để xóa — bỏ qua adaptive."
                )
                return False

        # Lưu kèm tier + quality metrics để:
        #   • _count_today_hard_adapts đếm được template tier='hard'/ngày
        #   • Có audit trail cho báo cáo: "X template học được trong điều
        #     kiện khắc nghiệt (brightness < 70, blur < 40) trong tuần"
        payload_dict = {"encoding": encoding, "source": source, "tier": tier}
        if quality_brightness is not None:
            payload_dict["brightness"] = round(quality_brightness, 1)
        if quality_blur is not None:
            payload_dict["blur_var"] = round(quality_blur, 1)
        payload = json.dumps(payload_dict)
        db.add(FaceEncoding(
            employee_id=employee_id,
            encoding_data=payload,
            is_primary=False,
        ))
        db.commit()
        logger.info(
            "FACE ADAPT  emp_id=%s  tier=%s  brightness=%s  blur=%s",
            employee_id, tier,
            f"{quality_brightness:.0f}" if quality_brightness is not None else "-",
            f"{quality_blur:.0f}" if quality_blur is not None else "-",
        )
        return True
    except Exception as e:
        db.rollback()
        logger.warning(f"Không thêm được template adaptive cho emp_id={employee_id}: {e}")
        return False


def _pick_redundant_adaptive(all_for_emp: list[FaceEncoding]) -> FaceEncoding | None:
    """
    Trong số template phụ (is_primary=False), trả về cái redundant nhất —
    tức cái có max-cosine với một template khác trong gallery cao nhất.

    Nếu nhiều template hòa max-cosine, tie-break bằng created_at cũ hơn
    (giống FIFO trên các template tương đương).

    Complexity O(n²) trên n = MAX_GALLERY_SIZE = 8 → 28 phép cosine, không
    đáng kể. Encoding lỗi parse được bỏ qua khi tính (an toàn).
    """
    parsed: list[tuple[FaceEncoding, list[float]]] = []
    for fe in all_for_emp:
        try:
            data = json.loads(fe.encoding_data)
            enc = data.get("encoding")
            if isinstance(enc, list) and enc:
                parsed.append((fe, enc))
        except (json.JSONDecodeError, TypeError):
            continue

    candidates = [(fe, enc) for fe, enc in parsed if not fe.is_primary]
    if not candidates:
        return None

    best_victim: FaceEncoding | None = None
    best_max_sim = -2.0
    for fe, enc in candidates:
        max_sim_to_others = -2.0
        for fe2, enc2 in parsed:
            if fe2.id == fe.id:
                continue
            sim = cosine_similarity(enc, enc2)
            if sim > max_sim_to_others:
                max_sim_to_others = sim
        if (max_sim_to_others > best_max_sim
                or (max_sim_to_others == best_max_sim
                    and best_victim is not None
                    and fe.created_at < best_victim.created_at)):
            best_max_sim = max_sim_to_others
            best_victim = fe

    # Fallback: nếu không tính được sim (chỉ có 1 template hợp lệ) → FIFO
    if best_victim is None:
        adaptive_only = [fe for fe in all_for_emp if not fe.is_primary]
        if adaptive_only:
            best_victim = min(adaptive_only, key=lambda fe: fe.created_at)
    return best_victim

@router.post("/recognize", response_model=dict)
def recognize_face(
    body: FaceRecognizeRequest,
    db: Session = Depends(get_db),
):
    _ = body, db
    raise HTTPException(
        status_code=403,
        detail="Bat buoc quet the RFID truoc roi xac thuc khuon mat 1:1.",
    )
