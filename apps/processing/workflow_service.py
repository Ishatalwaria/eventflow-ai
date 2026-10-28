import logging
import time
from dataclasses import dataclass
from typing import Protocol

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.workflows.models import Workflow, WorkflowAttempt

from .contracts import validate_workflow_task
from .models import OutboxMessage, ProcessingLog
from .topology import LIFECYCLE_TOPIC

logger = logging.getLogger(__name__)
STAGE = "order_validation"
TERMINAL_STATES = {
    Workflow.State.SUCCEEDED,
    Workflow.State.FAILED,
    Workflow.State.DEAD_LETTERED,
}
ALLOWED_TRANSITIONS = {
    Workflow.State.RECEIVED: {Workflow.State.PROCESSING},
    Workflow.State.RETRY_WAIT: {Workflow.State.PROCESSING},
    Workflow.State.PROCESSING: {
        Workflow.State.SUCCEEDED,
        Workflow.State.RETRY_WAIT,
        Workflow.State.FAILED,
        Workflow.State.DEAD_LETTERED,
    },
}


class PermanentProcessingError(Exception):
    def __init__(self, code, detail):
        self.code = code
        self.detail = detail


class TransientProcessingError(Exception):
    def __init__(self, code, detail):
        self.code = code
        self.detail = detail


class InventoryChecker(Protocol):
    def check(self, payload: dict, *, attempt_number: int) -> None: ...


class SimulatedInventoryChecker:
    """Deterministic portfolio behavior; it makes no external inventory mutation."""

    def check(self, payload, *, attempt_number):
        skus = {item["sku"] for item in payload["items"]}
        if any(sku.startswith("OOS-") for sku in skus):
            raise PermanentProcessingError(
                "INSUFFICIENT_INVENTORY", "One or more order items are unavailable."
            )
        if "TEMPORARY-FAIL-FIRST" in skus and attempt_number == 1:
            raise TransientProcessingError(
                "INVENTORY_TEMPORARILY_UNAVAILABLE",
                "Inventory validation is temporarily unavailable.",
            )


@dataclass(frozen=True)
class ProcessingDecision:
    action: str
    task: dict
    retry_index: int | None = None
    error_code: str = ""
    detail: str = ""


def _transition(workflow, target):
    if target not in ALLOWED_TRANSITIONS.get(workflow.state, set()):
        raise ValueError(f"Invalid workflow transition: {workflow.state} -> {target}")
    workflow.state = target
    workflow.updated_at = timezone.now()
    workflow.save(update_fields=["state", "updated_at"])


def _record_lifecycle(workflow, event_type, attempt_number, *, error_code=""):
    recorded_at = timezone.now()
    OutboxMessage.objects.create(
        event=workflow.event,
        topic=LIFECYCLE_TOPIC,
        dedupe_key=f"workflow:{workflow.id}:{attempt_number}:{event_type}",
        payload={
            "event_id": str(workflow.event_id),
            "workflow_id": str(workflow.id),
            "event_type": event_type,
            "schema_version": 1,
            "correlation_id": workflow.event.correlation_id,
            "occurred_at": recorded_at.isoformat(),
            "recorded_at": recorded_at.isoformat(),
            "payload": {
                "state": workflow.state,
                "stage": STAGE,
                "attempt_number": attempt_number,
                "error_code": error_code,
            },
        },
    )


def _write_log(workflow, attempt, message, *, level=ProcessingLog.Level.INFO, error_code=""):
    ProcessingLog.objects.create(
        event=workflow.event,
        workflow=workflow,
        attempt=attempt,
        level=level,
        message=message,
        request_id=workflow.event.request_id,
        correlation_id=workflow.event.correlation_id,
        attributes={"stage": STAGE, "error_code": error_code} if error_code else {"stage": STAGE},
    )


def _decision_for_existing(task, attempt):
    if attempt.outcome == WorkflowAttempt.Outcome.SUCCEEDED:
        return ProcessingDecision("ACK", task)
    if attempt.outcome == WorkflowAttempt.Outcome.RETRYING:
        retry_task = dict(task)
        retry_task["attempt_number"] = attempt.attempt_number + 1
        retry_task["task_id"] = f"{task['workflow_id']}:{STAGE}:{retry_task['attempt_number']}"
        return ProcessingDecision(
            "RETRY",
            retry_task,
            retry_index=attempt.attempt_number - 1,
            error_code=attempt.error_code,
            detail=attempt.error_detail,
        )
    if attempt.outcome in {
        WorkflowAttempt.Outcome.FAILED,
        WorkflowAttempt.Outcome.DEAD_LETTERED,
    }:
        return ProcessingDecision(
            "DEAD_LETTER",
            task,
            error_code=attempt.error_code,
            detail=attempt.error_detail,
        )
    return ProcessingDecision("ACK", task)


