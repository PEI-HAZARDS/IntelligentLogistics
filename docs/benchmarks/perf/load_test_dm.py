"""
Load tests for Data Module polyglot persistence (PostgreSQL + MongoDB + Redis).

Usage (run from docs/benchmarks/):
    pip install -r requirements.txt

    # Headless — 50 users, 5 min, HTML report saved next to this file
    locust -f perf/load_test_dm.py --host=http://<vm-ip>:8080 --headless \
           -u 50 -r 5 --run-time 5m \
           --html perf/dm_report.html

    # Or from repo root:
    locust -f docs/benchmarks/perf/load_test_dm.py --host=http://<vm-ip>:8080 \
           --headless -u 50 -r 5 --run-time 5m \
           --html docs/benchmarks/perf/dm_report.html

    # Web UI:
    locust -f perf/load_test_dm.py --host=http://<vm-ip>:8080
    # Then open http://localhost:8089

Scenarios covered:
  - PG read path: paginated arrivals list, single arrival by id
  - Redis cache: repeated reads that should hit cache after first miss
  - Redis miss → PG fallback: driver active appointment
  - Mongo: statistics/pipeline aggregation endpoint
  - Write path: detection-event POST (inserts into PG outbox, projects to Mongo)
  - Concurrent reads: stats endpoint under parallel load
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from locust import HttpUser, task, between, events
import metrics


@events.init.add_listener
def on_locust_init(environment, **_kwargs):
    metrics.register(environment)
import random

# Seeded license plates from data_init_trial.py / data_init_demo.py
KNOWN_PLATES = ["87AX60", "68BSH8", "98AZ00", "45BC30", "12DF90"]
GATE_IDS = [1, 2, 3]


class ReadHeavyUser(HttpUser):
    """
    Simulates the gate-operator dashboard — mostly reads, some writes.
    Targets the PG read path + Redis cache layer.
    """
    wait_time = between(0.5, 2)

    # -------------------------------------------------------------------------
    # PG read path — arrival list (paginated, goes through arrival_queries.py)
    # -------------------------------------------------------------------------

    @task(5)
    def list_arrivals_default(self):
        with self.client.get(
            "/api/v1/arrivals?skip=0&limit=20",
            name="/arrivals (default)",
            catch_response=True,
        ) as resp:
            if resp.status_code == 200:
                resp.success()
            else:
                resp.failure(f"status {resp.status_code}")

    @task(3)
    def list_arrivals_filtered_in_transit(self):
        with self.client.get(
            "/api/v1/arrivals?status=in_transit&skip=0&limit=20",
            name="/arrivals?status=in_transit",
            catch_response=True,
        ) as resp:
            if resp.status_code == 200:
                resp.success()
            else:
                resp.failure(f"status {resp.status_code}")

    @task(2)
    def list_arrivals_filtered_scheduled(self):
        with self.client.get(
            "/api/v1/arrivals?status=scheduled&skip=0&limit=20",
            name="/arrivals?status=scheduled",
            catch_response=True,
        ) as resp:
            if resp.status_code == 200:
                resp.success()
            else:
                resp.failure(f"status {resp.status_code}")

    @task(2)
    def list_arrivals_filtered_unloading(self):
        """Virtual filter — JOIN with Visit table."""
        with self.client.get(
            "/api/v1/arrivals?status=unloading&skip=0&limit=20",
            name="/arrivals?status=unloading",
            catch_response=True,
        ) as resp:
            if resp.status_code == 200:
                resp.success()
            else:
                resp.failure(f"status {resp.status_code}")

    @task(3)
    def get_arrival_by_id(self):
        """Single appointment lookup — exercises PG primary key path."""
        appt_id = random.randint(1, 50)
        with self.client.get(
            f"/api/v1/arrivals/{appt_id}",
            name="/arrivals/:id",
            catch_response=True,
        ) as resp:
            if resp.status_code in (200, 404):
                resp.success()
            else:
                resp.failure(f"status {resp.status_code}")

    @task(2)
    def query_by_license_plate(self):
        plate = random.choice(KNOWN_PLATES)
        with self.client.get(
            f"/api/v1/arrivals/query/license-plate/{plate}",
            name="/arrivals/query/license-plate/:plate",
            catch_response=True,
        ) as resp:
            if resp.status_code in (200, 404):
                resp.success()
            else:
                resp.failure(f"status {resp.status_code}")

    @task(2)
    def next_arrivals_gate(self):
        gate = random.choice(GATE_IDS)
        with self.client.get(
            f"/api/v1/arrivals/next/{gate}?limit=5",
            name="/arrivals/next/:gate",
            catch_response=True,
        ) as resp:
            if resp.status_code == 200:
                resp.success()
            else:
                resp.failure(f"status {resp.status_code}")

    # -------------------------------------------------------------------------
    # Redis cache path — arrival stats (short TTL cached result)
    # -------------------------------------------------------------------------

    @task(4)
    def arrival_stats(self):
        """Stats are Redis-cached — first call misses, subsequent calls hit."""
        with self.client.get(
            "/api/v1/arrivals/stats",
            name="/arrivals/stats (Redis TTL)",
            catch_response=True,
        ) as resp:
            if resp.status_code == 200:
                resp.success()
            else:
                resp.failure(f"status {resp.status_code}")

    # -------------------------------------------------------------------------
    # Redis cache path — alerts list (active_alerts_list_key, 30 s TTL)
    # -------------------------------------------------------------------------

    @task(3)
    def active_alerts(self):
        with self.client.get(
            "/api/v1/alerts/active?limit=50",
            name="/alerts/active (Redis TTL)",
            catch_response=True,
        ) as resp:
            if resp.status_code == 200:
                resp.success()
            else:
                resp.failure(f"status {resp.status_code}")

    @task(1)
    def active_alerts_custom_limit(self):
        """Custom limit bypasses the Redis list cache — goes straight to PG."""
        with self.client.get(
            "/api/v1/alerts/active?limit=10",
            name="/alerts/active (cache bypass)",
            catch_response=True,
        ) as resp:
            if resp.status_code == 200:
                resp.success()
            else:
                resp.failure(f"status {resp.status_code}")

    # -------------------------------------------------------------------------
    # Redis → PG fallback — driver active appointment (BR-29)
    # -------------------------------------------------------------------------

    @task(1)
    def driver_active_miss(self):
        """Unknown license triggers Redis miss → PG query."""
        plate = f"XX{random.randint(10000, 99999)}"
        with self.client.get(
            f"/api/v1/drivers/me/active?drivers_license={plate}",
            name="/drivers/me/active (cache miss)",
            catch_response=True,
        ) as resp:
            if resp.status_code in (200, 401, 404):
                resp.success()
            else:
                resp.failure(f"status {resp.status_code}")

    # -------------------------------------------------------------------------
    # Write path — detection event (PG insert → Outbox → Mongo projection)
    # -------------------------------------------------------------------------

    @task(1)
    def register_detection_event(self):
        plate = random.choice(KNOWN_PLATES)
        gate = random.choice(GATE_IDS)
        with self.client.post(
            "/api/v1/decisions/detection-event",
            json={
                "type": "license_plate_detection",
                "license_plate": plate,
                "gate_id": gate,
                "confidence": round(random.uniform(0.7, 1.0), 2),
                "agent": "AgentB",
            },
            name="/decisions/detection-event (PG write)",
            catch_response=True,
        ) as resp:
            if resp.status_code == 200:
                resp.success()
            else:
                resp.failure(f"status {resp.status_code}")


class ManagerDashboardUser(HttpUser):
    """
    Simulates the logistics manager dashboard — statistics-heavy, Mongo aggregation.
    """
    wait_time = between(1, 3)

    @task(5)
    def manager_summary(self):
        """Main KPI block — hits manager_statistics_queries.py → Mongo aggregation."""
        with self.client.get(
            "/api/v1/statistics/summary",
            name="/statistics/summary (Mongo aggr)",
            catch_response=True,
        ) as resp:
            if resp.status_code in (200, 404):
                resp.success()
            else:
                resp.failure(f"status {resp.status_code}")

    @task(3)
    def pipeline_stats_gate(self):
        """Per-gate pipeline stats — Redis cached, falls back to Mongo."""
        gate = random.choice(GATE_IDS)
        with self.client.get(
            f"/api/v1/statistics/pipeline/performance?gate_id={gate}&hours=24",
            name="/statistics/pipeline/performance (Redis+Mongo)",
            catch_response=True,
        ) as resp:
            if resp.status_code in (200, 404):
                resp.success()
            else:
                resp.failure(f"status {resp.status_code}")

    @task(2)
    def decision_events(self):
        """Mongo read — decision event log."""
        with self.client.get(
            "/api/v1/decisions/events/decisions?limit=20",
            name="/decisions/events/decisions (Mongo)",
            catch_response=True,
        ) as resp:
            if resp.status_code == 200:
                resp.success()
            else:
                resp.failure(f"status {resp.status_code}")

    @task(2)
    def detection_events(self):
        with self.client.get(
            "/api/v1/decisions/events/detections?limit=20",
            name="/decisions/events/detections (Mongo)",
            catch_response=True,
        ) as resp:
            if resp.status_code == 200:
                resp.success()
            else:
                resp.failure(f"status {resp.status_code}")

    @task(1)
    def alert_stats(self):
        with self.client.get(
            "/api/v1/alerts/stats",
            name="/alerts/stats",
            catch_response=True,
        ) as resp:
            if resp.status_code == 200:
                resp.success()
            else:
                resp.failure(f"status {resp.status_code}")
