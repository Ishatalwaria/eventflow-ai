import json
from io import BytesIO
from unittest.mock import patch
from urllib.error import HTTPError, URLError

import pytest

from apps.incidents.providers.base import PermanentProviderError, TransientProviderError
from apps.incidents.providers.gemini import GeminiProvider
from apps.incidents.service import get_provider


class FakeResponse(BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.close()


def gemini_body(summary):
    return json.dumps(
        {
            "modelVersion": "gemini-test-version",
            "candidates": [
                {"content": {"parts": [{"text": json.dumps(summary)}]}, "finishReason": "STOP"}
            ],
            "usageMetadata": {"promptTokenCount": 27, "candidatesTokenCount": 19},
        }
    ).encode()


def valid_summary():
    return {
        "headline": "Insufficient evidence to determine why this workflow failed.",
        "confirmed_facts": [],
        "hypotheses": [],
        "unknowns": ["Not enough records."],
        "recommended_checks": [],
        "insufficient_evidence": True,
    }


def test_gemini_adapter_uses_key_header_schema_and_no_tools():
    provider = GeminiProvider(
        api_key="gemini-test-secret", model="gemini-test", timeout=4, max_output_tokens=77
    )
    evidence = {"workflow_id": "workflow-test", "evidence": [{"id": "event:test"}]}
    with patch(
        "apps.incidents.providers.gemini.urlopen",
        return_value=FakeResponse(gemini_body(valid_summary())),
    ) as send:
        result = provider.generate(evidence)

    request = send.call_args.args[0]
    payload = json.loads(request.data)
    assert request.full_url.endswith("/v1beta/models/gemini-test:generateContent")
    assert request.get_header("X-goog-api-key") == "gemini-test-secret"
    assert payload["systemInstruction"]["parts"][0]["text"]
    assert json.loads(payload["contents"][0]["parts"][0]["text"]) == evidence
    assert payload["generationConfig"]["maxOutputTokens"] == 77
    assert payload["generationConfig"]["responseFormat"]["text"]["mimeType"] == "APPLICATION_JSON"
    assert payload["generationConfig"]["responseFormat"]["text"]["schema"]["type"] == "object"
    assert "tools" not in payload
    assert result.content == valid_summary()
    assert result.provider == "gemini"
    assert result.model == "gemini-test-version"
    assert result.input_tokens == 27
    assert result.output_tokens == 19


def test_gemini_2x_uses_compatible_structured_json_configuration():
    provider = GeminiProvider(api_key="test", model="gemini-2.5-flash")
    with patch(
        "apps.incidents.providers.gemini.urlopen",
        return_value=FakeResponse(gemini_body(valid_summary())),
    ) as send:
        provider.generate({"evidence": []})

    generation_config = json.loads(send.call_args.args[0].data)["generationConfig"]
    assert generation_config["responseMimeType"] == "application/json"
    assert generation_config["responseJsonSchema"]["type"] == "object"
    assert "responseFormat" not in generation_config


def test_gemini_3x_uses_low_thinking_level_for_latency():
    provider = GeminiProvider(api_key="test", model="gemini-3.8-flash")
    with patch(
        "apps.incidents.providers.gemini.urlopen",
        return_value=FakeResponse(gemini_body(valid_summary())),
    ) as send:
        provider.generate({"evidence": []})

    generation_config = json.loads(send.call_args.args[0].data)["generationConfig"]
    assert generation_config["thinkingConfig"] == {"thinkingLevel": "LOW"}


@pytest.mark.parametrize(
    "status, provider_status, exception_type, error_code",
    [
        (429, "RESOURCE_EXHAUSTED", TransientProviderError, "GEMINI_RATE_LIMITED"),
        (503, "UNAVAILABLE", TransientProviderError, "GEMINI_SERVER_ERROR"),
        (401, "UNAUTHENTICATED", PermanentProviderError, "GEMINI_AUTH_REJECTED"),
        (402, "RESOURCE_EXHAUSTED", PermanentProviderError, "GEMINI_QUOTA_EXHAUSTED"),
        (400, "INVALID_ARGUMENT", PermanentProviderError, "GEMINI_INVALID_REQUEST"),
        (404, "NOT_FOUND", PermanentProviderError, "GEMINI_MODEL_NOT_FOUND"),
    ],
)
def test_gemini_adapter_classifies_provider_errors(
    status, provider_status, exception_type, error_code
):
    error = HTTPError(
        "https://generativelanguage.googleapis.com/generateContent",
        status,
        "provider failure",
        {},
        BytesIO(json.dumps({"error": {"status": provider_status}}).encode()),
    )
    provider = GeminiProvider(api_key="test", model="model-test")
    with patch("apps.incidents.providers.gemini.urlopen", side_effect=error):
        with pytest.raises(exception_type) as exc_info:
            provider.generate({"evidence": []})
    assert exc_info.value.error_code == error_code


def test_gemini_adapter_rejects_invalid_or_oversized_response():
    provider = GeminiProvider(api_key="test", model="model-test")
    with patch("apps.incidents.providers.gemini.urlopen", return_value=FakeResponse(b"{}")):
        with pytest.raises(PermanentProviderError) as exc_info:
            provider.generate({"evidence": []})
    assert exc_info.value.error_code == "GEMINI_INVALID_RESPONSE"

    with patch(
        "apps.incidents.providers.gemini.urlopen",
        return_value=FakeResponse(b"x" * 256_001),
    ):
        with pytest.raises(PermanentProviderError) as exc_info:
            provider.generate({"evidence": []})
    assert exc_info.value.error_code == "GEMINI_RESPONSE_TOO_LARGE"


def test_gemini_adapter_requires_a_key():
    with pytest.raises(PermanentProviderError) as exc_info:
        GeminiProvider(api_key="", model="model-test")
    assert exc_info.value.error_code == "GEMINI_API_KEY_MISSING"


def test_gemini_adapter_converts_network_timeouts_to_transient_errors():
    provider = GeminiProvider(api_key="test", model="model-test")
    with patch(
        "apps.incidents.providers.gemini.urlopen",
        side_effect=URLError(TimeoutError("socket timeout")),
    ):
        with pytest.raises(TransientProviderError) as exc_info:
            provider.generate({"evidence": []})
    assert exc_info.value.error_code == "GEMINI_TIMEOUT"


def test_gemini_adapter_fails_over_to_low_latency_model_after_timeout(settings):
    settings.GEMINI_FALLBACK_MODEL = "gemini-3.5-flash-lite"
    provider = GeminiProvider(api_key="test", model="gemini-3.8-flash", timeout=5)
    with patch(
        "apps.incidents.providers.gemini.urlopen",
        side_effect=[
            URLError(TimeoutError("socket timeout")),
            FakeResponse(gemini_body(valid_summary())),
        ],
    ) as send:
        result = provider.generate({"evidence": []})

    assert send.call_count == 2
    assert "/models/gemini-3.8-flash:generateContent" in send.call_args_list[0].args[0].full_url
    assert (
        "/models/gemini-3.5-flash-lite:generateContent" in send.call_args_list[1].args[0].full_url
    )
    assert result.content == valid_summary()


def test_gemini_adapter_does_not_retry_same_model_when_fallback_times_out(settings):
    settings.GEMINI_FALLBACK_MODEL = "gemini-3.5-flash-lite"
    provider = GeminiProvider(api_key="test", model="gemini-3.8-flash")
    with patch(
        "apps.incidents.providers.gemini.urlopen",
        side_effect=URLError(TimeoutError("socket timeout")),
    ) as send:
        with pytest.raises(TransientProviderError) as exc_info:
            provider.generate({"evidence": []})

    assert exc_info.value.error_code == "GEMINI_TIMEOUT"
    assert send.call_count == 2


def test_service_selects_gemini_provider_when_configured(settings):
    settings.INCIDENT_LLM_PROVIDER = "gemini"
    settings.GEMINI_API_KEY = "test-gemini-key"
    settings.GEMINI_MODEL = "gemini-test"

    provider = get_provider()

    assert isinstance(provider, GeminiProvider)
