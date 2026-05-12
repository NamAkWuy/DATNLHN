"""
Unit tests for kiosk/api_client.py

Tests cover:
- frame_to_base64: chuyển frame OpenCV sang chuỗi base64 JPEG
- recognize_face: HTTP 200 thành công → dict, thất bại → None
- checkin_attendance: HTTP 200 → dict, thất bại → None
- scan_rfid_card: HTTP 200 → dict, thất bại → None

Dùng unittest.mock để giả lập httpx và cv2 (không cần camera hoặc backend thật).
"""
import sys
import os
import base64
import json
from unittest.mock import MagicMock, patch, call

import pytest
import numpy as np

# Thêm thư mục kiosk vào sys.path để import được các module kiosk
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_bgr_frame(height: int = 50, width: int = 50) -> np.ndarray:
    """Tạo frame giả dạng mảng numpy BGR."""
    return np.zeros((height, width, 3), dtype=np.uint8)


def _mock_httpx_response(status_code: int, json_data: dict) -> MagicMock:
    """Tạo mock httpx.Response."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data
    resp.text = json.dumps(json_data)
    return resp


# ---------------------------------------------------------------------------
# Tests: frame_to_base64
# ---------------------------------------------------------------------------

class TestFrameToBase64:
    def test_returns_non_empty_string(self):
        import cv2
        with patch("cv2.imencode") as mock_encode:
            fake_buffer = np.array([0xFF, 0xD8, 0xFF], dtype=np.uint8)
            mock_encode.return_value = (True, fake_buffer)

            import api_client
            frame = _make_bgr_frame()
            result = api_client.frame_to_base64(frame)

            assert isinstance(result, str)
            assert len(result) > 0

    def test_output_is_valid_base64(self):
        import cv2
        raw_bytes = b"\xff\xd8\xff\xe0test_bytes"
        fake_buffer = np.frombuffer(raw_bytes, dtype=np.uint8)

        with patch("cv2.imencode", return_value=(True, fake_buffer)):
            import api_client
            result = api_client.frame_to_base64(_make_bgr_frame())

        # Phải decode được không lỗi
        decoded = base64.b64decode(result)
        assert decoded == raw_bytes

    def test_uses_jpeg_encoding(self):
        """frame_to_base64 phải gọi cv2.imencode với đuôi '.jpg'."""
        import cv2
        fake_buffer = np.zeros(10, dtype=np.uint8)

        with patch("cv2.imencode", return_value=(True, fake_buffer)) as mock_enc:
            import api_client
            api_client.frame_to_base64(_make_bgr_frame())
            args = mock_enc.call_args[0]
            assert args[0] == ".jpg"

    def test_jpeg_quality_set_to_85(self):
        """Tham số quality phải = 85 (đã chuẩn hóa trong api_client)."""
        import cv2
        fake_buffer = np.zeros(10, dtype=np.uint8)

        with patch("cv2.imencode", return_value=(True, fake_buffer)) as mock_enc:
            import api_client
            api_client.frame_to_base64(_make_bgr_frame())
            kwargs = mock_enc.call_args
            # Danh sách params chứa [cv2.IMWRITE_JPEG_QUALITY, 85]
            call_args = kwargs[0] if kwargs[0] else []
            call_kwargs = kwargs[1] if kwargs[1] else {}
            params = call_args[2] if len(call_args) > 2 else call_kwargs.get("params", [])
            # Tìm giá trị quality 85 trong tham số
            assert 85 in params


# ---------------------------------------------------------------------------
# Tests: recognize_face
# ---------------------------------------------------------------------------

class TestRecognizeFace:
    @patch("api_client._client.post")
    def test_success_returns_employee_dict(self, mock_post):
        employee_data = {
            "employee_id": 5,
            "employee_name": "Nguyen Van A",
            "employee_code": "EMP005",
            "confidence": 0.95,
        }
        mock_resp = _mock_httpx_response(200, {"success": True, "data": employee_data})
        mock_post.return_value = mock_resp

        import cv2
        fake_buffer = np.zeros(10, dtype=np.uint8)
        with patch("cv2.imencode", return_value=(True, fake_buffer)):
            import api_client
            result = api_client.recognize_face(_make_bgr_frame())

        assert result is not None
        assert result["employee_id"] == 5
        assert result["employee_name"] == "Nguyen Van A"
        assert result["employee_code"] == "EMP005"
        assert result["confidence"] == 0.95

    @patch("api_client._client.post")
    def test_404_response_returns_none(self, mock_post):
        mock_resp = _mock_httpx_response(404, {"success": False, "message": "Not found"})
        mock_post.return_value = mock_resp

        import cv2
        fake_buffer = np.zeros(10, dtype=np.uint8)
        with patch("cv2.imencode", return_value=(True, fake_buffer)):
            import api_client
            result = api_client.recognize_face(_make_bgr_frame())

        assert result is None

    @patch("api_client._client.post")
    def test_success_false_in_response_returns_none(self, mock_post):
        """HTTP 200 nhưng success=False → trả về None."""
        mock_resp = _mock_httpx_response(200, {"success": False, "data": None})
        mock_post.return_value = mock_resp

        import cv2
        fake_buffer = np.zeros(10, dtype=np.uint8)
        with patch("cv2.imencode", return_value=(True, fake_buffer)):
            import api_client
            result = api_client.recognize_face(_make_bgr_frame())

        assert result is None

    @patch("api_client._client.post")
    def test_network_exception_returns_none(self, mock_post):
        """Lỗi mạng / exception → trả về None, không raise."""
        mock_post.side_effect = Exception(
            "Connection refused"
        )

        import cv2
        fake_buffer = np.zeros(10, dtype=np.uint8)
        with patch("cv2.imencode", return_value=(True, fake_buffer)):
            import api_client
            result = api_client.recognize_face(_make_bgr_frame())

        assert result is None

    @patch("api_client._client.post")
    def test_posts_to_correct_endpoint(self, mock_post):
        """Phải POST đến /face/recognize."""
        mock_resp = _mock_httpx_response(404, {"success": False})
        mock_post.return_value = mock_resp

        import cv2
        fake_buffer = np.zeros(10, dtype=np.uint8)
        with patch("cv2.imencode", return_value=(True, fake_buffer)):
            import api_client
            api_client.recognize_face(_make_bgr_frame())

        call_args = mock_post.call_args
        url = call_args[0][0] if call_args[0] else call_args[1].get("url", "")
        assert "/face/recognize" in url

    @patch("api_client._client.post")
    def test_sends_image_base64_in_payload(self, mock_post):
        """Payload phải chứa key 'image_base64'."""
        mock_resp = _mock_httpx_response(404, {"success": False})
        mock_post.return_value = mock_resp

        import cv2
        fake_buffer = np.zeros(10, dtype=np.uint8)
        with patch("cv2.imencode", return_value=(True, fake_buffer)):
            import api_client
            api_client.recognize_face(_make_bgr_frame())

        call_kwargs = mock_post.call_args[1]
        json_payload = call_kwargs.get("json", {})
        assert "image_base64" in json_payload


# ---------------------------------------------------------------------------
# Tests: checkin_attendance
# ---------------------------------------------------------------------------

class TestCheckinAttendance:
    @patch("api_client._client.post")
    def test_success_returns_data_dict(self, mock_post):
        attendance_data = {
            "action": "check_in",
            "log": {
                "id": 1,
                "employee_id": 3,
                "check_in": "2025-01-01T08:00:00",
                "check_out": None,
                "method": "face",
                "date": "2025-01-01",
            },
        }
        mock_resp = _mock_httpx_response(200, {"success": True, "data": attendance_data})
        mock_post.return_value = mock_resp

        import api_client
        result = api_client.checkin_attendance(employee_id=3, method="face")

        assert result is not None
        assert result["action"] == "check_in"
        assert result["log"]["employee_id"] == 3

    @patch("api_client._client.post")
    def test_checkout_returns_data_dict(self, mock_post):
        attendance_data = {
            "action": "check_out",
            "log": {"id": 1, "employee_id": 3, "check_out": "2025-01-01T17:00:00"},
        }
        mock_resp = _mock_httpx_response(200, {"success": True, "data": attendance_data})
        mock_post.return_value = mock_resp

        import api_client
        result = api_client.checkin_attendance(employee_id=3, method="face")

        assert result["action"] == "check_out"

    @patch("api_client._client.post")
    def test_400_response_returns_already_checked_out(self, mock_post):
        """HTTP 400 → checkin_attendance trả về dict báo đã chấm ra rồi."""
        mock_resp = _mock_httpx_response(400, {"detail": "Already checked out"})
        mock_post.return_value = mock_resp

        import api_client
        result = api_client.checkin_attendance(employee_id=3)

        assert result == {"error": "already_checked_out"}

    @patch("api_client._client.post")
    def test_exception_returns_none(self, mock_post):
        mock_post.side_effect = Exception(
            "Timeout"
        )

        import api_client
        result = api_client.checkin_attendance(employee_id=3)

        assert result is None

    @patch("api_client._client.post")
    def test_posts_to_correct_endpoint(self, mock_post):
        mock_resp = _mock_httpx_response(400, {"detail": "error"})
        mock_post.return_value = mock_resp

        import api_client
        api_client.checkin_attendance(employee_id=7)

        url = mock_post.call_args[0][0]
        assert "/attendance/checkin" in url

    @patch("api_client._client.post")
    def test_sends_employee_id_and_method(self, mock_post):
        mock_resp = _mock_httpx_response(400, {"detail": "error"})
        mock_post.return_value = mock_resp

        import api_client
        api_client.checkin_attendance(employee_id=9, method="rfid")

        json_payload = mock_post.call_args[1]["json"]
        assert json_payload["employee_id"] == 9
        assert json_payload["method"] == "rfid"


# ---------------------------------------------------------------------------
# Tests: scan_rfid_card
# ---------------------------------------------------------------------------

class TestScanRFIDCard:
    @patch("api_client._client.post")
    def test_success_returns_employee_dict(self, mock_post):
        rfid_data = {
            "employee_id": 2,
            "employee_name": "Tran Van B",
            "employee_code": "EMP002",
            "card_uid": "CARD-ABC123",
        }
        mock_resp = _mock_httpx_response(200, {"success": True, "data": rfid_data})
        mock_post.return_value = mock_resp

        import api_client
        result = api_client.scan_rfid_card("CARD-ABC123")

        assert result is not None
        assert result["employee_id"] == 2
        assert result["card_uid"] == "CARD-ABC123"

    @patch("api_client._client.post")
    def test_card_not_found_returns_none(self, mock_post):
        mock_resp = _mock_httpx_response(404, {"detail": "Card not found"})
        mock_post.return_value = mock_resp

        import api_client
        result = api_client.scan_rfid_card("UNKNOWN_CARD")

        assert result is None

    @patch("api_client._client.post")
    def test_disabled_card_returns_none(self, mock_post):
        mock_resp = _mock_httpx_response(403, {"detail": "Card disabled"})
        mock_post.return_value = mock_resp

        import api_client
        result = api_client.scan_rfid_card("DISABLED_CARD")

        assert result is None

    @patch("api_client._client.post")
    def test_exception_returns_none(self, mock_post):
        mock_post.side_effect = Exception(
            "Network error"
        )

        import api_client
        result = api_client.scan_rfid_card("ANY_CARD")

        assert result is None

    @patch("api_client._client.post")
    def test_posts_uid_to_correct_endpoint(self, mock_post):
        mock_resp = _mock_httpx_response(404, {"detail": "not found"})
        mock_post.return_value = mock_resp

        import api_client
        api_client.scan_rfid_card("MY_UID_001")

        url = mock_post.call_args[0][0]
        assert "/rfid/scan" in url

        json_payload = mock_post.call_args[1]["json"]
        assert json_payload["uid"] == "MY_UID_001"
