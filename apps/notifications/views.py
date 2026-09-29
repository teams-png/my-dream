from rest_framework import viewsets, permissions
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import Notification
from .serializers import NotificationSerializer


class NotificationViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Deliberately scoped to `request.user`, not `request.company` — a
    Notification always belongs to one recipient, and Staff must never see
    Owner-only notices (e.g. subscription billing) just by sharing a
    company. Read-only: notifications are created exclusively by
    notifications.services, never via a client POST.
    """
    serializer_class = NotificationSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Notification.objects.filter(
            company=self.request.company, recipient=self.request.user,
        )

    @action(detail=False, methods=["get"])
    def unread_count(self, request):
        return Response({"unread_count": self.get_queryset().filter(is_read=False).count()})

    @action(detail=True, methods=["post"])
    def mark_read(self, request, pk=None):
        notif = self.get_object()
        notif.is_read = True
        notif.save(update_fields=["is_read"])
        return Response(NotificationSerializer(notif).data)

    @action(detail=False, methods=["post"], url_path="mark-all-read")
    def mark_all_read(self, request):
        updated = self.get_queryset().filter(is_read=False).update(is_read=True)
        return Response({"marked_read": updated})
