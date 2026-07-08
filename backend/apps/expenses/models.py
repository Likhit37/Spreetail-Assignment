"""Core relational schema for the shared-expenses domain.

Design notes (these map directly to the flatmates' complaints):

* Member != User. A Member is a person who appears in a group's expenses
  (Meera, Dev, even Dev's friend Kabir). A User is a login account. Keeping
  them separate lets us import people who will never log in, and lets one
  human own many messy spellings via MemberAlias (Rohan's complaint).

* GroupMembership carries joined_at / left_at. An expense is split only
  among members active on the expense's date, so March electricity never
  touches Sam and April rent never touches Meera (Sam's complaint), even if
  the raw sheet lists them.

* Expense keeps amount_original + currency AND fx_rate + amount_inr. We never
  overwrite the number the user typed; the rupee value is derived and
  auditable (Priya's complaint).

* ExpenseSplit is one row per member per expense with the exact computed
  share. Balances are just sums of these rows, so every number drills down to
  its source (Rohan's "no magic numbers").

* Settlement is its own table. A payment ("Rohan paid Aisha back") is not an
  expense and must not be split (Aisha's complaint).
"""

from decimal import Decimal

from django.conf import settings
from django.db import models


class Group(models.Model):
    name = models.CharField(max_length=120)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="groups_created",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return self.name


class Member(models.Model):
    """A person within a group. Canonical identity for one human."""

    group = models.ForeignKey(
        Group, on_delete=models.CASCADE, related_name="members"
    )
    name = models.CharField(max_length=120)  # canonical display name
    # Optional link to a login account (most members never have one).
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="memberships",
    )
    is_guest = models.BooleanField(
        default=False, help_text="Ad-hoc participant, e.g. a friend on a trip"
    )

    class Meta:
        unique_together = ("group", "name")

    def __str__(self) -> str:
        return f"{self.name} ({self.group.name})"

    def is_active_on(self, on_date) -> bool:
        """True if this member belonged to the group on `on_date`."""
        windows = self.membership_windows.all()
        if not windows:
            # No explicit window recorded -> treat as always-active.
            return True
        return any(w.covers(on_date) for w in windows)


class MemberAlias(models.Model):
    """A raw spelling seen in the import that maps to a canonical Member.

    e.g. "priya", "Priya S", "rohan " (trailing space) -> the real member.
    Normalised form is stored to make lookups deterministic.
    """

    member = models.ForeignKey(
        Member, on_delete=models.CASCADE, related_name="aliases"
    )
    raw = models.CharField(max_length=120)
    normalized = models.CharField(max_length=120, db_index=True)

    class Meta:
        unique_together = ("member", "normalized")

    @staticmethod
    def normalize(value: str) -> str:
        return " ".join((value or "").strip().lower().split())

    def __str__(self) -> str:
        return f"{self.raw} -> {self.member.name}"


class GroupMembership(models.Model):
    """Time-bounded membership window. left_at null == still a member."""

    member = models.ForeignKey(
        Member, on_delete=models.CASCADE, related_name="membership_windows"
    )
    joined_at = models.DateField(null=True, blank=True)
    left_at = models.DateField(null=True, blank=True)

    def covers(self, on_date) -> bool:
        if self.joined_at and on_date < self.joined_at:
            return False
        if self.left_at and on_date > self.left_at:
            return False
        return True

    def __str__(self) -> str:
        return f"{self.member.name}: {self.joined_at} .. {self.left_at}"


class SplitType(models.TextChoices):
    EQUAL = "equal", "Equal"
    UNEQUAL = "unequal", "Unequal (exact amounts)"
    PERCENTAGE = "percentage", "Percentage"
    SHARE = "share", "Share (ratio)"


class Expense(models.Model):
    group = models.ForeignKey(
        Group, on_delete=models.CASCADE, related_name="expenses"
    )
    date = models.DateField()
    description = models.CharField(max_length=255)
    paid_by = models.ForeignKey(
        Member,
        on_delete=models.PROTECT,
        related_name="expenses_paid",
        null=True,
        blank=True,
    )

    # Original as entered — never overwritten.
    amount_original = models.DecimalField(max_digits=12, decimal_places=4)
    currency = models.CharField(max_length=3, default="INR")
    # Derived rupee value + the rate used to get there (auditable).
    fx_rate = models.DecimalField(
        max_digits=12, decimal_places=6, default=Decimal("1")
    )
    amount_inr = models.DecimalField(max_digits=12, decimal_places=2)

    split_type = models.CharField(
        max_length=16, choices=SplitType.choices, default=SplitType.EQUAL
    )
    notes = models.TextField(blank=True, default="")

    # Provenance: which import row produced this, for traceability.
    source_import_row = models.ForeignKey(
        "importer.ImportRow",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_expenses",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["date", "id"]

    def __str__(self) -> str:
        return f"{self.date} {self.description} ({self.amount_inr} INR)"


class ExpenseSplit(models.Model):
    """One member's share of one expense. Balances = sums of these."""

    expense = models.ForeignKey(
        Expense, on_delete=models.CASCADE, related_name="splits"
    )
    member = models.ForeignKey(
        Member, on_delete=models.PROTECT, related_name="splits"
    )
    # The raw share input (percent, ratio, or exact amount) kept for audit.
    share_value = models.DecimalField(
        max_digits=12, decimal_places=4, null=True, blank=True
    )
    # Final rupee amount this member owes for this expense.
    amount_inr = models.DecimalField(max_digits=12, decimal_places=2)

    class Meta:
        unique_together = ("expense", "member")

    def __str__(self) -> str:
        return f"{self.member.name} owes {self.amount_inr} for {self.expense_id}"


class Settlement(models.Model):
    """A payment from one member to another. Not an expense; never split."""

    group = models.ForeignKey(
        Group, on_delete=models.CASCADE, related_name="settlements"
    )
    date = models.DateField()
    from_member = models.ForeignKey(
        Member, on_delete=models.PROTECT, related_name="settlements_paid"
    )
    to_member = models.ForeignKey(
        Member, on_delete=models.PROTECT, related_name="settlements_received"
    )
    amount_inr = models.DecimalField(max_digits=12, decimal_places=2)
    note = models.CharField(max_length=255, blank=True, default="")
    source_import_row = models.ForeignKey(
        "importer.ImportRow",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_settlements",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["date", "id"]

    def __str__(self) -> str:
        return (
            f"{self.from_member.name} -> {self.to_member.name}: "
            f"{self.amount_inr} INR"
        )
