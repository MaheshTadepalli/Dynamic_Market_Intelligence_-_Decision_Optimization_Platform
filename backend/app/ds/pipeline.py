"""End-to-end DS pipeline: ingest → validate → features → train/predict → decision inputs."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from threading import Lock

import numpy as np
import pandas as pd

from app.core.config import get_settings
from app.ds.features import FEATURE_COLS, build_symbol_features
from app.ds.ingest import ingestor
from app.ds.mlflow_tracking import log_training_run
from app.ds.models import forecasting_suite
from app.ds.risk import blend_predicted_vols, estimate_covariance
from app.ds.universe import meta_for
from app.ds.validation import validate_ohlcv

logger = logging.getLogger(__name__)


class DSPipeline:
    def __init__(self) -> None:
        self._lock = Lock()
        self.status = "cold"
        self.last_error: str | None = None
        self.validation: dict | None = None
        self.last_train_metrics: list[dict] = []
        self.mlflow_run_id: str | None = None
        self.ready = False
        self._latest_forecasts: pd.DataFrame | None = None
        self._regime: dict | None = None

    def bootstrap(self, force_refresh: bool = False, train: bool = True) -> dict:
        with self._lock:
            self.status = "loading"
            try:
                panel = ingestor.fetch(force=force_refresh) if force_refresh else ingestor.get_panel()
                report = validate_ohlcv(panel)
                self.validation = report.to_dict()
                if not report.ok:
                    self.status = "validation_failed"
                    self.last_error = str(report.issues)
                    return {"ok": False, "validation": self.validation}

                loaded = forecasting_suite.load()
                if train or not loaded:
                    self.status = "training"
                    metrics = forecasting_suite.train(panel)
                    self.last_train_metrics = metrics
                    settings = get_settings()
                    try:
                        self.mlflow_run_id = log_training_run(
                            metrics,
                            params={
                                "horizons": settings.forecast_horizons,
                                "universe_size": settings.universe_size,
                                "lookback_years": settings.market_lookback_years,
                                "n_rows": len(panel),
                                "n_symbols": int(panel["symbol"].nunique()),
                            },
                        )
                    except Exception as mlflow_exc:  # noqa: BLE001
                        logger.warning("MLflow tracking failed (non-fatal): %s", mlflow_exc)
                        self.mlflow_run_id = None
                else:
                    self.last_train_metrics = [m.to_dict() for m in forecasting_suite.metrics]

                self._refresh_forecasts_unlocked(panel)
                self.ready = True
                self.status = "ready"
                self.last_error = None
                return self.snapshot()
            except Exception as exc:
                logger.exception("Pipeline bootstrap failed")
                self.status = "error"
                self.last_error = str(exc)
                self.ready = False
                return {"ok": False, "status": self.status, "error": self.last_error}

    def _refresh_forecasts_unlocked(self, panel: pd.DataFrame | None = None) -> None:
        panel = panel if panel is not None else ingestor.get_panel()
        rows = []
        for sym, g in panel.groupby("symbol"):
            feat = build_symbol_features(g)
            latest = feat.dropna(subset=FEATURE_COLS).tail(1)
            if latest.empty:
                continue
            row = latest.iloc[0]
            entry = {
                "symbol": sym,
                "date": str(pd.Timestamp(row["date"]).date()),
                "close": float(row["close"]),
                "rsi_14": float(row["rsi_14"]),
                "macd": float(row["macd"]),
                "macd_signal": float(row["macd_signal"]),
                "vol_21": float(row["vol_21"]),
                "mom_21": float(row["mom_21"]),
            }
            X = latest[FEATURE_COLS]
            for h, model in forecasting_suite.return_models.items():
                entry[f"pred_ret_{h}d"] = float(model.predict(X)[0])
            entry["pred_vol"] = float(forecasting_suite.predict_vol(X).iloc[0])
            rows.append(entry)

        self._latest_forecasts = pd.DataFrame(rows)

        spy = self._latest_forecasts[self._latest_forecasts["symbol"] == "SPY"]
        if not spy.empty:
            # rebuild spy feature vector for regime
            spy_hist = build_symbol_features(panel[panel["symbol"] == "SPY"]).dropna(
                subset=["ret_21", "vol_21", "mom_21", "rsi_14"]
            ).tail(1)
            if not spy_hist.empty:
                self._regime = forecasting_suite.predict_regime(spy_hist.iloc[0])
            else:
                self._regime = {"regime": "transition", "probabilities": {}, "score": 0.0}
        else:
            self._regime = {"regime": "transition", "probabilities": {}, "score": 0.0}

    def snapshot(self) -> dict:
        return {
            "ok": self.ready,
            "status": self.status,
            "error": self.last_error,
            "validation": self.validation,
            "trained_at": forecasting_suite.trained_at,
            "mlflow_run_id": self.mlflow_run_id,
            "metrics": self.last_train_metrics,
            "regime": self._regime,
            "n_forecasts": 0 if self._latest_forecasts is None else len(self._latest_forecasts),
            "as_of": datetime.now(timezone.utc).isoformat(),
        }

    def forecasts(self, symbols: list[str] | None = None, horizon: int = 21) -> list[dict]:
        if self._latest_forecasts is None:
            return []
        df = self._latest_forecasts
        if symbols:
            df = df[df["symbol"].isin([s.upper() for s in symbols])]
        key = f"pred_ret_{horizon}d"
        alt = [c for c in df.columns if c.startswith("pred_ret_")]
        out = []
        for _, r in df.iterrows():
            pred = float(r[key]) if key in df.columns else (float(r[alt[0]]) if alt else 0.0)
            meta = meta_for(r["symbol"])
            out.append(
                {
                    "symbol": r["symbol"],
                    "name": meta["name"],
                    "sector": meta["sector"],
                    "date": r["date"],
                    "close": r["close"],
                    "horizon_days": horizon,
                    "predicted_return": round(pred, 6),
                    "predicted_return_annualized": round(pred * (252 / horizon), 6),
                    "predicted_volatility": round(float(r["pred_vol"]), 6),
                    "rsi_14": round(float(r["rsi_14"]), 2),
                    "macd": round(float(r["macd"]), 4),
                    "momentum_21d": round(float(r["mom_21"]), 4),
                }
            )
        out.sort(key=lambda x: abs(x["predicted_return"]), reverse=True)
        return out

    def regime(self) -> dict:
        return self._regime or {"regime": "unknown", "probabilities": {}, "score": 0.0}

    def predicted_mu_cov(
        self, symbols: list[str], horizon: int = 21
    ) -> tuple[list[str], np.ndarray, np.ndarray, dict]:
        """Build annualized expected returns + blended covariance for optimizer."""
        panel = ingestor.get_panel()
        closes = ingestor.pivot_closes(symbols)
        rets = closes.pct_change().dropna(how="all")
        cov, cov_syms = estimate_covariance(rets[[s for s in symbols if s in rets.columns]].dropna(how="any"))

        if self._latest_forecasts is None:
            self._refresh_forecasts_unlocked(panel)
        assert self._latest_forecasts is not None

        key = f"pred_ret_{horizon}d"
        pred_map = {}
        vol_map = {}
        for _, r in self._latest_forecasts.iterrows():
            if key in self._latest_forecasts.columns:
                pred_map[r["symbol"]] = float(r[key]) * (252 / horizon)
            vol_map[r["symbol"]] = float(r["pred_vol"])

        # Fallback to historical mean if prediction missing
        hist_mu = rets.mean() * 252
        mu = np.array([pred_map.get(s, float(hist_mu.get(s, 0.0))) for s in cov_syms])
        cov = blend_predicted_vols(cov, cov_syms, vol_map)

        # Regime-conditioned risk adjustment
        regime = self.regime()
        if regime.get("regime") == "risk_off":
            cov = cov * 1.25
            mu = mu * 0.7
        elif regime.get("regime") == "risk_on":
            cov = cov * 0.9

        meta = {
            "horizon": horizon,
            "regime": regime,
            "source": "ml_predicted_returns + ledoit_wolf_cov",
        }
        return cov_syms, mu, cov, meta

    def backtest(
        self,
        horizon: int = 21,
        commission_bps: float = 5.0,
        slippage_bps: float = 5.0,
    ) -> dict:
        if not forecasting_suite.return_models:
            raise RuntimeError("Models not trained")
        from app.ds.backtest import run_validation_suite

        panel = ingestor.get_panel()
        return run_validation_suite(
            panel,
            return_models=forecasting_suite.return_models,
            vol_model=forecasting_suite.vol_model,
            regime_predict=forecasting_suite.predict_regime,
            horizon=horizon,
            commission_bps=commission_bps,
            slippage_bps=slippage_bps,
        )

    def stress_test(
        self,
        symbols: list[str],
        weights: list[float],
        scenarios: list[dict] | None = None,
    ) -> dict:
        """Multi-scenario stress tests beyond a single shock."""
        w = np.array(weights, dtype=float)
        w = w / w.sum()
        closes = ingestor.pivot_closes(symbols)
        rets = closes.pct_change().dropna()
        aligned = [s for s in symbols if s in rets.columns]
        if len(aligned) != len(symbols):
            # remap
            idx = [i for i, s in enumerate(symbols) if s in rets.columns]
            w = w[idx]
            w = w / w.sum()
            symbols = aligned

        hist = rets[symbols]
        scenarios = scenarios or [
            {"name": "market_crash_-10%", "type": "uniform", "shock": -0.10},
            {"name": "tech_selloff_-15%", "type": "sector", "sector": "Technology", "shock": -0.15},
            {"name": "rate_spike", "type": "custom", "shocks": {"JPM": -0.08, "MS": -0.08, "GS": -0.08, "TLT": -0.12}},
            {"name": "vol_of_vol", "type": "historical_percentile", "percentile": 1},
            {"name": "covid_like_-20%", "type": "uniform", "shock": -0.20},
        ]

        results = []
        for sc in scenarios:
            shocks = np.zeros(len(symbols))
            if sc["type"] == "uniform":
                shocks[:] = sc["shock"]
            elif sc["type"] == "sector":
                for i, s in enumerate(symbols):
                    if meta_for(s)["sector"] == sc.get("sector"):
                        shocks[i] = sc["shock"]
            elif sc["type"] == "custom":
                mapping = sc.get("shocks", {})
                for i, s in enumerate(symbols):
                    shocks[i] = float(mapping.get(s, 0.0))
            elif sc["type"] == "historical_percentile":
                # apply simultaneous historical worst-day scaled move
                port_hist = hist.values @ w
                q = np.percentile(port_hist, sc.get("percentile", 1))
                # approximate via equal shock to match portfolio q
                shocks[:] = q
            pnl = float(w @ shocks)
            contrib = [
                {"symbol": symbols[i], "weight": round(float(w[i]), 4), "shock_pct": round(float(shocks[i] * 100), 3), "contribution_pct": round(float(w[i] * shocks[i] * 100), 3)}
                for i in range(len(symbols))
            ]
            results.append({"name": sc["name"], "pnl_pct": round(pnl * 100, 3), "contributions": contrib})

        return {
            "as_of": datetime.now(timezone.utc).isoformat(),
            "scenarios": results,
            "worst_scenario": min(results, key=lambda x: x["pnl_pct"])["name"] if results else None,
        }


pipeline = DSPipeline()
