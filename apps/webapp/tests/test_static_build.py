"""The deploy runs collectstatic with hashed file names (whitenoise). It fails on any file that points at
a missing file (e.g. a CSS url() or a JS source map), which plain tests never notice — so run it here."""
import pytest
from django.core.management import call_command
from django.test import override_settings


@pytest.mark.django_db
def test_collectstatic_with_hashed_names_succeeds(tmp_path):
    storages = {"default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
                "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.ManifestStaticFilesStorage"}}
    with override_settings(STATIC_ROOT=str(tmp_path), STORAGES=storages):
        call_command("collectstatic", "--noinput", verbosity=0)
    assert (tmp_path / "staticfiles.json").exists()
