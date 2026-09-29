from rest_framework.routers import DefaultRouter
from .views import MembershipPlanViewSet, GymMemberViewSet, AttendanceViewSet

router = DefaultRouter()
router.register("plans", MembershipPlanViewSet, basename="gym-plan")
router.register("members", GymMemberViewSet, basename="gym-member")
router.register("attendance", AttendanceViewSet, basename="gym-attendance")

urlpatterns = router.urls
