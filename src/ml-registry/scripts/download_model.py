import os
import glob
import mlflow
import mlflow.artifacts
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings


# --- Config ---

class MLflowSettings(BaseSettings):
    tracking_uri: str = Field(default="http://localhost:5000", alias="MLFLOW_TRACKING_URI")
    s3_endpoint_url: str = Field(default="http://localhost:9000", alias="MLFLOW_S3_ENDPOINT_URL")
    aws_access_key_id: str = Field(default="minioadmin", alias="AWS_ACCESS_KEY_ID")
    aws_secret_access_key: str = Field(default="change_me_minio", alias="AWS_SECRET_ACCESS_KEY")
    model_cache_dir: str = Field(default="/tmp/model_cache", alias="MODEL_CACHE_DIR")

    model_config = {"populate_by_name": True}


class ModelRequest(BaseModel):
    model_name: str
    alias: str = "champion"


# --- Setup ---

settings = MLflowSettings()

mlflow.set_tracking_uri(settings.tracking_uri)
os.environ["MLFLOW_S3_ENDPOINT_URL"] = settings.s3_endpoint_url
os.environ["AWS_ACCESS_KEY_ID"] = settings.aws_access_key_id
os.environ["AWS_SECRET_ACCESS_KEY"] = settings.aws_secret_access_key


# --- Helpers ---

def _find_pt_file(directory: str) -> str:
    """Recursively find the first .pt file inside a directory."""
    matches = glob.glob(os.path.join(directory, "**", "*.pt"), recursive=True)
    if not matches:
        raise FileNotFoundError(
            f"No .pt file found inside the downloaded artifact directory: {directory}"
        )
    return matches[0]


# --- Loader ---

def load_model(request: ModelRequest) -> str:
    """
    Downloads the model artifact from the MLflow registry (if not cached) and
    returns the local file-system path to the .pt weights file.

    The upload script registers raw .pt files with a source URI that points
    directly to the file (not a directory). Using models:/name@alias with
    download_artifacts tries to list that source as a directory and finds
    nothing. Instead, we resolve the alias via MlflowClient to get the exact
    source URI and download that directly.

    Args:
        request: ModelRequest specifying the registry name and alias.

    Returns:
        Absolute path to the downloaded .pt file.
    """
    from mlflow import MlflowClient

    cache_path = os.path.join(settings.model_cache_dir, request.model_name, request.alias)

    if os.path.exists(cache_path):
        try:
            pt_path = _find_pt_file(cache_path)
            print(f"[{request.model_name}] Cache hit — {pt_path}")
            return pt_path
        except FileNotFoundError:
            print(f"[{request.model_name}] Cache dir exists but no .pt found — re-downloading...")

    print(f"[{request.model_name}] Downloading from MLflow registry (alias={request.alias})...")
    os.makedirs(cache_path, exist_ok=True)

    # Resolve alias → model version → source URI (the exact artifact path)
    client = MlflowClient()
    version = client.get_model_version_by_alias(request.model_name, request.alias)
    source_uri = version.source
    print(f"[{request.model_name}] Resolved source URI: {source_uri}")

    # Download the artifact directly using the resolved runs: URI
    mlflow.artifacts.download_artifacts(artifact_uri=source_uri, dst_path=cache_path)

    pt_path = _find_pt_file(cache_path)
    print(f"[{request.model_name}] Downloaded to: {pt_path}")
    return pt_path