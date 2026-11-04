from apps.commerce import inventory, orders, payments
from apps.commerce.models import InventoryReservation, Order
from apps.processing.errors import PermanentProcessingError, TransientProcessingError


def validate_order(*, workflow, payload, attempt_number, direction):
    order = orders.create_order_from_event(event=workflow.event, workflow=workflow, payload=payload)
    if not payload.get("items"):
        raise PermanentProcessingError("INVALID_ORDER", "Order must contain at least one item.")
    for item in payload["items"]:
        if item["quantity"] < 1:
            raise PermanentProcessingError("INVALID_ORDER", "Order line quantity must be >= 1.")
    orders.set_order_status(order, Order.Status.VALIDATED)
    return {"order_id": str(order.id)}


def reserve_inventory(*, workflow, payload, attempt_number, direction):
    if attempt_number == 1 and any(
        item["sku"] == "TEMPORARY-FAIL-FIRST" for item in payload["items"]
    ):
        raise TransientProcessingError(
            "INVENTORY_TEMPORARILY_UNAVAILABLE",
            "Inventory validation is temporarily unavailable.",
        )
    order = Order.objects.select_related("client").get(workflow=workflow)
    for item in payload["items"]:
        inventory.reserve_stock(
            order=order,
            workflow=workflow,
            sku=item["sku"],
            quantity=item["quantity"],
            idempotency_key=f"reserve:{workflow.id}:{item['sku']}",
        )
    orders.set_order_status(order, Order.Status.RESERVED)
    return {"reserved_lines": len(payload["items"])}


def authorize_payment(*, workflow, payload, attempt_number, direction):
    order = Order.objects.get(workflow=workflow)
    intent = payments.authorize_payment(
        order=order,
        workflow=workflow,
        idempotency_key=f"pay:{workflow.id}:authorize:{attempt_number}",
    )
    orders.set_order_status(order, Order.Status.PAYMENT_AUTHORIZED)
    return {"payment_id": str(intent.id), "status": intent.status}


def confirm_order(*, workflow, payload, attempt_number, direction):
    order = Order.objects.get(workflow=workflow)
    for reservation in InventoryReservation.objects.filter(
        workflow=workflow, status=InventoryReservation.Status.RESERVED
    ):
        inventory.consume_reservation(
            reservation=reservation,
            idempotency_key=f"consume:{workflow.id}:{reservation.id}",
        )
    orders.set_order_status(order, Order.Status.CONFIRMED)
    return {"order_status": order.status}


def prepare_shipment(*, workflow, payload, attempt_number, direction):
    order = Order.objects.get(workflow=workflow)
    orders.set_order_status(order, Order.Status.SHIPPING)
    return {"shipment": "prepared"}


def notify(*, workflow, payload, attempt_number, direction):
    order = Order.objects.get(workflow=workflow)
    orders.set_order_status(order, Order.Status.COMPLETED)
    return {"notified": True, "order_status": order.status}


def release_inventory(*, workflow, payload, attempt_number, direction):
    released = inventory.release_all_for_workflow(workflow=workflow, reason="compensate")
    order = Order.objects.filter(workflow=workflow).first()
    if order is not None and order.status not in {
        Order.Status.FAILED,
        Order.Status.CANCELLED,
        Order.Status.COMPLETED,
    }:
        orders.set_order_status(order, Order.Status.FAILED, failure_code="COMPENSATED")
    return {"released": len(released)}


HANDLERS = {
    "validate_order": validate_order,
    "reserve_inventory": reserve_inventory,
    "authorize_payment": authorize_payment,
    "confirm_order": confirm_order,
    "prepare_shipment": prepare_shipment,
    "notify": notify,
    "release_inventory": release_inventory,
}
