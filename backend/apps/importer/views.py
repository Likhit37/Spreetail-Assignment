from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.expenses.models import Group

from .models import ImportBatch, ImportRow
from .serializers import ImportBatchSerializer, ImportRowSerializer
from .services.detectors import analyze
from .services.parsing import parse_upload
from .services.pipeline import build_report, commit_batch, stage_batch
from .services.roster import default_roster


class UploadView(APIView):
    """Ingest the file, run detection, stage it, and return the review set.

    Nothing is committed here — the response is the anomaly review the user
    approves before any real rows are written.
    """

    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        group_id = request.data.get("group")
        upload = request.FILES.get("file")
        if not group_id or not upload:
            return Response(
                {"detail": "group and file are required"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        group = get_object_or_404(Group, id=group_id)
        roster = default_roster()
        raw_rows = parse_upload(upload, upload.name)
        analyzed = analyze(raw_rows, roster)
        batch = stage_batch(group, upload.name, request.user, analyzed)
        return Response(
            {
                "batch": ImportBatchSerializer(batch).data,
                "report": build_report(batch),
            },
            status=status.HTTP_201_CREATED,
        )


class BatchDetailView(APIView):
    def get(self, request, batch_id):
        batch = get_object_or_404(ImportBatch, id=batch_id)
        return Response(
            {
                "batch": ImportBatchSerializer(batch).data,
                "report": build_report(batch),
            }
        )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def batch_report(request, batch_id):
    batch = get_object_or_404(ImportBatch, id=batch_id)
    return Response(build_report(batch))


class RowResolutionView(APIView):
    """Capture a human decision on one row before commit (Meera's approval)."""

    def patch(self, request, row_id):
        row = get_object_or_404(ImportRow, id=row_id)
        serializer = ImportRowSerializer(row, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def commit_view(request, batch_id):
    batch = get_object_or_404(ImportBatch, id=batch_id)
    result = commit_batch(batch, default_roster())
    return Response({"result": result, "report": build_report(batch)})
