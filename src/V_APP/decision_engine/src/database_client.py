import logging
import os
import requests

logger = logging.getLogger("DatabaseClient")

class DatabaseClient:
    def __init__(self, api_url : str, gate_id) -> None:
        self.api_url = api_url
        self.gate_id = gate_id
    
    def get_appointments(self) -> dict:
        """Query Appointments API to get all candidates in time frame."""
        url = f"{self.api_url}/decisions/query-appointments"
        payload = {
            "time_frame": 24,
            "gate_id": self.gate_id
        }
        try:
            response = requests.post(url, json=payload, timeout=5)
            if response.status_code == 200:
                return response.json()
            else:
                logger.error(f"API Error {response.status_code}: {response.text}")
                return {"found": False, "candidates": [], "message": "API Error"}
            
        except Exception as e:
            logger.error(f"API Request failed: {e}")
            return {"found": False, "candidates": [], "message": str(e)}
        
    
    def update_appointment_status(self, appointment_id: int, decision: str):
        """Updates the appointment status via the Data Module API."""
        # Map decision to status (same as manual review)
        if decision == "ACCEPTED":
            new_status = "in_process"  # Truck at gate, being processed
        elif decision == "REJECTED":
            new_status = "canceled"
        else:
            return  # Don't update for MANUAL_REVIEW
        
        url = f"{self.api_url}/arrivals/{appointment_id}/status"
        payload = {
            "status": new_status,
            "notes": f"[Decision Engine] Auto-{decision.lower()}"
        }
        
        try:
            response = requests.patch(url, json=payload, timeout=5)
            if response.status_code == 200:
                logger.info(f"Updated appointment {appointment_id} status to '{new_status}'")
            else:
                logger.warning(f"Failed to update appointment status: {response.status_code} - {response.text}")
        
        except Exception as e:
            logger.error(f"Error updating appointment status: {e}")
    
    def is_api_unavailable(self, api_message: str) -> bool:
        """Checks if the API is unavailable based on the response message."""
        return "Connection refused" in api_message or "Max retries" in api_message
    