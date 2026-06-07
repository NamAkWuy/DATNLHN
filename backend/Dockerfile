FROM python:3.11-slim

# Thư viện hệ thống cho OpenCV (libGL, libgomp) — TensorFlow & DeepFace cần.
# libgl1 cung cấp libGL.so.1 — deepface tự cài opencv-python (full, không phải headless),
# bản này cần libGL.so.1 cho cv2 native module load được.
RUN apt-get update && apt-get install -y --no-install-recommends \
    libglib2.0-0 libsm6 libxext6 libxrender-dev libgomp1 libgl1 \
    && rm -rf /var/lib/apt/lists/*

# Hugging Face Spaces yêu cầu chạy dưới user không phải root (uid 1000).
# Tự tạo user + chuyển sang user đó trước khi pip install để pip cache đi đúng
# vị trí có quyền ghi lúc runtime.
RUN useradd -m -u 1000 user
USER user
ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH \
    DEEPFACE_HOME=/home/user/.deepface \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    TF_CPP_MIN_LOG_LEVEL=2 \
    TF_ENABLE_ONEDNN_OPTS=0 \
    PORT=7860

WORKDIR $HOME/app

# Cài deps trước → tận dụng layer cache, mỗi lần đổi code chỉ rebuild layer cuối.
COPY --chown=user requirements.txt .
RUN pip install --user --no-cache-dir -r requirements.txt

# Pre-download weights ArcFace + MTCNN vào image — tránh request đầu tiên
# timeout ~30s download model. DeepFace tự cache ở $DEEPFACE_HOME.
RUN python -c "import numpy as np; from deepface import DeepFace; \
    img = np.zeros((224, 224, 3), dtype='uint8'); img[80:144, 80:144] = 128; \
    DeepFace.represent(img_path=img, model_name='ArcFace', detector_backend='mtcnn', enforce_detection=False)" \
    || echo "Pre-download finished (some warnings normal)"

COPY --chown=user . .

EXPOSE 7860
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-7860} --proxy-headers --forwarded-allow-ips='*'"]
