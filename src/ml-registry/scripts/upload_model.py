#!/usr/bin/env python3
"""
MLflow Model Upload Script
---------------------------
Interactive CLI script to upload ML models to the MLflow registry.
Run from the project root:
    python scripts/upload_model.py
"""

import os
import sys
import mlflow
import mlflow.pytorch
import mlflow.sklearn
import mlflow.xgboost
import mlflow.pyfunc
from mlflow import MlflowClient
from pydantic import BaseModel, Field, field_validator
from pydantic_settings import BaseSettings
from dotenv import load_dotenv

load_dotenv(".env.upload")


# ---------------------------------------------------------------------------
# Settings — reads from env vars, falls back to prompting the user
# ---------------------------------------------------------------------------

class MLflowSettings(BaseSettings):
    tracking_uri: str = Field(default="http://localhost:5000", alias="MLFLOW_TRACKING_URI")
    s3_endpoint_url: str = Field(default="http://localhost:9000", alias="MLFLOW_S3_ENDPOINT_URL")
    aws_access_key_id: str = Field(default="", alias="AWS_ACCESS_KEY_ID")
    aws_secret_access_key: str = Field(default="", alias="AWS_SECRET_ACCESS_KEY")

    model_config = {"populate_by_name": True}


class UploadRequest(BaseModel):
    model_path: str
    registry_name: str
    framework: str
    alias: str = "champion"
    description: str = ""
    version_description: str = ""
    tags: dict[str, str] = {}
    metrics: dict[str, float] = {}

    @field_validator("model_path")
    @classmethod
    def path_must_exist(cls, v: str) -> str:
        if not os.path.exists(v):
            raise ValueError(f"Model path does not exist: {v}")
        return v

    @field_validator("framework")
    @classmethod
    def framework_must_be_valid(cls, v: str) -> str:
        valid = ["pytorch", "sklearn", "xgboost", "pyfunc", "artifact"]
        if v.lower() not in valid:
            raise ValueError(f"Framework must be one of: {', '.join(valid)}")
        return v.lower()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

FRAMEWORKS = {
    "1": "pytorch",
    "2": "sklearn",
    "3": "xgboost",
    "4": "pyfunc",
    "5": "artifact",
}

FRAMEWORK_LABELS = {
    "1": "PyTorch              — standard .pt model loaded via torch",
    "2": "scikit-learn         — .pkl model loaded via joblib",
    "3": "XGBoost              — .json/.ubj model loaded via xgboost",
    "4": "pyfunc               — generic MLflow model directory",
    "5": "Raw artifact         — upload file as-is (YOLO, custom, etc.)",
}

SEPARATOR = "─" * 60


def prompt(label: str, default: str = "") -> str:
    if default:
        value = input(f"  {label} [{default}]: ").strip()
        return value if value else default
    else:
        while True:
            value = input(f"  {label}: ").strip()
            if value:
                return value
            print("  ✗ This field is required.")


def prompt_optional(label: str) -> str:
    return input(f"  {label} (optional, Enter to skip): ").strip()


def parse_tags(raw: str) -> dict[str, str]:
    """Parse a comma-separated key=value string into a dict.
    e.g. "type=yolo,task=detection" -> {"type": "yolo", "task": "detection"}
    """
    tags = {}
    if not raw:
        return tags
    for pair in raw.split(","):
        pair = pair.strip()
        if "=" in pair:
            key, _, value = pair.partition("=")
            tags[key.strip()] = value.strip()
        elif pair:
            tags[pair] = "true"
    return tags


def parse_metrics(raw: str) -> dict[str, float]:
    """Parse a comma-separated key=value string into a dict of floats.
    e.g. "mAP=0.91,precision=0.88" -> {"mAP": 0.91, "precision": 0.88}
    """
    metrics = {}
    if not raw:
        return metrics
    for pair in raw.split(","):
        pair = pair.strip()
        if "=" in pair:
            key, _, value = pair.partition("=")
            try:
                metrics[key.strip()] = float(value.strip())
            except ValueError:
                print(f"  ✗ Skipping non-numeric metric: {key.strip()}={value.strip()}")
    return metrics

def print_header():
    print()
    print(SEPARATOR)
    print("  MLflow Model Upload")
    print(SEPARATOR)


def print_section(title: str):
    print()
    print(f"  ── {title}")


def list_registries(client: MlflowClient) -> list[str]:
    return [m.name for m in client.search_registered_models()]


