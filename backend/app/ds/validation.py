"""Data quality validation and leakage checks."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd


@dataclass
class ValidationReport:
    ok: bool
    n_rows: int
    n_symbols: int
    date_start: str | None
    date_end: str | None
    issues: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    metrics: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "ok": self.ok,
            "n_rows": self.n_rows,
            "n_symbols": self.n_symbols,
            "date_start": self.date_start,
            "date_end": self.date_end,
            "issues": self.issues,
            "warnings": self.warnings,
            "metrics": self.metrics,
        }


def validate_ohlcv(df: pd.DataFrame, min_history: int = 252) -> ValidationReport:
    """Validate long-format OHLCV panel: date, symbol, open, high, low, close, volume."""
    issues: list[str] = []
    warnings: list[str] = []
    required = {"date", "symbol", "open", "high", "low", "close", "volume"}
    missing = required - set(df.columns)
    if missing:
        return ValidationReport(
            ok=False,
            n_rows=len(df),
            n_symbols=0,
            date_start=None,
            date_end=None,
            issues=[f"Missing columns: {sorted(missing)}"],
        )

    work = df.copy()
    work["date"] = pd.to_datetime(work["date"])
    work = work.sort_values(["symbol", "date"])

    if work.empty:
        issues.append("Empty dataset")

    # Null / non-positive prices
    price_cols = ["open", "high", "low", "close"]
    null_pct = float(work[price_cols].isna().mean().mean())
    if null_pct > 0.01:
        issues.append(f"Null price ratio too high: {null_pct:.2%}")
    elif null_pct > 0:
        warnings.append(f"Null price ratio: {null_pct:.2%}")

    bad_ohlc = (work["high"] < work["low"]) | (work["close"] <= 0) | (work["open"] <= 0)
    if bad_ohlc.any():
        issues.append(f"Invalid OHLC rows: {int(bad_ohlc.sum())}")

    # Duplicate keys
    dups = work.duplicated(subset=["symbol", "date"]).sum()
    if dups:
        issues.append(f"Duplicate symbol-date rows: {int(dups)}")

    # Per-symbol history coverage
    counts = work.groupby("symbol").size()
    short = counts[counts < min_history]
    if len(short):
        warnings.append(f"{len(short)} symbols below {min_history} trading days")

    # Extreme returns (data spikes)
    rets = work.groupby("symbol")["close"].pct_change()
    spike = (rets.abs() > 0.35).sum()
    if spike:
        warnings.append(f"Extreme daily moves (>35%): {int(spike)}")

    # Calendar gaps (weekday continuity soft-check)
    gap_warnings = 0
    for sym, g in work.groupby("symbol"):
        deltas = g["date"].diff().dt.days.dropna()
        if (deltas > 10).any():
            gap_warnings += 1
    if gap_warnings:
        warnings.append(f"{gap_warnings} symbols have gaps >10 calendar days")

    symbols = work["symbol"].nunique()
    report = ValidationReport(
        ok=len(issues) == 0,
        n_rows=len(work),
        n_symbols=int(symbols),
        date_start=str(work["date"].min().date()) if len(work) else None,
        date_end=str(work["date"].max().date()) if len(work) else None,
        issues=issues,
        warnings=warnings,
        metrics={
            "null_price_pct": round(null_pct, 5),
            "median_history_days": int(counts.median()) if len(counts) else 0,
            "min_history_days": int(counts.min()) if len(counts) else 0,
            "max_abs_daily_return": float(rets.abs().max()) if len(rets) else 0.0,
        },
    )
    return report


def leakage_check(feature_cols: list[str], target_col: str = "target") -> list[str]:
    """Reject obviously leaky feature names (future info / target copies)."""
    blocked = []
    forbidden_substrings = (
        "future_",
        "fwd_",
        "lead_",
        "next_",
        "target",
        "label",
        "y_",
        "horizon_return",
    )
    for col in feature_cols:
        low = col.lower()
        if any(s in low for s in forbidden_substrings) and col != target_col:
            blocked.append(col)
        if low.endswith("_t1") or low.endswith("_ahead"):
            blocked.append(col)
    return sorted(set(blocked))


def time_split_indices(n: int, train_ratio: float = 0.7, val_ratio: float = 0.15) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Strict chronological split — no random shuffle (prevents leakage)."""
    i_train = int(n * train_ratio)
    i_val = int(n * (train_ratio + val_ratio))
    idx = np.arange(n)
    return idx[:i_train], idx[i_train:i_val], idx[i_val:]
