import pytest
from django.core import mail
from apps.notifications.models import NotificationDelivery, NotificationPreference
from apps.notifications.services import notify

pytestmark = pytest.mark.django_db(transaction=True)


def test_email_delivery_is_idempotent(tenant_a, tenant_a_owner):
    notify(company=tenant_a, recipient=tenant_a_owner, title="Test", message="Message", idempotency_key="fixed-key")
    notify(company=tenant_a, recipient=tenant_a_owner, title="Again", message="Message", idempotency_key="fixed-key")
    assert NotificationDelivery.objects.filter(company=tenant_a, idempotency_key="fixed-key").count() == 1
    assert len(mail.outbox) == 1


def test_email_preference_is_respected(tenant_a, tenant_a_owner):
    NotificationPreference.objects.create(company=tenant_a, user=tenant_a_owner, event_type="general", email_enabled=False)
    notify(company=tenant_a, recipient=tenant_a_owner, title="Silent")
    assert NotificationDelivery.objects.filter(company=tenant_a).count() == 0
