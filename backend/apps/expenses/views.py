from django.shortcuts import get_object_or_404
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import Expense, Group, GroupMembership, Member, Settlement
from .serializers import (
    ExpenseCreateSerializer,
    ExpenseSerializer,
    GroupSerializer,
    MemberSerializer,
    SettlementSerializer,
)
from .services.balances import member_ledger, net_balances, simplify
from .services.expense_ops import ExpenseInputError, create_expense
from .services.explain import explain_balance


def accessible_groups(user):
    """Groups the user created or is a member of. Used to scope reads/writes."""
    return (
        Group.objects.filter(created_by=user)
        | Group.objects.filter(members__user=user)
    ).distinct()


class GroupViewSet(viewsets.ModelViewSet):
    serializer_class = GroupSerializer

    def get_queryset(self):
        return accessible_groups(self.request.user)

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    def perform_destroy(self, instance):
        # Members are PROTECT-referenced by Expense.paid_by / ExpenseSplit.member
        # / Settlement, which stops a member being deleted while they're still
        # owed/owing. That protection is correct for deleting one member, but it
        # would otherwise make deleting a whole group (which should tear down
        # everything in it) fail with a ProtectedError. Clear the referencing
        # rows first, then the cascade from Group -> Member is unobstructed.
        from django.db import transaction

        with transaction.atomic():
            Expense.objects.filter(group=instance).delete()  # cascades splits
            Settlement.objects.filter(group=instance).delete()
            instance.delete()  # cascades members, memberships, aliases, imports

    @action(detail=True, methods=["get"])
    def balances(self, request, pk=None):
        group = self.get_object()
        members = {m.id: m.name for m in group.members.all()}
        net = net_balances(group)
        return Response(
            {
                "net": [
                    {
                        "member": mid,
                        "name": members[mid],
                        "net_inr": str(amt),
                    }
                    for mid, amt in net.items()
                ],
                "simplified": simplify(group),
            }
        )

    @action(
        detail=True,
        methods=["get"],
        url_path="members/(?P<member_id>[^/.]+)/ledger",
    )
    def ledger(self, request, pk=None, member_id=None):
        group = self.get_object()
        member = get_object_or_404(Member, group=group, id=member_id)
        return Response(member_ledger(group, member))

    @action(
        detail=True,
        methods=["get"],
        url_path="members/(?P<member_id>[^/.]+)/explain",
    )
    def explain(self, request, pk=None, member_id=None):
        group = self.get_object()
        member = get_object_or_404(Member, group=group, id=member_id)
        return Response(explain_balance(group, member))

    @action(detail=True, methods=["post"])
    def add_member(self, request, pk=None):
        """Add a person to the group, optionally with a join date."""
        group = self.get_object()
        name = (request.data.get("name") or "").strip()
        if not name:
            return Response({"detail": "name is required"}, status=400)
        member, created = Member.objects.get_or_create(group=group, name=name)
        joined_at = request.data.get("joined_at")
        if joined_at:
            GroupMembership.objects.get_or_create(
                member=member, joined_at=joined_at, left_at=None
            )
        return Response(MemberSerializer(member).data, status=201 if created else 200)

    @action(
        detail=True,
        methods=["post"],
        url_path="members/(?P<member_id>[^/.]+)/leave",
    )
    def member_leave(self, request, pk=None, member_id=None):
        """Mark when a member left (membership changes over time)."""
        group = self.get_object()
        member = get_object_or_404(Member, group=group, id=member_id)
        left_at = request.data.get("left_at")
        if not left_at:
            return Response({"detail": "left_at is required"}, status=400)
        window = member.membership_windows.filter(left_at__isnull=True).first()
        if window:
            window.left_at = left_at
            window.save(update_fields=["left_at"])
        else:
            GroupMembership.objects.create(member=member, left_at=left_at)
        return Response({"member": member.name, "left_at": left_at})


class MemberViewSet(viewsets.ModelViewSet):
    serializer_class = MemberSerializer

    def get_queryset(self):
        qs = Member.objects.filter(group__in=accessible_groups(self.request.user))
        group_id = self.request.query_params.get("group")
        if group_id:
            qs = qs.filter(group_id=group_id)
        return qs


class ExpenseViewSet(viewsets.ModelViewSet):
    serializer_class = ExpenseSerializer

    def get_queryset(self):
        # Only expenses in groups the user can access.
        qs = (
            Expense.objects.filter(group__in=accessible_groups(self.request.user))
            .select_related("paid_by")
            .prefetch_related("splits")
        )
        group_id = self.request.query_params.get("group")
        if group_id:
            qs = qs.filter(group_id=group_id)
        return qs

    def create(self, request, *args, **kwargs):
        """Manual add: compute + store splits via the shared engine."""
        form = ExpenseCreateSerializer(data=request.data)
        form.is_valid(raise_exception=True)
        v = form.validated_data
        if v["group"] not in accessible_groups(request.user):
            return Response({"detail": "no access to this group"}, status=403)
        try:
            expense = create_expense(
                group=v["group"],
                date=v["date"],
                description=v["description"],
                paid_by_id=v["paid_by"],
                amount_original=v["amount_original"],
                currency=v["currency"],
                split_type=v["split_type"],
                participant_ids=v["participants"],
                details_by_id=v["details"],
            )
        except ExpenseInputError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(
            ExpenseSerializer(expense).data, status=status.HTTP_201_CREATED
        )


class SettlementViewSet(viewsets.ModelViewSet):
    serializer_class = SettlementSerializer

    def get_queryset(self):
        qs = Settlement.objects.filter(
            group__in=accessible_groups(self.request.user)
        )
        group_id = self.request.query_params.get("group")
        if group_id:
            qs = qs.filter(group_id=group_id)
        return qs

    def perform_create(self, serializer):
        if serializer.validated_data["group"] not in accessible_groups(
            self.request.user
        ):
            from rest_framework.exceptions import PermissionDenied

            raise PermissionDenied("no access to this group")
        serializer.save()
