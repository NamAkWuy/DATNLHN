"""
Bộ tiện ích vẽ overlay lên cửa sổ OpenCV của kiosk.

Thiết kế hiện đại 2026: header gradient nhiều lớp, dock kính mờ,
khung khuôn mặt phát sáng, thẻ kết quả lớn — toàn bộ render qua Pillow
nên cạnh bo góc anti-aliasing mượt và chữ tiếng Việt sắc nét.
"""
import time
import unicodedata
from dataclasses import dataclass, field
from typing import Optional, Tuple

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont


# ============================================================================
# Bảng màu — chủ đề Mint
# Lưu RGB (Pillow native). Khi cần BGR cho OpenCV thì dùng _rgb_to_bgr().
# Giữ tên hằng số cũ để main.py không phải đổi.
# ============================================================================
# Mint chính
PRIMARY      = ( 16, 185, 129)    # mint-500
PRIMARY_DARK = (  5, 150, 105)    # mint-600
PRIMARY_DEEP = (  4, 120,  87)    # mint-700
PRIMARY_BG   = (236, 253, 245)    # mint-50

# Màu nhấn — teal sáng cho gradient mềm
ACCENT       = ( 45, 212, 191)    # teal-400
ACCENT_DEEP  = ( 13, 148, 136)    # teal-600

# Màu theo ngữ nghĩa
SUCCESS      = PRIMARY
SUCCESS_DARK = PRIMARY_DARK
DANGER       = (244,  63,  94)    # rose-500
DANGER_DARK  = (190,  47,  75)    # rose-700
WARNING      = (245, 158,  11)    # amber-500
WARNING_DARK = (217, 119,   6)    # amber-600

WHITE        = (255, 255, 255)
BLACK        = (  0,   0,   0)
GRAY_950     = ( 12,  18,  16)
GRAY_900     = ( 24,  35,  31)
GRAY_700     = ( 65,  82,  74)
GRAY_500     = (135, 152, 144)
GRAY_300     = (210, 225, 218)
GRAY_100     = (240, 248, 244)

CARD_BG      = (252, 254, 253)

# ─── BGR aliases (cho main.py truyền vào draw_face_box) ─────────────────────
def _rgb_to_bgr(c):
    return (c[2], c[1], c[0])

GREEN        = _rgb_to_bgr(SUCCESS)
RED          = _rgb_to_bgr(DANGER)
RED_BGR      = _rgb_to_bgr(DANGER)
BLUE         = _rgb_to_bgr(PRIMARY)
YELLOW       = _rgb_to_bgr(WARNING)
DARK_OVERLAY = _rgb_to_bgr(GRAY_900)


# ============================================================================
# Font — tải có cache
# ============================================================================
_FONT_CACHE: dict = {}
_FONT_PATHS = {
    "regular":  r"C:\Windows\Fonts\segoeui.ttf",
    "semibold": r"C:\Windows\Fonts\seguisb.ttf",
    "bold":     r"C:\Windows\Fonts\segoeuib.ttf",
    "light":    r"C:\Windows\Fonts\segoeuil.ttf",
}


def _get_font(weight: str, size: int) -> ImageFont.FreeTypeFont:
    key = (weight, size)
    f = _FONT_CACHE.get(key)
    if f is None:
        path = _FONT_PATHS.get(weight, _FONT_PATHS["regular"])
        try:
            f = ImageFont.truetype(path, size)
        except OSError:
            try:
                f = ImageFont.truetype(_FONT_PATHS["regular"], size)
            except OSError:
                f = ImageFont.load_default()
        _FONT_CACHE[key] = f
    return f


def _measure_text(text: str, weight="regular", size=18) -> Tuple[int, int]:
    font = _get_font(weight, size)
    bbox = font.getbbox(text)
    return (bbox[2] - bbox[0], bbox[3] - bbox[1])


