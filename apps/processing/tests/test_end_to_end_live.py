"""Authenticated API-to-workflow smoke using a disposable DB and live brokers."""

import json
import os
import time
import uuid
from datetime import UTC, datetime

import pytest
from django.conf import settings
from django.utils import timezone
from rest_framework.test import APIClient as RestAPIClient

from apps.common.services import create_api_client, revoke_api_client
from apps.processing.adapters.kafka import (
    BrokerUnavailable,
    ConfluentKafkaConsumer,
    ConfluentKafkaPublisher,
)
from apps.processing.adapters.rabbitmq import PikaRabbitAdapter, RabbitDelivery
from apps.processing.models import OutboxMessage
from apps.processing.outbox import publish_outbox_batch
from apps.processing.pipeline import forward_kafka_record, process_rabbit_delivery
from apps.processing.topology import (
    DOMAIN_TOPIC,
    INTEGRATION_TOPIC,
    KAFKA_CONSUMER_GROUP,
    TASK_QUEUE,
)
from apps.processing.workflow_service import process_workflow_task
from apps.workflows.models import Workflow

pytestmark = [pytest.mark.integration, pytest.mark.django_db(transaction=True)]


def test_authenticated_event_reaches_terminal_workflow_through_live_brokers():
    if os.getenv("EVENTFLOW_RUN_BROKER_INTEGRATION") != "1":
        pytest.skip("Set EVENTFLOW_RUN_BROKER_INTEGRATION=1 to use live local brokers.")

    api_client, token = create_api_client("temporary-live-smoke")
    from apps.commerce.models import InventoryItem, Product

    product = Product.objects.create(
        client=api_client,
        sku="LIVE-SMOKE-SKU",
        name="Live Smoke SKU",
        unit_price_minor=1299,
        active=True,
    )
    InventoryItem.objects.create(product=product, on_hand=10, reserved=0)

    correlation_id = f"live-smoke-{uuid.uuid4()}"
    payload = {
        "event_type": "order.created",
        "schema_version": 1,
        "source": "integration-test",
        "idempotency_key": f"live-smoke-{uuid.uuid4()}",
        "occurred_at": datetime.now(UTC).isoformat(),
        "correlation_id": correlation_id,
        "payload": {
            "order_id": str(uuid.uuid4()),
            "currency": "INR",
            "total_minor_units": 1299,
            "payment_method_token": "ok_card",
            "items": [{"sku": "LIVE-SMOKE-SKU", "quantity": 1}],
        },
    }
    kafka_consumer = None
    kafka_publisher = None
    rabbit = None
    try:
        api = RestAPIClient()
        response = api.post(
            "/api/v1/events",
            payload,
            HTTP_AUTHORIZATION=f"Bearer {token}",
            format="json",
        )
        assert response.status_code == 201, response.data
        event_id = str(response.data["event_id"])
        workflow_id = str(response.data["workflow_id"])

        event_response = api.get(
            f"/api/v1/events/{event_id}",
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )
        assert event_response.status_code == 200
        assert str(event_response.data["id"]) == str(event_id)
        assert event_response.data["correlation_id"] == correlation_id

        class TemporarilyUnavailablePublisher:
            def publish(self, **_kwargs):
                raise BrokerUnavailable("Injected one-time Kafka outage.")

        class IsolatedTopicPublisher:
            def publish(self, *, topic, key, value, timeout):
                kafka_publisher.publish(
                    topic=INTEGRATION_TOPIC,
                    key=key,
                    value=value,
                    timeout=timeout,
                )

        failed_publish = publish_outbox_batch(TemporarilyUnavailablePublisher())
        assert failed_publish.retried >= 1
        outbox_row = OutboxMessage.objects.get(event_id=event_id, topic=DOMAIN_TOPIC)
        assert outbox_row.published_at is None
        OutboxMessage.objects.filter(pk=outbox_row.pk).update(available_at=timezone.now())

        kafka_publisher = ConfluentKafkaPublisher(settings.KAFKA_BOOTSTRAP_SERVERS)
        publish_result = publish_outbox_batch(IsolatedTopicPublisher(), batch_size=10)
        assert publish_result.published >= 1
        outbox_row.refresh_from_db()
        assert outbox_row.published_at is not None

        group_id = f"{KAFKA_CONSUMER_GROUP}.live-smoke.{uuid.uuid4()}"
        kafka_consumer = ConfluentKafkaConsumer(
            bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
            group_id=group_id,
            topic=INTEGRATION_TOPIC,
        )
        rabbit = PikaRabbitAdapter(
            host=settings.RABBITMQ_HOST,
            port=settings.RABBITMQ_PORT,
            username=settings.RABBITMQ_USERNAME,
            password=settings.RABBITMQ_PASSWORD,
            vhost=settings.RABBITMQ_VHOST,
            timeout=settings.BROKER_CONNECT_TIMEOUT,
            use_tls=settings.RABBITMQ_USE_TLS,
            ca_cert=settings.RABBITMQ_CA_CERT,
        )

        deadline = time.monotonic() + 45
        forwarded = False
        while time.monotonic() < deadline:
            record = kafka_consumer.poll(1)
            if record is None:
                continue
            try:
                envelope = json.loads(record.value)
            except (TypeError, ValueError):
                continue
            if envelope.get("event_id") != event_id:
                continue
            forward_kafka_record(record, rabbit_publisher=rabbit, kafka_consumer=kafka_consumer)
            forwarded = True
            break
        assert forwarded, "Timed out waiting for the event on the domain topic."

        delivery_deadline = time.monotonic() + 20
        delivery = None
        while time.monotonic() < delivery_deadline:
            method, _properties, body = rabbit.channel.basic_get(
                queue=TASK_QUEUE,
                auto_ack=False,
            )
            if method is not None:
                task = json.loads(body)
                if task.get("workflow_id") == workflow_id:
                    delivery = RabbitDelivery(rabbit.channel, method, body)
                    break
                rabbit.channel.basic_nack(method.delivery_tag, requeue=True)
            time.sleep(0.1)
        assert delivery is not None, "Timed out waiting for the workflow task in RabbitMQ."
        task = json.loads(delivery.body)
        assert task["workflow_id"] == workflow_id

        # Simulate a worker crash after the database commit and before Rabbit ack.
        assert process_workflow_task(task).action == "ENQUEUE_NEXT"
        rabbit.close()
        rabbit = None

        rabbit = PikaRabbitAdapter(
            host=settings.RABBITMQ_HOST,
            port=settings.RABBITMQ_PORT,
            username=settings.RABBITMQ_USERNAME,
            password=settings.RABBITMQ_PASSWORD,
            vhost=settings.RABBITMQ_VHOST,
            timeout=settings.BROKER_CONNECT_TIMEOUT,
            use_tls=settings.RABBITMQ_USE_TLS,
            ca_cert=settings.RABBITMQ_CA_CERT,
        )
        redelivery_deadline = time.monotonic() + 20
        redelivery = None
        while time.monotonic() < redelivery_deadline:
            method, _properties, body = rabbit.channel.basic_get(
                queue=TASK_QUEUE,
                auto_ack=False,
            )
            if method is not None:
                if json.loads(body).get("workflow_id") == workflow_id:
                    assert method.redelivered
                    redelivery = RabbitDelivery(rabbit.channel, method, body)
                    break
                rabbit.channel.basic_nack(method.delivery_tag, requeue=True)
            time.sleep(0.1)
        assert redelivery is not None, "Timed out waiting for the unacknowledged task to requeue."
        assert process_rabbit_delivery(redelivery, rabbit_publisher=rabbit) == "ENQUEUE_NEXT"

        # Drive remaining saga stages until the workflow reaches a terminal state
        stage_deadline = time.monotonic() + 30
        while time.monotonic() < stage_deadline:
            method, _properties, body = rabbit.channel.basic_get(
                queue=TASK_QUEUE,
                auto_ack=False,
            )
            if method is None:
                time.sleep(0.05)
                continue
            stage_task = json.loads(body)
            if stage_task.get("workflow_id") != workflow_id:
                rabbit.channel.basic_nack(method.delivery_tag, requeue=True)
                time.sleep(0.05)
                continue
            stage_delivery = RabbitDelivery(rabbit.channel, method, body)
            action = process_rabbit_delivery(stage_delivery, rabbit_publisher=rabbit)
            if action == "ACK":
                break

        workflow = Workflow.objects.get(pk=workflow_id)
        assert workflow.state == Workflow.State.SUCCEEDED
        assert workflow.attempts.count() == 6
        assert workflow.attempts.filter(stage="validate_order").count() == 1

        workflow_response = None
        poll_deadline = time.monotonic() + 10
        while time.monotonic() < poll_deadline:
            workflow_response = api.get(
                f"/api/v1/workflows/{workflow_id}",
                HTTP_AUTHORIZATION=f"Bearer {token}",
            )
            if workflow_response.data.get("state") in {
                Workflow.State.SUCCEEDED,
                Workflow.State.FAILED,
                Workflow.State.DEAD_LETTERED,
            }:
                break
            time.sleep(0.1)
        assert workflow_response.status_code == 200
        assert workflow_response.data["state"] == Workflow.State.SUCCEEDED
        assert str(workflow_response.data["event_id"]) == str(event_id)
    finally:
        try:
            if kafka_consumer is not None:
                kafka_consumer.close()
        finally:
            try:
                if kafka_publisher is not None:
                    kafka_publisher.close()
            finally:
                try:
                    if rabbit is not None:
                        rabbit.close()
                finally:
                    revoke_api_client(api_client)
