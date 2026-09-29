"""
CompanyCounter tests — closes the invoice-numbering race condition flagged
since Phase 1 Section 13 and repeated as open work through Phase 21.

Real concurrent-request safety depends on Postgres's row-level locking via
SELECT ... FOR UPDATE; SQLite (used here for test speed, per
config/settings/test.py's own documented exception) treats
select_for_update() as a no-op rather than erroring, so these tests verify
correctness of the sequence and its per-company/per-key isolation, not
true concurrency — that guarantee is architectural (Postgres FOR UPDATE
semantics), not something a SQLite-backed unit test can exercise directly.
"""
import pytest

pytestmark = pytest.mark.django_db


class TestCompanyCounter:
    def test_sequence_increments_from_one(self, tenant_a):
        from apps.tenants.services import next_counter_value

        assert next_counter_value(tenant_a, "sales_invoice") == 1
        assert next_counter_value(tenant_a, "sales_invoice") == 2
        assert next_counter_value(tenant_a, "sales_invoice") == 3

    def test_different_keys_are_independent_sequences(self, tenant_a):
        from apps.tenants.services import next_counter_value

        assert next_counter_value(tenant_a, "sales_invoice") == 1
        assert next_counter_value(tenant_a, "some_other_doc") == 1  # unaffected by the sales_invoice sequence
        assert next_counter_value(tenant_a, "sales_invoice") == 2

    def test_sequence_is_per_company(self, tenant_a, tenant_b):
        from apps.tenants.services import next_counter_value

        assert next_counter_value(tenant_a, "sales_invoice") == 1
        assert next_counter_value(tenant_a, "sales_invoice") == 2
        assert next_counter_value(tenant_b, "sales_invoice") == 1  # tenant B's own sequence, unaffected

    def test_counter_row_is_created_on_first_use(self, tenant_a):
        from apps.tenants.models import CompanyCounter
        from apps.tenants.services import next_counter_value

        assert not CompanyCounter.objects.filter(company=tenant_a, key="sales_invoice").exists()
        next_counter_value(tenant_a, "sales_invoice")
        counter = CompanyCounter.objects.get(company=tenant_a, key="sales_invoice")
        assert counter.last_value == 1
