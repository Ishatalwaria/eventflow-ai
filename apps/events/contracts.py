from django.conf import settings
from django.utils.dateparse import parse_datetime
from rest_framework import serializers


class OrderItemSerializer(serializers.Serializer):
    sku = serializers.CharField(max_length=100)
    quantity = serializers.IntegerField(min_value=1)


class OrderCreatedV1PayloadSerializer(serializers.Serializer):
    order_id = serializers.CharField(max_length=128)
    currency = serializers.RegexField(r"^[A-Z]{3}$")
    total_minor_units = serializers.IntegerField(min_value=0)
    items = OrderItemSerializer(many=True, allow_empty=False, max_length=100)


class OffsetDateTimeField(serializers.DateTimeField):
    default_error_messages = {
        "timezone": "Timestamp must include a UTC offset or Z suffix.",
    }

    def to_internal_value(self, value):
        parsed = parse_datetime(value) if isinstance(value, str) else None
        if parsed is None or parsed.tzinfo is None or parsed.utcoffset() is None:
            self.fail("timezone")
        return super().to_internal_value(value)


class EventEnvelopeSerializer(serializers.Serializer):
    event_type = serializers.RegexField(r"^[a-z][a-z0-9]*(?:[._-][a-z0-9]+)*$", max_length=200)
    schema_version = serializers.IntegerField(min_value=1, max_value=32767)
    source = serializers.RegexField(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,99}$")
    idempotency_key = serializers.RegexField(r"^[\x21-\x7E]{1,255}$")
    occurred_at = OffsetDateTimeField()
    correlation_id = serializers.RegexField(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
    payload = serializers.JSONField()

    def validate(self, attrs):
        if attrs["event_type"] != "order.created":
            raise serializers.ValidationError({"event_type": "Unsupported event type."})
        if attrs["schema_version"] != 1:
            raise serializers.ValidationError({"schema_version": "Unsupported schema version."})

        payload_serializer = OrderCreatedV1PayloadSerializer(data=attrs["payload"])
        if not payload_serializer.is_valid():
            raise serializers.ValidationError({"payload": payload_serializer.errors})
        return attrs


class EventBatchSerializer(serializers.Serializer):
    events = serializers.ListField(
        child=EventEnvelopeSerializer(),
        allow_empty=False,
        max_length=settings.EVENT_BATCH_MAX_SIZE,
    )
