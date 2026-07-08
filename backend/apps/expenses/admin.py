from django.contrib import admin

from .models import (
    Expense,
    ExpenseSplit,
    Group,
    GroupMembership,
    Member,
    MemberAlias,
    Settlement,
)


class ExpenseSplitInline(admin.TabularInline):
    model = ExpenseSplit
    extra = 0


@admin.register(Expense)
class ExpenseAdmin(admin.ModelAdmin):
    list_display = (
        "date",
        "description",
        "paid_by",
        "amount_original",
        "currency",
        "amount_inr",
        "split_type",
    )
    list_filter = ("split_type", "currency", "group")
    inlines = [ExpenseSplitInline]


admin.site.register([Group, Member, MemberAlias, GroupMembership, Settlement])
