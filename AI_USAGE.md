# AI_USAGE.md

## Tools
- **Anthropic Claude** (via **Claude Code**, model Opus 4.8) — primary
  development collaborator across the whole build: schema, detectors, tests,
  frontend, deployment, and these docs.
- No other AI tools were used. Every line was reviewed and run; I remain the
  engineer of record.

## How I directed it
I gave Claude the assignment PDF and the raw export and drove the build in
small, verifiable steps, each ending in a run or a test rather than a "looks
right." Representative prompts, roughly in order:

- *"Read the assignment and the export sheet. Enumerate every deliberate data
  problem and map each to the specific flatmate complaint it relates to."*
- *"Design a relational schema where group membership changes over time and
  every balance can be traced back to the exact rows that produced it."*
- *"Write one small, named detector per anomaly. Then run them against the
  unedited xlsx and show me the count per anomaly type."*
- *"Convert USD to INR using the rate on the expense's date, and persist the
  rate so the numbers are reproducible in a live session."*
- *"Stage the import; commit only after review; the committed net balances
  must sum to exactly zero."*
- *"Re-read the assignment's minimum product requirements against what's
  actually built and callable from the UI — not what the models support in
  theory. List every gap."*
- *"Audit every write endpoint: can a user read or write a group they don't
  belong to?"*
- *"Sweep the repo for dead files and stale docs left over from the deploy
  pivots. Cross-check every frontend API call against the real backend URLs."*

The habit that caught the most — both by me and, in one important case, by the
person I was building this for — was **running the app against the real file
and checking an invariant** (an anomaly count, a balance sum, a specific row's
resolved date) rather than eyeballing the code and declaring it correct.

## Concrete cases where the AI was wrong

### 1. Alias detection silently missed casing/whitespace
- **What it produced:** `is_alias_of_canonical` normalised *both* the raw name
  and the canonical name before comparing, so "priya" vs "Priya" and "rohan "
  (trailing space) vs "Rohan" compared **equal** and were never flagged.
- **How I caught it:** running the detectors on the real file, `NAME_ALIAS`
  fired only **once**, but a manual scan showed three messy spellings (rows 8,
  10, 26). The count mismatch exposed it.
- **What I changed:** compare the **raw** string to the canonical name (not the
  normalised form) — exactly the spelling inconsistency Rohan complained
  about. `NAME_ALIAS` now fires 3×.

### 2. Ambiguous-date detector had false positives
- **What it produced:** flagged a date as out-of-order if it was `< previous OR
  > next`, and used the year-corrected "Airport cab" row (2014 → 2026-03-01, a
  guess later found to be wrong — see case 6) as a comparison anchor. This
  wrongly flagged row 25 (Parasailing refund) and produced **4** ambiguous
  dates instead of 1.
- **How I caught it:** printed the description + date of every flagged row and
  saw obviously in-order rows being flagged, traced to the corrupted anchor.
- **What I changed:** flag only when a 2026 date is **greater than the next**
  valid date, and **skip year-corrected rows as anchors**. Now exactly one row
  (Deep cleaning, 05-04) is flagged — the real ambiguous case.

### 3. Settings crashed only in production — `NameError`
- **What it produced:** the `if not DEBUG:` hardening block did
  `CSRF_TRUSTED_ORIGINS.append(...)` before that list was defined later in the
  file. It passed `manage.py check` locally, because the append was guarded by
  `if _render_host:` and that variable is only set on Render.
- **How I caught it:** the **Render build log** showed
  `NameError: name 'CSRF_TRUSTED_ORIGINS' is not defined` on first deploy.
- **What I changed:** moved the block after the CORS/CSRF definitions, and
  re-verified locally by exporting `DEBUG=False` **and**
  `RENDER_EXTERNAL_HOSTNAME` to reproduce the exact production condition —
  local testing alone had a blind spot the real environment didn't.

### 4. CSV import commit returned a 502 in production
- **What it produced:** the commit endpoint worked locally but returned **502
  after ~31s** on Render. gunicorn's **default 30s worker timeout** killed the
  request: the commit made one DB round-trip per `ExpenseSplit` row plus live
  FX calls, against a possibly-distant Neon instance.
- **How I caught it:** drove the deployed `/commit` endpoint with the real file
  and measured `HTTP 502 in 31.7s`.
- **What I changed:** raised the gunicorn timeout to 120s **and** switched to
  `bulk_create` for splits (one query per expense instead of one per member),
  cutting roughly 110 queries. Commit then returned 200, with balances summing
  to ₹0.00 in prod.

