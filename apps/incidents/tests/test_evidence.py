from datetime import timedelta

import pytest
from django.utils import timezone

from apps.common.models import APIClient
from apps.events.models import Event
from apps.incidents.evidence import MAX_EVIDENCE_ITEMS, build_workflow_evidence
from apps.processing.models import ProcessingLog
from apps.workflows.models import Workflow, WorkflowAttempt

pytestmark = pytest.mark.django_db


def create_failed_workflow(*, log_message="Order processing failed"):
    client = APIClient.objects.create(name="evidence-test", secret_hash="not-used")
    now = timezone.now()
    event = Event.objects.create(
        client=client,
        event_type="order.created",
        schema_version=1,
        source="evidence-test",
        idempotency_key="evidence-test-1",
        occurred_at=now - timedelta(minutes=2),
        correlation_id="corr-evidence-1",
        request_id="request-evidence-1",
        payload={"customer_email": "should-not-be-in-evidence@example.com"},
    )
    workflow = Workflow.objects.create(
        event=event,
        state=Workflow.State.FAILED,
        current_stage="order_validation",
        last_error_code="INVALID_ORDER",
        finished_at=now,
    )
    attempt = WorkflowAttempt.objects.create(
        workflow=workflow,
        stage="order_validation",
        attempt_number=1,
        outcome=WorkflowAttempt.Outcome.FAILED,
        started_at=now - timedelta(minutes=1),
        finished_at=now,
        duration_ms=42,
        error_code="INVALID_ORDER",
        error_detail="bad value for customer_email=test@example.com password=hunter2",
    )
    log = ProcessingLog.objects.create(
        event=event,
        workflow=workflow,
        attempt=attempt,
        level=ProcessingLog.Level.ERROR,
        message=log_message,
        request_id=event.request_id,
        correlation_id=event.correlation_id,
        attributes={
            "stage": "order_validation",
            "error_code": "INVALID_ORDER",
            "raw_payload": event.payload,
        },
    )
    return workflow, event, attempt, log, now


def test_builder_uses_stable_ids_redacts_and_excludes_event_payload():
    workflow, event, attempt, log, now = create_failed_workflow(
        log_message="Authorization: Bearer super-secret api_key=abc123 contact jane@example.com"
    )
    first = build_workflow_evidence(workflow)
    second = build_workflow_evidence(workflow)

    assert first == second
    assert first["evidence_hash"] == second["evidence_hash"]
    ids = {item["id"] for item in first["evidence"]}
    assert f"workflow:{workflow.id}" in ids
    assert f"event:{event.id}" in ids
    assert f"attempt:{attempt.id}" in ids
    assert f"log:{log.id}" in ids
    serialized = str(first)
    assert event.payload["customer_email"] not in serialized
    assert "super-secret" not in serialized
    assert "abc123" not in serialized
    assert "jane@example.com" not in serialized
    assert "[REDACTED]" in serialized
    log_item = next(item for item in first["evidence"] if item["id"] == f"log:{log.id}")
    assert "raw_payload" not in log_item["data"]["attributes"]
    assert len(first["evidence"]) <= MAX_EVIDENCE_ITEMS


def test_builder_redacts_personal_data_from_correlation_and_error_fields():
    workflow, event, attempt, _log, _now = create_failed_workflow()
    event.correlation_id = "person@example.com"
    event.save(update_fields=["correlation_id"])
    attempt.error_code = "INVALID_person@example.com"
    attempt.save(update_fields=["error_code"])

    serialized = str(build_workflow_evidence(workflow))

    assert "person@example.com" not in serialized
    assert "[REDACTED_EMAIL]" in serialized


def test_builder_excludes_logs_outside_the_workflow_time_window():
    workflow, _event, _attempt, old_log, now = create_failed_workflow()
    old_log.created_at = now - timedelta(days=3)
    old_log.save(update_fields=["created_at"])

    bundle = build_workflow_evidence(workflow)

    assert f"log:{old_log.id}" not in {item["id"] for item in bundle["evidence"]}


def test_builder_excludes_attempts_outside_the_workflow_time_window():
    workflow, _event, old_attempt, _log, now = create_failed_workflow()
    old_attempt.started_at = now - timedelta(days=3)
    old_attempt.save(update_fields=["started_at"])

    bundle = build_workflow_evidence(workflow)

    assert f"attempt:{old_attempt.id}" not in {item["id"] for item in bundle["evidence"]}


def test_builder_bounds_attempts_and_logs():
    workflow, event, _attempt, _log, now = create_failed_workflow()
    for number in range(2, 25):
        WorkflowAttempt.objects.create(
            workflow=workflow,
            stage="order_validation",
            attempt_number=number,
            outcome=WorkflowAttempt.Outcome.FAILED,
            started_at=now,
            finished_at=now,
            error_code="INVALID_ORDER",
        )
    for number in range(25):
        ProcessingLog.objects.create(
            event=event,
            workflow=workflow,
            level=ProcessingLog.Level.ERROR,
            message=f"Failure {number}",
            request_id=event.request_id,
            correlation_id=event.correlation_id,
        )

    bundle = build_workflow_evidence(workflow)

    assert bundle["truncated"] is True
    assert len(bundle["evidence"]) <= MAX_EVIDENCE_ITEMS
    assert sum(item["kind"] == "workflow_attempt" for item in bundle["evidence"]) == 20
