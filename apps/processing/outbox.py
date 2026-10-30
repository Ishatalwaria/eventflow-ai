import uuid
from dataclasses import dataclass
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.common.observability import (
    OUTBOX_OLDEST_AGE,
    OUTBOX_PUBLISHES,
    OUTBOX_UNPUBLISHED,
    bind_log_context,
)
from apps.events.models import Event

from .adapters.kafka import BrokerUnavailable
from .contracts import ContractError, encode_message
from .models import OutboxMessage
from .topology import DOMAIN_TOPIC, LIFECYCLE_TOPIC

PUBLISH_TIMEOUT_SECONDS = 10.0


@dataclass(frozen=True)
class PublishSummary:
    claimed: int
    published: int
    retried: int
    dead_lettered: int


def claim_outbox_messages(*, owner, batch_size=25, now=None):
    """Lease ready rows in a short transaction; callers publish after commit."""
    now = now or timezone.now()
    if not 1 <= batch_size <= 100:
        raise ValueError("batch_size must be between 1 and 100")
    available_lease = Q(lease_expires_at__isnull=True) | Q(lease_expires_at__lte=now)
    with transaction.atomic():
        rows = list(
            OutboxMessage.objects.select_for_update(skip_locked=True)
            .filter(
                published_at__isnull=True,
                dead_lettered_at__isnull=True,
                available_at__lte=now,
            )
            .filter(available_lease)
            .order_by("created_at", "id")[:batch_size]
        )
        lease_until = now + timedelta(seconds=settings.OUTBOX_LEASE_SECONDS)
        for row in rows:
            row.lease_owner = owner
            row.lease_expires_at = lease_until
        OutboxMessage.objects.bulk_update(rows, ["lease_owner", "lease_expires_at"])
    return rows


def _encoded_payload(message):
    if message.topic == DOMAIN_TOPIC:
        return encode_message(message.payload)
    if message.topic == LIFECYCLE_TOPIC:
        return encode_message(message.payload, lifecycle=True)
    raise ContractError("Outbox row has an unsupported topic.")


def _mark_published(message, owner):
    return OutboxMessage.objects.filter(pk=message.pk, lease_owner=owner).update(
        published_at=timezone.now(),
        publish_attempts=message.publish_attempts + 1,
        lease_owner=None,
        lease_expires_at=None,
        last_error_code="",
        last_error_detail="",
    )


def _record_failure(message, owner, *, error_code, detail, permanent=False):
    attempts = message.publish_attempts + 1
    exhausted = attempts >= settings.OUTBOX_MAX_ATTEMPTS
    dead_lettered = permanent or exhausted
    delay = min(
        settings.OUTBOX_RETRY_BASE_SECONDS * 2 ** min(max(attempts - 1, 0), 10),
        settings.OUTBOX_RETRY_MAX_SECONDS,
    )
    return OutboxMessage.objects.filter(pk=message.pk, lease_owner=owner).update(
        publish_attempts=attempts,
        available_at=timezone.now() + timedelta(seconds=delay),
        dead_lettered_at=timezone.now() if dead_lettered else None,
        lease_owner=None,
        lease_expires_at=None,
        last_error_code=error_code[:100],
        last_error_detail=detail[:500],
    ), dead_lettered


def publish_outbox_batch(publisher, *, batch_size=25, owner=None):
    owner = owner or uuid.uuid4()
    messages = claim_outbox_messages(owner=owner, batch_size=batch_size)
    published = retried = dead_lettered = 0
    for message in messages:
        with bind_log_context(
            event_id=message.payload.get("event_id"),
            workflow_id=message.payload.get("workflow_id"),
            correlation_id=message.payload.get("correlation_id"),
            request_id=message.payload.get("request_id"),
            trace_id=message.payload.get("request_id"),
        ):
            try:
                encoded = _encoded_payload(message)
                publisher.publish(
                    topic=message.topic,
                    key=str(message.payload["event_id"]).encode("ascii"),
                    value=encoded,
                    timeout=PUBLISH_TIMEOUT_SECONDS,
                )
            except ContractError:
                _changed, terminal = _record_failure(
                    message,
                    owner,
                    error_code="OUTBOX_INVALID_MESSAGE",
                    detail="Outbox message failed contract validation.",
                    permanent=True,
                )
                OUTBOX_PUBLISHES.labels(
                    result="dead_lettered", error_code="OUTBOX_INVALID_MESSAGE"
                ).inc()
                dead_lettered += int(terminal)
                continue
            except BrokerUnavailable:
                _changed, terminal = _record_failure(
                    message,
                    owner,
                    error_code="KAFKA_UNAVAILABLE",
                    detail="Kafka did not confirm the outbox publication.",
                )
                result = "dead_lettered" if terminal else "retry"
                OUTBOX_PUBLISHES.labels(result=result, error_code="KAFKA_UNAVAILABLE").inc()
                dead_lettered += int(terminal)
                retried += int(not terminal)
                continue

            if _mark_published(message, owner) == 1:
                OUTBOX_PUBLISHES.labels(result="published", error_code="").inc()
                published += 1

    return PublishSummary(
        claimed=len(messages),
        published=published,
        retried=retried,
        dead_lettered=dead_lettered,
    )


def record_initial_domain_outbox(event: Event, *, workflow_id=None):
    """Create the versioned initial domain event inside event acceptance's transaction."""
    recorded_at = timezone.now()
    OutboxMessage.objects.create(
        event=event,
        topic=DOMAIN_TOPIC,
        dedupe_key=f"event:{event.id}:domain.v1",
        payload={
            "event_id": str(event.id),
            "request_id": event.request_id,
            **({"workflow_id": str(workflow_id)} if workflow_id else {}),
            "event_type": event.event_type,
            "schema_version": event.schema_version,
            "correlation_id": event.correlation_id,
            "occurred_at": event.occurred_at.isoformat(),
            "recorded_at": recorded_at.isoformat(),
            "payload": event.payload,
        },
    )


def oldest_unpublished_summary():
    pending = OutboxMessage.objects.filter(published_at__isnull=True)
    oldest = pending.order_by("created_at").values_list("created_at", flat=True).first()
    age_seconds = max(0, int((timezone.now() - oldest).total_seconds())) if oldest else None
    summary = {
        "unpublished_count": pending.count(),
        "dead_lettered_count": pending.filter(dead_lettered_at__isnull=False).count(),
        "oldest_unpublished_age_seconds": age_seconds,
    }
    OUTBOX_UNPUBLISHED.set(summary["unpublished_count"])
    OUTBOX_OLDEST_AGE.set(age_seconds if age_seconds is not None else 0)
    return summary