# ============================================================================
# PIL overlay context — gom mọi thao tác vẽ vào 1 lần convert BGR↔RGB
# Pillow vẽ rounded_rectangle có anti-aliasing sẵn, sắc nét hơn cv2 nhiều.
# ============================================================================
class _PILCanvas:
    """Wrapper Pillow để vẽ overlay lên frame BGR. Gọi commit() để ghi lại."""

    def __init__(self, frame: np.ndarray):
        self.frame = frame
        self.h, self.w = frame.shape[:2]
        self.img = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
        self.draw = ImageDraw.Draw(self.img, "RGBA")

    def commit(self):
        self.frame[:] = cv2.cvtColor(np.array(self.img), cv2.COLOR_RGB2BGR)

    def rounded_rect(self, xy, radius, fill=None, outline=None, width=1):
        self.draw.rounded_rectangle(xy, radius=radius, fill=fill,
                                    outline=outline, width=width)

    def rect(self, xy, fill=None, outline=None, width=1):
        self.draw.rectangle(xy, fill=fill, outline=outline, width=width)

    def ellipse(self, xy, fill=None, outline=None, width=1):
        self.draw.ellipse(xy, fill=fill, outline=outline, width=width)

    def line(self, xy, fill, width=1):
        self.draw.line(xy, fill=fill, width=width)

    def text(self, xy, text, weight="regular", size=18, color=WHITE,
             anchor="lt"):
        font = _get_font(weight, size)
        self.draw.text(xy, text, font=font, fill=color, anchor=anchor)

    def vgradient(self, xy, color1, color2):
        """Tô gradient dọc trong vùng xy = (x1,y1,x2,y2). RGBA tuples."""
        x1, y1, x2, y2 = xy
        h = max(y2 - y1, 1)
        for i in range(h):
            t = i / max(h - 1, 1)
            col = tuple(int(color1[c] * (1 - t) + color2[c] * t)
                        for c in range(len(color1)))
            self.draw.rectangle((x1, y1 + i, x2, y1 + i + 1), fill=col)

    def hgradient(self, xy, color1, color2):
        """Tô gradient ngang."""
        x1, y1, x2, y2 = xy
        w = max(x2 - x1, 1)
        for i in range(w):
            t = i / max(w - 1, 1)
            col = tuple(int(color1[c] * (1 - t) + color2[c] * t)
                        for c in range(len(color1)))
            self.draw.rectangle((x1 + i, y1, x1 + i + 1, y2), fill=col)


# ============================================================================
# Hàm tương thích ngược (giữ cho main.py phiên bản cũ)
# ============================================================================
def ascii_text(text: str) -> str:
    """Bỏ dấu — không còn cần nhưng giữ để code cũ gọi không lỗi."""
    normalized = unicodedata.normalize("NFD", text)
    return "".join(c for c in normalized if unicodedata.category(c) != "Mn")


