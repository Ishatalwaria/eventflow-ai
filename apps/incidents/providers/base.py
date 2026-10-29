from dataclasses import dataclass
from typing import Protocol


class TransientProviderError(RuntimeError):
    """Provider failure eligible for bounded retry."""

    def __init__(self, message, *, error_code="PROVIDER_TEMPORARY_FAILURE"):
        super().__init__(message)
        self.error_code = error_code


class PermanentProviderError(RuntimeError):
    """Provider failure that should not be retried."""

    def __init__(self, message, *, error_code="PROVIDER_REQUEST_REJECTED"):
        super().__init__(message)
        self.error_code = error_code


@dataclass(frozen=True)
class ProviderResult:
    content: dict
    provider: str
    model: str
    latency_ms: int
    input_tokens: int | None = None
    output_tokens: int | None = None


class IncidentProvider(Protocol):
    def generate(self, evidence_bundle: dict) -> ProviderResult: ...
