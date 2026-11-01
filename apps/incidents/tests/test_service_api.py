import pytest
from django.contrib.auth.hashers import make_password
from rest_framework.test import APIClient as RestClient

from apps.common.models import APIClient
from apps.events.models import Event
from apps.incidents.models import IncidentSummary
from apps.incidents.providers.base import TransientProviderError
from apps.workflows.models import Workflow

pytestmark = pytest.mark.django_db


def make_workflow(client, *, state=Workflow.State.FAILED, key="incident-api"):
    event = Event.objects.create(
        client=client,
        event_type="order.created",
        schema_version=1,
        source="test",
        idempotency_key=key,
        occurred_at="2026-10-29T00:00:00Z",
        correlation_id=f"corr-{key}",
        request_id=f"req-{key}",
        payload={"sensitive": "not-for-evidence"},
    )
    return Workflow.objects.create(
        event=event,
        state=state,
        current_stage="order_validation",
        last_error_code="INVALID_ORDER",
    )


@pytest.fixture
def client_and_workflow():
    credential = "private-test-token"
    api_client = APIClient.objects.create(
        name="incident-api", secret_hash=make_password(credential)
    )
    workflow = make_workflow(api_client)
    return api_client, credential, workflow


def make_summary(workflow, requested_by, headline):
    return IncidentSummary.objects.create(
        workflow=workflow,
        requested_by=requested_by,
        evidence_hash="a" * 64,
        evidence={"workflow_id": str(workflow.pk), "evidence": []},
        summary={"headline": headline},
        prompt_version="test-v1",
        provider="test-provider",
        model="test-model",
        latency_ms=1,
    )


def test_summary_endpoint_authenticates_and_persists_evidence_and_provider_metadata(
    client_and_workflow,
):
    api_client, credential, workflow = client_and_workflow
    http = RestClient()

    response = http.post(
        f"/api/v1/workflows/{workflow.pk}/incident-summary",
        HTTP_AUTHORIZATION=f"Bearer {api_client.pk}.{credential}",
        format="json",
    )

    assert response.status_code == 201
    assert str(response.data["workflow_id"]) == str(workflow.pk)
    assert response.data["provider"] == "mock"
    assert response.data["summary"]["insufficient_evidence"] is True
    assert response.data["evidence_hash"]
    assert IncidentSummary.objects.count() == 1
    saved = IncidentSummary.objects.get()
    assert saved.requested_by_id == api_client.pk
    assert "not-for-evidence" not in str(saved.evidence)
    assert saved.prompt_version


def test_saved_incidents_can_be_listed_filtered_paginated_and_retrieved(client_and_workflow):
    api_client, credential, failed = client_and_workflow
    second_failed = make_workflow(api_client, key="incident-api-second")
    dead_lettered = make_workflow(
        api_client, state=Workflow.State.DEAD_LETTERED, key="incident-api-dlq"
    )
    summaries = [
        make_summary(failed, api_client, "First order failure"),
        make_summary(second_failed, api_client, "Inventory dependency timeout"),
        make_summary(dead_lettered, api_client, "Dead letter order failure"),
    ]
    headers = {"HTTP_AUTHORIZATION": f"Bearer {api_client.pk}.{credential}"}

    page = RestClient().get("/api/v1/incidents?page_size=2&page=2", **headers)
    filtered = RestClient().get(
        "/api/v1/incidents?search=dependency&workflow_state=FAILED", **headers
    )
    detail = RestClient().get(f"/api/v1/incidents/{summaries[1].pk}", **headers)

    assert page.status_code == 200
    assert page.data["count"] == 3
    assert len(page.data["results"]) == 1
    assert "evidence" not in page.data["results"][0]
    assert filtered.status_code == 200
    assert filtered.data["count"] == 1
    assert filtered.data["results"][0]["headline"] == "Inventory dependency timeout"
    assert detail.status_code == 200
    assert detail.data["summary"]["headline"] == "Inventory dependency timeout"
    assert detail.data["evidence"]["workflow_id"] == str(second_failed.pk)


