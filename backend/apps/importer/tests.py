"""Detector tests run against the real, unedited export file.

Each test pins one anomaly to the specific row that triggers it, so if a
detector regresses we know exactly which flatmate complaint broke.
"""

import datetime as dt
from decimal import Decimal
from pathlib import Path

from django.test import SimpleTestCase, TestCase

from apps.expenses.models import Expense, Group
from apps.expenses.services.balances import net_balances

from .models import FxRate
from .services import anomalies as A
from .services.detectors import analyze
from .services.parsing import parse_upload
from .services.pipeline import build_report, commit_batch, stage_batch
from .services.roster import default_roster

XLSX = Path(__file__).resolve().parents[3] / "expenses_export assigbment annex.xlsx"


def _analyze():
    with open(XLSX, "rb") as f:
        return analyze(parse_upload(f, "expenses.xlsx"), default_roster())


def _codes_by_row(rows):
    out = {}
    for r in rows:
        for a in r["anomalies"]:
            out.setdefault(r["row_number"], set()).add(a.code)
    return out


class DetectorCoverageTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.rows = _analyze()
        cls.by_row = _codes_by_row(cls.rows)

    def all_codes(self):
        codes = set()
        for s in self.by_row.values():
            codes |= s
        return codes

    def test_file_parses_to_42_rows(self):
        self.assertEqual(len(self.rows), 42)

    def test_every_expected_anomaly_type_is_detected(self):
        expected = {
            A.DUPLICATE_EXACT,
            A.DUPLICATE_CONFLICT,
            A.SETTLEMENT_AS_EXPENSE,
            A.FOREIGN_CURRENCY,
            A.NEGATIVE_AMOUNT,
            A.MISSING_CURRENCY,
            A.MISSING_PAYER,
            A.NAME_ALIAS,
            A.IMPOSSIBLE_DATE,
            A.AMBIGUOUS_DATE,
            A.ZERO_AMOUNT,
            A.PERCENTAGE_SUM_INVALID,
            A.SUBUNIT_PRECISION,
            A.SPLIT_TYPE_DETAIL_CONFLICT,
            A.MEMBERSHIP_DATE_MISMATCH,
            A.NON_MEMBER_PARTICIPANT,
        }
        missing = expected - self.all_codes()
        self.assertEqual(missing, set(), f"undetected anomalies: {missing}")

    def test_at_least_12_problems_found(self):
        # The assignment promises "at least 12 deliberate data problems".
        total = sum(len(s) for s in self.by_row.values())
        self.assertGreaterEqual(total, 12)

    # --- specific rows, keyed to the story ---
    def test_marina_dinner_is_exact_duplicate(self):
        # Row 5 duplicates row 4 (same date/amount/payer, Dev 3200).
        self.assertIn(A.DUPLICATE_EXACT, self.by_row.get(5, set()))

    def test_thalassa_is_conflicting_duplicate(self):
        # Rows 23 & 24: Aisha 2400 vs Rohan 2450 for the same dinner.
        self.assertIn(A.DUPLICATE_CONFLICT, self.by_row.get(23, set()))
        self.assertIn(A.DUPLICATE_CONFLICT, self.by_row.get(24, set()))

    def test_rohan_payback_is_settlement(self):
        self.assertIn(A.SETTLEMENT_AS_EXPENSE, self.by_row.get(13, set()))

    def test_airport_cab_impossible_year(self):
        self.assertIn(A.IMPOSSIBLE_DATE, self.by_row.get(26, set()))

    def test_airport_cab_reconstructs_day_from_month_year_format(self):
        # Row 26 is stored as 2014-03-01 with a mmm-yy format ("Mar-14"); the
        # "14" is the intended day, so it must resolve to 2026-03-14.
        row = next(r for r in self.rows if r["row_number"] == 26)
        self.assertEqual(row["cleaned"]["date"].isoformat(), "2026-03-14")

    def test_deep_cleaning_ambiguous_date(self):
        self.assertIn(A.AMBIGUOUS_DATE, self.by_row.get(33, set()))

    def test_pizza_percentages_over_100(self):
        self.assertIn(A.PERCENTAGE_SUM_INVALID, self.by_row.get(14, set()))

    def test_meera_not_in_flat_in_april(self):
        # Row 35: April 2 groceries still list Meera.
        self.assertIn(A.MEMBERSHIP_DATE_MISMATCH, self.by_row.get(35, set()))

    def test_kabir_is_non_member(self):
        self.assertIn(A.NON_MEMBER_PARTICIPANT, self.by_row.get(22, set()))


