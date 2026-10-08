"""Downloads one real photo per picture key into static/products/photos/<key>.jpg.

Only public-domain / CC0 photos (Openverse, license=cc0,pdm), so they can be shipped and changed freely.
Each is cropped to 4:3 and saved small (~30 KB). Credits go to static/products/photos/CREDITS.json.
Keys without a good photo keep their illustration. Run with --only haircut,milk to redo a few.
"""
import io
import json
import time
from pathlib import Path

import requests
from django.conf import settings
from django.core.management.base import BaseCommand
from PIL import Image, ImageOps

from apps.inventory.pictures import ART

API = "https://api.openverse.org/v1/images/"
# better search words where the key name alone is vague
QUERY = {
    "haircut": "barber haircut", "beard": "beard trim barber", "hair_colour": "hair coloring salon",
    "hair_care": "shampoo bottles", "massage": "massage spa", "facial": "facial treatment spa", "nails": "manicure",
    "makeup": "makeup cosmetics", "threading": "eyebrow", "bath": "spa bath", "candle": "scented candle",
    "stone": "hot stone massage", "perfume": "perfume bottle", "shirt": "dress shirt", "tshirt": "t-shirt",
    "dress": "dress fashion", "saree": "saree", "trousers": "jeans", "kids_wear": "baby clothes", "shoes": "sneakers",
    "sandals": "sandals", "bag": "handbag", "scarf": "scarf", "belt": "leather belt", "fabric": "fabric rolls",
    "cap": "baseball cap", "glasses": "eyeglasses", "sunglasses": "sunglasses", "watch": "wristwatch", "ring": "diamond ring",
    "jewel": "gold jewellery", "phone": "smartphone", "charger": "phone charger", "headphones": "earbuds",
    "speaker": "bluetooth speaker", "laptop": "laptop", "monitor": "television", "mouse": "computer mouse",
    "battery": "power bank", "storage": "external hard drive", "camera": "camera photography", "printer": "printer",
    "glass_guard": "phone case", "repair": "repair tools workshop", "ac": "air conditioner", "washing": "laundry",
    "microwave": "microwave oven", "milk": "milk glass", "bread": "bread loaf", "cake": "chocolate cake",
    "croissant": "croissant", "cookies": "cookies", "rice": "rice", "oil": "cooking oil bottle", "sugar": "spices",
    "tea": "cup of tea", "banana": "bananas", "apple": "red apples", "tomato": "tomatoes", "onion": "onions",
    "fish": "fresh fish market", "chicken": "raw chicken", "meat": "raw meat butcher", "water": "bottled water",
    "cleaning": "cleaning supplies", "protein": "protein powder", "medicine": "pills tablets", "syrup": "laboratory test tubes",
    "thermometer": "thermometer", "doctor": "doctor stethoscope", "tooth": "dentist", "wheelchair": "wheelchair",
    "pet": "dog grooming", "gym": "gym dumbbells", "football": "football ball", "cricket": "cricket bat",
    "badminton": "badminton racket", "bicycle": "bicycle", "helmet": "bicycle helmet", "pass": "ticket",
    "gloves": "gloves", "paint": "paint cans", "drill": "power drill", "tape": "measuring tape", "bulb": "light bulb",
    "wire": "electrical wire", "pipe": "plumbing pipes", "cement": "cement bags", "sofa": "sofa", "table": "dining table",
    "pan": "frying pan", "car": "car", "tyre": "car tyre", "brake": "car parts", "fuel": "fuel pump", "motor_oil": "motor oil",
    "wiper": "windshield wiper", "air_freshener": "garden plants", "flowers": "bouquet roses", "gift": "gift box",
    "teddy": "teddy bear", "blocks": "toy blocks", "diaper": "baby products", "book": "books", "notebook": "stationery",
    "guitar": "acoustic guitar", "keyboard_music": "piano keyboard", "seeds": "seedlings", "room": "hotel room",
    "hall": "banquet hall", "desk": "coworking office", "equipment": "construction machinery", "food_service": "buffet",
    "transport": "delivery truck", "plane": "airplane travel", "document": "documents paperwork", "insurance": "insurance",
    "bug": "pest control", "course": "classroom", "driving": "driving lesson car", "house": "apartment building",
    "website": "website laptop", "code": "programming code", "megaphone": "marketing", "chart": "accounting calculator",
    "people": "team people", "party": "party balloons", "broom": "cleaning office", "wrench": "maintenance worker",
    "design": "interior design", "fee": "payment card", "package": "gift card", "box": "cardboard box",
}


def _square(data):
    im = ImageOps.exif_transpose(Image.open(io.BytesIO(data))).convert("RGB")
    return ImageOps.fit(im, (480, 360), Image.LANCZOS, centering=(0.5, 0.45))


class Command(BaseCommand):
    help = "Download public-domain photos for the default product pictures (needs network access)."

    def add_arguments(self, parser):
        parser.add_argument("--only", default="", help="comma-separated keys")

    def handle(self, *args, only="", **options):
        out = Path(settings.BASE_DIR) / "static" / "products" / "photos"
        out.mkdir(parents=True, exist_ok=True)
        credits_file = out / "CREDITS.json"
        credits = json.loads(credits_file.read_text()) if credits_file.exists() else {}
        keys = [k for k, _e, _w in ART if not only or k in only.split(",")]
        session = requests.Session()
        session.headers["User-Agent"] = "BookPilot product pictures (contact: support)"
        done = 0
        for key in keys:
            query = QUERY.get(key, key.replace("_", " "))
            try:
                r = session.get(API, params={"q": query, "license": "cc0,pdm", "page_size": 8,
                                             "aspect_ratio": "wide,square", "size": "medium,large"}, timeout=20)
                r.raise_for_status()
                results = r.json().get("results", [])
            except Exception as exc:
                self.stderr.write(f"{key}: search failed ({exc})")
                continue
            for item in results:
                try:
                    img = session.get(item["url"], timeout=30)
                    img.raise_for_status()
                    _square(img.content).save(out / f"{key}.jpg", "JPEG", quality=78, optimize=True, progressive=True)
                except Exception:
                    continue
                credits[key] = {"title": item.get("title"), "creator": item.get("creator"), "license": item.get("license"),
                                "source": item.get("foreign_landing_url") or item.get("url")}
                done += 1
                self.stdout.write(f"{key}: {item.get('title')!r} ({item.get('license')})")
                break
            else:
                self.stderr.write(f"{key}: no usable photo, keeping the illustration")
            time.sleep(0.4)
        credits_file.write_text(json.dumps(credits, indent=1, ensure_ascii=False))
        self.stdout.write(f"{done} photos saved in {out}")
