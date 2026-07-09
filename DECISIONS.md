# DECISIONS.md — Decision Log

Each entry: the decision, the options considered, and why the chosen one won.

---

### 1. Backend framework — **Django + DRF**
- **Options:** Django REST Framework · FastAPI · Flask.
- **Chosen:** Django + DRF. The role is a Django/Python role and the assignment
  requires a relational DB; Django's ORM, migrations, auth, and admin remove a
  lot of undifferentiated work and give a free data browser for the live session.

### 2. Database — **Postgres in prod, SQLite in dev**
- **Options:** Postgres everywhere · SQLite everywhere · split.
- **Chosen:** split via `DATABASE_URL` (`dj-database-url`). Postgres satisfies
  "relational only" and matches production; SQLite keeps local setup and tests
  zero-config. Same ORM, so behaviour is identical.

### 3. **Member is separate from User**
- **Options:** one `User` model for everyone · separate `Member` for people in a
  group.
- **Chosen:** separate. People appear in the sheet (Meera, Dev, Kabir) who will
  never log in. A `Member` is the unit of splitting; a `User` is a login. This
  also lets one person own many messy spellings via `MemberAlias`.

### 4. Membership is **time-bounded windows**, not a boolean
- **Options:** an `is_active` flag · `joined_at`/`left_at` windows.
- **Chosen:** windows (`GroupMembership`). Sam's complaint ("why would March
  electricity affect me?") is fundamentally about *dates*. A split includes only
  members active on the expense's date — so the rule is structural, not a special
  case bolted on later.

### 5. Store the **original amount and the derived rupee amount**
- **Options:** overwrite the amount with INR at import · keep both.
- **Chosen:** keep both (`amount_original` + `currency`, plus `fx_rate` +
  `amount_inr`). Priya must be able to see that a dollar wasn't treated as a
  rupee. The original is never destroyed; the rupee value and the rate that
  produced it are auditable on every row.

### 6. Currency — **live dated FX, then persisted**
- **Options:** fixed hard-coded rate · live "current" rate · dated historical
  rate cached on the row.
