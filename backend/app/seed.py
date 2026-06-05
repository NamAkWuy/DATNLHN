"""
Database seeder: populates demo data idempotently.

Hành vi:
- KHÔNG xoá data có sẵn.
- Mỗi entity được kiểm tra theo unique key trước khi insert,
  nên seeder có thể chạy lại nhiều lần mà không tạo bản sao.
- Với attendance history: chỉ thêm bản ghi cho ngày NV chưa có log.
- Với đơn từ / thông báo (không có unique key tự nhiên): dùng sự tồn tại
  của phòng ban "Marketing" làm marker đã-seed-extra.
"""
import random
import logging
from datetime import datetime, date, timedelta, timezone

from sqlalchemy.orm import Session
from passlib.context import CryptContext

logger = logging.getLogger(__name__)
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def _dt(d: date, hour: int, minute: int) -> datetime:
    return datetime(d.year, d.month, d.day, hour, minute, 0, tzinfo=timezone.utc)


# Marker phòng ban: nếu Marketing đã tồn tại → coi như extra đơn từ + thông báo đã seed
EXTRA_MARKER_DEPT = "Marketing"


def run_seed(db: Session) -> None:
    from app.models.department import Department
    from app.models.employee import Employee
    from app.models.user import User
    from app.models.rfid_card import RFIDCard
    from app.models.attendance_log import AttendanceLog
    from app.models.leave_request import LeaveRequest
    from app.models.notification import Notification

    logger.info("Running database seed v2 (additive mode)...")
    rng = random.Random(42)

    extra_already_seeded = (
        db.query(Department).filter(Department.name == EXTRA_MARKER_DEPT).first() is not None
    )

    # -------------------------------------------------------------------------
    # 1. Phòng ban
    # -------------------------------------------------------------------------
    dept_names = ["Kỹ thuật", "Nhân sự", "Kinh doanh", "Kế toán", "Marketing"]
    depts: dict[str, Department] = {}
    new_dept_count = 0
    for name in dept_names:
        d = db.query(Department).filter(Department.name == name).first()
        if d is None:
            d = Department(name=name)
            db.add(d)
            db.flush()
            new_dept_count += 1
        depts[name] = d

    # -------------------------------------------------------------------------
    # 2. Admin employee + user (idempotent theo employee_code / username)
    # -------------------------------------------------------------------------
    admin_emp = _ensure_employee(
        db, Employee,
        code="EMP001", full_name="Lê Hoài Nam",
        email="lehoainam@company.com", phone="0901234567",
        position="Trưởng phòng Kỹ thuật",
        department_id=depts["Kỹ thuật"].id,
    )
    admin_user = _ensure_user(
        db, User,
        employee_id=admin_emp.id,
        username="admin",
        password_hash=pwd_context.hash("admin123"),
        role="admin",
    )

    # -------------------------------------------------------------------------
    # 3. Danh sách nhân viên gốc + mở rộng
    # -------------------------------------------------------------------------
    core_employees = [
        {"code": "EMP002", "full_name": "Nguyễn Thị Hương",
         "email": "nthuong@company.com", "phone": "0912345678",
         "position": "Nhân viên HR", "dept": "Nhân sự", "username": "nthuong"},
        {"code": "EMP003", "full_name": "Trần Văn Minh",
         "email": "tvminh@company.com", "phone": "0923456789",
         "position": "Kỹ sư phần mềm", "dept": "Kỹ thuật", "username": "tvminh"},
        {"code": "EMP004", "full_name": "Phạm Thị Lan",
         "email": "ptlan@company.com", "phone": "0934567890",
         "position": "Nhân viên Kinh doanh", "dept": "Kinh doanh", "username": "ptlan"},
        {"code": "EMP005", "full_name": "Hoàng Văn Đức",
         "email": "hvduc@company.com", "phone": "0945678901",
         "position": "Kỹ sư DevOps", "dept": "Kỹ thuật", "username": "hvduc"},
        {"code": "EMP006", "full_name": "Vũ Thị Mai",
         "email": "vtmai@company.com", "phone": "0956789012",
         "position": "Trưởng phòng Kinh doanh", "dept": "Kinh doanh", "username": "vtmai"},
    ]
    extra_employees = [
        {"code": "EMP007", "full_name": "Đặng Quốc Anh",
         "email": "dqanh@company.com", "phone": "0967890123",
         "position": "Kỹ sư Backend", "dept": "Kỹ thuật", "username": "dqanh"},
        {"code": "EMP008", "full_name": "Bùi Thị Thu",
         "email": "btthu@company.com", "phone": "0978901234",
         "position": "Kỹ sư Frontend", "dept": "Kỹ thuật", "username": "btthu"},
        {"code": "EMP009", "full_name": "Lý Thanh Tùng",
         "email": "lttung@company.com", "phone": "0989012345",
         "position": "Nhân viên Kế toán", "dept": "Kế toán", "username": "lttung"},
        {"code": "EMP010", "full_name": "Ngô Thị Hồng",
         "email": "nthong@company.com", "phone": "0990123456",
         "position": "Trưởng phòng Kế toán", "dept": "Kế toán", "username": "nthong"},
        {"code": "EMP011", "full_name": "Đỗ Minh Quân",
         "email": "dmquan@company.com", "phone": "0901234561",
         "position": "Chuyên viên Marketing", "dept": "Marketing", "username": "dmquan"},
        {"code": "EMP012", "full_name": "Phan Thị Linh",
         "email": "ptlinh@company.com", "phone": "0902345672",
         "position": "Trưởng phòng Marketing", "dept": "Marketing", "username": "ptlinh"},
        {"code": "EMP013", "full_name": "Lê Văn Phong",
         "email": "lvphong@company.com", "phone": "0903456783",
         "position": "Nhân viên Kinh doanh", "dept": "Kinh doanh", "username": "lvphong"},
        {"code": "EMP014", "full_name": "Trịnh Thị Yến",
         "email": "ttyen@company.com", "phone": "0904567894",
         "position": "Trưởng phòng Nhân sự", "dept": "Nhân sự", "username": "ttyen"},
        {"code": "EMP015", "full_name": "Hồ Quang Huy",
         "email": "hqhuy@company.com", "phone": "0905678905",
         "position": "Chuyên viên Tuyển dụng", "dept": "Nhân sự", "username": "hqhuy"},
        {"code": "EMP016", "full_name": "Mai Thị Hà",
         "email": "mtha@company.com", "phone": "0906789016",
         "position": "Nhân viên Kế toán", "dept": "Kế toán", "username": "mtha"},
    ]

    emp_objects: list[Employee] = [admin_emp]
    user_by_emp: dict[int, User] = {admin_emp.id: admin_user}
    new_emp_count = 0
    for data in core_employees + extra_employees:
        before = db.query(Employee).filter(Employee.employee_code == data["code"]).first() is not None
        emp = _ensure_employee(
            db, Employee,
            code=data["code"], full_name=data["full_name"],
            email=data["email"], phone=data["phone"],
            position=data["position"],
            department_id=depts[data["dept"]].id,
        )
        if not before:
            new_emp_count += 1
        u = _ensure_user(
            db, User,
            employee_id=emp.id,
            username=data["username"],
            password_hash=pwd_context.hash("123456"),
            role="employee",
        )
        emp_objects.append(emp)
        user_by_emp[emp.id] = u

    # -------------------------------------------------------------------------
    # 4. RFID — phát thẻ cho NV nào chưa có thẻ active
    # -------------------------------------------------------------------------
    new_rfid_count = 0
    for idx, emp in enumerate(emp_objects, start=1):
        existing = db.query(RFIDCard).filter(RFIDCard.employee_id == emp.id).first()
        if existing is not None:
            continue
        db.add(RFIDCard(
            uid=f"RFID-{idx:04d}-{rng.randint(0x1000, 0xFFFF):04X}",
            employee_id=emp.id,
            status="active",
            assigned_at=datetime.now(timezone.utc) - timedelta(days=rng.randint(30, 180)),
        ))
        new_rfid_count += 1
    db.flush()

    # -------------------------------------------------------------------------
    # 5. Chấm công 30 ngày — chỉ ngày làm việc, skip ngày đã có log
    # -------------------------------------------------------------------------
    today = datetime.now(timezone.utc).date()
    methods = ["face", "face", "face", "rfid", "rfid", "manual"]
    new_log_count = 0

    for emp in emp_objects:
        # Lấy danh sách ngày NV này đã có log trong 31 ngày gần đây
        existing_dates = {
            r[0] for r in db.query(AttendanceLog.date).filter(
                AttendanceLog.employee_id == emp.id,
                AttendanceLog.date >= today - timedelta(days=31),
            ).all()
        }

        for days_back in range(30, 0, -1):
            d = today - timedelta(days=days_back)
            if d.weekday() >= 5 or d in existing_dates:
                continue
            roll = rng.random()
            if roll < 0.05:
                continue  # nghỉ
            if roll < 0.15:
                ci = _dt(d, rng.randint(9, 10), rng.randint(0, 59))
            else:
                ci = _dt(d, rng.choice([7, 8]),
                         rng.randint(20, 59) if rng.random() > 0.5 else rng.randint(0, 30))
            if roll < 0.10:
                co = _dt(d, rng.randint(15, 16), rng.randint(0, 59))
            else:
                co = _dt(d, rng.randint(17, 18), rng.randint(0, 59))
            db.add(AttendanceLog(
                employee_id=emp.id, check_in=ci, check_out=co,
                method=rng.choice(methods), date=d,
            ))
            new_log_count += 1

        # Hôm nay: chỉ check-in (ngày làm việc, chưa có log)
        if today.weekday() < 5 and today not in existing_dates:
            db.add(AttendanceLog(
                employee_id=emp.id,
                check_in=_dt(today, rng.choice([7, 8]), rng.randint(0, 59)),
                check_out=None,
                method=rng.choice(["face", "rfid"]),
                date=today,
            ))
            new_log_count += 1

    db.flush()

    # -------------------------------------------------------------------------
    # 6. Đơn từ + thông báo — chỉ chạy 1 lần (dùng EXTRA_MARKER_DEPT làm khoá)
    # -------------------------------------------------------------------------
    new_request_count = 0
    new_notif_count = 0

    if not extra_already_seeded:
        new_request_count, new_notif_count = _seed_requests_and_notifications(
            db, emp_objects, user_by_emp, admin_user, today, rng,
            LeaveRequest=LeaveRequest, Notification=Notification,
        )

    db.commit()
    logger.info(
        "Seed done. New: %d depts, %d employees, %d RFID, %d attendance, %d requests, %d notifications.",
        new_dept_count, new_emp_count, new_rfid_count,
        new_log_count, new_request_count, new_notif_count,
    )
    logger.info("=== Default accounts ===")
    logger.info("  Admin: username=admin, password=admin123")
    logger.info("  Employees: password=123456")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _ensure_employee(db, Employee, *, code, full_name, email, phone,
                     position, department_id):
    emp = db.query(Employee).filter(Employee.employee_code == code).first()
    if emp is None:
        emp = Employee(
            employee_code=code, full_name=full_name, email=email,
            phone=phone, position=position, department_id=department_id,
            status="active",
        )
        db.add(emp)
        db.flush()
    return emp


