from django.utils.dateparse import parse_date
from rest_framework.decorators import api_view
from rest_framework.response import Response
from apps.inventory.models import Warehouse
from .services import dashboard_metrics


@api_view(["GET"])
def dashboard(request):
    start = parse_date(request.query_params.get("start_date", ""))
    end = parse_date(request.query_params.get("end_date", ""))
    warehouse = None
    if request.query_params.get("warehouse"):
        warehouse = Warehouse.objects.for_company(request.company).filter(pk=request.query_params["warehouse"]).first()
        if warehouse is None:
            return Response({"detail": "Warehouse not found."}, status=404)
    return Response(dashboard_metrics(company=request.company, start_date=start, end_date=end, warehouse=warehouse))
