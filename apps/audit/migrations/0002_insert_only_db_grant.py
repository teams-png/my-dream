"""
Closes the AuditLog write-only DB grant flagged since Phase 0 Section 14
("no DELETE/UPDATE permission granted to the application DB user on that
table, so even a compromised app can't erase its own trail") and repeated
as open work through Phase 21.

Postgres-only (REVOKE/GRANT have no SQLite equivalent — this is a
deliberate no-op there, matching config/settings/test.py's own documented
SQLite exception). Also a deliberate no-op if DB_APP_ROLE isn't set, so it
doesn't break a local Postgres setup that just uses one shared superuser —
set DB_APP_ROLE to your app's actual Postgres role (e.g. `saas_app` from
the Phase 19 deployment guide) in production for this to take effect.
"""
import os
import re

from django.db import migrations

_VALID_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _get_role():
    role = os.environ.get("DB_APP_ROLE")
    if role and _VALID_IDENTIFIER.match(role):
        return role
    return None  # unset, or something that doesn't look like a plain identifier — skip rather than guess


def grant_insert_only(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    role = _get_role()
    if not role:
        return

    table = apps.get_model("audit", "AuditLog")._meta.db_table
    qtable = schema_editor.quote_name(table)
    qrole = schema_editor.quote_name(role)
    schema_editor.execute(f"REVOKE UPDATE, DELETE ON {qtable} FROM {qrole}")
    schema_editor.execute(f"GRANT INSERT, SELECT ON {qtable} TO {qrole}")


def reverse_grant(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    role = _get_role()
    if not role:
        return

    table = apps.get_model("audit", "AuditLog")._meta.db_table
    qtable = schema_editor.quote_name(table)
    qrole = schema_editor.quote_name(role)
    schema_editor.execute(f"GRANT UPDATE, DELETE ON {qtable} TO {qrole}")


class Migration(migrations.Migration):

    dependencies = [
        ("audit", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(grant_insert_only, reverse_grant),
    ]
