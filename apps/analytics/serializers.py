from rest_framework import serializers


class LifecycleAnalyticsQuerySerializer(serializers.Serializer):
    date_from = serializers.DateField()
    date_to = serializers.DateField()

    def validate(self, attrs):
        start_date = attrs["date_from"]
        end_date = attrs["date_to"]
        if end_date < start_date:
            raise serializers.ValidationError({"date_to": "Must be on or after date_from."})
        if (end_date - start_date).days > 366:
            raise serializers.ValidationError({"date_to": "Date range cannot exceed 367 days."})
        return attrs


class ProcessedMinuteSerializer(serializers.Serializer):
    minute = serializers.DateTimeField()
    count = serializers.IntegerField()


class RetryCountSerializer(serializers.Serializer):
    retry_count = serializers.IntegerField()
    workflow_count = serializers.IntegerField()


class ErrorCodeCountSerializer(serializers.Serializer):
    error_code = serializers.CharField()
    count = serializers.IntegerField()


class StageFailureRateSerializer(serializers.Serializer):
    stage = serializers.CharField()
    failures = serializers.IntegerField()
    terminal_count = serializers.IntegerField()
    failure_rate = serializers.FloatField()


class LatencyPercentileSerializer(serializers.Serializer):
    p50 = serializers.FloatField(allow_null=True)
    p95 = serializers.FloatField(allow_null=True)
    p99 = serializers.FloatField(allow_null=True)


class LifecycleAnalyticsSerializer(serializers.Serializer):
    date_from = serializers.DateField()
    date_to = serializers.DateField()
    source = serializers.ChoiceField(choices=("clickhouse", "postgresql"))
    consistency = serializers.ChoiceField(choices=("eventually_consistent", "current_state"))
    generated_at = serializers.DateTimeField()
    data_lag_seconds = serializers.IntegerField(allow_null=True)
    oldest_event_time = serializers.DateTimeField(allow_null=True)
    latest_event_time = serializers.DateTimeField(allow_null=True)
    processed_per_minute = ProcessedMinuteSerializer(many=True)
    success_count = serializers.IntegerField()
    failure_count = serializers.IntegerField()
    success_rate = serializers.FloatField()
    failure_rate = serializers.FloatField()
    latency_ms = LatencyPercentileSerializer()
    retry_count_distribution = RetryCountSerializer(many=True)
    frequent_error_codes = ErrorCodeCountSerializer(many=True)
    failure_rate_by_stage = StageFailureRateSerializer(many=True)


class OverviewWorkflowSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    event_id = serializers.UUIDField()
    state = serializers.CharField()
    current_stage = serializers.CharField()
    created_at = serializers.DateTimeField()
    updated_at = serializers.DateTimeField()
    started_at = serializers.DateTimeField(allow_null=True)
    finished_at = serializers.DateTimeField(allow_null=True)
    attempt_count = serializers.IntegerField()


class OverviewEventSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    event_type = serializers.CharField()
    source = serializers.CharField()
    schema_version = serializers.IntegerField()
    idempotency_key = serializers.CharField()
    correlation_id = serializers.CharField()
    received_at = serializers.DateTimeField()
    workflow_id = serializers.UUIDField(allow_null=True)
    workflow_state = serializers.CharField(allow_null=True)


class OverviewSerializer(serializers.Serializer):
    generated_at = serializers.DateTimeField()
    event_count = serializers.IntegerField()
    processed_event_count = serializers.IntegerField()
    workflow_state_counts = serializers.DictField(child=serializers.IntegerField())
    average_processing_latency_ms = serializers.FloatField(allow_null=True)
    processed_per_minute = ProcessedMinuteSerializer(many=True)
    recent_events = OverviewEventSerializer(many=True)
    recent_workflows = OverviewWorkflowSerializer(many=True)
    outbox_pending_count = serializers.IntegerField()
    outbox_dead_lettered_count = serializers.IntegerField()
