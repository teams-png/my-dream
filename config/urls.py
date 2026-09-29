from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from apps.common.views import health, readiness, pwa_manifest, service_worker

urlpatterns = [
    path("health/", health, name="health"),
    path("ready/", readiness, name="readiness"),
    path("manifest.webmanifest", pwa_manifest, name="pwa-manifest"),
    path("service-worker.js", service_worker, name="service-worker"),
    path("admin/", admin.site.urls),
    path("i18n/", include("django.conf.urls.i18n")),

    path("", include("apps.webapp.urls")),

    path("api/accounts/", include("apps.accounts.urls")),
    path("api/tenants/", include("apps.tenants.urls")),
    path("api/subscriptions/", include("apps.subscriptions.urls")),

    path("api/accounting/", include("apps.accounting.urls")),
    path("api/customers/", include("apps.customers.urls")),
    path("api/suppliers/", include("apps.suppliers.urls")),
    path("api/inventory/", include("apps.inventory.urls")),
    path("api/sales/", include("apps.sales.urls")),
    path("api/purchases/", include("apps.purchases.urls")),
    path("api/expenses/", include("apps.expenses.urls")),
    path("api/employees/", include("apps.employees.urls")),
    path("api/reports/", include("apps.reports.urls")),
    path("api/platform-admin/", include("apps.platform_admin.urls")),
    path("api/notifications/", include("apps.notifications.urls")),
    path("api/audit/", include("apps.audit.urls")),
    path("api/banking/", include("apps.banking.urls")),
    path("api/collections/", include("apps.collections.urls")),
    path("api/crm/", include("apps.crm.urls")),
    path("api/analytics/", include("apps.analytics.urls")),

    # view layer still checks CompanyModule before returning data (Phase 0 Section 8)
    path("api/gym/", include("apps.verticals.gym.urls")),
    path("api/textile/", include("apps.verticals.textile.urls")),
    path("api/spa/", include("apps.verticals.spa.urls")),
    path("api/construction/", include("apps.verticals.construction.urls")),
    path("api/mobile-shop/", include("apps.verticals.mobile_shop.urls")),
    path("api/vehicle-wash/", include("apps.verticals.vehicle_wash.urls")),
    path("api/sports-shop/", include("apps.verticals.sports_shop.urls")),
    path("api/cycle-shop/", include("apps.verticals.cycle_shop.urls")),
    path("api/saloon/", include("apps.verticals.saloon.urls")),
    path("api/beauty-parlour/", include("apps.verticals.beauty_parlour.urls")),
    path("api/medical-shop/", include("apps.verticals.medical_shop.urls")),
    path("api/protein-shop/", include("apps.verticals.protein_shop.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
