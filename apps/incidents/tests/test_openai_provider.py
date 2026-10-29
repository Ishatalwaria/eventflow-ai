import json
from io import BytesIO
from unittest.mock import patch
from urllib.error import HTTPError

import pytest

from apps.incidents.providers.base import PermanentProviderError, TransientProviderError
from apps.incidents.providers.openai import OpenAIResponsesProvider


def response_body(content):
    return json.dumps(
        {
            "model": "model-test",
            "output": [
                {
                    "type": "message",
                    "content": [{"type": "output_text", "text": json.dumps(content)}],
                }
            ],
            "usage": {"input_tokens": 22, "output_tokens": 18},
        }
    ).encode()


class FakeResponse(BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.close()


def test_openai_adapter_sends_only_evidence_and_disables_tools():
    provider = OpenAIResponsesProvider(
        api_key="secret-for-test", model="model-test", timeout=3, max_output_tokens=90
    )
    expected = {
        "headline": "Insufficient evidence to determine why this workflow failed.",
        "confirmed_facts": [],
        "hypotheses": [],
        "unknowns": ["Not enough records."],
        "recommended_checks": [],
        "insufficient_evidence": True,
    }
    evidence = {"workflow_id": "wf-id", "evidence": []}
    with patch(
        "apps.incidents.providers.openai.urlopen",
        return_value=FakeResponse(response_body(expected)),
    ) as send:
        result = provider.generate(evidence)
    req = send.call_args.args[0]
    body = json.loads(req.data)
    assert req.full_url == "https://api.openai.com/v1/responses"
    assert req.get_header("Authorization") == "Bearer secret-for-test"
    assert body["tools"] == []
    assert body["store"] is False
    assert body["max_output_tokens"] == 90
    assert json.loads(body["input"]) == evidence
    assert result.content == expected
    assert result.input_tokens == 22
    assert result.output_tokens == 18


def test_openai_adapter_classifies_transient_and_permanent_http_errors():
    provider = OpenAIResponsesProvider(api_key="test", model="model-test")
    with patch(
        "apps.incidents.providers.openai.urlopen",
        side_effect=HTTPError("url", 429, "busy", {}, None),
    ):
        with pytest.raises(TransientProviderError) as exc_info:
            provider.generate({"evidence": []})
        assert exc_info.value.error_code == "OPENAI_RATE_LIMITED"
    with patch(
        "apps.incidents.providers.openai.urlopen",
        side_effect=HTTPError("url", 401, "bad key", {}, None),
    ):
        with pytest.raises(PermanentProviderError) as exc_info:
            provider.generate({"evidence": []})
        assert exc_info.value.error_code == "OPENAI_AUTH_REJECTED"


@pytest.mark.parametrize(
    "provider_error, expected_code",
    [
        (
            {"type": "insufficient_quota", "code": "credit_balance_exhausted"},
            "OPENAI_QUOTA_EXHAUSTED",
        ),
        ({"type": "rate_limit_error", "code": "rate_limit_exceeded"}, "OPENAI_RATE_LIMITED"),
    ],
)
def test_openai_adapter_distinguishes_quota_exhaustion_from_transient_rate_limit(
    provider_error, expected_code
):
    provider = OpenAIResponsesProvider(api_key="test", model="model-test")
    http_error = HTTPError(
        "https://api.openai.com/v1/responses",
        429,
        "rate limited",
        {},
        BytesIO(json.dumps({"error": provider_error}).encode()),
    )
    with patch("apps.incidents.providers.openai.urlopen", side_effect=http_error):
        expected_exception = (
            PermanentProviderError
            if expected_code == "OPENAI_QUOTA_EXHAUSTED"
            else TransientProviderError
        )
        with pytest.raises(expected_exception) as exc_info:
            provider.generate({"evidence": []})
    assert exc_info.value.error_code == expected_code


def test_openai_adapter_rejects_invalid_provider_response():
    provider = OpenAIResponsesProvider(api_key="test", model="model-test")
    with patch("apps.incidents.providers.openai.urlopen", return_value=FakeResponse(b"{}")):
        with pytest.raises(PermanentProviderError):
            provider.generate({"evidence": []})
