"""Strict validation for provider output; no unsupported evidence references pass."""

MAX_HEADLINE_LENGTH = 240
MAX_STATEMENTS = 12
MAX_STATEMENT_LENGTH = 500
MAX_UNKNOWN_OR_CHECK_LENGTH = 300


class SummaryValidationError(ValueError):
    pass


def evidence_ids(bundle):
    return {item["id"] for item in bundle.get("evidence", []) if isinstance(item, dict)}


def evidence_is_insufficient(bundle):
    items = bundle.get("evidence", [])
    attempts = [item for item in items if item.get("kind") == "workflow_attempt"]
    has_failure_detail = any(
        item["data"].get("error_code") or item["data"].get("outcome") in {"FAILED", "DEAD_LETTERED"}
        for item in attempts
    )
    has_error_log = any(
        item.get("kind") == "processing_log" and item.get("data", {}).get("level") == "ERROR"
        for item in items
    )
    return len(items) < 3 or not (has_failure_detail or has_error_log)


def _validate_statements(value, *, known_ids, hypotheses=False):
    if not isinstance(value, list) or len(value) > MAX_STATEMENTS:
        raise SummaryValidationError("Statement list is invalid or too large.")
    output = []
    for item in value:
        if not isinstance(item, dict):
            raise SummaryValidationError("Statement entry must be an object.")
        expected = (
            {"statement", "evidence_ids", "confidence"}
            if hypotheses
            else {
                "statement",
                "evidence_ids",
            }
        )
        if set(item) != expected:
            raise SummaryValidationError("Statement entry has unexpected or missing fields.")
        statement = item["statement"]
        refs = item["evidence_ids"]
        if (
            not isinstance(statement, str)
            or not statement.strip()
            or len(statement) > MAX_STATEMENT_LENGTH
            or not isinstance(refs, list)
            or not refs
            or len(refs) > 8
            or any(not isinstance(ref, str) or ref not in known_ids for ref in refs)
            or len(set(refs)) != len(refs)
        ):
            raise SummaryValidationError("Statement has invalid text or evidence references.")
        result = {"statement": statement.strip(), "evidence_ids": refs}
        if hypotheses:
            confidence = item["confidence"]
            if type(confidence) not in {int, float} or not 0 <= confidence <= 1:
                raise SummaryValidationError("Hypothesis confidence must be between 0 and 1.")
            result["confidence"] = float(confidence)
        output.append(result)
    return output


def validate_summary(value, bundle):
    expected = {
        "headline",
        "confirmed_facts",
        "hypotheses",
        "unknowns",
        "recommended_checks",
        "insufficient_evidence",
    }
    if not isinstance(value, dict) or set(value) != expected:
        raise SummaryValidationError("Summary does not match the incident response schema.")
    headline = value["headline"]
    insufficient = value["insufficient_evidence"]
    if (
        not isinstance(headline, str)
        or not headline.strip()
        or len(headline) > MAX_HEADLINE_LENGTH
        or type(insufficient) is not bool
    ):
        raise SummaryValidationError("Summary headline or sufficiency flag is invalid.")
    known_ids = evidence_ids(bundle)
    facts = _validate_statements(value["confirmed_facts"], known_ids=known_ids)
    hypotheses = _validate_statements(value["hypotheses"], known_ids=known_ids, hypotheses=True)
    strings = {}
    for key in ("unknowns", "recommended_checks"):
        items = value[key]
        if (
            not isinstance(items, list)
            or len(items) > MAX_STATEMENTS
            or any(
                not isinstance(item, str)
                or not item.strip()
                or len(item) > MAX_UNKNOWN_OR_CHECK_LENGTH
                for item in items
            )
        ):
            raise SummaryValidationError(f"{key} is invalid or too large.")
        strings[key] = [item.strip() for item in items]
    if evidence_is_insufficient(bundle):
        if not insufficient or not headline.lower().startswith("insufficient evidence"):
            raise SummaryValidationError("Insufficient evidence must be stated explicitly.")
        if not strings["unknowns"]:
            raise SummaryValidationError("Insufficient evidence requires at least one unknown.")
    if insufficient and (
        not headline.lower().startswith("insufficient evidence") or not strings["unknowns"]
    ):
        raise SummaryValidationError(
            "An insufficient-evidence response must explain what is unknown."
        )
    return {
        "headline": headline.strip(),
        "confirmed_facts": facts,
        "hypotheses": hypotheses,
        "unknowns": strings["unknowns"],
        "recommended_checks": strings["recommended_checks"],
        "insufficient_evidence": insufficient,
    }
