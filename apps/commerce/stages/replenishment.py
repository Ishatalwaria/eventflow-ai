from apps.commerce import inventory, orders
from apps.commerce.models import ReplenishmentRequest
from apps.processing.errors import PermanentProcessingError


def validate_replenishment(*, workflow, payload, attempt_number, direction):
    request = orders.create_replenishment_from_event(
        event=workflow.event, workflow=workflow, payload=payload
    )
    if payload.get("quantity", 0) < 1:
        raise PermanentProcessingError("INVALID_REPLENISHMENT", "Quantity must be >= 1.")
    return {"request_id": str(request.id)}


def approve_replenishment(*, workflow, payload, attempt_number, direction):
    request = ReplenishmentRequest.objects.get(workflow=workflow)
    token = (request.approval_token or "").lower()
    if token.startswith("reject"):
        request.status = ReplenishmentRequest.Status.REJECTED
        request.failure_code = "REPLENISHMENT_REJECTED"
        request.save(update_fields=["status", "failure_code", "updated_at"])
        raise PermanentProcessingError(
            "REPLENISHMENT_REJECTED", "Replenishment request was rejected."
        )
    request.status = ReplenishmentRequest.Status.APPROVED
    request.save(update_fields=["status", "updated_at"])
    return {"status": request.status}


def apply_stock(*, workflow, payload, attempt_number, direction):
    request = ReplenishmentRequest.objects.select_related("client").get(workflow=workflow)
    inventory.replenish_stock(
        client=request.client,
        sku=request.sku,
        quantity=request.quantity,
        workflow=workflow,
        idempotency_key=f"replenish:{workflow.id}:{request.sku}",
    )
    request.status = ReplenishmentRequest.Status.APPLIED
    request.save(update_fields=["status", "updated_at"])
    return {"sku": request.sku, "quantity": request.quantity}


def complete_replenishment(*, workflow, payload, attempt_number, direction):
    request = ReplenishmentRequest.objects.get(workflow=workflow)
    if request.status != ReplenishmentRequest.Status.APPLIED:
        request.status = ReplenishmentRequest.Status.APPLIED
        request.save(update_fields=["status", "updated_at"])
    return {"status": request.status}


HANDLERS = {
    "validate_replenishment": validate_replenishment,
    "approve_replenishment": approve_replenishment,
    "apply_stock": apply_stock,
    "complete_replenishment": complete_replenishment,
}
