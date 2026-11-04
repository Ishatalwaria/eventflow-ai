import pytest
from django.test import override_settings

from apps.commerce.models import InventoryItem, InventoryReservation, Order
from apps.common.observability import WORKFLOW_ATTEMPTS
from apps.processing.errors import TransientProcessingError
from apps.processing.models import OutboxMessage, ProcessingLog
from apps.processing.saga import engine
from apps.processing.workflow_service import process_workflow_task
from apps.workflows.models import Workflow, WorkflowAttempt

from .helpers import create_workflow

pytestmark = pytest.mark.django_db


def test_first_stage_enqueues_the_next_stage():
    event, workflow, task = create_workflow()

    decision = process_workflow_task(task)

    workflow.refresh_from_db()
    attempt = WorkflowAttempt.objects.get(workflow=workflow)
    assert decision.action == "ENQUEUE_NEXT"
    assert decision.task["stage"] == "reserve_inventory"
    assert workflow.state == Workflow.State.QUEUED
    assert attempt.stage == "validate_order"
    assert attempt.outcome == WorkflowAttempt.Outcome.SUCCEEDED
    assert Order.objects.filter(workflow=workflow, status=Order.Status.VALIDATED).exists()
    assert ProcessingLog.objects.filter(event=event).count() == 2


@pytest.mark.django_db(transaction=True)
def test_successful_attempt_metric_increments_only_after_commit():
    _event, workflow, task = create_workflow()
    counter = WORKFLOW_ATTEMPTS.labels(stage="validate_order", outcome="SUCCEEDED")
    before = counter._value.get()

    process_workflow_task(task)

    assert counter._value.get() == before + 1
    workflow.refresh_from_db()
    assert workflow.state == Workflow.State.QUEUED


def test_transient_failure_retries_once_then_reserves():
    _event, workflow, task = create_workflow(sku="TEMPORARY-FAIL-FIRST", on_hand=5)
    validated = process_workflow_task(task)
    first = process_workflow_task(validated.task)
    workflow.refresh_from_db()
    assert first.action == "RETRY"
    assert first.task["stage"] == "reserve_inventory"
    assert first.task["attempt_number"] == 2
    assert workflow.state == Workflow.State.RETRY_WAIT

    second = process_workflow_task(first.task)
    workflow.refresh_from_db()
    assert second.action == "ENQUEUE_NEXT"
    assert second.task["stage"] == "authorize_payment"
    assert InventoryReservation.objects.filter(workflow=workflow).count() == 1


def test_permanent_inventory_failure_does_not_reserve_stock():
    _event, workflow, task = create_workflow(sku="OOS-MOUSE", on_hand=0)
    validated = process_workflow_task(task)
    decision = process_workflow_task(validated.task)

    workflow.refresh_from_db()
    assert decision.action == "DEAD_LETTER"
    assert decision.error_code == "INSUFFICIENT_INVENTORY"
    assert workflow.state == Workflow.State.FAILED
    assert InventoryReservation.objects.filter(workflow=workflow).count() == 0
    assert "OOS-MOUSE" not in decision.detail


def test_payment_failure_releases_inventory_exactly_once():
    _event, workflow, task = create_workflow(payment_method_token="fail_card", on_hand=3)
    item = (
        InventoryItem.objects.get(product__sku="ITEM-KEYBOARD")
        if False
        else InventoryItem.objects.get()
    )
    before = item.on_hand
    current = task
    decision = None
    for _ in range(6):
        decision = process_workflow_task(current)
        if decision.action == "ACK":
            break
        current = decision.task
    workflow.refresh_from_db()
    item.refresh_from_db()
    assert workflow.state == Workflow.State.FAILED
    assert item.on_hand == before
    assert item.reserved == 0
    assert (
        InventoryReservation.objects.filter(
            workflow=workflow, status=InventoryReservation.Status.RELEASED
        ).count()
        == 1
    )
    again = process_workflow_task(current)
    item.refresh_from_db()
    assert again.action == "ACK"
    assert item.reserved == 0
    assert (
        InventoryReservation.objects.filter(
            workflow=workflow, status=InventoryReservation.Status.RELEASED
        ).count()
        == 1
    )


def test_happy_path_consumes_stock_once():
    _event, workflow, task = create_workflow(on_hand=4)
    item = InventoryItem.objects.get()
    current = task
    for _ in range(8):
        decision = process_workflow_task(current)
        if decision.action == "ACK" and decision.task["stage"] == "notify":
            break
        current = decision.task
    workflow.refresh_from_db()
    item.refresh_from_db()
    order = Order.objects.get(workflow=workflow)
    assert workflow.state == Workflow.State.SUCCEEDED
    assert order.status == Order.Status.COMPLETED
    assert item.on_hand == 3
    assert item.reserved == 0


def test_duplicate_task_redelivery_does_not_duplicate_stage():
    event, workflow, task = create_workflow()
    first = process_workflow_task(task)
    redelivery = process_workflow_task(task)
    assert first.action == redelivery.action == "ENQUEUE_NEXT"
    assert first.task["task_id"] == redelivery.task["task_id"]
    assert WorkflowAttempt.objects.filter(workflow=workflow).count() == 1
    assert Order.objects.filter(workflow=workflow).count() == 1
    assert ProcessingLog.objects.filter(event=event).count() == 2


@override_settings(WORKER_MAX_ATTEMPTS=2, WORKER_RETRY_DELAYS_SECONDS=(5,))
def test_transient_failure_limit_dead_letters():
    _event, workflow, task = create_workflow()

    def boom(**_kwargs):
        raise TransientProcessingError("INVENTORY_UNAVAILABLE", "Inventory service is unavailable.")

    engine_handlers = engine.get_handler

    def wrapped(stage):
        if stage == "validate_order":
            return boom
        return engine_handlers(stage)

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(engine, "get_handler", wrapped)
    try:
        first = process_workflow_task(task)
        second = process_workflow_task(first.task)
    finally:
        monkeypatch.undo()
    workflow.refresh_from_db()
    assert first.action == "RETRY"
    assert second.action == "DEAD_LETTER"
    assert workflow.state == Workflow.State.DEAD_LETTERED


def test_outbox_failure_rolls_back_workflow_attempt_and_logs(monkeypatch):
    _event, workflow, task = create_workflow()

    def fail_create(*_args, **_kwargs):
        raise RuntimeError("database write failed")

    monkeypatch.setattr(engine.OutboxMessage.objects, "create", fail_create)
    with pytest.raises(RuntimeError, match="database write failed"):
        process_workflow_task(task)

    workflow.refresh_from_db()
    assert workflow.state == Workflow.State.RECEIVED
    assert WorkflowAttempt.objects.filter(workflow=workflow).count() == 0
    assert ProcessingLog.objects.filter(workflow=workflow).count() == 0
    assert OutboxMessage.objects.filter(event=_event).count() == 0
