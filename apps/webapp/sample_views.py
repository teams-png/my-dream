"""Owner's switch for the sample products, services and customers a new business starts with."""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from apps.common.safe_redirect import safe_next
from apps.industry import sample_kit


@login_required
@require_POST
def sample_data(request):
    company = request.company
    if request.POST.get("action") == "remove":
        kept = sample_kit.remove(company)
        messages.success(request, _("Sample data removed. You can now add your own products and services."))
        if kept:
            messages.info(request, _("%(n)s sample items were already used in bills, so they were switched off instead.") % {"n": kept})
    else:
        if sample_kit.install(company, request.user):
            messages.success(request, _("Sample data added. Remove it any time from the overview or Settings."))
    return redirect(safe_next(request, "webapp:dashboard"))


MILESTONES = {"devices", "tour_done", "checklist_hidden"}


@login_required
@require_POST
def milestone(request):
    """The browser reports a first-time step the server cannot see (printer set up, tour finished, checklist hidden)."""
    from django.http import JsonResponse
    from .checklist import mark
    key = request.POST.get("key", "")
    if request.company is None or key not in MILESTONES:
        return JsonResponse({"ok": False}, status=400)
    mark(request.company, key)
    return JsonResponse({"ok": True})
