from dataclasses import dataclass

import pytest

from apps.processing.adapters.kafka import BrokerUnavailable
from apps.processing.pipeline import forward_kafka_record, process_rabbit_delivery
from apps.processing.workflow_service import (
    TransientProcessingError,
    process_workflow_task,
)
from apps.workflows.models import Workflow, WorkflowAttempt

from .helpers import create_workflow

pytestmark = pytest.mark.django_db


@dataclass
class Record:
    topic: str
    partition: int
    offset: int
    value: bytes
    key: bytes | None = None


class FakeKafkaConsumer:
    def __init__(self):
        self.commits = []

    def commit(self, record):
        self.commits.append(record.offset)


class FakeRabbitPublisher:
    def __init__(self):
        self.tasks = []
        self.retries = []
        self.dead_letters = []
        self.invalid = []
        self.fail_task_publish = False

    def publish_task(self, task):
        if self.fail_task_publish:
            raise BrokerUnavailable("Rabbit is unavailable")
        self.tasks.append(task)

    def publish_retry(self, task, retry_index):
        self.retries.append((task, retry_index))

    def publish_dead_letter(self, task, *, error_code, detail):
        self.dead_letters.append((task, error_code, detail))

    def publish_invalid_payload(self, *, message_id, body, error_code):
        self.invalid.append((message_id, body, error_code))


class FakeDelivery:
    def __init__(self, body, *, on_ack=None):
        self.body = body
        self.ack_count = 0
        self.on_ack = on_ack

    def ack(self):
        if self.on_ack:
            self.on_ack()
        self.ack_count += 1


class AlwaysTemporaryInventoryFailure:
    def check(self, _payload, *, attempt_number):
        raise TransientProcessingError("INVENTORY_UNAVAILABLE", "Inventory service is unavailable.")


def domain_record(event, offset=4):
    import json

    envelope = {
        "event_id": str(event.id),
        "event_type": event.event_type,
        "schema_version": event.schema_version,
        "correlation_id": event.correlation_id,
        "occurred_at": event.occurred_at.isoformat(),
        "recorded_at": event.received_at.isoformat(),
        "payload": event.payload,
    }
    return Record(
        "eventflow.domain.events.v1",
        1,
        offset,
        json.dumps(envelope).encode(),
        str(event.id).encode(),
    )


def test_duplicate_kafka_record_creates_duplicate_safe_stable_rabbit_tasks():
    event, _workflow, _task = create_workflow()
    record = domain_record(event)
    rabbit = FakeRabbitPublisher()
    consumer = FakeKafkaConsumer()

    assert (
        forward_kafka_record(record, rabbit_publisher=rabbit, kafka_consumer=consumer)
        == "FORWARDED"
    )
    assert (
        forward_kafka_record(record, rabbit_publisher=rabbit, kafka_consumer=consumer)
        == "FORWARDED"
    )

    assert len(rabbit.tasks) == 2
    assert rabbit.tasks[0]["task_id"] == rabbit.tasks[1]["task_id"]
    assert consumer.commits == [4, 4]


def test_kafka_offset_is_not_committed_when_rabbit_publish_fails():
    event, _workflow, _task = create_workflow()
    rabbit = FakeRabbitPublisher()
    rabbit.fail_task_publish = True
    consumer = FakeKafkaConsumer()

    with pytest.raises(BrokerUnavailable):
        forward_kafka_record(domain_record(event), rabbit_publisher=rabbit, kafka_consumer=consumer)

    assert consumer.commits == []


def test_invalid_kafka_record_is_dead_lettered_before_offset_commit():
    rabbit = FakeRabbitPublisher()
    consumer = FakeKafkaConsumer()
    record = Record("eventflow.domain.events.v1", 0, 9, b"not-json")

    result = forward_kafka_record(record, rabbit_publisher=rabbit, kafka_consumer=consumer)

    assert result == "DEAD_LETTER"
    assert rabbit.invalid == [
        ("kafka:eventflow.domain.events.v1:0:9", b"not-json", "INVALID_DOMAIN_EVENT")
    ]
    assert consumer.commits == [9]


