"""
Test Step 1 — Verify the 4 manager statistics endpoints exist
and match the frontend contract (statistics.ts).

Uses source-code inspection to avoid needing fastapi/psycopg2 in the test venv.

Checks:
1. statistics.py imports the 4 manager statistics query functions.
2. statistics.py defines routes for /summary, /by-company, /volume, /alerts.
3. manager_statistics_queries.py defines the 4 required functions.
4. get_dashboard_summary returns keys matching the frontend DashboardSummary type.
"""

import pytest
from pathlib import Path

ROUTES_DIR = Path(__file__).parent.parent / "routes"
QUERIES_DIR = Path(__file__).parent.parent / "application" / "queries"


def _read(path: Path) -> str:
    return path.read_text()


@pytest.mark.unit
class TestManagerStatisticsRoutesRegistered:
    """statistics.py must define the 4 routes the frontend expects."""

    def test_summary_route_exists(self):
        source = _read(ROUTES_DIR / "statistics.py")
        assert '"/summary"' in source or "'/summary'" in source, (
            "GET /statistics/summary must exist for the manager dashboard."
        )

    def test_by_company_route_exists(self):
        source = _read(ROUTES_DIR / "statistics.py")
        assert '"/by-company"' in source or "'/by-company'" in source, (
            "GET /statistics/by-company must exist for company metrics."
        )

    def test_volume_route_exists(self):
        source = _read(ROUTES_DIR / "statistics.py")
        assert '"/volume"' in source or "'/volume'" in source, (
            "GET /statistics/volume must exist for volume time series."
        )

    def test_alerts_route_exists(self):
        source = _read(ROUTES_DIR / "statistics.py")
        assert '"/alerts"' in source or "'/alerts'" in source, (
            "GET /statistics/alerts must exist for alerts breakdown."
        )


@pytest.mark.unit
class TestManagerStatisticsQueriesExist:
    """manager_statistics_queries.py must define the 4 required functions."""

    def test_get_dashboard_summary_defined(self):
        source = _read(QUERIES_DIR / "manager_statistics_queries.py")
        assert "def get_dashboard_summary(" in source

    def test_get_transport_stats_defined(self):
        source = _read(QUERIES_DIR / "manager_statistics_queries.py")
        assert "def get_transport_stats(" in source

    def test_get_volume_data_defined(self):
        source = _read(QUERIES_DIR / "manager_statistics_queries.py")
        assert "def get_volume_data(" in source

    def test_get_alerts_breakdown_defined(self):
        source = _read(QUERIES_DIR / "manager_statistics_queries.py")
        assert "def get_alerts_breakdown(" in source


@pytest.mark.unit
class TestManagerStatisticsImportsWired:
    """statistics.py must import from manager_statistics_queries."""

    def test_imports_manager_statistics_queries(self):
        source = _read(ROUTES_DIR / "statistics.py")
        assert "from application.queries.manager_statistics_queries import" in source

    def test_imports_all_functions(self):
        source = _read(ROUTES_DIR / "statistics.py")
        for fn in [
            "get_dashboard_summary",
            "get_transport_stats",
            "get_volume_data",
            "get_alerts_breakdown",
            "get_decision_analytics",
        ]:
            assert fn in source, f"statistics.py must import {fn}"


@pytest.mark.unit
class TestManagerStatisticsResponseContract:
    """manager_statistics_queries must return keys matching the frontend types."""

    def test_summary_returns_camelcase_keys(self):
        """get_dashboard_summary must return camelCase keys matching statistics.ts."""
        source = _read(QUERIES_DIR / "manager_statistics_queries.py")
        for key in [
            "trucksInPort",
            "trucksInTransit",
            "scheduledCount",
            "unloadingCount",
            "completedCount",
            "entriesCount",
            "exitsCount",
            "avgPermanenceMinutes",
            "avgWaitingMinutes",
            "delayRate",
            "slaCompliance",
            "infractionCount",
            "peakHour",
            "portCapacity",
            "congestionRate",
            "vehiclesPerHour",
        ]:
            assert f'"{key}"' in source, (
                f'manager_statistics_queries must return "{key}" (camelCase) to match '
                f"the frontend DashboardSummary interface."
            )

    def test_transport_stats_returns_correct_keys(self):
        """get_transport_stats must return keys matching TransportStats."""
        source = _read(QUERIES_DIR / "manager_statistics_queries.py")
        for key in [
            "companyName",
            "companyNif",
            "avgUnloadingTime",
            "avgWaitingTime",
            "operationsCount",
            "slaAttendedRate",
        ]:
            assert f'"{key}"' in source, (
                f'manager_statistics_queries must return "{key}" to match '
                f"the frontend TransportStats interface."
            )

    def test_volume_returns_correct_keys(self):
        """get_volume_data must return keys matching VolumeDataPoint."""
        source = _read(QUERIES_DIR / "manager_statistics_queries.py")
        for key in ["timestamp", "entries", "exits"]:
            assert f'"{key}"' in source, (
                f'manager_statistics_queries must return "{key}" to match '
                f"the frontend VolumeDataPoint interface."
            )

    def test_alerts_returns_correct_keys(self):
        """get_alerts_breakdown must return keys matching AlertsBreakdown."""
        source = _read(QUERIES_DIR / "manager_statistics_queries.py")
        for key in ["type", "count", "percentage"]:
            assert f'"{key}"' in source, (
                f'manager_statistics_queries must return "{key}" to match '
                f"the frontend AlertsBreakdown interface."
            )

    def test_decision_analytics_returns_correct_keys(self):
        """get_decision_analytics must return keys matching DecisionAnalytics."""
        source = _read(QUERIES_DIR / "manager_statistics_queries.py")
        for key in [
            "totalDecisions",
            "accepted",
            "rejected",
            "manualReview",
            "acceptanceRate",
            "avgPipelineMs",
            "avgDetectionToDecisionMs",
        ]:
            assert f'"{key}"' in source, (
                f'manager_statistics_queries must return "{key}" to match '
                f"the frontend DecisionAnalytics interface."
            )


@pytest.mark.unit
class TestDecisionAnalyticsRouteRegistered:
    """statistics.py must define the decision-analytics route."""

    def test_decision_analytics_route_exists(self):
        source = _read(ROUTES_DIR / "statistics.py")
        assert '"/decision-analytics"' in source or "'/decision-analytics'" in source, (
            "GET /statistics/decision-analytics must exist for decision event analytics."
        )

    def test_get_decision_analytics_defined(self):
        source = _read(QUERIES_DIR / "manager_statistics_queries.py")
        assert "def get_decision_analytics(" in source
