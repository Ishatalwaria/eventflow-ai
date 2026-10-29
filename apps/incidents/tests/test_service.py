from unittest.mock import Mock

import pytest
from django.contrib.auth.hashers import make_password
from django.utils import timezone

from apps.common.models import APIClient
from apps.events.models import Event
from apps.incidents.providers.base import ProviderResult, TransientProviderError
from apps.incidents.service import create_incident_summary
from apps.workflows.models import Workflow, WorkflowAttempt

pytestmark = pytest.mark.django_db


def test_transient_provider_failure_is_retried_with_a_bounded_attempt_count():
    client = APIClient.objects.create(name="retry", secret_hash=make_password("credential"))
    event = Event.objects.create(
        client=client,
        event_type="order.created",
        schema_version=1,
        source="test",
        idempotency_key="retry-service",
        occurred_at=timezone.now(),
        correlation_id="corr-retry-service",
        request_id="req-retry-service",
        payload={},
    )
    workflow = Workflow.objects.create(
        event=event,
        state=Workflow.State.FAILED,
        current_stage="worker",
        last_error_code="WORKER_ERROR",
    )
    WorkflowAttempt.objects.create(
        workflow=workflow,
        stage="worker",
        attempt_number=1,
        outcome=WorkflowAttempt.Outcome.FAILED,
        started_at=timezone.now(),
        error_code="WORKER_ERROR",
    )
    provider = Mock()
    provider.generate.side_effect = [
        TransientProviderError("network issue"),
        ProviderResult(
            content={
                "headline": "The workflow failed with a recorded stage error.",
                "confirmed_facts": [
                    {
                        "statement": "Workflow state is FAILED.",
                        "evidence_ids": [f"workflow:{workflow.pk}"],
                    }
                ],
                "hypotheses": [],
                "unknowns": [],
                "recommended_checks": ["Review the failed attempt details."],
                "insufficient_evidence": False,
            },
            provider="test",
            model="test-model",
            latency_ms=1,
        ),
    ]

    record = create_incident_summary(workflow, client, provider=provider)

    assert provider.generate.call_count == 2
    assert record.provider == "test"
    assert record.summary["confirmed_facts"][0]["evidence_ids"] == [f"workflow:{workflow.pk}"]
