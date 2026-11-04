import uuid

from django.db import models
from django.db.models import F, Q


class Product(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    client = models.ForeignKey(
        "common.APIClient", on_delete=models.PROTECT, related_name="products"
    )
    sku = models.CharField(max_length=100)
    name = models.CharField(max_length=200)
    unit_price_minor = models.PositiveIntegerField(default=0)
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["client", "sku"], name="product_client_sku_uniq"),
        ]
        indexes = [models.Index(fields=["client", "sku"], name="product_client_sku_idx")]

    def __str__(self):
        return f"{self.sku} ({self.client_id})"


class InventoryItem(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    product = models.OneToOneField(Product, on_delete=models.PROTECT, related_name="inventory")
    on_hand = models.PositiveIntegerField(default=0)
    reserved = models.PositiveIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(on_hand__gte=F("reserved")) & Q(reserved__gte=0),
                name="inventory_on_hand_covers_reserved",
            )
        ]

    @property
    def available(self):
        return self.on_hand - self.reserved

    def __str__(self):
        return f"{self.product.sku}: available={self.available}"


class Order(models.Model):
    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        VALIDATED = "VALIDATED", "Validated"
        RESERVED = "RESERVED", "Reserved"
        PAYMENT_AUTHORIZED = "PAYMENT_AUTHORIZED", "Payment authorized"
        CONFIRMED = "CONFIRMED", "Confirmed"
        SHIPPING = "SHIPPING", "Shipping"
        COMPLETED = "COMPLETED", "Completed"
        FAILED = "FAILED", "Failed"
        CANCELLED = "CANCELLED", "Cancelled"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    client = models.ForeignKey("common.APIClient", on_delete=models.PROTECT, related_name="orders")
    event = models.OneToOneField("events.Event", on_delete=models.PROTECT, related_name="order")
    workflow = models.OneToOneField(
        "workflows.Workflow", on_delete=models.PROTECT, related_name="order"
    )
    external_order_id = models.CharField(max_length=128)
    currency = models.CharField(max_length=3)
    total_minor_units = models.PositiveIntegerField()
    status = models.CharField(max_length=32, choices=Status.choices, default=Status.PENDING)
    payment_method_token = models.CharField(max_length=128, blank=True)
    failure_code = models.CharField(max_length=100, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["client", "created_at"], name="order_client_created_idx"),
            models.Index(fields=["status", "created_at"], name="order_status_created_idx"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["client", "external_order_id"],
                name="order_client_external_id_uniq",
            )
        ]

    def __str__(self):
        return f"{self.external_order_id} ({self.status})"


class OrderLine(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="lines")
    sku = models.CharField(max_length=100)
    quantity = models.PositiveIntegerField()
    unit_price_minor = models.PositiveIntegerField(default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["order", "sku"], name="order_line_order_sku_uniq"),
            models.CheckConstraint(condition=Q(quantity__gte=1), name="order_line_qty_positive"),
        ]


class InventoryReservation(models.Model):
    class Status(models.TextChoices):
        RESERVED = "RESERVED", "Reserved"
        RELEASED = "RELEASED", "Released"
        CONSUMED = "CONSUMED", "Consumed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order = models.ForeignKey(Order, on_delete=models.PROTECT, related_name="reservations")
    workflow = models.ForeignKey(
        "workflows.Workflow", on_delete=models.PROTECT, related_name="reservations"
    )
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name="reservations")
    quantity = models.PositiveIntegerField()
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.RESERVED)
    idempotency_key = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["idempotency_key"], name="inventory_reservation_idem_uniq"
            ),
            models.CheckConstraint(
                condition=Q(quantity__gte=1), name="inventory_reservation_qty_positive"
            ),
        ]
        indexes = [
            models.Index(fields=["workflow", "status"], name="reservation_wf_status_idx"),
        ]


class InventoryMovement(models.Model):
    class Kind(models.TextChoices):
        RESERVE = "RESERVE", "Reserve"
        RELEASE = "RELEASE", "Release"
        CONSUME = "CONSUME", "Consume"
        REPLENISH = "REPLENISH", "Replenish"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name="movements")
    order = models.ForeignKey(
        Order, null=True, blank=True, on_delete=models.SET_NULL, related_name="movements"
    )
    workflow = models.ForeignKey(
        "workflows.Workflow",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="inventory_movements",
    )
    reservation = models.ForeignKey(
        InventoryReservation,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="movements",
    )
    kind = models.CharField(max_length=16, choices=Kind.choices)
    quantity = models.PositiveIntegerField()
    on_hand_after = models.PositiveIntegerField()
    reserved_after = models.PositiveIntegerField()
    idempotency_key = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["idempotency_key"], name="inventory_movement_idem_uniq"
            ),
        ]
        indexes = [
            models.Index(fields=["product", "created_at"], name="movement_product_created_idx")
        ]


class PaymentIntent(models.Model):
    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        AUTHORIZED = "AUTHORIZED", "Authorized"
        REJECTED = "REJECTED", "Rejected"
        TIMED_OUT = "TIMED_OUT", "Timed out"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order = models.ForeignKey(Order, on_delete=models.PROTECT, related_name="payments")
    workflow = models.ForeignKey(
        "workflows.Workflow", on_delete=models.PROTECT, related_name="payments"
    )
    amount_minor = models.PositiveIntegerField()
    currency = models.CharField(max_length=3)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    provider = models.CharField(max_length=64, default="local_simulator")
    provider_ref = models.CharField(max_length=128, blank=True)
    failure_code = models.CharField(max_length=100, blank=True)
    idempotency_key = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["idempotency_key"], name="payment_intent_idem_uniq"),
        ]
        indexes = [
            models.Index(fields=["workflow", "status"], name="payment_wf_status_idx"),
        ]


class ReplenishmentRequest(models.Model):
    class Status(models.TextChoices):
        REQUESTED = "REQUESTED", "Requested"
        APPROVED = "APPROVED", "Approved"
        REJECTED = "REJECTED", "Rejected"
        APPLIED = "APPLIED", "Applied"
        FAILED = "FAILED", "Failed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    client = models.ForeignKey(
        "common.APIClient", on_delete=models.PROTECT, related_name="replenishments"
    )
    event = models.OneToOneField(
        "events.Event", on_delete=models.PROTECT, related_name="replenishment"
    )
    workflow = models.OneToOneField(
        "workflows.Workflow", on_delete=models.PROTECT, related_name="replenishment"
    )
    sku = models.CharField(max_length=100)
    quantity = models.PositiveIntegerField()
    approval_token = models.CharField(max_length=128, blank=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.REQUESTED)
    failure_code = models.CharField(max_length=100, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=Q(quantity__gte=1), name="replenishment_qty_positive"),
        ]
