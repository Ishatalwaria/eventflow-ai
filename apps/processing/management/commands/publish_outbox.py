import logging
import time

from django.conf import settings
from django.core.management.base import BaseCommand

from apps.common.metrics import start_background_metrics_server
from apps.common.observability import BROKER_OPERATIONS
from apps.processing.adapters.kafka import ConfluentKafkaPublisher
from apps.processing.outbox import oldest_unpublished_summary, publish_outbox_batch

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Publish claimed transactional outbox messages to Kafka."

    def add_arguments(self, parser):
        parser.add_argument("--once", action="store_true", help="Publish one batch and exit.")
        parser.add_argument("--batch-size", type=int, default=25)
        parser.add_argument("--poll-seconds", type=float, default=1.0)

    def handle(self, *args, **options):
        if not 1 <= options["batch_size"] <= 100 or options["poll_seconds"] <= 0:
            self.stderr.write("batch size must be 1..100 and poll interval must be positive")
            return
        publisher = ConfluentKafkaPublisher(settings.KAFKA_BOOTSTRAP_SERVERS)
        start_background_metrics_server()
        next_outbox_sample = 0.0
        try:
            while True:
                summary = publish_outbox_batch(publisher, batch_size=options["batch_size"])
                if time.monotonic() >= next_outbox_sample:
                    oldest_unpublished_summary()
                    next_outbox_sample = time.monotonic() + 15
                if summary.claimed:
                    logger.info(
                        "Outbox batch claimed=%s published=%s retried=%s dead_lettered=%s",
                        summary.claimed,
                        summary.published,
                        summary.retried,
                        summary.dead_lettered,
                    )
                if options["once"]:
                    return
                if summary.claimed == 0:
                    time.sleep(options["poll_seconds"])
        except KeyboardInterrupt:
            logger.info("Outbox publisher shutdown requested")
        except Exception:
            BROKER_OPERATIONS.labels(
                broker="kafka", operation="outbox_publish", result="error"
            ).inc()
            raise
        finally:
            publisher.close()
