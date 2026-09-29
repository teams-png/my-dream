from rest_framework import viewsets, permissions

from .models import SportsProductDetail
from .serializers import SportsProductDetailSerializer


def _require_sports_shop_module(request):
    return request.company.active_modules().filter(code="sports_shop").exists()


class SportsProductDetailViewSet(viewsets.ModelViewSet):
    serializer_class = SportsProductDetailSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        if not _require_sports_shop_module(self.request):
            return SportsProductDetail.objects.none()
        return SportsProductDetail.objects.for_company(self.request.company).select_related("product")

    def perform_create(self, serializer):
        serializer.save(company=self.request.company)