def test_saved_incident_reads_are_authenticated_and_tenant_scoped(client_and_workflow):
    api_client, credential, workflow = client_and_workflow
    summary = make_summary(workflow, api_client, "Private incident")
    other = APIClient.objects.create(name="other", secret_hash=make_password("other-token"))

    unauthenticated = RestClient().get("/api/v1/incidents")
    other_list = RestClient().get(
        "/api/v1/incidents", HTTP_AUTHORIZATION=f"Bearer {other.pk}.other-token"
    )
    other_detail = RestClient().get(
        f"/api/v1/incidents/{summary.pk}",
        HTTP_AUTHORIZATION=f"Bearer {other.pk}.other-token",
    )

    assert unauthenticated.status_code == 401
    assert other_list.status_code == 200
    assert other_list.data["count"] == 0
    assert other_detail.status_code == 404


def test_summary_endpoint_requires_authentication(client_and_workflow):
    _api_client, _credential, workflow = client_and_workflow
    response = RestClient().post(f"/api/v1/workflows/{workflow.pk}/incident-summary", format="json")
    assert response.status_code == 401


def test_summary_endpoint_is_tenant_scoped(client_and_workflow):
    _api_client, _credential, workflow = client_and_workflow
    other = APIClient.objects.create(name="other", secret_hash=make_password("another-token"))
    response = RestClient().post(
        f"/api/v1/workflows/{workflow.pk}/incident-summary",
        HTTP_AUTHORIZATION=f"Bearer {other.pk}.another-token",
        format="json",
    )
    assert response.status_code == 404
    assert IncidentSummary.objects.count() == 0


def test_summary_only_for_failed_or_dead_lettered_workflow(client_and_workflow):
    api_client, credential, _failed = client_and_workflow
    workflow = make_workflow(api_client, state=Workflow.State.SUCCEEDED, key="succeeded")
    response = RestClient().post(
        f"/api/v1/workflows/{workflow.pk}/incident-summary",
        HTTP_AUTHORIZATION=f"Bearer {api_client.pk}.{credential}",
        format="json",
    )
    assert response.status_code == 409
    assert IncidentSummary.objects.count() == 0


def test_summary_rate_limit_is_shared_and_bounded(client_and_workflow):
    api_client, credential, workflow = client_and_workflow
    http = RestClient()
    url = f"/api/v1/workflows/{workflow.pk}/incident-summary"
    for _ in range(5):
        assert (
            http.post(
                url,
                HTTP_AUTHORIZATION=f"Bearer {api_client.pk}.{credential}",
                format="json",
            ).status_code
            == 201
        )
    response = http.post(
        url,
        HTTP_AUTHORIZATION=f"Bearer {api_client.pk}.{credential}",
        format="json",
    )
    assert response.status_code == 429
    assert IncidentSummary.objects.count() == 5


def test_transient_provider_failure_returns_safe_diagnostic_code(client_and_workflow, monkeypatch):
    api_client, credential, workflow = client_and_workflow

    def fail_provider(*_args, **_kwargs):
        raise TransientProviderError("temporary failure", error_code="OPENAI_NETWORK_ERROR")

    monkeypatch.setattr("apps.incidents.views.create_incident_summary", fail_provider)
    response = RestClient().post(
        f"/api/v1/workflows/{workflow.pk}/incident-summary",
        HTTP_AUTHORIZATION=f"Bearer {api_client.pk}.{credential}",
        format="json",
    )

    assert response.status_code == 503
    assert response.data["error"]["code"] == "OPENAI_NETWORK_ERROR"
    assert response.data["error"]["details"]["detail"] == (
        "Incident analysis is temporarily unavailable."
    )
    workflow.refresh_from_db()
    assert workflow.state == Workflow.State.FAILED
    assert IncidentSummary.objects.count() == 0


def test_throttle_response_explains_retry_wait(client_and_workflow, monkeypatch):
    api_client, credential, workflow = client_and_workflow

    class AlwaysThrottle:
        def allow_request(self, request, view):
            return False

        def wait(self):
            return 2029

    from apps.incidents.views import IncidentSummaryCreateView

    monkeypatch.setattr(IncidentSummaryCreateView, "throttle_classes", [AlwaysThrottle])
    response = RestClient().post(
        f"/api/v1/workflows/{workflow.pk}/incident-summary",
        HTTP_AUTHORIZATION=f"Bearer {api_client.pk}.{credential}",
        format="json",
    )

    assert response.status_code == 429
    assert response.data["error"]["code"] == "THROTTLED"
    assert "2029 seconds" in response.data["error"]["message"]
