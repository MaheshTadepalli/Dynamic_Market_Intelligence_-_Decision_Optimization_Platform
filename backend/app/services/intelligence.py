"""Market intelligence: technical signals + ML forecasts + probabilistic regimes."""

from __future__ import annotations

from datetime import datetime, timezone

from app.ds.pipeline import pipeline
from app.ds.universe import meta_for
from app.schemas import IntelligenceSignal, MarketOverview, Quote
from app.services.market_data import market_data


class IntelligenceService:
    def overview(self) -> MarketOverview:
        indices = market_data.get_quotes(["SPY", "QQQ", "IWM"])
        all_q = [q for q in market_data.get_quotes() if q.sector != "Index"]
        movers = sorted(all_q, key=lambda q: abs(q.change_pct), reverse=True)[:8]
        adv = sum(1 for q in all_q if q.change_pct > 0)
        dec = sum(1 for q in all_q if q.change_pct < 0)
        flat = len(all_q) - adv - dec
        avg = sum(q.change_pct for q in all_q) / len(all_q) if all_q else 0

        regime_info = pipeline.regime()
        regime_key = regime_info.get("regime", "transition")
        regime_labels = {
            "risk_on": "Risk-On Expansion",
            "risk_off": "Risk-Off Contraction",
            "transition": "Range-Bound / Transition",
        }
        return MarketOverview(
            as_of=datetime.now(timezone.utc),
            indices=indices,
            movers=movers,
            breadth={"advancers": adv, "decliners": dec, "unchanged": flat, "avg_change_pct": round(avg, 3)},
            regime=regime_labels.get(regime_key, regime_key),
            regime_score=round(float(regime_info.get("score", 0.0)), 3),
        )

    def signal_for(self, symbol: str) -> IntelligenceSignal | None:
        quote = market_data.get_quote(symbol)
        ind = market_data.indicators(symbol)
        if not quote or not ind:
            return None

        score = 0.0
        drivers: list[str] = []

        # Technical layer (kept)
        if ind.rsi < 30:
            score += 1.0
            drivers.append(f"RSI oversold at {ind.rsi:.1f}")
        elif ind.rsi > 70:
            score -= 1.0
            drivers.append(f"RSI overbought at {ind.rsi:.1f}")
        else:
            drivers.append(f"RSI neutral at {ind.rsi:.1f}")

        if ind.macd > ind.macd_signal:
            score += 0.7
            drivers.append("MACD above signal")
        else:
            score -= 0.7
            drivers.append("MACD below signal")

        if quote.price > ind.sma_20 > ind.sma_50:
            score += 0.8
            drivers.append("Price above SMA stack")
        elif quote.price < ind.sma_20 < ind.sma_50:
            score -= 0.8
            drivers.append("Price below SMA stack")

        # ML forecast layer
        forecasts = pipeline.forecasts([symbol], horizon=21)
        if forecasts:
            pred = forecasts[0]["predicted_return"]
            pred_ann = forecasts[0]["predicted_return_annualized"]
            if pred > 0.01:
                score += 1.2
                drivers.append(f"ML 21d forecast +{pred:.2%} (ann {pred_ann:.1%})")
            elif pred < -0.01:
                score -= 1.2
                drivers.append(f"ML 21d forecast {pred:.2%} (ann {pred_ann:.1%})")
            else:
                drivers.append(f"ML 21d forecast flat ({pred:.2%})")

        regime = pipeline.regime()
        if regime.get("regime") == "risk_off":
            score -= 0.4
            drivers.append("Regime: risk-off (probabilistic GMM)")
        elif regime.get("regime") == "risk_on":
            score += 0.4
            drivers.append("Regime: risk-on (probabilistic GMM)")

        if ind.volatility > 0.45:
            risk = "high"
            score *= 0.85
        elif ind.volatility > 0.28:
            risk = "medium"
        else:
            risk = "low"

        if score >= 1.0:
            signal = "bullish"
        elif score <= -1.0:
            signal = "bearish"
        else:
            signal = "neutral"

        confidence = min(0.95, 0.45 + abs(score) / 5)
        summaries = {
            "bullish": f"{symbol}: technicals + ML forecast support upside under current regime.",
            "bearish": f"{symbol}: technicals + ML forecast point to downside / de-risking.",
            "neutral": f"{symbol}: mixed technical/ML evidence — size conservatively.",
        }
        return IntelligenceSignal(
            symbol=symbol.upper(),
            signal=signal,  # type: ignore[arg-type]
            confidence=round(confidence, 3),
            score=round(score, 3),
            drivers=drivers[:6],
            risk_level=risk,  # type: ignore[arg-type]
            horizon="21d forecast",
            summary=summaries[signal],
            updated_at=datetime.now(timezone.utc),
        )

    def signals(self, symbols: list[str] | None = None) -> list[IntelligenceSignal]:
        if symbols is None:
            # Prefer top absolute ML forecasts for ranking
            fc = pipeline.forecasts(horizon=21)
            symbols = [f["symbol"] for f in fc if meta_for(f["symbol"])["sector"] != "Index"][:40]
            if not symbols:
                symbols = [s["symbol"] for s in market_data.list_symbols() if s["sector"] != "Index"][:40]
        out: list[IntelligenceSignal] = []
        for s in symbols:
            sig = self.signal_for(s)
            if sig:
                out.append(sig)
        return sorted(out, key=lambda x: abs(x.score), reverse=True)

    def sector_heatmap(self) -> list[dict]:
        quotes = [q for q in market_data.get_quotes() if q.sector != "Index"]
        buckets: dict[str, list[Quote]] = {}
        for q in quotes:
            buckets.setdefault(q.sector, []).append(q)
        rows = []
        for sector, items in sorted(buckets.items()):
            avg = sum(i.change_pct for i in items) / len(items)
            rows.append(
                {
                    "sector": sector,
                    "change_pct": round(avg, 3),
                    "leaders": sorted(items, key=lambda x: x.change_pct, reverse=True)[:2],
                    "count": len(items),
                }
            )
        return rows


intelligence = IntelligenceService()
