import uuid
from datetime import UTC, datetime

import pytest

from apps.analytics.management.commands.consume_lifecycle_analytics import project_record
from apps.analytics.sink import AnalyticsUnavailable, ClickHouseLifecycleSink, make_analytical_row
from apps.processing.contracts import encode_message


def lifecycle_event(event_type="workflow.succeeded", *, attempt=1, duration=12):
    event_id = str(uuid.uuid4())
    workflow_id = str(uuid.uuid4())
    return {
        "event_id": event_id,
        "workflow_id": workflow_id,
        "event_type": event_type,
        "schema_version": 1,
        "correlation_id": "analytics-test",
        "occurred_at": "2040-01-02T03:04:05+00:00",
        "recorded_at": "2040-01-02T03:04:05+00:00",
        "payload": {
            "state": "SUCCEEDED",
            "stage": "order_validation",
            "attempt_number": attempt,
            "error_code": "",
            "duration_ms": duration,
        },
    }


class FakeClickHouse:
    def __init__(self, *, fail=False):
        self.rows = []
        self.fail = fail

    def insert(self, table, rows, *, column_names):
        if self.fail:
            raise TimeoutError("private endpoint detail")
        self.rows.extend(rows)


def test_lifecycle_fact_has_deterministic_identity_for_duplicate_delivery():
    event = lifecycle_event()
    assert make_analytical_row(event)["lifecycle_id"] == make_analytical_row(event)["lifecycle_id"]


def test_sink_maps_lifecycle_fields_and_wraps_temporary_outage():
    event = lifecycle_event()
    client = FakeClickHouse()
    sink = ClickHouseLifecycleSink(client)
    sink.write(event)
    assert len(client.rows) == 1
    assert client.rows[0][0] == make_analytical_row(event)["lifecycle_id"]
    with pytest.raises(AnalyticsUnavailable, match="not confirmed"):
        ClickHouseLifecycleSink(FakeClickHouse(fail=True)).write(event)


def test_consumer_commits_only_after_clickhouse_insert_succeeds():
    class Record:
        value = encode_message(lifecycle_event(), lifecycle=True)

    class Consumer:
        committed = False

        def commit(self, _record):
            self.committed = True

    consumer = Consumer()
    fake_client = FakeClickHouse(fail=True)
    failing_sink = ClickHouseLifecycleSink(fake_client)
    with pytest.raises(AnalyticsUnavailable):
        project_record(Record(), sink=failing_sink, consumer=consumer)
    assert not consumer.committed

    fake_client.fail = False
    project_record(Record(), sink=failing_sink, consumer=consumer)
    assert consumer.committed
    assert len(fake_client.rows) == 1


@pytest.mark.integration
def test_clickhouse_seeded_lifecycle_analytics():
    import os

    if os.getenv("EVENTFLOW_RUN_CLICKHOUSE_INTEGRATION") != "1":
        pytest.skip("Set EVENTFLOW_RUN_CLICKHOUSE_INTEGRATION=1 for live ClickHouse checks.")
    from apps.analytics.queries import lifecycle_report
    from apps.analytics.sink import ClickHouseLifecycleSink

    sink = ClickHouseLifecycleSink()
    cases = [
        lifecycle_event("workflow.succeeded", attempt=1, duration=120),
        lifecycle_event("workflow.failed", attempt=2, duration=800),
        lifecycle_event("workflow.retry_wait", attempt=1, duration=None),
    ]
    for event in cases:
        event["event_id"] = str(
            uuid.uuid5(uuid.NAMESPACE_URL, f"m3-seed:{event['event_type']}:event")
        )
        event["workflow_id"] = str(
            uuid.uuid5(uuid.NAMESPACE_URL, f"m3-seed:{event['event_type']}:workflow")
        )
        event["recorded_at"] = datetime(2041, 1, 2, 3, 4, 5, tzinfo=UTC).isoformat()
        event["occurred_at"] = event["recorded_at"]
        if event["event_type"] == "workflow.failed":
            event["payload"].update(state="FAILED", error_code="TEST_FAILURE")
        elif event["event_type"] == "workflow.retry_wait":
            event["payload"].update(state="RETRY_WAIT", error_code="TEMPORARY", duration_ms=None)
        sink.write(event)
        if event["event_type"] == "workflow.succeeded":
            sink.write(event)  # emulate Kafka replay after insert-before-offset-commit crash
            row = make_analytical_row(event)
            result = sink.client.query(
                "SELECT count() FROM eventflow.workflow_lifecycle_facts FINAL "
                "WHERE lifecycle_id = {lifecycle_id:UUID}",
                parameters={"lifecycle_id": str(row["lifecycle_id"])},
            ).result_rows[0][0]
            assert result == 1
    report = lifecycle_report(datetime(2041, 1, 2).date(), datetime(2041, 1, 2).date())
    assert report["success_count"] == 1
    assert report["failure_count"] == 1
    assert report["success_rate"] == 0.5
    assert report["failure_rate"] == 0.5
    assert report["processed_per_minute"] == [(datetime(2041, 1, 2, 3, 4), 2)]
    assert report["latency_ms_p50_p95_p99"] == pytest.approx([460, 766, 793], abs=1)
    assert report["retry_count_distribution"] == [(1, 1)]
    assert report["frequent_error_codes"] == [("TEST_FAILURE", 1)]
    assert report["failure_rate_by_stage"] == [
        {"stage": "order_validation", "failures": 1, "terminal_count": 2, "failure_rate": 0.5}
    ]
    assert report["oldest_event_time"] == datetime(2041, 1, 2, 3, 4, 5)
    assert report["latest_event_time"] == datetime(2041, 1, 2, 3, 4, 5)


@pytest.mark.integration
def test_clickhouse_replay_after_offset_commit_failure_is_idempotent():
    import os

    from django.conf import settings

    from apps.analytics.sink import TABLE

    if os.getenv("EVENTFLOW_RUN_CLICKHOUSE_INTEGRATION") != "1":
        pytest.skip("Set EVENTFLOW_RUN_CLICKHOUSE_INTEGRATION=1 for live ClickHouse checks.")

    event = lifecycle_event()

    class Record:
        value = encode_message(event, lifecycle=True)

    class CommitFailsOnce:
        calls = 0

        def commit(self, _record):
            self.calls += 1
            if self.calls == 1:
                raise RuntimeError("simulated offset commit interruption")

    consumer = CommitFailsOnce()
    sink = ClickHouseLifecycleSink()
    try:
        with pytest.raises(RuntimeError, match="offset commit interruption"):
            project_record(Record(), sink=sink, consumer=consumer)
        project_record(Record(), sink=sink, consumer=consumer)
        lifecycle_id = str(make_analytical_row(event)["lifecycle_id"])
        count = sink.client.query(
            f"SELECT count() FROM {settings.CLICKHOUSE_DATABASE}.{TABLE} FINAL "
            "WHERE lifecycle_id = {lifecycle_id:UUID}",
            parameters={"lifecycle_id": lifecycle_id},
        ).result_rows[0][0]
        assert consumer.calls == 2
        assert count == 1
    finally:
        sink.client.close()
