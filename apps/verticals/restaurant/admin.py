from django.contrib import admin
from .models import DiningArea, DiningTable, FoodWaste, KitchenStation, MenuModifier, MenuModifierGroup, MenuModifierOption, RestaurantMenuItem, RestaurantProfile, RecipeIngredient, RestaurantCombo, RestaurantComboItem, RestaurantShift, RestaurantOrder, RestaurantOrderLine, RestaurantOrderLineModifier, TableReservation, KitchenTicket, RestaurantPaymentSplit, DeliveryIntegration, DeliveryOrderImport

for model in (DiningArea, DiningTable, FoodWaste, KitchenStation, MenuModifier, MenuModifierGroup, MenuModifierOption, RestaurantMenuItem, RestaurantProfile, RecipeIngredient, RestaurantCombo, RestaurantComboItem, RestaurantShift, RestaurantOrder, RestaurantOrderLine, RestaurantOrderLineModifier, TableReservation, KitchenTicket, RestaurantPaymentSplit, DeliveryIntegration, DeliveryOrderImport):
    admin.site.register(model)
