"""Order creation and status transitions tied to workflow events."""

from django.db import IntegrityError, transaction

from .models import Order, OrderLine, Product, ReplenishmentRequest


@transaction.atomic
def create_order_from_event(*, event, workflow, payload):
    existing = Order.objects.filter(event=event).first()
    if existing is not None:
        return existing

    token = payload.get("payment_method_token") or "ok_card"
    if not isinstance(token, str):
        token = "ok_card"

    try:
        order = Order.objects.create(
            client=event.client,
            event=event,
            workflow=workflow,
            external_order_id=payload["order_id"],
            currency=payload["currency"],
            total_minor_units=payload["total_minor_units"],
            payment_method_token=token[:128],
            status=Order.Status.PENDING,
        )
    except IntegrityError:
        return Order.objects.get(event=event)

    for item in payload["items"]:
        product = Product.objects.filter(client=event.client, sku=item["sku"], active=True).first()
        unit_price = product.unit_price_minor if product else 0
        OrderLine.objects.create(
            order=order,
            sku=item["sku"],
            quantity=item["quantity"],
            unit_price_minor=unit_price,
        )
    return order


def set_order_status(order, status, *, failure_code=""):
    order.status = status
    order.failure_code = failure_code
    order.save(update_fields=["status", "failure_code", "updated_at"])
    return order


@transaction.atomic
def create_replenishment_from_event(*, event, workflow, payload):
    existing = ReplenishmentRequest.objects.filter(event=event).first()
    if existing is not None:
        return existing
    try:
        return ReplenishmentRequest.objects.create(
            client=event.client,
            event=event,
            workflow=workflow,
            sku=payload["sku"],
            quantity=payload["quantity"],
            approval_token=str(payload.get("approval_token") or "approve"),
            status=ReplenishmentRequest.Status.REQUESTED,
        )
    except IntegrityError:
        return ReplenishmentRequest.objects.get(event=event)
