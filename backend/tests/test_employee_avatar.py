from app.config import settings


AVATAR_BYTES = b"fake png bytes"


def _use_tmp_upload_dir(tmp_path, monkeypatch):
    upload_dir = tmp_path / "avatars"
    upload_dir.mkdir()
    monkeypatch.setattr(settings, "UPLOAD_DIR", str(upload_dir))
    return upload_dir


def test_upload_avatar_updates_employee_and_writes_file(client, db, employee, tmp_path, monkeypatch):
    upload_dir = _use_tmp_upload_dir(tmp_path, monkeypatch)

    res = client.post(
        f"/api/v1/employees/{employee.id}/avatar",
        files={"file": ("avatar.png", AVATAR_BYTES, "image/png")},
    )

    assert res.status_code == 200
    payload = res.json()
    expected_url = f"/uploads/avatars/emp_{employee.id}.png"
    assert payload["success"] is True
    assert payload["data"]["avatar_url"] == expected_url

    db.refresh(employee)
    assert employee.avatar_url == expected_url
    assert (upload_dir / f"emp_{employee.id}.png").read_bytes() == AVATAR_BYTES


def test_upload_avatar_rejects_non_image_file(client, employee, tmp_path, monkeypatch):
    upload_dir = _use_tmp_upload_dir(tmp_path, monkeypatch)

    res = client.post(
        f"/api/v1/employees/{employee.id}/avatar",
        files={"file": ("avatar.txt", b"not an image", "text/plain")},
    )

    assert res.status_code == 400
    assert list(upload_dir.iterdir()) == []


def test_upload_avatar_returns_404_for_missing_employee(client, tmp_path, monkeypatch):
    _use_tmp_upload_dir(tmp_path, monkeypatch)

    res = client.post(
        "/api/v1/employees/99999/avatar",
        files={"file": ("avatar.png", AVATAR_BYTES, "image/png")},
    )

    assert res.status_code == 404
