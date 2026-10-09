"""Turns real photos into default product pictures without a background: static/products/photos/<key>.webp.

    pip install "rembg[cpu]"        # once, on your own computer (not needed on the server)
    python manage.py cutout_photos ~/Downloads/photos

Name each photo after its picture key (haircut.jpg, massage.png, biryani.webp …; see `--keys` for the list);
add ".women" (haircut.women.jpg) for the photo ladies' salons and spas should get instead. The background is
removed, slivers of neighbouring pictures along the edges are dropped (photos cut from a sheet), and the object
is centred on a transparent square and saved small. The results are committed, so servers never run this; a
photo here replaces that key's 3D picture everywhere.
"""
from pathlib import Path

import numpy as np
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from PIL import Image, ImageOps

from apps.inventory.pictures import ART

SIZE = 360
TYPES = {".jpg", ".jpeg", ".png", ".webp"}


def main_object(cut):
    """Keep the object in the middle of the photo and what touches it; drop neighbours' slivers along the edges."""
    from scipy import ndimage
    arr = np.array(cut)
    alpha = arr[..., 3]
    labels, count = ndimage.label(alpha > 90)
    if count < 2:
        return cut
    h, w = alpha.shape
    sizes = np.array(ndimage.sum(np.ones_like(alpha), labels, range(1, count + 1)))
    boxes = ndimage.find_objects(labels)

    def centre_score(i):
        box = boxes[i]
        cy, cx = (box[0].start + box[0].stop) / 2 / h, (box[1].start + box[1].stop) / 2 / w
        return sizes[i] * max(0.05, 1 - (((cx - .5) ** 2 + (cy - .5) ** 2) ** .5) * 1.6) ** 2
    best = max(range(count), key=centre_score)
    main = boxes[best]
    keep = np.zeros(alpha.shape, dtype=bool)
    for i, box in enumerate(boxes):
        on_edge = box[1].start <= 1 or box[1].stop >= w - 1 or box[0].start <= 1 or box[0].stop >= h - 1
        near = not (box[1].stop < main[1].start - w * .03 or box[1].start > main[1].stop + w * .03 or
                    box[0].stop < main[0].start - h * .03 or box[0].start > main[0].stop + h * .03)
        if i == best or (near and sizes[i] > sizes[best] * .04 and not (on_edge and sizes[i] < sizes[best] * .5)):
            keep |= labels == i + 1
    arr[~ndimage.binary_dilation(keep, iterations=3), 3] = 0
    return Image.fromarray(arr)


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
        parser.add_argument("--model", default="birefnet-general", help="rembg model (birefnet-general, isnet-general-use …)")

    def handle(self, *args, folder="", keys=False, model="birefnet-general", **options):
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
            name = path.stem.lower().replace(" ", "_").replace("-", "_")
            key = name.removesuffix(".women")
            if key not in known:
                self.stderr.write(f"{path.name}: not a picture key, skipped (see --keys)")
                continue
            photo = ImageOps.exif_transpose(Image.open(path)).convert("RGB")
            if max(photo.size) < 600:  # small photos: the model finds edges better on a larger copy
                factor = 600 / max(photo.size)
                photo = photo.resize((round(photo.width * factor), round(photo.height * factor)), Image.LANCZOS)
            photo.thumbnail((1200, 1200))
            picture = tidy(main_object(remove(photo, session=session).convert("RGBA")))
            if picture is None:
                self.stderr.write(f"{path.name}: nothing found in the photo, skipped")
                continue
            picture.save(out / f"{name}.webp", "WEBP", quality=88, method=6)
            done += 1
            self.stdout.write(f"{name} ✓")
        self.stdout.write(self.style.SUCCESS(f"{done} photos saved in {out}"))
