"""Turns real photos into default product pictures without a background: static/products/photos/<key>.webp.

    pip install "rembg[cpu]"        # once, on your own computer (not needed on the server)
    python manage.py cutout_photos ~/Downloads/photos

Name each photo after its picture key (haircut.jpg, massage.png, biryani.webp …; see `--keys` for the list).
The background is removed, the object cropped, centred on a transparent square and saved small. The results
are committed, so servers never run this; a photo here replaces that key's 3D picture everywhere.
"""
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from PIL import Image, ImageOps

from apps.inventory.pictures import ART

SIZE = 360
TYPES = {".jpg", ".jpeg", ".png", ".webp"}


def tidy(cut):
    """Firm up the soft edges the model leaves, crop to the object and centre it on a square."""
    alpha = cut.getchannel("A").point(lambda a: 0 if a < 40 else 255 if a > 200 else a)
    cut.putalpha(alpha)
    box = alpha.point(lambda a: 255 if a > 60 else 0).getbbox()
    if not box:
        return None
    cut = cut.crop(box)
    cut.thumbnail((int(SIZE * .9), int(SIZE * .9)), Image.LANCZOS)
    square = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    square.alpha_composite(cut, ((SIZE - cut.width) // 2, (SIZE - cut.height) // 2))
    return square


class Command(BaseCommand):
    help = "Remove the background from photos named <key>.jpg and save them as default product pictures."

    def add_arguments(self, parser):
        parser.add_argument("folder", nargs="?", default="")
        parser.add_argument("--keys", action="store_true", help="list the picture keys and exit")
        parser.add_argument("--model", default="isnet-general-use", help="rembg model (isnet-general-use, u2net, …)")

    def handle(self, *args, folder="", keys=False, model="isnet-general-use", **options):
        known = {k: words for k, _e, words in ART}
        if keys or not folder:
            for key, words in known.items():
                self.stdout.write(f"{key:16} {words}")
            return
        try:
            from rembg import new_session, remove
        except ImportError:
            raise CommandError('Install the background remover first: pip install "rembg[cpu]"')
        out = Path(settings.BASE_DIR) / "static" / "products" / "photos"
        out.mkdir(parents=True, exist_ok=True)
        session = new_session(model)
        done = 0
        for path in sorted(Path(folder).expanduser().iterdir()):
            if path.suffix.lower() not in TYPES:
                continue
            key = path.stem.lower().replace(" ", "_").replace("-", "_")
            if key not in known:
                self.stderr.write(f"{path.name}: not a picture key, skipped (see --keys)")
                continue
            photo = ImageOps.exif_transpose(Image.open(path)).convert("RGB")
            photo.thumbnail((1200, 1200))
            picture = tidy(remove(photo, session=session).convert("RGBA"))
            if picture is None:
                self.stderr.write(f"{path.name}: nothing found in the photo, skipped")
                continue
            picture.save(out / f"{key}.webp", "WEBP", quality=88, method=6)
            done += 1
            self.stdout.write(f"{key} ✓")
        self.stdout.write(self.style.SUCCESS(f"{done} photos saved in {out}"))
