import uuid

import pytest
from apps.commerce.models import InventoryReservation, ReplenishmentRequest
from apps.processing.saga.engine import process_workflow_task as run_stage
from apps.processing.tests.helpers import create_workflow
from apps.processing.workflow_service import process_workflow_task
from apps.workflows.models import OperatorAuditLog, Workflow, WorkflowAttempt
from rest_framework.test import APIClient

pytestmark = pytest.mark.django_db


def _client_for(owner):
    api = APIClient()
    api.force_authenticate(user=owner)
    return api


@pytest.fixture
def owner(django_user_model):
    return django_user_model.objects.create_user(
        username="ops@example.com", email="ops@example.com", password="ValidPassword123!"
    )


def test_retry_requires_authentication():
    response = APIClient().post(
        f"/api/v1/workflows/{uuid.uuid4()}/retry",
        HTTP_IDEMPOTENCY_KEY="retry-1",
    )
    assert response.status_code in {401, 403}


def test_retry_failed_payment_workflow_is_audited(owner):
    _event, workflow, task = create_workflow(payment_method_token="fail_card", on_hand=2)
    workflow.event.client.owner = owner
    workflow.event.client.save(update_fields=["owner"])
    current = task
    for _ in range(8):
        decision = process_workflow_task(current)
        if decision.action == "ACK":
            break
        current = decision.task
    workflow.refresh_from_db()
    assert workflow.state == Workflow.State.FAILED
    api = _client_for(owner)
    response = api.post(
        f"/api/v1/workflows/{workflow.id}/retry",
        HTTP_IDEMPOTENCY_KEY="retry-payment-1",
    )
    assert response.status_code == 200
    workflow.refresh_from_db()
    assert workflow.state == Workflow.State.QUEUED
    assert OperatorAuditLog.objects.filter(workflow=workflow, action="retry").count() == 1
    again = api.post(
        f"/api/v1/workflows/{workflow.id}/retry",
        HTTP_IDEMPOTENCY_KEY="retry-payment-1",
    )
    assert again.status_code == 200
    assert OperatorAuditLog.objects.filter(workflow=workflow).count() == 1


def test_cancel_active_workflow_releases_reservation(owner):
    _event, workflow, task = create_workflow(on_hand=3)
    workflow.event.client.owner = owner
    workflow.event.client.save(update_fields=["owner"])
    validated = process_workflow_task(task)
    process_workflow_task(validated.task)
    workflow.refresh_from_db()
    assert InventoryReservation.objects.filter(workflow=workflow, status="RESERVED").exists()
    api = _client_for(owner)
    response = api.post(
        f"/api/v1/workflows/{workflow.id}/cancel",
        HTTP_IDEMPOTENCY_KEY="cancel-1",
    )
    assert response.status_code == 200
    workflow.refresh_from_db()
    assert workflow.state == Workflow.State.COMPENSATING
    compensate = {
        "task_version": 1,
        "task_id": f"{workflow.id}:compensate:release_inventory:1",
        "workflow_id": str(workflow.id),
        "event_id": str(workflow.event_id),
        "event_type": "order.created",
        "event_schema_version": 1,
        "workflow_type": "order_fulfillment",
        "stage": "release_inventory",
        "direction": "compensate",
        "correlation_id": workflow.event.correlation_id,
        "request_id": workflow.event.request_id,
        "attempt_number": 1,
        "payload": workflow.event.payload,
        "remaining_compensations": [],
        "terminal_state": "CANCELLED",
    }
    decision = run_stage(compensate)
    workflow.refresh_from_db()
    assert decision.action == "ACK"
    assert workflow.state == Workflow.State.CANCELLED
    assert InventoryReservation.objects.filter(workflow=workflow, status="RELEASED").count() == 1


def test_replenishment_workflow_increases_stock():
    from datetime import UTC, datetime

    from apps.commerce.models import InventoryItem, Product
    from apps.common.models import APIClient as MachineClient
    from apps.events.models import Event
    from django.contrib.auth.hashers import make_password

    client = MachineClient.objects.create(name="replenish", secret_hash=make_password("x"))
    product = Product.objects.create(
        client=client, sku="ITEM-KEYBOARD", name="Keyboard", active=True
    )
    InventoryItem.objects.create(product=product, on_hand=1, reserved=0)
    event = Event.objects.create(
        client=client,
        event_type="inventory.replenishment.requested",
        schema_version=1,
        source="ops",
        idempotency_key="replenish-1",
        occurred_at=datetime(2026, 11, 3, tzinfo=UTC),
        correlation_id="replenish-corr",
        request_id="replenish-req",
        payload={"sku": "ITEM-KEYBOARD", "quantity": 4, "approval_token": "approve"},
    )
    workflow = Workflow.objects.create(event=event, workflow_type="inventory_replenishment")
    task = {
        "task_version": 1,
        "task_id": f"{workflow.id}:forward:validate_replenishment:1",
        "workflow_id": str(workflow.id),
        "event_id": str(event.id),
        "event_type": event.event_type,
        "event_schema_version": 1,
        "workflow_type": "inventory_replenishment",
        "stage": "validate_replenishment",
        "direction": "forward",
        "correlation_id": event.correlation_id,
        "request_id": event.request_id,
        "attempt_number": 1,
        "payload": event.payload,
    }
    current = task
    for _ in range(6):
        decision = run_stage(current)
        if decision.action == "ACK":
            break
        current = decision.task
    workflow.refresh_from_db()
    product.inventory.refresh_from_db()
    assert workflow.state == Workflow.State.SUCCEEDED
    assert product.inventory.on_hand == 5
    assert ReplenishmentRequest.objects.get(workflow=workflow).status == "APPLIED"
    assert WorkflowAttempt.objects.filter(workflow=workflow, outcome="SUCCEEDED").count() == 4
