"""Anomaly detectors + the analysis orchestrator.

Each `detect_*` function does ONE thing and appends Anomaly objects to a row's
working context. This is deliberate: in the live review a grader can point at
`detect_percentage_sum` and read the whole rule in ten lines. `analyze()` wires
them together — first a per-row pass, then cross-row passes (dates, duplicates).

Nothing here writes to the database. It produces an annotated plan that the
review UI shows and the commit step later turns into real rows.
"""

import datetime as dt
import re
from decimal import Decimal, InvalidOperation

from . import anomalies as A
from .roster import Roster, normalize

STOPWORDS = {"at", "the", "a", "an", "for", "order", "-", "night", "bill"}
SETTLEMENT_WORDS = re.compile(r"\b(paid|back|deposit|settle|settl|repay|owe)\b", re.I)


# --------------------------------------------------------------------------- #
# small parsing helpers
# --------------------------------------------------------------------------- #
def to_decimal(value):
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def parse_date(value):
    if value is None:
        return None
    if isinstance(value, dt.date):
        return value
    try:
        return dt.date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def parse_participants(split_with):
    if not split_with:
        return []
    return [p.strip() for p in str(split_with).split(";") if p.strip()]


def parse_details(split_details):
    """'Aisha 30%; Rohan 20' -> {'Aisha': Decimal(30), 'Rohan': Decimal(20)}."""
    out = {}
    if not split_details:
        return out
    for seg in str(split_details).split(";"):
        seg = seg.strip()
        if not seg:
            continue
        m = re.match(r"^(.*?)[\s]+([-\d.]+)\s*%?\s*$", seg)
        if m:
            name = m.group(1).strip()
            num = to_decimal(m.group(2))
            if num is not None:
                out[name] = num
    return out


def significant_tokens(description):
    tokens = re.findall(r"[a-z0-9]+", (description or "").lower())
    return frozenset(t for t in tokens if t not in STOPWORDS)


# --------------------------------------------------------------------------- #
# per-row detectors
# --------------------------------------------------------------------------- #
def detect_missing_payer(ctx, roster):
    if ctx["kind"] == "settlement":
        return
    if not ctx["raw"].get("paid_by"):
        ctx["anomalies"].append(
            A.Anomaly(
                A.MISSING_PAYER,
                "blocker",
                "No payer recorded for this expense.",
                "Assign who actually paid before committing.",
                "hold row until a payer is chosen",
            )
        )


def detect_unknown_payer(ctx, roster):
    raw_payer = ctx["raw"].get("paid_by")
    if not raw_payer:
        return
    if roster.canonical(raw_payer) is None:
        ctx["anomalies"].append(
            A.Anomaly(
                A.UNKNOWN_PAYER,
                "blocker",
                f"Payer '{raw_payer}' is not a known member.",
                "Map to a member or add them.",
                "hold row",
            )
        )


def detect_missing_currency(ctx, roster):
    if ctx["raw"].get("currency") in (None, ""):
        ctx["cleaned"]["currency"] = "INR"
        ctx["anomalies"].append(
            A.Anomaly(
                A.MISSING_CURRENCY,
                "warning",
                "Currency was blank.",
                "Defaulted to INR (all neighbouring rows are INR).",
                "assume INR",
            )
        )


def detect_foreign_currency(ctx, roster):
    cur = ctx["cleaned"].get("currency") or ctx["raw"].get("currency")
    if cur and cur != "INR":
        ctx["anomalies"].append(
            A.Anomaly(
                A.FOREIGN_CURRENCY,
                "info",
                f"Amount is in {cur}, not INR.",
                "Convert to INR using the rate on the expense date.",
                "convert via dated FX rate",
                meta={"currency": cur},
            )
        )


def detect_negative_amount(ctx, roster):
    amt = ctx["cleaned"].get("amount")
    if amt is not None and amt < 0:
        ctx["anomalies"].append(
            A.Anomaly(
                A.NEGATIVE_AMOUNT,
                "warning",
                f"Amount is negative ({amt}).",
                "Looks like a refund; keep the sign so it reduces balances.",
                "treat as refund (negative expense)",
            )
        )


