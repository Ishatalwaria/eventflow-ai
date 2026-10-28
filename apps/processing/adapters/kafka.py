from dataclasses import dataclass

from confluent_kafka import Consumer, KafkaError, Producer, TopicPartition

from apps.processing.ports import KafkaPublisher
from apps.processing.topology import DOMAIN_TOPIC, KAFKA_CONSUMER_GROUP


class BrokerUnavailable(RuntimeError):
    """A broker operation failed or timed out and can be retried."""


class KafkaPublishError(BrokerUnavailable):
    pass


@dataclass(frozen=True)
class KafkaMessage:
    topic: str
    partition: int
    offset: int
    key: bytes | None
    value: bytes


class ConfluentKafkaPublisher(KafkaPublisher):
    """Project-owned Kafka producer adapter with delivery confirmation."""

    def __init__(self, bootstrap_servers):
        self._producer = Producer(
            {
                "bootstrap.servers": bootstrap_servers,
                "client.id": "eventflow-outbox-publisher",
                "acks": "all",
                "enable.idempotence": True,
                "message.timeout.ms": 10_000,
                **_kafka_security_config(),
            }
        )

    def publish(self, *, topic, key, value, timeout):
        delivery = {"error": None}

        def on_delivery(error, _message):
            delivery["error"] = error

        try:
            self._producer.produce(topic=topic, key=key, value=value, callback=on_delivery)
            pending = self._producer.flush(timeout)
        except Exception as exc:
            raise KafkaPublishError("Kafka publish failed.") from exc
        if pending or delivery["error"] is not None:
            raise KafkaPublishError("Kafka did not confirm the publish before timeout.")

    def close(self):
        pending = self._producer.flush(10.0)
        if pending:
            raise KafkaPublishError("Kafka producer shutdown timed out with pending messages.")


class ConfluentKafkaConsumer:
    """Consumer with manual, synchronous offset commits after Rabbit confirms."""

    def __init__(self, *, bootstrap_servers, group_id=KAFKA_CONSUMER_GROUP, topic=DOMAIN_TOPIC):
        self._consumer = Consumer(
            {
                "bootstrap.servers": bootstrap_servers,
                "client.id": "eventflow-kafka-to-rabbit",
                "group.id": group_id,
                "enable.auto.commit": False,
                "enable.auto.offset.store": False,
                "allow.auto.create.topics": False,
                "auto.offset.reset": "earliest",
                "session.timeout.ms": 10_000,
                "max.poll.interval.ms": 60_000,
                "max.partition.fetch.bytes": 1_048_576,
                **_kafka_security_config(),
            }
        )
        self._consumer.subscribe([topic])

    def poll(self, timeout):
        try:
            message = self._consumer.poll(timeout)
        except Exception as exc:
            raise BrokerUnavailable("Kafka poll failed.") from exc
        if message is None:
            return None
        error = message.error()
        if error is not None:
            if error.code() == KafkaError._PARTITION_EOF:
                return None
            raise BrokerUnavailable("Kafka returned a consumer error.")
        return KafkaMessage(
            topic=message.topic(),
            partition=message.partition(),
            offset=message.offset(),
            key=message.key(),
            value=message.value(),
        )

    def commit(self, record):
        try:
            result = self._consumer.commit(
                offsets=[TopicPartition(record.topic, record.partition, record.offset + 1)],
                asynchronous=False,
            )
        except Exception as exc:
            raise BrokerUnavailable("Kafka offset commit failed.") from exc
        if result and any(partition.error is not None for partition in result):
            raise BrokerUnavailable("Kafka did not confirm the offset commit.")

    def close(self):
        self._consumer.close()


def _kafka_security_config():
    """Return TLS/SASL options shared by the producer and consumer."""
    from django.conf import settings

    protocol = settings.KAFKA_SECURITY_PROTOCOL
    config = {"security.protocol": protocol}
    if protocol.startswith("SASL_"):
        config.update(
            {
                "sasl.mechanism": settings.KAFKA_SASL_MECHANISM,
                "sasl.username": settings.KAFKA_SASL_USERNAME,
                "sasl.password": settings.KAFKA_SASL_PASSWORD,
            }
        )
    if settings.KAFKA_SSL_CA_LOCATION:
        config["ssl.ca.location"] = settings.KAFKA_SSL_CA_LOCATION
    return config
