"""Staging tables for the CSV/XLSX import.

The importer never writes straight into Expense. It writes a snapshot of the
raw file plus every anomaly it detected into these staging tables, surfaces
them to the user for review/approval, and only then commits real rows. This
is what gives us:
  * the Import Report deliverable (every anomaly + action taken),
  * Meera's approval workflow (nothing changes without a human OK),
  * full traceability in the live session (each Expense points back to its
    ImportRow, which holds the original messy values).
"""

from django.conf import settings
from django.db import models


class ImportStatus(models.TextChoices):
    PENDING = "pending", "Pending review"
    COMMITTED = "committed", "Committed"
    CANCELLED = "cancelled", "Cancelled"


class RowStatus(models.TextChoices):
    CLEAN = "clean", "Clean"
    NEEDS_REVIEW = "needs_review", "Needs review"
    APPROVED = "approved", "Approved"
    SKIPPED = "skipped", "Skipped"
    COMMITTED = "committed", "Committed"


class RowKind(models.TextChoices):
    """What a row resolves to after detection."""

    EXPENSE = "expense", "Expense"
    SETTLEMENT = "settlement", "Settlement"
    DUPLICATE = "duplicate", "Duplicate (drop)"
    INVALID = "invalid", "Invalid (drop)"


class ImportBatch(models.Model):
    group = models.ForeignKey(
        "expenses.Group", on_delete=models.CASCADE, related_name="import_batches"
    )
    filename = models.CharField(max_length=255)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    status = models.CharField(
        max_length=16, choices=ImportStatus.choices, default=ImportStatus.PENDING
    )
    created_at = models.DateTimeField(auto_now_add=True)
    committed_at = models.DateTimeField(null=True, blank=True)

    def __str__(self) -> str:
        return f"Import {self.id} of {self.filename} ({self.status})"


class ImportRow(models.Model):
    batch = models.ForeignKey(
        ImportBatch, on_delete=models.CASCADE, related_name="rows"
    )
    row_number = models.IntegerField()  # 1-based data row in the sheet

    # Verbatim snapshot of the original cells (nothing edited).
    raw = models.JSONField()

    # Parsed / cleaned values the app intends to use (filled by detectors).
    cleaned = models.JSONField(default=dict, blank=True)

    kind = models.CharField(
        max_length=16, choices=RowKind.choices, default=RowKind.EXPENSE
    )
    status = models.CharField(
        max_length=16, choices=RowStatus.choices, default=RowStatus.CLEAN
    )

    # Detected anomalies: list of {code, severity, message, suggestion, action}.
    anomalies = models.JSONField(default=list, blank=True)

    # Human decisions captured during review (overrides applied on commit).
    resolution = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["batch_id", "row_number"]
        unique_together = ("batch", "row_number")

    def __str__(self) -> str:
        return f"Row {self.row_number} [{self.kind}/{self.status}]"

    @property
    def has_blocking(self) -> bool:
        return any(a.get("severity") == "blocker" for a in self.anomalies)
