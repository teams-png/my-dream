"""Draws the illustrations for the Kerala starter menu into static/restaurant/kerala/<code>.png.
Run once after changing kerala_menu.DISHES; the PNGs are committed so sign-up never draws anything."""
import random
from pathlib import Path

from django.core.management.base import BaseCommand

from apps.verticals.restaurant.kerala_menu import DISHES

W, H, S = 480, 360, 2  # output size and supersampling


def rgb(hex_colour):
    hex_colour = hex_colour.lstrip("#")
    return tuple(int(hex_colour[i:i + 2], 16) for i in (0, 2, 4))


def shade(c, f):
    return tuple(max(0, min(255, int(v * f))) for v in c)


def mix(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


class Art:
    def __init__(self, colour, seed):
        from PIL import Image, ImageDraw
        self.Image = Image
        self.c = rgb(colour)
        self.rnd = random.Random(seed)
        self.img = Image.new("RGB", (W * S, H * S))
        self.d = ImageDraw.Draw(self.img)
        self.background()

    def s(self, *v):
        return [int(x * S) for x in v]

    def background(self):
        top, bottom = mix(self.c, (255, 247, 235), 0.82), mix(self.c, (255, 236, 214), 0.65)
        for y in range(H * S):
            self.d.line([(0, y), (W * S, y)], fill=mix(top, bottom, y / (H * S)))
        for _ in range(26):  # soft confetti of spices
            x, y, r = self.rnd.randint(0, W), self.rnd.randint(0, H), self.rnd.randint(2, 5)
            self.d.ellipse(self.s(x - r, y - r, x + r, y + r), fill=mix(self.c, (255, 255, 255), 0.55))

    def ellipse(self, box, fill, outline=None, width=0):
        self.d.ellipse(self.s(*box), fill=fill, outline=outline, width=width * S)

    def shadow(self, cx, cy, rx, ry):
        self.ellipse((cx - rx, cy - ry + 14, cx + rx, cy + ry + 14), fill=(0, 0, 0) if False else mix(self.c, (60, 40, 30), 0.25))

    def plate(self, cx=240, cy=200, rx=170, ry=118):
        self.shadow(cx, cy, rx, ry)
        self.ellipse((cx - rx, cy - ry, cx + rx, cy + ry), fill=(250, 250, 248), outline=(225, 225, 222), width=3)
        self.ellipse((cx - rx + 26, cy - ry + 20, cx + rx - 26, cy + ry - 20), fill=(244, 244, 240))

    def leaf(self):
        green, dark = (64, 140, 52), (40, 104, 36)
        self.d.polygon([tuple(self.s(x, y)) for x, y in ((24, 210), (120, 70), (460, 60), (470, 300), (60, 330))], fill=green)
        self.d.line(self.s(30, 270, 465, 120), fill=dark, width=6 * S)
        for i in range(9):
            x = 70 + i * 45
            self.d.line(self.s(x, 270 - i * 17, x + 30, 300 - i * 6), fill=dark, width=2 * S)

    def blobs(self, cx, cy, rx, ry, n, colour, size=(16, 30)):
        for _ in range(n):
            a, b = self.rnd.uniform(-1, 1), self.rnd.uniform(-1, 1)
            if a * a + b * b > 1:
                continue
            x, y, r = cx + a * rx, cy + b * ry, self.rnd.randint(*size)
            col = shade(colour, self.rnd.uniform(0.75, 1.12))
            self.ellipse((x - r, y - r * 0.8, x + r, y + r * 0.8), fill=col)

    def leaves(self, cx, cy, rx, ry, n=6):
        for _ in range(n):
            x, y = cx + self.rnd.uniform(-rx, rx), cy + self.rnd.uniform(-ry, ry)
            self.ellipse((x - 9, y - 4, x + 9, y + 4), fill=(46, 125, 50))

    # ------------------------------------------------------------- styles
    def rice(self):
        self.plate()
        self.blobs(240, 190, 120, 70, 260, (250, 236, 200), (5, 8))
        self.blobs(240, 185, 105, 60, 70, self.c, (5, 8))
        self.blobs(240, 180, 70, 40, 6, shade(self.c, 0.55), (22, 30))
        self.blobs(240, 175, 100, 55, 30, (122, 70, 30), (4, 7))  # fried onions
        self.blobs(240, 175, 90, 50, 10, (240, 220, 170), (6, 9))  # cashews
        self.leaves(240, 180, 90, 55, 8)

    def curry(self):
        self.shadow(240, 200, 150, 100)
        self.ellipse((90, 100, 390, 300), fill=(236, 233, 228), outline=(205, 200, 195), width=3)
        self.ellipse((112, 116, 368, 280), fill=self.c)
        self.ellipse((150, 140, 330, 250), fill=shade(self.c, 1.08))
        self.blobs(240, 195, 95, 55, 12, shade(self.c, 0.6), (14, 24))
        self.blobs(240, 195, 100, 60, 18, mix(self.c, (255, 240, 200), 0.5), (3, 6))
        self.leaves(240, 190, 90, 50, 7)

    def fry(self):
        self.plate()
        self.blobs(240, 190, 115, 65, 34, self.c, (16, 28))
        self.blobs(240, 190, 110, 60, 20, shade(self.c, 0.7), (8, 14))
        self.leaves(240, 185, 110, 60, 10)
        for _ in range(3):  # onion rings
            x, y = self.rnd.randint(170, 310), self.rnd.randint(150, 230)
            self.ellipse((x - 16, y - 10, x + 16, y + 10), fill=None, outline=(235, 170, 200), width=3)

    def bread(self):
        self.plate()
        for i in range(3):
            y = 205 - i * 18
            self.ellipse((130 + i * 8, y - 55, 350 - i * 8, y + 55), fill=shade(self.c, 0.88 + i * 0.06),
                         outline=shade(self.c, 0.7), width=2)
            for k in range(5):
                self.d.arc(self.s(160 + i * 8 + k * 6, y - 40 + k * 4, 320 - i * 8 - k * 6, y + 40 - k * 4), 200, 340,
                           fill=shade(self.c, 0.72), width=2 * S)

    def dosa(self):
        self.plate(rx=200, ry=110)
        self.d.polygon([tuple(self.s(x, y)) for x, y in ((70, 215), (240, 120), (410, 160), (395, 215), (230, 265))],
                       fill=self.c, outline=shade(self.c, 0.75))
        self.d.line(self.s(80, 214, 400, 190), fill=shade(self.c, 0.7), width=3 * S)
        for x, colour in ((130, (240, 240, 230)), (200, (200, 120, 40)), (270, (110, 170, 80))):  # chutneys
            self.ellipse((x - 24, 262, x + 24, 300), fill=(230, 230, 225))
            self.ellipse((x - 18, 266, x + 18, 296), fill=colour)

    def breakfast(self):
        self.plate()
        self.ellipse((140, 140, 250, 260), fill=self.c, outline=shade(self.c, 0.85), width=2)
        self.ellipse((160, 150, 230, 210), fill=shade(self.c, 1.04))
        self.ellipse((255, 150, 370, 250), fill=(232, 232, 228))
        self.ellipse((265, 158, 360, 242), fill=(150, 80, 40))
        self.blobs(312, 200, 35, 30, 10, (110, 55, 25), (8, 12))
        self.leaves(310, 195, 40, 30, 4)

    def meals(self):
        self.leaf()
        self.ellipse((150, 140, 330, 270), fill=(206, 160, 130))  # matta rice
        self.blobs(240, 205, 80, 55, 160, (214, 168, 138), (4, 7))
        cups = [(110, 125, self.c), (380, 120, (200, 120, 40)), (400, 220, (233, 220, 150)), (90, 245, (160, 200, 90))]
        for x, y, colour in cups:
            self.ellipse((x - 38, y - 30, x + 38, y + 30), fill=(238, 236, 232))
            self.ellipse((x - 30, y - 23, x + 30, y + 23), fill=colour)
        self.ellipse((300, 260, 370, 300), fill=(245, 225, 160))  # pappadam

    def fish(self):
        self.plate(rx=190)
        body = [(110, 200), (180, 150), (300, 150), (360, 195), (300, 245), (180, 245)]
        self.d.polygon([tuple(self.s(x, y)) for x, y in body], fill=self.c)
        self.d.polygon([tuple(self.s(x, y)) for x, y in ((355, 195), (410, 155), (400, 240))], fill=shade(self.c, 0.8))
        self.ellipse((140, 185, 156, 200), fill=(250, 250, 250))
        for k in range(5):
            self.d.line(self.s(190 + k * 25, 165, 180 + k * 25, 230), fill=shade(self.c, 0.65), width=3 * S)
        self.blobs(240, 260, 120, 12, 10, (250, 240, 120), (6, 9))  # lemon
        self.leaves(250, 200, 120, 50, 8)

    def glass(self):
        self.shadow(240, 300, 90, 20)
        self.d.polygon([tuple(self.s(x, y)) for x, y in ((170, 60), (310, 60), (290, 315), (190, 315))], fill=(235, 245, 250),
                       outline=(200, 215, 225))
        self.d.polygon([tuple(self.s(x, y)) for x, y in ((178, 100), (302, 100), (288, 305), (192, 305))], fill=self.c)
        self.d.polygon([tuple(self.s(x, y)) for x, y in ((185, 100), (215, 100), (205, 300), (195, 300))],
                       fill=mix(self.c, (255, 255, 255), 0.45))
        self.d.line(self.s(265, 30, 245, 200), fill=(230, 60, 60), width=7 * S)  # straw
        self.ellipse((285, 70, 335, 110), fill=(160, 210, 80))

    def cup(self):
        self.shadow(240, 270, 120, 26)
        self.ellipse((110, 240, 370, 300), fill=(240, 238, 234), outline=(215, 212, 208), width=2)
        self.d.polygon([tuple(self.s(x, y)) for x, y in ((165, 120), (315, 120), (300, 275), (180, 275))], fill=(250, 250, 250),
                       outline=(220, 220, 220))
        self.d.arc(self.s(295, 150, 360, 230), 270, 90, fill=(225, 225, 225), width=10 * S)
        self.ellipse((165, 108, 315, 140), fill=self.c)
        self.ellipse((190, 115, 240, 128), fill=mix(self.c, (255, 255, 255), 0.4))
        for k in range(3):  # steam
            self.d.arc(self.s(195 + k * 30, 40, 225 + k * 30, 100), 100, 260, fill=(255, 255, 255), width=4 * S)

    def dessert(self):
        self.shadow(240, 210, 140, 80)
        self.ellipse((110, 120, 370, 290), fill=(236, 232, 226), outline=(205, 200, 195), width=3)
        self.ellipse((130, 135, 350, 270), fill=self.c)
        self.blobs(240, 200, 85, 45, 14, (245, 230, 190), (6, 10))  # cashews
        self.blobs(240, 200, 85, 45, 10, (110, 50, 40), (4, 7))  # raisins

    def snack(self):
        self.plate()
        for _ in range(5):
            x, y = self.rnd.randint(165, 315), self.rnd.randint(150, 235)
            self.ellipse((x - 42, y - 28, x + 42, y + 28), fill=self.c, outline=shade(self.c, 0.7), width=2)
            self.blobs(x, y, 30, 18, 6, shade(self.c, 0.8), (3, 6))

    def roll(self):
        self.plate()
        for k in range(2):
            y = 175 + k * 50
            self.d.rounded_rectangle(self.s(120, y - 24, 360, y + 24), radius=24 * S, fill=self.c, outline=shade(self.c, 0.75))
            self.ellipse((345, y - 24, 385, y + 24), fill=(240, 230, 210))
            self.blobs(365, y, 12, 14, 6, (150, 80, 40), (3, 6))
            self.leaves(365, y, 10, 12, 2)

    def grill(self):
        self.plate(rx=190)
        self.blobs(230, 190, 95, 55, 6, self.c, (40, 55))
        for k in range(6):
            self.d.line(self.s(150 + k * 25, 150, 175 + k * 25, 235), fill=shade(self.c, 0.45), width=5 * S)
        self.ellipse((330, 165, 390, 215), fill=(250, 250, 245))  # garlic sauce
        self.blobs(320, 250, 50, 12, 10, (245, 200, 80), (6, 10))  # fries
        self.leaves(220, 250, 80, 15, 6)

    def save(self, path):
        self.img.resize((W, H), self.Image.LANCZOS).quantize(colors=96, method=2).save(path, optimize=True)


class Command(BaseCommand):
    help = "Draw illustrations for the Kerala starter menu"

    def handle(self, *args, **options):
        out = Path(__file__).resolve().parents[5] / "static" / "restaurant" / "kerala"
        out.mkdir(parents=True, exist_ok=True)
        count = 0
        for category, rows in DISHES.items():
            for code, _name, _ml, _price, _desc, _veg, _spice, _prep, _feat, art, colour in rows:
                drawing = Art(colour, code)
                getattr(drawing, art)()
                drawing.save(out / f"{code}.png")
                count += 1
        self.stdout.write(self.style.SUCCESS(f"{count} illustrations written to {out}"))
