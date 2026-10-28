from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from django.conf import settings
from django.contrib.auth.hashers import check_password, make_password
from django.db import close_old_connections, connection
from django.utils import timezone
from rest_framework.test import APIClient

from apps.common.models import APIClient as APIClientModel
from apps.common.services import create_api_client, revoke_api_client, rotate_api_client
from apps.events.contracts import EventEnvelopeSerializer
from apps.events.models import Event
from apps.processing.models import OutboxMessage, ProcessingLog
from apps.workflows.models import Workflow

pytestmark = pytest.mark.django_db


@pytest.fixture
def api_credentials():
    secret = "test-client-secret-value"
    client = APIClientModel.objects.create(name="test-client", secret_hash=make_password(secret))
    return client, f"{client.pk}.{secret}"


def make_event(**overrides):
    envelope = {
        "event_type": "order.created",
        "schema_version": 1,
        "source": "test-store",
        "idempotency_key": "order-100-created-v1",
        "occurred_at": "2026-10-24T10:00:00Z",
        "correlation_id": "checkout-100",
        "payload": {
            "order_id": "order-100",
            "currency": "INR",
            "total_minor_units": 129900,
            "items": [{"sku": "SKU-1", "quantity": 2}],
        },
    }
    envelope.update(overrides)
    return envelope


def post_event(token, envelope=None, *, path="/api/v1/events", request_id="test-request-1"):
    return APIClient().post(
        path,
        envelope if envelope is not None else make_event(),
        format="json",
        HTTP_AUTHORIZATION=f"Bearer {token}",
        HTTP_X_REQUEST_ID=request_id,
    )


def test_valid_event_is_created_with_workflow_outbox_and_safe_log(api_credentials):
    client, token = api_credentials

    response = post_event(token, request_id="req-event-1")

    assert response.status_code == 201
    data = response.json()
    assert data["duplicate"] is False
    assert data["workflow_state"] == Workflow.State.RECEIVED
    event = Event.objects.get(pk=data["event_id"])
    workflow = Workflow.objects.get(pk=data["workflow_id"])
    outbox = OutboxMessage.objects.get(event=event)
    log = ProcessingLog.objects.get(event=event)
    assert event.client == client
    assert workflow.event == event
    assert outbox.payload["event_id"] == str(event.id)
    assert log.request_id == "req-event-1"
    assert log.correlation_id == "checkout-100"
    assert response["X-Request-ID"] == "req-event-1"
    headers = {"HTTP_AUTHORIZATION": f"Bearer {token}"}
    event_response = APIClient().get(f"/api/v1/events/{event.id}", **headers)
    workflow_response = APIClient().get(f"/api/v1/workflows/{workflow.id}", **headers)
    assert event_response.status_code == 200
    assert event_response.json()["workflow"]["id"] == str(workflow.id)
    assert workflow_response.status_code == 200
    assert workflow_response.json()["state"] == Workflow.State.RECEIVED


def test_invalid_payload_returns_safe_error_and_writes_nothing(api_credentials):
    _, token = api_credentials
    envelope = make_event(payload={"currency": "INR"})

    response = post_event(token, envelope)

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
    assert response.json()["error"]["request_id"] == "test-request-1"
    assert Event.objects.count() == 0


def test_unsupported_schema_version_is_rejected(api_credentials):
    _, token = api_credentials

    response = post_event(token, make_event(schema_version=2))

    assert response.status_code == 400
    assert "schema_version" in response.json()["error"]["details"]
    assert Event.objects.count() == 0


def test_unsupported_event_type_is_rejected(api_credentials):
    _, token = api_credentials

    response = post_event(token, make_event(event_type="order.deleted"))

    assert response.status_code == 400
    assert "event_type" in response.json()["error"]["details"]
    assert Event.objects.count() == 0


def test_naive_timestamp_is_rejected(api_credentials):
    _, token = api_credentials

    response = post_event(token, make_event(occurred_at="2026-10-24T10:00:00"))

    assert response.status_code == 400
    assert Event.objects.count() == 0


def test_missing_and_invalid_authentication_are_rejected():
    missing = APIClient().post("/api/v1/events", make_event(), format="json")
    invalid = APIClient().post(
        "/api/v1/events",
        make_event(),
        format="json",
        HTTP_AUTHORIZATION="Bearer not-a-valid-token",
    )

    assert missing.status_code == 401
    assert missing.json()["error"]["code"] == "AUTHENTICATION_FAILED"
    assert invalid.status_code == 401
    assert invalid.json()["error"]["code"] == "AUTHENTICATION_FAILED"


def test_revoked_client_cannot_authenticate(api_credentials):
    client, token = api_credentials
    client.revoked_at = timezone.now()
    client.save(update_fields=["revoked_at"])

    response = post_event(token)

    assert response.status_code == 401
    assert Event.objects.count() == 0


def test_management_services_create_hash_rotate_and_revoke_credentials():
    client, first_token = create_api_client("rotating-client")
    first_secret = first_token.split(".", maxsplit=1)[1]
    assert first_secret not in client.secret_hash
    assert check_password(first_secret, client.secret_hash)

    second_token = rotate_api_client(client)
    client.refresh_from_db()
    second_secret = second_token.split(".", maxsplit=1)[1]
    assert client.rotated_at is not None
    assert second_secret not in client.secret_hash
    assert check_password(second_secret, client.secret_hash)
    assert not check_password(first_secret, client.secret_hash)
    assert first_secret != second_secret

    revoke_api_client(client)
    client.refresh_from_db()
    assert client.revoked_at is not None
    with pytest.raises(ValueError, match="revoked"):
        rotate_api_client(client)


