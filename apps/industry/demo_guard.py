"""Keeps the public demo businesses safe: visitors can try everything except things that reach outside the demo
(passwords, staff logins, exports, payments, sending email, uploading files)."""
from django.contrib import messages
from django.shortcuts import redirect
from django.utils.translation import gettext as _

BLOCKED = {"password_change", "security_settings", "export_data", "backups", "backup_download", "backup_drive_callback",
           "staff_invite", "staff_remove", "staff_role_change", "role_add", "role_permissions_edit", "switch_company",
           "online_payment_settings", "daily_report", "reminder_settings", "ob_wp_plugin", "rec_wp_plugin"}
BLOCKED_POST = {"company_settings", "help", "help_messages", "site_editor", "invoice_share", "setup",
                "tax_currency", "branch_add", "branch_edit", "branch_delete", "sample_data"}


def blocked(url_name, method, has_files):
    if url_name in BLOCKED or url_name.startswith("billing_") or url_name.startswith("platform_"):
        return True
    return method == "POST" and (url_name in BLOCKED_POST or has_files)


class DemoGuardMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)

    def process_view(self, request, view_func, view_args, view_kwargs):
        company = getattr(request, "company", None)
        match = getattr(request, "resolver_match", None)
        if company is None or not company.is_demo or not match or match.namespace != "webapp":
            return None
        if not blocked(match.url_name or "", request.method, bool(request.FILES)):
            return None
        messages.info(request, _("That is switched off in the demo. Start your free trial to use it with your own business."))
        return redirect("webapp:dashboard")
