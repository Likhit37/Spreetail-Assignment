"""Detector tests run against the real, unedited export file.

Each test pins one anomaly to the specific row that triggers it, so if a
detector regresses we know exactly which flatmate complaint broke.
"""

from pathlib import Path

from django.test import SimpleTestCase

from .services import anomalies as A
from .services.detectors import analyze
from .services.parsing import parse_upload
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

    def test_deep_cleaning_ambiguous_date(self):
        self.assertIn(A.AMBIGUOUS_DATE, self.by_row.get(33, set()))

    def test_pizza_percentages_over_100(self):
        self.assertIn(A.PERCENTAGE_SUM_INVALID, self.by_row.get(14, set()))

    def test_meera_not_in_flat_in_april(self):
        # Row 35: April 2 groceries still list Meera.
        self.assertIn(A.MEMBERSHIP_DATE_MISMATCH, self.by_row.get(35, set()))

    def test_kabir_is_non_member(self):
        self.assertIn(A.NON_MEMBER_PARTICIPANT, self.by_row.get(22, set()))