def process_workflow_task(task, *, inventory_checker=None):
    """Persist an idempotent stage outcome and lifecycle outbox in one transaction."""
    validate_workflow_task(task)
    inventory_checker = inventory_checker or SimulatedInventoryChecker()
    attempt_number = task["attempt_number"]
    started = time.monotonic()
    with transaction.atomic():
        workflow = (
            Workflow.objects.select_for_update()
            .select_related("event")
            .filter(pk=task["workflow_id"], event_id=task["event_id"])
            .first()
        )
        if workflow is None:
            raise PermanentProcessingError("WORKFLOW_NOT_FOUND", "Task workflow does not exist.")

        previous = WorkflowAttempt.objects.filter(
            workflow=workflow, stage=STAGE, attempt_number=attempt_number
        ).first()
        if previous:
            return _decision_for_existing(task, previous)
        if workflow.state in TERMINAL_STATES:
            return ProcessingDecision("ACK", task)

        now = timezone.now()
        attempt = WorkflowAttempt.objects.create(
            workflow=workflow,
            stage=STAGE,
            attempt_number=attempt_number,
            outcome=WorkflowAttempt.Outcome.STARTED,
            started_at=now,
        )
        _transition(workflow, Workflow.State.PROCESSING)
        workflow.current_stage = STAGE
        workflow.started_at = workflow.started_at or now
        workflow.save(update_fields=["current_stage", "started_at"])
        _write_log(workflow, attempt, "Order validation started")
        _record_lifecycle(workflow, "workflow.processing", attempt_number)

        result_state = Workflow.State.SUCCEEDED
        outcome = WorkflowAttempt.Outcome.SUCCEEDED
        action = "ACK"
        error_code = ""
        detail = ""
        try:
            payload = task["payload"]
            if (
                not isinstance(payload.get("order_id"), str)
                or not isinstance(payload.get("items"), list)
                or not payload["items"]
            ):
                raise PermanentProcessingError("INVALID_ORDER", "Order payload failed validation.")
            inventory_checker.check(payload, attempt_number=attempt_number)
        except PermanentProcessingError as exc:
            result_state = Workflow.State.FAILED
            outcome = WorkflowAttempt.Outcome.FAILED
            action, error_code, detail = "DEAD_LETTER", exc.code, exc.detail
        except TransientProcessingError as exc:
            error_code, detail = exc.code, exc.detail
            if attempt_number >= settings.WORKER_MAX_ATTEMPTS:
                result_state = Workflow.State.DEAD_LETTERED
                outcome = WorkflowAttempt.Outcome.DEAD_LETTERED
                action = "DEAD_LETTER"
            else:
                result_state = Workflow.State.RETRY_WAIT
                outcome = WorkflowAttempt.Outcome.RETRYING
                action = "RETRY"
        except Exception as exc:  # bounded, sanitized retry for unexpected stage errors
            logger.error(
                "Workflow stage error workflow_id=%s attempt=%s error_type=%s",
                workflow.id,
                attempt_number,
                type(exc).__name__,
            )
            error_code = "WORKER_UNEXPECTED_ERROR"
            detail = "An unexpected processing error occurred."
            if attempt_number >= settings.WORKER_MAX_ATTEMPTS:
                result_state = Workflow.State.DEAD_LETTERED
                outcome = WorkflowAttempt.Outcome.DEAD_LETTERED
                action = "DEAD_LETTER"
            else:
                result_state = Workflow.State.RETRY_WAIT
                outcome = WorkflowAttempt.Outcome.RETRYING
                action = "RETRY"

        finished_at = timezone.now()
        attempt.outcome = outcome
        attempt.finished_at = finished_at
        attempt.duration_ms = max(0, int((time.monotonic() - started) * 1000))
        attempt.error_code = error_code
        attempt.error_detail = detail
        attempt.save(
            update_fields=[
                "outcome",
                "finished_at",
                "duration_ms",
                "error_code",
                "error_detail",
            ]
        )
        _transition(workflow, result_state)
        workflow.finished_at = finished_at if result_state in TERMINAL_STATES else None
        workflow.last_error_code = error_code
        workflow.save(update_fields=["finished_at", "last_error_code"])

        event_type = {
            Workflow.State.SUCCEEDED: "workflow.succeeded",
            Workflow.State.RETRY_WAIT: "workflow.retry_wait",
            Workflow.State.FAILED: "workflow.failed",
            Workflow.State.DEAD_LETTERED: "workflow.dead_lettered",
        }[result_state]
        log_level = (
            ProcessingLog.Level.INFO
            if result_state == Workflow.State.SUCCEEDED
            else ProcessingLog.Level.ERROR
        )
        message = "Order processing completed" if action == "ACK" else detail
        _write_log(workflow, attempt, message, level=log_level, error_code=error_code)
        _record_lifecycle(workflow, event_type, attempt_number, error_code=error_code)

        retry_index = attempt_number - 1 if action == "RETRY" else None
        if retry_index is not None and retry_index >= len(settings.WORKER_RETRY_DELAYS_SECONDS):
            raise RuntimeError("Retry schedule is inconsistent with WORKER_MAX_ATTEMPTS")
        retry_task = dict(task)
        if action == "RETRY":
            retry_task["attempt_number"] = attempt_number + 1
            retry_task["task_id"] = f"{workflow.id}:{STAGE}:{attempt_number + 1}"

        return ProcessingDecision(
            action,
            retry_task,
            retry_index=retry_index,
            error_code=error_code,
            detail=detail,
        )
