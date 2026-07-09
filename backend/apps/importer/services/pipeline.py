"""Staging + commit pipeline.

Flow: analyze() has already produced annotated rows. Here we
  * persist them into ImportBatch / ImportRow (staging),
  * expose an import report (the deliverable),
  * commit approved rows into real Members / Expenses / Splits / Settlements,
    applying each anomaly's policy and dated FX conversion.

Commit is the only place that writes domain data, and it only runs on a batch
the user has reviewed — this is Meera's "approve before anything changes".
"""

from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from apps.expenses.models import (
    Expense,
    ExpenseSplit,
    GroupMembership,
    Member,
    MemberAlias,
    Settlement,
)
from apps.expenses.services.splitting import compute_shares, round_money

from ..models import ImportBatch, ImportRow, ImportStatus, RowKind, RowStatus
from . import fx
from .roster import Roster, normalize


# --------------------------------------------------------------------------- #
# serialisation helpers (cleaned values -> JSON-safe)
# --------------------------------------------------------------------------- #
def _jsonify(value):
    if isinstance(value, Decimal):
        return str(value)
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if isinstance(value, dict):
        return {k: _jsonify(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_jsonify(v) for v in value]
    return value


def stage_batch(group, filename, uploaded_by, analyzed_rows) -> ImportBatch:
    batch = ImportBatch.objects.create(
        group=group, filename=filename, uploaded_by=uploaded_by
    )
    kind_map = {
        "expense": RowKind.EXPENSE,
        "settlement": RowKind.SETTLEMENT,
        "duplicate": RowKind.DUPLICATE,
        "invalid": RowKind.INVALID,
    }
    for ctx in analyzed_rows:
        ImportRow.objects.create(
            batch=batch,
            row_number=ctx["row_number"],
            raw=_jsonify(ctx["raw"]),
            cleaned=_jsonify(ctx["cleaned"]),
            kind=kind_map.get(ctx["kind"], RowKind.EXPENSE),
            status=(
                RowStatus.NEEDS_REVIEW
                if ctx["status"] == "needs_review"
                else RowStatus.CLEAN
            ),
            anomalies=[a.to_dict() for a in ctx["anomalies"]],
        )
    return batch


def build_report(batch: ImportBatch) -> dict:
    """The import report deliverable: every anomaly + the action taken."""
    rows = list(batch.rows.all())
    counts = {}
    findings = []
    for row in rows:
        for a in row.anomalies:
            counts[a["code"]] = counts.get(a["code"], 0) + 1
            findings.append(
                {
                    "row": row.row_number,
                    "description": row.raw.get("description"),
                    "code": a["code"],
                    "severity": a["severity"],
                    "message": a["message"],
                    "action": a["action"],
                }
            )
    return {
        "batch_id": batch.id,
        "filename": batch.filename,
        "status": batch.status,
        "total_rows": len(rows),
        "rows_with_anomalies": sum(1 for r in rows if r.anomalies),
        "anomaly_counts": counts,
        "distinct_anomaly_types": len(counts),
        "findings": findings,
    }


# --------------------------------------------------------------------------- #
# commit
# --------------------------------------------------------------------------- #
def _get_or_create_member(group, canonical_name, cache, is_guest=False):
    if canonical_name in cache:
        return cache[canonical_name]
    member, _ = Member.objects.get_or_create(
        group=group,
        name=canonical_name,
        defaults={"is_guest": is_guest},
    )
    cache[canonical_name] = member
    return member


def _record_alias(member, raw_name):
    if raw_name and raw_name != member.name:
        MemberAlias.objects.get_or_create(
            member=member,
            normalized=normalize(raw_name),
            defaults={"raw": raw_name},
        )


def _seed_membership_windows(group, roster: Roster, cache):
    for name, window in roster.windows.items():
        if name in cache:
            joined, left = window
            GroupMembership.objects.get_or_create(
                member=cache[name],
                joined_at=joined,
                left_at=left,
            )


@transaction.atomic
def commit_batch(batch: ImportBatch, roster: Roster) -> dict:
    if batch.status == ImportStatus.COMMITTED:
        return {"detail": "already committed", "batch_id": batch.id}

    group = batch.group
    cache: dict = {}
    created = {"expenses": 0, "settlements": 0, "skipped": 0, "members": set()}

    for row in batch.rows.all().order_by("row_number"):
        res = row.resolution or {}
        # Skip duplicates/invalids unless a human chose to keep them.
        if row.kind in (RowKind.DUPLICATE, RowKind.INVALID) and not res.get("keep"):
            row.status = RowStatus.SKIPPED
            row.save(update_fields=["status"])
            created["skipped"] += 1
            continue

        raw = row.raw
        cleaned = row.cleaned
        d = _date(res.get("date") or cleaned.get("date"))
        raw_payer = res.get("paid_by") or raw.get("paid_by")
        payer_name = roster.canonical(raw_payer)

        if payer_name is None:
            # Unresolved missing/unknown payer -> cannot commit this row.
            row.status = RowStatus.SKIPPED
            row.save(update_fields=["status"])
            created["skipped"] += 1
            continue

        payer = _get_or_create_member(group, payer_name, cache)
        _record_alias(payer, raw_payer)
        created["members"].add(payer_name)

        # Convert amount to INR using the dated rate.
        amount = Decimal(str(cleaned.get("amount")))
        currency = cleaned.get("currency") or "INR"
        rate, _src = fx.get_rate(d, currency, "INR")
        amount_inr = round_money(amount * rate)

        if row.kind == RowKind.SETTLEMENT:
            to_name = roster.canonical(cleaned.get("settlement_to") or "")
            if to_name is None:
                row.status = RowStatus.SKIPPED
                row.save(update_fields=["status"])
                created["skipped"] += 1
                continue
            to_member = _get_or_create_member(group, to_name, cache)
            created["members"].add(to_name)
            Settlement.objects.create(
                group=group,
                date=d,
                from_member=payer,
                to_member=to_member,
                amount_inr=amount_inr,
                note=raw.get("description") or "",
                source_import_row=row,
            )
            created["settlements"] += 1
            row.status = RowStatus.COMMITTED
            row.save(update_fields=["status"])
            continue

        # --- expense row ---
        participants, details_by_member = _resolve_participants(
            group, roster, cleaned, d, cache, created
        )
        if not participants:
            row.status = RowStatus.SKIPPED
            row.save(update_fields=["status"])
            created["skipped"] += 1
            continue

        expense = Expense.objects.create(
            group=group,
            date=d,
            description=cleaned.get("description") or raw.get("description") or "",
            paid_by=payer,
            amount_original=amount,
            currency=currency,
            fx_rate=rate,
            amount_inr=amount_inr,
            split_type=cleaned.get("split_type") or "equal",
            notes=raw.get("notes") or "",
            source_import_row=row,
        )

        shares = compute_shares(
            expense.split_type,
            amount_inr,
            participants,
            details_by_member or None,
        )
        # Bulk-insert splits (one query instead of one per member) to cut
        # round-trips to a possibly-distant Postgres during import.
        ExpenseSplit.objects.bulk_create(
            [
                ExpenseSplit(expense=expense, member=member, amount_inr=share)
                for member, share in shares.items()
            ]
        )
        created["expenses"] += 1
        row.status = RowStatus.COMMITTED
        row.save(update_fields=["status"])

    _seed_membership_windows(group, roster, cache)

    batch.status = ImportStatus.COMMITTED
    batch.committed_at = timezone.now()
    batch.save(update_fields=["status", "committed_at"])

    created["members"] = sorted(created["members"])
    return {"batch_id": batch.id, "committed": created}


def _resolve_participants(group, roster, cleaned, on_date, cache, created):
    """Map raw participants to Members, dropping those inactive on the date.

    Returns (members_list, details_by_member). Non-members become guests
    (default policy 'add as guest'); members outside their window are excluded
    (policy 'drop inactive members from split').
    """
    raw_participants = cleaned.get("participants_raw", [])
    raw_details = cleaned.get("details") or {}
    members = []
    details_by_member = {}
    for raw_name in raw_participants:
        canon = roster.canonical(raw_name)
        if canon is None:
            # guest
            guest = _get_or_create_member(group, raw_name.strip(), cache, is_guest=True)
            _record_alias(guest, raw_name)
            member = guest
        else:
            if not roster.active_on(canon, on_date):
                continue  # dropped: not in the flat on this date
            member = _get_or_create_member(group, canon, cache)
            _record_alias(member, raw_name)
            created["members"].add(canon)
        members.append(member)
        # match any detail entry for this raw name
        for dk, dv in raw_details.items():
            if normalize(dk) == normalize(raw_name):
                details_by_member[member] = Decimal(str(dv))
    return members, details_by_member


def _date(value):
    if hasattr(value, "isoformat"):
        return value
    import datetime as dt

    return dt.date.fromisoformat(str(value)[:10])
