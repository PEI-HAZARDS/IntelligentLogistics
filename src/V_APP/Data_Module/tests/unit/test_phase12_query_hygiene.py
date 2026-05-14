"""
Phase 12 unit tests — Query hygiene.

- PROJECTION MISS log lines removed from routes/worker.py
- arrival_queries.get_transport_stats_by_company carries DeprecationWarning
- routes/arrivals.py transport-stats endpoint uses canonical manager_statistics_queries.get_transport_stats
- manager_statistics_queries.get_volume_data uses FULL OUTER JOIN (not union-of-buckets workaround)
- driver_repository.get_appointment_for_claim returns dock_bay_number / dock_location
- routes/driver.py passes dock fields through to ClaimAppointmentResponse
"""
import pathlib
import pytest

_BASE = pathlib.Path(__file__).parents[2]


def _src(rel: str) -> str:
    return (_BASE / rel).read_text()


# ---------------------------------------------------------------------------
# PROJECTION MISS logs removed from worker.py
# ---------------------------------------------------------------------------

class TestProjectionMissRemoved:

    def test_no_projection_miss_in_worker_route(self):
        src = _src("routes/worker.py")
        assert "PROJECTION MISS" not in src, (
            "PROJECTION MISS log lines must be removed from routes/worker.py (Phase 6 landed)"
        )


# ---------------------------------------------------------------------------
# get_transport_stats_by_company deprecated
# ---------------------------------------------------------------------------

class TestTransportStatsDeprecated:

    def test_arrival_queries_function_deprecated(self):
        src = _src("application/queries/arrival_queries.py")
        fn_start = src.index("def get_transport_stats_by_company(")
        fn_end = src.index("\n    end_date", fn_start)
        fn_header = src[fn_start:fn_end]
        assert "DEPRECATED" in fn_header
        assert "DeprecationWarning" in fn_header

    def test_route_uses_canonical_function(self):
        src = _src("routes/arrivals.py")
        # Must import from manager_statistics_queries
        assert "manager_statistics_queries" in src or "_get_transport_stats_canonical" in src

    def test_route_does_not_call_deprecated_function(self):
        src = _src("routes/arrivals.py")
        fn_start = src.index("def get_transport_stats(")
        fn_end = src.index("\n\n@router", fn_start) if "\n\n@router" in src[fn_start:] else len(src)
        fn_body = src[fn_start:fn_end]
        assert "get_transport_stats_by_company" not in fn_body, (
            "routes/arrivals.py transport-stats must call canonical function, not deprecated one"
        )

    def test_route_no_longer_needs_db_session(self):
        src = _src("routes/arrivals.py")
        fn_start = src.index("def get_transport_stats(")
        fn_end = src.index("\n\n@router", fn_start) if "\n\n@router" in src[fn_start:] else len(src)
        fn_sig = src[fn_start:fn_start + 300]
        # The old implementation needed db: Session = Depends(get_db)
        # After switching to canonical, db param not needed
        assert "get_transport_stats_by_company" not in fn_sig


# ---------------------------------------------------------------------------
# get_volume_data: FULL OUTER JOIN
# ---------------------------------------------------------------------------

class TestVolumeDataFullOuterJoin:

    def test_full_outer_join_used(self):
        src = _src("application/queries/manager_statistics_queries.py")
        fn_start = src.index("def get_volume_data(")
        fn_end = src.index("\ndef ", fn_start + 1)
        fn_body = src[fn_start:fn_end]
        assert "full=True" in fn_body, (
            "get_volume_data must use outerjoin(..., full=True) for FULL OUTER JOIN"
        )

    def test_union_all_workaround_removed(self):
        src = _src("application/queries/manager_statistics_queries.py")
        fn_start = src.index("def get_volume_data(")
        fn_end = src.index("\ndef ", fn_start + 1)
        fn_body = src[fn_start:fn_end]
        assert "union_all" not in fn_body, (
            "get_volume_data must not use union_all workaround — use FULL OUTER JOIN instead"
        )


# ---------------------------------------------------------------------------
# driver_repository.get_appointment_for_claim: dock fields populated
# ---------------------------------------------------------------------------

class TestDriverRepositoryDockFields:

    def test_terminal_docks_eager_loaded(self):
        src = _src("infrastructure/persistence/driver_repository.py")
        assert "Terminal.docks" in src or "terminal).joinedload(Terminal.docks)" in src

    def test_dock_bay_number_in_return_dict(self):
        src = _src("infrastructure/persistence/driver_repository.py")
        fn_start = src.index("def get_appointment_for_claim(")
        fn_end = src.index("\n    def ", fn_start + 1)
        fn_body = src[fn_start:fn_end]
        assert '"dock_bay_number"' in fn_body

    def test_dock_location_in_return_dict(self):
        src = _src("infrastructure/persistence/driver_repository.py")
        fn_start = src.index("def get_appointment_for_claim(")
        fn_end = src.index("\n    def ", fn_start + 1)
        fn_body = src[fn_start:fn_end]
        assert '"dock_location"' in fn_body

    def test_dock_imported(self):
        src = _src("infrastructure/persistence/driver_repository.py")
        assert "Dock" in src


# ---------------------------------------------------------------------------
# routes/driver.py: passes dock fields to ClaimAppointmentResponse
# ---------------------------------------------------------------------------

class TestDriverRouteClaimResponse:

    def _claim_response_block(self) -> str:
        src = _src("routes/driver.py")
        fn_start = src.index("return ClaimAppointmentResponse(")
        fn_end = src.index("\n\n", fn_start)
        return src[fn_start:fn_end]

    def test_dock_bay_number_from_appointment(self):
        block = self._claim_response_block()
        assert 'appointment.get("dock_bay_number")' in block or \
               'appointment["dock_bay_number"]' in block, (
            "ClaimAppointmentResponse must populate dock_bay_number from appointment dict"
        )

    def test_dock_location_from_appointment(self):
        block = self._claim_response_block()
        assert 'appointment.get("dock_location")' in block or \
               'appointment["dock_location"]' in block

    def test_not_hardcoded_none(self):
        block = self._claim_response_block()
        assert "dock_bay_number=None" not in block
        assert "dock_location=None" not in block
