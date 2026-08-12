"""Portfolio performance metrics for rigorous backtest reporting."""

from __future__ import annotations

import numpy as np
import pandas as pd


def portfolio_metrics(
    returns: pd.Series | np.ndarray,
    *,
    turnover: pd.Series | np.ndarray | None = None,
    risk_free_daily: float = 0.0,
    periods_per_year: int = 252,
    var_alpha: float = 0.05,
) -> dict:
    r = pd.Series(returns, dtype=float).dropna()
    if r.empty:
        return _empty_metrics()

    wealth = (1 + r).cumprod()
    n = len(r)
    years = n / periods_per_year
    total = float(wealth.iloc[-1] - 1)
    cagr = float(wealth.iloc[-1] ** (1 / years) - 1) if years > 0 and wealth.iloc[-1] > 0 else 0.0

    vol = float(r.std(ddof=1) * np.sqrt(periods_per_year)) if n > 1 else 0.0
    mean_ann = float(r.mean() * periods_per_year)
    excess = r - risk_free_daily
    sharpe = float(excess.mean() / r.std(ddof=1) * np.sqrt(periods_per_year)) if r.std(ddof=1) > 1e-12 else 0.0

    downside = r[r < 0]
    downside_std = float(downside.std(ddof=1)) if len(downside) > 1 else 0.0
    sortino = (
        float(excess.mean() / downside_std * np.sqrt(periods_per_year)) if downside_std > 1e-12 else 0.0
    )

    peak = wealth.cummax()
    dd = wealth / peak - 1
    mdd = float(dd.min())
    calmar = float(cagr / abs(mdd)) if mdd < -1e-12 else 0.0

    var = float(np.quantile(r, var_alpha))
    cvar = float(r[r <= var].mean()) if (r <= var).any() else var

    avg_turnover = float(pd.Series(turnover).mean()) if turnover is not None and len(turnover) else 0.0
    ann_turnover = avg_turnover * (periods_per_year / max(1, 1))  # daily avg * 252 if daily turnover series
    # If turnover is per-rebalance sparse, caller should pass daily series with zeros

    return {
        "cagr": round(cagr, 4),
        "total_return": round(total, 4),
        "ann_return": round(mean_ann, 4),
        "volatility": round(vol, 4),
        "sharpe": round(sharpe, 4),
        "sortino": round(sortino, 4),
        "max_drawdown": round(mdd, 4),
        "calmar": round(calmar, 4),
        "var_5": round(var, 4),
        "cvar_5": round(cvar, 4),
        "hit_rate": round(float((r > 0).mean()), 4),
        "avg_daily_turnover": round(avg_turnover, 4),
        "ann_turnover": round(avg_turnover * periods_per_year, 4),
        "n_days": int(n),
    }


def _empty_metrics() -> dict:
    return {
        "cagr": 0.0,
        "total_return": 0.0,
        "ann_return": 0.0,
        "volatility": 0.0,
        "sharpe": 0.0,
        "sortino": 0.0,
        "max_drawdown": 0.0,
        "calmar": 0.0,
        "var_5": 0.0,
        "cvar_5": 0.0,
        "hit_rate": 0.0,
        "avg_daily_turnover": 0.0,
        "ann_turnover": 0.0,
        "n_days": 0,
    }


def apply_trading_costs(
    gross_returns: np.ndarray,
    turnover: np.ndarray,
    commission_bps: float = 5.0,
    slippage_bps: float = 5.0,
) -> dict[str, np.ndarray]:
    """
    gross → commission → slippage → net

    Cost model: each day pay (commission_bps + slippage_bps) * turnover
    where turnover = 0.5 * sum(|w_t - w_{t-1}|)  (one-way fraction traded).
    """
    cost_rate = (commission_bps + slippage_bps) / 10_000.0
    cost = turnover * cost_rate
    commission_only = turnover * (commission_bps / 10_000.0)
    slippage_only = turnover * (slippage_bps / 10_000.0)
    after_commission = gross_returns - commission_only
    net = gross_returns - cost
    return {
        "gross": np.asarray(gross_returns, dtype=float),
        "after_commission": after_commission,
        "net": net,
        "commission_drag": commission_only,
        "slippage_drag": slippage_only,
        "total_cost": cost,
    }


def turnover_from_weights(prev_w: np.ndarray | None, new_w: np.ndarray, union_n: int | None = None) -> float:
    """One-way turnover = 0.5 * L1 distance (fully invested long-only)."""
    if prev_w is None:
        # initial deployment counts as full investment turnover
        return 0.5 * float(np.sum(np.abs(new_w)))
    if len(prev_w) != len(new_w):
        # pad shorter — conservative: treat missing as 0
        n = max(len(prev_w), len(new_w))
        a = np.zeros(n)
        b = np.zeros(n)
        a[: len(prev_w)] = prev_w
        b[: len(new_w)] = new_w
        return 0.5 * float(np.sum(np.abs(b - a)))
    return 0.5 * float(np.sum(np.abs(new_w - prev_w)))
