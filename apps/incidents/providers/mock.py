"""Deterministic evidence-aware provider used by tests and local development."""

import time

from .base import ProviderResult


class DeterministicMockProvider:
    name = "mock"
    model = "eventflow-incident-mock-v1"

    def generate(self, evidence_bundle):
        started = time.monotonic()
        items = evidence_bundle.get("evidence", [])
        known = {item["id"] for item in items}
        attempts = [item for item in items if item.get("kind") == "workflow_attempt"]
        workflow = next((item for item in items if item.get("kind") == "workflow_state"), None)
        facts = []
        hypotheses = []
        unknowns = []
        checks = []
        if workflow:
            state = workflow["data"].get("state", "unknown")
            stage = workflow["data"].get("failed_stage", "unknown")
            facts.append(
                {
                    "statement": f"Workflow state is {state} at stage {stage}.",
                    "evidence_ids": [workflow["id"]],
                }
            )

        failure_attempts = [
            item
            for item in attempts
            if item["data"].get("error_code")
            or item["data"].get("outcome") in {"FAILED", "DEAD_LETTERED"}
        ]
        if failure_attempts:
            codes = [item["data"].get("error_code", "") for item in failure_attempts]
            ids = [item["id"] for item in failure_attempts]
            counts = {code: codes.count(code) for code in set(codes) if code}
            repeated_timeout = any(
                "TIMEOUT" in code.upper() and count > 1 for code, count in counts.items()
            )
            if repeated_timeout:
                hypotheses.append(
                    {
                        "statement": (
                            "Repeated timeouts occurred during the recorded attempts; "
                            "the underlying cause is not established by these records."
                        ),
                        "evidence_ids": ids,
                        "confidence": 0.75,
                    }
                )
            else:
                error_codes = ", ".join(
                    sorted(set(code for code in codes if code)) or ["unspecified"]
                )
                facts.append(
                    {
                        "statement": (
                            f"The recorded failing attempt(s) include error code(s): {error_codes}."
                        ),
                        "evidence_ids": ids,
                    }
                )
                hypotheses.append(
                    {
                        "statement": (
                            "The recorded attempt error is a likely contributor, but evidence "
                            "does not establish an external root cause."
                        ),
                        "evidence_ids": ids,
                        "confidence": 0.55,
                    }
                )
            checks.append(
                "Review the stage logs and dependency telemetry for the cited attempt timestamps."
            )
        else:
            unknowns.append(
                "No failed attempt with an error code or failure outcome is present "
                "in the evidence."
            )
            checks.append(
                "Collect the worker attempt and sanitized error details for the failed stage."
            )

        compensation = next(
            (item for item in items if item.get("kind") == "compensation_summary"), None
        )
        if compensation and compensation["data"].get("count"):
            succeeded = compensation["data"].get("succeeded", 0)
            facts.append(
                {
                    "statement": (
                        f"Compensation actions recorded: {compensation['data']['count']}; "
                        f"succeeded: {succeeded}."
                    ),
                    "evidence_ids": [compensation["id"]],
                }
            )
            checks.append(
                "Confirm reserved inventory and payment status match the compensation outcome."
            )

        metrics = next(
            (item for item in items if item.get("kind") == "health_metrics_availability"), None
        )
        if metrics and not metrics["data"].get("available"):
            unknowns.append(
                "Workflow-correlated health metrics are unavailable; dependency "
                "health is unconfirmed."
            )
        insufficient = not failure_attempts
        if insufficient:
            headline = "Insufficient evidence to determine why this workflow failed."
        elif any(
            "TIMEOUT" in item["data"].get("error_code", "").upper() for item in failure_attempts
        ):
            headline = (
                "The workflow recorded timeout failures; the underlying cause remains unconfirmed."
            )
        else:
            headline = (
                "The workflow failed with a recorded stage error; more evidence is needed "
                "to confirm root cause."
            )

        # The mock checks its own citations through the same strict app validator in service code.
        result = {
            "headline": headline,
            "confirmed_facts": facts,
            "hypotheses": hypotheses,
            "unknowns": unknowns,
            "recommended_checks": checks,
            "insufficient_evidence": insufficient,
        }
        for statement in facts:
            statement["evidence_ids"] = [ref for ref in statement["evidence_ids"] if ref in known]
        for statement in hypotheses:
            statement["evidence_ids"] = [ref for ref in statement["evidence_ids"] if ref in known]
        return ProviderResult(
            content=result,
            provider=self.name,
            model=self.model,
            latency_ms=max(0, int((time.monotonic() - started) * 1000)),
            input_tokens=None,
            output_tokens=None,
        )
