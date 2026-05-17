"""
Stress test for the Data Module — ramp-to-break scenario for Milestone 4 Scalability.

Progressively increases concurrent users until the system saturates, revealing the
primary bottleneck (CPU, PG connection pool, Redis memory, etc.).

Usage (run from docs/benchmarks/):
    pip install -r requirements.txt

    # Headless ramp — push to breaking point, HTML report saved next to this file
    locust -f scale/stress_test.py \
           --host=http://<vm-ip>:8080 \
           --headless \
           --run-time 8m \
           --html scale/stress_report_1x.html

    # Or from repo root:
    locust -f docs/benchmarks/scale/stress_test.py \
           --host=http://<vm-ip>:8080 \
           --headless --run-time 8m \
           --html docs/benchmarks/scale/stress_report_1x.html

    # Scale-out comparison (2 instances behind Nginx):
    locust -f scale/stress_test.py \
           --host=http://<vm-ip>:9090 \
           --headless --run-time 8m \
           --html scale/stress_report_2x.html

    # Web UI (watch live):
    locust -f scale/stress_test.py --host=http://<vm-ip>:8080

Shape:
  Stage 1   0 –  60 s  ramp   0 →  20 users  (warm-up)
  Stage 2  60 – 120 s  ramp  20 →  60 users  (normal load)
  Stage 3 120 – 180 s  ramp  60 → 120 users  (high load)
  Stage 4 180 – 240 s  ramp 120 → 200 users  (stress zone)
  Stage 5 240 – 300 s  ramp 200 → 350 users  (heavy stress)
  Stage 6 300 – 360 s  ramp 350 → 500 users  (breaking-point hunt)
  Stage 7 360 – 480 s  hold 500 users        (observe collapse)

Monitor during the run (on VM):
  docker stats --no-stream --format "table {{.Name}}\\t{{.CPUPerc}}\\t{{.MemUsage}}"
  watch -n2 'psql -U porto -d porto_logistica -c "SELECT count(*) FROM pg_stat_activity;"'
  Grafana -> data-module dashboard -> latency heatmap + error rate panels
"""

import random
from locust import HttpUser, task, between, LoadTestShape

KNOWN_PLATES = ["87AX60", "68BSH8", "98AZ00", "45BC30", "12DF90"]
GATE_IDS = [1, 2, 3]


# ---------------------------------------------------------------------------
# Load shape — staged ramp then sustained hold
# ---------------------------------------------------------------------------

class StressRampShape(LoadTestShape):
    """
    Returns (user_count, spawn_rate) per tick.
    None signals Locust to stop the test.
    """
    stages = [
        # (duration_s, target_users, spawn_rate)
        (60,  20,   1),   # warm-up
        (120, 60,   2),   # normal
        (180, 120,  3),   # high
        (240, 200,  5),   # stress
        (300, 350,  8),   # heavy stress
        (360, 500, 10),   # breaking point hunt
        (480, 500,  0),   # hold at peak — observe collapse
    ]

    def tick(self):
        run_time = self.get_run_time()
        for stage_end, users, rate in self.stages:
            if run_time < stage_end:
                return (users, rate if rate > 0 else 10)
        return None


# ---------------------------------------------------------------------------
# Stress user — hammers all critical paths simultaneously
# ---------------------------------------------------------------------------

