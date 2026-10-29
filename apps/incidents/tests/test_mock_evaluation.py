import json
import time
from pathlib import Path

import pytest

from apps.incidents.providers.mock import DeterministicMockProvider
from apps.incidents.summary_schema import SummaryValidationError, validate_summary

DATASET = Path(__file__).parent / "fixtures" / "labeled_incidents.json"


@pytest.mark.parametrize(
    "case", json.loads(DATASET.read_text(encoding="utf-8")), ids=lambda case: case["case"]
)
def test_labeled_incident_dataset_quality(case):
    provider = DeterministicMockProvider()
    started = time.monotonic()
    response = provider.generate({"evidence": case["evidence"]})
    latency_ms = (time.monotonic() - started) * 1000
    validated = validate_summary(response.content, {"evidence": case["evidence"]})

    cited = {
        evidence_id
        for item in [*validated["confirmed_facts"], *validated["hypotheses"]]
        for evidence_id in item["evidence_ids"]
    }
    expected = set(case["expected_evidence_ids"])
    coverage = len(cited & expected) / len(expected) if expected else 1.0
    text_output = " ".join(
        [validated["headline"]]
        + [item["statement"] for item in validated["confirmed_facts"]]
        + [item["statement"] for item in validated["hypotheses"]]
        + validated["unknowns"]
        + validated["recommended_checks"]
    ).casefold()
    unsupported_claims = sum(
        phrase.casefold() in text_output for phrase in case["unsupported_claim_phrases"]
    )

    assert coverage >= 0.8
    assert unsupported_claims == 0
    assert latency_ms < 1000
    assert response.provider == "mock"
    assert validated["insufficient_evidence"] is (case["case"] == "insufficient_evidence")
    if case["case"] == "prompt_injection_log":
        assert "successful" not in validated["headline"].lower()
        assert all(
            case["untrusted_log"] not in item["statement"] for item in validated["confirmed_facts"]
        )


def test_schema_rejects_unknown_evidence_references():
    bundle = {
        "evidence": [
            {
                "id": "attempt:known",
                "kind": "workflow_attempt",
                "data": {"error_code": "X", "outcome": "FAILED"},
            }
        ]
    }
    response = DeterministicMockProvider().generate(bundle).content
    response["confirmed_facts"].append(
        {"statement": "Unsupported statement", "evidence_ids": ["attempt:invented"]}
    )
    with pytest.raises(SummaryValidationError, match="evidence"):
        validate_summary(response, bundle)


def test_insufficient_evidence_requires_explicit_unknown():
    bundle = {"evidence": [{"id": "workflow:one", "kind": "workflow_state", "data": {}}]}
    response = DeterministicMockProvider().generate(bundle).content
    response["headline"] = "The worker crashed."
    response["insufficient_evidence"] = False
    with pytest.raises(SummaryValidationError, match="Insufficient evidence"):
        validate_summary(response, bundle)
