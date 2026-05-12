"""
Timezone utilities — hệ thống chạy theo giờ Việt Nam (UTC+7).
Dùng now_vn() / today_vn() thay cho datetime.now(timezone.utc)
để tránh lệch 7 tiếng khi lưu vào MySQL DateTime (không có timezone).
"""
from datetime import datetime, date, timezone, timedelta

VN_TZ = timezone(timedelta(hours=7))


def now_vn() -> datetime:
    """Giờ hiện tại theo giờ Việt Nam, dạng naive (không có tzinfo) để lưu MySQL."""
    return datetime.now(VN_TZ).replace(tzinfo=None)


def today_vn() -> date:
    """Ngày hôm nay theo giờ Việt Nam."""
    return datetime.now(VN_TZ).date()
