"""Salon, spa and beauty services take an optional photo, shown wherever the service is sold."""
import io

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import Client, override_settings
from django.urls import reverse
from PIL import Image

from apps.accounts.models import User
from apps.modules.models import BusinessType
from apps.tenants.services import create_company_with_owner, provision_company_basics

pytestmark = pytest.mark.django_db


def _png(name="massage.png", colour=(200, 120, 90)):
    buf = io.BytesIO()
    Image.new("RGB", (60, 40), colour).save(buf, "PNG")
    return SimpleUploadedFile(name, buf.getvalue(), content_type="image/png")


@pytest.mark.parametrize("code,prefix", [("spa", "spa"), ("saloon", "saloon"), ("beauty_parlour", "beauty")])
def test_service_photo_upload_change_and_remove(tmp_path, code, prefix):
    call_command("seed_platform")
    user = User.objects.create_user(username=f"o@{code}.test", email=f"o@{code}.test", password="Pass-2026-xyz!")
    bt, _ = BusinessType.objects.get_or_create(code=code, defaults={"name": code})
    company = create_company_with_owner(user=user, name=code, slug=code.replace("_", "-"), business_type=bt,
                                        country="Qatar", phone="", email=user.email, default_currency="QAR")
    provision_company_basics(company=company)
    c = Client()
    c.force_login(user)
    with override_settings(MEDIA_ROOT=tmp_path):
        form = c.get(reverse(f"webapp:{prefix}_service_add")).content.decode()
        assert 'enctype="multipart/form-data"' in form and 'name="photo"' in form
        r = c.post(reverse(f"webapp:{prefix}_service_add"),
                   {"name": "Signature massage", "duration_minutes": 60, "price": "150", "photo": _png()})
        assert r.status_code == 302, r.content
        from apps.inventory.models import Product
        product = Product.objects.get(company=company, name__endswith="Signature massage")
        assert product.image and product.image.name.endswith(".png")
        listing = c.get(reverse(f"webapp:{prefix}_service_list")).content.decode()
        assert product.image.url in listing

        related = {"spa": "spa_service", "saloon": "saloon_service", "beauty_parlour": "beauty_service"}[code]
        service_id = getattr(product, related).id
        edit_url = reverse(f"webapp:{prefix}_service_edit", args=[service_id])
        assert product.image.url in c.get(edit_url).content.decode()
        c.post(edit_url, {"name": "Signature massage", "duration_minutes": 60, "price": "150", "remove_photo": "on"})
        product.refresh_from_db()
        assert not product.image

        bad = c.post(reverse(f"webapp:{prefix}_service_add"), {"name": "X", "duration_minutes": 30, "price": "10",
                                                               "photo": SimpleUploadedFile("x.png", b"not an image")})
        assert bad.status_code == 200 and not Product.objects.filter(company=company, name__endswith="— X").exists()
