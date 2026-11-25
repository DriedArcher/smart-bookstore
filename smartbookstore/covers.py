import hashlib
import textwrap
from PIL import Image, ImageDraw, ImageFont

W, H = 300, 450


def _font(size):
    try:
        return ImageFont.truetype("DejaVuSans-Bold.ttf", size)
    except OSError:
        return ImageFont.load_default(size)


def makeCover(title, author, path, seedText=None):
    h = hashlib.md5((seedText or title).encode()).digest()
    base = (40 + h[0] % 160, 40 + h[1] % 160, 40 + h[2] % 160)
    accent = (255 - base[0], 255 - base[1] // 2, 255 - base[2])
    img = Image.new("RGB", (W, H), base)
    d = ImageDraw.Draw(img)
    style = h[3] % 4
    for i in range(0, H, 6):
        t = i / H
        d.line([(0, i), (W, i)], fill=tuple(int(base[c] * (1 - 0.45 * t)) for c in range(3)))
    if style == 0:
        for k in range(6):
            x = 20 + (h[4 + k] % 5) * 50
            d.ellipse([x, 250 + k * 12, x + 60 + k * 8, 310 + k * 12], outline=accent, width=3)
    elif style == 1:
        for k in range(9):
            d.rectangle([20 + k * 30, 260, 40 + k * 30, 260 + 20 + (h[5 + k % 8] % 120)], fill=accent)
    elif style == 2:
        for k in range(7):
            d.polygon([(150, 250 + k * 8), (30 + k * 6, 420), (270 - k * 6, 420)], outline=accent)
    else:
        for k in range(12):
            d.line([(0, 250 + k * 16), (W, 270 + (h[6 + k % 8] % 120))], fill=accent, width=3)
    d.rectangle([10, 10, W - 10, H - 10], outline=accent, width=3)
    y = 40
    for line in textwrap.wrap(title, 16)[:4]:
        d.text((24, y), line, font=_font(26), fill=(255, 255, 255))
        y += 34
    d.text((24, H - 50), author[:28], font=_font(16), fill=(240, 240, 240))
    img.save(path)
    return path
