"""Turn one expense's split_type + inputs into exact per-member rupee shares.

Kept deliberately small and pure so it is easy to trace by hand in the live
session and easy to unit-test. All money is Decimal; we round half-up to 2 dp
and put any leftover paisa on the payer (or the first member) so the shares
always sum back to the total exactly — no money is invented or lost.
"""

from decimal import ROUND_HALF_UP, Decimal

TWO_DP = Decimal("0.01")


def round_money(value: Decimal) -> Decimal:
    return Decimal(value).quantize(TWO_DP, rounding=ROUND_HALF_UP)


def _distribute(total: Decimal, weights: list[Decimal]) -> list[Decimal]:
    """Split `total` across `weights`, rounding each and fixing the remainder.

    The last cent(s) lost/gained to rounding are absorbed by the largest share
    so the parts always sum to `total`.
    """
    weight_sum = sum(weights)
    if weight_sum == 0:
        raise ValueError("weights sum to zero")
    raw = [total * w / weight_sum for w in weights]
    rounded = [round_money(x) for x in raw]
    drift = round_money(total) - sum(rounded)
    if drift != 0:
        # Put the drift on the member with the largest share.
        idx = max(range(len(rounded)), key=lambda i: rounded[i])
        rounded[idx] = round_money(rounded[idx] + drift)
    return rounded


def compute_shares(
    split_type: str,
    total_inr: Decimal,
    members: list,
    details: dict | None = None,
) -> dict:
    """Return {member: rupee_share}.

    `members` is the list of participating members (already filtered to those
    active on the expense date). `details` maps member -> raw share input for
    unequal/percentage/share types.
    """
    total_inr = Decimal(total_inr)
    details = details or {}

    if not members:
        raise ValueError("no participating members")

    if split_type == "equal":
        weights = [Decimal("1")] * len(members)
        amounts = _distribute(total_inr, weights)
        return dict(zip(members, amounts))

    if split_type == "unequal":
        # details are exact rupee amounts; must sum to the total.
        amounts = [Decimal(details[m]) for m in members]
        if round_money(sum(amounts)) != round_money(total_inr):
            raise ValueError(
                f"unequal amounts {sum(amounts)} != total {total_inr}"
            )
        return {m: round_money(a) for m, a in zip(members, amounts)}

    if split_type == "percentage":
        weights = [Decimal(details[m]) for m in members]
        amounts = _distribute(total_inr, weights)
        return dict(zip(members, amounts))

    if split_type == "share":
        weights = [Decimal(details[m]) for m in members]
        amounts = _distribute(total_inr, weights)
        return dict(zip(members, amounts))

    raise ValueError(f"unknown split_type: {split_type}")
