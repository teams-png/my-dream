from rest_framework.permissions import BasePermission


class IsPlatformAdmin(BasePermission):
    """
    Every view in this app uses this instead of the normal tenant
    permission stack. A platform admin has no CompanyMembership row (Phase 0
    Section 24) — deliberately kept separate so a compromised tenant Owner
    account can never escalate into platform-wide access, and vice versa.
    """
    message = "Super Admin access required."

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.is_active and request.user.is_platform_admin)
