"""Offline restaurant POS: page shell, device data and bill sync."""
import json

from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import JsonResponse
from django.middleware.csrf import get_token
from django.shortcuts import render
from django.views.decorators.cache import never_cache

from apps.verticals.restaurant import offline

from .views import require_business_group, require_permission

MAX_BILLS_PER_SYNC = 50


def restaurant_view(view):
    return login_required(require_business_group("restaurant")(require_permission("restaurant.manage")(view)))


@restaurant_view
def offline_pos(request):
    """The page is cached on the device; all data comes from bootstrap + IndexedDB."""
    return render(request, "webapp/restaurant/offline_pos.html", {})


@never_cache
@restaurant_view
def offline_bootstrap(request):
    data = offline.bootstrap(request.company)
    data["csrf"] = get_token(request)
    data["user"] = request.user.email or request.user.username
    return JsonResponse(data)


@never_cache
@restaurant_view
def offline_sync(request):
    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=405)
    try:
        bills = json.loads(request.body or b"{}").get("bills") or []
    except ValueError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)
    if not isinstance(bills, list) or len(bills) > MAX_BILLS_PER_SYNC:
        return JsonResponse({"error": "Send at most 50 bills at a time"}, status=400)
    results = []
    for payload in bills:
        try:
            record = offline.sync_offline_order(company=request.company, user=request.user, payload=payload)
            results.append(offline.result(record))
        except (ValidationError, ValueError, TypeError) as exc:
            messages = getattr(exc, "messages", [str(exc)])
            results.append({"client_id": str((payload or {}).get("client_id", "")), "status": "error",
                            "error": " ".join(messages)[:255]})
    return JsonResponse({"results": results})
