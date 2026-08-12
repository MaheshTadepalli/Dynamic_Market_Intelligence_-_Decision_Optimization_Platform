"""Covariance / risk estimation with Ledoit-Wolf shrinkage."""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.covariance import LedoitWolf


def estimate_covariance(returns: pd.DataFrame, annualize: float = 252.0) -> tuple[np.ndarray, list[str]]:
    """returns: date x symbol daily returns."""
    clean = returns.dropna(axis=1, how="all").dropna(how="any")
    if clean.shape[1] < 2 or clean.shape[0] < 40:
        raise ValueError("Insufficient return history for covariance estimation")
    symbols = list(clean.columns)
    lw = LedoitWolf().fit(clean.values)
    cov = lw.covariance_ * annualize
    # PSD safety
    cov = cov + np.eye(len(symbols)) * 1e-8
    return cov, symbols


def blend_predicted_vols(
    cov: np.ndarray,
    symbols: list[str],
    predicted_daily_vol: dict[str, float],
    annualize: float = 252.0,
) -> np.ndarray:
    """Rescale covariance diagonals toward model-predicted vols while keeping correlations."""
    out = cov.copy()
    d = np.sqrt(np.clip(np.diag(out), 1e-12, None))
    corr = out / np.outer(d, d)
    new_vol = []
    for i, s in enumerate(symbols):
        hist = d[i]
        pred = predicted_daily_vol.get(s)
        if pred is None or not np.isfinite(pred):
            new_vol.append(hist)
        else:
            pred_ann = float(pred) * np.sqrt(annualize)
            # Blend 60% model / 40% historical
            new_vol.append(0.6 * pred_ann + 0.4 * hist)
    new_vol_arr = np.array(new_vol)
    return corr * np.outer(new_vol_arr, new_vol_arr) + np.eye(len(symbols)) * 1e-8
