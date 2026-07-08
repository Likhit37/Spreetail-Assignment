"""Who's who in this flat.

The importer needs a canonical roster to do three things the raw sheet can't:
  * fold messy spellings ("priya", "Priya S", "rohan ") into one person,
  * know that Meera left end-March and Sam joined mid-April (date windows),
  * spot a participant who isn't a flatmate at all (Dev's friend Kabir).

These defaults come straight from the assignment narrative and are documented
in DECISIONS.md. They are *defaults*: the review UI lets a human correct any of
them before commit, so we are not hard-coding a silent guess — we are seeding a
best guess and surfacing it.
"""

from dataclasses import dataclass, field
from datetime import date


def normalize(value: str) -> str:
    return " ".join((value or "").strip().lower().split())


@dataclass
class Roster:
    # normalized spelling -> canonical name
    aliases: dict = field(default_factory=dict)
    # canonical name -> (joined_at, left_at); None means open-ended
    windows: dict = field(default_factory=dict)

    def canonical(self, raw_name: str):
        """Canonical member name for a raw spelling, or None if unknown."""
        return self.aliases.get(normalize(raw_name))

    def is_alias_of_canonical(self, raw_name: str) -> bool:
        """True if the raw spelling differs from its canonical form.

        We compare the *raw* string, not the normalised one, so casing- and
        whitespace-only messes ("priya", "rohan ") are surfaced too — that is
        exactly the spelling inconsistency Rohan complained about.
        """
        canon = self.canonical(raw_name)
        return canon is not None and raw_name != canon

    def active_on(self, canonical_name: str, on: date) -> bool:
        window = self.windows.get(canonical_name)
        if not window:
            return True
        joined, left = window
        if joined and on < joined:
            return False
        if left and on > left:
            return False
        return True

    def members(self) -> list:
        return sorted(set(self.aliases.values()))


def default_roster() -> Roster:
    """The flat's roster as told by the assignment."""
    canon = ["Aisha", "Rohan", "Priya", "Meera", "Dev", "Sam"]
    aliases = {normalize(c): c for c in canon}
    # Extra spellings that appear in the sheet.
    aliases.update(
        {
            normalize("priya s"): "Priya",
            normalize("priya"): "Priya",
            normalize("rohan"): "Rohan",  # trailing-space variant normalises here
        }
    )
    windows = {
        # Meera moved out at the end of March.
        "Meera": (date(2026, 2, 1), date(2026, 3, 31)),
        # Sam moved in mid-April; his deposit is dated Apr 8.
        "Sam": (date(2026, 4, 8), None),
        # Aisha/Rohan/Priya are here throughout. Dev is a visitor with no
        # strict window (he only ever appears on trip/visit dates anyway).
    }
    return Roster(aliases=aliases, windows=windows)
