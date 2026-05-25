from datetime import datetime

from app.models.leave_request import LeaveRequest


def _make_leave_request(db, employee, status="cho_duyet"):
    req = LeaveRequest(
        employee_id=employee.id,
        type="nghi_phep",
        start_datetime=datetime(2026, 5, 15, 8, 0, 0),
        end_datetime=datetime(2026, 5, 15, 17, 0, 0),
        reason="Viec ca nhan",
        status=status,
    )
    db.add(req)
    db.flush()
    return req


def test_reject_leave_request_with_reason(client, db, employee, admin_user):
    req = _make_leave_request(db, employee)

    res = client.put(
        f"/api/v1/requests/{req.id}/reject",
        json={"reason": "Khong duoc chap thuan"},
    )

    assert res.status_code == 200
    payload = res.json()
    assert payload["success"] is True
    assert payload["data"]["status"] == "tu_choi"
    assert payload["data"]["reject_reason"] == "Khong duoc chap thuan"
    assert payload["data"]["reviewed_by"] == admin_user.id
    assert payload["data"]["reviewed_at"] is not None

    db.refresh(req)
    assert req.status == "tu_choi"
    assert req.reject_reason == "Khong duoc chap thuan"
    assert req.reviewed_by == admin_user.id


def test_reject_leave_request_accepts_legacy_reject_reason(client, db, employee):
    req = _make_leave_request(db, employee)

    res = client.put(
        f"/api/v1/requests/{req.id}/reject",
        json={"reject_reason": "Trung lich lam viec"},
    )

    assert res.status_code == 200
    assert res.json()["data"]["reject_reason"] == "Trung lich lam viec"


def test_reject_leave_request_requires_pending_status(client, db, employee):
    req = _make_leave_request(db, employee, status="da_duyet")

    res = client.put(
        f"/api/v1/requests/{req.id}/reject",
        json={"reason": "Khong duoc chap thuan"},
    )

    assert res.status_code == 400
    assert req.status == "da_duyet"
