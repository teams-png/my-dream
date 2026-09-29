"""
Idempotent: creates the platform owner account from environment variables
so a host without shell access (e.g. Render's free plan) can still get a
first admin login. Does nothing unless both variables are set. The
password of an existing account is only replaced when
PLATFORM_ADMIN_RESET_PASSWORD is true — turn it off again afterwards, or
every deploy will overwrite a password changed in the app.

    PLATFORM_ADMIN_EMAIL=you@example.com
    PLATFORM_ADMIN_PASSWORD=<strong password>
    PLATFORM_ADMIN_RESET_PASSWORD=True   # optional, one-off reset
"""
import os

from django.core.management.base import BaseCommand

from apps.accounts.models import LoginAttempt, User


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

        user.is_platform_admin = user.is_superuser = user.is_staff = user.is_active = True
        update_fields = ["is_platform_admin", "is_superuser", "is_staff", "is_active"]
        reset = os.environ.get("PLATFORM_ADMIN_RESET_PASSWORD", "").strip().lower() in ("1", "true", "yes")
        if reset:
            user.set_password(password)
            update_fields.append("password")
            # Clear any lockout left by failed attempts with the old password.
            LoginAttempt.objects.filter(identifier__iexact=email, successful=False).delete()
        user.save(update_fields=update_fields)
        if reset:
            self.stdout.write(self.style.WARNING(
                f"Platform admin {email} password reset. Set PLATFORM_ADMIN_RESET_PASSWORD=False now."
            ))
        else:
            self.stdout.write(f"Platform admin {email} already exists — password left unchanged.")
