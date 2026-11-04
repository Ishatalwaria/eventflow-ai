"""Orchestration saga engine: one stage task in, next stage or compensation out."""

import logging
import time
from dataclasses import dataclass

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.commerce.stages import get_handler
from apps.common.observability import (
    WORKFLOW_ATTEMPTS,
    WORKFLOW_DEAD_LETTERS,
    WORKFLOW_RETRIES,
    bind_log_context,
)
from apps.processing.errors import PermanentProcessingError, TransientProcessingError
from apps.processing.models import OutboxMessage, ProcessingLog
from apps.processing.saga.definitions import get_definition
from apps.processing.topology import LIFECYCLE_TOPIC
from apps.workflows.models import Workflow, WorkflowAttempt

logger = logging.getLogger(__name__)

TERMINAL_STATES = {
    Workflow.State.SUCCEEDED,
    Workflow.State.FAILED,
    Workflow.State.DEAD_LETTERED,
    Workflow.State.CANCELLED,
}

ALLOWED_TRANSITIONS = {
    Workflow.State.RECEIVED: {
        Workflow.State.PROCESSING,
        Workflow.State.COMPENSATING,
        Workflow.State.CANCELLED,
    },
    Workflow.State.QUEUED: {
        Workflow.State.PROCESSING,
        Workflow.State.COMPENSATING,
        Workflow.State.CANCELLED,
    },
    Workflow.State.RETRY_WAIT: {Workflow.State.PROCESSING, Workflow.State.COMPENSATING},
    Workflow.State.PROCESSING: {
        Workflow.State.QUEUED,
        Workflow.State.PROCESSING,
        Workflow.State.RETRY_WAIT,
        Workflow.State.COMPENSATING,
        Workflow.State.SUCCEEDED,
        Workflow.State.FAILED,
        Workflow.State.DEAD_LETTERED,
        Workflow.State.CANCELLED,
    },
    Workflow.State.COMPENSATING: {
        Workflow.State.COMPENSATING,
        Workflow.State.RETRY_WAIT,
        Workflow.State.FAILED,
        Workflow.State.CANCELLED,
        Workflow.State.DEAD_LETTERED,
    },
    Workflow.State.FAILED: {Workflow.State.QUEUED, Workflow.State.PROCESSING},
    Workflow.State.DEAD_LETTERED: {Workflow.State.QUEUED, Workflow.State.PROCESSING},
}


@dataclass(frozen=True)
class ProcessingDecision:
    action: str
    task: dict
    retry_index: int | None = None
    error_code: str = ""
    detail: str = ""


def _transition(workflow, target):
    if workflow.state == target:
        workflow.updated_at = timezone.now()
        workflow.save(update_fields=["updated_at"])
        return
    if target not in ALLOWED_TRANSITIONS.get(workflow.state, set()):
        raise ValueError(f"Invalid workflow transition: {workflow.state} -> {target}")
    workflow.state = target
    workflow.updated_at = timezone.now()
    workflow.save(update_fields=["state", "updated_at"])


def _build_task(base, *, stage, direction, attempt_number, remaining=None, terminal_state=None):
    task = {
        "task_version": 1,
        "task_id": f"{base['workflow_id']}:{direction}:{stage}:{attempt_number}",
        "workflow_id": base["workflow_id"],
        "event_id": base["event_id"],
        "event_type": base["event_type"],
        "event_schema_version": base.get("event_schema_version", 1),
        "workflow_type": base["workflow_type"],
        "stage": stage,
        "direction": direction,
        "correlation_id": base["correlation_id"],
        "attempt_number": attempt_number,
        "payload": base["payload"],
    }
    if base.get("request_id"):
        task["request_id"] = base["request_id"]
    if remaining:
        task["remaining_compensations"] = list(remaining)
    if terminal_state:
        task["terminal_state"] = terminal_state
    elif base.get("terminal_state") and direction == "compensate":
        task["terminal_state"] = base["terminal_state"]
    return task


