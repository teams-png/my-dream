from rest_framework import permissions
from rest_framework.response import Response
from rest_framework.views import APIView

from .serializers import SubscriptionSerializer


class MySubscriptionView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        if not request.company or not hasattr(request.company, "subscription"):
            return Response({"detail": "No subscription found."}, status=404)
        return Response(SubscriptionSerializer(request.company.subscription).data)
