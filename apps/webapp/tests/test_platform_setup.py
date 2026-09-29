import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from apps.modules.models import BusinessType, BusinessTypeDefaultModule, Module
from apps.platform_admin.models import PaymentGatewaySettings
from apps.platform_admin.payment_gateways import get_payment_gateway_config


@pytest.fixture
def platform_superuser(db):
    return get_user_model().objects.create_superuser(
        username="platform-owner",
        email="owner@example.com",
        password="Test-Pass-123",
        is_platform_admin=True,
    )


@pytest.mark.django_db
def test_platform_setup_pages_are_available_to_superuser(client, platform_superuser):
    client.force_login(platform_superuser)
    route_names = [
        "platform_setup", "platform_module_list", "platform_business_type_list",
        "platform_user_list", "platform_support_list", "platform_audit_list",
        "platform_payment_gateway_settings",
    ]
    for route_name in route_names:
        response = client.get(reverse(f"webapp:{route_name}"))
        assert response.status_code == 200, route_name


@pytest.mark.django_db
def test_platform_setup_rejects_normal_business_user(client, user_factory):
    user = user_factory()
    client.force_login(user)
    response = client.get(reverse("webapp:platform_setup"))
    assert response.status_code == 302
    assert response.url == reverse("webapp:dashboard")


@pytest.mark.django_db
def test_platform_owner_can_create_module_and_business_defaults(client, platform_superuser):
    client.force_login(platform_superuser)
    response = client.post(reverse("webapp:platform_module_add"), {
        "code": "repairs", "name": "Repair Management", "is_core": "",
    })
    assert response.status_code == 302
    module = Module.objects.get(code="repairs")

    response = client.post(reverse("webapp:platform_business_type_add"), {
        "code": "mobile_shop", "name": "Mobile Shop", "default_modules": [module.id],
    })
    assert response.status_code == 302
    business_type = BusinessType.objects.get(code="mobile_shop")
    assert BusinessTypeDefaultModule.objects.filter(
        business_type=business_type, module=module,
    ).exists()


@pytest.mark.django_db
def test_platform_owner_can_save_encrypted_payment_keys(client, platform_superuser):
    client.force_login(platform_superuser)
    response = client.post(reverse("webapp:platform_payment_gateway_settings"), {
        "stripe_enabled": "on",
        "stripe_test_mode": "on",
        "stripe_publishable_key": "pk_test_bookpilot",
        "stripe_secret_key": "sk_test_bookpilot_secret",
        "stripe_webhook_secret": "whsec_bookpilot",
        "razorpay_enabled": "on",
        "razorpay_test_mode": "on",
        "razorpay_key_id": "rzp_test_bookpilot",
        "razorpay_key_secret": "razorpay-secret-value",
        "razorpay_webhook_secret": "razorpay-webhook-value",
    })
    assert response.status_code == 302

    saved = PaymentGatewaySettings.objects.get(pk=1)
    assert "sk_test_bookpilot_secret" not in saved.stripe_secret_key_ciphertext
    assert "razorpay-secret-value" not in saved.razorpay_key_secret_ciphertext
    assert saved.get_secret("stripe_secret_key") == "sk_test_bookpilot_secret"

    runtime = get_payment_gateway_config()
    assert runtime.stripe_enabled is True
    assert runtime.stripe_secret_key == "sk_test_bookpilot_secret"
    assert runtime.razorpay_enabled is True
    assert runtime.razorpay_key_id == "rzp_test_bookpilot"


@pytest.mark.django_db
def test_blank_payment_fields_keep_saved_secrets(client, platform_superuser):
    saved = PaymentGatewaySettings.load()
    saved.set_secret("stripe_secret_key", "existing-secret")
    saved.save()
    client.force_login(platform_superuser)

    response = client.post(reverse("webapp:platform_payment_gateway_settings"), {
        "stripe_enabled": "on", "stripe_test_mode": "on",
    })
    assert response.status_code == 302
    saved.refresh_from_db()
    assert saved.get_secret("stripe_secret_key") == "existing-secret"
