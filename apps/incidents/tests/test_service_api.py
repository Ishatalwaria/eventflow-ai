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
