"""Branch-restricted staff: a cashier assigned to some branches (warehouses) only sells from,
and only sees the stock and bills of, those branches.

The allowed branches for the current request are kept in a context variable set by
ActiveCompanyMiddleware, so every "which branch is this sale from?" helper honours it
without each of the many business-type views passing the request down.
"""
from contextvars import ContextVar

_allowed = ContextVar("bookpilot_allowed_warehouses", default=None)


def ids_for(membership):
    """Allowed warehouse ids for a membership, or None for every branch."""
    if membership is None or getattr(membership.role, "name", "") == "Owner":
        return None
    ids = frozenset(membership.warehouses.values_list("id", flat=True))
    return ids or None


def activate(ids):
    return _allowed.set(frozenset(ids) if ids else None)


def reset(token):
    _allowed.reset(token)


def allowed():
    return _allowed.get()


def limit(qs, field="id"):
    """Narrows a queryset to the allowed branches (no-op for unrestricted users)."""
    ids = _allowed.get()
    return qs if ids is None else qs.filter(**{f"{field}__in": ids})


def is_allowed(warehouse_id):
    ids = _allowed.get()
    return ids is None or (warehouse_id is not None and int(warehouse_id) in ids)


def pick(company, warehouse_id=None):
    """For a branch-restricted user: the requested branch if they may use it, else their first branch.
    Returns None for unrestricted users so callers keep their usual default-branch logic."""
    ids = _allowed.get()
    if ids is None:
        return None
    from .models import Warehouse
    qs = Warehouse.objects.for_company(company).filter(id__in=ids, is_active=True)
    if warehouse_id:
        found = qs.filter(id=warehouse_id).first()
        if found:
            return found
    return qs.order_by("-is_default", "id").first()
