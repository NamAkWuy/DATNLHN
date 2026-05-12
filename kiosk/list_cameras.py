"""
Liệt kê các camera đang có trên máy (Windows).

Cách dùng:
    python list_cameras.py

Mục đích: xác định đúng index của webcam để gán vào CAMERA_SOURCE trong
config.py. Script thử mở lần lượt index 0..5 với cả 2 backend DirectShow và
Media Foundation, đọc 1 frame để kiểm tra camera có hoạt động thật hay không,
đồng thời in độ phân giải gốc và FPS.
"""
import cv2

BACKENDS = [
    ("MSMF",  cv2.CAP_MSMF),    # mặc định Windows
    ("DSHOW", cv2.CAP_DSHOW),   # fallback
]
MAX_INDEX = 5


def probe(index: int, backend_name: str, backend_flag: int) -> None:
    cap = cv2.VideoCapture(index, backend_flag)
    if not cap.isOpened():
        cap.release()
        return

    ok, frame = cap.read()
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = cap.get(cv2.CAP_PROP_FPS)
    cap.release()

    status = "OK" if ok and frame is not None else "MO DUOC NHUNG KHONG DOC FRAME"
    print(f"  [{backend_name:5s}] index={index}  {w}x{h} @ {fps:.1f}fps  -> {status}")


def main() -> None:
    print("=" * 70)
    print("Quet camera tu index 0 toi", MAX_INDEX)
    print("=" * 70)

    for backend_name, backend_flag in BACKENDS:
        print(f"\n--- Backend: {backend_name} ---")
        for i in range(MAX_INDEX + 1):
            probe(i, backend_name, backend_flag)

    print("\n" + "=" * 70)
    print("HUONG DAN:")
    print("  • Webcam laptop tich hop thuong la index 0.")
    print("  • Mo kiosk/config.py va dat:")
    print("      CAMERA_SOURCE  = <index cua webcam>")
    print("      CAMERA_BACKEND = 'msmf'  (hoac 'dshow' neu msmf khong on)")
    print("=" * 70)


if __name__ == "__main__":
    main()
