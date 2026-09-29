from django.urls import path
from rest_framework.routers import DefaultRouter
from .views import PipelineStageViewSet, LeadViewSet, OpportunityViewSet, ActivityViewSet, timeline

router = DefaultRouter()
router.register("stages", PipelineStageViewSet, basename="crm-stage")
router.register("leads", LeadViewSet, basename="crm-lead")
router.register("opportunities", OpportunityViewSet, basename="crm-opportunity")
router.register("activities", ActivityViewSet, basename="crm-activity")
urlpatterns = router.urls + [path("customers/<int:customer_id>/timeline/", timeline)]
