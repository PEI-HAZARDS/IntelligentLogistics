"""
Load tests for the API Gateway — authenticated proxy layer (Keycloak + FastAPI).

Usage (run from docs/benchmarks/):
    pip install -r requirements.txt

    # Headless — operator scenario, 30 concurrent users, 5 min
    locust -f perf/load_test_gw.py --host=http://<vm-ip>:8000 \
           --headless -u 30 -r 3 --run-time 5m \
           --html perf/gw_report.html

    # Or from repo root:
    locust -f docs/benchmarks/perf/load_test_gw.py --host=http://<vm-ip>:8000 \
           --headless -u 30 -r 3 --run-time 5m \
           --html docs/benchmarks/perf/gw_report.html

    # Web UI:
    locust -f perf/load_test_gw.py --host=http://<vm-ip>:8000

Environment variables (override defaults):
    OPERATOR_EMAIL      — email of a seeded operator (default: worker@porto.pt)
    OPERATOR_PASSWORD   — password (default: password123)
    MANAGER_EMAIL       — email of a seeded manager (default: manager@example.pt)
    MANAGER_PASSWORD    — password (default: password123)

Scenarios covered:
  - JWT login flow (Keycloak ROPC via API GW /api/auth/workers/login)
  - Operator dashboard: arrivals list, single arrival, next-gate, alerts
  - Manager dashboard: statistics summary, pipeline performance, alert stats
  - Mixed traffic: operator 70% / manager 30%
"""

import os
import random
import time
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from locust import HttpUser, task, between, events
import metrics


@events.init.add_listener
def on_locust_init(environment, **_kwargs):
    metrics.register(environment)

# ---------------------------------------------------------------------------
# Seed data — must match data_init_demo.py / data_init_trial.py
# ---------------------------------------------------------------------------
KNOWN_PLATES = ["87AX60", "68BSH8", "98AZ00", "45BC30", "12DF90"]
GATE_IDS = [1, 2, 3]

OPERATOR_EMAIL = os.getenv("OPERATOR_EMAIL", "worker@porto.pt")
OPERATOR_PASSWORD = os.getenv("OPERATOR_PASSWORD", "password123")
MANAGER_EMAIL = os.getenv("MANAGER_EMAIL", "manager@example.pt")
MANAGER_PASSWORD = os.getenv("MANAGER_PASSWORD", "password123")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _login(client, email: str, password: str, retries: int = 2) -> str | None:
    """POST /api/auth/workers/login and return the access token (or None on error).

    Retries on transient failures (Keycloak connection pool saturation during ramp-up).
    """
    for attempt in range(retries + 1):
        with client.post(
            "/api/auth/workers/login",
            json={"email": email, "password": password},
            name="/auth/workers/login",
            catch_response=True,
        ) as resp:
            if resp.status_code == 200:
                resp.success()
                return resp.json().get("access_token")
            elif attempt < retries:
                resp.success()  # suppress intermediate failure — will retry
                time.sleep(1 + attempt)
            else:
                resp.failure(f"Login failed after {retries + 1} attempts: {resp.status_code}")
    return None


def _auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# Operator user — simulates gate-operator dashboard
# ---------------------------------------------------------------------------

