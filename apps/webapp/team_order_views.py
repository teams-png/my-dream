"""Sports shops: team / club orders — jerseys with each player's name, number and size, a print sheet for the
printer, and the status and balance at a glance."""
import datetime
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.translation import gettext as _

from apps.customers.models import Customer
from apps.verticals.sports_shop.models import TeamOrder, TeamOrderPlayer

SPORTS_TYPES = {"sports_shop", "fitness_sports_store"}


def _company(request):
    company = getattr(request, "company", None)
    if company is None or company.business_type.code not in SPORTS_TYPES:
        raise Http404
    return company


def parse_players(text):
    """One player per line: "Name, Number, Size" (any part may be left out). Returns [(name, number, size)]."""
    players = []
    for line in (text or "").splitlines():
        parts = [p.strip() for p in line.replace("\t", ",").split(",")]
        if not any(parts):
            continue
        parts += [""] * (3 - len(parts))
        players.append((parts[0][:60], parts[1][:6], parts[2][:10].upper()))
    return players


def _money(value):
    try:
        return max(Decimal(str(value or "0").replace(",", "")), Decimal("0"))
    except InvalidOperation:
        return None


@login_required
def team_order_list(request):
    company = _company(request)
    orders = TeamOrder.objects.for_company(company).exclude(status="cancelled").prefetch_related("players")
    return render(request, "webapp/sports_shop/team_orders.html", {"orders": orders, "today": timezone.localdate()})


@login_required
def team_order_form(request, order_id=None):
    company = _company(request)
    order = get_object_or_404(TeamOrder.objects.for_company(company), id=order_id) if order_id else None
    data = request.POST if request.method == "POST" else {}
    errors = []
    if request.method == "POST":
        team = (data.get("team_name") or "").strip()
        item = (data.get("item") or "").strip()
        price, advance = _money(data.get("price_per_piece")), _money(data.get("advance"))
        try:
            due = datetime.date.fromisoformat(data.get("due_date") or "")
        except ValueError:
            due = None
        players = parse_players(data.get("players"))
        if not team or not item:
            errors.append(_("Enter the team name and what is being made."))
        if due is None:
            errors.append(_("Choose the delivery date."))
        if price is None or advance is None:
            errors.append(_("Price and advance must be numbers."))
        if not players:
            errors.append(_("Add at least one player: name, number, size — one per line."))
        if not errors:
            customer = Customer.objects.for_company(company).filter(id=data.get("customer") or 0).first()
            with transaction.atomic():
                order = order or TeamOrder(company=company)
                order.team_name, order.item, order.price_per_piece, order.advance = team, item, price, advance
                order.due_date, order.customer = due, customer
                order.contact_phone = (data.get("contact_phone") or "").strip()[:30]
                order.notes = (data.get("notes") or "").strip()
                order.save()
                order.players.all().delete()
                TeamOrderPlayer.objects.bulk_create(
                    [TeamOrderPlayer(company=company, order=order, name=n, number=no, size=s) for n, no, s in players])
            messages.success(request, _("Team order saved."))
            return redirect("webapp:team_order_detail", order_id=order.id)
    if request.method == "POST":
        values = {k: data.get(k, "") for k in ("team_name", "customer", "contact_phone", "item", "price_per_piece",
                                                 "advance", "due_date", "players", "notes")}
    elif order:
        values = {"team_name": order.team_name, "customer": str(order.customer_id or ""), "contact_phone": order.contact_phone,
                  "item": order.item, "price_per_piece": order.price_per_piece, "advance": order.advance,
                  "due_date": order.due_date.isoformat(), "notes": order.notes,
                  "players": "\n".join(", ".join(x for x in (p.name, p.number, p.size)) for p in order.players.all())}
    else:
        values = {"advance": "0", "due_date": (timezone.localdate() + datetime.timedelta(days=7)).isoformat()}
    return render(request, "webapp/sports_shop/team_order_form.html", {
        "order": order, "errors": errors, "v": values,
        "customers": Customer.objects.for_company(company).filter(is_active=True).order_by("name")})


@login_required
def team_order_detail(request, order_id):
    company = _company(request)
    order = get_object_or_404(TeamOrder.objects.for_company(company).prefetch_related("players"), id=order_id)
    if request.method == "POST" and request.POST.get("status") in dict(TeamOrder.STATUS):
        order.status = request.POST["status"]
        order.save(update_fields=["status"])
        messages.success(request, _("Status updated."))
        return redirect("webapp:team_order_detail", order_id=order.id)
    sizes = {}
    for p in order.players.all():
        sizes[p.size or "—"] = sizes.get(p.size or "—", 0) + 1
    return render(request, "webapp/sports_shop/team_order_detail.html", {
        "order": order, "sizes": sorted(sizes.items()), "statuses": TeamOrder.STATUS,
        "print": request.GET.get("print") == "1"})
