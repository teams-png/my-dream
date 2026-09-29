"""Phase 1 Section 38: 'Accounting entries' — Section 41's double-entry rule."""
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError

from apps.accounting.models import Account
from apps.accounting.services import post_journal_entry, account_balance

pytestmark = pytest.mark.django_db


def test_chart_of_accounts_is_seeded_on_company_creation(make_company):
    company, owner = make_company("textile")
    codes = set(Account.objects.for_company(company).values_list("code", flat=True))
    assert {"1000", "1100", "2000", "4000", "5100"}.issubset(codes)


def test_balanced_journal_entry_posts_successfully(make_company):
    company, owner = make_company("textile")
    cash = Account.objects.for_company(company).get(code="1000")
    revenue = Account.objects.for_company(company).get(code="4000")

    entry = post_journal_entry(
        company=company, date="2026-09-09", user=owner,
        lines=[(cash, Decimal("500.00"), Decimal("0")), (revenue, Decimal("0"), Decimal("500.00"))],
        reference="TEST-JE-1",
    )
    assert entry.lines.count() == 2
    assert account_balance(cash) == Decimal("500.00")


def test_unbalanced_journal_entry_is_rejected(make_company):
    """Section 41: this is the rule the whole engine exists to enforce — debits must equal credits."""
    company, owner = make_company("textile")
    cash = Account.objects.for_company(company).get(code="1000")
    revenue = Account.objects.for_company(company).get(code="4000")

    with pytest.raises(ValidationError):
        post_journal_entry(
            company=company, date="2026-09-09", user=owner,
            lines=[(cash, Decimal("500.00"), Decimal("0")), (revenue, Decimal("0"), Decimal("400.00"))],
        )


def test_zero_amount_journal_entry_is_rejected(make_company):
    company, owner = make_company("textile")
    cash = Account.objects.for_company(company).get(code="1000")
    revenue = Account.objects.for_company(company).get(code="4000")

    with pytest.raises(ValidationError):
        post_journal_entry(
            company=company, date="2026-09-09", user=owner,
            lines=[(cash, Decimal("0"), Decimal("0")), (revenue, Decimal("0"), Decimal("0"))],
        )
