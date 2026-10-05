from django.contrib import messages
from django.contrib.auth import get_user_model, login
from django.contrib.auth import views as auth_views
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _

from apps.accounts import services as account_services
from apps.accounts import twofactor

PENDING_MAX_AGE = 300  # seconds allowed between password and code


def login_2fa(request):
    pending = request.session.get("2fa_pending")
    if not pending or timezone.now().timestamp() - pending.get("at", 0) > PENDING_MAX_AGE:
        request.session.pop("2fa_pending", None)
        messages.error(request, "Please sign in again.")
        return redirect("webapp:login")
    user = get_user_model().objects.filter(pk=pending["user_id"], is_active=True).first()
    if user is None:
        return redirect("webapp:login")
    if request.method == "POST":
        identifier = f"2fa:{user.pk}"
        ip_address = account_services.client_ip(request)
        if account_services.is_locked_out(identifier, ip_address):
            messages.error(request, "Too many wrong codes. Try again in a few minutes.")
            return render(request, "webapp/auth/login_2fa.html", {"user_email": user.email})
        ok = twofactor.verify(user, request.POST.get("code", ""))
        account_services.record_attempt(identifier, ip_address, successful=ok)
        if ok:
            request.session.pop("2fa_pending", None)
            login(request, user, backend=pending.get("backend"))
            if twofactor.remaining_recovery_codes(user) <= 2:
                messages.warning(request, "You are running out of recovery codes. Create new ones in Security settings.")
            return redirect("webapp:platform_admin_dashboard" if user.is_platform_admin else "webapp:dashboard")
        messages.error(request, "That code is not correct. Check the time on your phone and try again.")
    return render(request, "webapp/auth/login_2fa.html", {"user_email": user.email})


@login_required
def security_settings(request):
    user = request.user
    context = {"enabled": twofactor.is_enabled(user), "recovery_left": twofactor.remaining_recovery_codes(user)}
    action = request.POST.get("action") if request.method == "POST" else None

    if action == "start":
        secret = twofactor.start_setup(user)
        request.session["2fa_setup_secret"] = secret
        return redirect("webapp:security_settings")
    if action == "confirm":
        codes = twofactor.confirm_setup(user, request.POST.get("code", ""))
        if codes:
            request.session.pop("2fa_setup_secret", None)
            messages.success(request, "Two-step login is on. Save your recovery codes now.")
            return render(request, "webapp/security.html", {**context, "enabled": True, "recovery_codes": codes, "recovery_left": len(codes)})
        messages.error(request, "That code did not match. Scan the QR code again and enter the newest code.")
    if action in {"disable", "regenerate"}:
        if not user.check_password(request.POST.get("password", "")) or not twofactor.verify(user, request.POST.get("code", "")):
            messages.error(request, "Password or code is not correct.")
            return redirect("webapp:security_settings")
        if action == "disable":
            twofactor.disable(user)
            messages.success(request, "Two-step login is off.")
            return redirect("webapp:security_settings")
        codes = twofactor.regenerate_recovery_codes(user)
        messages.success(request, "New recovery codes created. The old ones no longer work.")
        return render(request, "webapp/security.html", {**context, "enabled": True, "recovery_codes": codes, "recovery_left": len(codes)})

    secret = request.session.get("2fa_setup_secret")
    if secret and not context["enabled"]:
        uri = twofactor.provisioning_uri(user, secret)
        context.update({"setup_secret": secret, "qr_svg": twofactor.qr_svg(uri)})
    return render(request, "webapp/security.html", context)


@login_required
def export_data(request):
    """Owner-only download of every record of the active business (backup / portability)."""
    from django.http import HttpResponse
    from apps.common.exporting import export_company_zip
    company = getattr(request, "company", None)
    role = getattr(request, "role", None)
    if company is None or role is None or role.name != "Owner":
        messages.error(request, "Only the business owner can download all data.")
        return redirect("webapp:dashboard")
    if request.method != "POST":
        return redirect("webapp:security_settings")
    data, counts = export_company_zip(company, include_media=request.POST.get("media") == "1")
    from apps.audit.services import log_action
    log_action(company=company, user=request.user, action="export", model_name="Company", object_id=company.id,
               changes={"tables": len(counts), "rows": sum(counts.values())})
    response = HttpResponse(data, content_type="application/zip")
    response["Content-Disposition"] = f'attachment; filename="{company.slug}-{timezone.localdate():%Y%m%d}.zip"'
    return response


class PasswordChange(auth_views.PasswordChangeView):
    """Signed-in users change their own password (old password + new one twice); stays signed in."""
    template_name = "webapp/auth/password_change.html"

    def get_success_url(self):
        return reverse("webapp:password_change")

    def form_valid(self, form):
        response = super().form_valid(form)
        from apps.audit.services import log_action
        company = getattr(self.request, "company", None)
        if company is not None:
            log_action(company=company, user=self.request.user, action="update", model_name="User",
                       object_id=self.request.user.pk, changes={"password": "changed"})
        messages.success(self.request, _("Your password has been changed."))
        return response
