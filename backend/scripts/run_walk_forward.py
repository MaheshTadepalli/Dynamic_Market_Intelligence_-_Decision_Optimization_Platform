"""
Walk-forward monthly expanding retrain on the same Yahoo OHLCV cache.

HOLDOUT RULE (strict):
  - Walk-forward months (year < holdout_start): train on all history BEFORE rebalance date (with purge).
  - Holdout months (year >= holdout_start): train ONLY on data BEFORE holdout_start.
    Holdout rows are NEVER used for training, tuning, or quantile clipping.

STRATEGY LABELS:
  - ML (pure): ranking from the trained model only (primary ML claim).
  - Hybrid ML+Mom (--mom-blend > 0): separate strategy; blends ML and momentum ranks.
    Improving hybrid vs momentum does NOT prove the ML model alone got better.

Usage (from backend/):
  ..\\.venv\\Scripts\\python scripts\\run_walk_forward.py --start-test 2018 --holdout-start 2025
  ..\\.venv\\Scripts\\python scripts\\run_walk_forward.py ... --mom-blend 0.25  # optional hybrid
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.linear_model import Ridge
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.ds.features import FEATURE_COLS, build_panel_features  # noqa: E402
from app.ds.ingest import ingestor  # noqa: E402
from app.ds.metrics_portfolio import apply_trading_costs, portfolio_metrics  # noqa: E402

INDEX = {"SPY", "QQQ", "IWM", "DIA", "TLT", "GLD", "HYG"}
HORIZON = 21  # ~1 month in trading days


def month_starts(dates: pd.DatetimeIndex) -> list[pd.Timestamp]:
    s = pd.Series(1, index=dates)
    return list(s.groupby([dates.year, dates.month]).head(1).index)


def holdout_boundary(holdout_start: int) -> pd.Timestamp:
    """First calendar day of holdout — training rows must be strictly before this."""
    return pd.Timestamp(f"{holdout_start}-01-01")


def trading_purge_cutoff(trading_dates: pd.DatetimeIndex, asof: pd.Timestamp, horizon: int) -> pd.Timestamp:
    """
    Last label date allowed in training: label at t uses return t->t+horizon,
    so require trading_dates[idx(t) + horizon] < asof.
    """
    prior = trading_dates[trading_dates < asof]
    if len(prior) <= horizon + 5:
        return pd.Timestamp("1900-01-01")
    # last index where t + horizon is still before asof
    cutoff_idx = len(prior) - horizon - 1
    return pd.Timestamp(prior[cutoff_idx])


def add_cross_section(feat: pd.DataFrame) -> pd.DataFrame:
    df = feat.copy()
    target = f"target_ret_{HORIZON}"
    df["target_xs"] = df[target] - df.groupby("date")[target].transform("mean")
    for c in FEATURE_COLS:
        mu = df.groupby("date")[c].transform("mean")
        sd = df.groupby("date")[c].transform("std").replace(0, np.nan)
        df[f"xs_{c}"] = (df[c] - mu) / sd
    return df


def xs_feature_cols() -> list[str]:
    return [f"xs_{c}" for c in FEATURE_COLS]


def train_model(
    feat: pd.DataFrame,
    asof: pd.Timestamp,
    holdout_start: int,
    trading_dates: pd.DatetimeIndex,
    model_type: str = "hgb",
) -> tuple[Pipeline | None, dict]:
    """
    Returns (model, audit_info).
    Training rows: date <= purge_cutoff AND date < holdout_wall (during holdout phase).
    """
    cols = xs_feature_cols()
    holdout_wall = holdout_boundary(holdout_start)
    in_holdout = asof >= holdout_wall

    purge_end = trading_purge_cutoff(trading_dates, asof, HORIZON)
    if in_holdout:
        # FROZEN: never train on holdout calendar years
        train_end = min(purge_end, holdout_wall - pd.Timedelta(1, unit="D"))
        train_mode = "frozen_pre_holdout"
    else:
        train_end = purge_end
        train_mode = "expanding_walk_forward"

    past = feat[
        (feat["date"] <= train_end)
        & feat[cols + ["target_xs"]].notna().all(axis=1)
        & ~feat["symbol"].isin(INDEX)
    ].copy()

    audit = {
        "asof": str(asof.date()),
        "train_mode": train_mode,
        "holdout_wall": str(holdout_wall.date()),
        "purge_end": str(train_end.date()),
        "n_train_rows": len(past),
        "train_max_date": str(past["date"].max().date()) if len(past) else None,
        "holdout_leak": False,
    }

    if len(past) < 1500:
        return None, audit

    # Hard assertion: no holdout-era rows in training when evaluating holdout
    if in_holdout and past["date"].max() >= holdout_wall:
        audit["holdout_leak"] = True
        raise RuntimeError(
            f"HOLDOUT LEAK: training max date {past['date'].max()} >= wall {holdout_wall}"
        )

    lo, hi = past["target_xs"].quantile([0.01, 0.99])
    past = past[(past["target_xs"] >= lo) & (past["target_xs"] <= hi)]

    if model_type == "ridge":
        model: Pipeline = Pipeline([("scaler", StandardScaler()), ("model", Ridge(alpha=5.0))])
    else:
        model = Pipeline(
            [
                ("scaler", StandardScaler()),
                (
                    "model",
                    HistGradientBoostingRegressor(
                        max_depth=3,
                        learning_rate=0.04,
                        max_iter=150,
                        min_samples_leaf=50,
                        l2_regularization=2.0,
                        random_state=42,
                    ),
                ),
            ]
        )
    model.fit(past[cols], past["target_xs"])
    return model, audit


def latest_xs_rows(feat: pd.DataFrame, asof: pd.Timestamp, symbols: list[str]) -> pd.DataFrame:
    cols = xs_feature_cols()
    day = feat[(feat["date"] < asof) & (~feat["symbol"].isin(INDEX))]
    rows = []
    for sym in symbols:
        g = day[day["symbol"] == sym].dropna(subset=cols + ["vol_21"]).tail(1)
        if g.empty:
            continue
        rows.append(g.iloc[0])
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows)


def predict_scores(model: Pipeline, rows: pd.DataFrame) -> pd.Series:
    cols = xs_feature_cols()
    pred = model.predict(rows[cols])
    return pd.Series(pred, index=rows["symbol"].values)


def blend_ml_momentum_scores(
    ml_scores: pd.Series,
    mom: pd.Series,
    mom_weight: float,
) -> pd.Series:
    """Rank blend: keeps ML primary, borrows momentum when it disagrees less."""
    if mom.empty or mom_weight <= 0:
        return ml_scores
    common = ml_scores.index.intersection(mom.index)
    if len(common) < 5:
        return ml_scores
    ml_r = ml_scores.loc[common].rank(pct=True)
    mom_r = mom.loc[common].rank(pct=True)
    blended = (1 - mom_weight) * ml_r + mom_weight * mom_r
    return blended.sort_values(ascending=False)


def inv_vol_weights(scores: pd.Series, vol: pd.Series, top_k: int, temperature: float = 8.0) -> dict[str, float]:
    if scores.empty:
        return {}
    top = scores.nlargest(top_k)
    if top.empty:
        return {}
    z = (top - top.mean()) / (top.std() + 1e-9)
    sw = np.exp(np.clip(z * temperature / top_k, -5, 5))
    vols = vol.reindex(top.index).replace(0, np.nan).fillna(vol.median())
    raw = sw / vols
    raw = raw / raw.sum()
    return {s: float(w) for s, w in raw.items()}


def equal_weight(symbols: list[str]) -> dict[str, float]:
    if not symbols:
        return {}
    w = 1.0 / len(symbols)
    return {s: w for s in symbols}


def pick_topk_flat(scores: dict[str, float] | pd.Series, k: int) -> dict[str, float]:
    s = pd.Series(scores) if not isinstance(scores, pd.Series) else scores
    if s.empty:
        return {}
    top = s.nlargest(k)
    w = 1.0 / len(top)
    return {i: w for i in top.index}


def blend_weights(prev: dict[str, float] | None, new: dict[str, float], mix: float) -> dict[str, float]:
    if not prev or mix >= 0.999:
        return new
    keys = set(prev) | set(new)
    out = {k: mix * new.get(k, 0.0) + (1 - mix) * prev.get(k, 0.0) for k in keys}
    s = sum(out.values())
    return {k: v / s for k, v in out.items()} if s > 0 else new


def turnover(prev: dict[str, float] | None, new: dict[str, float]) -> float:
    if not prev:
        return 0.5 * sum(abs(v) for v in new.values())
    keys = set(prev) | set(new)
    return 0.5 * sum(abs(new.get(k, 0.0) - prev.get(k, 0.0)) for k in keys)


def build_ml_book(
    scores: pd.Series,
    vols: pd.Series,
    top_k: int,
    min_spread: float,
    prev_w: dict[str, float] | None,
    blend: float,
    rets: pd.DataFrame,
    equities: list[str],
    t0: pd.Timestamp,
) -> tuple[dict[str, float], bool, float]:
    """Returns (weights, gated, spread)."""
    spread = float(scores.nlargest(top_k).mean() - scores.nsmallest(top_k).mean()) if len(scores) >= top_k * 2 else 0.0
    if spread < min_spread:
        w_raw = equal_weight(list(scores.nlargest(min(top_k, len(scores))).index))
        gated = True
    else:
        w_raw = inv_vol_weights(scores, vols, top_k=top_k)
        gated = False
    w = blend_weights(prev_w, w_raw, mix=blend)
    if "SPY" in rets.columns:
        spy_trail = rets["SPY"].loc[: t0 - pd.Timedelta(1, unit="D")].tail(21)
        spy_vol = float(spy_trail.std() * np.sqrt(252)) if len(spy_trail) > 5 else 0.0
        spy_hist_vol = rets["SPY"].loc[: t0 - pd.Timedelta(1, unit="D")].tail(252).std() * np.sqrt(252)
        if spy_hist_vol and spy_vol > float(spy_hist_vol) * 1.25:
            w_ew_safe = equal_weight(equities[: max(top_k, 15)])
            w = blend_weights(w_ew_safe, w, mix=0.5)
    return w, gated, spread


def period_return(rets: pd.DataFrame, weights: dict[str, float], start: pd.Timestamp, end: pd.Timestamp) -> float:
    cols = [s for s in weights if s in rets.columns]
    if not cols:
        return 0.0
    w = np.array([weights[s] for s in cols], dtype=float)
    w = w / w.sum()
    window = rets.loc[(rets.index >= start) & (rets.index < end), cols].fillna(0.0)
    if window.empty:
        return 0.0
    return float(np.prod(1.0 + window.values @ w) - 1.0)


def run(
    start_test: int,
    holdout_start: int,
    commission_bps: float,
    slippage_bps: float,
    top_k: int,
    model_type: str,
    blend: float,
    min_spread: float,
    mom_blend: float,
) -> None:
    print("Loading Yahoo cache (same dataset)...")
    panel = ingestor.get_panel(force_refresh=False)
    panel["date"] = pd.to_datetime(panel["date"]).dt.normalize()
    print(
        f"  rows={len(panel)} symbols={panel['symbol'].nunique()} "
        f"range={panel['date'].min().date()} -> {panel['date'].max().date()}"
    )

    wall = holdout_boundary(holdout_start)
    print(f"  HOLDOUT WALL: training never uses dates >= {wall.date()}")

    print("Building features + cross-sectional relative labels...")
    feat = build_panel_features(panel, [HORIZON])
    feat["date"] = pd.to_datetime(feat["date"]).dt.normalize()
    feat = add_cross_section(feat)

    closes = panel.pivot(index="date", columns="symbol", values="close").sort_index().ffill()
    rets = closes.pct_change()
    equities = [c for c in closes.columns if c not in INDEX]
    trading_dates = pd.DatetimeIndex(closes.index)
    starts = [d for d in month_starts(trading_dates) if d.year >= start_test]
    if len(starts) < 3:
        raise SystemExit("Not enough months — refresh longer history first")

    print(
        f"WF monthly | model={model_type} | purge={HORIZON}td | blend={blend} | "
        f"min_spread={min_spread} | costs={commission_bps}+{slippage_bps}bps"
    )
    if mom_blend > 0:
        ml_w = 1.0 - mom_blend
        print(
            f"  HYBRID enabled: ML rank x {ml_w:.0%} + Momentum rank x {mom_blend:.0%} "
            f"(reported separately from pure ML)"
        )
    else:
        print("  Primary strategy: PURE ML (no momentum in ranking)")
    print()

    records = []
    audits = []
    prev_ml_pure: dict[str, float] | None = None
    prev_ml_hybrid: dict[str, float] | None = None
    prev_mom: dict[str, float] | None = None
    n_gated = 0

    for i, t0 in enumerate(starts[:-1]):
        t1 = starts[i + 1]
        year = int(t0.year)
        phase = "holdout" if t0 >= wall else "walk_forward"

        model, audit = train_model(feat, t0, holdout_start, trading_dates, model_type=model_type)
        audit["phase"] = phase
        audits.append(audit)
        if model is None:
            print(f"  skip {t0.date()} — insufficient train (mode={audit['train_mode']})")
            continue

        rows = latest_xs_rows(feat, t0, equities)
        if rows.empty:
            continue

        scores_pure = predict_scores(model, rows)
        hist = closes[equities].loc[: t0 - pd.Timedelta(1, unit="D")].tail(126)
        mom = (hist.iloc[-1] / hist.iloc[0] - 1).dropna() if len(hist) >= 60 else pd.Series(dtype=float)
        vols = pd.Series(rows["vol_21"].values, index=rows["symbol"].values)

        w_ml_pure, gated, spread = build_ml_book(
            scores_pure, vols, top_k, min_spread, prev_ml_pure, blend, rets, equities, t0
        )
        if gated:
            n_gated += 1

        w_ml_hybrid = None
        if mom_blend > 0 and len(mom) >= top_k:
            scores_hybrid = blend_ml_momentum_scores(scores_pure, mom, mom_blend)
            w_ml_hybrid, _, _ = build_ml_book(
                scores_hybrid, vols, top_k, min_spread, prev_ml_hybrid, blend, rets, equities, t0
            )

        w_mom_raw = pick_topk_flat(mom, top_k) if len(mom) >= top_k else equal_weight(equities[:top_k])
        w_mom = blend_weights(prev_mom, w_mom_raw, mix=blend)

        w_ew = equal_weight(equities[: max(top_k, 15)])
        w_ew_same = equal_weight(list(w_ml_pure.keys())) if w_ml_pure else w_ew

        r_ml_pure = period_return(rets, w_ml_pure, t0, t1)
        r_ml_hybrid = period_return(rets, w_ml_hybrid, t0, t1) if w_ml_hybrid else None
        r_mom = period_return(rets, w_mom, t0, t1)
        r_ew = period_return(rets, w_ew, t0, t1)
        r_ew_same = period_return(rets, w_ew_same, t0, t1)
        r_spy = period_return(rets, {"SPY": 1.0}, t0, t1) if "SPY" in rets.columns else 0.0

        records.append(
            {
                "date": t0,
                "year": year,
                "phase": phase,
                "train_mode": audit["train_mode"],
                "train_max_date": audit["train_max_date"],
                "spread": spread,
                "gated": gated,
                "ml_pure_gross": r_ml_pure,
                "ml_hybrid_gross": r_ml_hybrid,
                "mom_gross": r_mom,
                "ew_gross": r_ew,
                "ew_same_gross": r_ew_same,
                "spy_gross": r_spy,
                "to_ml_pure": turnover(prev_ml_pure, w_ml_pure),
                "to_ml_hybrid": turnover(prev_ml_hybrid, w_ml_hybrid) if w_ml_hybrid else None,
                "to_mom": turnover(prev_mom, w_mom),
                "to_ew": 0.15,
                "to_ew_same": 1.0,
                "mom_blend": mom_blend,
            }
        )
        prev_ml_pure = w_ml_pure
        if w_ml_hybrid:
            prev_ml_hybrid = w_ml_hybrid
        prev_mom = w_mom

        if (i + 1) % 6 == 0 or i == 0:
            line = (
                f"  {t0.date()} [{phase}] pure_ML={r_ml_pure:+.2%} MOM={r_mom:+.2%}"
            )
            if r_ml_hybrid is not None:
                line += f" hybrid={r_ml_hybrid:+.2%}"
            print(line)

    df = pd.DataFrame(records).set_index("date")
    if df.empty:
        raise SystemExit("No results")

    # Audit: verify holdout never trained on holdout dates
    holdout_rows = df[df["phase"] == "holdout"]
    if len(holdout_rows):
        max_train_in_holdout = pd.to_datetime(holdout_rows["train_max_date"]).max()
        if max_train_in_holdout >= wall:
            raise RuntimeError(f"HOLDOUT LEAK in results: max train date {max_train_in_holdout} >= {wall}")
        print(f"\nHOLDOUT AUDIT OK: max training date during holdout = {max_train_in_holdout.date()} (< {wall.date()})")

    def score(gross_col: str, to_col: str, mask: pd.Series) -> dict:
        g = df.loc[mask, gross_col].values
        to = df.loc[mask, to_col].values
        net = apply_trading_costs(g, to, commission_bps, slippage_bps)["net"]
        return portfolio_metrics(net, turnover=to, periods_per_year=12)

    print(f"\nConfidence gates: {n_gated}/{len(df)} months ({n_gated/len(df):.0%})")
    print("\n=== NET results (after commission + slippage) ===")
    print("NOTE: 'ML (pure)' = ML ranking only. 'Hybrid' = ML+momentum rank blend (separate strategy).\n")

    strategy_rows = [
        ("ML (pure)", "ml_pure_gross", "to_ml_pure"),
        ("Momentum", "mom_gross", "to_mom"),
        ("Equal weight", "ew_gross", "to_ew"),
        ("EW same names", "ew_same_gross", "to_ew_same"),
        ("Buy&Hold SPY", "spy_gross", "to_ew"),
    ]
    if mom_blend > 0 and df["ml_hybrid_gross"].notna().any():
        strategy_rows.insert(1, ("Hybrid ML+Mom", "ml_hybrid_gross", "to_ml_hybrid"))

    for phase in ["walk_forward", "holdout"]:
        mask = df["phase"] == phase
        if mask.sum() == 0:
            continue
        print(f"\n{phase.upper()}  (n_months={int(mask.sum())})")
        metrics = {}
        for name, gcol, tcol in strategy_rows:
            idx_mask = mask.copy()
            if gcol == "ml_hybrid_gross":
                idx_mask &= df[gcol].notna()
                if idx_mask.sum() == 0:
                    continue
            g = df.loc[idx_mask, gcol].values
            to = df.loc[idx_mask, tcol].values
            net = apply_trading_costs(g, to, commission_bps, slippage_bps)["net"]
            m = portfolio_metrics(net, turnover=to, periods_per_year=12)
            metrics[name] = m
            print(
                f"  {name:16s}  CAGR={m['cagr']:+.2%}  Sharpe={m['sharpe']:.2f}  "
                f"Sortino={m['sortino']:.2f}  MDD={m['max_drawdown']:.2%}  "
                f"Calmar={m['calmar']:.2f}  Vol={m['volatility']:.2%}  annTO={m['ann_turnover']:.2f}"
            )
        pure_s = metrics.get("ML (pure)", {}).get("sharpe")
        mom_s = metrics.get("Momentum", {}).get("sharpe")
        if pure_s is not None and mom_s is not None:
            print(f"  -> ML (pure) Sharpe - Momentum Sharpe = {pure_s - mom_s:+.2f}")
        if "Hybrid ML+Mom" in metrics:
            hyb_s = metrics["Hybrid ML+Mom"]["sharpe"]
            print(f"  -> Hybrid Sharpe - Momentum Sharpe = {hyb_s - mom_s:+.2f}  (hybrid strategy, not pure ML)")

    print("\n=== ML (pure) net by year ===")
    for year, g in df.groupby("year"):
        m = score("ml_pure_gross", "to_ml_pure", df["year"] == year)
        mm = score("mom_gross", "to_mom", df["year"] == year)
        phase = g["phase"].iloc[0]
        print(
            f"  {year} [{phase}]  pure_ML Sharpe={m['sharpe']:.2f} CAGR={m['cagr']:+.2%}  |  "
            f"MOM Sharpe={mm['sharpe']:.2f}  |  gated={int(g['gated'].sum())}/{len(g)}"
        )

    out_dir = Path("data")
    out_dir.mkdir(parents=True, exist_ok=True)
    df.to_csv(out_dir / "walk_forward_results_v3.csv")
    pd.DataFrame(audits).to_csv(out_dir / "walk_forward_train_audit.csv", index=False)
    print(f"\nSaved results -> {(out_dir / 'walk_forward_results_v3.csv').resolve()}")
    print(f"Saved audit   -> {(out_dir / 'walk_forward_train_audit.csv').resolve()}")


def main() -> None:
    p = argparse.ArgumentParser(description="Walk-forward with strict holdout wall")
    p.add_argument("--start-test", type=int, default=2018)
    p.add_argument("--holdout-start", type=int, default=2025, help="Years >= this are holdout; never used in training")
    p.add_argument("--commission-bps", type=float, default=5.0)
    p.add_argument("--slippage-bps", type=float, default=5.0)
    p.add_argument("--top-k", type=int, default=8)
    p.add_argument("--model", choices=["hgb", "ridge"], default="hgb")
    p.add_argument("--blend", type=float, default=0.40, help="New weight fraction each month")
    p.add_argument("--min-spread", type=float, default=0.012)
    p.add_argument(
        "--mom-blend",
        type=float,
        default=0.0,
        help="Optional hybrid: blend momentum into ML ranks (e.g. 0.25 = 75%% ML + 25%% mom). "
        "Reported separately; does not change pure ML metrics.",
    )
    args = p.parse_args()
    run(
        args.start_test,
        args.holdout_start,
        args.commission_bps,
        args.slippage_bps,
        args.top_k,
        args.model,
        args.blend,
        args.min_spread,
        args.mom_blend,
    )


if __name__ == "__main__":
    main()
