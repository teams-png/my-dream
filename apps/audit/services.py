from .models import AuditLog


def log_action(*, company, user, action, model_name, object_id, changes=None, ip_address=None):
    """
    Called from other apps' services after a write (not from views — keeps
    the audit trail authoritative regardless of which entry point was used).
    In production, the app DB user should have INSERT-only grant on this
    table (Phase 0 Section 14) — set that up as a raw SQL migration once a
    real Postgres role is provisioned; it can't be expressed in Django ORM.
    """
    return AuditLog.objects.create(
        company=company, user=user, action=action, model_name=model_name,
        object_id=str(object_id), changes=changes or {}, ip_address=ip_address,
    )
