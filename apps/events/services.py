import logging
from dataclasses import dataclass

from django.db import IntegrityError, transaction

from apps.processing.models import OutboxMessage, ProcessingLog
from apps.workflows.models import Workflow

from .models import Event

logger = logging.getLogger(__name__)
OUTBOX_TOPIC = "event.accepted.v1"


@dataclass(frozen=True)
class AcceptedEvent:
    event: Event
    workflow: Workflow
    duplicate: bool


def _outbox_envelope(event):
    return {
        "event_id": str(event.id),
        "event_type": event.event_type,
        "schema_version": event.schema_version,
        "source": event.source,
        "idempotency_key": event.idempotency_key,
        "occurred_at": event.occurred_at.isoformat(),
        "correlation_id": event.correlation_id,
        "payload": event.payload,
    }


def _create_one(*, client, envelope, request_id):
    try:
        # A savepoint keeps the outer batch transaction usable after a uniqueness race.
        with transaction.atomic():
            event = Event.objects.create(
                client=client,
                event_type=envelope["event_type"],
                schema_version=envelope["schema_version"],
                source=envelope["source"],
                idempotency_key=envelope["idempotency_key"],
                occurred_at=envelope["occurred_at"],
                correlation_id=envelope["correlation_id"],
                request_id=request_id,
                payload=envelope["payload"],
            )
            workflow = Workflow.objects.create(event=event)
            OutboxMessage.objects.create(
                event=event,
                topic=OUTBOX_TOPIC,
                payload=_outbox_envelope(event),
            )
            ProcessingLog.objects.create(
                event=event,
                workflow=workflow,
                message="Event accepted",
                request_id=request_id,
                correlation_id=event.correlation_id,
                attributes={"workflow_state": workflow.state},
            )
    except IntegrityError:
        existing = (
            Event.objects.select_related("workflow")
            .filter(
                client=client,
                source=envelope["source"],
                idempotency_key=envelope["idempotency_key"],
            )
            .first()
        )
        if existing is None:
            raise
        return AcceptedEvent(event=existing, workflow=existing.workflow, duplicate=True)

    logger.info(
        "Event accepted event_id=%s workflow_id=%s request_id=%s correlation_id=%s",
        event.id,
        workflow.id,
        request_id,
        event.correlation_id,
    )
    return AcceptedEvent(event=event, workflow=workflow, duplicate=False)


@transaction.atomic
def accept_events(*, client, envelopes, request_id):
    """Accept a validated batch atomically; no broker publication happens here."""
    return [
        _create_one(client=client, envelope=envelope, request_id=request_id)
        for envelope in envelopes
    ]
