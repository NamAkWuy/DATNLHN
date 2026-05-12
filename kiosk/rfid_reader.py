"""
Đầu đọc RFID qua USB HID (chế độ giả lập bàn phím).

Đa số đầu đọc RFID giá rẻ kết nối USB hoạt động như thiết bị bàn phím — khi
quẹt thẻ chúng "gõ" UID của thẻ ra rồi kết thúc bằng phím Enter.

Module này đọc từ stdin theo cách non-blocking, gom các ký tự lại cho đến khi
gặp Enter (\\n hoặc \\r) thì trả về chuỗi UID đầy đủ.

- Trên Windows: chạy được ngay với mọi đầu đọc RFID USB HID.
- Trên Linux: cũng chạy được ngay (đầu đọc xuất hiện như thiết bị bàn phím).
"""
import queue
import threading
import logging

logger = logging.getLogger(__name__)


class RFIDReader:
    """
    Đầu đọc RFID non-blocking, lắng nghe sự kiện quẹt thẻ qua bàn phím giả lập.

    Cách dùng:
        reader = RFIDReader()
        reader.start()
        # Trong vòng lặp chính:
        uid = reader.get_uid()   # trả về chuỗi UID hoặc None
        reader.stop()
    """

    def __init__(self):
        self._queue: queue.Queue[str] = queue.Queue()
        self._buffer = ""
        self._running = False
        self._thread: threading.Thread | None = None

    def start(self):
        """Khởi động luồng nền để đọc tín hiệu RFID."""
        self._running = True
        self._thread = threading.Thread(target=self._read_loop, daemon=True)
        self._thread.start()
        logger.info("Đã khởi động đầu đọc RFID (chế độ USB HID / bàn phím)")

    def stop(self):
        self._running = False

    def get_uid(self) -> str | None:
        """Non-blocking: trả về UID nếu vừa có thẻ được quẹt, ngược lại trả về None."""
        try:
            return self._queue.get_nowait()
        except queue.Empty:
            return None

    def _read_loop(self):
        """
        Đọc từng ký tự một từ stdin.
        Đầu đọc RFID ở chế độ giả lập bàn phím gõ rất nhanh (< 50ms cho 1 thẻ).
        Ta gom ký tự cho đến khi gặp ký tự xuống dòng rồi đẩy vào hàng đợi.
        """
        import sys
        import select

        while self._running:
            # Kiểm tra stdin non-blocking (Linux/Mac dùng select; Windows dùng msvcrt)
            try:
                if sys.platform == "win32":
                    import msvcrt
                    if msvcrt.kbhit():
                        ch = msvcrt.getwch()
                        if ch in ("\r", "\n"):
                            uid = self._buffer.strip()
                            if uid:
                                logger.info(f"Đã quẹt thẻ RFID: {uid}")
                                self._queue.put(uid)
                            self._buffer = ""
                        else:
                            self._buffer += ch
                    else:
                        import time
                        time.sleep(0.01)
                else:
                    # Linux / Mac
                    r, _, _ = select.select([sys.stdin], [], [], 0.01)
                    if r:
                        ch = sys.stdin.read(1)
                        if ch in ("\r", "\n"):
                            uid = self._buffer.strip()
                            if uid:
                                logger.info(f"Đã quẹt thẻ RFID: {uid}")
                                self._queue.put(uid)
                            self._buffer = ""
                        else:
                            self._buffer += ch
            except Exception as e:
                logger.debug(f"Lỗi khi đọc RFID: {e}")
                import time
                time.sleep(0.05)
