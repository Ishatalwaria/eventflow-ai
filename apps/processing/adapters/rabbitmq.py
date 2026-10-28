import base64
import hashlib
import json
import ssl

import pika

from apps.processing.contracts import MAX_MESSAGE_BYTES, encode_task
from apps.processing.ports import RabbitTaskPublisher
from apps.processing.topology import (
    DEAD_EXCHANGE,
    DEAD_QUEUE,
    DEAD_ROUTING_KEY,
    RETRY_EXCHANGE,
    RETRY_QUEUE_TTLS_MS,
    RETRY_ROUTES,
    TASK_EXCHANGE,
    TASK_QUEUE,
    TASK_ROUTING_KEY,
)

from .kafka import BrokerUnavailable


class RabbitDelivery:
    def __init__(self, channel, method, body):
        self.body = body
        self._channel = channel
        self._method = method

    def ack(self):
        if self._channel.is_open:
            self._channel.basic_ack(delivery_tag=self._method.delivery_tag)

    def reject_without_requeue(self):
        if self._channel.is_open:
            self._channel.basic_nack(delivery_tag=self._method.delivery_tag, requeue=False)


class PikaRabbitAdapter(RabbitTaskPublisher):
    """RabbitMQ topology, publisher-confirm, and manual-consumer adapter."""

    def __init__(
        self,
        *,
        host,
        port,
        username,
        password,
        vhost,
        timeout,
        use_tls=False,
        ca_cert="",
    ):
        credentials = pika.PlainCredentials(username, password)
        ssl_options = None
        if use_tls:
            context = ssl.create_default_context(cafile=ca_cert or None)
            ssl_options = pika.SSLOptions(context, host)
        parameters = pika.ConnectionParameters(
            host=host,
            port=port,
            virtual_host=vhost,
            credentials=credentials,
            socket_timeout=timeout,
            stack_timeout=timeout,
            blocked_connection_timeout=timeout,
            heartbeat=30,
            connection_attempts=1,
            ssl_options=ssl_options,
        )
        try:
            self.connection = pika.BlockingConnection(parameters)
            self.channel = self.connection.channel()
            self.declare_topology()
            self.channel.confirm_delivery()
        except pika.exceptions.AMQPError as exc:
            raise BrokerUnavailable("RabbitMQ connection or topology setup failed.") from exc

    def declare_topology(self):
        for exchange in (TASK_EXCHANGE, RETRY_EXCHANGE, DEAD_EXCHANGE):
            self.channel.exchange_declare(exchange=exchange, exchange_type="direct", durable=True)

        quorum = {"x-queue-type": "quorum", "x-quorum-initial-group-size": 1}
        self.channel.queue_declare(
            queue=TASK_QUEUE,
            durable=True,
            arguments={
                **quorum,
                "x-max-length": 10_000,
                "x-dead-letter-exchange": DEAD_EXCHANGE,
                "x-dead-letter-routing-key": "worker.rejected",
            },
        )
        self.channel.queue_bind(TASK_QUEUE, TASK_EXCHANGE, TASK_ROUTING_KEY)

        for route, ttl_ms in zip(RETRY_ROUTES, RETRY_QUEUE_TTLS_MS, strict=True):
            self.channel.queue_declare(
                queue=f"eventflow.tasks.{route}.q",
                durable=True,
                arguments={
                    **quorum,
                    "x-max-length": 10_000,
                    "x-message-ttl": ttl_ms,
                    "x-dead-letter-exchange": TASK_EXCHANGE,
                    "x-dead-letter-routing-key": TASK_ROUTING_KEY,
                    "x-dead-letter-strategy": "at-least-once",
                    "x-overflow": "reject-publish",
                },
            )
            self.channel.queue_bind(f"eventflow.tasks.{route}.q", RETRY_EXCHANGE, route)

        self.channel.queue_declare(
            queue=DEAD_QUEUE,
            durable=True,
            arguments={**quorum, "x-max-length": 10_000},
        )
        self.channel.queue_bind(DEAD_QUEUE, DEAD_EXCHANGE, DEAD_ROUTING_KEY)
        self.channel.queue_bind(DEAD_QUEUE, DEAD_EXCHANGE, "worker.rejected")
        self.channel.queue_bind(DEAD_QUEUE, DEAD_EXCHANGE, "invalid.domain_event")

    def _publish(self, *, exchange, routing_key, body, message_id, headers=None):
        if not isinstance(body, bytes) or len(body) > MAX_MESSAGE_BYTES:
            raise ValueError("RabbitMQ message is empty or exceeds the size limit.")
        try:
            confirmed = self.channel.basic_publish(
                exchange=exchange,
                routing_key=routing_key,
                body=body,
                mandatory=True,
                properties=pika.BasicProperties(
                    content_type="application/json",
                    delivery_mode=pika.DeliveryMode.Persistent,
                    message_id=message_id,
                    headers=headers or {},
                ),
            )
        except pika.exceptions.AMQPError as exc:
            raise BrokerUnavailable("RabbitMQ did not confirm the publish.") from exc
        if confirmed is False:
            raise BrokerUnavailable("RabbitMQ rejected the publish.")

    def publish_task(self, task):
        self._publish(
            exchange=TASK_EXCHANGE,
            routing_key=TASK_ROUTING_KEY,
            body=encode_task(task),
            message_id=task["task_id"],
            headers={"schema": "eventflow.workflow-task.v1"},
        )

    def publish_retry(self, task, retry_index):
        if not 0 <= retry_index < len(RETRY_ROUTES):
            raise ValueError("Retry route index is outside the configured bounded schedule.")
        self._publish(
            exchange=RETRY_EXCHANGE,
            routing_key=RETRY_ROUTES[retry_index],
            body=encode_task(task),
            message_id=task["task_id"],
            headers={"schema": "eventflow.workflow-task.v1", "retry_index": retry_index + 1},
        )

    def publish_dead_letter(self, task, *, error_code, detail):
        payload = {
            "task": task,
            "error_code": error_code[:100],
            "detail": detail[:500],
        }
        body = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
        self._publish(
            exchange=DEAD_EXCHANGE,
            routing_key=DEAD_ROUTING_KEY,
            body=body,
            message_id=task.get("task_id", "unknown"),
            headers={"schema": "eventflow.dead-letter.v1"},
        )

    def publish_invalid_payload(self, *, message_id, body, error_code):
        preview = body[:4096]
        envelope = {
            "error_code": error_code[:100],
            "original_bytes": len(body),
            "sha256": hashlib.sha256(body).hexdigest(),
            "preview_base64": base64.b64encode(preview).decode("ascii"),
        }
        self._publish(
            exchange=DEAD_EXCHANGE,
            routing_key="invalid.domain_event",
            body=json.dumps(envelope, separators=(",", ":"), sort_keys=True).encode("utf-8"),
            message_id=message_id,
            headers={"schema": "eventflow.invalid-message.v1", "error_code": error_code[:100]},
        )

    def consume(self, handler, *, should_stop):
        self.channel.basic_qos(prefetch_count=1)

        def on_message(channel, method, _properties, body):
            handler(RabbitDelivery(channel, method, body))

        self.channel.basic_consume(queue=TASK_QUEUE, on_message_callback=on_message, auto_ack=False)
        while not should_stop() and self.connection.is_open and self.channel.is_open:
            self.connection.process_data_events(time_limit=0.5)
        if self.channel.is_open:
            self.channel.stop_consuming()

    def close(self):
        if self.connection.is_open:
            self.connection.close()
