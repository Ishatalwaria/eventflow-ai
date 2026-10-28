import json
import os
import time
import uuid

import pytest
from django.conf import settings

from apps.processing.adapters.kafka import ConfluentKafkaConsumer, ConfluentKafkaPublisher
from apps.processing.adapters.rabbitmq import PikaRabbitAdapter
from apps.processing.contracts import encode_message, encode_task, make_workflow_task
from apps.processing.topology import INTEGRATION_TOPIC

pytestmark = pytest.mark.integration


def _require_live_brokers():
    if os.getenv("EVENTFLOW_RUN_BROKER_INTEGRATION") != "1":
        pytest.skip("Set EVENTFLOW_RUN_BROKER_INTEGRATION=1 to use live local brokers.")


def test_kafka_producer_and_consumer_round_trip():
    _require_live_brokers()
    event_id = str(uuid.uuid4())
    envelope = {
        "event_id": event_id,
        "event_type": "order.created",
        "schema_version": 1,
        "correlation_id": str(uuid.uuid4()),
        "occurred_at": "2026-10-27T00:00:00+00:00",
        "recorded_at": "2026-10-27T00:00:00+00:00",
        "payload": {
            "order_id": f"integration-{event_id}",
            "currency": "INR",
            "total_minor_units": 100,
            "items": [{"sku": "SKU-INTEGRATION", "quantity": 1}],
        },
    }
    group_id = f"eventflow.integration.{uuid.uuid4()}"
    publisher = ConfluentKafkaPublisher(settings.KAFKA_BOOTSTRAP_SERVERS)
    consumer = ConfluentKafkaConsumer(
        bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
        group_id=group_id,
        topic=INTEGRATION_TOPIC,
    )
    try:
        publisher.publish(
            topic=INTEGRATION_TOPIC,
            key=event_id.encode(),
            value=encode_message(envelope),
            timeout=10,
        )
        deadline = time.monotonic() + 30
        received = None
        while time.monotonic() < deadline:
            candidate = consumer.poll(1)
            if candidate is not None and candidate.key == event_id.encode():
                received = candidate
                break
        assert received is not None, "Timed out waiting for the Kafka integration record."
        consumer.commit(received)
    finally:
        consumer.close()
        publisher.close()


def test_rabbit_persistent_task_publish_is_routed_to_durable_queue():
    _require_live_brokers()
    if settings.RABBITMQ_USERNAME == "guest" or not settings.RABBITMQ_PASSWORD:
        pytest.fail(
            "Set RABBITMQ_USERNAME and RABBITMQ_PASSWORD in .env to match the local broker."
        )
    workflow_id = str(uuid.uuid4())
    event_id = str(uuid.uuid4())
    envelope = {
        "event_id": event_id,
        "event_type": "order.created",
        "schema_version": 1,
        "correlation_id": str(uuid.uuid4()),
        "occurred_at": "2026-10-27T00:00:00+00:00",
        "recorded_at": "2026-10-27T00:00:00+00:00",
        "payload": {
            "order_id": "rabbit-integration",
            "currency": "INR",
            "total_minor_units": 100,
            "items": [{"sku": "SKU-INTEGRATION", "quantity": 1}],
        },
    }
    task = make_workflow_task(envelope, workflow_id)
    publisher = PikaRabbitAdapter(
        host=settings.RABBITMQ_HOST,
        port=settings.RABBITMQ_PORT,
        username=settings.RABBITMQ_USERNAME,
        password=settings.RABBITMQ_PASSWORD,
        vhost=settings.RABBITMQ_VHOST,
        timeout=settings.BROKER_CONNECT_TIMEOUT,
        use_tls=settings.RABBITMQ_USE_TLS,
        ca_cert=settings.RABBITMQ_CA_CERT,
    )
    exchange = f"eventflow.integration.{uuid.uuid4()}.x"
    routing_key = f"integration.{uuid.uuid4()}"
    queue = f"eventflow.integration.{uuid.uuid4()}.q"
    exchange_created = queue_created = False
    try:
        channel = publisher.channel
        channel.exchange_declare(
            exchange=exchange, exchange_type="direct", durable=True, auto_delete=False
        )
        exchange_created = True
        channel.queue_declare(queue=queue, durable=True)
        queue_created = True
        channel.queue_bind(queue=queue, exchange=exchange, routing_key=routing_key)
        publisher._publish(
            exchange=exchange,
            routing_key=routing_key,
            body=encode_task(task),
            message_id=task["task_id"],
            headers={"schema": "eventflow.workflow-task.v1"},
        )
        deadline = time.monotonic() + 10
        delivery = None
        while time.monotonic() < deadline:
            method, properties, body = channel.basic_get(queue=queue, auto_ack=False)
            if method:
                delivery = (method, properties, body)
                break
            time.sleep(0.1)
        assert delivery is not None, "Timed out waiting for RabbitMQ's routed task copy."
        method, properties, body = delivery
        assert properties.delivery_mode == 2
        assert json.loads(body) == task
        channel.basic_ack(method.delivery_tag)
    finally:
        if publisher.channel.is_open:
            if queue_created:
                publisher.channel.queue_delete(queue=queue)
            if exchange_created:
                publisher.channel.exchange_delete(exchange=exchange)
        publisher.close()
