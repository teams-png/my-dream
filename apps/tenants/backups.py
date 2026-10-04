"""
Automatic backups of each business's data.

Every day (run_daily_jobs) each active business gets a zip of all its records (the same file as
"Download all my data") saved in private backup storage — S3 when configured, otherwise a folder on
the server that is never served to the web. Old automatic backups are pruned after the owner's
chosen number of days; the first backup of every month is kept for a year. If the owner connected
Google Drive, every backup is also copied to a "BookPilot backups" folder in their Drive.
"""
import base64
import hashlib
import logging
import os
from datetime import timedelta

from django.conf import settings
from django.core.files.base import ContentFile
from django.utils import timezone

from .models import BackupSettings, Company, CompanyBackup

log = logging.getLogger(__name__)
MIN_KEEP = 3          # never prune below this many backups
MONTHLY_KEEP_DAYS = 366
MAX_MANUAL_PER_DAY = 10


# ------------------------------------------------------------------ storage

def storage():
    from django.core.files.storage import FileSystemStorage, InvalidStorageError, storages
    try:
        return storages["backups"]
    except InvalidStorageError:
        return FileSystemStorage(location=str(getattr(settings, "BACKUP_ROOT", settings.BASE_DIR / "backups")))


def settings_for(company):
    obj, _ = BackupSettings.objects.get_or_create(company=company)
    return obj


# ------------------------------------------------------------------ making backups

def make_backup(company, *, kind="auto", user=None):
    from apps.common.exporting import export_company_zip
    prefs = settings_for(company)
    stamp = timezone.now().strftime("%Y%m%d-%H%M%S")
    record = CompanyBackup(company=company, kind=kind, include_media=prefs.include_media, created_by=user)
    try:
        data, counts = export_company_zip(company, include_media=prefs.include_media)
        name = storage().save(f"{company.pk}-{company.slug}/{company.slug}-{stamp}-{kind}.zip", ContentFile(data))
        record.file_name, record.size = name, len(data)
        record.rows, record.tables = sum(counts.values()), len(counts)
    except Exception as exc:  # one business failing must not stop the others
        log.exception("Backup failed for company %s", company.pk)
        record.status, record.error = "failed", f"{exc.__class__.__name__}: {exc}"[:255]
        record.save()
        return record
    record.save()
    if prefs.drive_enabled and prefs.drive_refresh_token:
        try:
            record.drive_file_id = drive_upload(prefs, record.file_name, data)
            record.save(update_fields=["drive_file_id"])
            if prefs.drive_error:
                BackupSettings.objects.filter(pk=prefs.pk).update(drive_error="")
        except Exception as exc:
            log.warning("Drive copy failed for company %s: %s", company.pk, exc)
            BackupSettings.objects.filter(pk=prefs.pk).update(drive_error=f"{exc}"[:255])
    return record


def open_file(backup):
    return storage().open(backup.file_name, "rb")


def manual_allowed(company):
    since = timezone.now() - timedelta(days=1)
    return CompanyBackup.objects.filter(company=company, kind="manual", created_at__gte=since).count() < MAX_MANUAL_PER_DAY


# ------------------------------------------------------------------ retention

def prune(company, now=None):
    """Deletes automatic backups older than keep_days, keeping the first of each month for a year
    and always the newest MIN_KEEP good backups. Manual backups follow the same rule."""
    now = now or timezone.now()
    prefs = settings_for(company)
    good = list(CompanyBackup.objects.filter(company=company, status="ok").order_by("-created_at"))
    protected = {b.pk for b in good[:MIN_KEEP]}
    first_of_month = {}
    for b in sorted(good, key=lambda b: b.created_at):
        first_of_month.setdefault((b.created_at.year, b.created_at.month), b.pk)
    removed = 0
    for b in good:
        age = now - b.created_at
        if b.pk in protected or age <= timedelta(days=prefs.keep_days):
            continue
        if b.pk in first_of_month.values() and age <= timedelta(days=MONTHLY_KEEP_DAYS):
            continue
        delete_backup(b, prefs)
        removed += 1
    CompanyBackup.objects.filter(company=company, status="failed", created_at__lt=now - timedelta(days=30)).delete()
    return removed


def delete_backup(backup, prefs=None):
    try:
        if backup.file_name:
            storage().delete(backup.file_name)
    except Exception:
        log.warning("Could not delete backup file %s", backup.file_name)
    if backup.drive_file_id:
        prefs = prefs or settings_for(backup.company)
        try:
            drive_delete(prefs, backup.drive_file_id)
        except Exception:
            pass
    backup.delete()


def run_daily():
    """Called from run_daily_jobs: one automatic backup per active business per day."""
    today = timezone.localdate()
    made = failed = 0
    for company in Company.objects.filter(is_active=True):
        prefs = settings_for(company)
        if not prefs.enabled:
            continue
        if CompanyBackup.objects.filter(company=company, kind="auto", status="ok", created_at__date=today).exists():
            continue
        record = make_backup(company)
        made += record.status == "ok"
        failed += record.status != "ok"
        try:
            prune(company)
        except Exception:
            log.exception("Backup pruning failed for company %s", company.pk)
    return {"made": made, "failed": failed}


def status(company):
    last = CompanyBackup.objects.filter(company=company).order_by("-created_at").first()
    last_ok = CompanyBackup.objects.filter(company=company, status="ok").order_by("-created_at").first()
    return {"last": last, "last_ok": last_ok,
            "healthy": bool(last_ok and timezone.now() - last_ok.created_at < timedelta(hours=36))}


