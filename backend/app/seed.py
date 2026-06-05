"""
Database seeder: populates initial demo data.
Only runs when the DB is empty (no departments found).
"""
import random
import logging
from datetime import datetime, date, timedelta, timezone

from sqlalchemy.orm import Session
from passlib.context import CryptContext

logger = logging.getLogger(__name__)
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def run_seed(db: Session) -> None:
    from app.models.department import Department
    from app.models.employee import Employee
    from app.models.user import User
    from app.models.rfid_card import RFIDCard
    from app.models.attendance_log import AttendanceLog
    from app.models.leave_request import LeaveRequest

    # Skip if data exists
    if db.query(Department).first():
        logger.info("Seed skipped: data already exists.")
        return

    logger.info("Running database seed...")

    # -------------------------------------------------------------------------
    # Departments
    # -------------------------------------------------------------------------
    dept_names = ["Kỹ thuật", "Nhân sự", "Kinh doanh"]
    depts = {}
    for name in dept_names:
        d = Department(name=name)
        db.add(d)
        db.flush()
        depts[name] = d

    # -------------------------------------------------------------------------
    # Admin employee + user
    # -------------------------------------------------------------------------
    admin_emp = Employee(
        employee_code="EMP001",
        full_name="Lê Hoài Nam",
        email="lehoainam@company.com",
        phone="0901234567",
        position="Trưởng phòng Kỹ thuật",
        department_id=depts["Kỹ thuật"].id,
        status="active",
    )
    db.add(admin_emp)
    db.flush()

    admin_user = User(
        employee_id=admin_emp.id,
        username="admin",
        password_hash=pwd_context.hash("admin123"),
        role="admin",
    )
    db.add(admin_user)
    db.flush()

    # -------------------------------------------------------------------------
    # Sample employees
    # -------------------------------------------------------------------------
    sample_employees = [
        {
            "code": "EMP002",
            "full_name": "Nguyễn Thị Hương",
            "email": "nthuong@company.com",
            "phone": "0912345678",
            "position": "Nhân viên HR",
            "dept": "Nhân sự",
            "username": "nthuong",
        },
        {
            "code": "EMP003",
            "full_name": "Trần Văn Minh",
            "email": "tvminh@company.com",
            "phone": "0923456789",
            "position": "Kỹ sư phần mềm",
            "dept": "Kỹ thuật",
            "username": "tvminh",
        },
        {
            "code": "EMP004",
            "full_name": "Phạm Thị Lan",
            "email": "ptlan@company.com",
            "phone": "0934567890",
            "position": "Nhân viên Kinh doanh",
            "dept": "Kinh doanh",
            "username": "ptlan",
        },
        {
            "code": "EMP005",
            "full_name": "Hoàng Văn Đức",
            "email": "hvduc@company.com",
            "phone": "0945678901",
            "position": "Kỹ sư DevOps",
            "dept": "Kỹ thuật",
            "username": "hvduc",
        },
        {
            "code": "EMP006",
            "full_name": "Vũ Thị Mai",
            "email": "vtmai@company.com",
            "phone": "0956789012",
            "position": "Trưởng phòng Kinh doanh",
            "dept": "Kinh doanh",
            "username": "vtmai",
        },
    ]

    emp_objects = [admin_emp]
    for data in sample_employees:
        emp = Employee(
            employee_code=data["code"],
            full_name=data["full_name"],
            email=data["email"],
            phone=data["phone"],
            position=data["position"],
            department_id=depts[data["dept"]].id,
            status="active",
        )
        db.add(emp)
        db.flush()

        user = User(
            employee_id=emp.id,
            username=data["username"],
            password_hash=pwd_context.hash("123456"),
            role="employee",
        )
        db.add(user)
        db.flush()
        emp_objects.append(emp)

    # -------------------------------------------------------------------------
    # KHÔNG seed face encoding giả — admin phải đăng ký khuôn mặt thật qua
    # trang "Quản lý Khuôn mặt" (chụp ảnh từ webcam) thì /verify mới có cơ sở so khớp.
    # Encoding seed theo employee_id sẽ không bao giờ khớp với mặt thật → kiosk
    # sẽ luôn từ chối, đúng nghiệp vụ.
    # -------------------------------------------------------------------------
    db.flush()

    # -------------------------------------------------------------------------
    # RFID Cards
    # -------------------------------------------------------------------------
    rfid1 = RFIDCard(
        uid="RFID-A1B2C3D4",
        employee_id=emp_objects[1].id,  # Nguyễn Thị Hương
        status="active",
        assigned_at=datetime.now(timezone.utc),
    )
    rfid2 = RFIDCard(
        uid="RFID-E5F6G7H8",
        employee_id=emp_objects[2].id,  # Trần Văn Minh
        status="active",
        assigned_at=datetime.now(timezone.utc),
    )
    db.add_all([rfid1, rfid2])
    db.flush()

    # -------------------------------------------------------------------------
    # Attendance records: today and yesterday for each employee
    # -------------------------------------------------------------------------
    today = datetime.now(timezone.utc).date()
    yesterday = today - timedelta(days=1)

    for emp in emp_objects:
        # Yesterday: check_in at 08:30-09:10, check_out at 17:00-18:00
        check_in_hour = random.randint(8, 9)
        check_in_min = random.randint(0, 59) if check_in_hour == 8 else random.randint(0, 15)
        check_out_hour = random.randint(17, 18)
        check_out_min = random.randint(0, 59)

        ci_yesterday = datetime(
            yesterday.year, yesterday.month, yesterday.day,
            check_in_hour, check_in_min, 0, tzinfo=timezone.utc
        )
        co_yesterday = datetime(
            yesterday.year, yesterday.month, yesterday.day,
            check_out_hour, check_out_min, 0, tzinfo=timezone.utc
        )
        log_y = AttendanceLog(
            employee_id=emp.id,
            check_in=ci_yesterday,
            check_out=co_yesterday,
            method=random.choice(["face", "rfid", "manual"]),
            date=yesterday,
        )
        db.add(log_y)

        # Today: check_in only (some employees haven't checked out yet)
        check_in_hour_t = random.randint(7, 9)
        check_in_min_t = random.randint(0, 59)
        ci_today = datetime(
            today.year, today.month, today.day,
            check_in_hour_t, check_in_min_t, 0, tzinfo=timezone.utc
        )
        log_t = AttendanceLog(
            employee_id=emp.id,
            check_in=ci_today,
            check_out=None,
            method=random.choice(["face", "rfid"]),
            date=today,
        )
        db.add(log_t)

    db.flush()

    # -------------------------------------------------------------------------
    # Leave requests (pending)
    # -------------------------------------------------------------------------
    tomorrow = today + timedelta(days=1)
    day_after = today + timedelta(days=2)

    lr1 = LeaveRequest(
        employee_id=emp_objects[1].id,
        type="nghi_phep",
        start_datetime=datetime(tomorrow.year, tomorrow.month, tomorrow.day, 8, 0, 0, tzinfo=timezone.utc),
        end_datetime=datetime(tomorrow.year, tomorrow.month, tomorrow.day, 17, 30, 0, tzinfo=timezone.utc),
        reason="Nghỉ phép cá nhân",
        status="cho_duyet",
    )
    lr2 = LeaveRequest(
        employee_id=emp_objects[3].id,
        type="di_muon",
        start_datetime=datetime(tomorrow.year, tomorrow.month, tomorrow.day, 10, 0, 0, tzinfo=timezone.utc),
        end_datetime=datetime(tomorrow.year, tomorrow.month, tomorrow.day, 12, 0, 0, tzinfo=timezone.utc),
        reason="Có việc gia đình buổi sáng",
        status="cho_duyet",
    )
    lr3 = LeaveRequest(
        employee_id=emp_objects[4].id,
        type="ve_som",
        start_datetime=datetime(day_after.year, day_after.month, day_after.day, 15, 0, 0, tzinfo=timezone.utc),
        end_datetime=datetime(day_after.year, day_after.month, day_after.day, 17, 30, 0, tzinfo=timezone.utc),
        reason="Đưa con đi khám",
        status="cho_duyet",
    )
    db.add_all([lr1, lr2, lr3])

    db.commit()
    logger.info("Seed completed successfully.")
    logger.info("=== Default accounts ===")
    logger.info("  Admin: username=admin, password=admin123")
    logger.info("  Employees: password=123456")
    logger.info("  Employee usernames: nthuong, tvminh, ptlan, hvduc, vtmai")
