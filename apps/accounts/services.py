"""
Lockout logic used by views.SecureTokenObtainPairView. Thresholds are
settings (LOGIN_LOCKOUT_THRESHOLD / LOGIN_LOCKOUT_WINDOW_MINUTES) so an
Owner-configurable version can be added later without changing this file.
"""
from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from .models import LoginAttempt

DEFAULT_THRESHOLD = getattr(settings, "LOGIN_LOCKOUT_THRESHOLD", 5)
DEFAULT_WINDOW_MINUTES = getattr(settings, "LOGIN_LOCKOUT_WINDOW_MINUTES", 15)


def is_locked_out(identifier, ip_address):
    window_start = timezone.now() - timedelta(minutes=DEFAULT_WINDOW_MINUTES)
    recent_failures = LoginAttempt.objects.filter(
        identifier=identifier, ip_address=ip_address,
        successful=False, attempted_at__gte=window_start,
    ).count()
    return recent_failures >= DEFAULT_THRESHOLD


def record_attempt(identifier, ip_address, *, successful):
    LoginAttempt.objects.create(identifier=identifier, ip_address=ip_address, successful=successful)
    if successful:
        # A successful login clears the slate — no reason to keep counting
        # failures from before a correct password was entered.
        LoginAttempt.objects.filter(identifier=identifier, ip_address=ip_address, successful=False).delete()


def client_ip(request):
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")
