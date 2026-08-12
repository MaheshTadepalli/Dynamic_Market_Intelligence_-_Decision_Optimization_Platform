"""Forecast uncertainty evaluation: errors, calibration, intervals."""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score


def evaluate_predictions(
    y_true: np.ndarray | pd.Series,
    y_pred: np.ndarray | pd.Series,
    *,
    y_vol_true: np.ndarray | pd.Series | None = None,
    y_vol_pred: np.ndarray | pd.Series | None = None,
    residual_std: float | None = None,
) -> dict:
    yt = np.asarray(y_true, dtype=float)
    yp = np.asarray(y_pred, dtype=float)
    mask = np.isfinite(yt) & np.isfinite(yp)
    yt, yp = yt[mask], yp[mask]
    if len(yt) < 10:
        return {"n": int(len(yt)), "ok": False}

    resid = yt - yp
    mae = float(mean_absolute_error(yt, yp))
    rmse = float(np.sqrt(mean_squared_error(yt, yp)))
    r2 = float(r2_score(yt, yp))
    dir_acc = float(((yp > 0) == (yt > 0)).mean())

    # Prediction intervals from residual std (Gaussian approx on holdout residuals)
    sigma = float(residual_std) if residual_std is not None else float(resid.std(ddof=1))
    z80, z95 = 1.2816, 1.95996
    cover80 = float((np.abs(resid) <= z80 * sigma).mean()) if sigma > 0 else 0.0
    cover95 = float((np.abs(resid) <= z95 * sigma).mean()) if sigma > 0 else 0.0

    # Calibration: reliability of P(up) if we treat sigmoid of standardized pred as prob
    # Simpler: decile calibration of predicted return sign strength
    calibration = _calibration_table(yt, yp, n_bins=5)

    out: dict = {
        "ok": True,
        "n": int(len(yt)),
        "mae": round(mae, 6),
        "rmse": round(rmse, 6),
        "r2": round(r2, 4),
        "directional_accuracy": round(dir_acc, 4),
        "residual_std": round(sigma, 6),
        "prediction_intervals": {
            "method": "gaussian_residual",
            "sigma": round(sigma, 6),
            "cover_80": round(cover80, 4),
            "cover_95": round(cover95, 4),
            "target_80": 0.80,
            "target_95": 0.95,
            "well_calibrated_80": abs(cover80 - 0.80) < 0.10,
            "well_calibrated_95": abs(cover95 - 0.95) < 0.10,
        },
        "calibration_bins": calibration,
    }

    if y_vol_true is not None and y_vol_pred is not None:
        vt = np.asarray(y_vol_true, dtype=float)
        vp = np.asarray(y_vol_pred, dtype=float)
        vm = np.isfinite(vt) & np.isfinite(vp)
        if vm.sum() >= 10:
            out["volatility_forecast"] = {
                "mae": round(float(mean_absolute_error(vt[vm], vp[vm])), 6),
                "rmse": round(float(np.sqrt(mean_squared_error(vt[vm], vp[vm]))), 6),
                "r2": round(float(r2_score(vt[vm], vp[vm])), 4),
                "n": int(vm.sum()),
            }
    return out


def _calibration_table(y_true: np.ndarray, y_pred: np.ndarray, n_bins: int = 5) -> list[dict]:
    """Bin by predicted return; report mean predicted vs mean realized."""
    if len(y_true) < n_bins * 5:
        return []
    qs = np.linspace(0, 1, n_bins + 1)
    edges = np.quantile(y_pred, qs)
    edges[0] -= 1e-12
    edges[-1] += 1e-12
    rows = []
    for i in range(n_bins):
        m = (y_pred >= edges[i]) & (y_pred < edges[i + 1])
        if not m.any():
            continue
        rows.append(
            {
                "bin": i + 1,
                "n": int(m.sum()),
                "mean_predicted": round(float(y_pred[m].mean()), 6),
                "mean_realized": round(float(y_true[m].mean()), 6),
                "frac_positive_pred": round(float((y_pred[m] > 0).mean()), 4),
                "frac_positive_real": round(float((y_true[m] > 0).mean()), 4),
            }
        )
    return rows
