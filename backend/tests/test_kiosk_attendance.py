"""
API integration tests for kiosk attendance flow.

Tests cover:
- Chấm công vào (check-in) lần đầu → tạo bản ghi mới
- Chấm công ra (check-out) lần hai → cập nhật bản ghi hiện có
- Chấm công lần ba → lỗi đã chấm công ra rồi
- Nhân viên inactive → 403
- Nhân viên không tồn tại → 404
- Quét thẻ RFID: thẻ hợp lệ → trả về đúng nhân viên
- Quét thẻ RFID: thẻ bị khóa → 403
- Quét thẻ RFID: thẻ chưa gán → 400
- Quét thẻ RFID: không tìm thấy → 404
- Flow đầy đủ: quét RFID → chấm công vào → chấm công ra
"""
import pytest
from datetime import datetime, timezone, date


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _checkin(client, employee_id: int, method: str = "face"):
    return client.post(
        "/api/v1/attendance/checkin",
        json={"employee_id": employee_id, "method": method},
    )


def _rfid_scan(client, uid: str):
    return client.post(
        "/api/v1/rfid/scan",
        json={"uid": uid},
    )


def _create_rfid_card(db, uid: str, employee_id=None, status: str = "active"):
    from app.models.rfid_card import RFIDCard

    card = RFIDCard(
        uid=uid,
        employee_id=employee_id,
        status=status,
        assigned_at=datetime.now(timezone.utc) if employee_id else None,
    )
    db.add(card)
    db.flush()
    return card


# ---------------------------------------------------------------------------
# Tests: attendance check-in/out via face
# ---------------------------------------------------------------------------

class TestFaceAttendance:
    def test_first_checkin_creates_new_log(self, client, employee, db):
        """Lần đầu quét mặt → tạo bản ghi mới với check_in."""
        from app.models.attendance_log import AttendanceLog

        res = _checkin(client, employee.id, method="face")
        assert res.status_code == 200
        body = res.json()
        assert body["success"] is True
        assert body["data"]["action"] == "check_in"

        # Kiểm tra DB
        log = (
            db.query(AttendanceLog)
            .filter(AttendanceLog.employee_id == employee.id)
            .first()
        )
        assert log is not None
        assert log.check_in is not None
        assert log.check_out is None
        assert log.method == "face"

    def test_second_checkin_becomes_checkout(self, client, employee, db):
        """Lần hai quét mặt cùng ngày → cập nhật check_out."""
        from app.models.attendance_log import AttendanceLog

        _checkin(client, employee.id, method="face")

        res = _checkin(client, employee.id, method="face")
        assert res.status_code == 200
        body = res.json()
        assert body["data"]["action"] == "check_out"
        assert body["data"]["log"]["check_out"] is not None

        # Kiểm tra DB – chỉ có 1 bản ghi hôm nay
        today = datetime.now(timezone.utc).date()
        logs = (
            db.query(AttendanceLog)
            .filter(
                AttendanceLog.employee_id == employee.id,
                AttendanceLog.date == today,
            )
            .all()
        )
        assert len(logs) == 1
        assert logs[0].check_out is not None

    def test_third_checkin_returns_error(self, client, employee):
        """Đã có check_in lẫn check_out → lần thứ ba phải lỗi 400."""
        _checkin(client, employee.id, method="face")
        _checkin(client, employee.id, method="face")

        res = _checkin(client, employee.id, method="face")
        assert res.status_code == 400

    def test_checkin_returns_employee_info_in_log(self, client, employee):
        res = _checkin(client, employee.id, method="face")
        log_data = res.json()["data"]["log"]
        assert log_data["employee_id"] == employee.id
        assert log_data["method"] == "face"

    def test_checkin_stores_correct_date(self, client, employee, db):
        from app.models.attendance_log import AttendanceLog

        _checkin(client, employee.id)
        today = datetime.now(timezone.utc).date()

        log = (
            db.query(AttendanceLog)
            .filter(AttendanceLog.employee_id == employee.id)
            .first()
        )
        # Chuyển đổi date để so sánh (SQLite có thể trả về string)
        log_date = log.date if isinstance(log.date, date) else date.fromisoformat(str(log.date))
        assert log_date == today

    def test_checkin_inactive_employee_returns_403(self, client, inactive_employee):
        res = _checkin(client, inactive_employee.id, method="face")
        assert res.status_code == 403

    def test_checkin_nonexistent_employee_returns_404(self, client):
        res = _checkin(client, 99999, method="face")
        assert res.status_code == 404

    def test_checkin_via_rfid_method_stored_correctly(self, client, employee, db):
        """Phương thức chấm công = 'rfid' phải được lưu đúng."""
        from app.models.attendance_log import AttendanceLog

        res = _checkin(client, employee.id, method="rfid")
        assert res.status_code == 200

        log = (
            db.query(AttendanceLog)
            .filter(AttendanceLog.employee_id == employee.id)
            .first()
        )
        assert log.method == "rfid"

    def test_checkin_via_manual_method(self, client, employee, db):
        from app.models.attendance_log import AttendanceLog

        res = _checkin(client, employee.id, method="manual")
        assert res.status_code == 200

        log = (
            db.query(AttendanceLog)
            .filter(AttendanceLog.employee_id == employee.id)
            .first()
        )
        assert log.method == "manual"


