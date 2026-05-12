from typing import Optional
from pydantic import BaseModel, Field


class FaceRegisterRequest(BaseModel):
    image_base64: str  # base64-encoded image — template chính
    # Multi-pose enrollment: ảnh bổ sung lưu vào gallery như template phụ
    # (is_primary=False). Cho phép kiosk "seed" gallery 3-5 góc/ánh sáng ngay
    # lúc đăng ký lần đầu, thay vì đợi adaptive enrollment học dần qua nhiều
    # lần verify. Ảnh nào extract embedding lỗi sẽ bị bỏ qua, không fail toàn bộ.
    extra_images: Optional[list[str]] = Field(default=None, max_length=10)


class FaceRecognizeRequest(BaseModel):
    image_base64: str


class FaceRecognizeResponse(BaseModel):
    employee_id: int
    employee_name: str
    employee_code: str
    confidence: float


class FaceStatusResponse(BaseModel):
    employee_id: int
    has_face: bool
    registered_at: Optional[str] = None
