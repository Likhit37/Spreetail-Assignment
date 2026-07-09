"""Create an expense manually (from the app UI, not the importer).

This is the counterpart to the importer's commit for a single, hand-entered
expense. It reuses the exact same tested pieces — dated FX conversion and
`compute_shares` — so a manually added expense produces identical, balanced
splits to an imported one. Balances stay a pure sum of ExpenseSplit rows.
"""

from decimal import Decimal

from django.db import transaction

from ..models import Expense, ExpenseSplit, Member
from .splitting import compute_shares, round_money


class ExpenseInputError(ValueError):
    """Raised for invalid manual-expense input (surfaced as HTTP 400)."""


@transaction.atomic
def create_expense(
    *,
    group,
    date,
    description,
    paid_by_id,
    amount_original,
    currency,
    split_type,
    participant_ids=None,
    details_by_id=None,
):
    amount_original = Decimal(str(amount_original))
    currency = (currency or "INR").upper()
    details_by_id = {int(k): Decimal(str(v)) for k, v in (details_by_id or {}).items()}

    payer = _member(group, paid_by_id, "payer")

    # For weighted/exact types the participants ARE the detail keys.
    if split_type in ("unequal", "percentage", "share"):
        if not details_by_id:
            raise ExpenseInputError(f"{split_type} split requires per-person values")
        member_ids = list(details_by_id.keys())
    else:  # equal
        member_ids = list(participant_ids or [])
        if not member_ids:
            raise ExpenseInputError("select at least one participant")

    members = [_member(group, mid, "participant") for mid in member_ids]
    for m in members:
        if not m.is_active_on(date):
            raise ExpenseInputError(
                f"{m.name} was not a member on {date} — they can't be in this split"
            )

    # Convert to INR on the expense date (imported here to avoid a circular
    # import at module load; importer depends on expenses).
    from apps.importer.services import fx

    rate, _source = fx.get_rate(date, currency, "INR")
    amount_inr = round_money(amount_original * rate)

    details_by_member = {
        m: details_by_id[m.id] for m in members if m.id in details_by_id
    }
    try:
        shares = compute_shares(split_type, amount_inr, members, details_by_member)
    except ValueError as exc:
        raise ExpenseInputError(str(exc)) from exc

    expense = Expense.objects.create(
        group=group,
        date=date,
        description=description,
        paid_by=payer,
        amount_original=amount_original,
        currency=currency,
        fx_rate=rate,
        amount_inr=amount_inr,
        split_type=split_type,
    )
    ExpenseSplit.objects.bulk_create(
        [ExpenseSplit(expense=expense, member=m, amount_inr=s) for m, s in shares.items()]
    )
    return expense


def _member(group, member_id, role):
    try:
        return Member.objects.get(group=group, id=member_id)
    except Member.DoesNotExist as exc:
        raise ExpenseInputError(f"{role} is not a member of this group") from exc
