"""Gunicorn hooks for Prometheus multiprocess metric lifecycle."""

import os
from pathlib import Path


def on_starting(_server):
    metrics_dir = os.environ.get("PROMETHEUS_MULTIPROC_DIR")
    if metrics_dir:
        path = Path(metrics_dir)
        path.mkdir(parents=True, exist_ok=True)
        for metric_file in path.glob("*.db"):
            metric_file.unlink(missing_ok=True)


def child_exit(_server, worker):
    if os.environ.get("PROMETHEUS_MULTIPROC_DIR"):
        from prometheus_client import multiprocess

        multiprocess.mark_process_dead(worker.pid)
