"""Inventory reservation with row locking and idempotent mutations."""

from django.db import IntegrityError, transaction

from apps.processing.errors import PermanentProcessingError, TransientProcessingError

from .models import InventoryItem, InventoryMovement, InventoryReservation, Product


def _get_locked_inventory(*, client, sku):
    try:
        product = Product.objects.select_related("inventory").get(
            client=client, sku=sku, active=True
        )
    except Product.DoesNotExist as exc:
        raise PermanentProcessingError(
            "UNKNOWN_SKU", f"Product SKU '{sku}' is not available."
        ) from exc
    inventory = (
        InventoryItem.objects.select_for_update()
        .select_related("product")
        .get(pk=product.inventory.pk)
    )
    return product, inventory


@transaction.atomic
def reserve_stock(*, order, workflow, sku, quantity, idempotency_key):
    existing = InventoryReservation.objects.filter(idempotency_key=idempotency_key).first()
    if existing is not None:
        return existing

    product, inventory = _get_locked_inventory(client=order.client, sku=sku)
    available = inventory.on_hand - inventory.reserved
    if available < quantity:
        raise PermanentProcessingError(
            "INSUFFICIENT_INVENTORY",
            "Insufficient stock for one or more order items.",
        )

    inventory.reserved += quantity
    inventory.save(update_fields=["reserved", "updated_at"])
    try:
        reservation = InventoryReservation.objects.create(
            order=order,
            workflow=workflow,
            product=product,
            quantity=quantity,
            status=InventoryReservation.Status.RESERVED,
            idempotency_key=idempotency_key,
        )
    except IntegrityError:
        return InventoryReservation.objects.get(idempotency_key=idempotency_key)

    InventoryMovement.objects.create(
        product=product,
        order=order,
        workflow=workflow,
        reservation=reservation,
        kind=InventoryMovement.Kind.RESERVE,
        quantity=quantity,
        on_hand_after=inventory.on_hand,
        reserved_after=inventory.reserved,
        idempotency_key=f"move:{idempotency_key}:reserve",
    )
    return reservation


@transaction.atomic
def release_reservation(*, reservation, idempotency_key):
    existing_move = InventoryMovement.objects.filter(idempotency_key=idempotency_key).first()
    if existing_move is not None:
        return InventoryReservation.objects.get(pk=reservation.pk)

    locked = (
        InventoryReservation.objects.select_for_update()
        .select_related("product")
        .get(pk=reservation.pk)
    )
    if locked.status != InventoryReservation.Status.RESERVED:
        return locked

    inventory = (
        InventoryItem.objects.select_for_update()
        .select_related("product")
        .get(product_id=locked.product_id)
    )
    if inventory.reserved < locked.quantity:
        raise TransientProcessingError(
            "INVENTORY_INCONSISTENT",
            "Reserved quantity is inconsistent during release.",
        )
    inventory.reserved -= locked.quantity
    inventory.save(update_fields=["reserved", "updated_at"])
    locked.status = InventoryReservation.Status.RELEASED
    locked.save(update_fields=["status", "updated_at"])
    InventoryMovement.objects.create(
        product=locked.product,
        order=locked.order,
        workflow=locked.workflow,
        reservation=locked,
        kind=InventoryMovement.Kind.RELEASE,
        quantity=locked.quantity,
        on_hand_after=inventory.on_hand,
        reserved_after=inventory.reserved,
        idempotency_key=idempotency_key,
    )
    return locked


@transaction.atomic
def consume_reservation(*, reservation, idempotency_key):
    existing_move = InventoryMovement.objects.filter(idempotency_key=idempotency_key).first()
    if existing_move is not None:
        return InventoryReservation.objects.get(pk=reservation.pk)

    locked = (
        InventoryReservation.objects.select_for_update()
        .select_related("product")
        .get(pk=reservation.pk)
    )
    if locked.status == InventoryReservation.Status.CONSUMED:
        return locked
    if locked.status != InventoryReservation.Status.RESERVED:
        raise PermanentProcessingError(
            "RESERVATION_NOT_ACTIVE",
            "Cannot consume a reservation that is not active.",
        )

    inventory = (
        InventoryItem.objects.select_for_update()
        .select_related("product")
        .get(product_id=locked.product_id)
    )
    if inventory.on_hand < locked.quantity or inventory.reserved < locked.quantity:
        raise TransientProcessingError(
            "INVENTORY_INCONSISTENT",
            "Inventory levels are inconsistent during consume.",
        )
    inventory.on_hand -= locked.quantity
    inventory.reserved -= locked.quantity
    inventory.save(update_fields=["on_hand", "reserved", "updated_at"])
    locked.status = InventoryReservation.Status.CONSUMED
    locked.save(update_fields=["status", "updated_at"])
    InventoryMovement.objects.create(
        product=locked.product,
        order=locked.order,
        workflow=locked.workflow,
        reservation=locked,
        kind=InventoryMovement.Kind.CONSUME,
        quantity=locked.quantity,
        on_hand_after=inventory.on_hand,
        reserved_after=inventory.reserved,
        idempotency_key=idempotency_key,
    )
    return locked


@transaction.atomic
def replenish_stock(*, client, sku, quantity, workflow=None, idempotency_key):
    existing = InventoryMovement.objects.filter(idempotency_key=idempotency_key).first()
    if existing is not None:
        return existing

    product, inventory = _get_locked_inventory(client=client, sku=sku)
    inventory.on_hand += quantity
    inventory.save(update_fields=["on_hand", "updated_at"])
    try:
        return InventoryMovement.objects.create(
            product=product,
            workflow=workflow,
            kind=InventoryMovement.Kind.REPLENISH,
            quantity=quantity,
            on_hand_after=inventory.on_hand,
            reserved_after=inventory.reserved,
            idempotency_key=idempotency_key,
        )
    except IntegrityError:
        return InventoryMovement.objects.get(idempotency_key=idempotency_key)


def release_all_for_workflow(*, workflow, reason="compensate"):
    released = []
    for reservation in InventoryReservation.objects.filter(
        workflow=workflow, status=InventoryReservation.Status.RESERVED
    ).order_by("created_at"):
        released.append(
            release_reservation(
                reservation=reservation,
                idempotency_key=f"release:{workflow.id}:{reservation.id}:{reason}",
            )
        )
    return released


DEMO_PRODUCTS = (
    ("ITEM-KEYBOARD", "Mechanical Keyboard", 24900, 40),
    ("ITEM-MOUSE", "Wireless Mouse", 7900, 25),
    ("OOS-MOUSE", "Out-of-stock Mouse", 7900, 0),
    ("TEMPORARY-FAIL-FIRST", "Flaky Inventory SKU", 1000, 5),
)


def seed_demo_catalog_for_client(client):
    """Seed default demonstration catalog for an API client."""
    for sku, name, price, on_hand in DEMO_PRODUCTS:
        product, _ = Product.objects.get_or_create(
            client=client,
            sku=sku,
            defaults={"name": name, "unit_price_minor": price, "active": True},
        )
        InventoryItem.objects.get_or_create(
            product=product,
            defaults={"on_hand": on_hand, "reserved": 0},
        )
