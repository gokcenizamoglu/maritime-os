from checklists.models import ChecklistItem
from rest_framework import serializers


class ChecklistItemSerializer(serializers.ModelSerializer):
    document_type_name = serializers.CharField(source="document_type.name", read_only=True)
    mapped_document_count = serializers.SerializerMethodField()

    class Meta:
        model = ChecklistItem
        fields = [
            "id", "document_type", "document_type_name", "required_count",
            "is_complete", "mapped_document_count",
        ]

    def get_mapped_document_count(self, obj):
        """
        REVIEW FIX (#7): this previously counted ALL classified/validated
        documents linked to the item, INCLUDING ones that had since been
        superseded by a corrected upload — so the UI could show e.g.
        "2/1 mapped" for an item where one of those two was a stale,
        replaced version. Now mirrors the exact same qualifying-count
        logic used by checklists.services.recompute_checklist_item(), so
        the number shown here can never disagree with is_complete.
        """
        return obj.documents.filter(
            status__in=["classified", "validated"],
            superseded_by_set__isnull=True,
        ).count()
