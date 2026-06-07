-- =============================================================
-- HỆ THỐNG QUẢN LÝ NHÂN SỰ VÀ CHẤM CÔNG NHẬN DIỆN KHUÔN MẶT
-- MySQL Schema - utf8mb4 (hỗ trợ tiếng Việt đầy đủ)
-- =============================================================

CREATE DATABASE IF NOT EXISTS attendance_db
    CHARACTER SET utf8mb4
    COLLATE utf8mb4_unicode_ci;

USE attendance_db;

-- -------------------------------------------------------------
-- 1. PHÒNG BAN
-- -------------------------------------------------------------
CREATE TABLE IF NOT EXISTS phong_ban (
    ma_phong_ban    INT             NOT NULL AUTO_INCREMENT   COMMENT 'Mã phòng ban (tự tăng)',
    ten_phong_ban   VARCHAR(100)    NOT NULL                  COMMENT 'Tên phòng ban (duy nhất)',
    ngay_tao        DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Thời điểm tạo bản ghi',
    PRIMARY KEY (ma_phong_ban),
    UNIQUE KEY uq_phong_ban_ten (ten_phong_ban)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='Danh sách phòng ban trong tổ chức';

-- -------------------------------------------------------------
-- 2. NHÂN VIÊN
-- -------------------------------------------------------------
CREATE TABLE IF NOT EXISTS nhan_vien (
    ma_nhan_vien    INT             NOT NULL AUTO_INCREMENT   COMMENT 'Mã nhân viên (tự tăng)',
    ma_so           VARCHAR(20)     NOT NULL                  COMMENT 'Mã số nhân viên (duy nhất, ví dụ: NV001)',
    ho_ten          VARCHAR(150)    NOT NULL                  COMMENT 'Họ và tên đầy đủ',
    email           VARCHAR(150)    NOT NULL                  COMMENT 'Địa chỉ email (duy nhất)',
    so_dien_thoai   VARCHAR(20)         NULL                  COMMENT 'Số điện thoại',
    chuc_vu         VARCHAR(100)        NULL                  COMMENT 'Chức vụ / vị trí công việc',
    ma_phong_ban    INT                 NULL                  COMMENT 'Mã phòng ban (khóa ngoại → phong_ban)',
    trang_thai      VARCHAR(20)     NOT NULL DEFAULT 'active' COMMENT 'Trạng thái: active | inactive',
    anh_dai_dien    VARCHAR(500)        NULL                  COMMENT 'Đường dẫn ảnh đại diện',
    ngay_tao        DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP                      COMMENT 'Thời điểm tạo bản ghi',
    ngay_cap_nhat   DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT 'Thời điểm cập nhật gần nhất',
    PRIMARY KEY (ma_nhan_vien),
    UNIQUE  KEY uq_nhan_vien_ma_so  (ma_so),
    UNIQUE  KEY uq_nhan_vien_email  (email),
    KEY     idx_nhan_vien_ma_so     (ma_so),
    KEY     idx_nhan_vien_email     (email),
    CONSTRAINT fk_nhan_vien_phong_ban
        FOREIGN KEY (ma_phong_ban) REFERENCES phong_ban (ma_phong_ban) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='Thông tin hồ sơ nhân viên';

-- -------------------------------------------------------------
-- 3. TÀI KHOẢN ĐĂNG NHẬP
-- -------------------------------------------------------------
CREATE TABLE IF NOT EXISTS tai_khoan (
    ma_tai_khoan        INT             NOT NULL AUTO_INCREMENT   COMMENT 'Mã tài khoản (tự tăng)',
    ma_nhan_vien        INT                 NULL                  COMMENT 'Mã nhân viên liên kết (khóa ngoại → nhan_vien)',
    ten_dang_nhap       VARCHAR(50)     NOT NULL                  COMMENT 'Tên đăng nhập (duy nhất)',
    mat_khau_ma_hoa     VARCHAR(255)    NOT NULL                  COMMENT 'Mật khẩu đã mã hóa bcrypt',
    vai_tro             VARCHAR(20)     NOT NULL DEFAULT 'employee' COMMENT 'Vai trò: admin | employee',
    so_lan_sai          INT             NOT NULL DEFAULT 0        COMMENT 'Số lần đăng nhập sai liên tiếp',
    khoa_den            DATETIME            NULL                  COMMENT 'Tài khoản bị khóa đến thời điểm này (NULL = không bị khóa)',
    lan_cuoi_dang_nhap  DATETIME            NULL                  COMMENT 'Thời điểm đăng nhập gần nhất',
    ngay_tao            DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Thời điểm tạo tài khoản',
    PRIMARY KEY (ma_tai_khoan),
    UNIQUE  KEY uq_tai_khoan_ma_nhan_vien (ma_nhan_vien),
    UNIQUE  KEY uq_tai_khoan_ten_dang_nhap (ten_dang_nhap),
    KEY     idx_tai_khoan_ten_dang_nhap   (ten_dang_nhap),
    CONSTRAINT fk_tai_khoan_nhan_vien
        FOREIGN KEY (ma_nhan_vien) REFERENCES nhan_vien (ma_nhan_vien) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='Tài khoản đăng nhập hệ thống';

-- -------------------------------------------------------------
-- 4. ĐẶC TRƯNG KHUÔN MẶT
-- Lưu dưới dạng chuỗi JSON, không lưu ảnh thô.
-- Mỗi NV có template gallery: 1 template chính + nhiều template phụ (multi-pose
-- enrollment + adaptive learning). Vì vậy KHÔNG có UNIQUE trên ma_nhan_vien;
-- chỉ có index thường để tăng tốc truy vấn theo NV.
-- -------------------------------------------------------------
CREATE TABLE IF NOT EXISTS dac_trung_khuon_mat (
    ma_ban_ghi          INT         NOT NULL AUTO_INCREMENT   COMMENT 'Mã bản ghi (tự tăng)',
    ma_nhan_vien        INT         NOT NULL                  COMMENT 'Mã nhân viên (khóa ngoại → nhan_vien, một NV có nhiều template)',
    du_lieu_vector      MEDIUMTEXT  NOT NULL                  COMMENT 'Vector đặc trưng khuôn mặt dạng JSON (danh sách số thực)',
    la_template_chinh   BOOLEAN     NOT NULL DEFAULT TRUE     COMMENT 'TRUE = template do admin đăng ký (primary), FALSE = template phụ (multi-pose seed / adaptive)',
    ngay_tao            DATETIME    NOT NULL DEFAULT CURRENT_TIMESTAMP                      COMMENT 'Thời điểm đăng ký khuôn mặt',
    ngay_cap_nhat       DATETIME    NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT 'Thời điểm cập nhật khuôn mặt gần nhất',
    PRIMARY KEY (ma_ban_ghi),
    KEY ix_face_employee     (ma_nhan_vien),
    KEY ix_face_emp_primary  (ma_nhan_vien, la_template_chinh),
    CONSTRAINT fk_dac_trung_khuon_mat_nhan_vien
        FOREIGN KEY (ma_nhan_vien) REFERENCES nhan_vien (ma_nhan_vien) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='Vector đặc trưng khuôn mặt cho nhận diện (gallery multi-template, không lưu ảnh thô)';

-- -------------------------------------------------------------
-- 5. THẺ RFID
-- -------------------------------------------------------------
CREATE TABLE IF NOT EXISTS the_rfid (
    ma_the          INT             NOT NULL AUTO_INCREMENT   COMMENT 'Mã thẻ (tự tăng)',
    uid             VARCHAR(100)    NOT NULL                  COMMENT 'Mã UID duy nhất của thẻ RFID',
    ma_nhan_vien    INT                 NULL                  COMMENT 'Mã nhân viên được gán thẻ (khóa ngoại → nhan_vien, NULL = chưa gán)',
    trang_thai      VARCHAR(20)     NOT NULL DEFAULT 'active' COMMENT 'Trạng thái thẻ: active | disabled',
    ngay_cap_phat   DATETIME            NULL                  COMMENT 'Thời điểm gán thẻ cho nhân viên',
    ngay_tao        DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Thời điểm thêm thẻ vào hệ thống',
    PRIMARY KEY (ma_the),
    UNIQUE  KEY uq_the_rfid_uid    (uid),
    KEY     idx_the_rfid_uid       (uid),
    CONSTRAINT fk_the_rfid_nhan_vien
        FOREIGN KEY (ma_nhan_vien) REFERENCES nhan_vien (ma_nhan_vien) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='Danh sách thẻ RFID và nhân viên được gán';

-- -------------------------------------------------------------
-- 6. LỊCH SỬ CHẤM CÔNG
-- -------------------------------------------------------------
CREATE TABLE IF NOT EXISTS lich_su_cham_cong (
    ma_ban_ghi      INT             NOT NULL AUTO_INCREMENT   COMMENT 'Mã bản ghi chấm công (tự tăng)',
    ma_nhan_vien    INT             NOT NULL                  COMMENT 'Mã nhân viên (khóa ngoại → nhan_vien)',
    gio_vao         DATETIME        NOT NULL                  COMMENT 'Thời điểm vào ca (check-in)',
    gio_ra          DATETIME            NULL                  COMMENT 'Thời điểm ra ca (check-out, NULL = chưa ra)',
    ghi_chu         TEXT                NULL                  COMMENT 'Ghi chú thêm',
    ngay_lam_viec   DATE            NOT NULL                  COMMENT 'Ngày làm việc (dùng để truy vấn theo ngày)',
    ngay_tao        DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Thời điểm tạo bản ghi',
    PRIMARY KEY (ma_ban_ghi),
    KEY idx_lich_su_cham_cong_nhan_vien (ma_nhan_vien),
    KEY idx_lich_su_cham_cong_ngay      (ngay_lam_viec),
    CONSTRAINT fk_lich_su_cham_cong_nhan_vien
        FOREIGN KEY (ma_nhan_vien) REFERENCES nhan_vien (ma_nhan_vien) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='Lịch sử chấm công vào/ra của nhân viên';

-- -------------------------------------------------------------
-- 6.1. SU KIEN DONG BO TU KIOSK
-- Luu ma su kien do kiosk tao de retry an toan, tranh ghi trung khi mat mang.
-- -------------------------------------------------------------
CREATE TABLE IF NOT EXISTS su_kien_cham_cong_kiosk (
    ma_su_kien          INT          NOT NULL AUTO_INCREMENT,
    ma_su_kien_client   VARCHAR(64)  NOT NULL,
    ma_nhan_vien        INT          NOT NULL,
    ma_ban_ghi          INT          NOT NULL,
    hanh_dong           VARCHAR(20)  NOT NULL COMMENT 'check_in | check_out',
    ma_thiet_bi         VARCHAR(100)     NULL,
    thoi_diem_cham_cong DATETIME     NOT NULL,
    thoi_diem_dong_bo   DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (ma_su_kien),
    UNIQUE KEY uq_kiosk_event_client (ma_su_kien_client),
    KEY idx_kiosk_event_employee (ma_nhan_vien),
    KEY idx_kiosk_event_attendance_log (ma_ban_ghi),
    CONSTRAINT fk_kiosk_event_nhan_vien
        FOREIGN KEY (ma_nhan_vien) REFERENCES nhan_vien (ma_nhan_vien) ON DELETE CASCADE,
    CONSTRAINT fk_kiosk_event_lich_su
        FOREIGN KEY (ma_ban_ghi) REFERENCES lich_su_cham_cong (ma_ban_ghi) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='Su kien cham cong do kiosk gui len, dung cho idempotency khi dong bo';

-- -------------------------------------------------------------
-- 7. DON TU
-- -------------------------------------------------------------
CREATE TABLE IF NOT EXISTS don_tu (
    ma_don              INT             NOT NULL AUTO_INCREMENT   COMMENT 'Mã đơn (tự tăng)',
    ma_nhan_vien        INT             NOT NULL                  COMMENT 'Mã nhân viên gửi đơn (khóa ngoại → nhan_vien)',
    loai_don            VARCHAR(30)     NOT NULL                  COMMENT 'Loại đơn: nghi_phep | di_muon | ve_som | cong_tac | khac',
    thoi_gian_bat_dau   DATETIME        NOT NULL                  COMMENT 'Thời điểm bắt đầu nghỉ / đi muộn',
    thoi_gian_ket_thuc  DATETIME        NOT NULL                  COMMENT 'Thời điểm kết thúc',
    ly_do               TEXT            NOT NULL                  COMMENT 'Lý do',
    trang_thai          VARCHAR(20)     NOT NULL DEFAULT 'cho_duyet' COMMENT 'Trạng thái: cho_duyet | da_duyet | tu_choi | da_huy',
    ly_do_tu_choi       TEXT                NULL                  COMMENT 'Lý do từ chối (chỉ có khi trang_thai = tu_choi)',
    nguoi_duyet         INT                 NULL                  COMMENT 'Mã tài khoản quản lý đã duyệt/từ chối (khóa ngoại → tai_khoan)',
    ngay_duyet          DATETIME            NULL                  COMMENT 'Thời điểm duyệt hoặc từ chối đơn',
    ngay_tao            DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP                      COMMENT 'Thời điểm tạo đơn',
    ngay_cap_nhat       DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT 'Thời điểm cập nhật gần nhất',
    PRIMARY KEY (ma_don),
    KEY idx_don_tu_nhan_vien (ma_nhan_vien),
    CONSTRAINT fk_don_tu_nhan_vien
        FOREIGN KEY (ma_nhan_vien) REFERENCES nhan_vien (ma_nhan_vien) ON DELETE CASCADE,
    CONSTRAINT fk_don_tu_nguoi_duyet
        FOREIGN KEY (nguoi_duyet) REFERENCES tai_khoan (ma_tai_khoan) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='Đơn từ của nhân viên (nghỉ phép, đi muộn, v.v.) và trạng thái duyệt';

-- -------------------------------------------------------------
-- 8. THÔNG BÁO
-- Thông báo gửi tới tài khoản đăng nhập (đơn được duyệt/từ chối,
-- nhắc chấm công, cảnh báo bảo mật, v.v.). Gắn với tai_khoan vì
-- thông báo chỉ hiển thị cho người đang đăng nhập.
-- -------------------------------------------------------------
CREATE TABLE IF NOT EXISTS thong_bao (
    ma_thong_bao    INT             NOT NULL AUTO_INCREMENT   COMMENT 'Mã thông báo (tự tăng)',
    ma_tai_khoan    INT             NOT NULL                  COMMENT 'Mã tài khoản nhận thông báo (khóa ngoại → tai_khoan)',
    loai            VARCHAR(40)     NOT NULL                  COMMENT 'Loại thông báo: don_duyet | don_tu_choi | nhac_cham_cong | bao_mat | khac',
    tieu_de         VARCHAR(255)    NOT NULL                  COMMENT 'Tiêu đề thông báo',
    noi_dung        TEXT            NOT NULL                  COMMENT 'Nội dung chi tiết',
    duong_dan       VARCHAR(255)        NULL                  COMMENT 'Đường dẫn liên kết (mở trang liên quan khi click)',
    da_doc          BOOLEAN         NOT NULL DEFAULT FALSE    COMMENT 'Đã đọc hay chưa (FALSE = chưa đọc)',
    ngay_doc        DATETIME            NULL                  COMMENT 'Thời điểm đánh dấu đã đọc (NULL nếu chưa đọc)',
    ngay_tao        DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Thời điểm tạo thông báo',
    PRIMARY KEY (ma_thong_bao),
    KEY idx_thong_bao_tai_khoan (ma_tai_khoan),
    CONSTRAINT fk_thong_bao_tai_khoan
        FOREIGN KEY (ma_tai_khoan) REFERENCES tai_khoan (ma_tai_khoan) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='Thông báo gửi đến tài khoản đăng nhập';

USE attendance_db;
SHOW TABLES;
