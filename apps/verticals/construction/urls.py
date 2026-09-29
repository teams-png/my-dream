from rest_framework.routers import DefaultRouter
from .views import ProjectViewSet, ContractorViewSet, ProjectAssignmentViewSet, ProjectExpenseViewSet

router = DefaultRouter()
router.register("projects", ProjectViewSet, basename="construction-project")
router.register("contractors", ContractorViewSet, basename="construction-contractor")
router.register("assignments", ProjectAssignmentViewSet, basename="construction-assignment")
router.register("expenses", ProjectExpenseViewSet, basename="construction-expense")

urlpatterns = router.urls
