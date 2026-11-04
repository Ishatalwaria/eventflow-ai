"""Bounded, tenant-independent evidence extraction for one workflow."""

import hashlib
import json
import re
from datetime import timedelta

from apps.processing.models import ProcessingLog
from apps.workflows.models import Workflow, WorkflowAttempt

EVIDENCE_WINDOW = timedelta(hours=24)
MAX_ATTEMPTS = 20
MAX_LOGS = 18
MAX_EVIDENCE_ITEMS = 40
MAX_TEXT_LENGTH = 300

_SECRET_PATTERN = re.compile(
    r"(?i)\b(password|passwd|secret|api[_-]?key|access[_-]?token|refresh[_-]?token)"
    r"\s*[:=]\s*([^\s,;]+)"
)
_BEARER_PATTERN = re.compile(r"(?i)\b(bearer\s+)[A-Za-z0-9._~+/-]+=*")
_AUTH_HEADER_PATTERN = re.compile(r"(?i)(authorization\s*[:=]\s*)[^,;]+")
_EMAIL_PATTERN = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
_PHONE_PATTERN = re.compile(r"(?<!\w)(?:\+?\d[\d .()/-]{7,}\d)(?!\w)")
_CONTROL_PATTERN = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def sanitize_text(value: str, *, max_length: int = MAX_TEXT_LENGTH) -> str:
    """Remove common credentials and personal identifiers from untrusted text."""
    text = str(value)
    text = _CONTROL_PATTERN.sub(" ", text)
    text = _SECRET_PATTERN.sub(lambda match: f"{match.group(1)}=[REDACTED]", text)
    text = _BEARER_PATTERN.sub(r"\1[REDACTED]", text)
    text = _AUTH_HEADER_PATTERN.sub(r"\1[REDACTED]", text)
    text = _EMAIL_PATTERN.sub("[REDACTED_EMAIL]", text)
    text = _PHONE_PATTERN.sub("[REDACTED_PHONE]", text)
    text = " ".join(text.split())
    if len(text) > max_length:
        text = text[: max_length - 1] + "…"
    return text


def _iso(value):
    return value.isoformat() if value else None


def _attempt_evidence(attempt):
    return {
        "id": f"attempt:{attempt.id}",
        "kind": "workflow_attempt",
        "data": {
            "stage": sanitize_text(attempt.stage),
            "direction": attempt.direction,
            "attempt_number": attempt.attempt_number,
            "outcome": attempt.outcome,
            "started_at": _iso(attempt.started_at),
            "finished_at": _iso(attempt.finished_at),
            "duration_ms": attempt.duration_ms,
            "error_code": sanitize_text(attempt.error_code) if attempt.error_code else "",
            "error_detail": sanitize_text(attempt.error_detail) if attempt.error_detail else "",
        },
    }


def _log_evidence(log):
    attributes = {}
    for key in ("stage", "direction", "error_code"):
        value = log.attributes.get(key) if isinstance(log.attributes, dict) else None
        if isinstance(value, str):
            attributes[key] = sanitize_text(value, max_length=100)
    return {
        "id": f"log:{log.id}",
        "kind": "processing_log",
        "data": {
            "level": log.level,
            "created_at": _iso(log.created_at),
            "message": sanitize_text(log.message),
            "attributes": attributes,
        },
    }


def build_workflow_evidence(workflow: Workflow) -> dict:
    """Build a small evidence bundle; event payload and arbitrary log attrs are excluded."""
    anchor = workflow.finished_at or workflow.updated_at
    start = anchor - EVIDENCE_WINDOW
    end = anchor + timedelta(minutes=1)

    evidence = [
        {
            "id": f"workflow:{workflow.id}",
            "kind": "workflow_state",
            "data": {
                "state": workflow.state,
                "workflow_type": sanitize_text(workflow.workflow_type),
                "failed_stage": workflow.current_stage,
                "created_at": _iso(workflow.created_at),
                "updated_at": _iso(workflow.updated_at),
                "finished_at": _iso(workflow.finished_at),
                "last_error_code": sanitize_text(workflow.last_error_code)
                if workflow.last_error_code
                else "",
            },
        },
        {
            "id": f"event:{workflow.event_id}",
            "kind": "related_event",
            "data": {
                "event_id": str(workflow.event_id),
                "event_type": sanitize_text(workflow.event.event_type),
                "correlation_id": sanitize_text(workflow.event.correlation_id),
                "request_id": sanitize_text(workflow.event.request_id),
                "received_at": _iso(workflow.event.received_at),
                "occurred_at": _iso(workflow.event.occurred_at),
            },
        },
    ]

    attempts = list(
        WorkflowAttempt.objects.filter(
            workflow=workflow,
            started_at__gte=start,
            started_at__lte=end,
        ).order_by("attempt_number", "started_at", "id")[: MAX_ATTEMPTS + 1]
    )
    attempt_truncated = len(attempts) > MAX_ATTEMPTS
    included_attempts = attempts[:MAX_ATTEMPTS]
    for attempt in included_attempts:
        evidence.append(_attempt_evidence(attempt))
    compensations = [
        attempt
        for attempt in included_attempts
        if attempt.direction == WorkflowAttempt.Direction.COMPENSATE
    ]
    evidence.append(
        {
            "id": f"compensation:{workflow.id}",
            "kind": "compensation_summary",
            "data": {
                "count": len(compensations),
                "succeeded": sum(
                    1
                    for attempt in compensations
                    if attempt.outcome == WorkflowAttempt.Outcome.SUCCEEDED
                ),
                "stages": [attempt.stage for attempt in compensations],
            },
        }
    )

    # Reserve one slot for the health-metric availability fact.
    remaining_logs = max(0, MAX_EVIDENCE_ITEMS - 1 - len(evidence))
    log_limit = min(MAX_LOGS, remaining_logs)
    logs = list(
        ProcessingLog.objects.filter(
            workflow=workflow,
            created_at__gte=start,
            created_at__lte=end,
        ).order_by("created_at", "id")[: log_limit + 1]
    )
    log_truncated = len(logs) > log_limit
    for log in logs[:log_limit]:
        evidence.append(_log_evidence(log))

    metrics_present = False  # No workflow-correlated health metric source is integrated in M1–M3.
    evidence.append(
        {
            "id": f"health-metrics:{workflow.id}",
            "kind": "health_metrics_availability",
            "data": {
                "available": metrics_present,
                "detail": (
                    "No workflow-correlated health metrics are available in the configured sources."
                ),
            },
        }
    )
    bundle = {
        "workflow_id": str(workflow.id),
        "time_window": {"start": _iso(start), "end": _iso(end)},
        "truncated": attempt_truncated or log_truncated,
        "evidence": evidence[:MAX_EVIDENCE_ITEMS],
    }
    bundle["evidence_hash"] = hash_evidence(bundle)
    return bundle


def hash_evidence(bundle: dict) -> str:
    canonical = {key: value for key, value in bundle.items() if key != "evidence_hash"}
    serialized = json.dumps(canonical, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()
