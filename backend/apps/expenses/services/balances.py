"""Balance engine.

Two products, both required by the flatmates:

* net_balances(group)  -> one signed number per member (Aisha: "who owes whom")
* simplify(group)      -> minimal list of "X pays Y ₹Z" transfers
* member_ledger(group, member) -> every line that makes up a balance, so a
  number is never magic (Rohan).

Convention: a member's net is
    net = (what they paid out) - (their share of expenses)
          + (settlements they paid) - (settlements they received)
Positive net  => the group owes them (creditor).
Negative net  => they owe the group (debtor).

Settlements move money without creating a share: paying down a debt raises the
payer's net and lowers the receiver's.
"""

from decimal import Decimal

from ..models import Expense, ExpenseSplit, Member, Settlement
from .splitting import round_money


def _zero_map(members):
    return {m.id: Decimal("0") for m in members}


def net_balances(group) -> dict:
    """Return {member_id: Decimal net} for every member in the group."""
    members = list(group.members.all())
    net = _zero_map(members)

    # Expenses: payer is credited the full rupee amount.
    for exp in group.expenses.select_related("paid_by").all():
        if exp.paid_by_id is not None:
            net[exp.paid_by_id] += exp.amount_inr

    # Splits: each member is debited their share.
    for split in ExpenseSplit.objects.filter(expense__group=group):
        net[split.member_id] -= split.amount_inr

    # Settlements: payer's debt shrinks (+), receiver's credit shrinks (-).
    for s in group.settlements.all():
        net[s.from_member_id] += s.amount_inr
        net[s.to_member_id] -= s.amount_inr

    return {mid: round_money(v) for mid, v in net.items()}


def simplify(group) -> list[dict]:
    """Greedy minimal transfers: match biggest debtor to biggest creditor.

    Returns [{from_member, to_member, amount}]. This is Aisha's "one number
    per person" view. It is intentionally simple and deterministic so it can
    be walked by hand.
    """
    net = net_balances(group)
    id_to_member = {m.id: m for m in group.members.all()}

    debtors = sorted(
        ([mid, amt] for mid, amt in net.items() if amt < 0),
        key=lambda x: x[1],
    )
    creditors = sorted(
        ([mid, amt] for mid, amt in net.items() if amt > 0),
        key=lambda x: -x[1],
    )

    transfers = []
    i = j = 0
    while i < len(debtors) and j < len(creditors):
        d_id, d_amt = debtors[i]
        c_id, c_amt = creditors[j]
        pay = min(-d_amt, c_amt)
        pay = round_money(pay)
        if pay > 0:
            transfers.append(
                {
                    "from_member": d_id,
                    "from_name": id_to_member[d_id].name,
                    "to_member": c_id,
                    "to_name": id_to_member[c_id].name,
                    "amount": str(pay),
                }
            )
        debtors[i][1] = d_amt + pay
        creditors[j][1] = c_amt - pay
        if debtors[i][1] == 0:
            i += 1
        if creditors[j][1] == 0:
            j += 1
    return transfers


def member_ledger(group, member: Member) -> dict:
    """Every line item behind one member's balance (Rohan's drill-down)."""
    paid = []
    for exp in group.expenses.filter(paid_by=member):
        paid.append(
            {
                "expense_id": exp.id,
                "date": str(exp.date),
                "description": exp.description,
                "amount_inr": str(exp.amount_inr),
            }
        )

    owes = []
    for split in (
        ExpenseSplit.objects.filter(expense__group=group, member=member)
        .select_related("expense")
    ):
        owes.append(
            {
                "expense_id": split.expense_id,
                "date": str(split.expense.date),
                "description": split.expense.description,
                "share_inr": str(split.amount_inr),
            }
        )

    settlements = []
    for s in Settlement.objects.filter(group=group).filter(
        from_member=member
    ) | Settlement.objects.filter(group=group, to_member=member):
        direction = "paid" if s.from_member_id == member.id else "received"
        other = s.to_member if direction == "paid" else s.from_member
        settlements.append(
            {
                "settlement_id": s.id,
                "date": str(s.date),
                "direction": direction,
                "counterparty": other.name,
                "amount_inr": str(s.amount_inr),
            }
        )

    net = net_balances(group).get(member.id, Decimal("0"))
    return {
        "member": member.name,
        "net_inr": str(net),
        "interpretation": (
            "is owed by the group"
            if net > 0
            else "owes the group"
            if net < 0
            else "is settled up"
        ),
        "paid_expenses": paid,
        "owed_shares": owes,
        "settlements": settlements,
    }
