from django.urls import path

from apps.commerce.views import (
    DeadLetterListView,
    InventoryListView,
    OrderDetailView,
    OrderListView,
    PaymentDetailView,
    SeedDemoCatalogView,
    WorkflowCancelView,
    WorkflowReplayView,
    WorkflowRetryView,
)

urlpatterns = [
    path("inventory", InventoryListView.as_view(), name="inventory-list"),
    path("seed-catalog", SeedDemoCatalogView.as_view(), name="seed-catalog"),
    path("orders", OrderListView.as_view(), name="order-list"),
    path("orders/<uuid:order_id>", OrderDetailView.as_view(), name="order-detail"),
    path("payments/<uuid:payment_id>", PaymentDetailView.as_view(), name="payment-detail"),
    path("dead-letters", DeadLetterListView.as_view(), name="dead-letter-list"),
    path("workflows/<uuid:workflow_id>/retry", WorkflowRetryView.as_view(), name="workflow-retry"),
    path(
        "workflows/<uuid:workflow_id>/replay", WorkflowReplayView.as_view(), name="workflow-replay"
    ),
    path(
        "workflows/<uuid:workflow_id>/cancel", WorkflowCancelView.as_view(), name="workflow-cancel"
    ),
]