# ---------------------------------------------------------------------------
# Tests: RFID scan endpoint
# ---------------------------------------------------------------------------

class TestRFIDScan:
    def test_rfid_scan_returns_employee_info(self, client, employee, db):
        """Quét thẻ RFID hợp lệ → trả về thông tin nhân viên."""
        _create_rfid_card(db, uid="CARD_VALID_001", employee_id=employee.id)

        res = _rfid_scan(client, "CARD_VALID_001")
        assert res.status_code == 200
        body = res.json()
        assert body["success"] is True
        assert body["data"]["employee_id"] == employee.id
        assert body["data"]["employee_name"] == employee.full_name
        assert body["data"]["employee_code"] == employee.employee_code
        assert body["data"]["card_uid"] == "CARD_VALID_001"

    def test_rfid_scan_disabled_card_returns_403(self, client, employee, db):
        """Thẻ RFID bị khóa → 403."""
        _create_rfid_card(db, uid="CARD_DISABLED_001", employee_id=employee.id, status="disabled")

        res = _rfid_scan(client, "CARD_DISABLED_001")
        assert res.status_code == 403

    def test_rfid_scan_unassigned_card_returns_400(self, client, db):
        """Thẻ RFID chưa gán cho nhân viên nào → 400."""
        _create_rfid_card(db, uid="CARD_UNASSIGNED_001", employee_id=None)

        res = _rfid_scan(client, "CARD_UNASSIGNED_001")
        assert res.status_code == 400

    def test_rfid_scan_nonexistent_card_returns_404(self, client):
        """Thẻ RFID không tồn tại → 404."""
        res = _rfid_scan(client, "CARD_DOES_NOT_EXIST")
        assert res.status_code == 404

    def test_rfid_scan_inactive_employee_returns_403(self, client, inactive_employee, db):
        """Nhân viên inactive dù thẻ active → 403."""
        _create_rfid_card(db, uid="CARD_INACTIVE_EMP", employee_id=inactive_employee.id)

        res = _rfid_scan(client, "CARD_INACTIVE_EMP")
        assert res.status_code == 403


# ---------------------------------------------------------------------------
# Tests: full kiosk flow (RFID scan → check-in → check-out)
# ---------------------------------------------------------------------------

