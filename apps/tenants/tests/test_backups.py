"""Automatic daily backups: private files, owner-only download, pruning, daily run and Google Drive copy."""
import io
import json
import zipfile
from datetime import timedelta
from unittest import mock

import pytest
from django.contrib.auth import get_user_model
from django.core import signing
from django.core.management import call_command
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone

from apps.modules.models import BusinessType
from apps.tenants import backups as svc
from apps.tenants.models import CompanyBackup, CompanyMembership, Role
from apps.tenants.services import create_company_with_owner

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def private_folder(tmp_path, settings):
    settings.BACKUP_ROOT = str(tmp_path / "backups")
    call_command("seed_platform")


def _company(slug, code="supermarket"):
    user = get_user_model().objects.create_user(username=f"o-{slug}", email=f"{slug}@t.qa", password="Pass-12345!")
    company = create_company_with_owner(user=user, name=f"Biz {slug}", slug=slug, business_type=BusinessType.objects.get(code=code))
    return company, user


def test_owner_backs_up_now_and_downloads(client):
    company, owner = _company("b1")
    client.force_login(owner)
    assert client.get(reverse("webapp:backups")).status_code == 200
    client.post(reverse("webapp:backups"), {"action": "now"})
    backup = CompanyBackup.objects.get(company=company)
    assert backup.status == "ok" and backup.kind == "manual" and backup.rows > 0
    response = client.get(reverse("webapp:backup_download", args=[backup.id]))
    data = b"".join(response.streaming_content)
    manifest = json.loads(zipfile.ZipFile(io.BytesIO(data)).read("manifest.json"))
    assert manifest["company"] == "Biz b1"
    # staff and other businesses can't get it
    staff = get_user_model().objects.create_user(username="st", email="st@t.qa", password="Pass-12345!")
    CompanyMembership.objects.create(company=company, user=staff, role=Role.objects.get(company=company, name="Staff"))
    client.force_login(staff)
    assert client.get(reverse("webapp:backup_download", args=[backup.id])).status_code == 403
    _other, other_owner = _company("b2")
    client.force_login(other_owner)
    assert client.get(reverse("webapp:backup_download", args=[backup.id])).status_code == 404


def test_daily_run_is_once_a_day_and_respects_the_switch():
    a, _ = _company("d1")
    b, _ = _company("d2")
    svc.settings_for(b).__class__.objects.filter(company=b).update(enabled=False)
    first = svc.run_daily()
    assert first["made"] >= 1 and CompanyBackup.objects.filter(company=a).count() == 1
    assert not CompanyBackup.objects.filter(company=b).exists()
    svc.run_daily()
    assert CompanyBackup.objects.filter(company=a).count() == 1


def test_old_backups_are_pruned_but_monthly_and_newest_kept():
    company, _ = _company("p1")
    now = timezone.now()
    ages = [0, 1, 2, 10, 20, 40, 400]
    made = []
    for days in ages:
        b = svc.make_backup(company)
        CompanyBackup.objects.filter(pk=b.pk).update(created_at=now - timedelta(days=days))
        made.append(b.pk)
    svc.settings_for(company).__class__.objects.filter(company=company).update(keep_days=7)
    svc.prune(company, now=now)
    left = set(CompanyBackup.objects.filter(company=company).values_list("pk", flat=True))
    assert {made[0], made[1], made[2]} <= left           # newest and within 7 days
    assert made[6] not in left                           # older than a year
    assert len(left) < len(made)


@override_settings(GOOGLE_OAUTH_CLIENT_ID="cid", GOOGLE_OAUTH_CLIENT_SECRET="secret")
def test_google_drive_connect_and_copy(client):
    company, owner = _company("g1")
    client.force_login(owner)
    response = client.post(reverse("webapp:backups"), {"action": "drive_connect"})
    assert response.status_code == 302 and response["Location"].startswith(svc.GOOGLE_AUTH)
    state = signing.dumps({"c": company.pk, "u": owner.pk}, salt="bookpilot-drive-backup")

    def fake_post(url, data=None, json=None, headers=None, params=None, timeout=None):
        r = mock.Mock(status_code=200, headers={"Location": "https://upload.example/session"})
        if url == svc.GOOGLE_TOKEN and data.get("grant_type") == "authorization_code":
            payload = "e30." + __import__("base64").urlsafe_b64encode(b'{"email":"owner@gmail.com"}').decode().rstrip("=") + ".sig"
            r.json.return_value = {"refresh_token": "r-token", "access_token": "a", "id_token": payload}
        elif url == svc.GOOGLE_TOKEN:
            r.json.return_value = {"access_token": "a-token"}
        elif url == svc.DRIVE_FILES:
            r.json.return_value = {"id": "folder-1"}
        else:
            r.json.return_value = {}
        return r

    put = mock.Mock(return_value=mock.Mock(status_code=200, json=lambda: {"id": "file-9"}))
    with mock.patch("requests.post", side_effect=fake_post), mock.patch("requests.put", put):
        client.get(reverse("webapp:backup_drive_callback"), {"code": "abc", "state": state})
        prefs = svc.settings_for(company)
        assert prefs.drive_enabled and prefs.drive_email == "owner@gmail.com" and prefs.drive_refresh_token.startswith("v1:")
        assert svc.unseal(prefs.drive_refresh_token) == "r-token"
        backup = svc.make_backup(company)
    assert backup.drive_file_id == "file-9" and svc.settings_for(company).drive_folder_id == "folder-1"
    # a forged state is refused
    client.get(reverse("webapp:backup_drive_callback"), {"code": "x", "state": "bad"})
    with mock.patch("requests.post", side_effect=RuntimeError("down")):
        failed_copy = svc.make_backup(company)
    assert failed_copy.status == "ok" and not failed_copy.drive_file_id and "down" in svc.settings_for(company).drive_error


def test_platform_admin_overview(client):
    _company("pa1")
    admin = get_user_model().objects.create_user(username="pa", email="pa@bp.qa", password="Pass-12345!", is_platform_admin=True)
    client.force_login(admin)
    assert client.post(reverse("webapp:platform_backups"), {"action": "run"}).status_code == 302
    page = client.get(reverse("webapp:platform_backups")).content.decode()
    assert "Biz pa1" in page and "Run backups now" in page