class OperatorUser(HttpUser):
    """
    Gate operator: reads arrivals and alerts.
    Weight 7 — represents 70% of the simulated user mix.
    """
    weight = 7
    wait_time = between(0.5, 2)

    def on_start(self):
        self.token = _login(self.client, OPERATOR_EMAIL, OPERATOR_PASSWORD)

    # -- Arrivals list (the main page the operator sees) --------------------

    @task(6)
    def list_arrivals(self):
        if not self.token:
            return
        with self.client.get(
            "/api/arrivals?page=1&limit=20",
            headers=_auth_headers(self.token),
            name="/arrivals (list, default)",
            catch_response=True,
        ) as resp:
            if resp.status_code == 200:
                resp.success()
            elif resp.status_code == 401:
                # Token expired — re-login
                self.token = _login(self.client, OPERATOR_EMAIL, OPERATOR_PASSWORD)
                resp.failure("Token expired, re-logged in")
            else:
                resp.failure(f"status {resp.status_code}")

    @task(3)
    def list_arrivals_in_transit(self):
        if not self.token:
            return
        with self.client.get(
            "/api/arrivals?status=in_transit&page=1&limit=20",
            headers=_auth_headers(self.token),
            name="/arrivals?status=in_transit",
            catch_response=True,
        ) as resp:
            if resp.status_code == 200:
                resp.success()
            else:
                resp.failure(f"status {resp.status_code}")

    @task(2)
    def list_arrivals_scheduled(self):
        if not self.token:
            return
        with self.client.get(
            "/api/arrivals?status=scheduled&page=1&limit=20",
            headers=_auth_headers(self.token),
            name="/arrivals?status=scheduled",
            catch_response=True,
        ) as resp:
            if resp.status_code == 200:
                resp.success()
            else:
                resp.failure(f"status {resp.status_code}")

    @task(2)
    def get_arrival_by_id(self):
        if not self.token:
            return
        appt_id = random.randint(1, 30)
        with self.client.get(
            f"/api/arrivals/{appt_id}",
            headers=_auth_headers(self.token),
            name="/arrivals/:id",
            catch_response=True,
        ) as resp:
            if resp.status_code in (200, 404):
                resp.success()
            else:
                resp.failure(f"status {resp.status_code}")

    @task(2)
    def next_arrivals_gate(self):
        if not self.token:
            return
        gate = random.choice(GATE_IDS)
        with self.client.get(
            f"/api/arrivals/next/{gate}",
            headers=_auth_headers(self.token),
            name="/arrivals/next/:gate",
            catch_response=True,
        ) as resp:
            if resp.status_code in (200, 404):
                resp.success()
            else:
                resp.failure(f"status {resp.status_code}")

    # -- Alerts (active list) -----------------------------------------------

    @task(3)
    def active_alerts(self):
        if not self.token:
            return
        with self.client.get(
            "/api/alerts/active?limit=50",
            headers=_auth_headers(self.token),
            name="/alerts/active",
            catch_response=True,
        ) as resp:
            if resp.status_code == 200:
                resp.success()
            else:
                resp.failure(f"status {resp.status_code}")

    @task(1)
    def search_arrivals_by_plate(self):
        if not self.token:
            return
        plate = random.choice(KNOWN_PLATES)
        with self.client.get(
            f"/api/arrivals?search={plate}&page=1&limit=10",
            headers=_auth_headers(self.token),
            name="/arrivals?search=:plate",
            catch_response=True,
        ) as resp:
            if resp.status_code == 200:
                resp.success()
            else:
                resp.failure(f"status {resp.status_code}")


# ---------------------------------------------------------------------------
# Manager user — simulates logistics manager dashboard (statistics-heavy)
# ---------------------------------------------------------------------------

class ManagerUser(HttpUser):
    """
    Logistics manager: statistics, KPIs, pipeline performance.
    Weight 3 — represents 30% of the simulated user mix.
    """
    weight = 3
    wait_time = between(1, 3)

    def on_start(self):
        self.token = _login(self.client, MANAGER_EMAIL, MANAGER_PASSWORD)

    def _get(self, url: str, name: str, ok_codes: tuple = (200,)):
        if not self.token:
            return
        with self.client.get(
            url,
            headers=_auth_headers(self.token),
            name=name,
            catch_response=True,
        ) as resp:
            if resp.status_code in ok_codes:
                resp.success()
            elif resp.status_code == 401:
                self.token = _login(self.client, MANAGER_EMAIL, MANAGER_PASSWORD)
                resp.failure("Token expired, re-logged in")
            else:
                resp.failure(f"status {resp.status_code}")

    @task(5)
    def statistics_summary(self):
        self._get("/api/statistics/summary", "/statistics/summary (Mongo aggr)")

    @task(4)
    def pipeline_performance(self):
        gate = random.choice(GATE_IDS)
        self._get(
            f"/api/statistics/pipeline/performance?gate_id={gate}&hours=24",
            "/statistics/pipeline/performance",
            ok_codes=(200, 404),
        )

    @task(3)
    def list_all_arrivals_overview(self):
        self._get("/api/arrivals?page=1&limit=50", "/arrivals (manager overview)")

    @task(2)
    def alert_stats(self):
        self._get("/api/alerts/stats", "/alerts/stats")

    @task(2)
    def active_alerts(self):
        self._get("/api/alerts/active?limit=50", "/alerts/active (manager)")

    @task(1)
    def workers_list(self):
        self._get("/api/workers?page=1&limit=20", "/workers (list)")
