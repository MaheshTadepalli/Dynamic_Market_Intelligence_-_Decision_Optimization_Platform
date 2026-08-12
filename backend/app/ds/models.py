"""Return, volatility, and regime forecasting models."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.mixture import GaussianMixture
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from app.core.config import get_settings
from app.ds.evaluation import evaluate_predictions
from app.ds.features import FEATURE_COLS, build_panel_features
from app.ds.validation import time_split_indices


@dataclass
class ModelMetrics:
    horizon: int | None
    model_type: str
    mae: float
    rmse: float
    r2: float
    n_train: int
    n_test: int
    extras: dict

    def to_dict(self) -> dict:
        return {
            "horizon": self.horizon,
            "model_type": self.model_type,
            "mae": self.mae,
            "rmse": self.rmse,
            "r2": self.r2,
            "n_train": self.n_train,
            "n_test": self.n_test,
            "extras": self.extras,
        }


class ForecastingSuite:
    """Multi-horizon return forecasts + vol forecasts + probabilistic regimes."""

    def __init__(self) -> None:
        settings = get_settings()
        self.horizons = settings.horizon_list
        self.models_dir = Path(settings.models_dir)
        self.models_dir.mkdir(parents=True, exist_ok=True)
        self.return_models: dict[int, Pipeline] = {}
        self.vol_model: Pipeline | None = None
        self.regime_model: GaussianMixture | None = None
        self.metrics: list[ModelMetrics] = []
        self.trained_at: str | None = None
        self.feature_cols = FEATURE_COLS

    def _xy(self, panel_feat: pd.DataFrame, target: str) -> tuple[pd.DataFrame, pd.Series, pd.DataFrame]:
        cols = self.feature_cols + [target, "date", "symbol"]
        data = panel_feat[cols].dropna().sort_values("date")
        X = data[self.feature_cols]
        y = data[target]
        meta = data[["date", "symbol"]]
        return X, y, meta

    def train(self, panel: pd.DataFrame) -> list[dict]:
        feat = build_panel_features(panel, self.horizons)
        self.metrics = []

        # --- Return models per horizon ---
        for h in self.horizons:
            target = f"target_ret_{h}"
            X, y, meta = self._xy(feat, target)
            if len(X) < 500:
                continue
            # Chronological split by date (global time order)
            order = meta["date"].argsort()
            X = X.iloc[order].reset_index(drop=True)
            y = y.iloc[order].reset_index(drop=True)
            tr, va, te = time_split_indices(len(X), 0.7, 0.15)
            # Prefer GBM for longer horizons; Ridge for 1d stability
            if h <= 1:
                model: Pipeline = Pipeline(
                    [("scaler", StandardScaler()), ("model", Ridge(alpha=2.0))]
                )
            else:
                model = Pipeline(
                    [
                        ("scaler", StandardScaler()),
                        (
                            "model",
                            GradientBoostingRegressor(
                                n_estimators=120,
                                max_depth=3,
                                learning_rate=0.05,
                                subsample=0.8,
                                random_state=42,
                            ),
                        ),
                    ]
                )
            model.fit(X.iloc[tr], y.iloc[tr])
            pred = model.predict(X.iloc[te])
            y_te = y.iloc[te]
            # residual std from validation fold for interval calibration
            pred_va = model.predict(X.iloc[va]) if len(va) else pred
            y_va = y.iloc[va] if len(va) else y_te
            resid_std = float((y_va - pred_va).std(ddof=1)) if len(va) > 5 else float((y_te - pred).std(ddof=1))
            unc = evaluate_predictions(y_te, pred, residual_std=resid_std)
            m = ModelMetrics(
                horizon=h,
                model_type=type(model.named_steps["model"]).__name__,
                mae=float(mean_absolute_error(y_te, pred)),
                rmse=float(np.sqrt(mean_squared_error(y_te, pred))),
                r2=float(r2_score(y_te, pred)),
                n_train=len(tr),
                n_test=len(te),
                extras={
                    "val_size": len(va),
                    "directional_acc": unc.get("directional_accuracy"),
                    "residual_std": unc.get("residual_std"),
                    "cover_80": unc.get("prediction_intervals", {}).get("cover_80"),
                    "cover_95": unc.get("prediction_intervals", {}).get("cover_95"),
                    "calibration_bins": unc.get("calibration_bins", [])[:5],
                },
            )
            self.return_models[h] = model
            self.metrics.append(m)
            joblib.dump(model, self.models_dir / f"return_h{h}.joblib")

        # --- Volatility model: predict next-day realized vol proxy ---
        vol_df = feat.copy()
        vol_df["target_vol_21"] = vol_df.groupby("symbol")["ret_1"].transform(
            lambda s: s.rolling(21).std().shift(-1)
        )
        Xv, yv, metav = self._xy(vol_df.rename(columns={"target_vol_21": "target_vol_21"}), "target_vol_21")
        # rebuild with correct target name present
        cols = self.feature_cols + ["target_vol_21", "date", "symbol"]
        data = vol_df[cols].dropna().sort_values("date")
        Xv = data[self.feature_cols]
        yv = data["target_vol_21"]
        if len(Xv) >= 500:
            tr, va, te = time_split_indices(len(Xv), 0.7, 0.15)
            vol_model = Pipeline(
                [
                    ("scaler", StandardScaler()),
                    ("model", GradientBoostingRegressor(n_estimators=80, max_depth=2, random_state=42)),
                ]
            )
            vol_model.fit(Xv.iloc[tr], yv.iloc[tr])
            pred = vol_model.predict(Xv.iloc[te])
            self.vol_model = vol_model
            vol_unc = evaluate_predictions(yv.iloc[te], pred)
            self.metrics.append(
                ModelMetrics(
                    horizon=None,
                    model_type="VolGBM",
                    mae=float(mean_absolute_error(yv.iloc[te], pred)),
                    rmse=float(np.sqrt(mean_squared_error(yv.iloc[te], pred))),
                    r2=float(r2_score(yv.iloc[te], pred)),
                    n_train=len(tr),
                    n_test=len(te),
                    extras={
                        "cover_80": vol_unc.get("prediction_intervals", {}).get("cover_80"),
                        "cover_95": vol_unc.get("prediction_intervals", {}).get("cover_95"),
                        "residual_std": vol_unc.get("residual_std"),
                    },
                )
            )
            joblib.dump(vol_model, self.models_dir / "vol_model.joblib")

        # --- Regime model on market (SPY) features ---
        spy = feat[feat["symbol"] == "SPY"].dropna(subset=["ret_1", "vol_21", "mom_21"]).copy()
        if len(spy) >= 300:
            regime_X = spy[["ret_21", "vol_21", "mom_21", "rsi_14"]].replace([np.inf, -np.inf], np.nan).dropna()
            gmm = GaussianMixture(n_components=3, covariance_type="full", random_state=42)
            gmm.fit(regime_X.values)
            self.regime_model = gmm
            labels = gmm.predict(regime_X.values)
            # Map components by mean return: low/mid/high
            means = {k: float(regime_X.iloc[labels == k]["ret_21"].mean()) for k in range(3)}
            order = sorted(means, key=means.get)
            self.regime_label_map = {
                order[0]: "risk_off",
                order[1]: "transition",
                order[2]: "risk_on",
            }
            joblib.dump(
                {"model": gmm, "label_map": self.regime_label_map, "cols": ["ret_21", "vol_21", "mom_21", "rsi_14"]},
                self.models_dir / "regime_gmm.joblib",
            )
            self.metrics.append(
                ModelMetrics(
                    horizon=None,
                    model_type="RegimeGMM",
                    mae=0.0,
                    rmse=0.0,
                    r2=0.0,
                    n_train=len(regime_X),
                    n_test=0,
                    extras={
                        "components": 3,
                        "label_map": self.regime_label_map,
                        "bic": float(gmm.bic(regime_X.values)),
                        "aic": float(gmm.aic(regime_X.values)),
                    },
                )
            )
        else:
            self.regime_label_map = {0: "risk_off", 1: "transition", 2: "risk_on"}

        self.trained_at = datetime.now(timezone.utc).isoformat()
        (self.models_dir / "metrics.json").write_text(
            json.dumps({"trained_at": self.trained_at, "metrics": [m.to_dict() for m in self.metrics]}, indent=2)
        )
        return [m.to_dict() for m in self.metrics]

    def load(self) -> bool:
        loaded = False
        for h in self.horizons:
            path = self.models_dir / f"return_h{h}.joblib"
            if path.exists():
                self.return_models[h] = joblib.load(path)
                loaded = True
        vol_path = self.models_dir / "vol_model.joblib"
        if vol_path.exists():
            self.vol_model = joblib.load(vol_path)
            loaded = True
        reg_path = self.models_dir / "regime_gmm.joblib"
        if reg_path.exists():
            blob = joblib.load(reg_path)
            self.regime_model = blob["model"]
            self.regime_label_map = blob["label_map"]
            loaded = True
        else:
            self.regime_label_map = {0: "risk_off", 1: "transition", 2: "risk_on"}
        metrics_path = self.models_dir / "metrics.json"
        if metrics_path.exists():
            blob = json.loads(metrics_path.read_text())
            self.trained_at = blob.get("trained_at")
            self.metrics = [
                ModelMetrics(
                    horizon=m.get("horizon"),
                    model_type=m["model_type"],
                    mae=m["mae"],
                    rmse=m["rmse"],
                    r2=m["r2"],
                    n_train=m["n_train"],
                    n_test=m["n_test"],
                    extras=m.get("extras", {}),
                )
                for m in blob.get("metrics", [])
            ]
        return loaded

    def predict_returns(self, feature_rows: pd.DataFrame, horizon: int = 21) -> pd.Series:
        model = self.return_models.get(horizon) or self.return_models.get(min(self.return_models))
        if model is None:
            raise RuntimeError("Return models not trained")
        X = feature_rows[self.feature_cols]
        return pd.Series(model.predict(X), index=feature_rows.index)

    def predict_vol(self, feature_rows: pd.DataFrame) -> pd.Series:
        if self.vol_model is None:
            # fallback: use vol_21 feature annualized proxy
            return feature_rows["vol_21"].fillna(feature_rows["vol_21"].median())
        return pd.Series(self.vol_model.predict(feature_rows[self.feature_cols]), index=feature_rows.index)

    def predict_regime(self, spy_features: pd.Series | dict) -> dict:
        if self.regime_model is None:
            return {
                "regime": "transition",
                "probabilities": {"risk_off": 0.33, "transition": 0.34, "risk_on": 0.33},
                "score": 0.0,
            }
        cols = ["ret_21", "vol_21", "mom_21", "rsi_14"]
        x = np.array([[float(spy_features[c]) for c in cols]])
        proba = self.regime_model.predict_proba(x)[0]
        label_map = getattr(self, "regime_label_map", {0: "risk_off", 1: "transition", 2: "risk_on"})
        probs = {label_map[i]: float(proba[i]) for i in range(len(proba))}
        regime = max(probs, key=probs.get)
        score = probs.get("risk_on", 0) - probs.get("risk_off", 0)
        return {"regime": regime, "probabilities": probs, "score": round(score, 4)}


forecasting_suite = ForecastingSuite()
