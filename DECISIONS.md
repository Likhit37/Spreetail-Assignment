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

### 16. Deployment — **Render (API + Postgres) + Vercel (frontend)**
- **Options:** single host · split.
- **Chosen:** split. Render gives managed Postgres + Python web service via a
  committed `render.yaml`; Vercel is the natural home for a Vite build. Wired
  together with environment-based CORS and API base URL.
