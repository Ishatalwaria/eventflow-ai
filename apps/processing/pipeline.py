import hashlib

from django.conf import settings

from apps.common.observability import (
    BROKER_OPERATIONS,
    WORKFLOW_DEAD_LETTERS,
    bind_log_context,
)
from apps.events.models import Event
from apps.workflows.models import Workflow

from .contracts import ContractError, decode_message, decode_task, make_workflow_task
from .workflow_service import PermanentProcessingError, process_workflow_task


def forward_kafka_record(record, *, rabbit_publisher, kafka_consumer):
    """Forward one Kafka record, then synchronously commit its offset."""
    message_id = f"kafka:{record.topic}:{record.partition}:{record.offset}"
    try:
        event = decode_message(record.value)
        event_id = event["event_id"]
        event_row = Event.objects.filter(pk=event_id).first()
        workflow = Workflow.objects.only("id").filter(event_id=event_id).first()
        if event_row is None or workflow is None:
            raise ContractError("Kafka domain event has no transactional Event/Workflow record.")
        if (
            event_row.event_type != event["event_type"]
            or event_row.schema_version != event["schema_version"]
            or event_row.correlation_id != event["correlation_id"]
            or event_row.payload != event["payload"]
            or ("request_id" in event and event_row.request_id != event["request_id"])
            or ("workflow_id" in event and str(workflow.id) != event["workflow_id"])
        ):
            raise ContractError("Kafka domain event does not match its PostgreSQL source record.")
        event["request_id"] = event_row.request_id
    except ContractError:
        raw = record.value or b""
        rabbit_publisher.publish_invalid_payload(
            message_id=message_id,
            body=raw,
            error_code="INVALID_DOMAIN_EVENT",
        )
        kafka_consumer.commit(record)
        return "DEAD_LETTER"

    task = make_workflow_task(event, workflow.id)
    with bind_log_context(
        request_id=event_row.request_id,
        trace_id=event_row.request_id,
        event_id=event_id,
        workflow_id=workflow.id,
        correlation_id=event["correlation_id"],
    ):
        rabbit_publisher.publish_task(task)
        kafka_consumer.commit(record)
    BROKER_OPERATIONS.labels(broker="kafka", operation="forward", result="success").inc()
    return "FORWARDED"


def process_rabbit_delivery(delivery, *, rabbit_publisher, inventory_checker=None):
    """Record a durable outcome before confirming or rerouting a Rabbit delivery."""
    try:
        task = decode_task(delivery.body)
    except ContractError:
        message_id = hashlib.sha256(delivery.body).hexdigest()
        rabbit_publisher.publish_invalid_payload(
            message_id=f"rabbit-invalid:{message_id}",
            body=delivery.body,
            error_code="INVALID_WORKFLOW_TASK",
        )
        delivery.ack()
        WORKFLOW_DEAD_LETTERS.labels(stage="unknown", error_code="INVALID_WORKFLOW_TASK").inc()
        return "DEAD_LETTER"

    with bind_log_context(
        request_id=task.get("request_id"),
        trace_id=task.get("request_id"),
        event_id=task.get("event_id"),
        workflow_id=task.get("workflow_id"),
        correlation_id=task.get("correlation_id"),
    ):
        try:
            decision = process_workflow_task(task, inventory_checker=inventory_checker)
        except PermanentProcessingError as exc:
            rabbit_publisher.publish_dead_letter(
                task,
                error_code=exc.code,
                detail=exc.detail,
            )
            delivery.ack()
            WORKFLOW_DEAD_LETTERS.labels(stage="unknown", error_code=exc.code).inc()
            return "DEAD_LETTER"

        if decision.action == "RETRY":
            rabbit_publisher.publish_retry(decision.task, decision.retry_index)
            delivery.ack()
            BROKER_OPERATIONS.labels(broker="rabbitmq", operation="retry", result="success").inc()
            return decision.action
        if decision.action == "DEAD_LETTER":
            rabbit_publisher.publish_dead_letter(
                decision.task,
                error_code=decision.error_code,
                detail=decision.detail,
            )
            delivery.ack()
            BROKER_OPERATIONS.labels(
                broker="rabbitmq", operation="dead_letter", result="success"
            ).inc()
            return decision.action
        delivery.ack()
        BROKER_OPERATIONS.labels(broker="rabbitmq", operation="ack", result="success").inc()
        return "ACK"


def rabbit_connection_settings():
    return {
        "host": settings.RABBITMQ_HOST,
        "port": settings.RABBITMQ_PORT,
        "username": settings.RABBITMQ_USERNAME,
        "password": settings.RABBITMQ_PASSWORD,
        "vhost": settings.RABBITMQ_VHOST,
        "timeout": settings.BROKER_CONNECT_TIMEOUT,
        "use_tls": settings.RABBITMQ_USE_TLS,
        "ca_cert": settings.RABBITMQ_CA_CERT,
    }
