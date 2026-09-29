"""
Full data export for one business (backup / data portability).

Collects every row that belongs to the company: models with a `company`
foreign key, plus their child rows (invoice lines, journal lines…) one level
down. Passwords, 2FA secrets and platform-wide tables are never included.
"""
import io
import json
import zipfile

from django.apps import apps
from django.core import serializers
from django.utils import timezone

SKIP_MODELS = {"accounts.User", "accounts.TwoFactorDevice", "accounts.LoginAttempt", "sessions.Session",
               "admin.LogEntry", "contenttypes.ContentType", "auth.Permission", "auth.Group"}


def _company_field(model):
    try:
        field = model._meta.get_field("company")
    except Exception:
        return None
    return field if getattr(field, "related_model", None) and field.related_model._meta.label == "tenants.Company" else None


def company_querysets(company):
    owned = {}
    for model in apps.get_models():
        label = model._meta.label
        if label in SKIP_MODELS or model._meta.proxy:
            continue
        if _company_field(model):
            owned[label] = model._base_manager.filter(company=company)
    for model in apps.get_models():
        label = model._meta.label
        if label in owned or label in SKIP_MODELS or model._meta.proxy:
            continue
        for field in model._meta.get_fields():
            parent = getattr(field, "related_model", None)
            if field.many_to_one and parent is not None and parent._meta.label in owned and _company_field(parent):
                owned[label] = model._base_manager.filter(**{f"{field.name}__company": company})
                break
    owned["tenants.Company"] = apps.get_model("tenants", "Company")._base_manager.filter(pk=company.pk)
    return owned


def export_company_zip(company, *, include_media=False):
    buffer = io.BytesIO()
    counts = {}
    media_files = set()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for label, qs in sorted(company_querysets(company).items()):
            rows = list(qs)
            if not rows:
                continue
            counts[label] = len(rows)
            archive.writestr(f"data/{label}.json", serializers.serialize("json", rows, indent=1))
            if include_media:
                for row in rows:
                    for field in row._meta.fields:
                        value = getattr(row, field.name, None)
                        if hasattr(value, "name") and hasattr(value, "storage") and value.name:
                            media_files.add((value.storage, value.name))
        for storage, name in sorted(media_files, key=lambda x: x[1]):
            try:
                with storage.open(name, "rb") as fh:
                    archive.writestr(f"media/{name}", fh.read())
            except Exception:
                continue
        archive.writestr("manifest.json", json.dumps({
            "company": company.name, "company_id": company.pk, "exported_at": timezone.now().isoformat(),
            "format": "Django JSON fixtures, one file per table", "tables": counts,
            "media_files": len(media_files) if include_media else "not included",
        }, indent=2))
    return buffer.getvalue(), counts
