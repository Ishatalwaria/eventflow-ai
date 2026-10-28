import logging
import signal
import threading
import time

from django.conf import settings
from django.core.management.base import BaseCommand

from apps.processing.adapters.kafka import ConfluentKafkaConsumer
from apps.processing.adapters.rabbitmq import PikaRabbitAdapter
from apps.processing.pipeline import forward_kafka_record, rabbit_connection_settings

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Forward Kafka domain events to durable RabbitMQ tasks."

    def add_arguments(self, parser):
        parser.add_argument("--once", action="store_true", help="Forward one record and exit.")

    def handle(self, *args, **options):
        stop_event = threading.Event()
        old_handlers = {}

        def stop(_signum, _frame):
            stop_event.set()

        for sig in (signal.SIGINT, signal.SIGTERM):
            old_handlers[sig] = signal.signal(sig, stop)

        backoff = 1
        try:
            while not stop_event.is_set():
                consumer = rabbit = None
                try:
                    consumer = ConfluentKafkaConsumer(
                        bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
                        group_id=settings.KAFKA_CONSUMER_GROUP,
                    )
                    rabbit = PikaRabbitAdapter(**rabbit_connection_settings())
                    backoff = 1
                    while not stop_event.is_set():
                        record = consumer.poll(1.0)
                        if record is None:
                            continue
                        result = forward_kafka_record(
                            record,
                            rabbit_publisher=rabbit,
                            kafka_consumer=consumer,
                        )
                        logger.info(
                            "Kafka record handled topic=%s partition=%s offset=%s result=%s",
                            record.topic,
                            record.partition,
                            record.offset,
                            result,
                        )
                        if options["once"]:
                            return
                except KeyboardInterrupt:
                    stop_event.set()
                except Exception as exc:
                    logger.warning(
                        "Kafka-to-Rabbit connection loop failed error_type=%s retry_seconds=%s",
                        type(exc).__name__,
                        backoff,
                    )
                    if not stop_event.is_set():
                        time.sleep(backoff)
                        backoff = min(backoff * 2, 30)
                finally:
                    for adapter in (consumer, rabbit):
                        if adapter is not None:
                            try:
                                adapter.close()
                            except Exception as exc:
                                logger.warning("Broker shutdown error_type=%s", type(exc).__name__)
        finally:
            for sig, handler in old_handlers.items():
                signal.signal(sig, handler)
