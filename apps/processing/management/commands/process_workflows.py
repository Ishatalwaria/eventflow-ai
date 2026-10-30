import logging
import signal
import threading
import time

from django.core.management.base import BaseCommand

from apps.common.metrics import start_background_metrics_server
from apps.common.observability import BROKER_OPERATIONS
from apps.processing.adapters.rabbitmq import PikaRabbitAdapter
from apps.processing.pipeline import process_rabbit_delivery, rabbit_connection_settings

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Consume durable RabbitMQ workflow tasks and record workflow outcomes."

    def handle(self, *args, **options):
        start_background_metrics_server()
        stop_event = threading.Event()
        old_handlers = {}

        def stop(_signum, _frame):
            stop_event.set()

        for sig in (signal.SIGINT, signal.SIGTERM):
            old_handlers[sig] = signal.signal(sig, stop)

        backoff = 1
        try:
            while not stop_event.is_set():
                rabbit = None
                try:
                    rabbit = PikaRabbitAdapter(**rabbit_connection_settings())
                    backoff = 1
                    rabbit.consume(
                        lambda delivery, publisher=rabbit: process_rabbit_delivery(
                            delivery, rabbit_publisher=publisher
                        ),
                        should_stop=stop_event.is_set,
                    )
                except KeyboardInterrupt:
                    stop_event.set()
                except Exception as exc:
                    BROKER_OPERATIONS.labels(
                        broker="rabbitmq", operation="consume", result="error"
                    ).inc()
                    # The unacked delivery is recovered when this connection closes.
                    logger.warning(
                        "Workflow worker connection loop failed error_type=%s retry_seconds=%s",
                        type(exc).__name__,
                        backoff,
                    )
                    if not stop_event.is_set():
                        time.sleep(backoff)
                        backoff = min(backoff * 2, 30)
                finally:
                    if rabbit is not None:
                        try:
                            rabbit.close()
                        except Exception as exc:
                            logger.warning("RabbitMQ shutdown error_type=%s", type(exc).__name__)
        finally:
            for sig, handler in old_handlers.items():
                signal.signal(sig, handler)
