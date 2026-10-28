DOMAIN_TOPIC = "eventflow.domain.events.v1"
LIFECYCLE_TOPIC = "eventflow.workflow.lifecycle.v1"
INTEGRATION_TOPIC = "eventflow.integration.events.v1"
KAFKA_CONSUMER_GROUP = "eventflow.kafka-to-rabbit.v1"

TASK_EXCHANGE = "eventflow.tasks.x"
TASK_QUEUE = "eventflow.tasks.order-validation.q"
TASK_ROUTING_KEY = "order.created.v1"
RETRY_EXCHANGE = "eventflow.retry.x"
DEAD_EXCHANGE = "eventflow.dead.x"
DEAD_QUEUE = "eventflow.tasks.dead.q"
DEAD_ROUTING_KEY = "workflow.dead_lettered"
RETRY_ROUTES = ("retry.5s", "retry.30s")
RETRY_QUEUE_TTLS_MS = (5_000, 30_000)
