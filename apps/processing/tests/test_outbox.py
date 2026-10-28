import uuid
from datetime import timedelta

import pytest
from django.test import override_settings
from django.utils import timezone

from apps.processing import outbox
from apps.processing.adapters.kafka import BrokerUnavailable
from apps.processing.models import OutboxMessage
from apps.processing.outbox import publish_outbox_batch, record_initial_domain_outbox

from .helpers import create_workflow

pytestmark = pytest.mark.django_db


class RecordingPublisher:
    def __init__(self):
        self.messages = []

    def publish(self, **message):
        self.messages.append(message)


class UnavailablePublisher:
    def publish(self, **_message):
        raise BrokerUnavailable("Kafka unavailable")


def test_crash_after_broker_publish_republishes_same_outbox_key(monkeypatch):
    event, _workflow, _task = create_workflow()
    record_initial_domain_outbox(event)
    outbox_message = OutboxMessage.objects.get(event=event)
    publisher = RecordingPublisher()
    original_mark = outbox._mark_published

    def crash_before_mark(*_args):
        raise RuntimeError("simulated publisher crash")

    monkeypatch.setattr(outbox, "_mark_published", crash_before_mark)

    with pytest.raises(RuntimeError, match="simulated publisher crash"):
        publish_outbox_batch(publisher, owner=uuid.uuid4())

    outbox_message.refresh_from_db()
    assert outbox_message.published_at is None
    assert len(publisher.messages) == 1
    first_key = publisher.messages[0]["key"]

    OutboxMessage.objects.filter(pk=outbox_message.pk).update(
        lease_expires_at=timezone.now() - timedelta(seconds=1)
    )
    monkeypatch.setattr(outbox, "_mark_published", original_mark)
    result = publish_outbox_batch(publisher, owner=uuid.uuid4())

    outbox_message.refresh_from_db()
    assert result.published == 1
    assert [message["key"] for message in publisher.messages] == [first_key, first_key]
    assert outbox_message.published_at is not None


def test_outbox_broker_failures_back_off_and_stop_at_attempt_limit():
    event, _workflow, _task = create_workflow()
    record_initial_domain_outbox(event)
    row = OutboxMessage.objects.get(event=event)

    with override_settings(OUTBOX_MAX_ATTEMPTS=2):
        first = publish_outbox_batch(UnavailablePublisher(), owner=uuid.uuid4())
        row.refresh_from_db()
        assert first.retried == 1
        assert row.publish_attempts == 1
        assert row.dead_lettered_at is None

        OutboxMessage.objects.filter(pk=row.pk).update(available_at=timezone.now())
        second = publish_outbox_batch(UnavailablePublisher(), owner=uuid.uuid4())

    row.refresh_from_db()
    assert second.dead_lettered == 1
    assert row.publish_attempts == 2
    assert row.dead_lettered_at is not None
    assert row.last_error_code == "KAFKA_UNAVAILABLE"