# ------------------------------------------------------------------ Google Drive

GOOGLE_AUTH = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN = "https://oauth2.googleapis.com/token"
GOOGLE_REVOKE = "https://oauth2.googleapis.com/revoke"
DRIVE_FILES = "https://www.googleapis.com/drive/v3/files"
DRIVE_UPLOAD = "https://www.googleapis.com/upload/drive/v3/files"
DRIVE_SCOPE = "https://www.googleapis.com/auth/drive.file openid email"


def drive_configured():
    return bool(getattr(settings, "GOOGLE_OAUTH_CLIENT_ID", "") and getattr(settings, "GOOGLE_OAUTH_CLIENT_SECRET", ""))


def _key():
    source = getattr(settings, "BACKUP_TOKEN_KEY", "") or settings.SECRET_KEY
    return hashlib.sha256(("bookpilot-backup-token:" + source).encode()).digest()


def seal(token):
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    nonce = os.urandom(12)
    return "v1:" + base64.urlsafe_b64encode(nonce + AESGCM(_key()).encrypt(nonce, token.encode(), b"drive")).decode()


def unseal(value):
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    raw = base64.urlsafe_b64decode(value[3:].encode())
    return AESGCM(_key()).decrypt(raw[:12], raw[12:], b"drive").decode()


def drive_auth_url(redirect_uri, state):
    from urllib.parse import urlencode
    return GOOGLE_AUTH + "?" + urlencode({
        "client_id": settings.GOOGLE_OAUTH_CLIENT_ID, "redirect_uri": redirect_uri, "response_type": "code",
        "scope": DRIVE_SCOPE, "access_type": "offline", "prompt": "consent", "include_granted_scopes": "true",
        "state": state})


def drive_connect(prefs, code, redirect_uri):
    import requests
    resp = requests.post(GOOGLE_TOKEN, data={
        "code": code, "client_id": settings.GOOGLE_OAUTH_CLIENT_ID, "client_secret": settings.GOOGLE_OAUTH_CLIENT_SECRET,
        "redirect_uri": redirect_uri, "grant_type": "authorization_code"}, timeout=20)
    resp.raise_for_status()
    data = resp.json()
    refresh = data.get("refresh_token")
    if not refresh:
        raise ValueError("Google did not return offline access. Remove BookPilot from your Google account and connect again.")
    email = ""
    if data.get("id_token"):
        try:
            import json
            payload = data["id_token"].split(".")[1]
            email = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4))).get("email", "")
        except Exception:
            email = ""
    prefs.drive_refresh_token, prefs.drive_email = seal(refresh), email[:254]
    prefs.drive_enabled, prefs.drive_folder_id, prefs.drive_error = True, "", ""
    prefs.save()
    return prefs


def _access_token(prefs):
    import requests
    resp = requests.post(GOOGLE_TOKEN, data={
        "client_id": settings.GOOGLE_OAUTH_CLIENT_ID, "client_secret": settings.GOOGLE_OAUTH_CLIENT_SECRET,
        "refresh_token": unseal(prefs.drive_refresh_token), "grant_type": "refresh_token"}, timeout=20)
    if resp.status_code in (400, 401):
        raise PermissionError("Google Drive access was removed. Connect Google Drive again.")
    resp.raise_for_status()
    return resp.json()["access_token"]


def _folder(prefs, token):
    import requests
    if prefs.drive_folder_id:
        return prefs.drive_folder_id
    resp = requests.post(DRIVE_FILES, headers={"Authorization": f"Bearer {token}"}, timeout=20, json={
        "name": f"BookPilot backups – {prefs.company.name}", "mimeType": "application/vnd.google-apps.folder"})
    resp.raise_for_status()
    prefs.drive_folder_id = resp.json()["id"]
    BackupSettings.objects.filter(pk=prefs.pk).update(drive_folder_id=prefs.drive_folder_id)
    return prefs.drive_folder_id


def drive_upload(prefs, name, data):
    """Resumable upload (works for any size); returns the Drive file id."""
    import requests
    token = _access_token(prefs)
    folder = _folder(prefs, token)
    start = requests.post(f"{DRIVE_UPLOAD}?uploadType=resumable", timeout=20, json={
        "name": name.rsplit("/", 1)[-1], "parents": [folder], "mimeType": "application/zip"},
        headers={"Authorization": f"Bearer {token}", "X-Upload-Content-Type": "application/zip",
                 "X-Upload-Content-Length": str(len(data))})
    start.raise_for_status()
    done = requests.put(start.headers["Location"], data=data, timeout=120,
                        headers={"Content-Type": "application/zip"})
    done.raise_for_status()
    return done.json()["id"]


def drive_delete(prefs, file_id):
    import requests
    token = _access_token(prefs)
    requests.delete(f"{DRIVE_FILES}/{file_id}", headers={"Authorization": f"Bearer {token}"}, timeout=20)


def drive_disconnect(prefs):
    import requests
    if prefs.drive_refresh_token:
        try:
            requests.post(GOOGLE_REVOKE, params={"token": unseal(prefs.drive_refresh_token)}, timeout=10)
        except Exception:
            pass
    prefs.drive_enabled, prefs.drive_refresh_token, prefs.drive_email = False, "", ""
    prefs.drive_folder_id, prefs.drive_error = "", ""
    prefs.save()
