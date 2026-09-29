"""
Reusable DRF permission classes on top of request.role (set by
apps.tenants.middleware.ActiveCompanyMiddleware). Views that need
"Owner only" or "Owner or Accountant" gates should compose these instead
of checking request.role.name inline — keeps the role-name convention in
one place (Phase 6's same convention note in notifications/services.py).
"""
from rest_framework.permissions import BasePermission

OWNER_ROLE = "Owner"
ACCOUNTANT_ROLE = "Accountant"


class IsOwnerRole(BasePermission):
    """Owner-only endpoints: subscription/billing, user management, audit log viewing (Section 24/25)."""

    message = "Only the company Owner can perform this action."

    def has_permission(self, request, view):
        return bool(request.role and request.role.name == OWNER_ROLE)


class IsOwnerOrAccountantRole(BasePermission):
    """Financial endpoints: accounts, ledger, financial reports (Section 7 — Accountant's allowed scope)."""

    message = "Only the Owner or Accountant can perform this action."

    def has_permission(self, request, view):
        return bool(request.role and request.role.name in (OWNER_ROLE, ACCOUNTANT_ROLE))
