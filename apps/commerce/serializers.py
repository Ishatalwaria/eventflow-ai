from rest_framework import serializers

from .models import InventoryItem, InventoryReservation, Order, OrderLine, PaymentIntent


class InventoryItemSerializer(serializers.ModelSerializer):
    sku = serializers.CharField(source="product.sku", read_only=True)
    name = serializers.CharField(source="product.name", read_only=True)
    available = serializers.IntegerField(read_only=True)
    client_id = serializers.UUIDField(source="product.client_id", read_only=True)
    client_name = serializers.CharField(source="product.client.name", read_only=True)

    class Meta:
        model = InventoryItem
        fields = (
            "id",
            "client_id",
            "client_name",
            "sku",
            "name",
            "on_hand",
            "reserved",
            "available",
            "updated_at",
        )


class InventoryReservationSerializer(serializers.ModelSerializer):
    sku = serializers.CharField(source="product.sku", read_only=True)

    class Meta:
        model = InventoryReservation
        fields = ("id", "sku", "quantity", "status", "created_at", "updated_at")


class OrderLineSerializer(serializers.ModelSerializer):
    class Meta:
        model = OrderLine
        fields = ("sku", "quantity", "unit_price_minor")


class PaymentIntentSerializer(serializers.ModelSerializer):
    class Meta:
        model = PaymentIntent
        fields = (
            "id",
            "order_id",
            "workflow_id",
            "amount_minor",
            "currency",
            "status",
            "provider",
            "provider_ref",
            "failure_code",
            "created_at",
        )


class OrderDetailSerializer(serializers.ModelSerializer):
    lines = OrderLineSerializer(many=True, read_only=True)
    reservations = InventoryReservationSerializer(many=True, read_only=True)
    payments = PaymentIntentSerializer(many=True, read_only=True)

    class Meta:
        model = Order
        fields = (
            "id",
            "workflow_id",
            "event_id",
            "external_order_id",
            "currency",
            "total_minor_units",
            "status",
            "payment_method_token",
            "failure_code",
            "created_at",
            "updated_at",
            "lines",
            "reservations",
            "payments",
        )
