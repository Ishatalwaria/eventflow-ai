"""Operator actions that re-enter the saga without bypassing state rules."""

from django.contrib.auth import get_user_model
from django.db import transaction

from apps.processing.contracts import encode_task
from apps.processing.saga.definitions import get_definition
from apps.processing.saga.engine import _build_task, _transition
from apps.workflows.models import OperatorAuditLog, Workflow, WorkflowAttempt

User = get_user_model()


class OperatorActionError(Exception):
    def __init__(self, code, detail, status=409):
        self.code = code
        self.detail = detail
        self.status = status


def _actor(request):
    user = getattr(request, "user", None)
    return user if isinstance(user, User) else None


def _base_task(workflow):
    event = workflow.event
    return {
        "workflow_id": str(workflow.id),
        "event_id": str(event.id),
        "event_type": event.event_type,
        "event_schema_version": event.schema_version,
        "workflow_type": workflow.workflow_type,
        "correlation_id": event.correlation_id,
        "request_id": event.request_id,
        "payload": event.payload,
    }


def _record(workflow, request, action, idempotency_key, detail):
    log, created = OperatorAuditLog.objects.get_or_create(
        idempotency_key=idempotency_key,
        defaults={
            "workflow": workflow,
            "actor": _actor(request),
            "action": action,
            "detail": detail,
        },
    )
    if not created and log.workflow_id != workflow.id:
        raise OperatorActionError(
            "IDEMPOTENCY_CONFLICT", "Idempotency key was used elsewhere.", 409
        )
    return log, created


def publish_operator_task(task):
    encode_task(task)
    from apps.processing.adapters.kafka import BrokerUnavailable
    from apps.processing.adapters.rabbitmq import PikaRabbitAdapter
    from apps.processing.pipeline import rabbit_connection_settings

    adapter = PikaRabbitAdapter(**rabbit_connection_settings())
    try:
        adapter.publish_task(task)
    except BrokerUnavailable as exc:
        raise OperatorActionError("BROKER_UNAVAILABLE", "Task broker is unavailable.", 503) from exc
    finally:
        adapter.close()


@transaction.atomic
def retry_workflow(*, workflow, request, idempotency_key, action=OperatorAuditLog.Action.RETRY):
    workflow = Workflow.objects.select_for_update().get(pk=workflow.pk)
    log, created = _record(
        workflow,
        request,
        action,
        idempotency_key,
        {"state": workflow.state, "stage": workflow.current_stage},
    )
    if not created:
        return workflow, log
    if workflow.state not in {Workflow.State.FAILED, Workflow.State.DEAD_LETTERED}:
        raise OperatorActionError(
            "WORKFLOW_NOT_RETRYABLE",
            "Only failed or dead-lettered workflows can be retried.",
        )
    failed = (
        WorkflowAttempt.objects.filter(
            workflow=workflow,
            direction=WorkflowAttempt.Direction.FORWARD,
            outcome__in=[
                WorkflowAttempt.Outcome.FAILED,
                WorkflowAttempt.Outcome.DEAD_LETTERED,
            ],
        )
        .order_by("-started_at")
        .first()
    )
    stage = failed.stage if failed else get_definition(workflow.workflow_type).first_stage
    attempt_number = (failed.attempt_number + 1) if failed else 1
    _transition(workflow, Workflow.State.QUEUED)
    workflow.finished_at = None
    workflow.current_stage = stage
    workflow.save(update_fields=["finished_at", "current_stage", "updated_at"])
    task = _build_task(
        _base_task(workflow),
        stage=stage,
        direction="forward",
        attempt_number=attempt_number,
    )
    transaction.on_commit(lambda: publish_operator_task(task))
    return workflow, log


@transaction.atomic
def replay_workflow(*, workflow, request, idempotency_key):
    workflow = Workflow.objects.select_for_update().get(pk=workflow.pk)
    if workflow.state != Workflow.State.DEAD_LETTERED:
        raise OperatorActionError(
            "WORKFLOW_NOT_REPLAYABLE",
            "Only dead-lettered workflows can be replayed.",
        )
    return retry_workflow(
        workflow=workflow,
        request=request,
        idempotency_key=idempotency_key,
        action=OperatorAuditLog.Action.REPLAY,
    )


@transaction.atomic
def cancel_workflow(*, workflow, request, idempotency_key):
    workflow = Workflow.objects.select_for_update().select_related("event").get(pk=workflow.pk)
    log, created = _record(
        workflow,
        request,
        OperatorAuditLog.Action.CANCEL,
        idempotency_key,
        {"state": workflow.state, "stage": workflow.current_stage},
    )
    if not created:
        return workflow, log
    if workflow.state in {
        Workflow.State.SUCCEEDED,
        Workflow.State.FAILED,
        Workflow.State.DEAD_LETTERED,
        Workflow.State.CANCELLED,
    }:
        raise OperatorActionError(
            "WORKFLOW_NOT_CANCELLABLE",
            "Terminal workflows cannot be cancelled.",
        )
    definition = get_definition(workflow.workflow_type)
    chain = definition.compensation_chain(workflow.current_stage)
    if workflow.current_stage in definition.stage_names():
        # Include compensation for the current stage when it already succeeded.
        current = next(stage for stage in definition.stages if stage.name == workflow.current_stage)
        succeeded = WorkflowAttempt.objects.filter(
            workflow=workflow,
            stage=workflow.current_stage,
            direction=WorkflowAttempt.Direction.FORWARD,
            outcome=WorkflowAttempt.Outcome.SUCCEEDED,
        ).exists()
        if succeeded and current.compensate and current.compensate not in chain:
            chain = (current.compensate, *chain)
    if not chain:
        _transition(workflow, Workflow.State.CANCELLED)
        workflow.finished_at = workflow.updated_at
        workflow.save(update_fields=["finished_at", "updated_at"])
        return workflow, log
    _transition(workflow, Workflow.State.COMPENSATING)
    task = _build_task(
        _base_task(workflow),
        stage=chain[0],
        direction="compensate",
        attempt_number=1,
        remaining=chain[1:],
        terminal_state=Workflow.State.CANCELLED,
    )
    transaction.on_commit(lambda: publish_operator_task(task))
    return workflow, log
