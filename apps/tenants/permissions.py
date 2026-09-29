from rest_framework.permissions import BasePermission


class HasCompanyPermission(BasePermission):
    """
    Reusable RBAC gate (Phase 0 Section 6): permission checks live in the
    service/view layer, not just hidden from a sidebar — a Staff user
    hitting a protected endpoint directly must be blocked here, not only
    kept from seeing the link in the UI.

    Usage on a viewset/view:
        permission_classes = [permissions.IsAuthenticated, HasCompanyPermission]
        required_permissions = {
            "list": "sales.view_invoice",
            "retrieve": "sales.view_invoice",
            "create": "sales.create_invoice",
            "record_payment": "sales.create_invoice",
            "default": "sales.view_invoice",   # used for actions/methods not listed above
        }

    For a plain APIView (no `.action`), the HTTP method name (lowercased)
    is used as the lookup key instead — map "get"/"post"/etc.

    Omitting `required_permissions` entirely on a view makes this a no-op
    (falls back to whatever else is in permission_classes) — set it
    explicitly on every view that touches tenant data.
    """

    def has_permission(self, request, view):
        if not (request.user and request.user.is_authenticated):
            return False
        if not getattr(request, "company", None) or not getattr(request, "role", None):
            return False

        required_map = getattr(view, "required_permissions", None)
        if required_map is None:
            return True

        key = getattr(view, "action", None) or request.method.lower()
        code = required_map.get(key, required_map.get("default"))
        if code is None:
            return True

        return request.role.permissions.filter(permission__code=code).exists()
