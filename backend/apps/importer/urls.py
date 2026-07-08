from django.urls import path

from .views import (
    BatchDetailView,
    RowResolutionView,
    UploadView,
    batch_report,
    commit_view,
)

urlpatterns = [
    path("upload/", UploadView.as_view(), name="import-upload"),
    path("batches/<int:batch_id>/", BatchDetailView.as_view(), name="import-batch"),
    path("batches/<int:batch_id>/report/", batch_report, name="import-report"),
    path("batches/<int:batch_id>/commit/", commit_view, name="import-commit"),
    path("rows/<int:row_id>/", RowResolutionView.as_view(), name="import-row"),
]
