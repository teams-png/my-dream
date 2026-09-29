from rest_framework.routers import DefaultRouter
from .views import BankAccountViewSet, StatementTransactionViewSet

router = DefaultRouter()
router.register("bank-accounts", BankAccountViewSet, basename="bank-account")
router.register("statement-transactions", StatementTransactionViewSet, basename="statement-transaction")

urlpatterns = router.urls