### 5. Manual "add expense" silently produced no splits
- **What it produced:** early on, the only path that created balanced
  `ExpenseSplit` rows was the importer's commit step. A manually-added expense
  (the assignment's requirement #3 — "create and manage expenses") saved an
  `Expense` row with **zero splits**, so it wouldn't appear in anyone's
  balance at all — a silently broken feature, not a crash.
- **How I caught it:** not a bug report — re-reading the assignment's minimum
  product requirements against what was actually reachable from the running
  UI, rather than what the data model supported in theory. There was no test
  for it because the feature didn't fully exist yet.
- **What I changed:** built `create_expense()` as a thin wrapper around the
  *same* `compute_shares()` + dated-FX code the importer uses, so a manual
  expense and an imported one are computed identically and both keep balances
  summing to zero. Added a UI form with split-type-aware inputs and a
  membership-date check that disables members not active on the chosen date.

### 6. A date bug I did not catch myself — the user did
- **What it produced:** row 26 ("Airport cab") is stored in the sheet as
  `2014-03-01` — an impossible year, correctly flagged by `IMPOSSIBLE_DATE` —
  and my fix swapped the year to 2026, giving **2026-03-01**. That passed every
  automated check I had (it's a valid 2026 date, it didn't collide with
  anything, and the row's own ambiguous-date detector didn't fire on it). The
  user then compared the generated report line-by-line against the raw sheet
  and pointed out the date was wrong for that row specifically.
- **Root cause, on investigation:** that one cell uses a different Excel
  number format than every other date in the column — `mmm-yy` (month-year)
  instead of `mm-dd-yy`. A month-year cell never stores a real day; Excel
  defaults it to the 1st, and the "14" that looks like a two-digit year is
  actually the day the person typed, misread by the format. The row sits
  between Mar-12 and Mar-15 in the sheet, confirming the intended date is
  March 14.
- **What I changed:** the parser now reads each date cell's Excel
  `number_format` (not just its value) and, when that format has no day token,
  reconstructs the real date from the two-digit "year" instead of guessing a
  plain year-swap. Row 26 now resolves to **2026-03-14**. Added a test pinning
  this exact row, and re-verified none of the other 41 date cells share the
  odd format (they don't — this was a one-off).
- **Why this one matters most:** it's the clearest example in this project of
  the AI producing something that was *plausible, passed every check I wrote,
  and was still wrong* — because my checks encoded my own assumptions about
  what "fixed" looked like, not an independent read of the source data. That
  gap only closed when a human compared output against the original file.

### 7. No authorization check on group-scoped endpoints
- **What it produced:** `ExpenseViewSet`, `MemberViewSet`, and
  `SettlementViewSet` filtered lists by `?group=<id>` but never checked the
  requesting user actually belonged to that group — any authenticated user
  could read or write another group's expenses by guessing an id.
- **How I caught it:** a deliberate security sweep after the functional
  requirements were met — not a failing test, since no test existed for the
  negative case yet.
- **What I changed:** added an `accessible_groups(user)` helper and applied it
  to every relevant queryset and write path (including the importer's upload).
  Added a test asserting a second user gets `403` on someone else's group.

## Smaller catches
- The rule-based balance explanation first rendered "Rohan owes the group
  **₹-500.00**" — a negative sign after "owes." Caught in the explain smoke
  test; changed the template to use the **absolute** magnitude.
- A DRF drill-down action was named `member_ledger`, shadowing the imported
  `member_ledger()` service function it called. It worked (Python resolves the
  call to the module global), but was fragile; renamed to `ledger`.
- After the deploy platform changed twice (Koyeb and Hugging Face Docker
  Spaces both added card requirements after I'd already configured them;
  settled on Render + Neon + GitHub Pages), a `Dockerfile`, `.dockerignore`,
  and `vercel.json` were left behind from the abandoned attempts, and
  `DECISIONS.md` still documented "Render + Vercel" as the final choice —
  contradicting the actual live URL. Caught by the user asking "is this still
  needed?"; removed the dead files and rewrote the decision entry to describe
  what's actually deployed and why it changed.

## What this demonstrates
The AI was fast at producing plausible code, and wrong in ways that mostly
surfaced by **running it against the real data and checking an invariant**
(anomaly counts, balances summing to zero, a diff of the report against the
raw sheet) rather than reading the code and declaring it correct. Case 6 is
the important exception: it passed every invariant I thought to check, and
only a human comparing the output to the source caught it — a reminder that
self-testing is bounded by what the tester thought to test for.
