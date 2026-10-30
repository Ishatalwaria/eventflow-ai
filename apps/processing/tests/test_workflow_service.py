import pytest
from django.test import override_settings

from apps.common.observability import WORKFLOW_ATTEMPTS
from apps.processing.models import OutboxMessage, ProcessingLog
from apps.processing.workflow_service import (
    TransientProcessingError,
    process_workflow_task,
)
from apps.workflows.models import Workflow, WorkflowAttempt

from .helpers import create_workflow

pytestmark = pytest.mark.django_db


class AlwaysTemporaryInventoryFailure:
    def check(self, _payload, *, attempt_number):
        raise TransientProcessingError("INVENTORY_UNAVAILABLE", "Inventory service is unavailable.")


def test_success_records_attempt_logs_and_lifecycle_outbox_atomically():
    event, workflow, task = create_workflow()

    decision = process_workflow_task(task)

    workflow.refresh_from_db()
    attempt = WorkflowAttempt.objects.get(workflow=workflow)
    assert decision.action == "ACK"
    assert workflow.state == Workflow.State.SUCCEEDED
    assert attempt.outcome == WorkflowAttempt.Outcome.SUCCEEDED
    assert attempt.started_at is not None
    assert attempt.finished_at is not None
    assert attempt.duration_ms is not None
    assert ProcessingLog.objects.filter(event=event).count() == 2
    lifecycle = OutboxMessage.objects.filter(event=event, topic="eventflow.workflow.lifecycle.v1")
    assert lifecycle.count() == 2
    assert {row.payload["event_type"] for row in lifecycle} == {
        "workflow.processing",
        "workflow.succeeded",
    }


@pytest.mark.django_db(transaction=True)
def test_successful_attempt_metric_increments_only_after_commit():
    _event, workflow, task = create_workflow()
    counter = WORKFLOW_ATTEMPTS.labels(stage="order_validation", outcome="SUCCEEDED")
    before = counter._value.get()

    process_workflow_task(task)

    assert counter._value.get() == before + 1
    workflow.refresh_from_db()
    assert workflow.state == Workflow.State.SUCCEEDED


def test_transient_failure_retries_once_then_succeeds():
    _event, workflow, task = create_workflow(sku="TEMPORARY-FAIL-FIRST")

    first = process_workflow_task(task)
    workflow.refresh_from_db()
    assert first.action == "RETRY"
    assert first.retry_index == 0
    assert first.task["attempt_number"] == 2
    assert workflow.state == Workflow.State.RETRY_WAIT

    second = process_workflow_task(first.task)
    workflow.refresh_from_db()
    assert second.action == "ACK"
    assert workflow.state == Workflow.State.SUCCEEDED
    assert list(
        WorkflowAttempt.objects.filter(workflow=workflow)
        .order_by("attempt_number")
        .values_list("outcome", flat=True)
    ) == [WorkflowAttempt.Outcome.RETRYING, WorkflowAttempt.Outcome.SUCCEEDED]


def test_permanent_inventory_failure_is_recorded_and_dead_lettered():
    _event, workflow, task = create_workflow(sku="OOS-SKU-1")

    decision = process_workflow_task(task)

    workflow.refresh_from_db()
    attempt = WorkflowAttempt.objects.get(workflow=workflow)
    assert decision.action == "DEAD_LETTER"
    assert decision.error_code == "INSUFFICIENT_INVENTORY"
    assert workflow.state == Workflow.State.FAILED
    assert attempt.outcome == WorkflowAttempt.Outcome.FAILED
    assert "OOS-SKU-1" not in attempt.error_detail


def test_transient_failure_limit_transitions_to_dead_lettered():
    _event, workflow, task = create_workflow()

    with override_settings(WORKER_MAX_ATTEMPTS=3, WORKER_RETRY_DELAYS_SECONDS=(5, 30)):
        first = process_workflow_task(task, inventory_checker=AlwaysTemporaryInventoryFailure())
        second = process_workflow_task(
            first.task, inventory_checker=AlwaysTemporaryInventoryFailure()
        )
        third = process_workflow_task(
            second.task, inventory_checker=AlwaysTemporaryInventoryFailure()
        )

    workflow.refresh_from_db()
    assert first.action == second.action == "RETRY"
    assert second.retry_index == 1
    assert third.action == "DEAD_LETTER"
    assert workflow.state == Workflow.State.DEAD_LETTERED
    assert (
        WorkflowAttempt.objects.filter(
            workflow=workflow, outcome=WorkflowAttempt.Outcome.DEAD_LETTERED
        ).count()
        == 1
    )


def test_duplicate_task_and_crash_after_db_commit_are_idempotent():
    event, workflow, task = create_workflow()

    first = process_workflow_task(task)
    # Simulates a worker dying after the PostgreSQL transaction commits but before basic_ack.
    redelivery = process_workflow_task(task)

    assert first.action == redelivery.action == "ACK"
    assert WorkflowAttempt.objects.filter(workflow=workflow).count() == 1
    assert OutboxMessage.objects.filter(event=event).count() == 2
    assert ProcessingLog.objects.filter(event=event).count() == 2


def test_duplicate_retry_delivery_republishes_the_same_next_task():
    _event, workflow, task = create_workflow(sku="TEMPORARY-FAIL-FIRST")

    first = process_workflow_task(task)
    duplicate = process_workflow_task(task)

    assert first.action == duplicate.action == "RETRY"
    assert first.task["task_id"] == duplicate.task["task_id"]
    assert first.task["attempt_number"] == duplicate.task["attempt_number"] == 2
    assert WorkflowAttempt.objects.filter(workflow=workflow).count() == 1


def test_outbox_failure_rolls_back_workflow_attempt_and_logs(monkeypatch):
    from apps.processing import workflow_service

    _event, workflow, task = create_workflow()

    def fail_create(*_args, **_kwargs):
        raise RuntimeError("database write failed")

    monkeypatch.setattr(workflow_service.OutboxMessage.objects, "create", fail_create)
    with pytest.raises(RuntimeError, match="database write failed"):
        process_workflow_task(task)

    workflow.refresh_from_db()
    assert workflow.state == Workflow.State.RECEIVED
    assert WorkflowAttempt.objects.filter(workflow=workflow).count() == 0
    assert ProcessingLog.objects.filter(workflow=workflow).count() == 0
