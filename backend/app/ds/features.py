"""Feature engineering for multi-horizon forecasting (no future leakage)."""

from __future__ import annotations

import numpy as np
import pandas as pd

from app.ds.validation import leakage_check


FEATURE_COLS = [
    "ret_1",
    "ret_5",
    "ret_21",
    "ret_63",
    "vol_10",
    "vol_21",
    "vol_63",
    "rsi_14",
    "macd",
    "macd_signal",
    "macd_hist",
    "sma_ratio_20",
    "sma_ratio_50",
    "mom_10",
    "mom_21",
    "volume_z_20",
    "high_low_range",
    "gap",
]


def _rsi(close: pd.Series, window: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(window).mean()
    loss = (-delta.clip(upper=0)).rolling(window).mean()
    rs = gain / loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def _ema(series: pd.Series, span: int) -> pd.Series:
    return series.ewm(span=span, adjust=False).mean()


def build_symbol_features(ohlcv: pd.DataFrame) -> pd.DataFrame:
    """Build lagged technical + return features for one symbol. All features use t and earlier only."""
    df = ohlcv.sort_values("date").copy()
    c = df["close"]
    df["ret_1"] = c.pct_change(1)
    df["ret_5"] = c.pct_change(5)
    df["ret_21"] = c.pct_change(21)
    df["ret_63"] = c.pct_change(63)
    df["vol_10"] = df["ret_1"].rolling(10).std()
    df["vol_21"] = df["ret_1"].rolling(21).std()
    df["vol_63"] = df["ret_1"].rolling(63).std()
    df["rsi_14"] = _rsi(c, 14)
    ema12 = _ema(c, 12)
    ema26 = _ema(c, 26)
    df["macd"] = ema12 - ema26
    df["macd_signal"] = _ema(df["macd"], 9)
    df["macd_hist"] = df["macd"] - df["macd_signal"]
    sma20 = c.rolling(20).mean()
    sma50 = c.rolling(50).mean()
    df["sma_ratio_20"] = c / sma20 - 1
    df["sma_ratio_50"] = c / sma50 - 1
    df["mom_10"] = c.pct_change(10)
    df["mom_21"] = c.pct_change(21)
    vol_mean = df["volume"].rolling(20).mean()
    vol_std = df["volume"].rolling(20).std().replace(0, np.nan)
    df["volume_z_20"] = (df["volume"] - vol_mean) / vol_std
    df["high_low_range"] = (df["high"] - df["low"]) / c
    df["gap"] = df["open"] / c.shift(1) - 1
    return df


def build_panel_features(panel: pd.DataFrame, horizons: list[int]) -> pd.DataFrame:
    """
    Build cross-sectional panel with features and forward targets.
    Targets are shifted -h (future returns) and must NEVER appear as features.
    """
    frames = []
    for sym, g in panel.groupby("symbol"):
        feat = build_symbol_features(g)
        for h in horizons:
            # Forward return from t -> t+h (label only)
            feat[f"target_ret_{h}"] = feat["close"].pct_change(h).shift(-h)
        frames.append(feat)
    out = pd.concat(frames, ignore_index=True)
    leaky = leakage_check(list(out.columns))
    # target_* intentionally present; strip other leaky cols if any
    leaky = [c for c in leaky if not c.startswith("target_ret_")]
    if leaky:
        raise ValueError(f"Potential leakage columns detected: {leaky}")
    return out


def latest_feature_row(panel: pd.DataFrame, symbol: str) -> pd.Series | None:
    g = panel[panel["symbol"] == symbol.upper()]
    if g.empty:
        return None
    feat = build_symbol_features(g)
    row = feat.dropna(subset=FEATURE_COLS).tail(1)
    if row.empty:
        return None
    return row.iloc[0]
