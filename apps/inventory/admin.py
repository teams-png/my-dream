from django.contrib import admin
from .models import ProductCategory, Brand, Unit, Warehouse, Product, StockMovement

admin.site.register(ProductCategory)
admin.site.register(Brand)
admin.site.register(Unit)
admin.site.register(Warehouse)
admin.site.register(Product)
admin.site.register(StockMovement)
