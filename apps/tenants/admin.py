from django.contrib import admin
from .models import Company, Role, Permission, RolePermission, CompanyMembership, CompanyCounter


@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    list_display = ("name", "business_type", "is_active", "created_at")
    list_filter = ("is_active", "business_type")
    search_fields = ("name", "slug")


@admin.register(Role)
class RoleAdmin(admin.ModelAdmin):
    list_display = ("name", "company", "is_system_role")
    list_filter = ("is_system_role",)


admin.site.register(Permission)
admin.site.register(RolePermission)
admin.site.register(CompanyMembership)
admin.site.register(CompanyCounter)
