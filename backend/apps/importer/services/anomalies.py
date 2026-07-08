"""Anomaly registry.

Every deliberate data problem in the sheet has a code here. Keeping them in one
place means SCOPE.md, the import report, and the detectors never drift apart.

severity:
  * blocker  -> row cannot commit until a human resolves it
  * warning  -> committed with a documented default, but surfaced
  * info     -> handled automatically, shown for transparency
"""

from dataclasses import dataclass, field


@dataclass
class Anomaly:
    code: str
    severity: str
    message: str
    suggestion: str = ""
    # The default action the importer will take if the user does not override.
    action: str = ""
    meta: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "code": self.code,
            "severity": self.severity,
            "message": self.message,
            "suggestion": self.suggestion,
            "action": self.action,
            "meta": self.meta,
        }


# --- codes (also used as stable keys in the report) ---
DUPLICATE_EXACT = "DUPLICATE_EXACT"
DUPLICATE_CONFLICT = "DUPLICATE_CONFLICT"
SETTLEMENT_AS_EXPENSE = "SETTLEMENT_AS_EXPENSE"
FOREIGN_CURRENCY = "FOREIGN_CURRENCY"
NEGATIVE_AMOUNT = "NEGATIVE_AMOUNT"
MISSING_CURRENCY = "MISSING_CURRENCY"
MISSING_PAYER = "MISSING_PAYER"
NAME_ALIAS = "NAME_ALIAS"
IMPOSSIBLE_DATE = "IMPOSSIBLE_DATE"
AMBIGUOUS_DATE = "AMBIGUOUS_DATE"
ZERO_AMOUNT = "ZERO_AMOUNT"
PERCENTAGE_SUM_INVALID = "PERCENTAGE_SUM_INVALID"
SUBUNIT_PRECISION = "SUBUNIT_PRECISION"
SPLIT_TYPE_DETAIL_CONFLICT = "SPLIT_TYPE_DETAIL_CONFLICT"
MEMBERSHIP_DATE_MISMATCH = "MEMBERSHIP_DATE_MISMATCH"
NON_MEMBER_PARTICIPANT = "NON_MEMBER_PARTICIPANT"
UNKNOWN_PAYER = "UNKNOWN_PAYER"
