"""
One-time / idempotent seed command for Phase 2: creates a couple of
BusinessTypes + Modules + the standard subscription plans so registration
(tenants.services.create_company_with_owner) has something to attach to.

Run with: python manage.py seed_platform
"""
from django.core.management.base import BaseCommand
from django.db import transaction

from apps.modules.models import BusinessType, Module, BusinessTypeDefaultModule
from apps.tenants.services import ensure_default_permissions
from apps.modules.catalog import BUSINESS_TYPE_MAP, RETAIL_TYPES, SERVICE_TYPES, PROJECT_TYPES, RESTAURANT_TYPES


class Command(BaseCommand):
    help = "Seed core BusinessTypes, Modules, and the standard subscription plans."

    @transaction.atomic
    def handle(self, *args, **options):
        ensure_default_permissions()

        core_modules = ["accounting", "customers", "suppliers", "inventory", "sales", "purchases", "expenses"]
        vertical_modules = ["gym", "textile", "spa", "construction", "mobile_shop", "vehicle_wash", "sports_shop", "cycle_shop", "saloon", "beauty_parlour", "medical_shop", "protein_shop", "restaurant", "retail_suite", "service_suite", "project_suite"]

        module_objs = {}
        for code in core_modules:
            m, _ = Module.objects.get_or_create(code=code, defaults={"name": code.title(), "is_core": True})
            module_objs[code] = m
        for code in vertical_modules:
            m, _ = Module.objects.get_or_create(code=code, defaults={"name": code.title(), "is_core": False})
            module_objs[code] = m

        general, _ = BusinessType.objects.get_or_create(code="general_retail", defaults={"name": "General Retail"})
        boutique_type, _ = BusinessType.objects.get_or_create(
            code="ladies_fashion_boutique", defaults={"name": "Ladies Fashion / Boutique"}
        )
        gym_type, _ = BusinessType.objects.get_or_create(code="gym", defaults={"name": "Gym"})
        textile_type, _ = BusinessType.objects.get_or_create(code="textile", defaults={"name": "Textile Shop"})
        spa_type, _ = BusinessType.objects.get_or_create(code="spa", defaults={"name": "Spa / Massage Centre"})
        construction_type, _ = BusinessType.objects.get_or_create(code="construction", defaults={"name": "Construction Company"})
        mobile_shop_type, _ = BusinessType.objects.get_or_create(code="mobile_shop", defaults={"name": "Mobile Shop"})
        vehicle_wash_type, _ = BusinessType.objects.get_or_create(code="vehicle_wash", defaults={"name": "Vehicle Wash"})
        sports_shop_type, _ = BusinessType.objects.get_or_create(code="sports_shop", defaults={"name": "Sports Shop"})
        cycle_shop_type, _ = BusinessType.objects.get_or_create(code="cycle_shop", defaults={"name": "Cycle Shop"})
        saloon_type, _ = BusinessType.objects.get_or_create(code="saloon", defaults={"name": "Saloon"})
        beauty_parlour_type, _ = BusinessType.objects.get_or_create(code="beauty_parlour", defaults={"name": "Beauty Parlour"})
        medical_shop_type, _ = BusinessType.objects.get_or_create(code="medical_shop", defaults={"name": "Medical Shop / Pharmacy"})
        protein_shop_type, _ = BusinessType.objects.get_or_create(code="protein_shop", defaults={"name": "Protein Powder / Supplement Shop"})

        for code in core_modules:
            BusinessTypeDefaultModule.objects.get_or_create(business_type=general, module=module_objs[code])
            BusinessTypeDefaultModule.objects.get_or_create(business_type=boutique_type, module=module_objs[code])
            BusinessTypeDefaultModule.objects.get_or_create(business_type=gym_type, module=module_objs[code])
            BusinessTypeDefaultModule.objects.get_or_create(business_type=textile_type, module=module_objs[code])
            BusinessTypeDefaultModule.objects.get_or_create(business_type=spa_type, module=module_objs[code])
            BusinessTypeDefaultModule.objects.get_or_create(business_type=construction_type, module=module_objs[code])
            BusinessTypeDefaultModule.objects.get_or_create(business_type=mobile_shop_type, module=module_objs[code])
            BusinessTypeDefaultModule.objects.get_or_create(business_type=vehicle_wash_type, module=module_objs[code])
            BusinessTypeDefaultModule.objects.get_or_create(business_type=sports_shop_type, module=module_objs[code])
            BusinessTypeDefaultModule.objects.get_or_create(business_type=cycle_shop_type, module=module_objs[code])
            BusinessTypeDefaultModule.objects.get_or_create(business_type=saloon_type, module=module_objs[code])
            BusinessTypeDefaultModule.objects.get_or_create(business_type=beauty_parlour_type, module=module_objs[code])
            BusinessTypeDefaultModule.objects.get_or_create(business_type=medical_shop_type, module=module_objs[code])
            BusinessTypeDefaultModule.objects.get_or_create(business_type=protein_shop_type, module=module_objs[code])
        BusinessTypeDefaultModule.objects.get_or_create(business_type=gym_type, module=module_objs["gym"])
        BusinessTypeDefaultModule.objects.get_or_create(business_type=textile_type, module=module_objs["textile"])
        BusinessTypeDefaultModule.objects.get_or_create(business_type=spa_type, module=module_objs["spa"])
        BusinessTypeDefaultModule.objects.get_or_create(business_type=construction_type, module=module_objs["construction"])
        BusinessTypeDefaultModule.objects.get_or_create(business_type=mobile_shop_type, module=module_objs["mobile_shop"])
        BusinessTypeDefaultModule.objects.get_or_create(business_type=vehicle_wash_type, module=module_objs["vehicle_wash"])
        BusinessTypeDefaultModule.objects.get_or_create(business_type=sports_shop_type, module=module_objs["sports_shop"])
        BusinessTypeDefaultModule.objects.get_or_create(business_type=cycle_shop_type, module=module_objs["cycle_shop"])
        BusinessTypeDefaultModule.objects.get_or_create(business_type=saloon_type, module=module_objs["saloon"])
        BusinessTypeDefaultModule.objects.get_or_create(business_type=beauty_parlour_type, module=module_objs["beauty_parlour"])
        BusinessTypeDefaultModule.objects.get_or_create(business_type=medical_shop_type, module=module_objs["medical_shop"])
        BusinessTypeDefaultModule.objects.get_or_create(business_type=protein_shop_type, module=module_objs["protein_shop"])

        # Keep every registration option provisioned. Previously most choices were
        # created only when the first client registered, leaving them without a
        # default suite/module mapping.
        for code, name in BUSINESS_TYPE_MAP.items():
            business_type, _ = BusinessType.objects.get_or_create(code=code, defaults={"name": name})
            for core_code in core_modules:
                BusinessTypeDefaultModule.objects.get_or_create(
                    business_type=business_type, module=module_objs[core_code]
                )
            if code in RETAIL_TYPES:
                suite_code = "retail_suite"
            elif code in SERVICE_TYPES:
                suite_code = "service_suite"
            elif code in PROJECT_TYPES:
                suite_code = "project_suite"
            else:
                suite_code = code if code in module_objs else None
            if suite_code:
                BusinessTypeDefaultModule.objects.get_or_create(
                    business_type=business_type, module=module_objs[suite_code]
                )
            if code in RESTAURANT_TYPES:
                BusinessTypeDefaultModule.objects.get_or_create(
                    business_type=business_type, module=module_objs["restaurant"]
                )

        # 1 / 3 / 5-user yearly plans: INR for India, QAR everywhere else.
        from apps.subscriptions.pricing import ensure_default_plans
        ensure_default_plans(modules=list(module_objs.values()))

        self.stdout.write(self.style.SUCCESS("Platform seed data created."))
