from django.shortcuts import get_object_or_404
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import Expense, Group, Member, Settlement
from .serializers import (
    ExpenseSerializer,
    GroupSerializer,
    MemberSerializer,
    SettlementSerializer,
)
from .services.balances import member_ledger, net_balances, simplify
from .services.explain import explain_balance


class GroupViewSet(viewsets.ModelViewSet):
    serializer_class = GroupSerializer

    def get_queryset(self):
        # Groups the user created or is a member of.
        user = self.request.user
        return (
            Group.objects.filter(created_by=user)
            | Group.objects.filter(members__user=user)
        ).distinct()

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

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


class MemberViewSet(viewsets.ModelViewSet):
    serializer_class = MemberSerializer

    def get_queryset(self):
        qs = Member.objects.all()
        group_id = self.request.query_params.get("group")
        if group_id:
            qs = qs.filter(group_id=group_id)
        return qs


class ExpenseViewSet(viewsets.ModelViewSet):
    serializer_class = ExpenseSerializer

    def get_queryset(self):
        qs = Expense.objects.select_related("paid_by").prefetch_related("splits")
        group_id = self.request.query_params.get("group")
        if group_id:
            qs = qs.filter(group_id=group_id)
        return qs


class SettlementViewSet(viewsets.ModelViewSet):
    serializer_class = SettlementSerializer

    def get_queryset(self):
        qs = Settlement.objects.all()
        group_id = self.request.query_params.get("group")
        if group_id:
            qs = qs.filter(group_id=group_id)
        return qs
