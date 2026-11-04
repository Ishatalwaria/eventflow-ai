from django.conf import settings
from django.utils.dateparse import parse_datetime
from rest_framework import serializers


class OrderItemSerializer(serializers.Serializer):
    sku = serializers.CharField(max_length=100)
    quantity = serializers.IntegerField(min_value=1)


class OffsetDateTimeField(serializers.DateTimeField):
    default_error_messages = {
        "timezone": "Timestamp must include a UTC offset or Z suffix.",
    }

    def to_internal_value(self, value):
        parsed = parse_datetime(value) if isinstance(value, str) else None
        if parsed is None or parsed.tzinfo is None or parsed.utcoffset() is None:
            self.fail("timezone")
        return super().to_internal_value(value)


class OrderCreatedV1PayloadSerializer(serializers.Serializer):
    order_id = serializers.CharField(max_length=128)
    currency = serializers.RegexField(r"^[A-Z]{3}$")
    total_minor_units = serializers.IntegerField(min_value=0)
    items = OrderItemSerializer(many=True, allow_empty=False, max_length=100)
    payment_method_token = serializers.CharField(max_length=128, required=False, default="ok_card")


class ReplenishmentRequestedV1Serializer(serializers.Serializer):
    sku = serializers.CharField(max_length=100)
    quantity = serializers.IntegerField(min_value=1)
    approval_token = serializers.CharField(max_length=128, required=False, default="approve")


class PaymentRecoveryRequestedV1Serializer(serializers.Serializer):
    source_workflow_id = serializers.UUIDField()
    payment_method_token = serializers.CharField(max_length=128, required=False, default="ok_card")


PAYLOAD_SERIALIZERS = {
    "order.created": OrderCreatedV1PayloadSerializer,
    "inventory.replenishment.requested": ReplenishmentRequestedV1Serializer,
    "payment.recovery.requested": PaymentRecoveryRequestedV1Serializer,
}


class EventEnvelopeSerializer(serializers.Serializer):
    event_type = serializers.RegexField(r"^[a-z][a-z0-9]*(?:[._-][a-z0-9]+)*$", max_length=200)
    schema_version = serializers.IntegerField(min_value=1, max_value=32767)
    source = serializers.RegexField(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,99}$")
    idempotency_key = serializers.RegexField(r"^[\x21-\x7E]{1,255}$")
    occurred_at = OffsetDateTimeField()
    correlation_id = serializers.RegexField(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
    payload = serializers.JSONField()

    def validate(self, attrs):
        if attrs["schema_version"] != 1:
            raise serializers.ValidationError({"schema_version": "Unsupported schema version."})
        serializer_cls = PAYLOAD_SERIALIZERS.get(attrs["event_type"])
        if serializer_cls is None:
            raise serializers.ValidationError({"event_type": "Unsupported event type."})
        payload_serializer = serializer_cls(data=attrs["payload"])
        if not payload_serializer.is_valid():
            raise serializers.ValidationError({"payload": payload_serializer.errors})
        return attrs


class EventBatchSerializer(serializers.Serializer):
    events = serializers.ListField(
        child=EventEnvelopeSerializer(),
        allow_empty=False,
        max_length=settings.EVENT_BATCH_MAX_SIZE,
    )