- **Chosen:** fetch the **historical** USD→INR for each expense's date from
  Frankfurter (free, no key), then **store it** on the expense and in an
  `FxRate` cache. This is both "real" (the trip's actual rate) and reproducible
  (the demo and the live session never depend on a network call). A documented
  offline fallback keeps imports from crashing if the API is unreachable.

### 7. Import is a **staging pipeline**, not a direct load
- **Options:** parse-and-insert · parse → stage → review → commit.
- **Chosen:** staging. `analyze()` writes annotated `ImportRow`s; nothing touches
  the domain tables until a human commits. This directly satisfies Meera's
  "approve before anything changes", produces the import-report deliverable, and
  keeps every committed row traceable back to its raw source.

### 8. **One small named detector per anomaly**
- **Options:** a single big parser with inline checks · a list of tiny detectors.
- **Chosen:** tiny detectors (`detect_percentage_sum`, `detect_settlement`, …).
  The live session will point at a rule and ask "why does this happen?" — a
  10-line function answers that; a 300-line parser doesn't. It also makes each
  anomaly independently unit-testable against its real row.

### 9. Duplicate policy — **keep the first-logged row**
- **Options:** keep highest amount · keep lowest · keep first · keep last.
- **Chosen:** keep first. The sheet is chronological, so the first entry is the
  original and later ones are re-logs ("Aisha also logged this"). Conflicting
  duplicates (different amounts) are still surfaced so a human can override.

### 10. Settlement detection — **single counterparty + payment intent**
- **Options:** only rows with empty `split_type` · a keyword/shape heuristic.
- **Chosen:** a row is a settlement if it has exactly one counterparty (≠ payer)
  **and** either an empty `split_type` or payment words ("paid…back", "deposit").
  This catches both the Feb 25 payback (empty type) and the Apr 8 deposit
  (type says `equal` but it's really a payment to one person).

### 11. Percentages that don't sum to 100 — **treat as weights**
- **Options:** reject/block the row · rescale to 100% · treat percentages as
  weights.
- **Chosen:** weights. 30/30/30/20 (=110) distributes the *actual* expense amount
  proportionally, which equals normalising to 100%. The true total is always
  split exactly; nothing is blocked on a data-entry slip, but it's flagged.

### 12. Rounding — **half-up to 2 dp, remainder to the largest share**
- **Options:** truncate · banker's rounding · round each then fix the remainder.
- **Chosen:** round each share half-up to paise, then put the leftover paisa on
  the largest share so the parts always sum back to the total. Deterministic and
  easy to verify by hand.

### 13. Non-members — **add as guests**
- **Options:** drop them · error · add as a guest member.
- **Chosen:** add as a guest (`is_guest=True`) and flag. Kabir genuinely joined
  parasailing, so the split is only correct if he's included; marking him a guest
  keeps him out of the flat's ongoing roster.

### 14. "Who owes whom" — **greedy minimal transfers**
- **Options:** show the full pairwise matrix · minimise the number of transfers.
- **Chosen:** greedy match of biggest debtor to biggest creditor. This is Aisha's
  "one number per person", it's deterministic, and it's simple enough to walk by
  hand in the live session.

### 15. LLM feature — **narrate the computed ledger, with a fallback**
- **Options:** let the LLM compute balances · let it only phrase our numbers ·
  skip it.
- **Chosen:** the balance engine computes everything; the LLM only *explains*
  numbers we already proved, so it cannot invent a balance. With no API key it
  falls back to a deterministic template, so the feature never breaks the demo.

### 16. Deployment — **Render (API) + Neon (Postgres) + GitHub Pages (frontend)**
- **Options:** single host · Render-managed Postgres · Vercel/Koyeb/Hugging Face
  for the backend · GitHub Pages for the frontend.
- **Chosen:** split across three free, card-minimal services. Render's own
  managed Postgres and several container hosts (Koyeb, Hugging Face Docker
  Spaces) started requiring a card even on their $0 tiers, so Postgres moved to
  **Neon** (free, card-free) via `DATABASE_URL`, and the backend stayed on
  **Render**'s free web service (`plan: free` in `render.yaml`, card verified
  but never charged). The frontend was originally planned for Vercel but moved
  to **GitHub Pages** — free, no card, and it keeps the whole repo on one
  platform. Wired together with a Vite `base`/router `basename` for the Pages
  subpath, a repo-level `VITE_API_BASE` variable, and environment-based CORS on
  the API.

### 17. The roster is the *only* hardcoded domain knowledge — everything else generic
- **Options:** hardcode names, aliasing, and date logic together as one
  assignment-specific blob · isolate exactly what can't be derived from data
  and keep everything else generic.
- **Chosen:** isolation. `default_roster()` (six names, one genuine alias,
  Meera/Sam's windows) is deliberately hardcoded because those facts come from
  a sentence of English in the assignment PDF — no algorithm can derive "Sam
  moved in mid-April" from the spreadsheet. Everything else that looked
  hardcoded on inspection turned out to be a bug and was fixed instead of
  documented as a limitation: (a) casing/whitespace alias matching is generic
  for any name via `normalize()`, not a per-name lookup; (b) a payer or
  settlement counterparty the roster doesn't recognise is now created as a
  guest member instead of the row being silently skipped, matching how
  unrecognised participants were already handled; (c) `detect_impossible_date`
  infers the sheet's own dominant year from its data (`_infer_expected_year`)
  instead of assuming a literal year. `GenericSheetTests` proves all three
  against a synthetic sheet the roster was never seeded for — including a
  2027 dataset that self-corrects to 2027, not a hardcoded 2026.

### 18. Commit isolates each row in its own savepoint, never trusts detectors alone
- **Options:** trust the detectors to catch everything ahead of time and let
  `commit_batch` assume clean input · defend at commit time too, with each row
  isolated so one failure can't affect any other.
- **Chosen:** defend at commit time as well. A blank amount was reachable
  without tripping any detector (no `MISSING_AMOUNT` existed) and crashed
  `commit_batch` with an unhandled `decimal.InvalidOperation` — found by
  asking "what if a column goes missing on a different sheet?", not by a
  failing test, since none existed for that case. Fixing the immediate crash
  wasn't enough: the whole function had no per-row failure isolation at all,
  and `commit_batch` is `@transaction.atomic`, so *any* unexpected failure on
  *any* row — a malformed `unequal` split whose amounts don't sum to the
  total, for instance — would have rolled back every other row already
  committed in the same batch, silently discarding otherwise-successful work.
  Added `MISSING_AMOUNT`/`MISSING_DATE` detectors so the common cases are
  caught proactively and shown in the review UI (with fix-it inputs, same
  pattern as `MISSING_PAYER`) — but detectors can never cover every possible
  malformed input, so each row's commit now also runs inside its own
  `transaction.atomic()` savepoint inside the outer one. An unexpected
  exception rolls back only that row, gets recorded on it as
  `resolution.commit_error`, surfaces in the import report as
  `ROW_COMMIT_ERROR`, and every other row in the batch is unaffected.
  `RobustnessTests` proves this with a deliberately broken row sandwiched
  between two good ones. Belt (proactive detection) and suspenders (recovery
  that can't crash) rather than either alone.