def _record_lifecycle(
    workflow,
    event_type,
    *,
    stage,
    direction,
    attempt_number,
    phase,
    error_code="",
    duration_ms=None,
):
    recorded_at = timezone.now()
    OutboxMessage.objects.create(
        event=workflow.event,
        topic=LIFECYCLE_TOPIC,
        dedupe_key=(
            f"workflow:{workflow.id}:{direction}:{stage}:{attempt_number}:{event_type}:{phase}"
        ),
        payload={
            "event_id": str(workflow.event_id),
            "request_id": workflow.event.request_id,
            "workflow_id": str(workflow.id),
            "event_type": event_type,
            "schema_version": 1,
            "correlation_id": workflow.event.correlation_id,
            "occurred_at": recorded_at.isoformat(),
            "recorded_at": recorded_at.isoformat(),
            "payload": {
                "state": workflow.state,
                "stage": stage,
                "direction": direction,
                "attempt_number": attempt_number,
                "error_code": error_code,
                "duration_ms": duration_ms,
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
        attributes={
            "stage": attempt.stage,
            "direction": attempt.direction,
            **({"error_code": error_code} if error_code else {}),
        },
    )


def _decision_for_existing(task, attempt, workflow):
    definition = get_definition(workflow.workflow_type)
    if attempt.outcome == WorkflowAttempt.Outcome.SUCCEEDED:
        if attempt.direction == WorkflowAttempt.Direction.COMPENSATE:
            remaining = list(task.get("remaining_compensations") or [])
            if remaining:
                nxt = remaining[0]
                return ProcessingDecision(
                    "ENQUEUE_COMPENSATE",
                    _build_task(
                        task,
                        stage=nxt,
                        direction="compensate",
                        attempt_number=1,
                        remaining=remaining[1:],
                        terminal_state=task.get("terminal_state") or Workflow.State.FAILED,
                    ),
                )
            return ProcessingDecision("ACK", task)
        nxt = definition.next_stage(attempt.stage)
        if nxt:
            return ProcessingDecision(
                "ENQUEUE_NEXT",
                _build_task(task, stage=nxt, direction="forward", attempt_number=1),
            )
        return ProcessingDecision("ACK", task)
    if attempt.outcome == WorkflowAttempt.Outcome.RETRYING:
        retry_task = _build_task(
            task,
            stage=attempt.stage,
            direction=attempt.direction,
            attempt_number=attempt.attempt_number + 1,
            remaining=task.get("remaining_compensations"),
            terminal_state=task.get("terminal_state"),
        )
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
        if (
            attempt.direction == WorkflowAttempt.Direction.FORWARD
            and workflow.state == Workflow.State.COMPENSATING
        ):
            chain = definition.compensation_chain(attempt.stage)
            if chain:
                return ProcessingDecision(
                    "ENQUEUE_COMPENSATE",
                    _build_task(
                        task,
                        stage=chain[0],
                        direction="compensate",
                        attempt_number=1,
                        remaining=chain[1:],
                        terminal_state=task.get("terminal_state") or Workflow.State.FAILED,
                    ),
                    error_code=attempt.error_code,
                    detail=attempt.error_detail,
                )
        return ProcessingDecision(
            "DEAD_LETTER",
            task,
            error_code=attempt.error_code,
            detail=attempt.error_detail,
        )
    return ProcessingDecision("ACK", task)


def process_workflow_task(task, *, inventory_checker=None):
    """Persist one saga stage. inventory_checker is ignored; inventory is transactional."""
    del inventory_checker
    from apps.processing.contracts import validate_workflow_task

    validate_workflow_task(task)
    with bind_log_context(
        request_id=task.get("request_id"),
        trace_id=task.get("request_id"),
        event_id=task.get("event_id"),
        workflow_id=task.get("workflow_id"),
        correlation_id=task.get("correlation_id"),
    ):
        return _process_validated_task(task)


def _process_validated_task(task):
    stage = task["stage"]
    direction = task["direction"]
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
        if workflow.workflow_type != task["workflow_type"]:
            raise PermanentProcessingError(
                "WORKFLOW_TYPE_MISMATCH", "Task workflow type does not match the workflow."
            )

        previous = WorkflowAttempt.objects.filter(
            workflow=workflow,
            stage=stage,
            direction=direction,
            attempt_number=attempt_number,
        ).first()
        if previous:
            return _decision_for_existing(task, previous, workflow)
        if workflow.state in TERMINAL_STATES and direction == "forward":
            return ProcessingDecision("ACK", task)

        now = timezone.now()
        attempt = WorkflowAttempt.objects.create(
            workflow=workflow,
            stage=stage,
            direction=direction,
            attempt_number=attempt_number,
            outcome=WorkflowAttempt.Outcome.STARTED,
            started_at=now,
        )
        entering = (
            Workflow.State.COMPENSATING if direction == "compensate" else Workflow.State.PROCESSING
        )
        if workflow.state != entering:
            _transition(workflow, entering)
        workflow.current_stage = stage
        workflow.started_at = workflow.started_at or now
        workflow.save(update_fields=["current_stage", "started_at", "updated_at"])
        _write_log(workflow, attempt, f"Stage {direction}:{stage} started")
        _record_lifecycle(
            workflow,
            "workflow.compensating" if direction == "compensate" else "workflow.processing",
            stage=stage,
            direction=direction,
            attempt_number=attempt_number,
            phase="started",
        )

        handler = get_handler(stage)
        action = "ACK"
        error_code = ""
        detail = ""
        follow_task = task
        try:
            handler(
                workflow=workflow,
                payload=task["payload"],
                attempt_number=attempt_number,
                direction=direction,
            )
            outcome = WorkflowAttempt.Outcome.SUCCEEDED
            definition = get_definition(workflow.workflow_type)
            if direction == "compensate":
                remaining = list(task.get("remaining_compensations") or [])
                if remaining:
                    action = "ENQUEUE_COMPENSATE"
                    follow_task = _build_task(
                        task,
                        stage=remaining[0],
                        direction="compensate",
                        attempt_number=1,
                        remaining=remaining[1:],
                        terminal_state=task.get("terminal_state") or Workflow.State.FAILED,
                    )
                    result_state = Workflow.State.COMPENSATING
                else:
                    action = "ACK"
                    result_state = task.get("terminal_state") or Workflow.State.FAILED
                    if result_state not in {
                        Workflow.State.FAILED,
                        Workflow.State.CANCELLED,
                    }:
                        result_state = Workflow.State.FAILED
            else:
                nxt = definition.next_stage(stage)
                if nxt:
                    action = "ENQUEUE_NEXT"
                    follow_task = _build_task(
                        task, stage=nxt, direction="forward", attempt_number=1
                    )
                    result_state = Workflow.State.QUEUED
                else:
                    action = "ACK"
                    result_state = Workflow.State.SUCCEEDED
        except PermanentProcessingError as exc:
            error_code, detail = exc.code, exc.detail
            outcome = WorkflowAttempt.Outcome.FAILED
            definition = get_definition(workflow.workflow_type)
            chain = (
                definition.compensation_chain(stage)
                if direction == "forward" and definition.compensate_on_permanent_failure
                else ()
            )
            if chain:
                action = "ENQUEUE_COMPENSATE"
                terminal = task.get("terminal_state") or Workflow.State.FAILED
                follow_task = _build_task(
                    task,
                    stage=chain[0],
                    direction="compensate",
                    attempt_number=1,
                    remaining=chain[1:],
                    terminal_state=terminal,
                )
                result_state = Workflow.State.COMPENSATING
            else:
                action = "DEAD_LETTER"
                result_state = (
                    Workflow.State.DEAD_LETTERED
                    if direction == "compensate"
                    else Workflow.State.FAILED
                )
        except TransientProcessingError as exc:
            error_code, detail = exc.code, exc.detail
            if attempt_number >= settings.WORKER_MAX_ATTEMPTS:
                outcome = WorkflowAttempt.Outcome.DEAD_LETTERED
                action = "DEAD_LETTER"
                result_state = Workflow.State.DEAD_LETTERED
            else:
                outcome = WorkflowAttempt.Outcome.RETRYING
                action = "RETRY"
                result_state = Workflow.State.RETRY_WAIT
                follow_task = _build_task(
                    task,
                    stage=stage,
                    direction=direction,
                    attempt_number=attempt_number + 1,
                    remaining=task.get("remaining_compensations"),
                    terminal_state=task.get("terminal_state"),
                )
        except Exception as exc:
            logger.error(
                "Workflow stage error workflow_id=%s stage=%s attempt=%s error_type=%s",
                workflow.id,
                stage,
                attempt_number,
                type(exc).__name__,
            )
            error_code = "WORKER_UNEXPECTED_ERROR"
            detail = "An unexpected processing error occurred."
            if attempt_number >= settings.WORKER_MAX_ATTEMPTS:
                outcome = WorkflowAttempt.Outcome.DEAD_LETTERED
                action = "DEAD_LETTER"
                result_state = Workflow.State.DEAD_LETTERED
            else:
                outcome = WorkflowAttempt.Outcome.RETRYING
                action = "RETRY"
                result_state = Workflow.State.RETRY_WAIT
                follow_task = _build_task(
                    task,
                    stage=stage,
                    direction=direction,
                    attempt_number=attempt_number + 1,
                    remaining=task.get("remaining_compensations"),
                    terminal_state=task.get("terminal_state"),
                )

        finished_at = timezone.now()
        attempt.outcome = outcome
        attempt.finished_at = finished_at
        attempt.duration_ms = max(0, int((time.monotonic() - started) * 1000))
        attempt.error_code = error_code
        attempt.error_detail = detail[:500]
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
        workflow.current_stage = stage
        workflow.save(
            update_fields=["finished_at", "last_error_code", "current_stage", "updated_at"]
        )

        event_type = {
            Workflow.State.SUCCEEDED: "workflow.succeeded",
            Workflow.State.QUEUED: "workflow.processing",
            Workflow.State.RETRY_WAIT: "workflow.retry_wait",
            Workflow.State.COMPENSATING: "workflow.compensating",
            Workflow.State.FAILED: "workflow.failed",
            Workflow.State.CANCELLED: "workflow.failed",
            Workflow.State.DEAD_LETTERED: "workflow.dead_lettered",
        }[result_state]
        log_level = (
            ProcessingLog.Level.INFO
            if outcome == WorkflowAttempt.Outcome.SUCCEEDED
            else ProcessingLog.Level.ERROR
        )
        message = f"Stage {direction}:{stage} completed" if not detail else detail
        _write_log(workflow, attempt, message, level=log_level, error_code=error_code)
        _record_lifecycle(
            workflow,
            event_type,
            stage=stage,
            direction=direction,
            attempt_number=attempt_number,
            phase="finished",
            error_code=error_code,
            duration_ms=attempt.duration_ms,
        )

        retry_index = attempt_number - 1 if action == "RETRY" else None
        if retry_index is not None and retry_index >= len(settings.WORKER_RETRY_DELAYS_SECONDS):
            raise RuntimeError("Retry schedule is inconsistent with WORKER_MAX_ATTEMPTS")

        def record_attempt_metrics():
            WORKFLOW_ATTEMPTS.labels(stage=stage, outcome=outcome).inc()
            if action == "RETRY":
                WORKFLOW_RETRIES.labels(stage=stage).inc()
            if action == "DEAD_LETTER":
                WORKFLOW_DEAD_LETTERS.labels(
                    stage=stage, error_code=error_code or "UNSPECIFIED"
                ).inc()

        transaction.on_commit(record_attempt_metrics)
        return ProcessingDecision(
            action,
            follow_task,
            retry_index=retry_index,
            error_code=error_code,
            detail=detail,
        )