class ImportCommitTests(TestCase):
    """Stage + commit the whole real file and check the invariants."""

    def setUp(self):
        # Seed FX for the trip's USD dates so the test never hits the network.
        for day in (9, 10, 11, 12):
            FxRate.objects.create(
                on_date=dt.date(2026, 3, day),
                base="USD",
                quote="INR",
                rate=Decimal("85"),
                source="test",
            )
        self.group = Group.objects.create(name="Flat 4B")
        self.roster = default_roster()
        with open(XLSX, "rb") as f:
            rows = analyze(parse_upload(f, "expenses.xlsx"), self.roster)
        self.batch = stage_batch(self.group, "expenses.xlsx", None, rows)

    def test_report_lists_all_anomaly_types(self):
        report = build_report(self.batch)
        self.assertEqual(report["total_rows"], 42)
        self.assertGreaterEqual(report["distinct_anomaly_types"], 12)

    def test_commit_produces_expected_row_counts(self):
        result = commit_batch(self.batch, self.roster)["committed"]
        # 36 expenses, 2 settlements, 4 skipped (1 exact dup, 1 conflict dup,
        # 1 zero-amount, 1 payer-less row).
        self.assertEqual(result["expenses"], 36)
        self.assertEqual(result["settlements"], 2)
        self.assertEqual(result["skipped"], 4)

    def test_balances_sum_to_zero(self):
        commit_batch(self.batch, self.roster)
        total = sum(net_balances(self.group).values())
        self.assertEqual(total, Decimal("0.00"))

    def test_february_rent_split_is_hand_verifiable(self):
        # Row 1: Aisha pays 48000, equal among 4 -> each owes 12000 exactly.
        commit_batch(self.batch, self.roster)
        rent = Expense.objects.get(description="February rent")
        self.assertEqual(rent.amount_inr, Decimal("48000.00"))
        shares = {s.member.name: s.amount_inr for s in rent.splits.all()}
        self.assertEqual(shares["Rohan"], Decimal("12000.00"))
        self.assertEqual(sum(shares.values()), Decimal("48000.00"))

    def test_meera_dropped_from_april_groceries(self):
        # Row 35: April 2 groceries listed Meera, who had left. She must not
        # get a split for it.
        commit_batch(self.batch, self.roster)
        exp = Expense.objects.filter(
            description="Groceries BigBasket", date=dt.date(2026, 4, 2)
        ).first()
        split_members = {s.member.name for s in exp.splits.all()}
        self.assertNotIn("Meera", split_members)

    def test_usd_expense_converted_with_stored_rate(self):
        # Row 19: Goa villa 540 USD * 85 = 45900 INR.
        commit_batch(self.batch, self.roster)
        villa = Expense.objects.get(description="Goa villa booking")
        self.assertEqual(villa.currency, "USD")
        self.assertEqual(villa.fx_rate, Decimal("85"))
        self.assertEqual(villa.amount_inr, Decimal("45900.00"))