class TestKioskFullFlow:
    def test_rfid_scan_then_checkin_flow(self, client, employee, db):
        """
        Mô phỏng luồng kiosk đầy đủ:
        1. Quét thẻ RFID → lấy employee_id
        2. Chấm công vào bằng employee_id
        3. Chấm công ra (quét lại)
        """
        from app.models.attendance_log import AttendanceLog

        _create_rfid_card(db, uid="KIOSK_CARD_001", employee_id=employee.id)

        # Bước 1: quét thẻ
        scan_res = _rfid_scan(client, "KIOSK_CARD_001")
        assert scan_res.status_code == 200
        emp_id = scan_res.json()["data"]["employee_id"]

        # Bước 2: chấm công vào
        checkin_res = _checkin(client, emp_id, method="rfid")
        assert checkin_res.status_code == 200
        assert checkin_res.json()["data"]["action"] == "check_in"

        # Bước 3: chấm công ra
        checkout_res = _checkin(client, emp_id, method="rfid")
        assert checkout_res.status_code == 200
        assert checkout_res.json()["data"]["action"] == "check_out"

        # Kiểm tra DB
        today = datetime.now(timezone.utc).date()
        log = (
            db.query(AttendanceLog)
            .filter(
                AttendanceLog.employee_id == employee.id,
                AttendanceLog.date == today,
            )
            .first()
        )
        assert log is not None
        assert log.check_in is not None
        assert log.check_out is not None
        assert log.method == "rfid"

    def test_face_then_rfid_checkout_flow(self, client, employee, db):
        """
        Chấm công vào bằng khuôn mặt, ra bằng RFID – phương thức cuối cùng lưu
        theo lần checkin (check-out method không thay đổi method của log).
        """
        from app.models.attendance_log import AttendanceLog

        _create_rfid_card(db, uid="MIXED_CARD_001", employee_id=employee.id)

        # Chấm công vào bằng face
        _checkin(client, employee.id, method="face")

        # Quét thẻ RFID → lấy employee_id
        scan_res = _rfid_scan(client, "MIXED_CARD_001")
        emp_id = scan_res.json()["data"]["employee_id"]

        # Chấm công ra bằng RFID
        checkout_res = _checkin(client, emp_id, method="rfid")
        assert checkout_res.status_code == 200
        assert checkout_res.json()["data"]["action"] == "check_out"

        today = datetime.now(timezone.utc).date()
        log = (
            db.query(AttendanceLog)
            .filter(
                AttendanceLog.employee_id == employee.id,
                AttendanceLog.date == today,
            )
            .first()
        )
        assert log.check_in is not None
        assert log.check_out is not None

    def test_multiple_employees_independent_logs(self, client, db):
        """Hai nhân viên chấm công độc lập → mỗi người có log riêng."""
        from app.models.employee import Employee
        from app.models.attendance_log import AttendanceLog

        emp_a = Employee(
            employee_code="FLOWA001",
            full_name="Flow Employee A",
            email="flowa@test.com",
            status="active",
        )
        emp_b = Employee(
            employee_code="FLOWB001",
            full_name="Flow Employee B",
            email="flowb@test.com",
            status="active",
        )
        db.add_all([emp_a, emp_b])
        db.flush()

        _checkin(client, emp_a.id, method="face")
        _checkin(client, emp_b.id, method="face")

        today = datetime.now(timezone.utc).date()
        log_a = (
            db.query(AttendanceLog)
            .filter(AttendanceLog.employee_id == emp_a.id, AttendanceLog.date == today)
            .first()
        )
        log_b = (
            db.query(AttendanceLog)
            .filter(AttendanceLog.employee_id == emp_b.id, AttendanceLog.date == today)
            .first()
        )
        assert log_a is not None
        assert log_b is not None
        assert log_a.id != log_b.id


# ---------------------------------------------------------------------------
# Tests: RFID card management (admin endpoints)
# ---------------------------------------------------------------------------

class TestRFIDCardManagement:
    def test_create_rfid_card_via_api(self, client, employee):
        """Admin tạo thẻ RFID mới qua API."""
        res = client.post(
            "/api/v1/rfid/",
            json={"uid": "NEW_CARD_API_001", "employee_id": employee.id},
        )
        assert res.status_code == 201
        body = res.json()
        assert body["success"] is True
        assert body["data"]["uid"] == "NEW_CARD_API_001"
        assert body["data"]["employee_id"] == employee.id
        assert body["data"]["status"] == "active"

    def test_create_duplicate_uid_returns_400(self, client, employee):
        client.post(
            "/api/v1/rfid/",
            json={"uid": "DUPE_CARD_001", "employee_id": employee.id},
        )
        res = client.post(
            "/api/v1/rfid/",
            json={"uid": "DUPE_CARD_001", "employee_id": employee.id},
        )
        assert res.status_code == 400

    def test_one_active_card_per_employee(self, client, employee, db):
        """Nhân viên đã có thẻ active → không thể thêm thẻ active thứ hai."""
        _create_rfid_card(db, uid="EXISTING_ACTIVE", employee_id=employee.id)

        res = client.post(
            "/api/v1/rfid/",
            json={"uid": "NEW_ACTIVE_001", "employee_id": employee.id},
        )
        assert res.status_code == 400

    def test_disable_card_via_api(self, client, employee, db):
        card = _create_rfid_card(db, uid="DISABLE_ME_001", employee_id=employee.id)

        res = client.put(
            f"/api/v1/rfid/{card.id}/status",
            json={"status": "disabled"},
        )
        assert res.status_code == 200
        assert res.json()["data"]["status"] == "disabled"

    def test_delete_card_via_api(self, client, employee, db):
        card = _create_rfid_card(db, uid="DELETE_ME_001", employee_id=employee.id)

        res = client.delete(f"/api/v1/rfid/{card.id}")
        assert res.status_code == 200
        assert res.json()["success"] is True
