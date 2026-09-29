from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    """
    Platform-wide identity — deliberately has NO company FK. One login can
    belong to multiple companies via tenants.CompanyMembership (Phase 0/1
    Section 6) — e.g. an accountant serving several small businesses.
    """
    email = models.EmailField(unique=True)
    phone = models.CharField(max_length=20, blank=True)
    is_platform_admin = models.BooleanField(default=False)  # super admin, NOT a tenant role

    def __str__(self):
        return self.email or self.username


class LoginAttempt(models.Model):
    """
    Not tenant-scoped (no company yet at login time — that's the whole
    point). Keyed on (identifier, ip_address) rather than a FK to User,
    because a lockout must also apply to attempts against emails that
    don't exist — otherwise "invalid email" vs "wrong password" timing/
    behaviour differences become a way to enumerate registered accounts.
    """
    identifier = models.CharField(max_length=255, db_index=True)  # the email/username typed in
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    successful = models.BooleanField(default=False)
    attempted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=["identifier", "attempted_at"])]
