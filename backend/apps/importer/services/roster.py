"""Who's who in this flat.

The importer needs a canonical roster to do three things the raw sheet can't:
  * fold messy spellings ("priya", "Priya S", "rohan ") into one person,
  * know that Meera left end-March and Sam joined mid-April (date windows),
  * spot a participant who isn't a flatmate at all (Dev's friend Kabir).

`default_roster()` below is the ONE deliberately hardcoded piece of domain
knowledge in this codebase, and it is hardcoded on purpose, not out of
laziness: the assignment PDF *narrates* who these six people are and states
outright that "Meera moved out at the end of March, and Sam moved in
mid-April." No algorithm can derive that from the spreadsheet alone — those
facts live in a sentence of English the sheet never contains. Swapping in a
different flat means writing a different `default_roster()` (or building a
small admin UI for it); nothing else in the importer changes.

Everything downstream of the roster IS generic, and is exercised in
GenericSheetTests against a synthetic sheet the roster was never seeded for:
  * name matching for casing/whitespace ("priya", "ROHAN ") happens for free
    for any name in the roster via `normalize()` below — no per-name entry
    needed. Only genuinely different spellings ("Priya S") need an explicit
    alias.
  * a payer or settlement counterparty the roster doesn't recognise is not
    silently dropped: they're created as a real (guest) member, exactly like
    an unrecognised participant already was. See `_resolve_or_create_member`
    in pipeline.py.
  * the "impossible date" detector infers which year the sheet is actually
    using from the sheet's own data (the mode of its parsed dates), instead
    of assuming any particular year. See `_infer_expected_year`.

These defaults are still just *defaults*: the review UI lets a human correct
any of them before commit, so seeding a best guess and surfacing it is not
the same as hard-coding a silent guess.
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
    """The flat's roster as told by the assignment's narrative (see module
    docstring for why this is the one deliberately hardcoded piece of
    domain knowledge here, and why nothing else needs to be).
    """
    canon = ["Aisha", "Rohan", "Priya", "Meera", "Dev", "Sam"]
    # Case/whitespace variants of these six names (e.g. "priya", "rohan ")
    # already match via normalize() in `canonical()` above — no per-name
    # entry needed for those. Only a genuinely different spelling needs one.
    aliases = {normalize(c): c for c in canon}
    aliases[normalize("priya s")] = "Priya"
    windows = {
        # Meera moved out at the end of March.
        "Meera": (date(2026, 2, 1), date(2026, 3, 31)),
        # Sam moved in mid-April; his deposit is dated Apr 8.
        "Sam": (date(2026, 4, 8), None),
        # Aisha/Rohan/Priya are here throughout. Dev is a visitor with no
        # strict window (he only ever appears on trip/visit dates anyway).
    }
    return Roster(aliases=aliases, windows=windows)
