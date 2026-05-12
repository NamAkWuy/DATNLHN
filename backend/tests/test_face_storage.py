"""
API integration tests for face registration, status, deletion, and recognition.

Tests verify:
1. Face encoding được lưu đúng vào DB sau khi đăng ký
2. Cập nhật encoding hoạt động (upsert)
3. Trạng thái has_face trả về đúng
4. Xóa encoding hoạt động đúng
5. Nhận diện khuôn mặt trả về đúng nhân viên
6. Các trường hợp lỗi (nhân viên không tồn tại, inactive, không có encoding)
"""
import json
import base64
from io import BytesIO

import pytest

from tests.conftest import make_test_image_base64
from app.services.face_service import (
    extract_face_encoding_from_base64,
    mock_encoding_for_employee,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _register_face(client, employee_id: int, image_b64: str):
    """POST /api/v1/face/register/{employee_id}"""
    return client.post(
        f"/api/v1/face/register/{employee_id}",
        json={"image_base64": image_b64},
    )


def _get_face_status(client, employee_id: int):
    """GET /api/v1/face/{employee_id}"""
    return client.get(f"/api/v1/face/{employee_id}")


def _delete_face(client, employee_id: int):
    """DELETE /api/v1/face/{employee_id}"""
    return client.delete(f"/api/v1/face/{employee_id}")


def _recognize_face(client, image_b64: str):
    """POST /api/v1/face/recognize"""
    return client.post(
        "/api/v1/face/recognize",
        json={"image_base64": image_b64},
    )


# ---------------------------------------------------------------------------
# Tests: face registration
# ---------------------------------------------------------------------------

class TestFaceRegistration:
    def test_register_face_returns_200(self, client, employee):
        img_b64 = make_test_image_base64()
        res = _register_face(client, employee.id, img_b64)
        assert res.status_code == 200

    def test_register_face_response_format(self, client, employee):
        img_b64 = make_test_image_base64()
        res = _register_face(client, employee.id, img_b64)
        body = res.json()
        assert body["success"] is True
        assert body["data"]["employee_id"] == employee.id
        assert body["data"]["employee_name"] == employee.full_name

    def test_register_face_stores_encoding_in_db(self, client, employee, db):
        """Sau khi đăng ký, bảng dac_trung_khuon_mat phải có bản ghi."""
        from app.models.face_encoding import FaceEncoding

        img_b64 = make_test_image_base64()
        _register_face(client, employee.id, img_b64)

        face_enc = (
            db.query(FaceEncoding)
            .filter(FaceEncoding.employee_id == employee.id)
            .first()
        )
        assert face_enc is not None, "Không tìm thấy encoding trong DB"
        assert face_enc.encoding_data is not None

    def test_register_face_encoding_is_valid_json_list(self, client, employee, db):
        """encoding_data lưu trong DB phải là JSON list 128 số thực."""
        from app.models.face_encoding import FaceEncoding

        img_b64 = make_test_image_base64()
        _register_face(client, employee.id, img_b64)

        fe = (
            db.query(FaceEncoding)
            .filter(FaceEncoding.employee_id == employee.id)
            .first()
        )
        encoding_list = json.loads(fe.encoding_data)
        assert isinstance(encoding_list, list)
        assert len(encoding_list) == 128
        assert all(isinstance(v, float) for v in encoding_list)

    def test_register_face_updates_existing_encoding(self, client, employee, db):
        """Đăng ký lại cùng nhân viên phải cập nhật encoding cũ (upsert, không tạo bản ghi mới)."""
        from app.models.face_encoding import FaceEncoding

        img1 = make_test_image_base64(color=(100, 100, 100))
        img2 = make_test_image_base64(color=(200, 200, 200))

        _register_face(client, employee.id, img1)
        enc1 = json.loads(
            db.query(FaceEncoding)
            .filter(FaceEncoding.employee_id == employee.id)
            .first()
            .encoding_data
        )

        _register_face(client, employee.id, img2)
        db.expire_all()

        face_rows = (
            db.query(FaceEncoding)
            .filter(FaceEncoding.employee_id == employee.id)
            .all()
        )
        # Chỉ có đúng 1 bản ghi (upsert, không duplicate)
        assert len(face_rows) == 1
        enc2 = json.loads(face_rows[0].encoding_data)
        # Encoding phải khác sau khi cập nhật bằng ảnh khác
        assert enc1 != enc2

    def test_register_face_404_for_nonexistent_employee(self, client):
        img_b64 = make_test_image_base64()
        res = _register_face(client, 99999, img_b64)
        assert res.status_code == 404

    def test_register_face_400_for_invalid_base64(self, client, employee):
        res = _register_face(client, employee.id, "not_valid_base64!!!!")
        assert res.status_code == 400


# ---------------------------------------------------------------------------
# Tests: face status
# ---------------------------------------------------------------------------

class TestFaceStatus:
    def test_has_face_true_after_registration(self, client, employee):
        img_b64 = make_test_image_base64()
        _register_face(client, employee.id, img_b64)

        res = _get_face_status(client, employee.id)
        body = res.json()

        assert res.status_code == 200
        assert body["success"] is True
        assert body["data"]["has_face"] is True
        assert body["data"]["employee_id"] == employee.id

    def test_has_face_false_when_not_registered(self, client, employee):
        res = _get_face_status(client, employee.id)
        body = res.json()

        assert res.status_code == 200
        assert body["data"]["has_face"] is False

    def test_registered_at_is_not_null_after_registration(self, client, employee):
        img_b64 = make_test_image_base64()
        _register_face(client, employee.id, img_b64)

        res = _get_face_status(client, employee.id)
        body = res.json()

        assert body["data"]["registered_at"] is not None

    def test_registered_at_is_null_before_registration(self, client, employee):
        res = _get_face_status(client, employee.id)
        assert res.json()["data"]["registered_at"] is None

    def test_face_status_404_for_nonexistent_employee(self, client):
        res = _get_face_status(client, 99999)
        assert res.status_code == 404


# ---------------------------------------------------------------------------
# Tests: face deletion
# ---------------------------------------------------------------------------

class TestFaceDeletion:
    def test_delete_face_removes_from_db(self, client, employee, db):
        from app.models.face_encoding import FaceEncoding

        img_b64 = make_test_image_base64()
        _register_face(client, employee.id, img_b64)

        res = _delete_face(client, employee.id)
        assert res.status_code == 200
        assert res.json()["success"] is True

        db.expire_all()
        face_enc = (
            db.query(FaceEncoding)
            .filter(FaceEncoding.employee_id == employee.id)
            .first()
        )
        assert face_enc is None, "Encoding phải bị xóa khỏi DB"

    def test_delete_face_returns_404_when_no_encoding(self, client, employee):
        res = _delete_face(client, employee.id)
        assert res.status_code == 404

    def test_has_face_false_after_deletion(self, client, employee):
        img_b64 = make_test_image_base64()
        _register_face(client, employee.id, img_b64)
        _delete_face(client, employee.id)

        res = _get_face_status(client, employee.id)
        assert res.json()["data"]["has_face"] is False


# ---------------------------------------------------------------------------
# Tests: face recognition
# ---------------------------------------------------------------------------

class TestFaceRecognition:
    def _seed_face_for_employee(self, db, employee_id: int, encoding: list[float]):
        """Trực tiếp chèn encoding vào DB để kiểm soát giá trị chính xác."""
        from app.models.face_encoding import FaceEncoding

        existing = (
            db.query(FaceEncoding)
            .filter(FaceEncoding.employee_id == employee_id)
            .first()
        )
        if existing:
            existing.encoding_data = json.dumps(encoding)
        else:
            fe = FaceEncoding(
                employee_id=employee_id,
                encoding_data=json.dumps(encoding),
            )
            db.add(fe)
        db.flush()

    def test_recognize_face_returns_correct_employee(self, client, employee, db):
        """
        Chiến lược: lấy encoding từ ảnh test, lưu vào DB, rồi nhận diện lại
        bằng cùng ảnh đó → phải trả về đúng nhân viên.
        """
        img_b64 = make_test_image_base64(color=(80, 130, 180))

        # Trích xuất encoding từ ảnh test
        true_encoding = extract_face_encoding_from_base64(img_b64)
        self._seed_face_for_employee(db, employee.id, true_encoding)

        # Nhận diện bằng cùng ảnh
        res = _recognize_face(client, img_b64)
        assert res.status_code == 200
        body = res.json()
        assert body["success"] is True
        assert body["data"]["employee_id"] == employee.id
        assert body["data"]["employee_name"] == employee.full_name
        assert body["data"]["employee_code"] == employee.employee_code

    def test_recognize_face_returns_confidence_score(self, client, employee, db):
        img_b64 = make_test_image_base64(color=(90, 140, 190))
        true_encoding = extract_face_encoding_from_base64(img_b64)
        self._seed_face_for_employee(db, employee.id, true_encoding)

        res = _recognize_face(client, img_b64)
        confidence = res.json()["data"]["confidence"]

        assert isinstance(confidence, float)
        # Cùng ảnh → confidence phải rất cao (≥ 0.99)
        assert confidence >= 0.99

    def test_recognize_face_404_when_no_encodings_in_db(self, client):
        """Hệ thống chưa có encoding nào → 404."""
        img_b64 = make_test_image_base64()
        res = _recognize_face(client, img_b64)
        assert res.status_code == 404

    def test_recognize_face_403_for_inactive_employee(self, client, inactive_employee, db):
        """Nhân viên bị vô hiệu hóa → 403 dù encoding khớp."""
        img_b64 = make_test_image_base64(color=(50, 100, 150))
        encoding = extract_face_encoding_from_base64(img_b64)
        self._seed_face_for_employee(db, inactive_employee.id, encoding)

        res = _recognize_face(client, img_b64)
        assert res.status_code == 403

    def test_recognize_face_400_for_invalid_base64(self, client, employee, db):
        img_b64 = make_test_image_base64()
        true_encoding = extract_face_encoding_from_base64(img_b64)
        self._seed_face_for_employee(db, employee.id, true_encoding)

        res = _recognize_face(client, "INVALID_BASE64!!!")
        assert res.status_code == 400

    def test_recognize_face_data_uri_prefix_accepted(self, client, employee, db):
        """Ảnh base64 có tiền tố 'data:image/jpeg;base64,' vẫn được nhận diện đúng."""
        img_b64 = make_test_image_base64(color=(60, 110, 160))
        true_encoding = extract_face_encoding_from_base64(img_b64)
        self._seed_face_for_employee(db, employee.id, true_encoding)

        img_with_prefix = f"data:image/jpeg;base64,{img_b64}"
        res = _recognize_face(client, img_with_prefix)
        assert res.status_code == 200
        assert res.json()["data"]["employee_id"] == employee.id

    def test_recognize_face_selects_best_match_among_multiple(self, client, db):
        """Khi có nhiều nhân viên, phải chọn đúng người có encoding khớp nhất."""
        from app.models.employee import Employee

        # Tạo 3 nhân viên với 3 ảnh khác nhau
        emps = []
        for i in range(1, 4):
            emp = Employee(
                employee_code=f"MULTI{i:03d}",
                full_name=f"Multi Employee {i}",
                email=f"multi{i}@test.com",
                status="active",
            )
            db.add(emp)
            db.flush()
            emps.append(emp)

        images = [
            make_test_image_base64(color=(i * 40, i * 50, i * 60))
            for i in range(1, 4)
        ]

        # Lưu encoding của từng nhân viên
        for emp, img in zip(emps, images):
            enc = extract_face_encoding_from_base64(img)
            self._seed_face_for_employee(db, emp.id, enc)

        # Nhận diện bằng ảnh của nhân viên thứ 2
        res = _recognize_face(client, images[1])
        assert res.status_code == 200
        assert res.json()["data"]["employee_id"] == emps[1].id