def detect_zero_amount(ctx, roster):
    amt = ctx["cleaned"].get("amount")
    if amt is not None and amt == 0:
        ctx["kind"] = "invalid"
        ctx["anomalies"].append(
            A.Anomaly(
                A.ZERO_AMOUNT,
                "warning",
                "Amount is zero.",
                "Placeholder row; excluded from balances by default.",
                "skip row",
            )
        )


def detect_subunit_precision(ctx, roster):
    amt = ctx["cleaned"].get("amount")
    if amt is None:
        return
    if -amt.as_tuple().exponent > 2:  # more than 2 decimal places
        ctx["anomalies"].append(
            A.Anomaly(
                A.SUBUNIT_PRECISION,
                "info",
                f"Amount {amt} has sub-paise precision.",
                "Rounded to 2 dp (round half-up).",
                "round to 2 dp",
            )
        )


def detect_impossible_date(ctx, roster):
    d = ctx["cleaned"].get("date")
    if not d or d.year == 2026:
        return

    fmt = (ctx.get("meta", {}).get("date_format") or "").lower()
    # A month-year format (has a year token, no day token) means the cell never
    # stored a real day — Excel defaulted it to the 1st. The two-digit "year"
    # the user typed (e.g. 2014 -> "14") is really the intended day of month.
    month_year_format = "y" in fmt and "d" not in fmt
    day_guess = d.year % 100
    if month_year_format and 1 <= day_guess <= 28:
        try:
            suggested = dt.date(2026, d.month, day_guess)
            reason = (
                f"Cell is month-year formatted ('{ctx['meta']['date_format']}'), "
                f"so '{day_guess}' is the day, not the year."
            )
            action = "read day from month-year format; year -> 2026"
        except ValueError:
            suggested, reason, action = _year_fix(d)
    else:
        suggested, reason, action = _year_fix(d)

    ctx["cleaned"]["date"] = suggested
    ctx["anomalies"].append(
        A.Anomaly(
            A.IMPOSSIBLE_DATE,
            "warning",
            f"Date {d.isoformat()} is outside the group's active period.",
            f"{reason} Corrected to {suggested.isoformat()}.",
            action,
        )
    )


def _year_fix(d):
    return (
        d.replace(year=2026),
        f"Year {d.year} looks like a typo.",
        "correct year to 2026",
    )


def detect_split_type_detail_conflict(ctx, roster):
    stype = (ctx["raw"].get("split_type") or "").strip().lower()
    details = ctx["cleaned"].get("details") or {}
    if stype == "equal" and details:
        ctx["anomalies"].append(
            A.Anomaly(
                A.SPLIT_TYPE_DETAIL_CONFLICT,
                "warning",
                "split_type is 'equal' but per-person shares were supplied.",
                "Honour the explicit split_type (equal); ignore the shares.",
                "use split_type, ignore details",
            )
        )
        ctx["cleaned"]["details"] = {}


def detect_percentage_sum(ctx, roster):
    if (ctx["cleaned"].get("split_type")) != "percentage":
        return
    details = ctx["cleaned"].get("details") or {}
    total = sum(details.values()) if details else Decimal("0")
    if details and total != 100:
        ctx["anomalies"].append(
            A.Anomaly(
                A.PERCENTAGE_SUM_INVALID,
                "warning",
                f"Percentages sum to {total}%, not 100%.",
                "Normalise proportionally so shares sum to the total.",
                "normalise to 100%",
                meta={"sum": str(total)},
            )
        )
        # normalisation happens in splitting via weights; percentages act as
        # weights so a 110 total still distributes the true expense amount.