class GenericSheetTests(TestCase):
    """Prove the importer isn't only wired for this exact flat's people.

    Builds a synthetic sheet with a payer and a settlement recipient the
    roster has never heard of, to check they're handled the same way an
    unrecognised participant already is (created as a member) instead of
    silently vanishing.
    """

    def _rows(self, raw_rows):
        return [{"row_number": i, "raw": r, "meta": {}} for i, r in enumerate(raw_rows, 1)]

    def test_unknown_payer_becomes_a_member_not_a_skip(self):
        raw_rows = self._rows(
            [
                {
                    "date": "2026-06-01",
                    "description": "Random shop run",
                    "paid_by": "Zoya",  # not in default_roster() at all
                    "amount": 500,
                    "currency": "INR",
                    "split_type": "equal",
                    "split_with": "Aisha;Rohan;Zoya",
                    "split_details": None,
                    "notes": None,
                }
            ]
        )
        group = Group.objects.create(name="Different Flat")
        roster = default_roster()
        analyzed = analyze(raw_rows, roster)
        batch = stage_batch(group, "other.xlsx", None, analyzed)
        result = commit_batch(batch, roster)["committed"]

        self.assertEqual(result["expenses"], 1)
        self.assertEqual(result["skipped"], 0)
        expense = Expense.objects.get(group=group)
        self.assertEqual(expense.paid_by.name, "Zoya")
        self.assertTrue(expense.paid_by.is_guest)

    def test_missing_payer_still_blocks_correctly(self):
        # An actually-blank payer must still be held, not guessed at.
        raw_rows = self._rows(
            [
                {
                    "date": "2026-06-01",
                    "description": "Mystery charge",
                    "paid_by": None,
                    "amount": 100,
                    "currency": "INR",
                    "split_type": "equal",
                    "split_with": "Aisha;Rohan",
                    "split_details": None,
                    "notes": None,
                }
            ]
        )
        group = Group.objects.create(name="Different Flat 2")
        roster = default_roster()
        analyzed = analyze(raw_rows, roster)
        batch = stage_batch(group, "other.xlsx", None, analyzed)
        result = commit_batch(batch, roster)["committed"]

        self.assertEqual(result["expenses"], 0)
        self.assertEqual(result["skipped"], 1)

    def test_impossible_date_corrects_to_the_sheets_own_year_not_2026(self):
        # A 2027 sheet with one garbled-year row must self-correct to 2027,
        # proving the "expected year" is inferred from the data, not a
        # hardcoded 2026 baked in for this one assignment's dataset.
        raw_rows = self._rows(
            [
                {
                    "date": "2027-01-05",
                    "description": "January rent",
                    "paid_by": "Aisha",
                    "amount": 1000,
                    "currency": "INR",
                    "split_type": "equal",
                    "split_with": "Aisha;Rohan",
                    "split_details": None,
                    "notes": None,
                },
                {
                    "date": "2027-01-10",
                    "description": "Groceries",
                    "paid_by": "Rohan",
                    "amount": 500,
                    "currency": "INR",
                    "split_type": "equal",
                    "split_with": "Aisha;Rohan",
                    "split_details": None,
                    "notes": None,
                },
                {
                    "date": "2003-01-08",  # typo'd year, should become 2027
                    "description": "Wifi bill",
                    "paid_by": "Aisha",
                    "amount": 1200,
                    "currency": "INR",
                    "split_type": "equal",
                    "split_with": "Aisha;Rohan",
                    "split_details": None,
                    "notes": None,
                },
            ]
        )
        roster = default_roster()
        analyzed = analyze(raw_rows, roster)
        wifi = next(r for r in analyzed if r["raw"]["description"] == "Wifi bill")
        self.assertEqual(wifi["cleaned"]["date"].year, 2027)
        codes = {a.code for a in wifi["anomalies"]}
        self.assertIn(A.IMPOSSIBLE_DATE, codes)