class StressUser(HttpUser):
    """
    Sends the full mix of read + write traffic to identify bottlenecks.
    Task weights intentionally heavier than the load test to amplify pressure.
    """
    wait_time = between(0.1, 0.5)  # minimal think-time — maximise concurrency

    # -- PG read paths -------------------------------------------------------

    @task(8)
    def list_arrivals(self):
        status = random.choice(["in_transit", "scheduled", "unloading", ""])
        qs = f"?status={status}&skip=0&limit=20" if status else "?skip=0&limit=20"
        with self.client.get(
            f"/api/v1/arrivals{qs}",
            name="/arrivals [PG]",
            catch_response=True,
        ) as resp:
            if resp.status_code == 200:
                resp.success()
            else:
                resp.failure(f"status {resp.status_code}")

    @task(5)
    def get_arrival_by_id(self):
        appt_id = random.randint(1, 50)
        with self.client.get(
            f"/api/v1/arrivals/{appt_id}",
            name="/arrivals/:id [PG PK]",
            catch_response=True,
        ) as resp:
            if resp.status_code in (200, 404):
                resp.success()
            else:
                resp.failure(f"status {resp.status_code}")

    @task(4)
    def query_by_plate(self):
        plate = random.choice(KNOWN_PLATES)
        with self.client.get(
            f"/api/v1/arrivals/query/license-plate/{plate}",
            name="/arrivals/query/license-plate [PG idx]",
            catch_response=True,
        ) as resp:
            if resp.status_code in (200, 404):
                resp.success()
            else:
                resp.failure(f"status {resp.status_code}")

    @task(3)
    def next_arrivals_gate(self):
        gate = random.choice(GATE_IDS)
        with self.client.get(
            f"/api/v1/arrivals/next/{gate}?limit=5",
            name="/arrivals/next/:gate [PG]",
            catch_response=True,
        ) as resp:
            if resp.status_code == 200:
                resp.success()
            else:
                resp.failure(f"status {resp.status_code}")

    # -- Redis cache paths ---------------------------------------------------

    @task(6)
    def arrival_stats_cached(self):
        """Short-TTL Redis cache — many concurrent callers hammer this."""
        with self.client.get(
            "/api/v1/arrivals/stats",
            name="/arrivals/stats [Redis TTL]",
            catch_response=True,
        ) as resp:
            if resp.status_code == 200:
                resp.success()
            else:
                resp.failure(f"status {resp.status_code}")

    @task(5)
    def active_alerts_cached(self):
        with self.client.get(
            "/api/v1/alerts/active?limit=50",
            name="/alerts/active [Redis TTL]",
            catch_response=True,
        ) as resp:
            if resp.status_code == 200:
                resp.success()
            else:
                resp.failure(f"status {resp.status_code}")

    # -- Mongo aggregation paths (expensive) ---------------------------------

    @task(3)
    def statistics_summary(self):
        """Mongo aggregation pipeline — most expensive read, saturates first."""
        with self.client.get(
            "/api/v1/statistics/summary",
            name="/statistics/summary [Mongo aggr]",
            catch_response=True,
        ) as resp:
            if resp.status_code in (200, 404):
                resp.success()
            else:
                resp.failure(f"status {resp.status_code}")

    @task(2)
    def pipeline_performance(self):
        gate = random.choice(GATE_IDS)
        with self.client.get(
            f"/api/v1/statistics/pipeline/performance?gate_id={gate}&hours=24",
            name="/statistics/pipeline/performance [Redis+Mongo]",
            catch_response=True,
        ) as resp:
            if resp.status_code in (200, 404):
                resp.success()
            else:
                resp.failure(f"status {resp.status_code}")

    # -- Write path (PG insert -> Outbox -> Mongo) ---------------------------

    @task(2)
    def detection_event_write(self):
        """
        Write path — inserts into PG outbox.
        Under stress this saturates PG connection pool before the reads do.
        """
        with self.client.post(
            "/api/v1/decisions/detection-event",
            json={
                "type": "license_plate_detection",
                "license_plate": random.choice(KNOWN_PLATES),
                "gate_id": random.choice(GATE_IDS),
                "confidence": round(random.uniform(0.7, 1.0), 2),
                "agent": "AgentB",
            },
            name="/decisions/detection-event [PG write+outbox]",
            catch_response=True,
        ) as resp:
            if resp.status_code == 200:
                resp.success()
            else:
                resp.failure(f"status {resp.status_code}")

    # -- Redis miss -> PG fallback -------------------------------------------

    @task(1)
    def driver_cache_miss(self):
        """Unknown plate forces Redis miss and PG query every time."""
        fake_plate = f"ST{random.randint(10000, 99999)}"
        with self.client.get(
            f"/api/v1/drivers/me/active?drivers_license={fake_plate}",
            name="/drivers/me/active [cache miss->PG]",
            catch_response=True,
        ) as resp:
            if resp.status_code in (200, 401, 404):
                resp.success()
            else:
                resp.failure(f"status {resp.status_code}")