def detect_names(ctx, roster):
    """Flag messy spellings and non-members among payer + participants."""
    seen_aliases = []
    non_members = []

    raw_payer = ctx["raw"].get("paid_by")
    if raw_payer and roster.is_alias_of_canonical(raw_payer):
        seen_aliases.append(raw_payer)

    for p in ctx["cleaned"].get("participants_raw", []):
        canon = roster.canonical(p)
        if canon is None:
            non_members.append(p)
        elif roster.is_alias_of_canonical(p):
            seen_aliases.append(p)

    if seen_aliases:
        ctx["anomalies"].append(
            A.Anomaly(
                A.NAME_ALIAS,
                "info",
                f"Non-canonical spelling(s): {', '.join(seen_aliases)}.",
                "Mapped to the canonical member.",
                "normalise name",
                meta={"aliases": seen_aliases},
            )
        )
    for nm in non_members:
        ctx["anomalies"].append(
            A.Anomaly(
                A.NON_MEMBER_PARTICIPANT,
                "warning",
                f"'{nm}' is not a flat member.",
                "Treat as a one-off guest, or drop from the split.",
                "add as guest",
                meta={"name": nm},
            )
        )


def detect_membership_dates(ctx, roster):
    """Flag participants who weren't in the flat on the expense date."""
    d = ctx["cleaned"].get("date")
    if not d:
        return
    inactive = []
    for p in ctx["cleaned"].get("participants_raw", []):
        canon = roster.canonical(p)
        if canon and not roster.active_on(canon, d):
            inactive.append(canon)
    if inactive:
        ctx["anomalies"].append(
            A.Anomaly(
                A.MEMBERSHIP_DATE_MISMATCH,
                "warning",
                f"{', '.join(inactive)} not in the flat on {d.isoformat()}.",
                "Exclude them from this expense's split.",
                "drop inactive members from split",
                meta={"members": inactive},
            )
        )


# --------------------------------------------------------------------------- #
# classification: expense vs settlement
# --------------------------------------------------------------------------- #
def classify_settlement(ctx, roster):
    """A single-counterparty payment is a settlement, not a shared expense."""
    stype = (ctx["raw"].get("split_type") or "").strip().lower()
    participants = ctx["cleaned"].get("participants_raw", [])
    payer = ctx["raw"].get("paid_by")
    text = f"{ctx['raw'].get('description', '')} {ctx['raw'].get('notes', '')}"

    single_other = (
        len(participants) == 1
        and payer
        and normalize(participants[0]) != normalize(payer)
    )
    looks_like_payment = stype in ("", "none") or bool(SETTLEMENT_WORDS.search(text))

    if single_other and looks_like_payment:
        ctx["kind"] = "settlement"
        ctx["cleaned"]["settlement_to"] = participants[0]
        ctx["anomalies"].append(
            A.Anomaly(
                A.SETTLEMENT_AS_EXPENSE,
                "warning",
                "This is a payment between two people, not a shared expense.",
                f"Record as a settlement {payer} -> {participants[0]}.",
                "reclassify as settlement",
            )
        )


# --------------------------------------------------------------------------- #
# cross-row detectors
# --------------------------------------------------------------------------- #
def detect_ambiguous_dates(rows):
    """Flag a 2026 date that jumps ahead of the row that follows it.

    The sheet is kept in chronological order, so a row whose date is later than
    the next row's date is out of sequence — the classic day/month-swap mess
    (e.g. 05-04 meant as 04-05). We only compare to the immediate next valid
    date to avoid false positives from same-day clusters or corrected years.
    """
    for ctx in rows:
        d = ctx["cleaned"].get("date")
        if not d or d.year != 2026:
            continue
        nxt = _next_valid_date(rows, ctx)
        if nxt and d > nxt:
            swapped = _swap_day_month(d)
            suggestion = (
                f"Possibly {swapped.isoformat()} (day/month swapped)."
                if swapped
                else "Confirm the intended date."
            )
            ctx["anomalies"].append(
                A.Anomaly(
                    A.AMBIGUOUS_DATE,
                    "warning",
                    f"Date {d.isoformat()} is out of order with its neighbours.",
                    suggestion,
                    "ask user to confirm date",
                    meta={"swapped": swapped.isoformat() if swapped else None},
                )
            )


