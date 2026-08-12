"""Portfolio / decision optimization fed by ML-predicted returns + risk."""

from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
from scipy.optimize import minimize

from app.ds.pipeline import pipeline
from app.schemas import (
    Allocation,
    OptimizeRequest,
    OptimizeResult,
    ScenarioRequest,
    ScenarioResult,
)
from app.services.market_data import market_data


class OptimizerService:
    def _stats(self, symbols: list[str], horizon: int = 21) -> tuple[list[str], np.ndarray, np.ndarray, dict]:
        if pipeline.ready:
            try:
                return pipeline.predicted_mu_cov(symbols, horizon=horizon)
            except Exception:
                pass
        # Fallback: historical stats from real data
        valid, matrix = market_data.get_returns_matrix(symbols, lookback=126)
        if len(valid) < 2 or not matrix:
            raise ValueError("Insufficient return history for optimization")
        arr = np.array(matrix)
        mu = arr.mean(axis=0) * 252
        cov = np.cov(arr, rowvar=False) * 252 + np.eye(len(valid)) * 1e-8
        return valid, mu, cov, {"source": "historical_fallback", "horizon": horizon}

    def optimize(self, req: OptimizeRequest) -> OptimizeResult:
        horizon = getattr(req, "forecast_horizon", 21) or 21
        symbols, mu, cov, meta = self._stats(req.symbols, horizon=horizon)
        n = len(symbols)

        def port_return(w: np.ndarray) -> float:
            return float(w @ mu)

        def port_vol(w: np.ndarray) -> float:
            return float(np.sqrt(w @ cov @ w))

        bounds = [(req.min_weight, req.max_weight)] * n
        cons = [{"type": "eq", "fun": lambda w: np.sum(w) - 1.0}]

        if req.objective == "max_sharpe":

            def neg_sharpe(w: np.ndarray) -> float:
                vol = port_vol(w)
                if vol < 1e-12:
                    return 0.0
                return -(port_return(w) - req.risk_free_rate) / vol

            objective = neg_sharpe
        elif req.objective == "min_volatility":
            objective = port_vol
        elif req.objective == "max_return":
            if req.target_return is not None:
                cons.append({"type": "ineq", "fun": lambda w: port_return(w) - req.target_return})
            objective = lambda w: -port_return(w)
        else:

            def risk_parity(w: np.ndarray) -> float:
                vol = port_vol(w)
                mrc = cov @ w
                rc = w * mrc
                target = vol**2 / n
                return float(np.sum((rc - target) ** 2))

            objective = risk_parity

        w0 = np.array([1 / n] * n)
        result = minimize(
            objective,
            w0,
            method="SLSQP",
            bounds=bounds,
            constraints=cons,
            options={"maxiter": 400, "ftol": 1e-10},
        )
        weights = result.x if result.success else w0
        weights = np.clip(weights, 0, None)
        weights = weights / weights.sum()

        er = port_return(weights)
        vol = port_vol(weights)
        sharpe = (er - req.risk_free_rate) / vol if vol > 1e-12 else 0.0
        diversification = float(1 - np.sum(weights**2))

        allocations = [
            Allocation(
                symbol=symbols[i],
                weight=round(float(weights[i]), 4),
                amount=round(float(weights[i]) * req.capital, 2),
                expected_return=round(float(mu[i]), 4),
                volatility=round(float(np.sqrt(cov[i, i])), 4),
            )
            for i in range(n)
            if weights[i] > 1e-4
        ]
        allocations.sort(key=lambda a: a.weight, reverse=True)
        frontier = self._efficient_frontier(mu, cov, req.min_weight, req.max_weight)

        constraints = {
            "capital": req.capital,
            "max_weight": req.max_weight,
            "min_weight": req.min_weight,
            "risk_free_rate": req.risk_free_rate,
            "symbols": symbols,
            "forecast_meta": meta,
        }

        return OptimizeResult(
            name=req.name,
            objective=req.objective,
            allocations=allocations,
            expected_return=round(er, 4),
            volatility=round(vol, 4),
            sharpe=round(sharpe, 4),
            diversification_score=round(diversification, 4),
            efficient_frontier=frontier,
            constraints=constraints,
            created_at=datetime.now(timezone.utc),
        )

    def _efficient_frontier(
        self, mu: np.ndarray, cov: np.ndarray, min_w: float, max_w: float, points: int = 12
    ) -> list[dict[str, float]]:
        n = len(mu)
        targets = np.linspace(float(mu.min()), float(mu.max()), points)
        out: list[dict[str, float]] = []
        for target in targets:
            cons = [
                {"type": "eq", "fun": lambda w: np.sum(w) - 1.0},
                {"type": "eq", "fun": lambda w, t=target: float(w @ mu) - t},
            ]
            res = minimize(
                lambda w: float(np.sqrt(w @ cov @ w)),
                np.array([1 / n] * n),
                method="SLSQP",
                bounds=[(min_w, max_w)] * n,
                constraints=cons,
                options={"maxiter": 200},
            )
            if res.success:
                w = res.x
                out.append(
                    {
                        "return": round(float(w @ mu), 4),
                        "volatility": round(float(np.sqrt(w @ cov @ w)), 4),
                    }
                )
        return out

    def scenario(self, req: ScenarioRequest) -> ScenarioResult:
        if len(req.symbols) != len(req.weights):
            raise ValueError("symbols and weights length mismatch")
        weights = np.array(req.weights, dtype=float)
        if abs(weights.sum() - 1.0) > 0.05:
            weights = weights / weights.sum()

        # Prefer multi-scenario engine; also return single-shock compatible result
        stress = pipeline.stress_test(req.symbols, weights.tolist()) if pipeline.ready else None
        quotes = {q.symbol: q.price for q in market_data.get_quotes(req.symbols)}
        shocked = set(s.upper() for s in (req.shocked_symbols or req.symbols))
        base = 1.0
        shocked_val = 0.0
        contributions = []
        for sym, w in zip(req.symbols, weights):
            price = quotes.get(sym.upper(), 100.0)
            shock = req.shock_pct if sym.upper() in shocked else 0.0
            new_price = price * (1 + shock)
            contrib = float(w * shock)
            shocked_val += float(w) * (new_price / price)
            contributions.append(
                {
                    "symbol": sym.upper(),
                    "weight": round(float(w), 4),
                    "shock_pct": round(shock * 100, 2),
                    "contribution_pct": round(contrib * 100, 3),
                }
            )
        pnl = shocked_val - base
        result = ScenarioResult(
            base_value=1.0,
            shocked_value=round(shocked_val, 6),
            pnl=round(pnl, 6),
            pnl_pct=round(pnl * 100, 3),
            contributions=contributions,
        )
        # Attach stress suite in a non-breaking way via contributions note is awkward;
        # API /ds/stress exposes full suite. Keep scenario contract stable.
        _ = stress
        return result


optimizer = OptimizerService()
