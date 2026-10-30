import json
import uuid
from datetime import datetime

MAX_MESSAGE_BYTES = 524_288
DOMAIN_EVENT_TYPE = "order.created"
LIFECYCLE_EVENT_TYPES = {
    "workflow.processing",
    "workflow.retry_wait",
    "workflow.succeeded",
    "workflow.failed",
    "workflow.dead_lettered",
}


class ContractError(ValueError):
    """A broker message does not match its versioned contract."""


def _validate_envelope(value, *, required):
    if not isinstance(value, dict) or not required.issubset(value):
        raise ContractError("Message envelope is missing required fields.")
    try:
        uuid.UUID(str(value["event_id"]))
        occurred_at = datetime.fromisoformat(str(value["occurred_at"]).replace("Z", "+00:00"))
        recorded_at = datetime.fromisoformat(str(value["recorded_at"]).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        raise ContractError(
            "Message envelope contains an invalid identifier or timestamp."
        ) from None
    if (
        not isinstance(value["correlation_id"], str)
        or not 1 <= len(value["correlation_id"]) <= 128
        or occurred_at.tzinfo is None
        or occurred_at.utcoffset() is None
        or recorded_at.tzinfo is None
        or recorded_at.utcoffset() is None
        or value["schema_version"] != 1
        or not isinstance(value.get("payload"), dict)
    ):
        raise ContractError("Message schema version or payload is invalid.")
    request_id = value.get("request_id")
    if request_id is not None and (
        not isinstance(request_id, str) or not 1 <= len(request_id) <= 64
    ):
        raise ContractError("Message request ID is invalid.")


def validate_domain_event(value):
    _validate_envelope(
        value,
        required={
            "event_id",
            "event_type",
            "schema_version",
            "correlation_id",
            "occurred_at",
            "recorded_at",
            "payload",
        },
    )
    if value["event_type"] != DOMAIN_EVENT_TYPE:
        raise ContractError("Unsupported domain event type.")
    if "workflow_id" in value:
        try:
            uuid.UUID(str(value["workflow_id"]))
        except (TypeError, ValueError):
            raise ContractError("Domain event workflow ID is invalid.") from None
    payload = value["payload"]
    if (
        not isinstance(payload.get("order_id"), str)
        or not isinstance(payload.get("currency"), str)
        or len(payload["currency"]) != 3
        or not payload["currency"].isupper()
        or type(payload.get("total_minor_units")) is not int
        or payload["total_minor_units"] < 0
        or not isinstance(payload.get("items"), list)
        or not 1 <= len(payload["items"]) <= 100
        or any(
            not isinstance(item, dict)
            or not isinstance(item.get("sku"), str)
            or type(item.get("quantity")) is not int
            or item["quantity"] < 1
            for item in payload["items"]
        )
    ):
        raise ContractError("Order event payload is invalid.")


def validate_lifecycle_event(value):
    _validate_envelope(
        value,
        required={
            "event_id",
            "workflow_id",
            "event_type",
            "schema_version",
            "correlation_id",
            "occurred_at",
            "recorded_at",
            "payload",
        },
    )
    try:
        uuid.UUID(str(value["workflow_id"]))
    except (TypeError, ValueError):
        raise ContractError("Lifecycle workflow ID is invalid.") from None
    if value["event_type"] not in LIFECYCLE_EVENT_TYPES:
        raise ContractError("Unsupported lifecycle event type.")
    payload = value["payload"]
    if (
        not isinstance(payload.get("state"), str)
        or payload["state"]
        not in {
            "RECEIVED",
            "QUEUED",
            "PROCESSING",
            "RETRY_WAIT",
            "SUCCEEDED",
            "FAILED",
            "DEAD_LETTERED",
        }
        or not isinstance(payload.get("stage"), str)
        or not 1 <= len(payload["stage"]) <= 100
        or type(payload.get("attempt_number")) is not int
        or not 1 <= payload["attempt_number"] <= 65535
        or not isinstance(payload.get("error_code", ""), str)
        or len(payload.get("error_code", "")) > 100
        or (
            payload.get("duration_ms") is not None
            and (
                type(payload["duration_ms"]) is not int
                or not 0 <= payload["duration_ms"] <= 4_294_967_295
            )
        )
    ):
        raise ContractError("Lifecycle payload fields are invalid.")


def encode_message(value, *, lifecycle=False):
    (validate_lifecycle_event if lifecycle else validate_domain_event)(value)
    try:
        encoded = json.dumps(value, separators=(",", ":"), sort_keys=True).encode("utf-8")
    except (TypeError, ValueError):
        raise ContractError("Message cannot be serialized as JSON.") from None
    if len(encoded) > MAX_MESSAGE_BYTES:
        raise ContractError("Message exceeds the configured size limit.")
    return encoded


def decode_message(raw, *, lifecycle=False):
    if not isinstance(raw, bytes) or len(raw) > MAX_MESSAGE_BYTES:
        raise ContractError("Message is empty or exceeds the size limit.")
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise ContractError("Message is not valid UTF-8 JSON.") from None
    (validate_lifecycle_event if lifecycle else validate_domain_event)(value)
    return value


def make_workflow_task(domain_event, workflow_id, attempt_number=1):
    validate_domain_event(domain_event)
    task = {
        "task_version": 1,
        "task_id": f"{workflow_id}:order-validation:{attempt_number}",
        "workflow_id": str(workflow_id),
        "event_id": domain_event["event_id"],
        "event_type": domain_event["event_type"],
        "event_schema_version": domain_event["schema_version"],
        "correlation_id": domain_event["correlation_id"],
        "attempt_number": attempt_number,
        "payload": domain_event["payload"],
    }
    if domain_event.get("request_id"):
        task["request_id"] = domain_event["request_id"]
    if len(json.dumps(task, separators=(",", ":")).encode("utf-8")) > MAX_MESSAGE_BYTES:
        raise ContractError("Task exceeds the configured size limit.")
    return task


def validate_workflow_task(value):
    required = {
        "task_version",
        "task_id",
        "workflow_id",
        "event_id",
        "event_type",
        "event_schema_version",
        "correlation_id",
        "attempt_number",
        "payload",
    }
    if not isinstance(value, dict) or not required.issubset(value):
        raise ContractError("Task is missing required fields.")
    try:
        uuid.UUID(str(value["workflow_id"]))
        uuid.UUID(str(value["event_id"]))
    except (TypeError, ValueError):
        raise ContractError("Task identifiers are invalid.") from None
    if (
        value["task_version"] != 1
        or value["event_schema_version"] != 1
        or value["event_type"] != DOMAIN_EVENT_TYPE
        or not isinstance(value["correlation_id"], str)
        or not 1 <= len(value["correlation_id"]) <= 128
        or type(value["attempt_number"]) is not int
        or not 1 <= value["attempt_number"] <= 100
        or not isinstance(value["payload"], dict)
    ):
        raise ContractError("Task fields are invalid.")
    request_id = value.get("request_id")
    if request_id is not None and (
        not isinstance(request_id, str) or not 1 <= len(request_id) <= 64
    ):
        raise ContractError("Task request ID is invalid.")


def encode_task(task):
    validate_workflow_task(task)
    encoded = json.dumps(task, separators=(",", ":"), sort_keys=True).encode("utf-8")
    if len(encoded) > MAX_MESSAGE_BYTES:
        raise ContractError("Task exceeds the configured size limit.")
    return encoded


def decode_task(raw):
    if not isinstance(raw, bytes) or len(raw) > MAX_MESSAGE_BYTES:
        raise ContractError("Task is empty or exceeds the size limit.")
    try:
        task = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise ContractError("Task is not valid UTF-8 JSON.") from None
    validate_workflow_task(task)
    return task
