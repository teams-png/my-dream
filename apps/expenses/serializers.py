from rest_framework import serializers
from .models import ExpenseCategory, Expense


class ExpenseCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = ExpenseCategory
        fields = ["id", "name"]


class ExpenseSerializer(serializers.ModelSerializer):
    class Meta:
        model = Expense
        fields = ["id", "category", "date", "amount", "description", "payment_method"]
        read_only_fields = ["id"]
