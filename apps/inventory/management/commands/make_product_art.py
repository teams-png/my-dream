"""Draws the default product / service pictures (static/products/<key>.webp) from apps.inventory.pictures.ART.

Needs the Noto Color Emoji font (fonts-noto-color-emoji). The PNGs are committed, so servers never run this.
"""
import colorsys
import hashlib
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from apps.inventory.pictures import ART

FONT = "/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf"
SIZE = 256


def _hue(key):
    return int(hashlib.md5(key.encode()).hexdigest()[:4], 16) / 65535


def draw(key, emoji):
    h = _hue(key)
    top = tuple(int(c * 255) for c in colorsys.hls_to_rgb(h, 0.90, 0.75))
    bottom = tuple(int(c * 255) for c in colorsys.hls_to_rgb((h + 0.06) % 1, 0.78, 0.65))
    bg = Image.new("RGB", (SIZE, SIZE), top)
    px = ImageDraw.Draw(bg)
    for y in range(SIZE):  # soft vertical gradient
        t = y / (SIZE - 1)
        px.line([(0, y), (SIZE, y)], fill=tuple(int(a + (b - a) * t) for a, b in zip(top, bottom)))
    glow = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    ImageDraw.Draw(glow).ellipse((48, 40, 208, 200), fill=(255, 255, 255, 120))
    bg = Image.alpha_composite(bg.convert("RGBA"), glow.filter(ImageFilter.GaussianBlur(18)))

    font = ImageFont.truetype(FONT, 109)
    art = Image.new("RGBA", (160, 160), (0, 0, 0, 0))
    ImageDraw.Draw(art).text((80, 80), emoji, font=font, embedded_color=True, anchor="mm")
    art = art.crop(art.getbbox() or (0, 0, 160, 160))
    scale = 150 / max(art.size)
    art = art.resize((max(1, int(art.width * scale)), max(1, int(art.height * scale))), Image.LANCZOS)
    shadow = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    alpha = art.split()[3].point(lambda a: a * 0.25)
    shadow.paste((0, 0, 0, 255), ((SIZE - art.width) // 2, (SIZE - art.height) // 2 + 10), alpha)
    bg = Image.alpha_composite(bg, shadow.filter(ImageFilter.GaussianBlur(8)))
    bg.alpha_composite(art, ((SIZE - art.width) // 2, (SIZE - art.height) // 2))
    return bg.convert("RGB")


class Command(BaseCommand):
    help = "Draw the default product and service pictures into static/products/."

    def handle(self, *args, **options):
        out = Path(settings.BASE_DIR) / "static" / "products"
        out.mkdir(parents=True, exist_ok=True)
        for key, emoji, _words in ART:
            draw(key, emoji).save(out / f"{key}.webp", "WEBP", quality=80, method=6)
        self.stdout.write(f"{len(ART)} pictures in {out}")
