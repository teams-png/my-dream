from rest_framework import serializers
from .models import Project, Contractor, ProjectAssignment, ProjectExpense


class ProjectSerializer(serializers.ModelSerializer):
    class Meta:
        model = Project
        fields = [
            "id", "name", "client", "site_address", "start_date", "end_date",
            "budget", "contract_value", "status",
        ]
        read_only_fields = ["id"]


class ContractorSerializer(serializers.ModelSerializer):
    class Meta:
        model = Contractor
        fields = ["id", "name", "phone", "specialty", "is_active"]
        read_only_fields = ["id"]


class ProjectAssignmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProjectAssignment
        fields = ["id", "project", "employee", "role_on_site", "daily_wage", "start_date", "end_date"]
        read_only_fields = ["id"]


class ProjectExpenseSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProjectExpense
        fields = [
            "id", "project", "category", "contractor", "amount",
            "date", "description", "payment_method",
        ]
        read_only_fields = ["id"]
