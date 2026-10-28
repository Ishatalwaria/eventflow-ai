"""Bounded analytical reads; PostgreSQL remains authoritative for live state."""

from datetime import date

from django.conf import settings

from .sink import TABLE, create_clickhouse_client


def lifecycle_report(start_date: date, end_date: date, *, client=None):
    if end_date < start_date or (end_date - start_date).days > 366:
        raise ValueError("Date range must be ordered and no longer than 367 days.")
    client = client or create_clickhouse_client()
    table = f"{settings.CLICKHOUSE_DATABASE}.{TABLE} FINAL"
    params = {"start_date": start_date, "end_date": end_date}
    processed = client.query(
        f"""SELECT toStartOfMinute(event_time) AS minute, count()
            FROM {table}
            WHERE event_date BETWEEN {{start_date:Date}} AND {{end_date:Date}}
              AND event_type IN ('workflow.succeeded','workflow.failed','workflow.dead_lettered')
            GROUP BY minute ORDER BY minute""",
        parameters=params,
    ).result_rows
    rate = client.query(
        f"""SELECT countIf(event_type = 'workflow.succeeded') AS succeeded,
                   countIf(event_type IN ('workflow.failed','workflow.dead_lettered')) AS failed
            FROM {table}
            WHERE event_date BETWEEN {{start_date:Date}} AND {{end_date:Date}}
              AND event_type IN (
                  'workflow.succeeded','workflow.failed','workflow.dead_lettered'
              )""",
        parameters=params,
    ).result_rows[0]
    latency = client.query(
        f"""SELECT quantiles(0.50, 0.95, 0.99)(duration_ms)
            FROM {table}
            WHERE event_date BETWEEN {{start_date:Date}} AND {{end_date:Date}}
              AND event_type IN ('workflow.succeeded','workflow.failed','workflow.dead_lettered')
              AND duration_ms IS NOT NULL""",
        parameters=params,
    ).result_rows[0][0]
    retries = client.query(
        f"""SELECT retry_count, count() FROM
            (SELECT workflow_id, count() AS retry_count FROM {table}
            WHERE event_date BETWEEN {{start_date:Date}} AND {{end_date:Date}}
              AND event_type = 'workflow.retry_wait' GROUP BY workflow_id)
            GROUP BY retry_count ORDER BY retry_count""",
        parameters=params,
    ).result_rows
    errors = client.query(
        f"""SELECT error_code, count() FROM {table}
            WHERE event_date BETWEEN {{start_date:Date}} AND {{end_date:Date}}
              AND event_type IN ('workflow.failed','workflow.dead_lettered')
              AND error_code != '' GROUP BY error_code ORDER BY count() DESC LIMIT 20""",
        parameters=params,
    ).result_rows
    stages = client.query(
        f"""SELECT stage, countIf(event_type IN ('workflow.failed','workflow.dead_lettered')),
                   countIf(event_type IN (
                       'workflow.succeeded','workflow.failed','workflow.dead_lettered'
                   ))
            FROM {table}
            WHERE event_date BETWEEN {{start_date:Date}} AND {{end_date:Date}}
              AND event_type IN ('workflow.succeeded','workflow.failed','workflow.dead_lettered')
            GROUP BY stage ORDER BY stage""",
        parameters=params,
    ).result_rows
    freshness = client.query(
        f"""SELECT min(event_time), max(event_time) FROM {table}
            WHERE event_date BETWEEN {{start_date:Date}} AND {{end_date:Date}}""",
        parameters=params,
    ).result_rows[0]
    succeeded, failed = rate
    total = succeeded + failed
    return {
        "processed_per_minute": processed,
        "success_count": succeeded,
        "failure_count": failed,
        "failure_rate": failed / total if total else 0.0,
        "success_rate": succeeded / total if total else 0.0,
        "latency_ms_p50_p95_p99": latency,
        "retry_count_distribution": retries,
        "frequent_error_codes": errors,
        "failure_rate_by_stage": [
            {
                "stage": stage,
                "failures": failures,
                "terminal_count": count,
                "failure_rate": failures / count if count else 0.0,
            }
            for stage, failures, count in stages
        ],
        "oldest_event_time": freshness[0],
        "latest_event_time": freshness[1],
    }
