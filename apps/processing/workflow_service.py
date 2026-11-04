"""Compatibility facade. Saga execution lives in apps.processing.saga.engine."""

from apps.processing.errors import PermanentProcessingError, TransientProcessingError
from apps.processing.saga.engine import (
    ALLOWED_TRANSITIONS,
    TERMINAL_STATES,
    ProcessingDecision,
    process_workflow_task,
)

__all__ = [
    "ALLOWED_TRANSITIONS",
    "TERMINAL_STATES",
    "PermanentProcessingError",
    "ProcessingDecision",
    "TransientProcessingError",
    "process_workflow_task",
]
