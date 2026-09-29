from django.urls import path
from django.contrib.auth import views as auth_views
from . import device_views, finance_views, offline_views, onboarding_views, public_views, security_views, share_views, views

app_name = "webapp"

urlpatterns = [
    path("login/", views.login_view, name="login"),
    path("login/verify/", security_views.login_2fa, name="login_2fa"),
    path("account/security/", security_views.security_settings, name="security_settings"),
    path("account/export/", security_views.export_data, name="export_data"),
    path("logout/", views.logout_view, name="logout"),

    path("password-reset/", auth_views.PasswordResetView.as_view(
        template_name="webapp/auth/password_reset_form.html",
        email_template_name="webapp/auth/password_reset_email.html",
        subject_template_name="webapp/auth/password_reset_subject.txt",
        success_url="/password-reset/done/",
    ), name="password_reset"),
    path("password-reset/done/", auth_views.PasswordResetDoneView.as_view(
        template_name="webapp/auth/password_reset_done.html",
    ), name="password_reset_done"),
    path("reset/<uidb64>/<token>/", auth_views.PasswordResetConfirmView.as_view(
        template_name="webapp/auth/password_reset_confirm.html",
        success_url="/reset/done/",
    ), name="password_reset_confirm"),
    path("reset/done/", auth_views.PasswordResetCompleteView.as_view(
        template_name="webapp/auth/password_reset_complete.html",
    ), name="password_reset_complete"),
    path("switch-company/<int:company_id>/", views.switch_company, name="switch_company"),
    path("admin-console/new-client/", views.register_client, name="register_client"),

    path("platform/", views.platform_admin_dashboard, name="platform_admin_dashboard"),
    path("platform/clients/", views.platform_admin_company_list, name="platform_admin_company_list"),
    path("platform/clients/<int:company_id>/", views.platform_admin_company_detail, name="platform_admin_company_detail"),
    path("platform/users/<int:user_id>/edit/", views.platform_admin_edit_user, name="platform_admin_edit_user"),
    path("platform/clients/<int:company_id>/delete/", views.platform_admin_company_delete, name="platform_admin_company_delete"),
    path("platform/clients/<int:company_id>/change-plan/", views.platform_admin_change_plan, name="platform_admin_change_plan"),
    path("platform/clients/<int:company_id>/record-payment/", views.platform_admin_record_payment, name="platform_admin_record_payment"),
    path("platform/clients/<int:company_id>/modules/", views.platform_admin_manage_modules, name="platform_admin_manage_modules"),
    path("platform/clients/<int:company_id>/business-suites/", views.platform_admin_manage_business_suites, name="platform_admin_manage_business_suites"),

    path("platform/clients/<int:company_id>/restore/", views.platform_admin_company_restore, name="platform_admin_company_restore"),
    path("platform/clients/<int:company_id>/roles/", views.platform_admin_roles, name="platform_admin_roles"),
    path("platform/clients/<int:company_id>/roles/<int:role_id>/permissions/", views.platform_admin_role_permissions, name="platform_admin_role_permissions"),
    path("platform/plans/", views.platform_plan_list, name="platform_plan_list"),
    path("platform/plans/add/", views.platform_plan_add, name="platform_plan_add"),
    path("platform/plans/<int:plan_id>/edit/", views.platform_plan_edit, name="platform_plan_edit"),

    path("platform/analytics/", views.platform_admin_analytics, name="platform_admin_analytics"),
    path("platform/commercial/", views.platform_commercial_control, name="platform_commercial_control"),
    path("platform/permissions/", views.platform_permission_catalogue, name="platform_permission_catalogue"),
    path("platform/clients/<int:company_id>/commercial/", views.platform_client_commercial_profile, name="platform_client_commercial_profile"),

    path("platform/pending-payments/", views.platform_pending_payments, name="platform_pending_payments"),
    path("platform/pending-payments/<int:payment_id>/approve/", views.platform_approve_payment, name="platform_approve_payment"),
    path("platform/setup/", views.platform_setup, name="platform_setup"),
    path("platform/setup/payment-gateways/", views.platform_payment_gateway_settings, name="platform_payment_gateway_settings"),
    path("platform/setup/modules/", views.platform_module_list, name="platform_module_list"),
    path("platform/setup/modules/add/", views.platform_module_form, name="platform_module_add"),
    path("platform/setup/modules/<int:module_id>/edit/", views.platform_module_form, name="platform_module_edit"),
    path("platform/setup/business-types/", views.platform_business_type_list, name="platform_business_type_list"),
    path("platform/setup/business-types/add/", views.platform_business_type_form, name="platform_business_type_add"),
    path("platform/setup/business-types/<int:business_type_id>/edit/", views.platform_business_type_form, name="platform_business_type_edit"),
    path("platform/users/", views.platform_user_list, name="platform_user_list"),
    path("platform/support/", views.platform_support_list, name="platform_support_list"),
    path("platform/support/<int:ticket_id>/edit/", views.platform_support_edit, name="platform_support_edit"),
    path("platform/audit-log/", views.platform_audit_list, name="platform_audit_list"),
    path("", public_views.home, name="dashboard"),
    path("welcome/", public_views.landing, name="landing"),
    path("signup/", public_views.signup, name="signup"),

    path("customers/", views.customer_list, name="customer_list"),
    path("customers/add/", views.customer_add, name="customer_add"),
    path("customers/<int:customer_id>/edit/", views.customer_edit, name="customer_edit"),
    path("customers/<int:customer_id>/delete/", views.customer_delete, name="customer_delete"),

    path("staff/", views.staff_list, name="staff_list"),
    path("staff/add/", views.staff_add, name="staff_add"),
    path("staff/<int:staff_id>/edit/", views.staff_edit, name="staff_edit"),
    path("staff/<int:staff_id>/delete/", views.staff_delete, name="staff_delete"),

    path("units/", views.inventory_unit_list, name="inventory_unit_list"),
    path("units/add/", views.inventory_unit_add, name="inventory_unit_add"),
    path("units/<int:unit_id>/delete/", views.inventory_unit_delete, name="inventory_unit_delete"),

    path("suppliers/", views.supplier_list, name="supplier_list"),
    path("suppliers/add/", views.supplier_add, name="supplier_add"),
    path("suppliers/<int:supplier_id>/edit/", views.supplier_edit, name="supplier_edit"),
    path("suppliers/<int:supplier_id>/delete/", views.supplier_delete, name="supplier_delete"),
    path("suppliers/<int:supplier_id>/", views.supplier_detail, name="supplier_detail"),
    path("suppliers/<int:supplier_id>/pay/", views.supplier_payment_add, name="supplier_payment_add"),

    path("purchases/", views.purchase_list, name="purchase_list"),
    path("purchases/add/", views.purchase_add, name="purchase_add"),
    path("purchases/reports/", views.purchase_reports, name="purchase_reports"),

    path("pos/", views.pos_view, name="pos"),
    path("finance/", finance_views.finance_home, name="finance_home"),
    path("finance/cheques/", finance_views.cheque_list, name="cheque_list"),
    path("finance/cheques/<int:cheque_id>/status/", finance_views.cheque_status, name="cheque_status"),
    path("finance/recurring/", finance_views.recurring_list, name="recurring_list"),
    path("finance/recurring/<int:recurring_id>/", finance_views.recurring_action, name="recurring_action"),
    path("finance/assets/", finance_views.asset_list, name="asset_list"),
    path("finance/assets/<int:asset_id>/dispose/", finance_views.asset_dispose, name="asset_dispose"),
    path("devices/", device_views.devices_settings, name="devices"),
    path("devices/customer-display/", device_views.customer_display, name="customer_display"),
    path("devices/print/invoice/<int:invoice_id>.json", device_views.invoice_receipt_data, name="device_invoice_receipt"),
    path("devices/print/restaurant/<int:order_id>.json", device_views.restaurant_receipt_data, name="device_restaurant_receipt"),
    path("devices/print/kot/<int:ticket_id>.json", device_views.kot_data, name="device_kot"),
    path("pos/checkout/", views.pos_checkout, name="pos_checkout"),
    path("pos/offline/sync/", views.pos_offline_sync, name="pos_offline_sync"),
    path("pos/offline/sales/", views.pos_offline_sales, name="pos_offline_sales"),
    path("setup/", onboarding_views.setup_wizard, name="setup"),
    path("setup/<slug:step>/", onboarding_views.setup_wizard, name="setup"),

    path("returns/", views.sales_return_list, name="sales_return_list"),
    path("returns/lookup/", views.sales_return_lookup, name="sales_return_lookup"),
    path("returns/<int:invoice_id>/new/", views.sales_return_add, name="sales_return_add"),
    path("returns/reports/", views.sales_return_reports, name="sales_return_reports"),

    path("expenses/categories/", views.expense_category_list, name="expense_category_list"),
    path("expenses/categories/add/", views.expense_category_add, name="expense_category_add"),
    path("expenses/categories/seed-defaults/", views.expense_category_seed_defaults, name="expense_category_seed_defaults"),
    path("expenses/categories/<int:category_id>/delete/", views.expense_category_delete, name="expense_category_delete"),
    path("expenses/", views.expense_list, name="expense_list"),
    path("expenses/add/", views.expense_add, name="expense_add"),
    path("expenses/reports/", views.expense_reports, name="expense_reports"),

    path("team/", views.staff_members_list, name="staff_members_list"),
    path("team/invite/", views.staff_invite, name="staff_invite"),
    path("team/<int:membership_id>/role/", views.staff_role_change, name="staff_role_change"),
    path("team/<int:membership_id>/remove/", views.staff_remove, name="staff_remove"),

    path("roles/", views.role_list, name="role_list"),
    path("roles/add/", views.role_add, name="role_add"),
    path("roles/<int:role_id>/permissions/", views.role_permissions_edit, name="role_permissions_edit"),

    path("analytics/", views.analytics_view, name="analytics"),

    path("billing/", views.billing_view, name="billing"),
    path("billing/stripe/checkout/", views.billing_stripe_checkout, name="billing_stripe_checkout"),
    path("billing/stripe/webhook/", views.billing_stripe_webhook, name="billing_stripe_webhook"),

    path("billing/razorpay/order/", views.billing_razorpay_order, name="billing_razorpay_order"),
    path("billing/razorpay/verify/", views.billing_razorpay_verify, name="billing_razorpay_verify"),
    path("billing/razorpay/webhook/", views.billing_razorpay_webhook, name="billing_razorpay_webhook"),

    path("settings/", views.company_settings, name="company_settings"),

    path("notifications/", views.notification_list, name="notification_list"),
    path("notifications/<int:notification_id>/read/", views.notification_mark_read, name="notification_mark_read"),
    path("notifications/mark-all-read/", views.notification_mark_all_read, name="notification_mark_all_read"),

    path("branches/", views.branch_list, name="branch_list"),
    path("branches/add/", views.branch_add, name="branch_add"),
    path("branches/<int:branch_id>/edit/", views.branch_edit, name="branch_edit"),
    path("branches/<int:branch_id>/delete/", views.branch_delete, name="branch_delete"),
    path("branches/stock/", views.branch_stock_report, name="branch_stock_report"),

    path("mobile-shop/products/export/", views.product_export_csv, name="product_export_csv"),
    path("mobile-shop/products/import/", views.product_import_csv, name="product_import_csv"),
    path("customers/export/", views.customer_export_csv, name="customer_export_csv"),
    path("retail/sales/export/", views.sales_export_csv, name="sales_export_csv"),

    path("coupons/", views.coupon_list, name="coupon_list"),
    path("coupons/add/", views.coupon_add, name="coupon_add"),
    path("coupons/<int:coupon_id>/toggle/", views.coupon_toggle, name="coupon_toggle"),
    path("coupons/validate/", views.coupon_validate_api, name="coupon_validate_api"),

    path("loyalty/", views.loyalty_accounts_list, name="loyalty_accounts_list"),
    path("loyalty/redeem/", views.loyalty_redeem, name="loyalty_redeem"),

    path("brands/", views.brand_list, name="brand_list"),
    path("brands/add/", views.brand_add, name="brand_add"),
    path("brands/<int:brand_id>/delete/", views.brand_delete, name="brand_delete"),

    path("barcodes/print/", views.barcode_print, name="barcode_print"),

    # ---- Mobile Shop ----
    path("mobile-shop/categories/", views.category_list, name="category_list"),
    path("mobile-shop/categories/add/", views.category_add, name="category_add"),
    path("mobile-shop/categories/<int:category_id>/edit/", views.category_edit, name="category_edit"),
    path("mobile-shop/categories/<int:category_id>/delete/", views.category_delete, name="category_delete"),

    path("mobile-shop/products/", views.product_list, name="product_list"),
    path("mobile-shop/products/add/", views.product_add, name="product_add"),
    path("mobile-shop/products/<int:product_id>/edit/", views.product_edit, name="product_edit"),
    path("mobile-shop/products/<int:product_id>/delete/", views.product_delete, name="product_delete"),
    path("mobile-shop/products/<int:product_id>/variants/add/", views.product_variant_add, name="product_variant_add"),
    path("mobile-shop/products/<int:product_id>/barcode/", views.product_barcode, name="product_barcode"),

    path("mobile-shop/units/", views.unit_list, name="unit_list"),
    path("mobile-shop/units/add/", views.unit_add, name="unit_add"),
    path("mobile-shop/units/bulk-imei/", views.mobile_bulk_imei_add, name="mobile_bulk_imei_add"),
    path("mobile-shop/units/<int:unit_id>/sell/", views.sell_unit, name="sell_unit"),

    path("mobile-shop/sales/", views.sale_list, name="sale_list"),
    path("mobile-shop/reports/", views.reports, name="reports"),
    path("mobile-shop/repairs/", views.mobile_repair_list, name="mobile_repair_list"),
    path("mobile-shop/repairs/add/", views.mobile_repair_form, name="mobile_repair_add"),
    path("mobile-shop/repairs/<int:job_id>/", views.mobile_repair_detail, name="mobile_repair_detail"),
    path("mobile-shop/repairs/<int:job_id>/edit/", views.mobile_repair_form, name="mobile_repair_edit"),
    path("mobile-shop/repairs/<int:job_id>/parts/add/", views.mobile_repair_part_add, name="mobile_repair_part_add"),
    path("mobile-shop/repairs/<int:job_id>/complete/", views.mobile_repair_complete, name="mobile_repair_complete"),
    path("mobile-shop/warranty/", views.mobile_warranty_list, name="mobile_warranty_list"),
    path("mobile-shop/warranty/add/", views.mobile_warranty_form, name="mobile_warranty_add"),
    path("mobile-shop/warranty/<int:claim_id>/edit/", views.mobile_warranty_form, name="mobile_warranty_edit"),
    path("mobile-shop/trade-ins/", views.mobile_tradein_list, name="mobile_tradein_list"),
    path("mobile-shop/trade-ins/add/", views.mobile_tradein_add, name="mobile_tradein_add"),
    path("mobile-shop/trade-ins/<int:trade_id>/accept/", views.mobile_tradein_accept, name="mobile_tradein_accept"),
    path("mobile-shop/installments/", views.mobile_installment_list, name="mobile_installment_list"),
    path("mobile-shop/installments/<int:plan_id>/pay/", views.mobile_installment_payment, name="mobile_installment_payment"),

    # ---- Gym ----
    path("gym/plans/", views.plan_list, name="plan_list"),
    path("gym/plans/add/", views.plan_add, name="plan_add"),
    path("gym/plans/<int:plan_id>/edit/", views.plan_edit, name="plan_edit"),
    path("gym/plans/<int:plan_id>/delete/", views.plan_delete, name="plan_delete"),

    path("gym/members/", views.member_list, name="member_list"),
    path("gym/members/enroll/", views.member_enroll, name="member_enroll"),
    path("gym/members/<int:member_id>/renew/", views.member_renew, name="member_renew"),
    path("gym/members/<int:member_id>/status/", views.member_status_toggle, name="member_status_toggle"),

    path("gym/attendance/", views.attendance_today, name="attendance_today"),
    path("gym/attendance/<int:member_id>/check-in/", views.attendance_check_in, name="attendance_check_in"),
    path("gym/attendance/<int:entry_id>/check-out/", views.attendance_check_out, name="attendance_check_out"),

    path("gym/reports/", views.gym_reports, name="gym_reports"),

    # ---- Spa ----
    path("spa/services/", views.spa_service_list, name="spa_service_list"),
    path("spa/services/add/", views.spa_service_add, name="spa_service_add"),
    path("spa/services/<int:service_id>/edit/", views.spa_service_edit, name="spa_service_edit"),
    path("spa/services/<int:service_id>/delete/", views.spa_service_delete, name="spa_service_delete"),

    path("spa/appointments/", views.appointment_list, name="appointment_list"),
    path("spa/appointments/book/", views.appointment_book, name="appointment_book"),
    path("spa/appointments/<int:appointment_id>/complete/", views.appointment_complete, name="appointment_complete"),
    path("spa/appointments/<int:appointment_id>/cancel/", views.appointment_cancel, name="appointment_cancel"),

    path("spa/reports/", views.spa_reports, name="spa_reports"),

    # ---- Textile ----
    path("textile/fabrics/", views.fabric_list, name="fabric_list"),
    path("textile/fabrics/add/", views.fabric_add, name="fabric_add"),
    path("textile/fabrics/<int:fabric_id>/edit/", views.fabric_edit, name="fabric_edit"),
    path("textile/fabrics/<int:fabric_id>/delete/", views.fabric_delete, name="fabric_delete"),

    path("textile/measurements/", views.measurement_list, name="measurement_list"),
    path("textile/measurements/add/", views.measurement_add, name="measurement_add"),
    path("textile/measurements/<int:measurement_id>/edit/", views.measurement_edit, name="measurement_edit"),
    path("textile/measurements/<int:measurement_id>/delete/", views.measurement_delete, name="measurement_delete"),

    path("textile/orders/", views.order_list, name="order_list"),
    path("textile/orders/add/", views.order_add, name="order_add"),
    path("textile/orders/<int:order_id>/edit/", views.order_edit, name="order_edit"),
    path("textile/orders/<int:order_id>/cancel/", views.order_cancel, name="order_cancel"),
    path("textile/orders/<int:order_id>/ready/", views.order_mark_ready, name="order_mark_ready"),
    path("textile/orders/<int:order_id>/delivered/", views.order_mark_delivered, name="order_mark_delivered"),

    path("textile/reports/", views.textile_reports, name="textile_reports"),

    # ---- Vehicle Wash ----
    path("vehicle-wash/vehicles/", views.vehicle_list, name="vehicle_list"),
    path("vehicle-wash/vehicles/add/", views.vehicle_add, name="vehicle_add"),
    path("vehicle-wash/vehicles/<int:vehicle_id>/edit/", views.vehicle_edit, name="vehicle_edit"),
    path("vehicle-wash/vehicles/<int:vehicle_id>/delete/", views.vehicle_delete, name="vehicle_delete"),

    path("vehicle-wash/packages/", views.wash_package_list, name="wash_package_list"),
    path("vehicle-wash/packages/add/", views.wash_package_add, name="wash_package_add"),
    path("vehicle-wash/packages/<int:package_id>/edit/", views.wash_package_edit, name="wash_package_edit"),
    path("vehicle-wash/packages/<int:package_id>/delete/", views.wash_package_delete, name="wash_package_delete"),

    path("vehicle-wash/orders/", views.wash_order_list, name="wash_order_list"),
    path("vehicle-wash/orders/book/", views.wash_order_book, name="wash_order_book"),
    path("vehicle-wash/orders/<int:order_id>/start/", views.wash_order_start, name="wash_order_start"),
    path("vehicle-wash/orders/<int:order_id>/complete/", views.wash_order_complete, name="wash_order_complete"),
    path("vehicle-wash/orders/<int:order_id>/cancel/", views.wash_order_cancel, name="wash_order_cancel"),

    path("vehicle-wash/reports/", views.vehicle_wash_reports, name="vehicle_wash_reports"),

    # ---- Sports Shop ----
    path("sports-shop/products/", views.sports_product_list, name="sports_product_list"),
    path("sports-shop/products/add/", views.sports_product_add, name="sports_product_add"),

    # ---- Cycle Shop ----
    path("cycle-shop/units/", views.cycle_unit_list, name="cycle_unit_list"),
    path("cycle-shop/units/add/", views.cycle_unit_add, name="cycle_unit_add"),
    path("cycle-shop/units/<int:unit_id>/edit/", views.cycle_unit_edit, name="cycle_unit_edit"),
    path("cycle-shop/units/<int:unit_id>/delete/", views.cycle_unit_delete, name="cycle_unit_delete"),
    path("cycle-shop/units/<int:unit_id>/sell/", views.cycle_sell, name="cycle_sell"),
    path("cycle-shop/tickets/", views.service_ticket_list, name="service_ticket_list"),
    path("cycle-shop/tickets/add/", views.service_ticket_add, name="service_ticket_add"),
    path("cycle-shop/tickets/<int:ticket_id>/start/", views.service_ticket_start, name="service_ticket_start"),
    path("cycle-shop/tickets/<int:ticket_id>/complete/", views.service_ticket_complete, name="service_ticket_complete"),
    path("cycle-shop/tickets/<int:ticket_id>/deliver/", views.service_ticket_deliver, name="service_ticket_deliver"),
    path("cycle-shop/reports/", views.cycle_shop_reports, name="cycle_shop_reports"),

    # ---- Saloon ----
    path("saloon/services/", views.saloon_service_list, name="saloon_service_list"),
    path("saloon/services/add/", views.saloon_service_add, name="saloon_service_add"),
    path("saloon/services/<int:service_id>/edit/", views.saloon_service_edit, name="saloon_service_edit"),
    path("saloon/services/<int:service_id>/delete/", views.saloon_service_delete, name="saloon_service_delete"),
    path("saloon/appointments/", views.saloon_appointment_list, name="saloon_appointment_list"),
    path("saloon/appointments/book/", views.saloon_appointment_book, name="saloon_appointment_book"),
    path("saloon/appointments/<int:appointment_id>/complete/", views.saloon_appointment_complete, name="saloon_appointment_complete"),
    path("saloon/appointments/<int:appointment_id>/cancel/", views.saloon_appointment_cancel, name="saloon_appointment_cancel"),
    path("saloon/reports/", views.saloon_reports, name="saloon_reports"),

    path("service-suite/profiles/", views.service_profile_list, name="service_profile_list"),
    path("service-suite/profiles/add/", views.service_profile_form, name="service_profile_add"),
    path("service-suite/profiles/<int:profile_id>/edit/", views.service_profile_form, name="service_profile_edit"),
    path("service-suite/cases/", views.service_case_list, name="service_case_list"),
    path("service-suite/cases/add/", views.service_case_form, name="service_case_add"),
    path("service-suite/cases/<int:case_id>/", views.service_case_detail, name="service_case_detail"),
    path("service-suite/cases/<int:case_id>/edit/", views.service_case_form, name="service_case_edit"),
    path("service-suite/cases/<int:case_id>/notes/add/", views.service_case_note_add, name="service_case_note_add"),
    path("service-suite/packages/", views.service_package_list, name="service_package_list"),
    path("service-suite/packages/add/", views.service_package_add, name="service_package_add"),
    path("service-suite/packages/sell/", views.service_package_purchase, name="service_package_purchase"),
    path("service-suite/reports/", views.service_suite_reports, name="service_suite_reports"),

    # ---- Beauty Parlour ----
    path("beauty-parlour/services/", views.beauty_service_list, name="beauty_service_list"),
    path("beauty-parlour/services/add/", views.beauty_service_add, name="beauty_service_add"),
    path("beauty-parlour/services/<int:service_id>/edit/", views.beauty_service_edit, name="beauty_service_edit"),
    path("beauty-parlour/services/<int:service_id>/delete/", views.beauty_service_delete, name="beauty_service_delete"),
    path("beauty-parlour/appointments/", views.beauty_appointment_list, name="beauty_appointment_list"),
    path("beauty-parlour/appointments/book/", views.beauty_appointment_book, name="beauty_appointment_book"),
    path("beauty-parlour/appointments/<int:appointment_id>/complete/", views.beauty_appointment_complete, name="beauty_appointment_complete"),
    path("beauty-parlour/appointments/<int:appointment_id>/cancel/", views.beauty_appointment_cancel, name="beauty_appointment_cancel"),
    path("beauty-parlour/reports/", views.beauty_reports, name="beauty_reports"),

    # ---- Medical Shop ----
    path("medical-shop/batches/", views.medicine_batch_list, name="medicine_batch_list"),
    path("medical-shop/batches/add/", views.medicine_batch_add, name="medicine_batch_add"),
    path("medical-shop/batches/<int:batch_id>/dispense/", views.medicine_dispense, name="medicine_dispense"),
    path("medical-shop/dispenses/", views.medicine_dispense_history, name="medicine_dispense_history"),
    path("medical-shop/reports/", views.medical_reports, name="medical_reports"),

    # ---- Protein Shop ----
    path("protein-shop/batches/", views.protein_batch_list, name="protein_batch_list"),
    path("protein-shop/batches/add/", views.protein_batch_add, name="protein_batch_add"),
    path("protein-shop/batches/<int:batch_id>/sell/", views.protein_sell, name="protein_sell"),
    path("protein-shop/sales/", views.protein_sale_history, name="protein_sale_history"),
    path("protein-shop/reports/", views.protein_reports, name="protein_reports"),

    # ---- Construction ----
    path("construction/projects/", views.project_list, name="project_list"),
    path("construction/projects/add/", views.project_add, name="project_add"),
    path("construction/projects/<int:project_id>/edit/", views.project_edit, name="project_edit"),
    path("construction/projects/<int:project_id>/", views.project_detail, name="project_detail"),
    path("construction/projects/<int:project_id>/milestones/add/", views.project_milestone_add, name="project_milestone_add"),
    path("construction/projects/<int:project_id>/tasks/add/", views.project_task_add, name="project_task_add"),
    path("construction/projects/<int:project_id>/timesheets/add/", views.project_timesheet_add, name="project_timesheet_add"),
    path("construction/contractors/", views.contractor_list, name="contractor_list"),
    path("construction/contractors/add/", views.contractor_add, name="contractor_add"),
    path("construction/contractors/<int:contractor_id>/edit/", views.contractor_edit, name="contractor_edit"),
    path("construction/contractors/<int:contractor_id>/delete/", views.contractor_delete, name="contractor_delete"),
    path("construction/expenses/add/", views.project_expense_add, name="project_expense_add"),
    path("construction/reports/", views.construction_reports, name="construction_reports"),

    # ---- Generic Retail (Watch / Perfume / Book Store) ----
    path("retail/sales/", views.retail_sale_list, name="retail_sale_list"),
    path("retail/sales/add/", views.retail_sale_add, name="retail_sale_add"),
    path("retail/reports/", views.retail_reports, name="retail_reports"),

    # ---- Restaurant / Café / Catering ----
    path("restaurant/", views.restaurant_dashboard, name="restaurant_dashboard"),
    path("restaurant/areas/add/", views.restaurant_area_add, name="restaurant_area_add"),
    path("restaurant/tables/add/", views.restaurant_table_add, name="restaurant_table_add"),
    path("restaurant/tables/<int:table_id>/status/", views.restaurant_table_status, name="restaurant_table_status"),
    path("restaurant/setup/", views.restaurant_setup, name="restaurant_setup"),
    path("restaurant/setup/menu/add/", views.restaurant_menu_item_form, name="restaurant_menu_item_add"),
    path("restaurant/setup/demo-menu/", views.restaurant_demo_menu, name="restaurant_demo_menu"),
    path("restaurant/setup/menu/<int:menu_item_id>/edit/", views.restaurant_menu_item_form, name="restaurant_menu_item_edit"),
    path("restaurant/setup/menu/<int:menu_item_id>/toggle/", views.restaurant_menu_item_toggle, name="restaurant_menu_item_toggle"),
    path("restaurant/setup/modifiers/add/", views.restaurant_modifier_add, name="restaurant_modifier_add"),
    path("restaurant/setup/modifier-groups/add/", views.restaurant_modifier_group_add, name="restaurant_modifier_group_add"),
    path("restaurant/setup/modifier-options/add/", views.restaurant_modifier_option_add, name="restaurant_modifier_option_add"),
    path("restaurant/setup/stations/add/", views.restaurant_station_add, name="restaurant_station_add"),
    path("restaurant/setup/profile/", views.restaurant_profile_edit, name="restaurant_profile_edit"),
    path("restaurant/setup/recipes/add/", views.restaurant_recipe_add, name="restaurant_recipe_add"),
    path("restaurant/setup/combos/add/", views.restaurant_combo_add, name="restaurant_combo_add"),
    path("restaurant/setup/combo-items/add/", views.restaurant_combo_item_add, name="restaurant_combo_item_add"),
    path("restaurant/setup/integrations/add/", views.restaurant_integration_form, name="restaurant_integration_add"),
    path("restaurant/setup/integrations/<int:integration_id>/edit/", views.restaurant_integration_form, name="restaurant_integration_edit"),
    path("restaurant/integrations/webhook/<uuid:webhook_token>/", views.restaurant_delivery_webhook, name="restaurant_delivery_webhook"),
    path("restaurant/orders/add/", views.restaurant_order_add, name="restaurant_order_add"),
    path("restaurant/orders/<int:order_id>/", views.restaurant_order_detail, name="restaurant_order_detail"),
    path("restaurant/kitchen/", views.restaurant_kitchen, name="restaurant_kitchen"),
    path("restaurant/offline/", offline_views.offline_pos, name="restaurant_offline_pos"),
    path("restaurant/offline/bootstrap.json", offline_views.offline_bootstrap, name="restaurant_offline_bootstrap"),
    path("restaurant/offline/sync/", offline_views.offline_sync, name="restaurant_offline_sync"),
    path("restaurant/kitchen/<int:ticket_id>/<str:status>/", views.restaurant_kitchen_status, name="restaurant_kitchen_status"),
    path("restaurant/shifts/open/", views.restaurant_shift_open, name="restaurant_shift_open"),
    path("restaurant/shifts/<int:shift_id>/close/", views.restaurant_shift_close, name="restaurant_shift_close"),
    path("restaurant/reservations/", views.restaurant_reservations, name="restaurant_reservations"),
    path("restaurant/reservations/<int:reservation_id>/<str:status>/", views.restaurant_reservation_status, name="restaurant_reservation_status"),
    path("restaurant/waste/", views.restaurant_waste, name="restaurant_waste"),
    path("restaurant/reports/", views.restaurant_reports, name="restaurant_reports"),
    path("restaurant/orders/<int:order_id>/receipt/", views.restaurant_receipt_print, name="restaurant_receipt_print"),
    path("restaurant/kot/<int:ticket_id>/print/", views.restaurant_kot_print, name="restaurant_kot_print"),
    path("restaurant/public/<uuid:token>/", views.restaurant_public_menu, name="restaurant_public_menu"),
    path("restaurant/public/<uuid:token>/qr.png", views.restaurant_public_menu_qr, name="restaurant_public_menu_qr"),
    path("restaurant/public/<uuid:token>/order/", views.restaurant_public_order, name="restaurant_public_order"),
    path("restaurant/public/order-status/<uuid:order_token>/", views.restaurant_public_order_status, name="restaurant_public_order_status"),
    path("restaurant/orders/<int:order_id>/cancel/", views.restaurant_order_cancel, name="restaurant_order_cancel"),
    path("restaurant/shifts/<int:shift_id>/z-report/", views.restaurant_z_report, name="restaurant_z_report"),

    # ---- Invoice PDF (shared) ----
    path("invoices/<int:invoice_id>/pdf/", views.invoice_pdf, name="invoice_pdf"),
    path("invoices/<int:invoice_id>/share/", share_views.invoice_share, name="invoice_share"),
    path("i/<str:token>/", share_views.public_invoice, name="public_invoice"),
]
