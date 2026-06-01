"""
AI_APP horizontal scale-out stress test — Milestone 4 Scalability.

Simulates N concurrent AI_APP pipelines hitting the V_APP API Gateway,
validating the core scalability model:

    Camera 1 -> AI_APP #1 -+
    Camera 2 -> AI_APP #2  +--> V_APP API Gateway (1 instance per port)
    Camera N -> AI_APP #N -+

Note: The real AI_APP -> V_APP path uses Kafka for event publishing (AgentA/B/C
topics). What is measured here is the HTTP read path that the Decision Engine
and V_Brain trigger after consuming those Kafka events:
  1. License plate lookup  -> GET /api/arrivals/query/license-plate/{plate}
  2. Next arrivals at gate -> GET /api/arrivals/next/{gate_id}
  3. Active alerts check   -> GET /api/alerts/active
  4. Statistics read       -> GET /api/statistics/summary  (Mongo aggregation)

Each Locust user = 1 AI_APP pipeline processing detections for 1 camera.

Usage (run from docs/benchmarks/):
    pip install -r requirements.txt

    # 1. Obtain a token once (avoids Keycloak brute-force protection under
    #    concurrent spawns — all pipelines share the same long-lived JWT):
    TOKEN=$(curl -s -X POST http://<vm-ip>:8000/api/auth/workers/login \\
      -H 'Content-Type: application/json' \\
      -d '{"email":"manager@example.pt","password":"password123"}' \\
      | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

    # 2. Run the stress test:
    BEARER_TOKEN=$TOKEN locust -f scale/stress_test_ai.py \\
           --host=http://<vm-ip>:8000 \\
           --headless \\
           --run-time 8m \\
           --html scale/stress_report_ai.html

    # Or from repo root:
    BEARER_TOKEN=$TOKEN locust -f docs/benchmarks/scale/stress_test_ai.py \\
           --host=http://<vm-ip>:8000 \\
           --headless --run-time 8m \\
           --html docs/benchmarks/scale/stress_report_ai.html

    # Web UI (set BEARER_TOKEN in env before launching):
    BEARER_TOKEN=$TOKEN locust -f scale/stress_test_ai.py --host=http://<vm-ip>:8000

Shape:
  Stage 1   0 –  60 s   1 ->  5 AI_APPs   (1 camera per gate)
  Stage 2  60 – 120 s   5 -> 10 AI_APPs   (2 cameras per gate)
  Stage 3 120 – 180 s  10 -> 20 AI_APPs   (high camera density)
  Stage 4 180 – 300 s  20 -> 30 AI_APPs   (stress — breaking point hunt)
  Stage 5 300 – 480 s  30 (hold)          (sustained load)
"""

import os
import random

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from locust import HttpUser, task, between, LoadTestShape, events
import metrics


@events.init.add_listener
def on_locust_init(environment, **_kwargs):
    metrics.register(environment)

KNOWN_PLATES = ["87AX60", "68BSH8", "98AZ00", "45BC30", "12DF90", "33GH72", "77KL01"]
GATE_IDS = [1, 2, 3]

# Token obtained once before the run via BEARER_TOKEN env var.
# All virtual users share this token — mirrors the real AI_APP behaviour where
# each instance logs in once and reuses its JWT for the session lifetime.
BEARER_TOKEN = os.environ.get("BEARER_TOKEN", "")


class AIAppPipelineShape(LoadTestShape):
    """Each user = 1 AI_APP pipeline (1 camera). Ramp to 30 concurrent pipelines."""
    stages = [
        # (duration_s, target_users, spawn_rate)
        (60,  5,  1),
        (120, 10, 1),
        (180, 20, 2),
        (300, 30, 2),
        (480, 30, 0),
    ]

    def tick(self):
        run_time = self.get_run_time()
        for stage_end, users, rate in self.stages:
            if run_time < stage_end:
                return (users, rate if rate > 0 else 5)
        return None


class AIAppPipeline(HttpUser):
    """
    Simulates the HTTP read load a single AI_APP pipeline generates on V_APP
    after publishing detection events to Kafka.
    """
    wait_time = between(0.5, 2.0)

    def on_start(self):
        self.gate_id = random.choice(GATE_IDS)
        self.headers = {"Authorization": f"Bearer {BEARER_TOKEN}"}

    @task(5)
    def license_plate_lookup(self):
        """Decision Engine queries appointment for detected plate."""
        plate = random.choice(KNOWN_PLATES)
        with self.client.get(
            f"/api/arrivals/query/license-plate/{plate}",
            name="/api/arrivals/query/license-plate [plate lookup]",
            headers=self.headers,
            catch_response=True,
        ) as resp:
            if resp.status_code in (200, 404):
                resp.success()
            else:
                resp.failure(f"status {resp.status_code}")

    @task(4)
    def next_arrivals(self):
        """Gate operator / Decision Engine checks next scheduled arrivals."""
        with self.client.get(
            f"/api/arrivals/next/{self.gate_id}",
            name="/api/arrivals/next/:gate [scheduled queue]",
            headers=self.headers,
            catch_response=True,
        ) as resp:
            if resp.status_code == 200:
                resp.success()
            else:
                resp.failure(f"status {resp.status_code}")

    @task(3)
    def active_alerts(self):
        """V_Brain checks active alerts after each detection cycle."""
        with self.client.get(
            "/api/alerts/active",
            name="/api/alerts/active [alert check]",
            headers=self.headers,
            catch_response=True,
        ) as resp:
            if resp.status_code == 200:
                resp.success()
            else:
                resp.failure(f"status {resp.status_code}")

    @task(2)
    def statistics_summary(self):
        """Manager dashboard — Mongo aggregation pipeline."""
        with self.client.get(
            "/api/statistics/summary",
            name="/api/statistics/summary [Mongo aggr]",
            headers=self.headers,
            catch_response=True,
        ) as resp:
            if resp.status_code in (200, 404):
                resp.success()
            else:
                resp.failure(f"status {resp.status_code}")

    @task(1)
    def arrivals_stats(self):
        """Redis-cached arrival stats — fast path."""
        with self.client.get(
            "/api/arrivals/stats",
            name="/api/arrivals/stats [Redis cache]",
            headers=self.headers,
            catch_response=True,
        ) as resp:
            if resp.status_code == 200:
                resp.success()
            else:
                resp.failure(f"status {resp.status_code}")
