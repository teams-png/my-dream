from rest_framework import serializers
from .models import Subscription, SubscriptionPlan


class SubscriptionPlanSerializer(serializers.ModelSerializer):
    class Meta:
        model = SubscriptionPlan
        fields = ["id", "name", "price", "billing_period", "max_users", "max_warehouses",
                  "max_invoices_per_month", "storage_limit_mb", "grace_period_days", "modules"]


class SubscriptionSerializer(serializers.ModelSerializer):
    plan = SubscriptionPlanSerializer(read_only=True)
    days_remaining = serializers.SerializerMethodField()

    class Meta:
        model = Subscription
        fields = ["id", "plan", "start_date", "end_date", "status", "auto_renew", "days_remaining",
                  "trial_ends_at", "grace_ends_at", "downgrade_effective_on"]

    def get_days_remaining(self, obj):
        return obj.days_remaining()
