"""MLflow experiment tracking helpers (optional if mlflow unavailable)."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

from app.core.config import get_settings

logger = logging.getLogger(__name__)


def log_training_run(metrics: list[dict], params: dict[str, Any] | None = None) -> str | None:
    settings = get_settings()
    try:
        import mlflow
    except ImportError:
        logger.warning("mlflow not installed; skipping tracking")
        return None

    try:
        # Prefer sqlite backend (file store is maintenance-mode in newer MLflow)
        uri = settings.mlflow_tracking_uri
        if uri.startswith("./") or uri.startswith(".\\") or (not uri.startswith("sqlite") and "://" not in uri):
            root = Path(uri)
            root.mkdir(parents=True, exist_ok=True)
            uri = f"sqlite:///{(root / 'mlflow.db').resolve().as_posix()}"
        os.environ.setdefault("MLFLOW_ALLOW_FILE_STORE", "true")
        mlflow.set_tracking_uri(uri)
        mlflow.set_experiment(settings.mlflow_experiment)
        with mlflow.start_run(run_name="forecast_suite_train") as run:
            if params:
                mlflow.log_params({k: str(v)[:250] for k, v in params.items()})
            for m in metrics:
                prefix = f"h{m['horizon']}_" if m.get("horizon") is not None else f"{m['model_type']}_"
                mlflow.log_metric(f"{prefix}mae", m["mae"])
                mlflow.log_metric(f"{prefix}rmse", m["rmse"])
                mlflow.log_metric(f"{prefix}r2", m["r2"])
                if "directional_acc" in (m.get("extras") or {}):
                    mlflow.log_metric(f"{prefix}dir_acc", m["extras"]["directional_acc"])
            return run.info.run_id
    except Exception as exc:  # noqa: BLE001
        logger.warning("MLflow logging skipped: %s", exc)
        return None