def test_duplicate_returns_existing_ids_and_does_not_create_more_rows(api_credentials):
    _, token = api_credentials
    first = post_event(token)
    second = post_event(token)

    assert first.status_code == 201
    assert second.status_code == 200
    assert second.json()["duplicate"] is True
    assert second.json()["event_id"] == first.json()["event_id"]
    assert second.json()["workflow_id"] == first.json()["workflow_id"]
    assert Event.objects.count() == Workflow.objects.count() == 1
    assert OutboxMessage.objects.count() == ProcessingLog.objects.count() == 1


def test_batch_is_atomic_and_marks_duplicates(api_credentials):
    _, token = api_credentials
    first = make_event()
    second = make_event(idempotency_key="order-101-created-v1", correlation_id="checkout-101")
    response = post_event(
        token,
        {"events": [first, first, second]},
        path="/api/v1/events/batch",
    )

    assert response.status_code == 200
    results = response.json()["results"]
    assert [item["duplicate"] for item in results] == [False, True, False]
    assert Event.objects.count() == Workflow.objects.count() == 2


def test_batch_size_is_bounded(api_credentials):
    _, token = api_credentials
    too_many = {"events": [make_event(idempotency_key=f"key-{i}") for i in range(51)]}

    response = post_event(token, too_many, path="/api/v1/events/batch")

    assert response.status_code == 400
    assert Event.objects.count() == 0


def test_event_body_size_is_bounded(api_credentials):
    _, token = api_credentials
    envelope = make_event(payload={"large": "x" * settings.EVENT_MAX_REQUEST_BYTES})

    response = post_event(token, envelope)

    assert response.status_code == 413
    assert response.json()["error"]["code"] == "REQUEST_TOO_LARGE"
    assert Event.objects.count() == 0


def test_transaction_rolls_back_event_workflow_and_outbox(api_credentials, monkeypatch):
    from apps.events import services

    client, _ = api_credentials
    envelope = make_event()

    def fail_outbox(*args, **kwargs):
        raise RuntimeError("outbox failure")

    monkeypatch.setattr(services, "record_initial_domain_outbox", fail_outbox)
    serializer = EventEnvelopeSerializer(data=envelope)
    assert serializer.is_valid()
    with pytest.raises(RuntimeError, match="outbox failure"):
        services.accept_events(
            client=client,
            envelopes=[serializer.validated_data],
            request_id="rollback-request",
        )

    assert Event.objects.count() == Workflow.objects.count() == 0
    assert OutboxMessage.objects.count() == ProcessingLog.objects.count() == 0


def test_unexpected_api_failure_returns_safe_error_and_rolls_back(api_credentials, monkeypatch):
    from apps.events import services

    _, token = api_credentials

    def fail_outbox(*args, **kwargs):
        raise RuntimeError("sensitive database detail")

    monkeypatch.setattr(services, "record_initial_domain_outbox", fail_outbox)
    response = post_event(token)

    assert response.status_code == 500
    body = response.json()
    assert body["error"]["code"] == "INTERNAL_ERROR"
    assert body["error"]["request_id"] == "test-request-1"
    assert "sensitive database detail" not in response.content.decode()
    assert Event.objects.count() == Workflow.objects.count() == 0
    assert OutboxMessage.objects.count() == ProcessingLog.objects.count() == 0


def test_workflow_detail_filter_and_pagination(api_credentials):
    _, token = api_credentials
    for index in range(3):
        post_event(
            token,
            make_event(
                idempotency_key=f"order-{index}-created-v1",
                correlation_id=f"checkout-{index}",
            ),
        )

    headers = {"HTTP_AUTHORIZATION": f"Bearer {token}"}
    response = APIClient().get("/api/v1/workflows?state=RECEIVED&page_size=2&page=2", **headers)
    invalid = APIClient().get("/api/v1/workflows?state=NOPE", **headers)

    assert response.status_code == 200
    assert response.json()["count"] == 3
    assert len(response.json()["results"]) == 1
    assert invalid.status_code == 400


def test_event_and_workflow_details_are_scoped_to_authenticated_client(api_credentials):
    _, token = api_credentials
    accepted = post_event(token).json()
    other_secret = "different-client-secret"
    other = APIClientModel.objects.create(
        name="other-client", secret_hash=make_password(other_secret)
    )
    other_token = f"{other.pk}.{other_secret}"

    event_response = APIClient().get(
        f"/api/v1/events/{accepted['event_id']}",
        HTTP_AUTHORIZATION=f"Bearer {other_token}",
    )
    workflow_response = APIClient().get(
        f"/api/v1/workflows/{accepted['workflow_id']}",
        HTTP_AUTHORIZATION=f"Bearer {other_token}",
    )

    assert event_response.status_code == 404
    assert workflow_response.status_code == 404


@pytest.mark.skipif(
    connection.vendor != "postgresql",
    reason="Concurrent unique-key race requires PostgreSQL.",
)
@pytest.mark.django_db(transaction=True)
def test_concurrent_duplicate_requests_create_one_workflow(api_credentials):
    _, token = api_credentials
    barrier = Barrier(2)

    def send():
        close_old_connections()
        try:
            barrier.wait(timeout=5)
            return post_event(token).status_code
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as pool:
        statuses = list(pool.map(lambda _: send(), range(2)))

    assert sorted(statuses) == [200, 201]
    assert Event.objects.count() == Workflow.objects.count() == 1
    assert OutboxMessage.objects.count() == ProcessingLog.objects.count() == 1
