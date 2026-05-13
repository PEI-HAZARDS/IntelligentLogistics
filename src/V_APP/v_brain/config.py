import json
import logging
from pydantic_settings import BaseSettings  # type: ignore
from pydantic import Field, field_validator  # type: ignore

logger = logging.getLogger("VBrain")


class VBrainConfig(BaseSettings):
    """Configuration for V_Brain, loaded from environment variables.

    V_Brain is gate-agnostic: a single instance handles ALL gates.
    GATE_IDS is a JSON array string, e.g. '["1","2","3"]'.
    """
    kafka_bootstrap: str = Field(default="localhost:9092")
    gate_ids: str = Field(default='["1"]')

    # Timeout for scale correlator — how long to wait for LP + HZ results
    # before forcing scale-down + reset
    correlator_timeout_seconds: int = Field(default=30)

    # Scaling API configuration (Tiago's slice scaling service)
    scaling_api_url: str = Field(default="http://localhost:8008")
    scaling_notification_destination: str = Field(default="https://one.one.one.one/")
    scaling_slice_id: str = Field(default="Nexus")
    scaling_request_id: str = Field(default="123456")

    @field_validator("gate_ids", mode="before")
    @classmethod
    def _parse_gate_ids(cls, v: str) -> str:
        """Validate that gate_ids is a valid JSON array string."""
        try:
            parsed = json.loads(v) if isinstance(v, str) else v
            if not isinstance(parsed, list) or len(parsed) == 0:
                raise ValueError("GATE_IDS must be a non-empty JSON array")
        except json.JSONDecodeError:
            raise ValueError(f"GATE_IDS is not valid JSON: {v}")
        return v

    @property
    def gate_id_list(self) -> list[str]:
        """Return gate IDs as a Python list of strings."""
        return [str(gid) for gid in json.loads(self.gate_ids)]

    class Config:
        env_prefix = ""
