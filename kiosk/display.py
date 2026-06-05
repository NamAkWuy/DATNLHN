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
# UI scaling — mọi kích thước/font được thiết kế cho frame width 1280px.
# Khi DISPLAY_SCALE > 1 (main.py upscale lên 1920/2560/…), ta nhân hằng số
# với `s = canvas.w / 1280` để UI co giãn THEO MÀN HÌNH thay vì cố định
# pixel → trên fullscreen 2K/4K vẫn lớn và sắc, không bị "card 620px lọt
# thỏm trong screen 2560px".
# ============================================================================
BASE_WIDTH = 1280

def _ui_scale(canvas) -> float:
    return canvas.w / BASE_WIDTH


def _S(canvas, *vals):
    """Scale một loạt int theo ui_scale. Dùng để gọn `S(canvas, 620, 360, 28)`."""
    s = _ui_scale(canvas)
    return tuple(int(v * s) for v in vals)


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
    s = _ui_scale(canvas)
    bar_h = int(76 * s)

    # Gradient ngang nhiều stop: deep → primary → accent
    canvas.hgradient((0, 0, w // 2, bar_h), PRIMARY_DEEP, PRIMARY_DARK)
    canvas.hgradient((w // 2, 0, w, bar_h), PRIMARY_DARK, ACCENT_DEEP)

    # Lớp sáng phía trên cho cảm giác glossy
    canvas.draw.rectangle((0, 0, w, bar_h // 3),
                          fill=(255, 255, 255, 24))

    # Đường viền dưới — accent sáng
    canvas.line(((0, bar_h - 1), (w, bar_h - 1)), fill=(*ACCENT, 220),
                width=max(1, int(2 * s)))
    canvas.line(((0, bar_h + 1), (w, bar_h + 1)),
                fill=(*PRIMARY_DEEP, 80), width=1)

    # ─── Logo: huy hiệu tròn có vành sáng ───
    cy = bar_h // 2
    cx = int(36 * s)
    halo_r = int(22 * s)
    badge_outer_r = int(18 * s)
    badge_inner_r = int(13 * s)
    # Halo
    canvas.ellipse((cx - halo_r, cy - halo_r, cx + halo_r, cy + halo_r),
                   fill=(255, 255, 255, 28))
    canvas.ellipse((cx - badge_outer_r, cy - badge_outer_r,
                    cx + badge_outer_r, cy + badge_outer_r), fill=WHITE)
    canvas.ellipse((cx - badge_inner_r, cy - badge_inner_r,
                    cx + badge_inner_r, cy + badge_inner_r), fill=PRIMARY_DEEP)
    # Hình bóng "người" đơn giản trong huy hiệu
    h_off = int(5 * s)
    canvas.ellipse((cx - h_off, cy - int(7 * s), cx + h_off, cy + int(3 * s)),
                   fill=WHITE)
    canvas.rounded_rect((cx - int(8 * s), cy + int(2 * s),
                         cx + int(8 * s), cy + int(11 * s)),
                        radius=int(4 * s), fill=WHITE)

    # ─── Brand text ───
    canvas.text((int(68 * s), cy), "TRẠM CHẤM CÔNG",
                weight="bold", size=int(22 * s), color=WHITE, anchor="lm")

    # ─── Đồng hồ + ngày ở phải ───
    t = time.strftime("%H:%M:%S")
    # map weekday tiếng Việt
    weekdays = {
        "Monday": "Thứ Hai", "Tuesday": "Thứ Ba", "Wednesday": "Thứ Tư",
        "Thursday": "Thứ Năm", "Friday": "Thứ Sáu",
        "Saturday": "Thứ Bảy", "Sunday": "Chủ nhật",
    }
    en = time.strftime("%A")
    d = f"{weekdays.get(en, en)} · {time.strftime('%d/%m/%Y')}"

    canvas.text((w - int(20 * s), cy - int(12 * s)), t,
                weight="bold", size=int(26 * s), color=WHITE, anchor="rm")
    canvas.text((w - int(20 * s), cy + int(16 * s)), d,
                weight="semibold", size=int(15 * s),
                color=(255, 255, 255, 230), anchor="rm")

    canvas.commit()


# ============================================================================
# Khung khuôn mặt — góc bo + glow + vòng quét nhịp
# ============================================================================
def draw_face_box(frame, x, y, w, h, color=GREEN):
    """Vẽ khung khuôn mặt có 4 góc bo, glow mềm và vòng quét nhịp."""
    # color là BGR (do main.py truyền) → đổi sang RGB cho Pillow
    color_rgb = _rgb_to_bgr(color) if isinstance(color, tuple) else SUCCESS
    canvas = _PILCanvas(frame)

    L = max(22, min(w, h) // 4)
    th = 2

    # Glow mềm phía sau (mỏng hơn — viền tinh tế thay vì bold)
    glow_color = (*color_rgb, 70)
    for (a, b) in [
        ((x, y), (x + L, y)), ((x, y), (x, y + L)),
        ((x + w, y), (x + w - L, y)), ((x + w, y), (x + w, y + L)),
        ((x, y + h), (x + L, y + h)), ((x, y + h), (x, y + h - L)),
        ((x + w, y + h), (x + w - L, y + h)),
        ((x + w, y + h), (x + w, y + h - L)),
    ]:
        canvas.line((a, b), fill=glow_color, width=th + 5)

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
    s = _ui_scale(canvas)
    success = overlay.success
    main_color = SUCCESS if success else DANGER
    dark_color = SUCCESS_DARK if success else DANGER_DARK

    # ─── Backdrop tối (vignette) ───
    canvas.rect((0, 0, w, h), fill=(8, 12, 10, 165))

    # ─── Kích thước thẻ — TỈ LỆ với frame width (không cố định pixel nữa) ───
    # Trên 1280 → 620w/360h (như cũ).
    # Trên 2560 → 1240w/720h → vẫn ~48% width nên không bị nhỏ.
    card_w = min(int(620 * s), w - int(80 * s))
    card_h = int(360 * s)
    cx1 = (w - card_w) // 2
    cy1 = (h - card_h) // 2
    cx2 = cx1 + card_w
    cy2 = cy1 + card_h
    radius = int(28 * s)

    # Bóng đổ — vẽ nhiều lớp ellipse để mượt
    for i, alpha in enumerate([18, 26, 36]):
        off = int((12 - i * 3) * s)
        canvas.rounded_rect(
            (cx1 - off, cy1 + off, cx2 + off, cy2 + off + int(6 * s)),
            radius=radius + off,
            fill=(0, 0, 0, alpha),
        )

    # Thân thẻ
    canvas.rounded_rect((cx1, cy1, cx2, cy2), radius=radius, fill=CARD_BG)
    accent_top = (*main_color, 18) if success else (*main_color, 16)
    canvas.rounded_rect((cx1, cy1, cx2, cy1 + int(120 * s)),
                        radius=radius, fill=accent_top)

    # Dải màu trên đỉnh thẻ
    canvas.rounded_rect((cx1, cy1, cx2, cy1 + int(14 * s)),
                        radius=radius, fill=main_color)
    canvas.rect((cx1, cy1 + int(7 * s), cx2, cy1 + int(14 * s)),
                fill=main_color)

    # ─── Biểu tượng trạng thái — vòng tròn lớn có halo ───
    icon_cx = w // 2
    icon_cy = cy1 + int(105 * s)
    icon_r = int(50 * s)

    canvas.ellipse(
        (icon_cx - icon_r - int(14 * s), icon_cy - icon_r - int(14 * s),
         icon_cx + icon_r + int(14 * s), icon_cy + icon_r + int(14 * s)),
        fill=(*main_color, 35),
    )
    canvas.ellipse(
        (icon_cx - icon_r - int(6 * s), icon_cy - icon_r - int(6 * s),
         icon_cx + icon_r + int(6 * s), icon_cy + icon_r + int(6 * s)),
        fill=(*main_color, 60),
    )
    canvas.ellipse(
        (icon_cx - icon_r, icon_cy - icon_r,
         icon_cx + icon_r, icon_cy + icon_r),
        fill=dark_color,
    )

    # Dấu tích / dấu X
    stroke = max(4, int(6 * s))
    if success:
        canvas.line(
            ((icon_cx - int(22 * s), icon_cy + int(2 * s)),
             (icon_cx - int(6 * s), icon_cy + int(18 * s))),
            fill=WHITE, width=stroke,
        )
        canvas.line(
            ((icon_cx - int(6 * s), icon_cy + int(18 * s)),
             (icon_cx + int(22 * s), icon_cy - int(12 * s))),
            fill=WHITE, width=stroke,
        )
    else:
        canvas.line(
            ((icon_cx - int(18 * s), icon_cy - int(18 * s)),
             (icon_cx + int(18 * s), icon_cy + int(18 * s))),
            fill=WHITE, width=stroke,
        )
        canvas.line(
            ((icon_cx + int(18 * s), icon_cy - int(18 * s)),
             (icon_cx - int(18 * s), icon_cy + int(18 * s))),
            fill=WHITE, width=stroke,
        )

    # ─── Thông điệp chính ───
    canvas.text((w // 2, cy1 + int(200 * s)), overlay.message,
                weight="bold", size=int(28 * s), color=GRAY_900, anchor="mm")

    # ─── Thông điệp phụ ───
    if overlay.submessage:
        canvas.text((w // 2, cy1 + int(240 * s)), overlay.submessage,
                    weight="semibold", size=int(16 * s),
                    color=GRAY_700, anchor="mm")

    # ─── Pill trạng thái dưới đáy ───
    pill_text = "THÀNH CÔNG" if success else "KHÔNG THÀNH CÔNG"
    pill_font_size = int(14 * s)
    pw, ph = _measure_text(pill_text, weight="bold", size=pill_font_size)
    pad_x, pad_y = int(20 * s), int(10 * s)
    pill_w = pw + pad_x * 2
    pill_h = ph + pad_y * 2 + int(4 * s)
    px1 = w // 2 - pill_w // 2
    py1 = cy2 - pill_h - int(24 * s)
    canvas.rounded_rect(
        (px1, py1, px1 + pill_w, py1 + pill_h),
        radius=pill_h // 2, fill=main_color,
    )
    canvas.text(
        (w // 2, py1 + pill_h // 2 + 1), pill_text,
        weight="bold", size=pill_font_size, color=WHITE, anchor="mm",
    )

    canvas.commit()


# ============================================================================
# Idle dock — thanh nhắc người dùng ở đáy màn hình
# ============================================================================
def draw_idle_prompt(frame):
    canvas = _PILCanvas(frame)
    w, h = canvas.w, canvas.h
    s = _ui_scale(canvas)
    dock_h = int(88 * s)
    margin = int(22 * s)
    dx1 = margin
    dy1 = h - dock_h - margin
    dx2 = w - margin
    dy2 = dy1 + dock_h
    radius = int(22 * s)

    # Bóng đổ mờ
    for i, a in enumerate([14, 20, 26]):
        off = int((10 - i * 3) * s)
        canvas.rounded_rect(
            (dx1 - off, dy1 + off, dx2 + off, dy2 + off + int(4 * s)),
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
                        radius=radius, outline=(*PRIMARY, 90),
                        width=max(1, int(1 * s)))

    # ─── Status dot pulsing bên trái ───
    cy = (dy1 + dy2) // 2
    pulse = 0.5 + 0.5 * np.sin(time.time() * 3)
    dot_r_outer = int((14 + pulse * 4) * s)
    dot_r_inner = int(8 * s)
    dot_cx = dx1 + int(30 * s)
    canvas.ellipse(
        (dot_cx - dot_r_outer, cy - dot_r_outer,
         dot_cx + dot_r_outer, cy + dot_r_outer),
        fill=(*PRIMARY, int(60 + 80 * pulse)),
    )
    canvas.ellipse(
        (dot_cx - dot_r_inner, cy - dot_r_inner,
         dot_cx + dot_r_inner, cy + dot_r_inner),
        fill=PRIMARY,
    )

    # ─── Text ───
    tx = dx1 + int(60 * s)
    canvas.text((tx, cy - int(11 * s)),
                "Sẵn sàng — Vui lòng quẹt thẻ và đưa khuôn mặt",
                weight="bold", size=int(19 * s), color=WHITE, anchor="lm")
    canvas.text((tx, cy + int(18 * s)),
                "Q / ESC: Thoát   ·   R: Đăng ký khuôn mặt mới",
                weight="semibold", size=int(14 * s),
                color=(225, 235, 230, 255), anchor="lm")

    canvas.commit()


# ============================================================================
# Đăng ký khuôn mặt — modal nhập mã NV
# ============================================================================
def draw_register_mode(frame, emp_id_buf: str):
    canvas = _PILCanvas(frame)
    w, h = canvas.w, canvas.h
    s = _ui_scale(canvas)

    # Backdrop
    canvas.rect((0, 0, w, h), fill=(8, 12, 10, 165))

    card_w = min(int(580 * s), w - int(80 * s))
    card_h = int(320 * s)
    cx1 = (w - card_w) // 2
    cy1 = (h - card_h) // 2
    cx2 = cx1 + card_w
    cy2 = cy1 + card_h
    radius = int(28 * s)

    # Bóng đổ
    for i, a in enumerate([18, 26, 36]):
        off = int((12 - i * 3) * s)
        canvas.rounded_rect(
            (cx1 - off, cy1 + off, cx2 + off, cy2 + off + int(6 * s)),
            radius=radius + off, fill=(0, 0, 0, a),
        )

    # Thân thẻ
    canvas.rounded_rect((cx1, cy1, cx2, cy2), radius=radius, fill=CARD_BG)
    canvas.rounded_rect((cx1, cy1, cx2, cy1 + int(120 * s)),
                        radius=radius, fill=(*WARNING, 18))

    # Dải màu trên đỉnh
    canvas.rounded_rect((cx1, cy1, cx2, cy1 + int(14 * s)),
                        radius=radius, fill=WARNING)
    canvas.rect((cx1, cy1 + int(7 * s), cx2, cy1 + int(14 * s)), fill=WARNING)

    # Icon
    icon_cx = w // 2
    icon_cy = cy1 + int(90 * s)
    icon_r = int(36 * s)
    canvas.ellipse(
        (icon_cx - icon_r - int(8 * s), icon_cy - icon_r - int(8 * s),
         icon_cx + icon_r + int(8 * s), icon_cy + icon_r + int(8 * s)),
        fill=(*WARNING, 50),
    )
    canvas.ellipse(
        (icon_cx - icon_r, icon_cy - icon_r,
         icon_cx + icon_r, icon_cy + icon_r),
        fill=WARNING_DARK,
    )
    canvas.text((icon_cx, icon_cy + 1), "ID",
                weight="bold", size=int(22 * s), color=WHITE, anchor="mm")

    # Tiêu đề
    canvas.text((w // 2, cy1 + int(160 * s)), "ĐĂNG KÝ KHUÔN MẶT MỚI",
                weight="bold", size=int(20 * s), color=GRAY_900, anchor="mm")
    canvas.text((w // 2, cy1 + int(188 * s)),
                "Nhập mã nhân viên rồi nhấn Enter để chụp",
                weight="semibold", size=int(14 * s),
                color=GRAY_700, anchor="mm")

    # Input pill
    pill_w = int(280 * s)
    pill_h = int(64 * s)
    px1 = w // 2 - pill_w // 2
    py1 = cy1 + int(210 * s)
    canvas.rounded_rect((px1, py1, px1 + pill_w, py1 + pill_h),
                        radius=int(16 * s), fill=GRAY_100,
                        outline=WARNING, width=max(2, int(3 * s)))

    show = emp_id_buf if emp_id_buf else ""
    caret = "│" if int(time.time() * 2) % 2 == 0 else " "
    placeholder = "0000" if not show else ""
    if placeholder:
        canvas.text((w // 2, py1 + pill_h // 2), placeholder,
                    weight="regular", size=int(24 * s),
                    color=GRAY_500, anchor="mm")
    canvas.text((w // 2, py1 + pill_h // 2),
                f"{show}{caret}",
                weight="bold", size=int(26 * s), color=GRAY_900, anchor="mm")

    # Hint dưới đáy
    canvas.text((w // 2, cy2 - int(26 * s)),
                "Enter: Xác nhận   ·   ESC: Hủy",
                weight="semibold", size=int(13 * s),
                color=GRAY_500, anchor="mm")

    canvas.commit()


# ============================================================================
# Processing badge — hiển thị khi đang chờ backend
# ============================================================================
def draw_processing_badge(frame):
    canvas = _PILCanvas(frame)
    w = canvas.w
    s = _ui_scale(canvas)
    text = "Đang xử lý..."
    font_size = int(15 * s)
    tw, th = _measure_text(text, weight="bold", size=font_size)

    pad_x, pad_y = int(18 * s), int(12 * s)
    spinner_box = int(24 * s)
    bw = tw + pad_x * 2 + spinner_box + int(8 * s)
    bh = th + pad_y * 2 + int(2 * s)
    bx2 = w - int(24 * s)
    bx1 = bx2 - bw
    by1 = int(96 * s)
    by2 = by1 + bh

    # Bóng đổ
    canvas.rounded_rect(
        (bx1 + int(2 * s), by1 + int(4 * s), bx2 + int(2 * s), by2 + int(6 * s)),
        radius=bh // 2, fill=(0, 0, 0, 60)
    )
    # Thân
    canvas.rounded_rect((bx1, by1, bx2, by2),
                        radius=bh // 2, fill=GRAY_900,
                        outline=WARNING, width=max(1, int(2 * s)))

    # Spinner
    spinner_cx = bx1 + pad_x + int(8 * s)
    spinner_cy = (by1 + by2) // 2
    angle = (time.time() * 360) % 360
    r = int(10 * s)
    canvas.draw.arc(
        (spinner_cx - r, spinner_cy - r, spinner_cx + r, spinner_cy + r),
        start=angle, end=angle + 270,
        fill=WARNING, width=max(2, int(2 * s)),
    )

    canvas.text((bx1 + pad_x + spinner_box + int(8 * s), spinner_cy), text,
                weight="bold", size=font_size, color=WHITE, anchor="lm")

    canvas.commit()
