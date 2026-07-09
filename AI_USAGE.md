# AI_USAGE.md

## Tools
- **Anthropic Claude** (via **Claude Code**, model Opus 4.8) — primary
  development collaborator: scaffolding, detectors, tests, frontend, and docs.
- No other AI tools were used. Every line was reviewed and run; I remain the
  engineer of record.

## How I directed it
I gave Claude the assignment PDF and the raw export and drove the build in small,
verifiable steps, each ending in a run or a test rather than a "looks right".
Representative prompts:

- *"Read the assignment and the export sheet. Enumerate every deliberate data
  problem and map each to the specific flatmate complaint it relates to."*
- *"Design a relational schema where group membership changes over time and every
  balance can be traced back to the exact rows that produced it."*
- *"Write one small, named detector per anomaly. Then run them against the
  unedited xlsx and show me the count per anomaly type."*
- *"Convert USD to INR using the rate on the expense's date, and persist the rate
  so the numbers are reproducible in a live session."*
- *"Stage the import; commit only after review; the committed net balances must
  sum to exactly zero."*

The "run it against the real file and show counts" habit is what caught most of
the mistakes below.

## Three concrete cases where the AI was wrong

### 1. Alias detection silently missed casing/whitespace
- **What it produced:** the first `is_alias_of_canonical` normalised *both* the
  raw name and the canonical name before comparing, so "priya" vs "Priya" and
  "rohan " (trailing space) vs "Rohan" compared **equal** and were not flagged.
- **How I caught it:** running the detectors on the real file, `NAME_ALIAS` fired
  only **once**, but a manual scan showed three messy spellings (rows 8, 10, 26).
  The count mismatch exposed it.
- **What I changed:** compare the **raw** string to the canonical name (not the
  normalised form), so casing/whitespace messes are surfaced — which is exactly
  the inconsistency Rohan complained about. `NAME_ALIAS` now fires 3×.

### 2. Ambiguous-date detector had false positives
- **What it produced:** the detector flagged a date as out-of-order if it was
  `< previous OR > next`, and it used the year-corrected "Airport cab" row (2014 →
  2026-03-01) as a comparison anchor. This wrongly flagged row 25 (Parasailing
  refund) and produced **4** ambiguous dates instead of 1.
- **How I caught it:** I printed the description + date of every flagged row and
  saw rows that were obviously in order being flagged, with the corrupted anchor
  as the cause.
- **What I changed:** flag only when a 2026 date is **greater than the next**
  valid date, and **skip year-corrected rows as anchors**. Now exactly one row
  (Deep cleaning, 05-04) is flagged — the real ambiguous case.

### 3. A view method shadowed the function it called
- **What it produced:** the DRF drill-down action was named `member_ledger`, the
  same name as the imported `member_ledger()` service it calls. It happened to
  work (Python resolves the call to the module global, not the class attribute),
  but it's fragile and misleading.
- **How I caught it:** reading the viewset back before running it — the duplicate
  name jumped out.
- **What I changed:** renamed the action to `ledger` so the endpoint method and
  the service function are clearly distinct.

## Bonus: a smaller catch
The rule-based balance explanation first rendered "Rohan owes the group
**₹-500.00**" — a negative sign after the word "owes". Caught in the explain
smoke test; changed the template to use the **absolute** magnitude.

## Two more caught during deployment (real environment, not local)

### 4. Settings crashed only in production — `NameError`
- **What it produced:** the `if not DEBUG:` hardening block did
  `CSRF_TRUSTED_ORIGINS.append(...)`, but that list was defined *later* in the
  file. The block also guarded the append behind `if _render_host:`.
- **How I caught it:** it passed `manage.py check` locally (no
  `RENDER_EXTERNAL_HOSTNAME`, so the append never ran) but the **Render build log**
  showed `NameError: name 'CSRF_TRUSTED_ORIGINS' is not defined`.
- **What I changed:** moved the block to after the CORS/CSRF definitions, and
  re-verified locally by exporting `DEBUG=False` **and** `RENDER_EXTERNAL_HOSTNAME`
  to reproduce the exact production condition.

### 5. CSV import returned a 502 in production
- **What it produced:** the commit endpoint worked locally but returned **502
  after ~31s** on Render. gunicorn's **default 30s worker timeout** killed the
  request: the commit makes many sequential round-trips to a (distant) Neon
  Postgres plus live FX calls.
- **How I caught it:** driving the deployed `/commit` endpoint with the real file
  and seeing `HTTP 502 in 31.7s`.
- **What I changed:** raised the gunicorn timeout to 120s **and** `bulk_create`d
  the expense splits (one query per expense instead of one per member), cutting
  ~110 queries. Commit then returned 200 and balances summed to ₹0.00 in prod.

## What this demonstrates
The AI was fast at producing plausible code, and wrong in ways that only surfaced
by **running it against the real data and checking invariants** (anomaly counts,
balances summing to zero, reading the code back). That verification loop — not
the generation — is where the engineering happened.
