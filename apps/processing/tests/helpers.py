import uuid
from datetime import UTC, datetime

from django.contrib.auth.hashers import make_password

from apps.common.models import APIClient
from apps.events.models import Event
from apps.workflows.models import Workflow


def create_workflow(*, sku="SKU-1"):
    client = APIClient.objects.create(
        name="pipeline-test", secret_hash=make_password("never-used-test-secret")
    )
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
            "items": [{"sku": sku, "quantity": 1}],
        },
    )
    workflow = Workflow.objects.create(event=event)
    task = {
        "task_version": 1,
        "task_id": f"{workflow.id}:order_validation:1",
        "workflow_id": str(workflow.id),
        "event_id": str(event.id),
        "event_type": event.event_type,
        "event_schema_version": event.schema_version,
        "correlation_id": event.correlation_id,
        "attempt_number": 1,
        "payload": event.payload,
    }
    return event, workflow, task
