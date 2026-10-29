"""OpenAI Responses API adapter using structured output and no tools."""

import json
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from django.conf import settings

from .base import PermanentProviderError, ProviderResult, TransientProviderError
from .contract import OUTPUT_SCHEMA, SYSTEM_INSTRUCTIONS


class OpenAIResponsesProvider:
    name = "openai"

    def __init__(self, *, api_key=None, model=None, timeout=None, max_output_tokens=None):
        self.api_key = api_key if api_key is not None else settings.OPENAI_API_KEY
        self.model = model or settings.OPENAI_MODEL
        self.timeout = timeout or settings.INCIDENT_LLM_TIMEOUT_SECONDS
        self.max_output_tokens = max_output_tokens or settings.INCIDENT_LLM_MAX_OUTPUT_TOKENS
        if not self.api_key:
            raise PermanentProviderError(
                "Incident provider credentials are not configured.",
                error_code="OPENAI_API_KEY_MISSING",
            )

    def generate(self, evidence_bundle):
        payload = {
            "model": self.model,
            "instructions": SYSTEM_INSTRUCTIONS,
            "input": json.dumps(evidence_bundle, ensure_ascii=False, separators=(",", ":")),
            "max_output_tokens": self.max_output_tokens,
            "store": False,
            "tools": [],
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "incident_summary",
                    "strict": True,
                    "schema": OUTPUT_SCHEMA,
                }
            },
        }
        request = Request(
            "https://api.openai.com/v1/responses",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            method="POST",
        )
        started = time.monotonic()
        try:
            with urlopen(request, timeout=self.timeout) as response:
                body = response.read(256_001)
        except HTTPError as exc:
            if exc.code == 429:
                try:
                    provider_error = json.loads(exc.read(16_384)).get("error", {})
                except (ValueError, AttributeError):
                    provider_error = {}
                provider_code = provider_error.get("code")
                provider_type = provider_error.get("type")
                if (
                    provider_code
                    in {
                        "credit_balance_exhausted",
                        "insufficient_quota",
                        "billing_hard_limit_reached",
                    }
                    or provider_type == "insufficient_quota"
                ):
                    raise PermanentProviderError(
                        "Incident provider quota is exhausted.",
                        error_code="OPENAI_QUOTA_EXHAUSTED",
                    ) from None
                raise TransientProviderError(
                    "Incident provider temporarily unavailable.",
                    error_code="OPENAI_RATE_LIMITED",
                ) from None
            if exc.code == 408:
                raise TransientProviderError(
                    "Incident provider temporarily unavailable.", error_code="OPENAI_TIMEOUT"
                ) from None
            if exc.code == 409 or exc.code >= 500:
                raise TransientProviderError(
                    "Incident provider temporarily unavailable.",
                    error_code="OPENAI_SERVER_ERROR",
                ) from None
            error_code = (
                "OPENAI_AUTH_REJECTED" if exc.code in {401, 403} else "OPENAI_REQUEST_REJECTED"
            )
            raise PermanentProviderError(
                "Incident provider rejected the request.", error_code=error_code
            ) from None
        except (URLError, TimeoutError, OSError) as exc:
            reason = getattr(exc, "reason", None)
            error_code = (
                "OPENAI_TIMEOUT"
                if isinstance(exc, TimeoutError) or isinstance(reason, TimeoutError)
                else "OPENAI_NETWORK_ERROR"
            )
            raise TransientProviderError(
                "Incident provider temporarily unavailable.", error_code=error_code
            ) from None
        if len(body) > 256_000:
            raise PermanentProviderError(
                "Incident provider response exceeded the size limit.",
                error_code="OPENAI_RESPONSE_TOO_LARGE",
            )
        try:
            response_data = json.loads(body)
            text = next(
                part["text"]
                for item in response_data["output"]
                if item.get("type") == "message"
                for part in item.get("content", [])
                if part.get("type") == "output_text"
            )
            content = json.loads(text)
        except (ValueError, KeyError, TypeError, StopIteration):
            raise PermanentProviderError(
                "Incident provider returned an invalid structured response.",
                error_code="OPENAI_INVALID_RESPONSE",
            ) from None
        usage = response_data.get("usage") or {}
        return ProviderResult(
            content=content,
            provider=self.name,
            model=response_data.get("model", self.model),
            latency_ms=max(0, int((time.monotonic() - started) * 1000)),
            input_tokens=usage.get("input_tokens"),
            output_tokens=usage.get("output_tokens"),
        )
