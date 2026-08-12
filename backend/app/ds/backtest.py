"""
Rigorous walk-forward validation:
baselines · transaction costs · ablations · regime-period evaluation.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable

import numpy as np
import pandas as pd
from scipy.optimize import minimize

from app.ds.evaluation import evaluate_predictions
from app.ds.features import FEATURE_COLS, build_panel_features
from app.ds.metrics_portfolio import apply_trading_costs, portfolio_metrics, turnover_from_weights
from app.ds.risk import blend_predicted_vols, estimate_covariance

INDEX_SET = {"SPY", "QQQ", "IWM", "DIA", "TLT", "GLD", "HYG"}


def _max_sharpe_weights(mu: np.ndarray, cov: np.ndarray, max_weight: float = 0.2) -> np.ndarray:
    n = len(mu)
    if n == 0:
        return np.array([])
    bounds = [(0.0, max_weight)] * n
    cons = [{"type": "eq", "fun": lambda w: np.sum(w) - 1.0}]

    def neg_sharpe(w: np.ndarray) -> float:
        vol = float(np.sqrt(max(w @ cov @ w, 0.0)))
        if vol < 1e-12:
            return 0.0
        return -float(w @ mu) / vol

    res = minimize(
        neg_sharpe,
        np.full(n, 1 / n),
        method="SLSQP",
        bounds=bounds,
        constraints=cons,
        options={"maxiter": 150, "ftol": 1e-9},
    )
    w = res.x if res.success else np.full(n, 1 / n)
    w = np.clip(w, 0, None)
    s = w.sum()
    return w / s if s > 0 else np.full(n, 1 / n)


def _sample_cov(hist: pd.DataFrame, annualize: float = 252.0) -> tuple[np.ndarray, list[str]]:
    clean = hist.dropna(how="any")
    if clean.shape[1] < 2 or clean.shape[0] < 40:
        raise ValueError("insufficient")
    symbols = list(clean.columns)
    cov = np.cov(clean.values, rowvar=False) * annualize + np.eye(len(symbols)) * 1e-8
    return cov, symbols


def _label_market_regimes(spy_rets: pd.Series) -> pd.Series:
    """Assign each date a market-state label for sliced evaluation."""
    roll_ret = spy_rets.rolling(63).sum()
    roll_vol = spy_rets.rolling(21).std() * np.sqrt(252)
    crash = spy_rets.rolling(21).sum() <= -0.12
    vol_hi = roll_vol >= roll_vol.quantile(0.75)
    vol_lo = roll_vol <= roll_vol.quantile(0.25)

    labels = pd.Series("mixed", index=spy_rets.index, dtype=object)
    labels[roll_ret > 0.08] = "bull"
    labels[roll_ret < -0.08] = "bear"
    labels[vol_hi & (roll_ret >= -0.08) & (roll_ret <= 0.08)] = "high_vol"
    labels[vol_lo & (roll_ret >= -0.08) & (roll_ret <= 0.08)] = "low_vol"
    labels[crash] = "crash"
    # recovery: positive 21d after a crash flag in prior 63d
    prior_crash = crash.rolling(63).max().fillna(0).astype(bool)
    labels[prior_crash & (spy_rets.rolling(21).sum() > 0.05) & ~crash] = "recovery"
    return labels


class ValidationEngine:
    def __init__(
        self,
        panel: pd.DataFrame,
        return_models: dict,
        vol_model=None,
        regime_predict: Callable | None = None,
        feature_cols: list[str] | None = None,
        horizon: int = 21,
        rebalance_every: int = 21,
        max_weight: float = 0.15,
        lookback: int = 126,
        commission_bps: float = 5.0,
        slippage_bps: float = 5.0,
    ) -> None:
        self.panel = panel
        self.return_models = return_models
        self.vol_model = vol_model
        self.regime_predict = regime_predict
        self.feature_cols = feature_cols or FEATURE_COLS
        self.horizon = horizon
        self.rebalance_every = rebalance_every
        self.max_weight = max_weight
        self.lookback = lookback
        self.commission_bps = commission_bps
        self.slippage_bps = slippage_bps

        self.feat = build_panel_features(panel, [horizon])
        self.closes = panel.pivot(index="date", columns="symbol", values="close").sort_index().ffill()
        self.rets = self.closes.pct_change()
        self.equities = [c for c in self.closes.columns if c not in INDEX_SET]
        self.dates = list(self.closes[self.equities].dropna(how="all").index)

        feat_idx = self.feat.dropna(subset=self.feature_cols).copy()
        feat_idx["date"] = pd.to_datetime(feat_idx["date"]).dt.normalize()
        self._feat_idx = feat_idx.set_index(["date", "symbol"]).sort_index()
        self.dates = [pd.Timestamp(d).normalize() for d in self.dates]

    def _feature_frame(self, dt, symbols: list[str]) -> tuple[pd.DataFrame, list[str]]:
        dt = pd.Timestamp(dt).normalize()
        rows, kept = [], []
        for sym in symbols:
            key = (dt, sym)
            if key not in self._feat_idx.index:
                continue
            row = self._feat_idx.loc[key]
            if isinstance(row, pd.DataFrame):
                row = row.iloc[0]
            if row[self.feature_cols].isna().any():
                continue
            rows.append(row)
            kept.append(sym)
        if not rows:
            return pd.DataFrame(), []
        return pd.DataFrame(rows), kept

    def _hist_window(self, symbols: list[str], dt) -> pd.DataFrame:
        return self.rets[symbols].loc[:dt].tail(self.lookback)

    def _mu_from_model(self, X: pd.DataFrame, symbols: list[str]) -> np.ndarray:
        model = self.return_models.get(self.horizon) or next(iter(self.return_models.values()))
        pred_h = model.predict(X[self.feature_cols])
        return np.asarray(pred_h, dtype=float) * (252 / self.horizon)

    def _cov(
        self,
        hist: pd.DataFrame,
        symbols: list[str],
        X: pd.DataFrame | None,
        use_lw: bool,
        blend_vol: bool,
    ) -> tuple[np.ndarray, list[str]]:
        if use_lw:
            cov, cov_syms = estimate_covariance(hist[symbols].dropna(how="any"))
        else:
            cov, cov_syms = _sample_cov(hist[symbols])
        if blend_vol and self.vol_model is not None and X is not None and len(X):
            # map predicted vol for cov_syms
            pred_vol = {}
            sym_to_i = {s: i for i, s in enumerate(symbols)}
            vols = self.vol_model.predict(X[self.feature_cols])
            for s, v in zip(symbols, vols):
                pred_vol[s] = float(v)
            cov = blend_predicted_vols(cov, cov_syms, pred_vol)
        return cov, cov_syms

    def _regime_scale(self, mu: np.ndarray, cov: np.ndarray, dt, enabled: bool) -> tuple[np.ndarray, np.ndarray, str]:
        if not enabled or self.regime_predict is None:
            return mu, cov, "none"
        spy_rows = self.feat[(self.feat["symbol"] == "SPY") & (self.feat["date"] == dt)]
        if spy_rows.empty:
            return mu, cov, "none"
        info = self.regime_predict(spy_rows.iloc[0])
        regime = info.get("regime", "transition")
        if regime == "risk_off":
            return mu * 0.7, cov * 1.25, regime
        if regime == "risk_on":
            return mu, cov * 0.9, regime
        return mu, cov, regime

    def _weights_for_variant(
        self,
        variant: str,
        dt,
        symbols: list[str],
        X: pd.DataFrame,
    ) -> tuple[np.ndarray, list[str]] | None:
        hist = self._hist_window(symbols, dt)
        if hist.dropna(how="any").shape[0] < 40:
            return None

        use_ml = variant in {
            "ml_tech",
            "ml_regime",
            "ml_lw",
            "ml_full",
            "ml_stress",
        }
        use_regime = variant in {"ml_regime", "ml_lw", "ml_full", "ml_stress"}
        use_lw = variant in {"ml_lw", "ml_full", "ml_stress", "hist_mean_lw"}
        blend_vol = variant in {"ml_full", "ml_stress"}

        if variant == "equal_weight":
            kept = [s for s in symbols if s in hist.columns]
            if len(kept) < 3:
                return None
            return np.full(len(kept), 1 / len(kept)), kept

        if variant == "buy_hold_spy":
            return np.array([1.0]), ["SPY"] if "SPY" in self.rets.columns else None

        if variant == "momentum":
            # top quintile by 126d momentum, equal weight
            mom = self.closes[symbols].loc[:dt].pct_change(126).iloc[-1].dropna()
            if len(mom) < 5:
                return None
            top = list(mom.nlargest(max(3, len(mom) // 5)).index)
            return np.full(len(top), 1 / len(top)), top

        if variant == "technical":
            # long names with RSI 40-60 crossing up sma20>sma50 proxy via features
            score = X["sma_ratio_20"].values + 0.5 * X["macd_hist"].fillna(0).values - 0.01 * (X["rsi_14"] - 50).abs()
            order = np.argsort(-score)
            k = max(3, len(symbols) // 5)
            pick = [symbols[i] for i in order[:k]]
            return np.full(len(pick), 1 / len(pick)), pick

        # Expected-return variants
        if use_ml:
            mu_all = self._mu_from_model(X, symbols)
        elif variant in {"hist_mean", "hist_mean_lw"}:
            mu_all = hist[symbols].mean().reindex(symbols).fillna(0).values * 252
        else:
            return None

        try:
            cov, cov_syms = self._cov(hist, symbols, X, use_lw=use_lw or variant == "hist_mean", blend_vol=blend_vol)
        except ValueError:
            return None

        idx = {s: i for i, s in enumerate(symbols)}
        mu = np.array([mu_all[idx[s]] for s in cov_syms])
        mu, cov, _ = self._regime_scale(mu, cov, dt, enabled=use_regime)

        max_w = self.max_weight
        if variant == "ml_stress":
            # stress-aware: tighten max weight and inflate cov in elevated vol
            spy = self.rets["SPY"].loc[:dt].tail(21) if "SPY" in self.rets.columns else None
            if spy is not None and float(spy.std() * np.sqrt(252)) > 0.25:
                cov = cov * 1.35
                max_w = min(max_w, 0.10)

        w = _max_sharpe_weights(mu, cov, max_weight=max_w)
        return w, cov_syms

    def _simulate(self, variant: str) -> dict:
        start_i = self.lookback
        if len(self.dates) < start_i + self.horizon * 3:
            raise ValueError("Not enough history for validation")

        gross: list[float] = []
        turnovers: list[float] = []
        dates_out: list = []
        current_w = None
        current_syms: list[str] = []
        prev_w_aligned = None
        n_reb = 0
        i = start_i

        while i < len(self.dates) - 1:
            dt = self.dates[i]
            X, syms = self._feature_frame(dt, self.equities)
            if len(syms) < 5 and variant not in {"buy_hold_spy"}:
                i += 1
                continue

            rebalance = current_w is None or ((i - start_i) % self.rebalance_every == 0)
            if rebalance:
                got = self._weights_for_variant(variant, dt, syms if variant != "buy_hold_spy" else ["SPY"], X)
                if got is None:
                    i += 1
                    continue
                new_w, new_syms = got
                if new_w is None or new_syms is None:
                    i += 1
                    continue
                # turnover vs previous book in union space
                if prev_w_aligned is None:
                    to = turnover_from_weights(None, new_w)
                else:
                    union = list(dict.fromkeys(current_syms + new_syms))
                    pw = np.zeros(len(union))
                    nw = np.zeros(len(union))
                    for j, s in enumerate(union):
                        if s in current_syms:
                            pw[j] = current_w[current_syms.index(s)]
                        if s in new_syms:
                            nw[j] = new_w[new_syms.index(s)]
                    to = turnover_from_weights(pw, nw)
                current_w, current_syms = new_w, new_syms
                prev_w_aligned = new_w
                n_reb += 1
            else:
                to = 0.0

            nxt = self.dates[i + 1]
            day = self.rets.loc[nxt, current_syms].fillna(0.0).values
            gr = float(np.dot(current_w, day))
            gross.append(gr)
            turnovers.append(to)
            dates_out.append(pd.Timestamp(nxt))
            i += 1

        if not gross:
            raise ValueError(f"No returns for variant {variant}")

        g = np.array(gross)
        t = np.array(turnovers)
        layers = apply_trading_costs(g, t, self.commission_bps, self.slippage_bps)
        net = layers["net"]
        metrics_gross = portfolio_metrics(g, turnover=t)
        metrics_net = portfolio_metrics(net, turnover=t)
        return {
            "variant": variant,
            "n_rebalances": n_reb,
            "cost_model": {
                "commission_bps": self.commission_bps,
                "slippage_bps": self.slippage_bps,
                "avg_daily_cost_bps": round(float(layers["total_cost"].mean() * 10_000), 3),
                "total_cost_drag": round(float(layers["total_cost"].sum()), 4),
            },
            "gross": metrics_gross,
            "net": metrics_net,
            "returns_net": net,
            "returns_gross": g,
            "dates": dates_out,
            "turnover": t,
        }

    def _equity_curve(self, dates, returns, step: int | None = None) -> list[dict]:
        r = pd.Series(returns, index=pd.DatetimeIndex(dates))
        wealth = (1 + r).cumprod() - 1
        step = step or max(1, len(wealth) // 100)
        return [
            {"date": str(idx.date()), "value": round(float(val), 4)}
            for idx, val in wealth.iloc[::step].items()
        ]

    def forecast_uncertainty(self) -> dict:
        """Holdout-style uncertainty using last 15% chronological rows."""
        target = f"target_ret_{self.horizon}"
        data = self.feat.dropna(subset=self.feature_cols + [target]).sort_values("date")
        if len(data) < 500:
            return {"ok": False, "reason": "insufficient rows"}
        split = int(len(data) * 0.85)
        te = data.iloc[split:]
        model = self.return_models.get(self.horizon) or next(iter(self.return_models.values()))
        pred = model.predict(te[self.feature_cols])
        y = te[target].values
        vol_true = vol_pred = None
        if self.vol_model is not None and "vol_21" in te.columns:
            # realized next-day rolling vol proxy already in training; use contemporaneous vol_21 as noisy true
            vol_true = te["vol_21"].values
            vol_pred = self.vol_model.predict(te[self.feature_cols])
        return evaluate_predictions(y, pred, y_vol_true=vol_true, y_vol_pred=vol_pred)

    def run(self) -> dict:
        variants = [
            "buy_hold_spy",
            "equal_weight",
            "hist_mean",
            "momentum",
            "technical",
            "ml_tech",       # ML μ + sample cov
            "ml_regime",     # + regime
            "ml_lw",         # + Ledoit-Wolf
            "ml_full",       # + vol blend
            "ml_stress",     # + stress-aware
        ]
        results = {}
        for v in variants:
            try:
                results[v] = self._simulate(v)
            except Exception as exc:  # noqa: BLE001
                results[v] = {"variant": v, "error": str(exc)}

        # Comparison table (net sharpe / cagr)
        comparison = []
        for v, res in results.items():
            if "error" in res:
                comparison.append({"strategy": v, "error": res["error"]})
                continue
            comparison.append(
                {
                    "strategy": v,
                    "role": _role(v),
                    "net_cagr": res["net"]["cagr"],
                    "net_sharpe": res["net"]["sharpe"],
                    "net_sortino": res["net"]["sortino"],
                    "max_drawdown": res["net"]["max_drawdown"],
                    "calmar": res["net"]["calmar"],
                    "volatility": res["net"]["volatility"],
                    "var_5": res["net"]["var_5"],
                    "cvar_5": res["net"]["cvar_5"],
                    "ann_turnover": res["net"]["ann_turnover"],
                    "gross_sharpe": res["gross"]["sharpe"],
                    "cost_drag": res["cost_model"]["total_cost_drag"],
                    "beats_equal_weight_net": (
                        res["net"]["sharpe"] > results.get("equal_weight", {}).get("net", {}).get("sharpe", -999)
                        if "net" in results.get("equal_weight", {})
                        else None
                    ),
                }
            )

        # Ablation ladder (delta net Sharpe vs previous step)
        ablation_order = ["technical", "ml_tech", "ml_regime", "ml_lw", "ml_full", "ml_stress"]
        ablation = []
        prev_sharpe = None
        for v in ablation_order:
            res = results.get(v, {})
            if "net" not in res:
                ablation.append({"step": v, "error": res.get("error", "missing")})
                continue
            sh = res["net"]["sharpe"]
            ablation.append(
                {
                    "step": v,
                    "label": _ablation_label(v),
                    "net_sharpe": sh,
                    "net_cagr": res["net"]["cagr"],
                    "max_drawdown": res["net"]["max_drawdown"],
                    "delta_sharpe": None if prev_sharpe is None else round(sh - prev_sharpe, 4),
                }
            )
            prev_sharpe = sh

        # Regime-period evaluation on best full ML variant
        primary = results.get("ml_full") or results.get("ml_stress")
        regime_slices = []
        if primary and "returns_net" in primary and "SPY" in self.rets.columns:
            spy = self.rets["SPY"].reindex(primary["dates"]).fillna(0)
            labels = _label_market_regimes(self.rets["SPY"]).reindex(primary["dates"]).fillna("mixed")
            net = pd.Series(primary["returns_net"], index=pd.DatetimeIndex(primary["dates"]))
            ew = results.get("equal_weight", {})
            ew_net = (
                pd.Series(ew["returns_net"], index=pd.DatetimeIndex(ew["dates"]))
                if "returns_net" in ew
                else None
            )
            for name in ["bull", "bear", "high_vol", "low_vol", "crash", "recovery"]:
                mask = labels == name
                if mask.sum() < 21:
                    regime_slices.append({"period": name, "n_days": int(mask.sum()), "insufficient": True})
                    continue
                m = portfolio_metrics(net[mask])
                row = {
                    "period": name,
                    "n_days": int(mask.sum()),
                    "ml_net": m,
                    "insufficient": False,
                }
                if ew_net is not None:
                    row["equal_weight_net"] = portfolio_metrics(ew_net.reindex(net[mask].index).dropna())
                    row["ml_beats_ew_sharpe"] = m["sharpe"] > row["equal_weight_net"]["sharpe"]
                regime_slices.append(row)

        # Curves for plotting
        curves = {}
        for key in ["ml_full", "equal_weight", "buy_hold_spy", "momentum", "technical"]:
            res = results.get(key)
            if res and "returns_net" in res:
                curves[key] = self._equity_curve(res["dates"], res["returns_net"])

        uncertainty = self.forecast_uncertainty()

        # Honest summary
        ml = results.get("ml_full", {})
        ew = results.get("equal_weight", {})
        bh = results.get("buy_hold_spy", {})
        summary = {
            "ml_net_sharpe": ml.get("net", {}).get("sharpe"),
            "ew_net_sharpe": ew.get("net", {}).get("sharpe"),
            "bh_net_sharpe": bh.get("net", {}).get("sharpe"),
            "ml_beats_ew_after_costs": (
                ml.get("net", {}).get("sharpe", -999) > ew.get("net", {}).get("sharpe", 999)
                if "net" in ml and "net" in ew
                else None
            ),
            "ml_beats_buyhold_after_costs": (
                ml.get("net", {}).get("sharpe", -999) > bh.get("net", {}).get("sharpe", 999)
                if "net" in ml and "net" in bh
                else None
            ),
            "gross_to_net_sharpe_gap": (
                round(ml["gross"]["sharpe"] - ml["net"]["sharpe"], 4) if "net" in ml else None
            ),
        }

        caveats = [
            "Models are fit once on the full sample then applied walk-forward (not re-fit each rebalance) — results can be optimistically biased.",
            "Directional accuracy near 50% means portfolio Sharpe may not be stable out of sample.",
            "Regime slices with few days (bear/crash) are marked insufficient — do not over-interpret them.",
            "Transaction costs use bps × turnover; real spreads vary by name and volatility.",
        ]

        return {
            "as_of": datetime.now(timezone.utc).isoformat(),
            "config": {
                "horizon": self.horizon,
                "rebalance_every": self.rebalance_every,
                "max_weight": self.max_weight,
                "lookback": self.lookback,
                "commission_bps": self.commission_bps,
                "slippage_bps": self.slippage_bps,
                "n_equities": len(self.equities),
            },
            "summary": summary,
            "caveats": caveats,
            "comparison": comparison,
            "ablation": ablation,
            "regime_periods": regime_slices,
            "uncertainty": uncertainty,
            "equity_curves_net": curves,
            "strategies": {
                k: {
                    "gross": v.get("gross"),
                    "net": v.get("net"),
                    "cost_model": v.get("cost_model"),
                    "n_rebalances": v.get("n_rebalances"),
                    "error": v.get("error"),
                }
                for k, v in results.items()
            },
        }


def _role(v: str) -> str:
    if v in {"buy_hold_spy", "equal_weight", "hist_mean", "momentum", "technical"}:
        return "baseline"
    return "ml_system"


def _ablation_label(v: str) -> str:
    return {
        "technical": "Technical features only",
        "ml_tech": "+ ML return predictions",
        "ml_regime": "+ regime probabilities",
        "ml_lw": "+ Ledoit-Wolf covariance",
        "ml_full": "+ predicted-vol blend",
        "ml_stress": "+ stress-aware optimization",
    }.get(v, v)


def run_backtest(panel, return_model, **kwargs) -> dict:
    """Backward-compatible wrapper → full validation suite."""
    models = return_model if isinstance(return_model, dict) else {kwargs.get("horizon", 21): return_model}
    engine = ValidationEngine(panel, return_models=models, **{k: v for k, v in kwargs.items() if k != "feature_cols"})
    return engine.run()


def run_validation_suite(
    panel: pd.DataFrame,
    return_models: dict,
    vol_model=None,
    regime_predict=None,
    **kwargs,
) -> dict:
    engine = ValidationEngine(
        panel,
        return_models=return_models,
        vol_model=vol_model,
        regime_predict=regime_predict,
        **kwargs,
    )
    return engine.run()
