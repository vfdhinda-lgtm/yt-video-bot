"""Makes a 1280x720 thumbnail: AI image + big bold text."""
import os

from PIL import Image, ImageDraw, ImageFont

FONTS = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "C:/Windows/Fonts/impact.ttf",
    "C:/Windows/Fonts/arialbd.ttf",
]


def _font(size):
    for f in FONTS:
        if os.path.exists(f):
            return ImageFont.truetype(f, size)
    return ImageFont.load_default()


def make(image_path, text, out):
    img = Image.open(image_path).convert("RGB").resize((1280, 720), Image.LANCZOS)
    shade = Image.new("L", (1280, 720), 0)
    d = ImageDraw.Draw(shade)
    for x in range(1280):  # dark on the left where the text goes
        d.line([(x, 0), (x, 720)], fill=max(0, 190 - x // 4))
    img = Image.composite(Image.new("RGB", img.size, "black"), img, shade)

    draw = ImageDraw.Draw(img)
    words = text.upper().split()[:4] or ["YOUR LIFE"]
    lines = [" ".join(words[:2]), " ".join(words[2:])] if len(words) > 2 else [" ".join(words)]
    size = 130
    font = _font(size)
    while max(draw.textlength(l, font=font) for l in lines) > 700 and size > 60:
        size -= 6
        font = _font(size)
    y = 360 - (len(lines) * (size + 20)) // 2
    for n, line in enumerate(lines):
        draw.text((60, y), line, font=font, fill="#FFD400" if n == 0 else "white",
                  stroke_width=8, stroke_fill="black")
        y += size + 20
    img.save(out, "JPEG", quality=90)
    return out