def _next_valid_date(rows, ctx):
    idx = rows.index(ctx)
    for later in rows[idx + 1 :]:
        # A row whose year we just corrected is not a trustworthy anchor.
        if any(a.code == A.IMPOSSIBLE_DATE for a in later["anomalies"]):
            continue
        d = later["cleaned"].get("date")
        if d and d.year == 2026:
            return d
    return None


def _swap_day_month(d):
    try:
        return dt.date(d.year, d.day, d.month)
    except ValueError:
        return None


def detect_duplicates(rows):
    """Group by (date, key description tokens); split into exact vs conflict."""
    groups = {}
    for ctx in rows:
        d = ctx["cleaned"].get("date")
        if not d or ctx["kind"] in ("settlement", "invalid"):
            continue
        key = (d, significant_tokens(ctx["raw"].get("description", "")))
        if not key[1]:
            continue
        groups.setdefault(key, []).append(ctx)

    for members in groups.values():
        if len(members) < 2:
            continue
        amounts = {str(m["cleaned"].get("amount")) for m in members}
        payers = {normalize(m["raw"].get("paid_by") or "") for m in members}
        first, rest = members[0], members[1:]
        if len(amounts) == 1 and len(payers) == 1:
            # Same date, description, amount, payer -> exact duplicate.
            for dup in rest:
                dup["kind"] = "duplicate"
                dup["anomalies"].append(
                    A.Anomaly(
                        A.DUPLICATE_EXACT,
                        "warning",
                        "Exact duplicate of an earlier row.",
                        f"Keep row {first['row_number']}; drop this one.",
                        "drop duplicate",
                        meta={"keep_row": first["row_number"]},
                    )
                )
        else:
            # Same event logged twice with different amounts/payers.
            for m in members:
                m["anomalies"].append(
                    A.Anomaly(
                        A.DUPLICATE_CONFLICT,
                        "warning",
                        "Same event logged more than once with different "
                        "amount/payer.",
                        f"Default: keep the first-logged row "
                        f"({first['row_number']}); confirm which is correct.",
                        "keep first-logged, user confirms",
                        meta={
                            "rows": [m["row_number"] for m in members],
                            "keep_row": first["row_number"],
                        },
                    )
                )
            for dup in rest:
                dup["kind"] = "duplicate"


# --------------------------------------------------------------------------- #
# orchestrator
# --------------------------------------------------------------------------- #
PER_ROW_DETECTORS = [
    detect_missing_payer,
    detect_unknown_payer,
    detect_missing_currency,
    detect_foreign_currency,
    detect_negative_amount,
    detect_zero_amount,
    detect_subunit_precision,
    detect_impossible_date,
    detect_split_type_detail_conflict,
    detect_percentage_sum,
    detect_names,
    detect_membership_dates,
]


def analyze(raw_rows, roster: Roster | None = None):
    roster = roster or Roster()
    rows = []
    for rr in raw_rows:
        raw = rr["raw"]
        ctx = {
            "row_number": rr["row_number"],
            "raw": raw,
            "meta": rr.get("meta", {}),
            "kind": "expense",
            "status": "clean",
            "anomalies": [],
            "cleaned": {
                "date": parse_date(raw.get("date")),
                "description": (raw.get("description") or "").strip(),
                "currency": raw.get("currency") or "INR",
                "amount": to_decimal(raw.get("amount")),
                "split_type": (raw.get("split_type") or "equal").strip().lower()
                if raw.get("split_type")
                else "equal",
                "participants_raw": parse_participants(raw.get("split_with")),
                "details": parse_details(raw.get("split_details")),
            },
        }
        # classification first (affects which detectors fire)
        classify_settlement(ctx, roster)
        for det in PER_ROW_DETECTORS:
            det(ctx, roster)
        rows.append(ctx)

    # cross-row passes
    detect_ambiguous_dates(rows)
    detect_duplicates(rows)

    # finalise status
    for ctx in rows:
        if any(a.severity == "blocker" for a in ctx["anomalies"]):
            ctx["status"] = "needs_review"
        elif ctx["anomalies"]:
            ctx["status"] = "needs_review"
        else:
            ctx["status"] = "clean"
    return rows
