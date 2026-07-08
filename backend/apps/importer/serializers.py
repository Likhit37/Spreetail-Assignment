from rest_framework import serializers

from .models import ImportBatch, ImportRow


class ImportRowSerializer(serializers.ModelSerializer):
    class Meta:
        model = ImportRow
        fields = (
            "id",
            "row_number",
            "raw",
            "cleaned",
            "kind",
            "status",
            "anomalies",
            "resolution",
        )
        read_only_fields = (
            "row_number",
            "raw",
            "cleaned",
            "kind",
            "status",
            "anomalies",
        )


class ImportBatchSerializer(serializers.ModelSerializer):
    rows = ImportRowSerializer(many=True, read_only=True)

    class Meta:
        model = ImportBatch
        fields = (
            "id",
            "group",
            "filename",
            "status",
            "created_at",
            "committed_at",
            "rows",
        )
