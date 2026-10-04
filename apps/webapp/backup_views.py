"""Backups: the owner's backup page (daily automatic backups, download, Google Drive) and the platform admin overview."""
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core import signing
from django.db.models import Count, Max, Q, Sum
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.translation import gettext as _

from apps.common.ids import pick_id
from apps.tenants import backups as svc
from apps.tenants.models import BackupSettings, Company, CompanyBackup

from .online_booking_views import owner_only
from .views import superuser_required

STATE_SALT = "bookpilot-drive-backup"


def _callback_url(request):
    return request.build_absolute_uri(reverse("webapp:backup_drive_callback"))


@login_required
@owner_only
def backups_page(request):
    company = request.company
    prefs = svc.settings_for(company)
    if request.method == "POST":
        action = request.POST.get("action")
        if action == "settings":
            prefs.enabled = request.POST.get("enabled") == "on"
            prefs.include_media = request.POST.get("include_media") == "on"
            keep = pick_id(request.POST.get("keep_days"))
            if keep in dict(BackupSettings.KEEP_CHOICES):
                prefs.keep_days = keep
            prefs.save()
            messages.success(request, _("Backup settings saved."))
        elif action == "now":
            if not svc.manual_allowed(company):
                messages.error(request, _("You made many backups today. Try again tomorrow."))
            else:
                record = svc.make_backup(company, kind="manual", user=request.user)
                if record.status == "ok":
                    messages.success(request, _("Backup made: %(rows)s records.") % {"rows": record.rows})
                else:
                    messages.error(request, _("The backup failed. Our team has been told; please try again later."))
        elif action == "drive_connect":
            if not svc.drive_configured():
                messages.error(request, _("Google Drive is not set up on this BookPilot server yet."))
            else:
                state = signing.dumps({"c": company.pk, "u": request.user.pk}, salt=STATE_SALT)
                return redirect(svc.drive_auth_url(_callback_url(request), state))
        elif action == "drive_disconnect":
            svc.drive_disconnect(prefs)
            messages.success(request, _("Google Drive disconnected."))
        return redirect("webapp:backups")
    items = CompanyBackup.objects.filter(company=company).select_related("created_by")[:60]
    return render(request, "webapp/backups/page.html", {
        "prefs": prefs, "items": items, "status": svc.status(company), "drive_ready": svc.drive_configured(),
        "keep_choices": BackupSettings.KEEP_CHOICES,
        "total_size": CompanyBackup.objects.filter(company=company, status="ok").aggregate(s=Sum("size"))["s"] or 0,
    })


@login_required
@owner_only
def backup_download(request, backup_id):
    backup = get_object_or_404(CompanyBackup, id=backup_id, company=request.company, status="ok")
    try:
        handle = svc.open_file(backup)
    except Exception:
        raise Http404(_("This backup file is no longer available."))
    from apps.audit.services import log_action
    log_action(company=request.company, user=request.user, action="export", model_name="CompanyBackup",
               object_id=backup.id, changes={"file": backup.file_name})
    return FileResponse(handle, as_attachment=True, filename=backup.file_name.rsplit("/", 1)[-1],
                        content_type="application/zip")


@login_required
@owner_only
def backup_drive_callback(request):
    prefs = svc.settings_for(request.company)
    try:
        state = signing.loads(request.GET.get("state") or "", salt=STATE_SALT, max_age=900)
    except signing.BadSignature:
        messages.error(request, _("The Google Drive link expired. Please try again."))
        return redirect("webapp:backups")
    if state.get("c") != request.company.pk or state.get("u") != request.user.pk:
        messages.error(request, _("The Google Drive link expired. Please try again."))
        return redirect("webapp:backups")
    if request.GET.get("error") or not request.GET.get("code"):
        messages.error(request, _("Google Drive was not connected."))
        return redirect("webapp:backups")
    try:
        svc.drive_connect(prefs, request.GET["code"], _callback_url(request))
        messages.success(request, _("Google Drive connected. Every backup is now copied to your Drive too."))
    except Exception as exc:
        messages.error(request, _("Google Drive could not be connected: %(error)s") % {"error": str(exc)[:160]})
    return redirect("webapp:backups")


@login_required
@superuser_required
def platform_backups(request):
    if request.method == "POST" and request.POST.get("action") == "run":
        result = svc.run_daily()
        messages.success(request, f"Backups made: {result['made']}, failed: {result['failed']}.")
        return redirect("webapp:platform_backups")
    q = (request.GET.get("q") or "").strip()
    companies = Company.objects.filter(is_active=True).annotate(
        last_ok=Max("backups__created_at", filter=Q(backups__status="ok")),
        failed=Count("backups", filter=Q(backups__status="failed")),
        stored=Sum("backups__size", filter=Q(backups__status="ok"))).order_by("last_ok", "name")
    if q:
        companies = companies.filter(name__icontains=q)
    from django.utils import timezone
    from datetime import timedelta
    stale = timezone.now() - timedelta(hours=36)
    companies = list(companies[:300])
    drive = set(BackupSettings.objects.filter(company__in=companies, drive_enabled=True).values_list("company_id", flat=True))
    rows = [{"c": c, "stale": not c.last_ok or c.last_ok < stale, "drive": c.pk in drive} for c in companies]
    return render(request, "webapp/backups/platform.html", {
        "rows": rows, "q": q, "stale_count": sum(1 for r in rows if r["stale"]),
        "drive_ready": svc.drive_configured(), "callback": _callback_url(request),
        "storage": "S3 (private-backups/)" if "backups" in settings.STORAGES else "Server folder (BACKUP_ROOT)",
    })
