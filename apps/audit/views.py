from rest_framework import viewsets

from apps.common.permissions import IsOwnerRole

from .models import AuditLog
from .serializers import AuditLogSerializer


class AuditLogViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Read-only by design — Section 28 ("Audit logs should not be easily
    deleted by normal users") means there is no delete/update endpoint at
    all, not just a permission-gated one. Owner-only: Staff/Accountant
    should not be able to see who did what across the company (Section 7).
    """
    serializer_class = AuditLogSerializer
    permission_classes = [IsOwnerRole]

    def get_queryset(self):
        qs = AuditLog.objects.for_company(self.request.company).select_related("user")

        user_id = self.request.query_params.get("user")
        if user_id:
            qs = qs.filter(user_id=user_id)

        model_name = self.request.query_params.get("model_name")
        if model_name:
            qs = qs.filter(model_name=model_name)

        action = self.request.query_params.get("action")
        if action:
            qs = qs.filter(action=action)

        date_from = self.request.query_params.get("date_from")
        if date_from:
            qs = qs.filter(timestamp__date__gte=date_from)

        date_to = self.request.query_params.get("date_to")
        if date_to:
            qs = qs.filter(timestamp__date__lte=date_to)

        return qs
