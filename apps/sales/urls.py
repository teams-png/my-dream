from rest_framework.routers import DefaultRouter
from .views import (SalesInvoiceViewSet, QuotationViewSet, SalesOrderViewSet, DeliveryNoteViewSet,
                    POSViewSet, PriceListViewSet, PromotionViewSet, CommercialSettingsViewSet,
                    ExchangeRateViewSet, TaxSchemeViewSet, TaxCodeViewSet)

router = DefaultRouter()
router.register("invoices", SalesInvoiceViewSet, basename="sales-invoice")
router.register("quotations", QuotationViewSet, basename="quotation")
router.register("orders", SalesOrderViewSet, basename="sales-order")
router.register("deliveries", DeliveryNoteViewSet, basename="delivery-note")
router.register("pos", POSViewSet, basename="pos")
router.register("price-lists", PriceListViewSet, basename="price-list")
router.register("promotions", PromotionViewSet, basename="promotion")
router.register("commercial-settings", CommercialSettingsViewSet, basename="commercial-settings")
router.register("exchange-rates", ExchangeRateViewSet, basename="exchange-rate")
router.register("tax-schemes", TaxSchemeViewSet, basename="tax-scheme")
router.register("tax-codes", TaxCodeViewSet, basename="tax-code")

urlpatterns = router.urls
