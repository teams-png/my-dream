"""Every product and service gets a picture: its photo, or an illustration chosen from its name."""
from pathlib import Path

from django.conf import settings

from apps.industry import sample_catalog
from apps.inventory.pictures import ART, pick


def test_every_picture_file_exists_without_a_background():
    from PIL import Image
    folder = Path(settings.BASE_DIR) / "static" / "products" / "cut"
    missing = [key for key, _e, _w in ART if not (folder / f"{key}.webp").exists()]
    assert not missing
    with Image.open(folder / "haircut.webp") as im:
        assert im.mode == "RGBA" and im.getpixel((0, 0))[3] == 0  # transparent corner
    assert (folder / "LICENSE.txt").exists()


def test_names_pick_sensible_pictures():
    assert pick("Haircut + beard") == "haircut"
    assert pick("Beard oil 30ml") == "beard"
    assert pick("Men's cotton shirt") == "shirt"
    assert pick("Samsung Galaxy A15 128GB") == "phone"
    assert pick("Paracetamol 500mg (24 tablets)") == "medicine"
    assert pick("Fresh milk 1L") == "milk"
    assert pick("Swedish massage – 60 min") == "massage"
    assert pick("Room 101 – Deluxe") == "room"
    assert pick("Something new", "Shoes") == "shoes"          # falls back to the category
    assert pick("Mystery item", "", "saloon") == "haircut"      # then the business type
    assert pick("Mystery item") == "box"
    assert pick("Chicken biryani") == "biryani" and pick("Masala dosa") == "dosa" and pick("Fresh lime juice") == "juice"
    assert pick("Karak chai") == "coffee" and pick("Chicken shawarma") == "shawarma"


def test_sample_items_mostly_get_their_own_picture():
    rows = []
    for kit in sample_catalog.KITS.values():
        rows += kit.get("products", []) + kit.get("variants", []) + kit.get("services", [])
    for items in sample_catalog.SALON_SERVICES.values():
        rows += items
    for items in sample_catalog.SERVICE_KITS.values():
        rows += items
    generic = [r["name"] for r in rows if pick(r["name"], r["category"]) == "box"]
    assert len(generic) <= len(rows) * 0.05, generic
