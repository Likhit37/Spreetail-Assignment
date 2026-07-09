from datetime import date
from decimal import Decimal

from django.test import TestCase

from .models import (
    Expense,
    ExpenseSplit,
    Group,
    GroupMembership,
    Member,
    Settlement,
)
from .services.balances import member_ledger, net_balances, simplify
from .services.expense_ops import ExpenseInputError, create_expense
from .services.splitting import compute_shares


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


class ManualExpenseTests(TestCase):
    def setUp(self):
        self.g = Group.objects.create(name="Flat")
        self.a = Member.objects.create(group=self.g, name="Aisha")
        self.b = Member.objects.create(group=self.g, name="Rohan")
        self.c = Member.objects.create(group=self.g, name="Priya")

    def test_manual_equal_expense_creates_balanced_splits(self):
        exp = create_expense(
            group=self.g,
            date=date(2026, 5, 1),
            description="Dinner",
            paid_by_id=self.a.id,
            amount_original=Decimal("900"),
            currency="INR",
            split_type="equal",
            participant_ids=[self.a.id, self.b.id, self.c.id],
        )
        self.assertEqual(exp.splits.count(), 3)
        net = net_balances(self.g)
        self.assertEqual(net[self.a.id], Decimal("600.00"))
        self.assertEqual(sum(net.values()), Decimal("0.00"))

    def test_manual_percentage_expense(self):
        exp = create_expense(
            group=self.g,
            date=date(2026, 5, 1),
            description="Party",
            paid_by_id=self.a.id,
            amount_original=Decimal("1000"),
            currency="INR",
            split_type="percentage",
            details_by_id={self.a.id: "50", self.b.id: "50"},
        )
        shares = {s.member_id: s.amount_inr for s in exp.splits.all()}
        self.assertEqual(shares[self.a.id], Decimal("500.00"))
        self.assertEqual(sum(shares.values()), Decimal("1000.00"))

    def test_manual_expense_rejects_inactive_member(self):
        # Priya left before the expense date.
        GroupMembership.objects.create(
            member=self.c, joined_at=date(2026, 1, 1), left_at=date(2026, 4, 30)
        )
        with self.assertRaises(ExpenseInputError):
            create_expense(
                group=self.g,
                date=date(2026, 5, 1),
                description="Late dinner",
                paid_by_id=self.a.id,
                amount_original=Decimal("300"),
                currency="INR",
                split_type="equal",
                participant_ids=[self.a.id, self.c.id],
            )

    def test_unequal_must_sum_to_total(self):
        with self.assertRaises(ExpenseInputError):
            create_expense(
                group=self.g,
                date=date(2026, 5, 1),
                description="Bad",
                paid_by_id=self.a.id,
                amount_original=Decimal("100"),
                currency="INR",
                split_type="unequal",
                details_by_id={self.a.id: "60", self.b.id: "50"},
            )


class ApiFlowTests(TestCase):
    """Endpoint-level tests for the management flows added for compliance."""

    def setUp(self):
        from django.contrib.auth import get_user_model
        from rest_framework.test import APIClient

        self.user = get_user_model().objects.create_user("u", "u@x.com", "pw123456")
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        self.g = Group.objects.create(name="Flat", created_by=self.user)
        self.a = Member.objects.create(group=self.g, name="Aisha")
        self.b = Member.objects.create(group=self.g, name="Rohan")

    def test_add_expense_endpoint_creates_splits(self):
        r = self.client.post(
            "/api/expenses/",
            {
                "group": self.g.id,
                "date": "2026-05-01",
                "description": "Groceries",
                "paid_by": self.a.id,
                "amount_original": "500",
                "currency": "INR",
                "split_type": "equal",
                "participants": [self.a.id, self.b.id],
            },
            format="json",
        )
        self.assertEqual(r.status_code, 201)
        self.assertEqual(len(r.json()["splits"]), 2)

    def test_settlement_rejects_same_from_to(self):
        r = self.client.post(
            "/api/settlements/",
            {
                "group": self.g.id,
                "date": "2026-05-01",
                "from_member": self.a.id,
                "to_member": self.a.id,
                "amount_inr": "100",
            },
            format="json",
        )
        self.assertEqual(r.status_code, 400)

    def test_settlement_valid_updates_balance(self):
        r = self.client.post(
            "/api/settlements/",
            {
                "group": self.g.id,
                "date": "2026-05-01",
                "from_member": self.b.id,
                "to_member": self.a.id,
                "amount_inr": "100",
            },
            format="json",
        )
        self.assertEqual(r.status_code, 201)
        net = net_balances(self.g)
        self.assertEqual(net[self.b.id], Decimal("100.00"))
        self.assertEqual(net[self.a.id], Decimal("-100.00"))

    def test_cannot_add_expense_to_other_users_group(self):
        from django.contrib.auth import get_user_model
        from rest_framework.test import APIClient

        other = get_user_model().objects.create_user("v", "v@x.com", "pw123456")
        c2 = APIClient()
        c2.force_authenticate(other)
        r = c2.post(
            "/api/expenses/",
            {
                "group": self.g.id,
                "date": "2026-05-01",
                "description": "Sneaky",
                "paid_by": self.a.id,
                "amount_original": "100",
                "currency": "INR",
                "split_type": "equal",
                "participants": [self.a.id, self.b.id],
            },
            format="json",
        )
        self.assertEqual(r.status_code, 403)

    def test_add_member_and_leave(self):
        r = self.client.post(
            f"/api/groups/{self.g.id}/add_member/",
            {"name": "Sam", "joined_at": "2026-04-08"},
            format="json",
        )
        self.assertIn(r.status_code, (200, 201))
        sam = Member.objects.get(group=self.g, name="Sam")
        # Sam is not active before joining.
        self.assertFalse(sam.is_active_on(date(2026, 3, 1)))
        self.assertTrue(sam.is_active_on(date(2026, 4, 20)))
        # Mark leaving.
        r = self.client.post(
            f"/api/groups/{self.g.id}/members/{sam.id}/leave/",
            {"left_at": "2026-06-30"},
            format="json",
        )
        self.assertEqual(r.status_code, 200)
        self.assertFalse(sam.is_active_on(date(2026, 7, 15)))
