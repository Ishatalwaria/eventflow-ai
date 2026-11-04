import uuid
from datetime import UTC, datetime

from django.contrib.auth.hashers import make_password

from apps.common.models import APIClient
from apps.events.models import Event
from apps.workflows.models import Workflow


def create_workflow(*, sku="ITEM-KEYBOARD", on_hand=10, payment_method_token="ok_card"):
    client = APIClient.objects.create(
        name="pipeline-test", secret_hash=make_password("never-used-test-secret")
    )
    from apps.commerce.models import InventoryItem, Product

    product = Product.objects.create(
        client=client,
        sku=sku,
        name=sku,
        unit_price_minor=100,
        active=True,
    )
    InventoryItem.objects.create(product=product, on_hand=on_hand, reserved=0)
    event = Event.objects.create(
        client=client,
        event_type="order.created",
        schema_version=1,
        source="pipeline-test",
        idempotency_key=str(uuid.uuid4()),
        occurred_at=datetime(2026, 10, 27, tzinfo=UTC),
        correlation_id="test-correlation",
        request_id="test-request",
        payload={
            "order_id": "order-test",
            "currency": "INR",
            "total_minor_units": 100,
            "payment_method_token": payment_method_token,
            "items": [{"sku": sku, "quantity": 1}],
        },
    )
    workflow = Workflow.objects.create(event=event, workflow_type="order_fulfillment")
    task = {
        "task_version": 1,
        "task_id": f"{workflow.id}:forward:validate_order:1",
        "workflow_id": str(workflow.id),
        "event_id": str(event.id),
        "event_type": event.event_type,
        "event_schema_version": event.schema_version,
        "workflow_type": "order_fulfillment",
        "stage": "validate_order",
        "direction": "forward",
        "correlation_id": event.correlation_id,
        "request_id": event.request_id,
        "attempt_number": 1,
        "payload": event.payload,
    }
    return event, workflow, task
