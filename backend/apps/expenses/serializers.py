from rest_framework import serializers

from .models import (
    Expense,
    ExpenseSplit,
    Group,
    Member,
    Settlement,
)


class MemberSerializer(serializers.ModelSerializer):
    class Meta:
        model = Member
        fields = ("id", "group", "name", "is_guest")
        read_only_fields = ("group",)


class GroupSerializer(serializers.ModelSerializer):
    members = MemberSerializer(many=True, read_only=True)

    class Meta:
        model = Group
        fields = ("id", "name", "created_at", "members")
        read_only_fields = ("created_at",)


class ExpenseSplitSerializer(serializers.ModelSerializer):
    member_name = serializers.CharField(source="member.name", read_only=True)

    class Meta:
        model = ExpenseSplit
        fields = ("id", "member", "member_name", "share_value", "amount_inr")


class ExpenseSerializer(serializers.ModelSerializer):
    splits = ExpenseSplitSerializer(many=True, read_only=True)
    paid_by_name = serializers.CharField(source="paid_by.name", read_only=True)

    class Meta:
        model = Expense
        fields = (
            "id",
            "group",
            "date",
            "description",
            "paid_by",
            "paid_by_name",
            "amount_original",
            "currency",
            "fx_rate",
            "amount_inr",
            "split_type",
            "notes",
            "splits",
        )


class SettlementSerializer(serializers.ModelSerializer):
    from_name = serializers.CharField(source="from_member.name", read_only=True)
    to_name = serializers.CharField(source="to_member.name", read_only=True)

    class Meta:
        model = Settlement
        fields = (
            "id",
            "group",
            "date",
            "from_member",
            "from_name",
            "to_member",
            "to_name",
            "amount_inr",
            "note",
        )
