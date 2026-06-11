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

# ArcFace cosine: cùng người ~0.55–0.85, khác người ~0.05–0.40.
VERIFY_THRESHOLD = float(os.getenv("FACE_VERIFY_THRESHOLD", "0.55"))
MOCK_VERIFY_THRESHOLD = float(os.getenv("FACE_MOCK_VERIFY_THRESHOLD", "0.86"))

# Gallery = 1 primary + tối đa 7 phụ (seed đa pose + adaptive).
MAX_GALLERY_SIZE       = 8
ENROLL_RESERVED_SLOTS  = 3   # chừa slot cho adaptive, không fill hết bằng seed
ADAPT_SIMILARITY       = 0.70
MOCK_ADAPT_SIMILARITY  = 0.95

# Tier HARD: học frame khó (0.60 ≤ sim < 0.70) với safeguard quality + diversity + rate-limit.
ADAPT_SIMILARITY_HARD          = 0.60
HARD_ADAPT_MIN_BRIGHTNESS      = 50.0
HARD_ADAPT_MAX_BRIGHTNESS      = 220.0
HARD_ADAPT_MIN_BLUR_VAR        = 30.0
HARD_ADAPT_DIVERSITY_MAX_SIM   = 0.90
HARD_ADAPT_DAILY_LIMIT         = 2


def _current_source() -> str:
    return "arcface_mtcnn_v1" if DEEPFACE_AVAILABLE else "mock_v2"


def _verify_threshold_for(source: str) -> float:
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

    source = _current_source()
    payload = json.dumps({"encoding": encoding, "source": source})

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
        # Đổi primary → reset gallery adaptive để không trộn encoding cũ-mới.
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

    extras_added = 0
    extras_failed = 0
    if body.extra_images:
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
            "gallery_size": len(encs),
            "adaptive_count": adaptive_count,
            "max_gallery_size": MAX_GALLERY_SIZE,
        }
    )


@router.post("/verify/{employee_id}", response_model=dict)
def verify_face_for_employee(
    employee_id: int,
    body: FaceRegisterRequest,
    db: Session = Depends(get_db),
):
    """Xác thực 1:1 — kiosk gọi sau khi quét RFID, không yêu cầu token."""
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
            "adapted": adapted,
            "adapt_tier": adapt_tier,
        }
    )


def _count_today_hard_adapts(db: Session, employee_id: int) -> int:
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
    if best_sim >= ADAPT_SIMILARITY:
        return "easy"

    if best_sim < ADAPT_SIMILARITY_HARD:
        return None

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

    max_existing_sim = max(compatible_sims) if compatible_sims else 0.0
    if max_existing_sim >= HARD_ADAPT_DIVERSITY_MAX_SIM:
        logger.info(
            "ADAPT-HARD REJECT  emp_id=%s  sim=%.4f  max_existing=%.4f ≥ %.2f "
            "(đã có template tương tự) — skip.",
            employee_id, best_sim, max_existing_sim, HARD_ADAPT_DIVERSITY_MAX_SIM,
        )
        return None

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
    """Thêm template phụ; khi gallery đầy → diversity-aware replacement."""
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
                logger.warning(
                    f"Gallery emp_id={employee_id} đầy nhưng không tìm được "
                    "template phụ để xóa — bỏ qua adaptive."
                )
                return False

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
    """Template phụ có max-cosine cao nhất với gallery = redundant nhất; tie-break FIFO."""
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
