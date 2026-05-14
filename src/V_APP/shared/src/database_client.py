"""HTTP client for the V_APP scheduling REST API.

This module provides ``DatabaseClient``, a thin wrapper around the
``requests`` library that queries the appointment-management backend.
All network errors are caught internally and surfaced as structured
error payloads so callers can apply consistent fallback logic without
duplicating exception handling.

Typical usage:
    client = DatabaseClient(api_url="http://api-gateway:8080/api/v1", gate_id="1")
    result = client.get_appointments()
"""

import logging
import requests


logger = logging.getLogger("DatabaseClient")


class DatabaseClient:
    """HTTP client for querying scheduled truck appointments from the API.

    Wraps the ``/decisions/query-appointments`` endpoint of the scheduling
    REST API. Responses are returned as plain dicts; callers are responsible
    for interpreting the ``found``, ``candidates``, and ``message`` keys.

    All ``requests`` exceptions are caught and converted to a structured
    error dict so that the caller always receives a consistent return type.
    """

    def __init__(self, api_url: str, gate_id: str = "") -> None:
        """Initialise the client with the API base URL and gate identifier.

        Args:
            api_url: Base URL of the scheduling REST API, without a trailing
                slash (e.g. ``"http://api-gateway:8080/api/v1"``).
            gate_id: Logical identifier of the gate this client serves. Sent
                as a payload field in every appointment query. When empty,
                appointments for all gates are returned.
        """
        self.api_url = api_url
        self.gate_id = gate_id

    def get_appointments(self) -> dict:
        """Query the API for all appointment candidates in the current time window.

        Issues a POST request to ``{api_url}/decisions/query-appointments`` with
        the configured ``gate_id``. The API is expected to return a JSON body
        with at least the keys ``found`` (bool) and ``candidates`` (list).

        On non-200 responses or network-level failures the exception is caught
        and a normalised error dict is returned so callers can apply the same
        fallback logic in all failure paths.

        Returns:
            On success: the parsed JSON response body as a ``dict``.
            On API error (non-200 status): ``{"found": False, "candidates": [],
                "message": "API Error"}``.
            On network failure: ``{"found": False, "candidates": [],
                "message": "<exception message>"}``.
        """
        url = f"{self.api_url}/decisions/query-appointments"
        payload: dict = {}
        if self.gate_id:
            payload["gate_id"] = self.gate_id
        try:
            response = requests.post(url, json=payload, timeout=5)
            if response.status_code == 200:
                return response.json()
            else:
                logger.error(f"API Error {response.status_code}: {response.text}")
                # Normalise non-200 responses to the standard error shape so
                # callers do not need to inspect the status code.
                return {"found": False, "candidates": [], "message": "API Error"}

        except Exception as e:
            logger.error(f"API Request failed: {e}")
            # Surface the exception message in the payload so is_api_unavailable()
            # can pattern-match on well-known connection-failure strings.
            return {"found": False, "candidates": [], "message": str(e)}

    def is_api_unavailable(self, api_message: str) -> bool:
        """Determine whether an error message indicates a connectivity failure.

        Inspects the ``message`` field of a failed ``get_appointments()``
        response to distinguish between a reachable API returning an error
        versus the API being entirely unreachable.

        Args:
            api_message: The ``message`` value from a ``get_appointments()``
                error payload (e.g. the stringified exception message).

        Returns:
            ``True`` if the message contains a known connectivity-failure
            substring (``"Connection refused"`` or ``"Max retries"``),
            indicating the API host is down or unreachable. ``False`` otherwise.
        """
        return "Connection refused" in api_message or "Max retries" in api_message