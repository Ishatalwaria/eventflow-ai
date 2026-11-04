from apps.commerce import inventory, orders, payments
from apps.commerce.models import Order, PaymentIntent
from apps.processing.errors import PermanentProcessingError
from apps.workflows.models import Workflow


def load_failed_payment(*, workflow, payload, attempt_number, direction):
    source_workflow_id = payload.get("source_workflow_id")
    if not source_workflow_id:
        raise PermanentProcessingError(
            "INVALID_RECOVERY", "payment.recovery.requested requires source_workflow_id."
        )
    source = Workflow.objects.filter(
        pk=source_workflow_id, event__client=workflow.event.client
    ).first()
    if source is None:
        raise PermanentProcessingError(
            "SOURCE_WORKFLOW_NOT_FOUND", "Source workflow was not found."
        )
    order = Order.objects.filter(workflow=source).first()
    if order is None:
        raise PermanentProcessingError("SOURCE_ORDER_NOT_FOUND", "Source order was not found.")
    failed_payment = (
        PaymentIntent.objects.filter(workflow=source)
        .exclude(status=PaymentIntent.Status.AUTHORIZED)
        .order_by("-created_at")
        .first()
    )
    if failed_payment is None and order.status not in {
        Order.Status.FAILED,
        Order.Status.RESERVED,
        Order.Status.VALIDATED,
    }:
        raise PermanentProcessingError(
            "NOTHING_TO_RECOVER", "No failed payment found for recovery."
        )
    # Link recovery workflow context onto order via payload token override for retry.
    if payload.get("payment_method_token"):
        order.payment_method_token = str(payload["payment_method_token"])[:128]
        order.save(update_fields=["payment_method_token", "updated_at"])
    return {
        "source_workflow_id": str(source.id),
        "order_id": str(order.id),
        "failed_payment_id": str(failed_payment.id) if failed_payment else "",
    }


def retry_authorize_payment(*, workflow, payload, attempt_number, direction):
    source_workflow_id = payload["source_workflow_id"]
    order = Order.objects.get(workflow_id=source_workflow_id)
    # Ensure inventory is still reserved; if released, re-reserve.
    from apps.commerce.models import InventoryReservation

    active = InventoryReservation.objects.filter(
        workflow_id=source_workflow_id, status=InventoryReservation.Status.RESERVED
    ).exists()
    if not active:
        for item in order.lines.all():
            inventory.reserve_stock(
                order=order,
                workflow=order.workflow,
                sku=item.sku,
                quantity=item.quantity,
                idempotency_key=f"reserve-recovery:{workflow.id}:{item.sku}",
            )
    intent = payments.authorize_payment(
        order=order,
        workflow=workflow,
        idempotency_key=f"pay-recovery:{workflow.id}:authorize",
    )
    orders.set_order_status(order, Order.Status.PAYMENT_AUTHORIZED)
    return {"payment_id": str(intent.id), "status": intent.status}


def finalize_recovery(*, workflow, payload, attempt_number, direction):
    source_workflow_id = payload["source_workflow_id"]
    order = Order.objects.select_related("workflow").get(workflow_id=source_workflow_id)
    for reservation in order.reservations.filter(status="RESERVED"):
        inventory.consume_reservation(
            reservation=reservation,
            idempotency_key=f"consume-recovery:{workflow.id}:{reservation.id}",
        )
    orders.set_order_status(order, Order.Status.COMPLETED)
    source = order.workflow
    if source.state in {Workflow.State.FAILED, Workflow.State.DEAD_LETTERED}:
        # Mark source recovered without inventing a new transition engine path.
        source.last_error_code = ""
        source.current_stage = "recovered_by_payment_recovery"
        source.save(update_fields=["last_error_code", "current_stage", "updated_at"])
    return {"order_status": order.status}


HANDLERS = {
    "load_failed_payment": load_failed_payment,
    "retry_authorize_payment": retry_authorize_payment,
    "finalize_recovery": finalize_recovery,
}
