from datetime import date
from decimal import Decimal

from django.test import TestCase

from .models import Expense, ExpenseSplit, Group, Member, Settlement
from .services.balances import member_ledger, net_balances, simplify
from .services.splitting import compute_shares, round_money


class SplittingTests(TestCase):
    def setUp(self):
        self.g = Group.objects.create(name="Flat")
        self.a = Member.objects.create(group=self.g, name="Aisha")
        self.b = Member.objects.create(group=self.g, name="Rohan")
        self.c = Member.objects.create(group=self.g, name="Priya")

    def test_equal_split_divides_evenly(self):
        shares = compute_shares("equal", Decimal("300"), [self.a, self.b, self.c])
        self.assertEqual(shares[self.a], Decimal("100.00"))
        self.assertEqual(sum(shares.values()), Decimal("300.00"))

    def test_equal_split_absorbs_rounding_remainder(self):
        # 100 / 3 = 33.33 each, 0.01 drift must be absorbed -> sum stays 100.
        shares = compute_shares("equal", Decimal("100"), [self.a, self.b, self.c])
        self.assertEqual(sum(shares.values()), Decimal("100.00"))

    def test_percentage_split(self):
        shares = compute_shares(
            "percentage",
            Decimal("1000"),
            [self.a, self.b],
            {self.a: Decimal("70"), self.b: Decimal("30")},
        )
        self.assertEqual(shares[self.a], Decimal("700.00"))
        self.assertEqual(shares[self.b], Decimal("300.00"))

    def test_share_ratio_split(self):
        # ratio 1:2:1 of 400 -> 100 / 200 / 100
        shares = compute_shares(
            "share",
            Decimal("400"),
            [self.a, self.b, self.c],
            {self.a: Decimal("1"), self.b: Decimal("2"), self.c: Decimal("1")},
        )
        self.assertEqual(shares[self.b], Decimal("200.00"))
        self.assertEqual(sum(shares.values()), Decimal("400.00"))

    def test_unequal_must_sum_to_total(self):
        with self.assertRaises(ValueError):
            compute_shares(
                "unequal",
                Decimal("100"),
                [self.a, self.b],
                {self.a: Decimal("60"), self.b: Decimal("50")},
            )


class BalanceTests(TestCase):
    def setUp(self):
        self.g = Group.objects.create(name="Flat")
        self.a = Member.objects.create(group=self.g, name="Aisha")
        self.b = Member.objects.create(group=self.g, name="Rohan")
        self.c = Member.objects.create(group=self.g, name="Priya")

    def _add_equal_expense(self, payer, amount, members):
        exp = Expense.objects.create(
            group=self.g,
            date=date(2026, 2, 1),
            description="test",
            paid_by=payer,
            amount_original=amount,
            currency="INR",
            amount_inr=amount,
            split_type="equal",
        )
        shares = compute_shares("equal", Decimal(amount), members)
        for m, share in shares.items():
            ExpenseSplit.objects.create(
                expense=exp, member=m, amount_inr=share
            )
        return exp

    def test_single_expense_balances(self):
        # Aisha pays 300 for all three; each owes 100. Aisha net +200.
        self._add_equal_expense(self.a, Decimal("300"), [self.a, self.b, self.c])
        net = net_balances(self.g)
        self.assertEqual(net[self.a.id], Decimal("200.00"))
        self.assertEqual(net[self.b.id], Decimal("-100.00"))
        self.assertEqual(net[self.c.id], Decimal("-100.00"))
        # Nets must always sum to zero.
        self.assertEqual(sum(net.values()), Decimal("0.00"))

    def test_settlement_moves_money(self):
        self._add_equal_expense(self.a, Decimal("300"), [self.a, self.b, self.c])
        # Rohan pays Aisha back his 100.
        Settlement.objects.create(
            group=self.g,
            date=date(2026, 2, 2),
            from_member=self.b,
            to_member=self.a,
            amount_inr=Decimal("100"),
        )
        net = net_balances(self.g)
        self.assertEqual(net[self.b.id], Decimal("0.00"))
        self.assertEqual(net[self.a.id], Decimal("100.00"))

    def test_simplify_produces_minimal_transfers(self):
        self._add_equal_expense(self.a, Decimal("300"), [self.a, self.b, self.c])
        transfers = simplify(self.g)
        # Two debtors each owe Aisha 100.
        self.assertEqual(len(transfers), 2)
        for t in transfers:
            self.assertEqual(t["to_name"], "Aisha")
            self.assertEqual(t["amount"], "100.00")

    def test_member_ledger_drilldown(self):
        self._add_equal_expense(self.a, Decimal("300"), [self.a, self.b, self.c])
        ledger = member_ledger(self.g, self.b)
        self.assertEqual(ledger["net_inr"], "-100.00")
        self.assertEqual(len(ledger["owed_shares"]), 1)
        self.assertEqual(ledger["owed_shares"][0]["share_inr"], "100.00")