def _ensure_user(db, User, *, employee_id, username, password_hash, role):
    u = db.query(User).filter(User.username == username).first()
    if u is None:
        u = User(
            employee_id=employee_id, username=username,
            password_hash=password_hash, role=role,
        )
        db.add(u)
        db.flush()
    return u


def _seed_requests_and_notifications(
    db, emp_objects, user_by_emp, admin_user, today, rng,
    *, LeaveRequest, Notification,
):
    leave_types = ["nghi_phep", "di_muon", "ve_som", "cong_tac", "khac"]
    type_reasons = {
        "nghi_phep": ["Nghỉ phép cá nhân", "Việc gia đình", "Nghỉ ốm",
                      "Đám cưới người thân", "Đưa con đi khám bệnh"],
        "di_muon": ["Có việc gia đình buổi sáng", "Tắc đường nghiêm trọng",
                    "Đưa con đi học", "Lịch khám sức khỏe định kỳ"],
        "ve_som": ["Đưa con đi khám", "Có việc gia đình", "Đi khám bệnh"],
        "cong_tac": ["Công tác Hà Nội gặp khách hàng",
                     "Công tác TP. HCM hỗ trợ chi nhánh",
                     "Đào tạo nội bộ tại trụ sở chính"],
        "khac": ["Tham dự hội thảo chuyên ngành", "Xin phép tham dự lễ tang"],
    }
    reject_reasons = [
        "Trùng lịch họp quan trọng, cần sắp xếp lại",
        "Đã hết số ngày phép trong tháng",
        "Không đủ thông tin chi tiết, vui lòng bổ sung",
    ]

    requests_to_seed = []
    non_admin = emp_objects[1:]

    def _add(status: str, count: int, *, future_only=False, past_only=False):
        for _ in range(count):
            emp = rng.choice(non_admin)
            t = rng.choice(leave_types)
            if future_only:
                offset = rng.randint(1, 14)
            elif past_only:
                offset = rng.randint(-20, 0)
            else:
                offset = rng.randint(-25, 10)
            start_date = today + timedelta(days=offset)
            sdt = _dt(start_date, rng.randint(8, 14), 0)
            edt = sdt + timedelta(hours=rng.choice([2, 4, 8]))
            req = LeaveRequest(
                employee_id=emp.id, type=t,
                start_datetime=sdt, end_datetime=edt,
                reason=rng.choice(type_reasons[t]),
                status=status,
            )
            if status == "tu_choi":
                req.reject_reason = rng.choice(reject_reasons)
                req.reviewed_by = admin_user.id
                req.reviewed_at = sdt - timedelta(days=rng.randint(1, 3))
            elif status == "da_duyet":
                req.reviewed_by = admin_user.id
                req.reviewed_at = sdt - timedelta(days=rng.randint(1, 3))
            requests_to_seed.append(req)

    _add("da_duyet", 12)
    _add("tu_choi", 5)
    _add("cho_duyet", 4, future_only=True)
    _add("da_huy", 2)

    db.add_all(requests_to_seed)
    db.flush()

    notifications_to_seed = []
    for req in requests_to_seed:
        target_user = user_by_emp.get(req.employee_id)
        if not target_user:
            continue
        if req.status == "da_duyet":
            notifications_to_seed.append(Notification(
                user_id=target_user.id, type="don_duyet",
                title="Đơn từ đã được duyệt",
                message=(
                    f"Đơn {req.type.replace('_', ' ')} của bạn từ "
                    f"{req.start_datetime.strftime('%d/%m/%Y %H:%M')} "
                    f"đến {req.end_datetime.strftime('%d/%m/%Y %H:%M')} đã được duyệt."
                ),
                link="/employee/requests",
                is_read=rng.random() < 0.6,
            ))
        elif req.status == "tu_choi":
            notifications_to_seed.append(Notification(
                user_id=target_user.id, type="don_tu_choi",
                title="Đơn từ bị từ chối",
                message=(
                    f"Đơn {req.type.replace('_', ' ')} của bạn đã bị từ chối. "
                    f"Lý do: {req.reject_reason}"
                ),
                link="/employee/requests",
                is_read=rng.random() < 0.5,
            ))
        elif req.status == "cho_duyet":
            notifications_to_seed.append(Notification(
                user_id=admin_user.id, type="khac",
                title="Có đơn từ mới chờ duyệt",
                message=f"Nhân viên gửi đơn {req.type.replace('_', ' ')} cần được duyệt.",
                link="/admin/requests",
                is_read=False,
            ))

    for emp in rng.sample(non_admin, k=min(3, len(non_admin))):
        u = user_by_emp.get(emp.id)
        if not u:
            continue
        notifications_to_seed.append(Notification(
            user_id=u.id, type="nhac_cham_cong",
            title="Nhắc nhở chấm công",
            message="Bạn chưa chấm công ra hôm qua. Vui lòng kiểm tra lại.",
            link="/employee/attendance",
            is_read=rng.random() < 0.4,
        ))

    notifications_to_seed.append(Notification(
        user_id=admin_user.id, type="bao_mat",
        title="Đăng nhập từ thiết bị mới",
        message="Tài khoản admin vừa đăng nhập từ một thiết bị chưa được ghi nhận.",
        link="/admin/security",
        is_read=True,
        read_at=datetime.now(timezone.utc) - timedelta(days=2),
    ))
    notifications_to_seed.append(Notification(
        user_id=admin_user.id, type="khac",
        title="Báo cáo chấm công tháng đã sẵn sàng",
        message="Báo cáo tổng hợp chấm công 30 ngày gần nhất đã được tạo.",
        link="/admin/reports",
        is_read=False,
    ))

    db.add_all(notifications_to_seed)
    db.flush()
    return len(requests_to_seed), len(notifications_to_seed)