def select_registry(client: MlflowClient) -> tuple[str, bool]:
    """
    Shows existing registries. User can:
      - Enter a number to select an existing one
      - Press Enter to create a new one
      - Type a name directly to select or create
    Returns (registry_name, is_new).
    """
    existing = list_registries(client)

    print_section("Model Registry")

    if existing:
        print("\n  Existing registries (enter number to select, Enter to create new):\n")
        for i, name in enumerate(existing, 1):
            print(f"    {i}. {name}")
        print()
    else:
        print("\n  No registries found. You will create a new one.\n")

    raw = input("  Selection: ").strip()

    # Enter with no input → create new
    if not raw:
        name = prompt("New registry name")
        return name, True

    # Number input → pick from list
    if raw.isdigit():
        idx = int(raw) - 1
        if 0 <= idx < len(existing):
            selected = existing[idx]
            print(f"  ✓ Selected: '{selected}'")
            return selected, False
        else:
            print(f"  ✗ Invalid number, treating as registry name.")

    # Text input → existing or new
    if raw in existing:
        print(f"  ✓ Using existing registry '{raw}'.")
        return raw, False
    else:
        print(f"  Registry '{raw}' does not exist.")
        create = prompt("Create it? (y/n)", default="y").lower()
        if create != "y":
            print("  Aborted.")
            sys.exit(0)
        return raw, True


def ensure_registry(client: MlflowClient, name: str, description: str = ""):
    client.create_registered_model(name=name, description=description)
    print(f"  ✓ Registry '{name}' created.")


def load_and_log_model(framework: str, model_path: str, artifact_path: str, registered_name: str):
    """Loads and logs the model. For artifact type, skips loading entirely."""

    if framework == "artifact":
        # Raw file upload — no loading, no framework wrapping
        print(f"  Uploading raw artifact: {model_path}")
        artifact_file = os.path.basename(model_path)
        mlflow.log_artifact(model_path, artifact_path=artifact_path)
        run_id = mlflow.active_run().info.run_id
        artifact_uri = f"runs:/{run_id}/{artifact_path}/{artifact_file}"
        client = MlflowClient()
        client.create_model_version(
            name=registered_name,
            source=artifact_uri,
            run_id=run_id,
        )

    elif framework == "pytorch":
        import torch
        print(f"  Loading PyTorch model from: {model_path}")
        model = torch.load(model_path, map_location="cpu", weights_only=False)
        mlflow.pytorch.log_model(
            pytorch_model=model,
            artifact_path=artifact_path,
            registered_model_name=registered_name,
        )

    elif framework == "sklearn":
        import joblib
        print(f"  Loading scikit-learn model from: {model_path}")
        model = joblib.load(model_path)
        mlflow.sklearn.log_model(
            sk_model=model,
            artifact_path=artifact_path,
            registered_model_name=registered_name,
        )

    elif framework == "xgboost":
        import xgboost as xgb
        print(f"  Loading XGBoost model from: {model_path}")
        booster = xgb.Booster()
        booster.load_model(model_path)
        mlflow.xgboost.log_model(
            xgb_model=booster,
            artifact_path=artifact_path,
            registered_model_name=registered_name,
        )

    elif framework == "pyfunc":
        print(f"  Logging pyfunc model from: {model_path}")
        mlflow.pyfunc.log_model(
            artifact_path=artifact_path,
            data_path=model_path,
            registered_model_name=registered_name,
        )


def get_latest_version(client: MlflowClient, registry_name: str) -> str:
    versions = client.search_model_versions(f"name='{registry_name}'")
    if not versions:
        return "1"
    return str(max(int(v.version) for v in versions))


# ---------------------------------------------------------------------------
# Main interactive flow
# ---------------------------------------------------------------------------

