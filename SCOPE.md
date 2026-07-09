# SCOPE.md — Anomaly Log & Database Schema

## Part 1 — Anomaly log

The importer ran against the unedited `expenses_export assigbment annex.xlsx`
(sheet `in`, 42 data rows). It detected **16 distinct anomaly types across 21
rows** (the assignment promises at least 12). Each anomaly is produced by one
small named detector in `backend/apps/importer/services/detectors.py`, so any
finding can be traced to its rule. The importer actually knows **20** anomaly
codes; the 4 that don't appear below the table are defensive — they exist for
data this specific file happens not to contain (an unrecognised payer, a
blank amount/date, a row that fails at commit for a reason no detector
anticipated) rather than for show. Severity drives behaviour:

- **blocker** — the row cannot commit until a human resolves it
- **warning** — committed with the documented default, but surfaced
- **info** — handled automatically, shown for transparency

| # | Code | Severity | Example row(s) | Policy / action taken |
|---|------|----------|----------------|-----------------------|
| 1 | `DUPLICATE_EXACT` | warning | Row 5 "dinner - marina bites" duplicates row 4 (same date/amount/payer, Dev 3200) | Keep the first row, drop the duplicate. |
| 2 | `DUPLICATE_CONFLICT` | warning | Rows 23 & 24 Thalassa dinner: Aisha 2400 vs Rohan 2450 | Keep the first-logged row; both surfaced so a human can pick the winner. |
| 3 | `SETTLEMENT_AS_EXPENSE` | warning | Row 13 "Rohan paid Aisha back" 5000; Row 37 "Sam deposit share" | Reclassify as a Settlement (payment), not a split expense. |
| 4 | `FOREIGN_CURRENCY` | info | Rows 19/20/22/25 in USD (villa 540, beach 84, parasailing 150, refund −30) | Convert to INR using the **dated** FX rate; store the rate on the expense. |
| 5 | `NEGATIVE_AMOUNT` | warning | Row 25 Parasailing refund −30 USD | Treat as a refund (keep the sign) so it reduces balances. |
| 6 | `MISSING_CURRENCY` | warning | Row 27 Groceries DMart 2105, currency blank | Default to INR (every neighbouring row is INR). |
| 7 | `MISSING_PAYER` | **blocker** | Row 12 House cleaning supplies, payer blank | Hold the row; a human must assign the payer before commit. |
| 8 | `NAME_ALIAS` | info | Row 8 "priya", Row 10 "Priya S", Row 26 "rohan " (trailing space) | Normalise to the canonical member; record the alias. |
| 9 | `IMPOSSIBLE_DATE` | warning | Row 26 Airport cab stored as 2014-03-01 with a `mmm-yy` cell format ("Mar-14") | The cell is month-year formatted, so it never stored a real day — the two-digit "year" (14) is the intended **day**. Resolves to **2026-03-14** (in sequence between Mar-12 and Mar-15). The target year isn't hardcoded: it's inferred as the mode of every parsed date in the batch (2026 for this file), so other impossible years correct to that inferred year, and a sheet from a different year would self-correct to its own year instead. |
| 10 | `AMBIGUOUS_DATE` | warning | Row 33 Deep cleaning 2026-05-04 (out of order; note admits the format is a mess) | Surface it; suggest the day/month swap (Apr 5); ask the user to confirm. |
| 11 | `ZERO_AMOUNT` | warning | Row 30 Swiggy 0 ("counted twice earlier") | Exclude from balances by default. |
| 12 | `PERCENTAGE_SUM_INVALID` | warning | Row 14 Pizza + Row 31 brunch: 30/30/30/20 = 110% | Treat the percentages as weights so the true expense amount is still distributed (normalised to 100%). |
| 13 | `SUBUNIT_PRECISION` | info | Row 9 Cylinder refill 899.995 | Round to 2 dp (round half-up). |
| 14 | `SPLIT_TYPE_DETAIL_CONFLICT` | warning | Row 41 Furniture: `split_type=equal` but per-person shares supplied | Honour the explicit `split_type` (equal); ignore the stray shares. |
| 15 | `MEMBERSHIP_DATE_MISMATCH` | warning | Row 35 April 2 groceries still lists Meera, who left end-March | Drop members who weren't in the flat on the expense date from the split. |
| 16 | `NON_MEMBER_PARTICIPANT` | warning | Row 22 Parasailing includes "Dev's friend Kabir" | Treat as a one-off guest (or drop); surfaced for confirmation. |
| — | `UNKNOWN_PAYER` | blocker | (defensive; no row triggers it in this file — see below) | An unrecognised payer/settlement-recipient is created as a real (guest) member, the same policy as `NON_MEMBER_PARTICIPANT`, rather than the row being dropped. |
| — | `MISSING_AMOUNT` | **blocker** | (defensive; no row triggers it in this file) | Hold the row until an amount is supplied via row resolution. |
| — | `MISSING_DATE` | **blocker** | (defensive; no row triggers it in this file) | Hold the row until a date is supplied via row resolution. |
| — | `ROW_COMMIT_ERROR` | **blocker** | (defensive; no row triggers it in this file) | Any row that fails unexpectedly at commit time (e.g. an `unequal` split whose amounts don't sum to the total) is skipped and its error recorded here — never a crash, and never at the cost of any other row in the same batch. |

### How the policies affect the commit
Committing the whole file produces **36 expenses, 2 settlements, and 4 skipped
rows** (the exact duplicate, one conflicting-duplicate row, the zero-amount row,
and the payer-less row). After commit, **net balances sum to exactly ₹0.00** — the
invariant that proves no money was invented or lost.

The four defensive codes above don't fire on this specific file — every payer
is known, every row has an amount and a date, and no split is malformed — but
they exist because the importer isn't only built to survive *this* file.
Committing runs each row in its own transaction savepoint: a row that fails
for a reason no detector anticipated is skipped and recorded, but the rows
around it still commit. `RobustnessTests` proves this with a deliberately
broken row sitting between two good ones — the two good rows commit and the
broken one shows up as a `ROW_COMMIT_ERROR` finding in the import report,
matching the assignment's own line: "A crashed import and a silent guess are
both failing answers."

The full machine-readable report is in [`import_report.json`](import_report.json)
and is also produced live by the app on every import (Import wizard → after
commit, and `GET /api/import/batches/{id}/report/`).

### Deliberate policy choices worth calling out
- **Duplicates default to "keep first-logged."** The sheet is chronological;
  the first entry is the original, later ones are re-logs. The UI still lets a
  human override.
- **A single-counterparty payment is a settlement**, detected by either an empty
  `split_type` or payment words ("paid…back", "deposit"). This catches both the
  Feb 25 payback and the Apr 8 deposit.
- **Membership is date-bounded, not a flag.** Meera (Feb 1–Mar 31) and Sam
  (from Apr 8) have windows; a split only includes members active on the
  expense's date. This is why March electricity never touches Sam.
- **Guests are real, non-member participants.** Kabir is added as a guest member
  (`is_guest=True`) so the parasailing split is correct, but he's flagged.

## Part 2 — Database schema

All tables are relational (PostgreSQL in prod, SQLite in dev). Models live in
`backend/apps/expenses/models.py` and `backend/apps/importer/models.py`.

### Domain tables (`expenses` app)
- **User** (`accounts.User`) — login account (custom, extends `AbstractUser`).
- **Group** — a flat/household. `created_by → User`.
- **Member** — a person within a group (`group → Group`, optional `user → User`,
  `is_guest`). Separate from User: most members never log in. Unique per
  (group, name).
- **MemberAlias** — a raw spelling seen in the import mapped to a canonical
  Member (`member`, `raw`, `normalized`). Resolves "priya"/"Priya S"/"rohan ".
- **GroupMembership** — a time-bounded window (`member`, `joined_at`, `left_at`).
  `left_at = null` means still a member. Drives the date-aware splitting.
- **Expense** — `group`, `date`, `description`, `paid_by → Member`,
  `amount_original` + `currency` (as entered), `fx_rate` + `amount_inr`
  (derived, auditable), `split_type`, `notes`, `source_import_row` (provenance).
- **ExpenseSplit** — one member's share of one expense (`expense`, `member`,
  `share_value` raw input, `amount_inr` final). Balances are sums of these rows.
- **Settlement** — a payment `from_member → to_member` (`group`, `date`,
  `amount_inr`, `note`, `source_import_row`). Never split.

### Import / staging tables (`importer` app)
- **ImportBatch** — one upload (`group`, `filename`, `uploaded_by`, `status`,
  timestamps).
- **ImportRow** — one staged row: `raw` (verbatim snapshot), `cleaned` (parsed
  values), `kind` (expense/settlement/duplicate/invalid), `status`, `anomalies`
  (JSON list), `resolution` (human overrides — also where an unexpected
  commit-time failure is recorded, under `resolution.commit_error`, so it's
  never lost even though the row itself was skipped). Every committed
  Expense/Settlement points back here.
- **FxRate** — cached rate for a (date, base, quote) pair with `source`
  (frankfurter/fallback), so imports are reproducible and demos don't depend on
  a live call.

### Key relationships
```
User 1─* Member *─1 Group 1─* Expense 1─* ExpenseSplit *─1 Member
                     Group 1─* Settlement (from_member, to_member → Member)
Member 1─* GroupMembership          Member 1─* MemberAlias
Group 1─* ImportBatch 1─* ImportRow ─(provenance)→ Expense / Settlement
```
