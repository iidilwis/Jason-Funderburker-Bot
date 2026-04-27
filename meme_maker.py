"""
Генератор мемів і демотиваторів через Pillow.
"""

from PIL import Image, ImageDraw, ImageFont
import textwrap
import io
import os
import random
import logging

logger = logging.getLogger(__name__)

# Шляхи до шрифтів (DejaVu є майже скрізь)
FONT_PATHS = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
    "/usr/share/fonts/truetype/ubuntu/Ubuntu-B.ttf",
]


def _get_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for path in FONT_PATHS:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    return ImageFont.load_default()


def _draw_text_with_outline(
    draw: ImageDraw.ImageDraw,
    xy: tuple,
    text: str,
    font,
    fill=(255, 255, 255),
    outline=(0, 0, 0),
    outline_width: int = 2,
):
    x, y = xy
    for dx in range(-outline_width, outline_width + 1):
        for dy in range(-outline_width, outline_width + 1):
            if dx != 0 or dy != 0:
                draw.text((x + dx, y + dy), text, font=font, fill=outline)
    draw.text((x, y), text, font=font, fill=fill)


def make_demotivator(
    image_bytes: bytes,
    title: str,
    subtitle: str = "",
) -> bytes:
    """
    Класичний демотиватор: чорний фон, біла рамка, картинка, текст знизу.
    """
    try:
        src = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    except Exception:
        src = Image.new("RGB", (400, 300), (50, 50, 50))

    # Масштабуємо картинку
    max_w, max_h = 500, 400
    src.thumbnail((max_w, max_h), Image.LANCZOS)
    img_w, img_h = src.size

    border = 3
    padding = 20
    title_font_size = max(22, img_w // 18)
    sub_font_size = max(16, img_w // 26)
    title_font = _get_font(title_font_size)
    sub_font = _get_font(sub_font_size)

    # Рахуємо висоту тексту
    dummy = Image.new("RGB", (1, 1))
    d = ImageDraw.Draw(dummy)
    title_wrapped = textwrap.fill(title, width=30)
    t_bbox = d.multiline_textbbox((0, 0), title_wrapped, font=title_font)
    t_h = t_bbox[3] - t_bbox[1] + 10

    sub_h = 0
    sub_wrapped = ""
    if subtitle:
        sub_wrapped = textwrap.fill(subtitle, width=40)
        s_bbox = d.multiline_textbbox((0, 0), sub_wrapped, font=sub_font)
        sub_h = s_bbox[3] - s_bbox[1] + 8

    canvas_w = img_w + padding * 2 + border * 2
    canvas_h = img_h + padding * 2 + border * 2 + t_h + sub_h + padding

    canvas = Image.new("RGB", (canvas_w, canvas_h), (0, 0, 0))

    # Рамка навколо картинки
    img_x = padding
    img_y = padding
    for i in range(border):
        rect_draw = ImageDraw.Draw(canvas)
        rect_draw.rectangle(
            [img_x - i - 1, img_y - i - 1,
             img_x + img_w + i, img_y + img_h + i],
            outline=(255, 255, 255)
        )

    canvas.paste(src, (img_x, img_y))

    draw = ImageDraw.Draw(canvas)

    # Заголовок
    text_y = img_y + img_h + border + padding // 2
    t_bbox2 = draw.multiline_textbbox((0, 0), title_wrapped, font=title_font)
    t_w = t_bbox2[2] - t_bbox2[0]
    draw.multiline_text(
        ((canvas_w - t_w) // 2, text_y),
        title_wrapped,
        font=title_font,
        fill=(255, 255, 255),
        align="center"
    )

    # Підзаголовок
    if sub_wrapped:
        sub_y = text_y + t_h
        s_bbox2 = draw.multiline_textbbox((0, 0), sub_wrapped, font=sub_font)
        s_w = s_bbox2[2] - s_bbox2[0]
        draw.multiline_text(
            ((canvas_w - s_w) // 2, sub_y),
            sub_wrapped,
            font=sub_font,
            fill=(180, 180, 180),
            align="center"
        )

    buf = io.BytesIO()
    canvas.save(buf, format="JPEG", quality=88)
    return buf.getvalue()


def make_impact_meme(
    image_bytes: bytes,
    top_text: str = "",
    bottom_text: str = "",
) -> bytes:
    """Мем з Impact-стилем текстом зверху і знизу."""
    try:
        img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    except Exception:
        img = Image.new("RGB", (500, 400), (30, 30, 30))

    img.thumbnail((600, 600), Image.LANCZOS)
    w, h = img.size
    draw = ImageDraw.Draw(img)
    font_size = max(28, w // 12)
    font = _get_font(font_size)

    def draw_centered(text: str, y: int):
        wrapped = textwrap.fill(text.upper(), width=20)
        lines = wrapped.split("\n")
        for i, line in enumerate(lines):
            bbox = draw.textbbox((0, 0), line, font=font)
            lw = bbox[2] - bbox[0]
            lh = bbox[3] - bbox[1]
            _draw_text_with_outline(
                draw,
                ((w - lw) // 2, y + i * (lh + 4)),
                line,
                font=font,
                outline_width=3
            )

    if top_text:
        draw_centered(top_text, 10)
    if bottom_text:
        # Рахуємо знизу
        wrapped = textwrap.fill(bottom_text.upper(), width=20)
        lines = wrapped.split("\n")
        bbox = draw.textbbox((0, 0), "A", font=font)
        line_h = bbox[3] - bbox[1] + 4
        total_h = len(lines) * line_h
        draw_centered(bottom_text, h - total_h - 15)

    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=88)
    return buf.getvalue()


def make_collage(image_bytes_list: list[bytes]) -> bytes:
    """Колаж з 2-3 картинок поряд."""
    imgs = []
    for b in image_bytes_list:
        try:
            im = Image.open(io.BytesIO(b)).convert("RGB")
            im.thumbnail((400, 400), Image.LANCZOS)
            imgs.append(im)
        except Exception:
            continue

    if not imgs:
        blank = Image.new("RGB", (400, 300), (20, 20, 20))
        buf = io.BytesIO()
        blank.save(buf, format="JPEG")
        return buf.getvalue()

    gap = 4
    total_w = sum(im.width for im in imgs) + gap * (len(imgs) - 1)
    max_h = max(im.height for im in imgs)
    canvas = Image.new("RGB", (total_w, max_h), (0, 0, 0))

    x = 0
    for im in imgs:
        canvas.paste(im, (x, (max_h - im.height) // 2))
        x += im.width + gap

    buf = io.BytesIO()
    canvas.save(buf, format="JPEG", quality=85)
    return buf.getvalue()
