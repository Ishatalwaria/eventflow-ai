import uuid
import pytest
from django.contrib.auth import get_user_model
from django.test import Client as DjangoClient
from rest_framework.test import APIClient

from apps.common.models import APIClient as MachineClient
from apps.events.models import Event

User = get_user_model()


@pytest.fixture
def auth_client():
    return APIClient()


@pytest.fixture
def test_user(db):
    user = User.objects.create_user(
        username="alice@example.com",
        email="alice@example.com",
        password="ValidPassword123!",
        first_name="Alice",
    )
    # create an owned client
    MachineClient.objects.create(
        name="alice-default",
        owner=user,
        secret_hash="pbkdf2_sha256$somehash",
    )
    return user


@pytest.fixture
def other_user(db):
    user = User.objects.create_user(
        username="bob@example.com",
        email="bob@example.com",
        password="ValidPassword123!",
        first_name="Bob",
    )
    MachineClient.objects.create(
        name="bob-default",
        owner=user,
        secret_hash="pbkdf2_sha256$otherhash",
    )
    return user


@pytest.mark.django_db
def test_csrf_endpoint_sets_cookie_and_returns_token(auth_client):
    response = auth_client.get("/api/v1/auth/csrf")
    assert response.status_code == 200
    data = response.json()
    assert "csrfToken" in data
    assert len(data["csrfToken"]) > 0


@pytest.mark.django_db
def test_user_registration_success_provisions_client_and_session(auth_client):
    payload = {
        "username": "charlie@example.com",
        "email": "charlie@example.com",
        "password": "StrongPassword99!",
        "confirm_password": "StrongPassword99!",
        "first_name": "Charlie",
        "last_name": "Brown",
    }
    response = auth_client.post("/api/v1/auth/register", payload, format="json")
    assert response.status_code == 201
    data = response.json()
    assert data["email"] == "charlie@example.com"
    assert data["type"] == "user"
    assert data["client_id"] is not None

    user = User.objects.get(email="charlie@example.com")
    assert user.first_name == "Charlie"
    # Verify auto-provisioned client
    client = MachineClient.objects.get(owner=user)
    assert client.is_active is True

    # Check that me endpoint recognizes the active session
    me_resp = auth_client.get("/api/v1/auth/me")
    assert me_resp.status_code == 200
    assert me_resp.json()["email"] == "charlie@example.com"


@pytest.mark.django_db
def test_user_registration_validations(auth_client, test_user):
    # Short password
    res = auth_client.post(
        "/api/v1/auth/register",
        {"name": "u1", "email": "u1@example.com", "password": "123", "password_confirm": "123"},
        format="json",
    )
    assert res.status_code == 400
    assert res.json()["error"]["code"] == "WEAK_PASSWORD"

    # Password mismatch
    res = auth_client.post(
        "/api/v1/auth/register",
        {
            "name": "u2",
            "email": "u2@example.com",
            "password": "StrongPassword99!",
            "password_confirm": "DifferentPassword99!",
        },
        format="json",
    )
    assert res.status_code == 400
    assert res.json()["error"]["code"] == "PASSWORD_MISMATCH"

    # Duplicate email
    res = auth_client.post(
        "/api/v1/auth/register",
        {
            "name": "Alice Duplicate",
            "email": test_user.email,
            "password": "StrongPassword99!",
            "password_confirm": "StrongPassword99!",
        },
        format="json",
    )
    assert res.status_code == 400
    assert res.json()["error"]["code"] == "EMAIL_ALREADY_EXISTS"


@pytest.mark.django_db
def test_login_and_logout_lifecycle(auth_client, test_user):
    # Bad credentials
    bad = auth_client.post(
        "/api/v1/auth/login",
        {"username": test_user.email, "password": "WrongPassword"},
        format="json",
    )
    assert bad.status_code == 401

    # Good credentials
    good = auth_client.post(
        "/api/v1/auth/login",
        {"username": test_user.email, "password": "ValidPassword123!"},
        format="json",
    )
    assert good.status_code == 200
    assert good.json()["email"] == test_user.email

    # /auth/me returns user profile
    me = auth_client.get("/api/v1/auth/me")
    assert me.status_code == 200
    assert me.json()["username"] == test_user.username

    # Logout
    logout_res = auth_client.post("/api/v1/auth/logout")
    assert logout_res.status_code == 200

    # /auth/me after logout is 401
    me_after = auth_client.get("/api/v1/auth/me")
    assert me_after.status_code == 401


