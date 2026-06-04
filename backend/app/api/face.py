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
ADAPT_SIMILARITY       = 0.70   # ngưỡng "rất chắc chắn" để được đưa vào gallery
MOCK_ADAPT_SIMILARITY  = 0.95


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
        query_encoding = extract_face_encoding_from_base64(body.image_base64)
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

    from app.services.face_service import cosine_similarity

    current = _current_source()
    threshold = _verify_threshold_for(current)
    adapt_threshold = ADAPT_SIMILARITY if current == "arcface_mtcnn_v1" else MOCK_ADAPT_SIMILARITY

    # ── So khớp với toàn bộ gallery — chỉ giữ encoding cùng source và cùng kích thước ──
    best_sim = -1.0
    best_record: FaceEncoding | None = None
    skipped_legacy = 0

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
        if sim > best_sim:
            best_sim = sim
            best_record = fe

    if best_record is None:
        return success_response(
            data={
                "match": False,
                "has_face": True,
                "confidence": 0.0,
                "employee_name": emp.full_name,
                "error": (
                    f"Không có template tương thích trong gallery "
                    f"(skipped {skipped_legacy}/{len(encodings)}). Vui lòng đăng ký lại khuôn mặt."
                ),
            }
        )

    match = best_sim >= threshold

    # ── Adaptive enrollment: nếu confidence rất cao thì lưu thêm template ──
    adapted = False
    if match and best_sim >= adapt_threshold:
        adapted = _add_adaptive_template(
            db, employee_id, query_encoding, current,
        )

    logger.info(
        "FACE VERIFY  emp_id=%s  name=%s  best_sim=%.4f  threshold=%.2f  match=%s  "
        "gallery=%d  adapted=%s",
        employee_id, emp.full_name, best_sim, threshold, match,
        len(encodings), adapted,
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
        }
    )


def _add_adaptive_template(
    db: Session,
    employee_id: int,
    encoding: list[float],
    source: str,
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

        payload = json.dumps({"encoding": encoding, "source": source})
        db.add(FaceEncoding(
            employee_id=employee_id,
            encoding_data=payload,
            is_primary=False,
        ))
        db.commit()
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
