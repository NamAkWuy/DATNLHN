"""
Shared pytest fixtures for backend tests.

Sets DATABASE_URL to a temporary SQLite file BEFORE any app imports,
so pydantic-settings picks up the test value at module load time.
"""
import os
import base64
import json
from io import BytesIO

# ── Must be set BEFORE any `app.*` imports ──────────────────────────────────
os.environ["DATABASE_URL"] = "sqlite:///./test_attendance.db"
os.environ["SECRET_KEY"] = "test-secret-key-for-testing-only"
# ────────────────────────────────────────────────────────────────────────────

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient
from passlib.context import CryptContext

TEST_DB_URL = "sqlite:///./test_attendance.db"
test_engine = create_engine(TEST_DB_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


# ---------------------------------------------------------------------------
# Database lifecycle – once per session
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session", autouse=True)
def setup_database():
    """Create all tables once; drop them after the whole session."""
    from app.database import Base
    # Import models so they register with Base.metadata
    import app.models.department      # noqa: F401
    import app.models.employee        # noqa: F401
    import app.models.user            # noqa: F401
    import app.models.face_encoding   # noqa: F401
    import app.models.rfid_card       # noqa: F401
    import app.models.attendance_log  # noqa: F401
    import app.models.leave_request   # noqa: F401

    Base.metadata.create_all(bind=test_engine)
    yield
    Base.metadata.drop_all(bind=test_engine)
    test_engine.dispose()  # release file handles before deletion (Windows)
    import time
    time.sleep(0.2)
    if os.path.exists("./test_attendance.db"):
        try:
            os.remove("./test_attendance.db")
        except PermissionError:
            pass  # ignore on Windows if a process still holds the file


# ---------------------------------------------------------------------------
# Per-test DB session with rollback isolation
# ---------------------------------------------------------------------------

@pytest.fixture
def db(setup_database):
    """
    Provide a transactional DB session that is rolled back after each test,
    keeping the DB clean without expensive re-creation.
    """
    connection = test_engine.connect()
    transaction = connection.begin()
    session = TestingSessionLocal(bind=connection)
    yield session
    session.close()
    transaction.rollback()
    connection.close()


# ---------------------------------------------------------------------------
# Model factories used by multiple test modules
# ---------------------------------------------------------------------------

@pytest.fixture
def admin_user(db):
    from app.models.user import User

    user = User(
        username="test_admin",
        password_hash=pwd_context.hash("admin123"),
        role="admin",
        failed_attempts=0,
    )
    db.add(user)
    db.flush()
    return user


@pytest.fixture
def employee(db):
    from app.models.employee import Employee

    emp = Employee(
        employee_code="TEST001",
        full_name="Nguyen Van Test",
        email="test001@test.com",
        status="active",
    )
    db.add(emp)
    db.flush()
    return emp


@pytest.fixture
def inactive_employee(db):
    from app.models.employee import Employee

    emp = Employee(
        employee_code="TEST002",
        full_name="Inactive User",
        email="inactive@test.com",
        status="inactive",
    )
    db.add(emp)
    db.flush()
    return emp


# ---------------------------------------------------------------------------
# TestClient with dependency overrides
# ---------------------------------------------------------------------------

@pytest.fixture
def client(db, admin_user):
    """
    FastAPI TestClient with:
    - get_db overridden to use the test session
    - get_current_admin / get_current_user bypassed (returns admin_user)
    """
    from app.main import app
    from app.database import get_db
    from app.api.deps import get_current_admin, get_current_user

    def override_get_db():
        yield db

    def override_admin():
        return admin_user

    def override_user():
        return admin_user

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_admin] = override_admin
    app.dependency_overrides[get_current_user] = override_user

    # Do NOT use the context manager form — lifespan would run seed and
    # interfere with rollback isolation.
    test_client = TestClient(app, raise_server_exceptions=True)
    yield test_client

    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Helper: minimal valid JPEG as base64
# ---------------------------------------------------------------------------

def make_test_image_base64(width: int = 10, height: int = 10,
                            color: tuple = (120, 160, 200)) -> str:
    """
    Return a small solid-color BMP encoded as a base64 string.

    BMP is used instead of JPEG because JPEG headers are identical across
    different solid colors (pixel data appears after byte 64), causing the
    mock face encoder (seeded by sum of first 64 bytes) to return the same
    embedding for every color.  BMP embeds pixel data starting at byte 54,
    so different colors yield different seeds and thus different embeddings.
    """
    try:
        from PIL import Image
        img = Image.new("RGB", (width, height), color=color)
        buf = BytesIO()
        img.save(buf, format="BMP")
        return base64.b64encode(buf.getvalue()).decode("utf-8")
    except ImportError:
        # Fallback: raw bytes unique per color (readable by cv2.imdecode via BMP)
        r, g, b = color
        return base64.b64encode(bytes([r, g, b] * 24)).decode("utf-8")
