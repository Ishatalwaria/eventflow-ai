import logging
import signal
import threading

from django.conf import settings
from django.core.management.base import BaseCommand

from apps.analytics.sink import ClickHouseLifecycleSink
from apps.common.metrics import start_background_metrics_server
from apps.common.observability import ANALYTICS_DELIVERIES, bind_log_context
from apps.processing.adapters.kafka import ConfluentKafkaConsumer
from apps.processing.contracts import decode_message
from apps.processing.topology import ANALYTICS_CONSUMER_GROUP, LIFECYCLE_TOPIC

logger = logging.getLogger(__name__)


def project_record(record, *, sink, consumer):
    event = decode_message(record.value, lifecycle=True)
    try:
        with bind_log_context(
            request_id=event.get("request_id"),
            trace_id=event.get("request_id"),
            event_id=event.get("event_id"),
            workflow_id=event.get("workflow_id"),
            correlation_id=event.get("correlation_id"),
        ):
            sink.write(event)
            consumer.commit(record)
    except Exception:
        ANALYTICS_DELIVERIES.labels(result="error").inc()
        raise
    ANALYTICS_DELIVERIES.labels(result="confirmed").inc()


class Command(BaseCommand):
    help = "Project lifecycle Kafka events to ClickHouse analytics."

    def add_arguments(self, parser):
        parser.add_argument(
            "--once", action="store_true", help="Consume one lifecycle event and exit."
        )

    def handle(self, *args, **options):
        start_background_metrics_server()
        stop = threading.Event()
        previous_handlers = {}

        def request_stop(_signum, _frame):
            stop.set()

        for sig in (signal.SIGINT, signal.SIGTERM):
            previous_handlers[sig] = signal.signal(sig, request_stop)
        backoff = 1
        try:
            while not stop.is_set():
                consumer = sink = None
                try:
                    consumer = ConfluentKafkaConsumer(
                        bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
                        group_id=ANALYTICS_CONSUMER_GROUP,
                        topic=LIFECYCLE_TOPIC,
                    )
                    sink = ClickHouseLifecycleSink()
                    while not stop.is_set():
                        record = consumer.poll(1.0)
                        if record is None:
                            continue
                        # Commit only after ClickHouse confirmed insert. A crash before this
                        # point replays the event; deterministic lifecycle_id handles it.
                        project_record(record, sink=sink, consumer=consumer)
                        backoff = 1
                        logger.info(
                            "Lifecycle event projected topic=%s partition=%s offset=%s",
                            record.topic,
                            record.partition,
                            record.offset,
                        )
                        if options["once"]:
                            return
                except KeyboardInterrupt:
                    stop.set()
                except Exception as exc:
                    # Do not commit poison messages or failed inserts. Operators can repair
                    # the record/schema; the consumer group remains safely replayable.
                    logger.warning(
                        "Analytics consumer retry error_type=%s retry_seconds=%s",
                        type(exc).__name__,
                        backoff,
                    )
                    if not stop.is_set():
                        stop.wait(backoff)
                        backoff = min(backoff * 2, settings.ANALYTICS_RETRY_MAX_SECONDS)
                finally:
                    if sink is not None:
                        try:
                            sink.client.close()
                        except Exception:
                            pass
                    if consumer is not None:
                        try:
                            consumer.close()
                        except Exception as exc:
                            logger.warning(
                                "Analytics consumer shutdown error_type=%s", type(exc).__name__
                            )
        finally:
            for sig, handler in previous_handlers.items():
                signal.signal(sig, handler)
