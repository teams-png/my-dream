from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers, viewsets
from rest_framework.decorators import action, api_view
from rest_framework.response import Response

from apps.customers.models import Customer
from .models import PipelineStage, Lead, Opportunity, Activity
from .serializers import PipelineStageSerializer, LeadSerializer, OpportunitySerializer, ActivitySerializer
from .services import convert_lead, duplicate_customer_candidates, customer_timeline


class ScopedViewSet(viewsets.ModelViewSet):
    model = None
    def get_queryset(self):
        return self.model.objects.for_company(self.request.company)


class PipelineStageViewSet(ScopedViewSet):
    model = PipelineStage
    serializer_class = PipelineStageSerializer


class LeadViewSet(ScopedViewSet):
    model = Lead
    serializer_class = LeadSerializer

    @action(detail=True, methods=["get"])
    def duplicates(self, request, pk=None):
        return Response(list(duplicate_customer_candidates(company=request.company, lead=self.get_object()).values("id", "name", "email", "phone")))

    @action(detail=True, methods=["post"])
    def convert(self, request, pk=None):
        existing = None
        if request.data.get("customer_id"):
            existing = Customer.objects.for_company(request.company).filter(pk=request.data["customer_id"]).first()
            if existing is None:
                raise serializers.ValidationError("Customer not found in this company.")
        try:
            customer, opportunity, quotation = convert_lead(
                company=request.company, lead=self.get_object(), user=request.user,
                existing_customer=existing, resolve_duplicate=bool(request.data.get("resolve_duplicate")),
                create_quotation=bool(request.data.get("create_quotation")),
            )
        except DjangoValidationError as exc:
            raise serializers.ValidationError(exc.message_dict if hasattr(exc, "message_dict") else exc.messages)
        return Response({"customer_id": customer.id, "opportunity_id": opportunity.id, "quotation_id": quotation.id if quotation else None})


class OpportunityViewSet(ScopedViewSet):
    model = Opportunity
    serializer_class = OpportunitySerializer


class ActivityViewSet(ScopedViewSet):
    model = Activity
    serializer_class = ActivitySerializer


@api_view(["GET"])
def timeline(request, customer_id):
    customer = Customer.objects.for_company(request.company).filter(pk=customer_id).first()
    if customer is None:
        return Response({"detail": "Not found."}, status=404)
    return Response(customer_timeline(company=request.company, customer=customer))
