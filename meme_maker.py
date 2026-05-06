from PIL import Image, ImageDraw, ImageFont
import textwrap
import io
import os
import glob
import random
import logging
import urllib.request

logger = logging.getLogger(__name__)

FONT_CACHE = {}
FONT_URL = "https://github.com/googlefonts/roboto/raw/main/src/hinted/Roboto-Bold.ttf"
LOCAL_FONT = "/tmp/bot_font.ttf"


def _find_system_font() -> str | None:
    patterns = [
        "/nix/store/*/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/nix/store/*/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/root/.nix-profile/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/truetype/ubuntu/Ubuntu-B.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
    ]
    for pattern in patterns:
        results = glob.glob(pattern, recursive=True)
        if results:
            return results[0]
    return None


def _get_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    if size in FONT_CACHE:
        return FONT_CACHE[size]

    # 1. Локально завантажений
    if os.path.exists(LOCAL_FONT):
        try:
            f = ImageFont.truetype(LOCAL_FONT, size)
            FONT_CACHE[size] = f
            return f
        except Exception:
            pass

    # 2. Системний шрифт
    path = _find_system_font()
    if path:
        try:
            f = ImageFont.truetype(path, size)
            FONT_CACHE[size] = f
            return f
        except Exception:
            pass

    # 3. Завантажити з інтернету
    try:
        logger.info("Downloading font...")
        urllib.request.urlretrieve(FONT_URL, LOCAL_FONT)
        f = ImageFont.truetype(LOCAL_FONT, size)
        FONT_CACHE[size] = f
        logger.info("Font downloaded ok")
        return f
    except Exception as e:
        logger.error(f"Font download failed: {e}")

    return ImageFont.load_default()


def _draw_outlined(draw, xy, text, font, fill=(255,255,255), outline=(0,0,0), width=2):
    x, y = xy
    for dx in range(-width, width+1):
        for dy in range(-width, width+1):
            if dx or dy:
                draw.text((x+dx, y+dy), text, font=font, fill=outline)
    draw.text((x, y), text, font=font, fill=fill)


def make_demotivator(image_bytes: bytes, title: str, subtitle: str = "") -> bytes:
    try:
        src = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    except Exception:
        src = Image.new("RGB", (400, 300), (50, 50, 50))

    src.thumbnail((500, 400), Image.LANCZOS)
    iw, ih = src.size

    border = 3
    pad = 20
    font_size = max(22, iw // 18)
    sub_size = max(16, iw // 26)
    font = _get_font(font_size)
    sfont = _get_font(sub_size)

    dummy = ImageDraw.Draw(Image.new("RGB", (1,1)))
    tw = textwrap.fill(title, width=30)
    tb = dummy.multiline_textbbox((0,0), tw, font=font)
    th = tb[3] - tb[1] + 10

    sw = ""
    sh = 0
    if subtitle:
        sw = textwrap.fill(subtitle, width=40)
        sb = dummy.multiline_textbbox((0,0), sw, font=sfont)
        sh = sb[3] - sb[1] + 8

    cw = iw + pad*2 + border*2
    ch = ih + pad*2 + border*2 + th + sh + pad

    canvas = Image.new("RGB", (cw, ch), (0,0,0))
    ix, iy = pad, pad
    draw = ImageDraw.Draw(canvas)
    for i in range(border):
        draw.rectangle([ix-i-1, iy-i-1, ix+iw+i, iy+ih+i], outline=(255,255,255))
    canvas.paste(src, (ix, iy))

    ty = iy + ih + border + pad//2
    tb2 = draw.multiline_textbbox((0,0), tw, font=font)
    draw.multiline_text(((cw-(tb2[2]-tb2[0]))//2, ty), tw, font=font, fill=(255,255,255), align="center")

    if sw:
        sb2 = draw.multiline_textbbox((0,0), sw, font=sfont)
        draw.multiline_text(((cw-(sb2[2]-sb2[0]))//2, ty+th), sw, font=sfont, fill=(180,180,180), align="center")

    buf = io.BytesIO()
    canvas.save(buf, format="JPEG", quality=88)
    return buf.getvalue()


def make_impact_meme(image_bytes: bytes, top_text: str = "", bottom_text: str = "") -> bytes:
    try:
        img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    except Exception:
        img = Image.new("RGB", (500, 400), (30,30,30))

    img.thumbnail((600, 600), Image.LANCZOS)
    w, h = img.size
    draw = ImageDraw.Draw(img)
    font_size = max(28, w // 12)
    font = _get_font(font_size)

    def draw_centered(text, y):
        wrapped = textwrap.fill(text.upper(), width=20)
        lines = wrapped.split("\n")
        for i, line in enumerate(lines):
            bb = draw.textbbox((0,0), line, font=font)
            lw = bb[2]-bb[0]
            lh = bb[3]-bb[1]
            _draw_outlined(draw, ((w-lw)//2, y + i*(lh+4)), line, font)

    if top_text:
        draw_centered(top_text, 10)
    if bottom_text:
        wrapped = textwrap.fill(bottom_text.upper(), width=20)
        lines = wrapped.split("\n")
        bb = draw.textbbox((0,0), "A", font=font)
        lh = bb[3]-bb[1]+4
        draw_centered(bottom_text, h - len(lines)*lh - 15)

    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=88)
    return buf.getvalue()


def make_collage(image_bytes_list: list[bytes]) -> bytes:
    imgs = []
    for b in image_bytes_list:
        try:
            im = Image.open(io.BytesIO(b)).convert("RGB")
            im.thumbnail((400, 400), Image.LANCZOS)
            imgs.append(im)
        except Exception:
            continue
    if not imgs:
        blank = Image.new("RGB", (400,300), (20,20,20))
        buf = io.BytesIO()
        blank.save(buf, format="JPEG")
        return buf.getvalue()
    gap = 4
    total_w = sum(im.width for im in imgs) + gap*(len(imgs)-1)
    max_h = max(im.height for im in imgs)
    canvas = Image.new("RGB", (total_w, max_h), (0,0,0))
    x = 0
    for im in imgs:
        canvas.paste(im, (x, (max_h-im.height)//2))
        x += im.width + gap
    buf = io.BytesIO()
    canvas.save(buf, format="JPEG", quality=85)
    return buf.getvalue()