def put_text_centered(frame, text: str, y: int, font_scale: float,
                      color, thickness: int = 2):
    """Vẽ chữ Unicode căn giữa qua Pillow."""
    canvas = _PILCanvas(frame)
    size = max(14, int(font_scale * 30))
    weight = "bold" if thickness >= 2 else "regular"
    color_rgb = (color[2], color[1], color[0]) if len(color) == 3 else color
    canvas.text((canvas.w // 2, y), text, weight=weight, size=size,
                color=color_rgb, anchor="ms")
    canvas.commit()


# ============================================================================
# Trạng thái thẻ kết quả
# ============================================================================
@dataclass
class ResultOverlay:
    """Nội dung thông báo kết quả tạm thời hiển thị toàn màn hình."""
    message: str
    submessage: str = ""
    success: bool = True
    show_until: float = field(default_factory=lambda: time.time() + 3.0)

    def is_active(self) -> bool:
        return time.time() < self.show_until


# ============================================================================
# Header — thanh trên cùng (gradient + brand + đồng hồ + status)
# ============================================================================
def draw_header(frame):
    canvas = _PILCanvas(frame)
    w = canvas.w
    bar_h = 76

    # Gradient ngang nhiều stop: deep → primary → accent
    canvas.hgradient((0, 0, w // 2, bar_h), PRIMARY_DEEP, PRIMARY_DARK)
    canvas.hgradient((w // 2, 0, w, bar_h), PRIMARY_DARK, ACCENT_DEEP)

    # Lớp sáng phía trên cho cảm giác glossy
    canvas.draw.rectangle((0, 0, w, bar_h // 3),
                          fill=(255, 255, 255, 24))

    # Đường viền dưới — accent sáng
    canvas.line(((0, bar_h - 1), (w, bar_h - 1)), fill=(*ACCENT, 220), width=2)
    canvas.line(((0, bar_h + 1), (w, bar_h + 1)),
                fill=(*PRIMARY_DEEP, 80), width=1)

    # ─── Logo: huy hiệu tròn có vành sáng ───
    cy = bar_h // 2
    cx = 36
    # Halo
    canvas.ellipse((cx - 22, cy - 22, cx + 22, cy + 22),
                   fill=(255, 255, 255, 28))
    canvas.ellipse((cx - 18, cy - 18, cx + 18, cy + 18), fill=WHITE)
    canvas.ellipse((cx - 13, cy - 13, cx + 13, cy + 13), fill=PRIMARY_DEEP)
    # Hình bóng "người" đơn giản trong huy hiệu
    canvas.ellipse((cx - 5, cy - 7, cx + 5, cy + 3), fill=WHITE)
    canvas.rounded_rect((cx - 8, cy + 2, cx + 8, cy + 11),
                        radius=4, fill=WHITE)

    # ─── Brand text ───
    canvas.text((68, cy - 12), "TRẠM CHẤM CÔNG",
                weight="bold", size=20, color=WHITE, anchor="lm")
    canvas.text((68, cy + 14), "Nhận diện khuôn mặt · RFID",
                weight="regular", size=12, color=(255, 255, 255, 200),
                anchor="lm")

    # ─── Đồng hồ + ngày ở phải ───
    t = time.strftime("%H:%M:%S")
    d = time.strftime("%A · %d/%m/%Y")
    # map weekday tiếng Việt
    weekdays = {
        "Monday": "Thứ Hai", "Tuesday": "Thứ Ba", "Wednesday": "Thứ Tư",
        "Thursday": "Thứ Năm", "Friday": "Thứ Sáu",
        "Saturday": "Thứ Bảy", "Sunday": "Chủ nhật",
    }
    en = time.strftime("%A")
    d = f"{weekdays.get(en, en)} · {time.strftime('%d/%m/%Y')}"

    canvas.text((w - 20, cy - 12), t, weight="bold", size=24,
                color=WHITE, anchor="rm")
    canvas.text((w - 20, cy + 14), d, weight="regular", size=12,
                color=(255, 255, 255, 200), anchor="rm")

    canvas.commit()


# ============================================================================
# Khung khuôn mặt — góc bo + glow + vòng quét nhịp
# ============================================================================
def draw_face_box(frame, x, y, w, h, color=GREEN):
    """Vẽ khung khuôn mặt có 4 góc bo, glow mềm và vòng quét nhịp."""
    # color là BGR (do main.py truyền) → đổi sang RGB cho Pillow
    color_rgb = _rgb_to_bgr(color) if isinstance(color, tuple) else SUCCESS
    canvas = _PILCanvas(frame)

    L = max(26, min(w, h) // 4)
    th = 4

    # Glow mềm phía sau (vẽ đậm hơn rồi sẽ phủ bằng line sắc nét)
    glow_color = (*color_rgb, 90)
    for (a, b) in [
        ((x, y), (x + L, y)), ((x, y), (x, y + L)),
        ((x + w, y), (x + w - L, y)), ((x + w, y), (x + w, y + L)),
        ((x, y + h), (x + L, y + h)), ((x, y + h), (x, y + h - L)),
        ((x + w, y + h), (x + w - L, y + h)),
        ((x + w, y + h), (x + w, y + h - L)),
    ]:
        canvas.line((a, b), fill=glow_color, width=th + 8)

    # Góc bo sắc nét — vẽ bằng arc + line để ra hình "L cong"
    r = 14  # bán kính bo của khung
    sharp = (*color_rgb, 255)

    def corner(cx, cy, dx, dy):
        # cx, cy là điểm góc; dx, dy là hướng chữ L
        # vẽ arc bo + 2 line vươn ra L pixel
        # góc trên-trái: dx=1, dy=1 → arc 180-270
        if dx == 1 and dy == 1:
            canvas.draw.arc((cx, cy, cx + 2 * r, cy + 2 * r),
                            180, 270, fill=sharp, width=th)
            canvas.line(((cx + r, cy), (cx + L, cy)),
                        fill=sharp, width=th)
            canvas.line(((cx, cy + r), (cx, cy + L)),
                        fill=sharp, width=th)
        elif dx == -1 and dy == 1:
            canvas.draw.arc((cx - 2 * r, cy, cx, cy + 2 * r),
                            270, 360, fill=sharp, width=th)
            canvas.line(((cx - L, cy), (cx - r, cy)),
                        fill=sharp, width=th)
            canvas.line(((cx, cy + r), (cx, cy + L)),
                        fill=sharp, width=th)
        elif dx == 1 and dy == -1:
            canvas.draw.arc((cx, cy - 2 * r, cx + 2 * r, cy),
                            90, 180, fill=sharp, width=th)
            canvas.line(((cx + r, cy), (cx + L, cy)),
                        fill=sharp, width=th)
            canvas.line(((cx, cy - L), (cx, cy - r)),
                        fill=sharp, width=th)
        else:  # dx=-1, dy=-1
            canvas.draw.arc((cx - 2 * r, cy - 2 * r, cx, cy),
                            0, 90, fill=sharp, width=th)
            canvas.line(((cx - L, cy), (cx - r, cy)),
                        fill=sharp, width=th)
            canvas.line(((cx, cy - L), (cx, cy - r)),
                        fill=sharp, width=th)

    corner(x, y,         1,  1)
    corner(x + w, y,    -1,  1)
    corner(x, y + h,     1, -1)
    corner(x + w, y + h, -1, -1)

    # Vòng quét nhịp đập
    pulse = 0.5 + 0.5 * np.sin(time.time() * 4)
    radius = int(min(w, h) * 0.55 + pulse * 10)
    cx, cy = x + w // 2, y + h // 2
    ring_alpha = int(80 + 100 * pulse)
    canvas.ellipse((cx - radius, cy - radius, cx + radius, cy + radius),
                   outline=(*color_rgb, ring_alpha), width=2)

    canvas.commit()


# ============================================================================
# Thẻ kết quả — modal toàn màn hình khi có kết quả chấm công
# ============================================================================
def draw_result_overlay(frame, overlay: ResultOverlay):
    canvas = _PILCanvas(frame)
    w, h = canvas.w, canvas.h
    success = overlay.success
    main_color = SUCCESS if success else DANGER
    dark_color = SUCCESS_DARK if success else DANGER_DARK

    # ─── Backdrop tối (vignette) ───
    canvas.rect((0, 0, w, h), fill=(8, 12, 10, 165))

    # ─── Kích thước thẻ ───
    card_w = min(620, w - 80)
    card_h = 360
    cx1 = (w - card_w) // 2
    cy1 = (h - card_h) // 2
    cx2 = cx1 + card_w
    cy2 = cy1 + card_h
    radius = 28

    # Bóng đổ — vẽ nhiều lớp ellipse để mượt
    for i, alpha in enumerate([18, 26, 36]):
        off = 12 - i * 3
        canvas.rounded_rect(
            (cx1 - off, cy1 + off, cx2 + off, cy2 + off + 6),
            radius=radius + off,
            fill=(0, 0, 0, alpha),
        )

    # Thân thẻ — gradient nhẹ (trắng → trắng-mint)
    canvas.rounded_rect((cx1, cy1, cx2, cy2), radius=radius, fill=CARD_BG)
    # Lớp accent mờ phủ phía trên thân thẻ
    accent_top = (*main_color, 18) if success else (*main_color, 16)
    canvas.rounded_rect((cx1, cy1, cx2, cy1 + 120),
                        radius=radius, fill=accent_top)

    # Dải màu trên đỉnh thẻ — bo cùng radius
    canvas.rounded_rect((cx1, cy1, cx2, cy1 + 14),
                        radius=radius, fill=main_color)
    canvas.rect((cx1, cy1 + 7, cx2, cy1 + 14), fill=main_color)

    # ─── Biểu tượng trạng thái — vòng tròn lớn có halo ───
    icon_cx = w // 2
    icon_cy = cy1 + 105
    icon_r = 50

    # Halo
    canvas.ellipse(
        (icon_cx - icon_r - 14, icon_cy - icon_r - 14,
         icon_cx + icon_r + 14, icon_cy + icon_r + 14),
        fill=(*main_color, 35),
    )
    canvas.ellipse(
        (icon_cx - icon_r - 6, icon_cy - icon_r - 6,
         icon_cx + icon_r + 6, icon_cy + icon_r + 6),
        fill=(*main_color, 60),
    )
    # Tâm
    canvas.ellipse(
        (icon_cx - icon_r, icon_cy - icon_r,
         icon_cx + icon_r, icon_cy + icon_r),
        fill=dark_color,
    )

    # Dấu tích / dấu X — vẽ qua line dày trên Pillow (có AA)
    if success:
        canvas.line(
            ((icon_cx - 22, icon_cy + 2), (icon_cx - 6, icon_cy + 18)),
            fill=WHITE, width=6,
        )
        canvas.line(
            ((icon_cx - 6, icon_cy + 18), (icon_cx + 22, icon_cy - 12)),
            fill=WHITE, width=6,
        )
    else:
        canvas.line(
            ((icon_cx - 18, icon_cy - 18), (icon_cx + 18, icon_cy + 18)),
            fill=WHITE, width=6,
        )
        canvas.line(
            ((icon_cx + 18, icon_cy - 18), (icon_cx - 18, icon_cy + 18)),
            fill=WHITE, width=6,
        )

    # ─── Thông điệp chính ───
    canvas.text((w // 2, cy1 + 200), overlay.message,
                weight="bold", size=28, color=GRAY_900, anchor="mm")

    # ─── Thông điệp phụ ───
    if overlay.submessage:
        canvas.text((w // 2, cy1 + 240), overlay.submessage,
                    weight="regular", size=15, color=GRAY_700, anchor="mm")

    # ─── Pill trạng thái dưới đáy ───
    pill_text = "THÀNH CÔNG" if success else "KHÔNG THÀNH CÔNG"
    pw, ph = _measure_text(pill_text, weight="bold", size=12)
    pad_x, pad_y = 18, 8
    pill_w = pw + pad_x * 2
    pill_h = ph + pad_y * 2 + 4
    px1 = w // 2 - pill_w // 2
    py1 = cy2 - pill_h - 24
    canvas.rounded_rect(
        (px1, py1, px1 + pill_w, py1 + pill_h),
        radius=pill_h // 2, fill=main_color,
    )
    canvas.text(
        (w // 2, py1 + pill_h // 2 + 1), pill_text,
        weight="bold", size=12, color=WHITE, anchor="mm",
    )

    canvas.commit()


# ============================================================================
# Idle dock — thanh nhắc người dùng ở đáy màn hình
# ============================================================================
def draw_idle_prompt(frame):
    canvas = _PILCanvas(frame)
    w, h = canvas.w, canvas.h
    dock_h = 88
    margin = 22
    dx1 = margin
    dy1 = h - dock_h - margin
    dx2 = w - margin
    dy2 = dy1 + dock_h
    radius = 22

    # Bóng đổ mờ
    for i, a in enumerate([14, 20, 26]):
        off = 10 - i * 3
        canvas.rounded_rect(
            (dx1 - off, dy1 + off, dx2 + off, dy2 + off + 4),
            radius=radius + off, fill=(0, 0, 0, a),
        )

    # Thân dock — kính mờ tối
    canvas.rounded_rect((dx1, dy1, dx2, dy2),
                        radius=radius, fill=(18, 28, 24, 215))
    # Lớp gradient nhẹ phía trên
    canvas.rounded_rect((dx1, dy1, dx2, dy1 + dock_h // 2),
                        radius=radius, fill=(255, 255, 255, 14))
    # Viền sáng mảnh
    canvas.rounded_rect((dx1, dy1, dx2, dy2),
                        radius=radius, outline=(*PRIMARY, 110), width=2)

    # ─── Status dot pulsing bên trái ───
    cy = (dy1 + dy2) // 2
    pulse = 0.5 + 0.5 * np.sin(time.time() * 3)
    dot_r_outer = int(14 + pulse * 4)
    dot_r_inner = 8
    canvas.ellipse(
        (dx1 + 30 - dot_r_outer, cy - dot_r_outer,
         dx1 + 30 + dot_r_outer, cy + dot_r_outer),
        fill=(*PRIMARY, int(60 + 80 * pulse)),
    )
    canvas.ellipse(
        (dx1 + 30 - dot_r_inner, cy - dot_r_inner,
         dx1 + 30 + dot_r_inner, cy + dot_r_inner),
        fill=PRIMARY,
    )
    # Highlight
    canvas.ellipse(
        (dx1 + 28, cy - 6, dx1 + 32, cy - 2),
        fill=(255, 255, 255, 200),
    )

    # ─── Text ───
    tx = dx1 + 60
    canvas.text((tx, cy - 10),
                "Sẵn sàng — Vui lòng quẹt thẻ và đưa khuôn mặt",
                weight="bold", size=17, color=WHITE, anchor="lm")
    canvas.text((tx, cy + 16),
                "Q / ESC: Thoát   ·   R: Đăng ký khuôn mặt mới",
                weight="regular", size=12, color=(225, 235, 230, 255),
                anchor="lm")

    # ─── Pill RFID + Camera ở phải ───
    pill_y = cy
    pill_h = 30
    pill_pad = 14

    def chip(text, x_right, color):
        tw, th = _measure_text(text, weight="semibold", size=11)
        pw = tw + pill_pad * 2 + 18
        x1 = x_right - pw
        y1 = pill_y - pill_h // 2
        canvas.rounded_rect((x1, y1, x_right, y1 + pill_h),
                            radius=pill_h // 2,
                            fill=(255, 255, 255, 28),
                            outline=(*color, 180), width=1)
        # dot
        dr = 4
        dot_x = x1 + 12
        canvas.ellipse((dot_x - dr, pill_y - dr,
                        dot_x + dr, pill_y + dr), fill=color)
        canvas.text((x1 + 24, pill_y + 1), text,
                    weight="semibold", size=11, color=WHITE, anchor="lm")
        return x1

    next_x = dx2 - 14
    next_x = chip("CAMERA", next_x, PRIMARY) - 10
    chip("RFID", next_x, ACCENT)

    canvas.commit()


# ============================================================================
# Đăng ký khuôn mặt — modal nhập mã NV
# ============================================================================
def draw_register_mode(frame, emp_id_buf: str):
    canvas = _PILCanvas(frame)
    w, h = canvas.w, canvas.h

    # Backdrop
    canvas.rect((0, 0, w, h), fill=(8, 12, 10, 165))

    card_w = min(580, w - 80)
    card_h = 320
    cx1 = (w - card_w) // 2
    cy1 = (h - card_h) // 2
    cx2 = cx1 + card_w
    cy2 = cy1 + card_h
    radius = 28

    # Bóng đổ
    for i, a in enumerate([18, 26, 36]):
        off = 12 - i * 3
        canvas.rounded_rect(
            (cx1 - off, cy1 + off, cx2 + off, cy2 + off + 6),
            radius=radius + off, fill=(0, 0, 0, a),
        )

    # Thân thẻ
    canvas.rounded_rect((cx1, cy1, cx2, cy2), radius=radius, fill=CARD_BG)
    # Lớp accent
    canvas.rounded_rect((cx1, cy1, cx2, cy1 + 120),
                        radius=radius, fill=(*WARNING, 18))

    # Dải màu trên đỉnh
    canvas.rounded_rect((cx1, cy1, cx2, cy1 + 14),
                        radius=radius, fill=WARNING)
    canvas.rect((cx1, cy1 + 7, cx2, cy1 + 14), fill=WARNING)

    # Icon cảnh báo / đăng ký — vòng tròn warning có chữ "ID"
    icon_cx = w // 2
    icon_cy = cy1 + 90
    icon_r = 36
    canvas.ellipse(
        (icon_cx - icon_r - 8, icon_cy - icon_r - 8,
         icon_cx + icon_r + 8, icon_cy + icon_r + 8),
        fill=(*WARNING, 50),
    )
    canvas.ellipse(
        (icon_cx - icon_r, icon_cy - icon_r,
         icon_cx + icon_r, icon_cy + icon_r),
        fill=WARNING_DARK,
    )
    canvas.text((icon_cx, icon_cy + 1), "ID",
                weight="bold", size=22, color=WHITE, anchor="mm")

    # Tiêu đề
    canvas.text((w // 2, cy1 + 160), "ĐĂNG KÝ KHUÔN MẶT MỚI",
                weight="bold", size=20, color=GRAY_900, anchor="mm")
    canvas.text((w // 2, cy1 + 188),
                "Nhập mã nhân viên rồi nhấn Enter để chụp",
                weight="regular", size=13, color=GRAY_700, anchor="mm")

    # Input pill
    pill_w = 280
    pill_h = 64
    px1 = w // 2 - pill_w // 2
    py1 = cy1 + 210
    canvas.rounded_rect((px1, py1, px1 + pill_w, py1 + pill_h),
                        radius=16, fill=GRAY_100,
                        outline=WARNING, width=3)

    show = emp_id_buf if emp_id_buf else ""
    caret = "│" if int(time.time() * 2) % 2 == 0 else " "
    placeholder = "0000" if not show else ""
    if placeholder:
        canvas.text((w // 2, py1 + pill_h // 2), placeholder,
                    weight="regular", size=24,
                    color=GRAY_500, anchor="mm")
    canvas.text((w // 2, py1 + pill_h // 2),
                f"{show}{caret}",
                weight="bold", size=26, color=GRAY_900, anchor="mm")

    # Hint dưới đáy
    canvas.text((w // 2, cy2 - 26),
                "Enter: Xác nhận   ·   ESC: Hủy",
                weight="regular", size=12, color=GRAY_500, anchor="mm")

    canvas.commit()


# ============================================================================
# Processing badge — hiển thị khi đang chờ backend
# ============================================================================
def draw_processing_badge(frame):
    canvas = _PILCanvas(frame)
    w = canvas.w
    text = "Đang xử lý..."
    tw, th = _measure_text(text, weight="bold", size=13)

    pad_x, pad_y = 16, 10
    spinner_box = 22
    bw = tw + pad_x * 2 + spinner_box + 8
    bh = th + pad_y * 2 + 2
    bx2 = w - 24
    bx1 = bx2 - bw
    by1 = 96
    by2 = by1 + bh

    # Bóng đổ
    canvas.rounded_rect((bx1 + 2, by1 + 4, bx2 + 2, by2 + 6),
                        radius=bh // 2, fill=(0, 0, 0, 60))
    # Thân
    canvas.rounded_rect((bx1, by1, bx2, by2),
                        radius=bh // 2, fill=GRAY_900,
                        outline=WARNING, width=2)

    # Spinner — vẽ arc xoay
    spinner_cx = bx1 + pad_x + 8
    spinner_cy = (by1 + by2) // 2
    angle = (time.time() * 360) % 360
    r = 9
    canvas.draw.arc(
        (spinner_cx - r, spinner_cy - r, spinner_cx + r, spinner_cy + r),
        start=angle, end=angle + 270,
        fill=WARNING, width=2,
    )

    canvas.text((bx1 + pad_x + spinner_box + 8, spinner_cy), text,
                weight="bold", size=13, color=WHITE, anchor="lm")

    canvas.commit()
