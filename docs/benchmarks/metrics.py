"""
Prometheus Pushgateway exporter for locust tests.

Pushes metrics every 5 s to a Pushgateway instance (default: localhost:9091).
Override the gateway address via the PUSHGATEWAY_URL environment variable.

    PUSHGATEWAY_URL=http://10.255.32.132:9091 locust -f perf/load_test_dm.py ...

The Pushgateway stores the latest values; Prometheus scrapes them on its own
interval. Grafana dashboard "Locust Load Tests" shows results in real time.

Usage in each locust script:
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from locust import events
    import metrics

    @events.init.add_listener
    def on_locust_init(environment, **_kwargs):
        metrics.register(environment)
"""

import os
import time
import threading

from prometheus_client import (
    CollectorRegistry, Gauge, Counter, Histogram, push_to_gateway,
)

_PUSH_INTERVAL = 5  # seconds


def register(environment, job: str = "locust") -> None:
    gateway = os.environ.get("PUSHGATEWAY_URL", "localhost:9091")
    registry = CollectorRegistry()

    users = Gauge("locust_users", "Active locust users", registry=registry)
    requests = Counter(
        "locust_requests_total", "Total requests",
        ["method", "name", "status"],
        registry=registry,
    )
    response_time_hist = Histogram(
        "locust_response_time_seconds", "Response time in seconds",
        ["method", "name"],
        buckets=[0.01, 0.025, 0.05, 0.1, 0.2, 0.3, 0.5, 0.75, 1.0, 2.5, 5.0],
        registry=registry,
    )

    def on_request(request_type, name, response_time, exception, **kwargs):
        status = "failure" if exception else "success"
        requests.labels(method=request_type, name=name, status=status).inc()
        if not exception and response_time is not None:
            response_time_hist.labels(method=request_type, name=name).observe(
                response_time / 1000.0
            )

    def on_spawning_complete(user_count, **kwargs):
        users.set(user_count)

    def on_quitting(**kwargs):
        try:
            push_to_gateway(gateway, job=job, registry=registry)
        except Exception:
            pass

    def _push_loop():
        while True:
            time.sleep(_PUSH_INTERVAL)
            try:
                push_to_gateway(gateway, job=job, registry=registry)
            except Exception:
                pass

    environment.events.request.add_listener(on_request)
    environment.events.spawning_complete.add_listener(on_spawning_complete)
    environment.events.quitting.add_listener(on_quitting)

    threading.Thread(target=_push_loop, daemon=True).start()
