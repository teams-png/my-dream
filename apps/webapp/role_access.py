"""Who may open which page: one table for the whole web app.

Every page whose url name is listed here needs that permission in the user's role (Owner always
passes). Pages that are not listed are open to every member: the POS, taking orders, customers,
bookings, today's work. Views keep their own @require_permission checks too; this table closes
the many pages that never had one, and hides their links from the sidebar.

Roles are edited by the owner under Settings → Roles. The defaults (apps.tenants.services) are:
Owner everything; Accountant money, reports, purchases and payroll; Staff day-to-day selling only."""
import re

from django.shortcuts import render
from django.urls import NoReverseMatch, reverse

SETTINGS = "business.manage_settings"
REPORTS = "reports.view"
PRODUCTS = "inventory.manage_products"
PURCHASES = "purchases.view_purchase"
EXPENSES = "expenses.view"
ACCOUNTS = "accounting.view_reports"
MEMBERS = "tenants.manage_members"
ROLES = "tenants.manage_roles"
EMPLOYEES = "employees.manage"
BANKING = "banking.view"

PAGE_PERMISSIONS = {
    # business settings, website, integrations, data
    **dict.fromkeys([
        "company_settings", "setup", "branch_list", "branch_add", "branch_edit", "branch_delete",
        "tax_currency", "online_payment_settings", "reminder_settings", "daily_report", "budgets",
        "ob_settings", "ob_wp_plugin", "restaurant_online_settings", "rec_website", "rec_wp_plugin",
        "site_editor", "scale_settings", "gold_rates",
        "restaurant_setup", "restaurant_profile_edit", "restaurant_integration_add", "restaurant_integration_edit",
        "restaurant_starter_kit", "restaurant_demo_menu", "sample_data", "restaurant_area_add", "restaurant_table_add",
        "restaurant_station_add", "restaurant_quick_sale_pin",
        "backups", "backup_download", "backup_drive_callback", "export_data", "company_audit_log",
        "coupon_add", "coupon_toggle", "mess_plan_add", "mess_plan_edit",
        "education_course_add", "education_course_edit", "property_add", "property_edit", "unit_add", "unit_edit",
        "booking_resource_add", "booking_resource_edit",
    ], SETTINGS),
    # team and roles
    **dict.fromkeys(["staff_members_list", "staff_invite", "staff_role_change", "staff_remove"], MEMBERS),
    **dict.fromkeys(["role_list", "role_add", "role_permissions_edit"], ROLES),
    # products, menu and prices
    **dict.fromkeys([
        "product_add", "product_edit", "product_delete", "product_variant_add", "product_import_csv", "product_import_template",
        "category_add", "category_edit", "category_delete", "brand_add", "brand_delete",
        "inventory_unit_add", "inventory_unit_delete", "unit_list",
        "restaurant_menu_item_add", "restaurant_menu_item_edit", "restaurant_menu_item_toggle",
        "restaurant_modifier_add", "restaurant_modifier_group_add", "restaurant_modifier_option_add",
        "restaurant_recipe_add", "restaurant_combo_add", "restaurant_combo_item_add",
        "pricing", "price_list_detail", "stock_transfer", "count_list", "count_detail",
    ], PRODUCTS),
    # reports and exports (money figures for the whole business)
    **dict.fromkeys([
        "analytics", "reports", "branch_stock_report", "restaurant_z_report", "acc_home",
        "product_export_csv", "customer_export_csv", "sales_export_csv",
    ], REPORTS),
    # suppliers and purchases
    **dict.fromkeys([
        "supplier_list", "supplier_add", "supplier_edit", "supplier_delete", "supplier_detail", "supplier_payment_add",
        "purchase_list", "purchase_add", "purchase_detail", "po_list", "po_add", "po_detail", "grn_detail",
    ], PURCHASES),
    # expenses and finance
    **dict.fromkeys([
        "expense_list", "expense_add", "expense_category_list", "expense_category_add",
        "expense_category_seed_defaults", "expense_category_delete",
    ], EXPENSES),
    **dict.fromkeys([
        "finance_home", "cheque_list", "cheque_status", "recurring_list", "recurring_action", "asset_list", "asset_dispose",
        "acc_pl", "acc_bs", "acc_tb", "acc_cf", "acc_vat", "acc_chart", "acc_ledger", "acc_journal",
        "acc_journal_add", "acc_journal_detail",
    ], ACCOUNTS),
    **dict.fromkeys(["bank_home", "bank_account"], BANKING),
    # staff records and payroll
    **dict.fromkeys([
        "staff_list", "staff_add", "staff_detail", "staff_edit", "staff_delete", "hr_attendance", "hr_attendance_month",
        "hr_leave", "hr_documents",
    ], EMPLOYEES),
    **dict.fromkeys(["hr_advances", "hr_payroll", "hr_payslip"], "employees.manage_payroll"),
}
REPORT_SUFFIX = re.compile(r"_reports?$")


def required_permission(url_name):
    if not url_name:
        return None
    if url_name in PAGE_PERMISSIONS:
        return PAGE_PERMISSIONS[url_name]
    if REPORT_SUFFIX.search(url_name):
        return REPORTS
    return None


def role_codes(request):
    """Permission codes of the signed-in member's role (cached on the request)."""
    if not hasattr(request, "_role_codes"):
        role = getattr(request, "role", None)
        request._role_codes = (set(role.permissions.values_list("permission__code", flat=True))
                               if role is not None else None)
    return request._role_codes


def is_owner(request):
    role = getattr(request, "role", None)
    return bool(role and role.is_system_role and role.name == "Owner")


def can_open(request, url_name):
    code = required_permission(url_name)
    if code is None or getattr(request, "role", None) is None or is_owner(request):
        return True
    return code in role_codes(request)


class RoleAccessMiddleware:
    """Refuses pages the member's role does not allow, with a friendly page instead of a redirect
    (a redirect could loop, e.g. an expired business sends everyone to Billing)."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)

    def process_view(self, request, view_func, view_args, view_kwargs):
        match = getattr(request, "resolver_match", None)
        if not match or match.namespace != "webapp" or getattr(request, "role", None) is None:
            return None
        if can_open(request, match.url_name):
            return None
        return render(request, "webapp/no_access.html", {"needed": required_permission(match.url_name)}, status=403)


def _webapp_url_names():
    from apps.webapp import urls
    return [p.name for p in urls.urlpatterns if p.name]


def blocked_paths(request):
    """Sidebar links (argument-free pages) this member can't open."""
    if getattr(request, "role", None) is None or is_owner(request):
        return set()
    codes = role_codes(request)
    paths = set()
    for name in _webapp_url_names():
        code = required_permission(name)
        if code is None or code in codes:
            continue
        try:
            paths.add(reverse(f"webapp:{name}"))
        except NoReverseMatch:
            continue
    return paths


_LINK = re.compile(r'<a\b[^>]*\bhref="([^"]+)"[^>]*>.*?</a>', re.S)
_SECTION = re.compile(r"<details\b[^>]*>\s*<summary\b.*?</summary>(?P<body>.*?)</details>", re.S)


def strip_links(html, paths):
    """Remove <a href> links to blocked paths, then any sidebar section left with no links."""
    if not paths:
        return html
    html = _LINK.sub(lambda m: "" if m.group(1).split("?")[0] in paths else m.group(0), html)
    return _SECTION.sub(lambda m: m.group(0) if "<a" in m.group("body") else "", html)