def _assert_stage_recorded(workflow, stage="validate_order"):
    workflow.refresh_from_db()
    assert workflow.current_stage == stage
    assert WorkflowAttempt.objects.filter(
        workflow=workflow, stage=stage, outcome=WorkflowAttempt.Outcome.SUCCEEDED
    ).exists()


def _assert_succeeded(workflow):
    workflow.refresh_from_db()
    assert workflow.state == Workflow.State.SUCCEEDED


def _assert_retry_wait(workflow):
    workflow.refresh_from_db()
    assert workflow.state == Workflow.State.RETRY_WAIT


def test_rabbit_duplicate_task_is_idempotent_and_acknowledged_after_db_commit():
    event, workflow, task = create_workflow()
    import json

    body = json.dumps(task).encode()
    rabbit = FakeRabbitPublisher()
    first_delivery = FakeDelivery(
        body,
        on_ack=lambda: _assert_stage_recorded(workflow, "validate_order"),
    )
    duplicate_delivery = FakeDelivery(
        body, on_ack=lambda: _assert_stage_recorded(workflow, "validate_order")
    )

    assert process_rabbit_delivery(first_delivery, rabbit_publisher=rabbit) == "ENQUEUE_NEXT"
    assert process_rabbit_delivery(duplicate_delivery, rabbit_publisher=rabbit) == "ENQUEUE_NEXT"

    assert first_delivery.ack_count == duplicate_delivery.ack_count == 1
    assert WorkflowAttempt.objects.filter(workflow=workflow).count() == 1
    workflow.refresh_from_db()
    assert workflow.state == Workflow.State.QUEUED


def test_crash_after_recorded_outcome_before_ack_redelivery_does_not_duplicate_attempt():
    event, workflow, task = create_workflow()
    import json

    rabbit = FakeRabbitPublisher()
    body = json.dumps(task).encode()

    def crash_after_commit():
        _assert_stage_recorded(workflow, "validate_order")
        raise RuntimeError("simulated worker crash before ack")

    with pytest.raises(RuntimeError, match="simulated worker crash"):
        process_rabbit_delivery(
            FakeDelivery(body, on_ack=crash_after_commit), rabbit_publisher=rabbit
        )

    retry = FakeDelivery(body, on_ack=lambda: _assert_stage_recorded(workflow, "validate_order"))
    assert process_rabbit_delivery(retry, rabbit_publisher=rabbit) == "ENQUEUE_NEXT"
    assert WorkflowAttempt.objects.filter(workflow=workflow).count() == 1
    workflow.refresh_from_db()
    assert workflow.state == Workflow.State.QUEUED


def test_transient_worker_failure_confirms_retry_before_ack():
    _event, workflow, task = create_workflow(sku="TEMPORARY-FAIL-FIRST", on_hand=5)
    import json

    # First run validate_order to advance to reserve_inventory stage
    validated_decision = process_workflow_task(task)
    assert validated_decision.action == "ENQUEUE_NEXT"
    reserve_task = validated_decision.task

    rabbit = FakeRabbitPublisher()
    body = json.dumps(reserve_task).encode()
    delivery = FakeDelivery(body, on_ack=lambda: _assert_retry_wait(workflow))

    result = process_rabbit_delivery(delivery, rabbit_publisher=rabbit)

    assert result == "RETRY"
    assert delivery.ack_count == 1
    assert rabbit.retries[0][0]["attempt_number"] == 2
    assert rabbit.retries[0][1] == 0


