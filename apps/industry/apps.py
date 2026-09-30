from django.apps import AppConfig


class IndustryConfig(AppConfig):
    """Industry modules switched on per business type (see apps.modules.catalog.INDUSTRY_FEATURES)."""
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.industry"
    label = "industry"
    verbose_name = "Industry modules"
