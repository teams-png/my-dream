"""Help chat: clients write to BookPilot support; the platform admin answers from one inbox."""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _
from django.views.decorators.http import require_GET

from apps.platform_admin import support
from apps.platform_admin.models import SupportMessage, SupportTicket
from apps.tenants.models import Company

from .forms import PlatformSupportTicketForm
from .guide_views import support_details
from .views import superuser_required


def _json(msg):
    return {"id": msg.id, "mine": None, "admin": msg.from_admin, "body": msg.body,
            "who": (msg.sender.get_full_name() or msg.sender.email) if msg.sender else "",
            "at": timezone.localtime(msg.created_at).strftime("%d %b %Y, %H:%M")}


def _after(request):
    try:
        return int(request.GET.get("after") or 0)
    except ValueError:
        return 0


# ---------- client side ----------

@login_required
def help_chat(request):
    company = getattr(request, "company", None)
    if company is None:
        return render(request, "webapp/no_company.html")
    if request.method == "POST":
        try:
            support.client_send(company, request.user, request.POST.get("body"),
                                admin_url=lambda t: request.build_absolute_uri(
                                    reverse("webapp:platform_support_chat", args=[t.pk])))
        except ValidationError as exc:
            if request.headers.get("x-requested-with") == "fetch":
                return JsonResponse({"error": exc.messages[0]}, status=400)
            messages.error(request, exc.messages[0])
        if request.headers.get("x-requested-with") == "fetch":
            return _client_json(request, company)
        return redirect("webapp:help")
    support.mark_read_by_client(company)
    return render(request, "webapp/help.html", {
        "chat": support.conversation(company), "support": support_details(),
        "open": support.current_ticket(company),
    })


@login_required
@require_GET
def help_messages(request):
    company = getattr(request, "company", None)
    if company is None:
        return JsonResponse({"messages": []})
    return _client_json(request, company)


def _client_json(request, company):
    rows = [_json(m) for m in support.conversation(company).filter(id__gt=_after(request))]
    for row in rows:
        row["mine"] = not row["admin"]
        if row["admin"]:
            row["who"] = _("BookPilot support")  # never show the support person's own email to clients
    if any(r["admin"] for r in rows):
        support.mark_read_by_client(company)
    return JsonResponse({"messages": rows})


# ---------- platform admin ----------

SHOW = [("open", "Open"), ("unread", "Unread"), ("resolved", "Resolved"), ("all", "All")]


@login_required
@superuser_required
def platform_support_list(request):
    show = request.GET.get("show") if request.GET.get("show") in dict(SHOW) else "open"
    q = (request.GET.get("q") or "").strip()
    tickets = SupportTicket.objects.select_related("company", "company__business_type", "raised_by")
    if show == "open":
        tickets = tickets.filter(status__in=support.OPEN)
    elif show == "unread":
        tickets = tickets.filter(admin_unread__gt=0)
    elif show == "resolved":
        tickets = tickets.filter(status__in=["resolved", "closed"])
    if q:
        tickets = tickets.filter(Q(company__name__icontains=q) | Q(company__phone__icontains=q) |
                                 Q(company__email__icontains=q) | Q(subject__icontains=q) |
                                 Q(raised_by__email__icontains=q) | Q(company__country__icontains=q))
    tickets = tickets.order_by("-admin_unread", "-last_message_at", "-created_at")[:300]
    rows = []
    for t in tickets:
        last = t.messages.order_by("-created_at", "-id").first()
        rows.append({"t": t, "last": last})
    return render(request, "webapp/platform_admin/support_list.html", {
        "rows": rows, "show": show, "tabs": SHOW, "q": q, "unread": support.admin_unread_total(),
    })


@login_required
@superuser_required
def platform_support_chat(request, ticket_id):
    ticket = get_object_or_404(SupportTicket.objects.select_related("company", "raised_by"), id=ticket_id)
    form = PlatformSupportTicketForm(instance=ticket)
    if request.method == "POST":
        action = request.POST.get("action", "reply")
        if action == "reply":
            try:
                support.admin_reply(ticket, request.user, request.POST.get("body"))
            except ValidationError as exc:
                if request.headers.get("x-requested-with") == "fetch":
                    return JsonResponse({"error": exc.messages[0]}, status=400)
                messages.error(request, exc.messages[0])
            if request.headers.get("x-requested-with") == "fetch":
                return _admin_json(request, ticket)
        else:
            form = PlatformSupportTicketForm(request.POST, instance=ticket)
            if form.is_valid():
                form.save()
                messages.success(request, "Conversation updated.")
        return redirect("webapp:platform_support_chat", ticket_id=ticket.id)
    support.mark_read_by_admin(ticket)
    company = ticket.company
    return render(request, "webapp/platform_admin/support_chat.html", {
        "ticket": ticket, "form": form, "d": support.client_details(company),
        "chat": SupportMessage.objects.filter(ticket=ticket).select_related("sender"),
        "older": SupportTicket.objects.filter(company=company).exclude(pk=ticket.pk).order_by("-created_at")[:10],
        "writer": ticket.raised_by,
    })


@login_required
@superuser_required
@require_GET
def platform_support_messages(request, ticket_id):
    return _admin_json(request, get_object_or_404(SupportTicket, id=ticket_id))


def _admin_json(request, ticket):
    rows = [_json(m) for m in SupportMessage.objects.filter(ticket=ticket, id__gt=_after(request)).select_related("sender")]
    for row in rows:
        row["mine"] = row["admin"]
    if any(not r["admin"] for r in rows):
        support.mark_read_by_admin(ticket)
    return JsonResponse({"messages": rows})


@login_required
@superuser_required
def platform_support_start(request, company_id):
    company = get_object_or_404(Company, id=company_id)
    if request.method == "POST":
        try:
            ticket = support.admin_start(company, request.user, request.POST.get("body"))
            return redirect("webapp:platform_support_chat", ticket_id=ticket.id)
        except ValidationError as exc:
            messages.error(request, exc.messages[0])
    ticket = support.current_ticket(company)
    if ticket:
        return redirect("webapp:platform_support_chat", ticket_id=ticket.id)
    return render(request, "webapp/platform_admin/support_start.html", {
        "company": company, "d": support.client_details(company)})


@login_required
@superuser_required
@require_GET
def platform_support_unread(request):
    latest = (SupportTicket.objects.filter(admin_unread__gt=0).select_related("company")
              .order_by("-last_message_at").first())
    return JsonResponse({
        "unread": support.admin_unread_total(),
        "latest": {"id": latest.id, "company": latest.company.name, "subject": latest.subject,
                   "url": reverse("webapp:platform_support_chat", args=[latest.id])} if latest else None,
    })


@login_required
@superuser_required
def platform_support_edit(request, ticket_id):
    return redirect("webapp:platform_support_chat", ticket_id=ticket_id)
