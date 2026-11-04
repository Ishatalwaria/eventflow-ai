import threading

import pytest
from apps.commerce.inventory import reserve_stock
from apps.commerce.models import InventoryItem, InventoryReservation
from apps.processing.errors import PermanentProcessingError
from apps.processing.tests.helpers import create_workflow
from apps.processing.workflow_service import process_workflow_task
from django.db import connection

pytestmark = pytest.mark.django_db


def test_second_reservation_cannot_oversell_remaining_stock():
    _event, workflow, task = create_workflow(on_hand=1)
    validated = process_workflow_task(task)
    process_workflow_task(validated.task)
    order = workflow.order
    item = InventoryItem.objects.get()
    assert item.available == 0
    with pytest.raises(PermanentProcessingError) as exc:
        reserve_stock(
            order=order,
            workflow=workflow,
            sku=item.product.sku,
            quantity=1,
            idempotency_key="second-order-same-sku",
        )
    assert exc.value.code == "INSUFFICIENT_INVENTORY"
    item.refresh_from_db()
    assert item.reserved == 1
    assert (
        InventoryReservation.objects.filter(status=InventoryReservation.Status.RESERVED).count()
        == 1
    )


def test_reserve_idempotency_key_returns_the_same_reservation():
    _event, workflow, task = create_workflow(on_hand=2)
    validated = process_workflow_task(task)
    process_workflow_task(validated.task)
    order = workflow.order
    item = InventoryItem.objects.select_related("product").get()
    first = reserve_stock(
        order=order,
        workflow=workflow,
        sku=item.product.sku,
        quantity=1,
        idempotency_key="same-key",
    )
    second = reserve_stock(
        order=order,
        workflow=workflow,
        sku=item.product.sku,
        quantity=1,
        idempotency_key="same-key",
    )
    item.refresh_from_db()
    assert first.id == second.id
    assert item.reserved == 2


@pytest.mark.skipif(connection.vendor != "postgresql", reason="row locks require PostgreSQL")
def test_concurrent_reservations_cannot_oversell(django_db_blocker):
    with django_db_blocker.unblock():
        _event, workflow, _task = create_workflow(on_hand=1)
        order = None
        from apps.commerce.orders import create_order_from_event

        order = create_order_from_event(
            event=workflow.event, workflow=workflow, payload=workflow.event.payload
        )
        sku = workflow.event.payload["items"][0]["sku"]
        errors = []
        barrier = threading.Barrier(2)

        def attempt(key):
            try:
                barrier.wait(timeout=5)
                reserve_stock(
                    order=order,
                    workflow=workflow,
                    sku=sku,
                    quantity=1,
                    idempotency_key=key,
                )
            except PermanentProcessingError as exc:
                errors.append(exc.code)

        threads = [
            threading.Thread(target=attempt, args=("concurrent-a",)),
            threading.Thread(target=attempt, args=("concurrent-b",)),
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        item = InventoryItem.objects.get(product__sku=sku)
        assert item.reserved == 1
        assert errors == ["INSUFFICIENT_INVENTORY"]
