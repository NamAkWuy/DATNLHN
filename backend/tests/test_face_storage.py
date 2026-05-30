"""
API integration tests for face registration, status, deletion, and blocked 1:N recognition.

Tests verify:
1. Face encoding được lưu đúng vào DB sau khi đăng ký
2. Cập nhật encoding hoạt động (upsert)
3. Trạng thái has_face trả về đúng
4. Xóa encoding hoạt động đúng
5. Endpoint nhận diện 1:N bị chặn nếu chưa quét RFID
6. Các trường hợp lỗi (nhân viên không tồn tại, inactive, không có encoding)
"""
import json
import random

import pytest
from tests.conftest import make_test_image_base64


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def fake_face_extractor(monkeypatch):
    def _fake_extract_face_encoding_from_base64(image_base64: str):
        if "not_valid" in image_base64 or "INVALID" in image_base64:
            raise ValueError("Invalid base64 image")

        rng = random.Random(image_base64)
        values = [rng.uniform(-1.0, 1.0) for _ in range(128)]
        norm = sum(v * v for v in values) ** 0.5
        return [v / norm for v in values]

    monkeypatch.setattr(
        "app.api.face.extract_face_encoding_from_base64",
        _fake_extract_face_encoding_from_base64,
    )


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
        payload = json.loads(fe.encoding_data)
        encoding_list = payload["encoding"] if isinstance(payload, dict) else payload
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
        if isinstance(enc1, dict):
            enc1 = enc1["encoding"]

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
        if isinstance(enc2, dict):
            enc2 = enc2["encoding"]
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
    def test_recognize_face_without_rfid_is_blocked(self, client):
        img_b64 = make_test_image_base64()
        res = _recognize_face(client, img_b64)

        assert res.status_code == 403
        assert "RFID" in res.json()["detail"]

    def test_recognize_face_invalid_image_is_still_blocked(self, client):
        res = _recognize_face(client, "INVALID_BASE64!!!")

        assert res.status_code == 403
        assert "RFID" in res.json()["detail"]