def main():
    print_header()

    # --- Connection ---
    settings = MLflowSettings()

    print_section("MLflow Connection")
    print(f"  Tracking URI : {settings.tracking_uri}")
    print(f"  MinIO URL    : {settings.s3_endpoint_url}")

    if not settings.aws_access_key_id:
        print()
        print("  ✗ AWS credentials not found in environment.")
        settings.aws_access_key_id = prompt("MinIO Access Key (AWS_ACCESS_KEY_ID)")
        settings.aws_secret_access_key = prompt("MinIO Secret Key (AWS_SECRET_ACCESS_KEY)")

    os.environ["MLFLOW_S3_ENDPOINT_URL"] = settings.s3_endpoint_url
    os.environ["AWS_ACCESS_KEY_ID"] = settings.aws_access_key_id
    os.environ["AWS_SECRET_ACCESS_KEY"] = settings.aws_secret_access_key
    mlflow.set_tracking_uri(settings.tracking_uri)

    try:
        client = MlflowClient()
        client.search_registered_models()  # connectivity check
        print(f"  ✓ Connected to MLflow.")
    except Exception as e:
        print(f"\n  ✗ Could not connect to MLflow: {e}")
        sys.exit(1)

    # --- Registry ---
    registry_name, is_new = select_registry(client)

    if is_new:
        reg_description = prompt_optional("Registry description")
        ensure_registry(client, registry_name, reg_description)

    # --- Model path ---
    print_section("Model File")
    model_path = prompt("Path to model file")

    # --- Framework ---
    print_section("Framework")
    for key, label in FRAMEWORK_LABELS.items():
        print(f"  {key}. {label}")
    print()
    framework_choice = prompt("Choose framework", default="1")
    framework = FRAMEWORKS.get(framework_choice, "pytorch")
    print(f"  ✓ Using: {framework}")

    # --- Alias & notes ---
    print_section("Alias & Description")
    alias = prompt("Alias for this version", default="champion")
    version_description = prompt_optional("Version description")
    raw_tags = prompt_optional("Tags (e.g. type=yolo,task=detection)")
    tags = parse_tags(raw_tags)
    if tags:
        print(f"  ✓ Tags: {tags}")
    raw_metrics = prompt_optional("Metrics (e.g. mAP=0.91,precision=0.88,recall=0.85)")
    metrics = parse_metrics(raw_metrics)
    if metrics:
        print(f"  ✓ Metrics: {metrics}")

    # --- Validate ---
    print_section("Validating")
    try:
        request = UploadRequest(
            model_path=model_path,
            registry_name=registry_name,
            framework=framework,
            alias=alias,
            version_description=version_description,
            tags=tags,
            metrics=metrics,
        )
        print("  ✓ All inputs valid.")
    except Exception as e:
        print(f"  ✗ Validation error: {e}")
        sys.exit(1)

    # --- Summary ---
    print()
    print(SEPARATOR)
    print("  Summary")
    print(SEPARATOR)
    print(f"  Registry  : {request.registry_name}")
    print(f"  Model     : {request.model_path}")
    print(f"  Framework : {request.framework}")
    print(f"  Alias     : {request.alias}")
    if request.version_description:
        print(f"  Note      : {request.version_description}")
    if request.tags:
        print(f"  Tags      : {', '.join(f'{k}={v}' for k, v in request.tags.items())}")
    if request.metrics:
        print(f"  Metrics   : {', '.join(f'{k}={v}' for k, v in request.metrics.items())}")
    print()

    confirm = prompt("Upload now? (y/n)", default="y").lower()
    if confirm != "y":
        print("  Aborted.")
        sys.exit(0)

    # --- Upload ---
    print_section("Uploading")
    try:
        with mlflow.start_run():
            load_and_log_model(
                framework=request.framework,
                model_path=request.model_path,
                artifact_path="model",
                registered_name=request.registry_name,
            )

            if request.metrics:
                mlflow.log_metrics(request.metrics)

        print("  ✓ Model uploaded to MLflow.")

        latest_version = get_latest_version(client, request.registry_name)

        if request.version_description:
            client.update_model_version(
                name=request.registry_name,
                version=latest_version,
                description=request.version_description,
            )

        client.set_registered_model_alias(
            name=request.registry_name,
            alias=request.alias,
            version=latest_version,
        )
        print(f"  ✓ Alias '{request.alias}' set on version {latest_version}.")

        if request.tags:
            for key, value in request.tags.items():
                client.set_model_version_tag(
                    name=request.registry_name,
                    version=latest_version,
                    key=key,
                    value=value,
                )
            print(f"  ✓ Tags applied: {request.tags}")

        if request.metrics:
            print(f"  ✓ Metrics logged: {request.metrics}")

    except Exception as e:
        print(f"\n  ✗ Upload failed: {e}")
        sys.exit(1)

    # --- Done ---
    print()
    print(SEPARATOR)
    print(f"  ✓ Done! Model available as:")
    print(f"    models:/{request.registry_name}@{request.alias}")
    print(SEPARATOR)
    print()


if __name__ == "__main__":
    main()