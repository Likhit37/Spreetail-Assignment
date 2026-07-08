from rest_framework.routers import DefaultRouter

from .views import (
    ExpenseViewSet,
    GroupViewSet,
    MemberViewSet,
    SettlementViewSet,
)

router = DefaultRouter()
router.register("groups", GroupViewSet, basename="group")
router.register("members", MemberViewSet, basename="member")
router.register("expenses", ExpenseViewSet, basename="expense")
router.register("settlements", SettlementViewSet, basename="settlement")

urlpatterns = router.urls
