"""Pytest configuration for AI_APP integration suites."""


def pytest_addoption(parser):
    """CLI options used by model integration tests."""
    parser.addoption(
        "--plate-type",
        default="license_plate",
        choices=["license_plate", "hazard_plate"],
        help="Expected classification for all crops in the directory",
    )
    parser.addoption(
        "--crops-dir",
        default=None,
        help="Path to crops directory (default: src/AI_APP/crops/)",
    )