class RobustnessTests(TestCase):
    """A missing field or a malformed row must never crash a commit, and must
    never take an otherwise-successful commit down with it. 'A crashed import
    and a silent guess are both failing answers' -- the assignment's own line.
    """

    def _rows(self, raw_rows):
        return [{"row_number": i, "raw": r, "meta": {}} for i, r in enumerate(raw_rows, 1)]

    def test_missing_amount_is_flagged_and_does_not_crash_commit(self):
        raw_rows = self._rows(
            [
                {
                    "date": "2026-06-01",
                    "description": "Blank amount",
                    "paid_by": "Aisha",
                    "amount": None,
                    "currency": "INR",
                    "split_type": "equal",
                    "split_with": "Aisha;Rohan",
                    "split_details": None,
                    "notes": None,
                }
            ]
        )
        roster = default_roster()
        analyzed = analyze(raw_rows, roster)
        self.assertIn(A.MISSING_AMOUNT, {a.code for a in analyzed[0]["anomalies"]})

        group = Group.objects.create(name="Robustness 1")
        batch = stage_batch(group, "x.xlsx", None, analyzed)
        result = commit_batch(batch, roster)["committed"]
        self.assertEqual(result["expenses"], 0)
        self.assertEqual(result["skipped"], 1)

    def test_missing_amount_commits_once_a_human_resolves_it(self):
        # The review UI lets a human type in the real amount; that override
        # must actually be used at commit, not silently ignored.
        raw_rows = self._rows(
            [
                {
                    "date": "2026-06-01",
                    "description": "Blank amount, then fixed",
                    "paid_by": "Aisha",
                    "amount": None,
                    "currency": "INR",
                    "split_type": "equal",
                    "split_with": "Aisha;Rohan",
                    "split_details": None,
                    "notes": None,
                }
            ]
        )
        roster = default_roster()
        analyzed = analyze(raw_rows, roster)
        group = Group.objects.create(name="Robustness 1b")
        batch = stage_batch(group, "x.xlsx", None, analyzed)
        row = batch.rows.get(row_number=1)
        row.resolution = {"amount": "600"}
        row.save(update_fields=["resolution"])

        result = commit_batch(batch, roster)["committed"]
        self.assertEqual(result["expenses"], 1)
        expense = Expense.objects.get(group=group)
        self.assertEqual(expense.amount_original, Decimal("600"))

    def test_missing_date_is_flagged_and_does_not_crash_commit(self):
        raw_rows = self._rows(
            [
                {
                    "date": None,
                    "description": "Blank date",
                    "paid_by": "Aisha",
                    "amount": 500,
                    "currency": "INR",
                    "split_type": "equal",
                    "split_with": "Aisha;Rohan",
                    "split_details": None,
                    "notes": None,
                }
            ]
        )
        roster = default_roster()
        analyzed = analyze(raw_rows, roster)
        self.assertIn(A.MISSING_DATE, {a.code for a in analyzed[0]["anomalies"]})

        group = Group.objects.create(name="Robustness 2")
        batch = stage_batch(group, "x.xlsx", None, analyzed)
        result = commit_batch(batch, roster)["committed"]
        self.assertEqual(result["expenses"], 0)
        self.assertEqual(result["skipped"], 1)

    def test_one_broken_row_does_not_sink_the_rest_of_the_batch(self):
        # An "unequal" split whose amounts don't sum to the total isn't
        # caught by any detector ahead of time -- it only fails inside
        # compute_shares() at commit. That must skip just this row, not
        # roll back the two good rows around it.
        raw_rows = self._rows(
            [
                {
                    "date": "2026-06-01",
                    "description": "Good expense before",
                    "paid_by": "Aisha",
                    "amount": 400,
                    "currency": "INR",
                    "split_type": "equal",
                    "split_with": "Aisha;Rohan",
                    "split_details": None,
                    "notes": None,
                },
                {
                    "date": "2026-06-02",
                    "description": "Broken unequal split",
                    "paid_by": "Aisha",
                    "amount": 100,
                    "currency": "INR",
                    "split_type": "unequal",
                    "split_with": "Aisha;Rohan",
                    "split_details": "Aisha 60; Rohan 50",  # sums to 110, not 100
                    "notes": None,
                },
                {
                    "date": "2026-06-03",
                    "description": "Good expense after",
                    "paid_by": "Rohan",
                    "amount": 200,
                    "currency": "INR",
                    "split_type": "equal",
                    "split_with": "Aisha;Rohan",
                    "split_details": None,
                    "notes": None,
                },
            ]
        )
        roster = default_roster()
        analyzed = analyze(raw_rows, roster)
        group = Group.objects.create(name="Robustness 3")
        batch = stage_batch(group, "x.xlsx", None, analyzed)

        result = commit_batch(batch, roster)["committed"]
        self.assertEqual(result["expenses"], 2)  # the two good rows
        self.assertEqual(result["skipped"], 1)  # only the broken one

        self.assertTrue(
            Expense.objects.filter(description="Good expense before").exists()
        )
        self.assertTrue(
            Expense.objects.filter(description="Good expense after").exists()
        )
        self.assertFalse(
            Expense.objects.filter(description="Broken unequal split").exists()
        )

        report = build_report(batch)
        error_findings = [
            f for f in report["findings"] if f["code"] == A.ROW_COMMIT_ERROR
        ]
        self.assertEqual(len(error_findings), 1)
        self.assertEqual(error_findings[0]["row"], 2)
