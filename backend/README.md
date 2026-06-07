---
title: HR Attendance Backend
emoji: 🎯
colorFrom: blue
colorTo: indigo
sdk: docker
app_port: 7860
pinned: false
short_description: Face recognition attendance backend (ArcFace + MTCNN)
---

# HR Attendance Backend

Backend FastAPI cho hệ thống chấm công bằng nhận diện khuôn mặt.

- **Face recognition**: DeepFace + ArcFace (embedding 512-d, L2 normalized)
- **Face detection / align**: MTCNN
- **Database**: MySQL (Railway) qua SQLAlchemy + pymysql
- **Auth**: JWT (HS256)
- **Realtime**: WebSocket cho kiosk events

## Endpoints

| Path | Mô tả |
|------|-------|
| `/docs` | Swagger UI |
| `/health` | Health check |
| `/api/v1/*` | API chính |
| `/ws` | WebSocket |

## Biến môi trường bắt buộc

Cấu hình tại **Space → Settings → Variables and secrets**:

| Tên | Loại | Ví dụ |
|-----|------|-------|
| `DATABASE_URL` | Secret | `mysql+pymysql://user:pass@host:port/db?charset=utf8mb4` |
| `SECRET_KEY` | Secret | chuỗi random dài ≥ 32 ký tự |
| `CORS_ORIGINS` | Variable | `https://your-frontend.vercel.app,http://localhost:5173` |
| `GROQ_API_KEY` | Secret | API key cho chatbot Groq |

## Build notes

Dockerfile tự pre-download trọng số ArcFace + MTCNN trong giai đoạn build →
request đầu tiên không phải chờ ~30s tải model.

Lần build đầu tốn ~10-15 phút (TensorFlow + DeepFace deps khoảng 1.8GB).