@pytest.mark.django_db
def test_current_user_supports_machine_api_client(auth_client):
    from apps.common.services import create_api_client

    client, token = create_api_client("machine-client")
    response = auth_client.get("/api/v1/auth/me", HTTP_AUTHORIZATION=f"Bearer {token}")
    assert response.status_code == 200
    data = response.json()
    assert data["type"] == "api_client"
    assert data["id"] == str(client.pk)
    assert data["name"] == "machine-client"


@pytest.mark.django_db
def test_client_management_crud_and_one_time_secret(auth_client, test_user, other_user):
    # Log in as test_user (Alice)
    auth_client.force_login(test_user)

    # 1. List clients - Alice sees only alice-default
    res = auth_client.get("/api/v1/clients")
    assert res.status_code == 200
    clients = res.json()["results"]
    assert len(clients) == 1
    assert clients[0]["name"] == "alice-default"
    assert "token" not in clients[0]
    assert "secret" not in clients[0]

    # 2. Create new client for Alice
    create_res = auth_client.post(
        "/api/v1/clients",
        {"name": "production-crawler"},
        format="json",
    )
    assert create_res.status_code == 201
    created = create_res.json()
    assert created["name"] == "production-crawler"
    assert "token" in created
    assert "." in created["token"]
    new_client_id = created["id"]

    # 3. List clients again - token is NOT present in list
    res = auth_client.get("/api/v1/clients")
    clients = res.json()["results"]
    assert len(clients) == 2
    for c in clients:
        assert "token" not in c
        assert "secret" not in c

    # 4. Revoke new client
    revoke_res = auth_client.post(f"/api/v1/clients/{new_client_id}/revoke")
    assert revoke_res.status_code == 200
    assert "revoked" in revoke_res.json()["detail"]

    # 5. Bob tries to access or revoke Alice's client -> 404
    auth_client.force_login(other_user)
    bob_list = auth_client.get("/api/v1/clients")
    assert len(bob_list.json()["results"]) == 1
    assert bob_list.json()["results"][0]["name"] == "bob-default"

    bob_revoke = auth_client.post(f"/api/v1/clients/{new_client_id}/revoke")
    assert bob_revoke.status_code == 404

    bob_revoke = auth_client.post(f"/api/v1/clients/{new_client_id}/revoke")
    assert bob_revoke.status_code == 404


@pytest.mark.django_db
def test_cross_tenant_isolation_for_human_users(auth_client, test_user, other_user):
    from datetime import datetime, timezone
    from apps.events.models import Event

    alice_client = MachineClient.objects.get(owner=test_user)
    bob_client = MachineClient.objects.get(owner=other_user)

    now = datetime.now(timezone.utc)
    Event.objects.create(
        client=alice_client,
        event_type="order.created",
        schema_version=1,
        source="alice-service",
        idempotency_key="alice-key-1",
        occurred_at=now,
        correlation_id="alice-corr-1",
        request_id="alice-req-1",
        payload={"order": 1},
    )
    Event.objects.create(
        client=bob_client,
        event_type="payment.processed",
        schema_version=1,
        source="bob-service",
        idempotency_key="bob-key-1",
        occurred_at=now,
        correlation_id="bob-corr-1",
        request_id="bob-req-1",
        payload={"payment": 2},
    )

    # Alice views events
    auth_client.force_login(test_user)
    alice_events = auth_client.get("/api/v1/events")
    assert alice_events.status_code == 200
    results = alice_events.json()["results"]
    assert len(results) == 1
    assert results[0]["idempotency_key"] == "alice-key-1"

    # Bob views events
    auth_client.force_login(other_user)
    bob_events = auth_client.get("/api/v1/events")
    assert bob_events.status_code == 200
    results = bob_events.json()["results"]
    assert len(results) == 1
    assert results[0]["idempotency_key"] == "bob-key-1"
