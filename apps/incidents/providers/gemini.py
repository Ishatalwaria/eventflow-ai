"""Google Gemini GenerateContent REST adapter with structured JSON output."""

import json
import logging
import time
from http.client import HTTPException
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from django.conf import settings

from .base import PermanentProviderError, ProviderResult, TransientProviderError
from .contract import OUTPUT_SCHEMA, SYSTEM_INSTRUCTIONS

logger = logging.getLogger(__name__)


class GeminiProvider:
    name = "gemini"

    def __init__(self, *, api_key=None, model=None, timeout=None, max_output_tokens=None):
        self.api_key = api_key if api_key is not None else settings.GEMINI_API_KEY
        self.model = model or settings.GEMINI_MODEL
        self.fallback_model = settings.GEMINI_FALLBACK_MODEL
        self.timeout = timeout or settings.INCIDENT_LLM_TIMEOUT_SECONDS
        self.max_output_tokens = max_output_tokens or settings.INCIDENT_LLM_MAX_OUTPUT_TOKENS
        if not self.api_key:
            raise PermanentProviderError(
                "Gemini API credentials are not configured.", error_code="GEMINI_API_KEY_MISSING"
            )

    def generate(self, evidence_bundle):
        try:
            return self._generate_for_model(evidence_bundle, self.model)
        except TransientProviderError as exc:
            if exc.error_code != "GEMINI_TIMEOUT" or self.model == self.fallback_model:
                raise
            logger.warning(
                "Gemini primary model timed out; trying configured fallback model=%s",
                self.fallback_model,
            )
            return self._generate_for_model(evidence_bundle, self.fallback_model)

    def _generate_for_model(self, evidence_bundle, model):
        payload = {
            "systemInstruction": {"parts": [{"text": SYSTEM_INSTRUCTIONS}]},
            "contents": [
                {
                    "role": "user",
                    "parts": [
                        {
                            "text": json.dumps(
                                evidence_bundle, ensure_ascii=False, separators=(",", ":")
                            )
                        }
                    ],
                }
            ],
            "generationConfig": {"maxOutputTokens": self.max_output_tokens},
        }
        if model.startswith("gemini-2."):
            payload["generationConfig"].update(
                {"responseMimeType": "application/json", "responseJsonSchema": OUTPUT_SCHEMA}
            )
        else:
            payload["generationConfig"]["responseFormat"] = {
                "text": {"mimeType": "APPLICATION_JSON", "schema": OUTPUT_SCHEMA}
            }
            if model.startswith(("gemini-3.", "gemini-4")):
                payload["generationConfig"]["thinkingConfig"] = {"thinkingLevel": "LOW"}
        escaped_model = quote(model, safe="-_.")
        request = Request(
            f"https://generativelanguage.googleapis.com/v1beta/models/{escaped_model}:generateContent",
            data=json.dumps(payload).encode("utf-8"),
            headers={"x-goog-api-key": self.api_key, "Content-Type": "application/json"},
            method="POST",
        )
        started = time.monotonic()
        try:
            with urlopen(request, timeout=self.timeout) as response:
                body = response.read(256_001)
        except HTTPError as exc:
            self._raise_http_error(exc)
        except (HTTPException, URLError, TimeoutError, OSError) as exc:
            reason = getattr(exc, "reason", None)
            error_code = (
                "GEMINI_TIMEOUT"
                if isinstance(exc, TimeoutError) or isinstance(reason, TimeoutError)
                else "GEMINI_NETWORK_ERROR"
            )
            raise TransientProviderError(
                "Gemini provider temporarily unavailable.", error_code=error_code
            ) from None
        if len(body) > 256_000:
            raise PermanentProviderError(
                "Gemini provider response exceeded the size limit.",
                error_code="GEMINI_RESPONSE_TOO_LARGE",
            )
        try:
            response_data = json.loads(body)
            candidate = response_data["candidates"][0]
            text = next(
                part["text"]
                for part in candidate["content"]["parts"]
                if isinstance(part.get("text"), str)
            )
            content = json.loads(text)
        except (ValueError, KeyError, TypeError, IndexError, StopIteration):
            raise PermanentProviderError(
                "Gemini provider returned an invalid structured response.",
                error_code="GEMINI_INVALID_RESPONSE",
            ) from None
        usage = response_data.get("usageMetadata") or {}
        return ProviderResult(
            content=content,
            provider=self.name,
            model=response_data.get("modelVersion", model),
            latency_ms=max(0, int((time.monotonic() - started) * 1000)),
            input_tokens=usage.get("promptTokenCount"),
            output_tokens=usage.get("candidatesTokenCount"),
        )

    @staticmethod
    def _raise_http_error(exc):
        try:
            body = json.loads(exc.read(16_384))
            provider_error = body.get("error", {})
        except (ValueError, AttributeError):
            provider_error = {}
        status = provider_error.get("status")
        if exc.code == 429 or exc.code in {408, 409} or exc.code >= 500:
            raise TransientProviderError(
                "Gemini provider temporarily unavailable.",
                error_code="GEMINI_RATE_LIMITED" if exc.code == 429 else "GEMINI_SERVER_ERROR",
            ) from None
        if exc.code == 402 or status == "RESOURCE_EXHAUSTED":
            raise PermanentProviderError(
                "Gemini provider billing quota is exhausted.",
                error_code="GEMINI_QUOTA_EXHAUSTED",
            ) from None
        error_code = "GEMINI_AUTH_REJECTED" if exc.code in {401, 403} else "GEMINI_REQUEST_REJECTED"
        if exc.code == 400 or status == "INVALID_ARGUMENT":
            error_code = "GEMINI_INVALID_REQUEST"
        elif exc.code == 404 or status == "NOT_FOUND":
            error_code = "GEMINI_MODEL_NOT_FOUND"
        raise PermanentProviderError(
            "Gemini provider rejected the request.", error_code=error_code
        ) from None
