from django.contrib import admin
from .models import SubscriptionPlan, Subscription, SubscriptionPayment, SubscriptionRenewal

admin.site.register(SubscriptionPlan)
admin.site.register(Subscription)
admin.site.register(SubscriptionPayment)
admin.site.register(SubscriptionRenewal)
