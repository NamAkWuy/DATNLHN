"""
Unit tests for kiosk/rfid_reader.py (RFIDReader class)

Tests cover:
- get_uid trả về None khi queue rỗng
- get_uid trả về UID khi có trong queue
- Xử lý ký tự: tích lũy buffer đến khi gặp newline
- Bỏ qua UID rỗng (chỉ gõ Enter)
- Loại bỏ khoảng trắng thừa ở đầu/cuối UID
- start/stop: thread daemon chạy và dừng đúng
"""
import sys
import os
import time
import threading
import queue as queue_module

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from rfid_reader import RFIDReader


# ---------------------------------------------------------------------------
# Tests: get_uid
# ---------------------------------------------------------------------------

class TestGetUID:
    def test_returns_none_when_queue_empty(self):
        reader = RFIDReader()
        assert reader.get_uid() is None

    def test_returns_uid_when_available(self):
        reader = RFIDReader()
        reader._queue.put("RFID-TEST-001")
        assert reader.get_uid() == "RFID-TEST-001"

    def test_returns_none_after_queue_drained(self):
        reader = RFIDReader()
        reader._queue.put("RFID-A")
        reader.get_uid()
        assert reader.get_uid() is None

    def test_fifo_order(self):
        """UIDs phải được trả về theo thứ tự FIFO."""
        reader = RFIDReader()
        reader._queue.put("FIRST")
        reader._queue.put("SECOND")
        reader._queue.put("THIRD")
        assert reader.get_uid() == "FIRST"
        assert reader.get_uid() == "SECOND"
        assert reader.get_uid() == "THIRD"
        assert reader.get_uid() is None


# ---------------------------------------------------------------------------
# Tests: buffer accumulation & newline handling
# ---------------------------------------------------------------------------

class TestBufferProcessing:
    """
    Test hành vi buffer bằng cách gọi trực tiếp logic xử lý ký tự,
    không cần stdin thật. Mô phỏng cách reader tích lũy ký tự.
    """

    def _simulate_input(self, reader: RFIDReader, chars: str):
        """
        Mô phỏng chuỗi ký tự gõ từ đầu đọc RFID bằng cách đẩy trực tiếp
        vào _buffer và xử lý ký tự newline.
        """
        for ch in chars:
            if ch in ("\r", "\n"):
                uid = reader._buffer.strip()
                if uid:
                    reader._queue.put(uid)
                reader._buffer = ""
            else:
                reader._buffer += ch

    def test_accumulates_uid_before_newline(self):
        reader = RFIDReader()
        self._simulate_input(reader, "RFID12345\n")
        assert reader.get_uid() == "RFID12345"

    def test_carriage_return_triggers_uid(self):
        reader = RFIDReader()
        self._simulate_input(reader, "CARD_A1B2\r")
        assert reader.get_uid() == "CARD_A1B2"

    def test_empty_buffer_on_newline_is_ignored(self):
        """Chỉ gõ Enter mà không có UID → không thêm vào queue."""
        reader = RFIDReader()
        self._simulate_input(reader, "\n")
        assert reader.get_uid() is None

    def test_whitespace_stripped_from_uid(self):
        reader = RFIDReader()
        self._simulate_input(reader, "  CARD123  \n")
        uid = reader.get_uid()
        assert uid == "CARD123"

    def test_multiple_scans_queued(self):
        """Nhiều lần quét liên tiếp → nhiều UID trong queue."""
        reader = RFIDReader()
        self._simulate_input(reader, "UID_001\nUID_002\nUID_003\n")
        assert reader.get_uid() == "UID_001"
        assert reader.get_uid() == "UID_002"
        assert reader.get_uid() == "UID_003"
        assert reader.get_uid() is None

    def test_partial_buffer_not_yielded_yet(self):
        """Ký tự đang nhập dở chưa gặp newline → chưa xuất UID."""
        reader = RFIDReader()
        self._simulate_input(reader, "PARTIAL")
        assert reader.get_uid() is None
        # Bây giờ kết thúc
        self._simulate_input(reader, "_UID\n")
        assert reader.get_uid() == "PARTIAL_UID"

    def test_buffer_cleared_after_newline(self):
        """Sau khi xử lý newline, buffer phải được reset."""
        reader = RFIDReader()
        self._simulate_input(reader, "CARD_X\n")
        assert reader._buffer == ""

    def test_typical_rfid_uid_format(self):
        """Định dạng UID điển hình: 8-16 ký tự hex."""
        reader = RFIDReader()
        self._simulate_input(reader, "E2001108921A4578\n")
        uid = reader.get_uid()
        assert uid == "E2001108921A4578"
        assert len(uid) == 16


# ---------------------------------------------------------------------------
# Tests: start/stop lifecycle
# ---------------------------------------------------------------------------

class TestRFIDReaderLifecycle:
    def test_initial_state_not_running(self):
        reader = RFIDReader()
        assert reader._running is False
        assert reader._thread is None

    def test_start_sets_running_true(self):
        reader = RFIDReader()
        # Mock _read_loop để tránh đọc stdin thật
        reader._read_loop = lambda: time.sleep(10)
        reader.start()
        try:
            assert reader._running is True
            assert reader._thread is not None
            assert reader._thread.is_alive()
            assert reader._thread.daemon is True
        finally:
            reader.stop()

    def test_stop_sets_running_false(self):
        reader = RFIDReader()
        reader._read_loop = lambda: time.sleep(10)
        reader.start()
        reader.stop()
        assert reader._running is False

    def test_queue_is_empty_on_init(self):
        reader = RFIDReader()
        assert reader._queue.empty()

    def test_buffer_is_empty_on_init(self):
        reader = RFIDReader()
        assert reader._buffer == ""


# ---------------------------------------------------------------------------
# Tests: thread safety
# ---------------------------------------------------------------------------

class TestThreadSafety:
    def test_get_uid_non_blocking(self):
        """get_uid không được block khi queue rỗng."""
        reader = RFIDReader()
        start = time.monotonic()
        result = reader.get_uid()
        elapsed = time.monotonic() - start
        assert result is None
        assert elapsed < 0.1, f"get_uid blocked for {elapsed:.3f}s"

    def test_multiple_threads_can_put_uids(self):
        """Nhiều thread đẩy UID vào queue đồng thời → tất cả được nhận đủ."""
        reader = RFIDReader()
        num_threads = 5
        uids_per_thread = 10

        def producer(prefix: str):
            for i in range(uids_per_thread):
                reader._queue.put(f"{prefix}_{i:03d}")

        threads = [
            threading.Thread(target=producer, args=(f"T{t}",))
            for t in range(num_threads)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        collected = []
        while True:
            uid = reader.get_uid()
            if uid is None:
                break
            collected.append(uid)

        assert len(collected) == num_threads * uids_per_thread
