"""
Tests the identifier-validation logic in the AuditLog INSERT-only DB grant
migration (apps/audit/migrations/0002_insert_only_db_grant.py). The
migration's actual REVOKE/GRANT statements only run against Postgres in
production (see the migration's own docstring) — nothing to assert here
against SQLite except that the safety checks that decide whether to run
at all are correct, since a wrong identifier check would be a SQL
injection surface if it ever let a bad value through.
"""
import importlib

grant_migration = importlib.import_module("apps.audit.migrations.0002_insert_only_db_grant")


class TestRoleIdentifierValidation:
    def test_accepts_plain_identifiers(self, monkeypatch):
        monkeypatch.setenv("DB_APP_ROLE", "saas_app")
        assert grant_migration._get_role() == "saas_app"

    def test_accepts_identifiers_with_underscores_and_digits(self, monkeypatch):
        monkeypatch.setenv("DB_APP_ROLE", "saas_app_2")
        assert grant_migration._get_role() == "saas_app_2"

    def test_rejects_identifiers_starting_with_a_digit(self, monkeypatch):
        monkeypatch.setenv("DB_APP_ROLE", "2saas")
        assert grant_migration._get_role() is None

    def test_rejects_sql_injection_attempts(self, monkeypatch):
        monkeypatch.setenv("DB_APP_ROLE", "saas_app; DROP TABLE audit_auditlog;--")
        assert grant_migration._get_role() is None

    def test_rejects_quoted_or_spaced_values(self, monkeypatch):
        monkeypatch.setenv("DB_APP_ROLE", '"saas app"')
        assert grant_migration._get_role() is None

    def test_returns_none_when_unset(self, monkeypatch):
        monkeypatch.delenv("DB_APP_ROLE", raising=False)
        assert grant_migration._get_role() is None
