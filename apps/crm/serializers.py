from rest_framework import serializers
from .models import PipelineStage, Lead, Opportunity, Activity


class CompanySerializer(serializers.ModelSerializer):
    def create(self, validated_data):
        validated_data["company"] = self.context["request"].company
        return super().create(validated_data)


class PipelineStageSerializer(CompanySerializer):
    class Meta:
        model = PipelineStage
        exclude = ("company",)


class LeadSerializer(CompanySerializer):
    class Meta:
        model = Lead
        exclude = ("company", "created_by")
        read_only_fields = ("status", "converted_customer", "created_at", "updated_at")

    def create(self, validated_data):
        validated_data["created_by"] = self.context["request"].user
        return super().create(validated_data)


class OpportunitySerializer(CompanySerializer):
    class Meta:
        model = Opportunity
        exclude = ("company",)
        read_only_fields = ("created_at", "updated_at")


class ActivitySerializer(CompanySerializer):
    class Meta:
        model = Activity
        exclude = ("company", "created_by")
        read_only_fields = ("created_at",)

    def create(self, validated_data):
        validated_data["created_by"] = self.context["request"].user
        instance = super().create(validated_data)
        instance.full_clean()
        return instance
