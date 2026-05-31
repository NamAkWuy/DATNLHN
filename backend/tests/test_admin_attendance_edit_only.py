"""
Verify rằng admin chỉ có thể CHỈNH SỬA bản ghi chấm công,
KHÔNG được xóa (theo yêu cầu của user).
"""
from datetime import datetime, date

from app.models.attendance_log import AttendanceLog


def _seed_log(db, employee_id: int) -> AttendanceLog:
    log = AttendanceLog(
        employee_id=employee_id,
        check_in=datetime(2026, 5, 31, 8, 0, 0),
        check_out=datetime(2026, 5, 31, 17, 0, 0),
        method="manual",
        note="seed",
        date=date(2026, 5, 31),
    )
    db.add(log)
    db.flush()
    return log


class TestAdminAttendanceUpdate:
    def test_update_attendance_returns_200(self, client, employee, db):
        log = _seed_log(db, employee.id)
        res = client.put(
            f"/api/v1/attendance/{log.id}",
            json={"note": "đã sửa", "check_out": "2026-05-31T18:30:00"},
        )
        assert res.status_code == 200, res.text
        body = res.json()
        assert body["data"]["note"] == "đã sửa"
        assert body["data"]["check_out"].startswith("2026-05-31T18:30")

    def test_update_nonexistent_returns_404(self, client):
        res = client.put("/api/v1/attendance/999999", json={"note": "x"})
        assert res.status_code == 404


class TestAdminAttendanceDeleteIsBlocked:
    def test_delete_endpoint_does_not_exist(self, client, employee, db):
        log = _seed_log(db, employee.id)
        res = client.delete(f"/api/v1/attendance/{log.id}")
        # FastAPI returns 405 Method Not Allowed khi route không hỗ trợ DELETE
        assert res.status_code == 405, (
            f"Endpoint xóa chấm công vẫn còn — phải bị gỡ. Status={res.status_code}, body={res.text}"
        )

        # Bản ghi vẫn phải tồn tại trong DB
        still_there = db.query(AttendanceLog).filter(AttendanceLog.id == log.id).first()
        assert still_there is not None, "Bản ghi đã bị xóa — endpoint DELETE chưa được khóa."
