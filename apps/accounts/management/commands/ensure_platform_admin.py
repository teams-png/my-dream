"""
Idempotent: creates the platform owner account from environment variables
so a host without shell access (e.g. Render's free plan) can still get a
first admin login. Does nothing unless both variables are set, and never
resets the password of an existing account.

    PLATFORM_ADMIN_EMAIL=you@example.com
    PLATFORM_ADMIN_PASSWORD=<strong password>
"""
import os

from django.core.management.base import BaseCommand

from apps.accounts.models import User


class Command(BaseCommand):
    help = "Create the platform admin from PLATFORM_ADMIN_EMAIL / PLATFORM_ADMIN_PASSWORD if missing."

    def handle(self, *args, **options):
        email = os.environ.get("PLATFORM_ADMIN_EMAIL", "").strip().lower()
        password = os.environ.get("PLATFORM_ADMIN_PASSWORD", "")
        if not email or not password:
            self.stdout.write("PLATFORM_ADMIN_EMAIL/PASSWORD not set — skipping platform admin creation.")
            return

        user = User.objects.filter(email__iexact=email).first()
        if user is None:
            User.objects.create_superuser(username=email, email=email, password=password, is_platform_admin=True)
            self.stdout.write(self.style.SUCCESS(f"Platform admin {email} created."))
            return

        if not (user.is_platform_admin and user.is_superuser and user.is_staff):
            user.is_platform_admin = user.is_superuser = user.is_staff = True
            user.save(update_fields=["is_platform_admin", "is_superuser", "is_staff"])
        self.stdout.write(f"Platform admin {email} already exists — password left unchanged.")
