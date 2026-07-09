from rest_framework import serializers

from .models import (
    Expense,
    ExpenseSplit,
    Group,
    Member,
    Settlement,
)


class MemberSerializer(serializers.ModelSerializer):
    # The member's membership window (if any), so the UI can tell who was in
    # the flat on a given date. Null dates mean open-ended / always active.
    joined_at = serializers.SerializerMethodField()
    left_at = serializers.SerializerMethodField()

    class Meta:
        model = Member
        fields = ("id", "group", "name", "is_guest", "joined_at", "left_at")
        read_only_fields = ("group",)

    def _window(self, obj):
        return obj.membership_windows.order_by("joined_at").first()

    def get_joined_at(self, obj):
        w = self._window(obj)
        return w.joined_at.isoformat() if w and w.joined_at else None

    def get_left_at(self, obj):
        w = self._window(obj)
        return w.left_at.isoformat() if w and w.left_at else None


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


class ExpenseCreateSerializer(serializers.Serializer):
    """Input for manually adding an expense (splits are computed server-side)."""

    group = serializers.PrimaryKeyRelatedField(queryset=Group.objects.all())
    date = serializers.DateField()
    description = serializers.CharField(max_length=255)
    paid_by = serializers.IntegerField()
    amount_original = serializers.DecimalField(max_digits=12, decimal_places=4)
    currency = serializers.CharField(max_length=3, default="INR")
    split_type = serializers.ChoiceField(
        choices=["equal", "unequal", "percentage", "share"]
    )
    participants = serializers.ListField(
        child=serializers.IntegerField(), required=False, default=list
    )
    # member_id -> value (percent / ratio / exact INR amount)
    details = serializers.DictField(
        child=serializers.DecimalField(max_digits=12, decimal_places=4),
        required=False,
        default=dict,
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

    def validate(self, data):
        group = data["group"]
        for role in ("from_member", "to_member"):
            if data[role].group_id != group.id:
                raise serializers.ValidationError(
                    f"{role} must belong to the group"
                )
        if data["from_member"] == data["to_member"]:
            raise serializers.ValidationError("payer and payee must differ")
        if data["amount_inr"] <= 0:
            raise serializers.ValidationError("amount must be positive")
        return data