def test_retry_exhaustion_publishes_dead_letter_before_ack():
    import json

    # Use timeout_card which triggers TransientProcessingError during authorize_payment
    _event, workflow, task = create_workflow(payment_method_token="timeout_card", on_hand=5)
    # Stage 1: validate_order
    val_decision = process_workflow_task(task)
    # Stage 2: reserve_inventory
    res_decision = process_workflow_task(val_decision.task)
    current_task = res_decision.task

    rabbit = FakeRabbitPublisher()
    expected_actions = ["RETRY", "RETRY", "DEAD_LETTER"]

    for expected_action in expected_actions:
        delivery = FakeDelivery(json.dumps(current_task).encode())
        result = process_rabbit_delivery(
            delivery,
            rabbit_publisher=rabbit,
        )
        assert result == expected_action
        assert delivery.ack_count == 1
        if expected_action == "RETRY":
            current_task = rabbit.retries[-1][0]

    workflow.refresh_from_db()
    assert workflow.state == Workflow.State.DEAD_LETTERED
    assert len(rabbit.dead_letters) == 1
    dead_letter_task, error_code, _detail = rabbit.dead_letters[0]
    assert dead_letter_task["attempt_number"] == 3
    assert error_code == "PAYMENT_TIMEOUT"


def test_permanent_business_failure_routes_dead_letter_after_persisting_failure():
    import json

    _event, workflow, task = create_workflow(sku="OOS-LOCAL-TEST", on_hand=0)
    # Advance through validate_order to reserve_inventory where insufficient stock is detected
    val_decision = process_workflow_task(task)
    reserve_task = val_decision.task

    rabbit = FakeRabbitPublisher()

    def assert_failed_before_ack():
        workflow.refresh_from_db()
        assert workflow.state == Workflow.State.FAILED
        assert WorkflowAttempt.objects.filter(
            workflow=workflow,
            stage="reserve_inventory",
            outcome=WorkflowAttempt.Outcome.FAILED,
        ).exists()

    delivery = FakeDelivery(json.dumps(reserve_task).encode(), on_ack=assert_failed_before_ack)
    result = process_rabbit_delivery(delivery, rabbit_publisher=rabbit)

    assert result == "DEAD_LETTER"
    assert delivery.ack_count == 1
    assert len(rabbit.dead_letters) == 1
    assert rabbit.dead_letters[0][1] == "INSUFFICIENT_INVENTORY"


def test_pipeline_full_saga_success():
    import json

    _event, workflow, current_task = create_workflow(on_hand=5)
    rabbit = FakeRabbitPublisher()

    for _ in range(10):
        delivery = FakeDelivery(json.dumps(current_task).encode())
        action = process_rabbit_delivery(delivery, rabbit_publisher=rabbit)
        if action == "ACK":
            break
        assert action == "ENQUEUE_NEXT"
        current_task = rabbit.tasks[-1]

    workflow.refresh_from_db()
    assert workflow.state == Workflow.State.SUCCEEDED
    assert workflow.order.status == "COMPLETED"
    assert WorkflowAttempt.objects.filter(workflow=workflow).count() == 6


def test_pipeline_saga_payment_failure_and_compensation():
    import json

    from apps.commerce.models import InventoryItem, InventoryReservation

    _event, workflow, current_task = create_workflow(payment_method_token="fail_card", on_hand=5)
    item = InventoryItem.objects.get(product__sku="ITEM-KEYBOARD")
    assert item.reserved == 0

    rabbit = FakeRabbitPublisher()

    for _ in range(10):
        delivery = FakeDelivery(json.dumps(current_task).encode())
        action = process_rabbit_delivery(delivery, rabbit_publisher=rabbit)
        if action == "ACK":
            break
        assert action in {"ENQUEUE_NEXT", "ENQUEUE_COMPENSATE"}
        current_task = rabbit.tasks[-1]

    workflow.refresh_from_db()
    assert workflow.state == Workflow.State.FAILED
    assert workflow.order.status == "FAILED"
    # Verify reservation was released
    assert not InventoryReservation.objects.filter(workflow=workflow, status="RESERVED").exists()
    assert InventoryReservation.objects.filter(workflow=workflow, status="RELEASED").count() == 1
    item.refresh_from_db()
    assert item.reserved == 0
