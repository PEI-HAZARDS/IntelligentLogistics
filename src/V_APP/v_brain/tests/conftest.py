"""
Shared fixtures for V_Brain unit tests.

Auto-patches `requests.post` because `_scale_up_try` / `_scale_down_try`
call `_call_scaling_api`, which would otherwise hit a real network. Tests
that want to inspect the scaling-API call should patch
`V_APP.v_brain.src.v_brain.requests.post` themselves to override this.
"""

from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture(autouse=True)
def _stub_scaling_http():
    """Prevent any real HTTP call from `_call_scaling_api` during unit tests."""
    response = MagicMock()
    response.status_code = 200
    response.text = "ok"
    with patch("V_APP.v_brain.src.v_brain.requests.post", return_value=response) as mock_post:
        yield mock_post
