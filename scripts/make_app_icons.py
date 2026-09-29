"""
Draws the BookPilot app icon (green tile, lime four-point star) at every size
the web app, desktop app and mobile apps need. Run: python scripts/make_app_icons.py
"""
import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parents[1]
DARK, LIGHT, LIME = (8, 39, 26), (47, 158, 90), (198, 244, 50)


def star(draw, cx, cy, r, color):
    pts = []
    for i in range(8):
        ang = -math.pi / 2 + i * math.pi / 4
        rad = r if i % 2 == 0 else r * 0.3
        pts.append((cx + rad * math.cos(ang), cy + rad * math.sin(ang)))
    draw.polygon(pts, fill=color)


def icon(size, *, maskable=False, rounded=True):
    scale = 4  # draw big, shrink for smooth edges
    s = size * scale
    grad = Image.new("RGB", (s, s))
    px = grad.load()
    for y in range(s):
        for x in range(s):
            t = min(1, (x + (s - y)) / (2 * s) * 1.4)
            px[x, y] = tuple(int(DARK[i] + (LIGHT[i] - DARK[i]) * t) for i in range(3))
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    mask = Image.new("L", (s, s), 0)
    radius = 0 if maskable or not rounded else int(s * 0.22)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, s - 1, s - 1), radius=radius, fill=255)
    img.paste(grad, (0, 0), mask)
    glow = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    r = s * (0.26 if maskable else 0.33)  # maskable icons keep the art inside the 80% safe zone
    star(ImageDraw.Draw(glow), s / 2, s / 2, r * 1.05, LIME + (90,))
    img = Image.alpha_composite(img, glow.filter(ImageFilter.GaussianBlur(s * 0.03)))
    star(ImageDraw.Draw(img), s / 2, s / 2, r, LIME + (255,))
    return img.resize((size, size), Image.LANCZOS)


def main():
    out = ROOT / "static" / "icons"
    out.mkdir(parents=True, exist_ok=True)
    for size in (48, 72, 96, 144, 192, 256, 384, 512, 1024):
        icon(size).save(out / f"icon-{size}.png")
    icon(512, maskable=True).save(out / "maskable-512.png")
    icon(192, maskable=True).save(out / "maskable-192.png")
    icon(180, rounded=False).convert("RGB").save(out / "apple-touch-icon.png")
    icon(256).save(out / "favicon.ico", sizes=[(16, 16), (32, 32), (48, 48), (256, 256)])
    print("icons written to", out)


if __name__ == "__main__":
    main()
