"""Market data facade over real historical OHLCV + optional replay stream."""

from __future__ import annotations

import math
from datetime import datetime, timezone
from threading import Lock

import pandas as pd

from app.core.config import get_settings
from app.ds.ingest import ingestor
from app.ds.universe import UNIVERSE_META, list_universe, meta_for
from app.schemas import Candle, IndicatorSnapshot, Quote


class MarketDataService:
    """Serves quotes/candles from real Yahoo-sourced history with optional day-by-day replay."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._replay_idx: int | None = None
        self._dates: list[pd.Timestamp] = []
        self._ready = False

    def bootstrap(self) -> None:
        settings = get_settings()
        panel = ingestor.get_panel()
        self._dates = sorted(pd.to_datetime(panel["date"].unique()))
        if settings.replay_enabled and self._dates:
            # Start near the end so UI looks "live" but can advance
            self._replay_idx = max(0, len(self._dates) - 60)
        else:
            self._replay_idx = len(self._dates) - 1 if self._dates else None
        self._ready = True

    def _asof(self) -> pd.Timestamp | None:
        if not self._dates or self._replay_idx is None:
            return None
        return self._dates[min(self._replay_idx, len(self._dates) - 1)]

    def tick(self) -> None:
        """Advance historical replay by one session (simulates live stream)."""
        with self._lock:
            if not self._dates or self._replay_idx is None:
                return
            if self._replay_idx < len(self._dates) - 1:
                self._replay_idx += 1

    def list_symbols(self) -> list[dict]:
        settings = get_settings()
        return list_universe(include_index=True, limit=settings.universe_size + 10)

    def _history_to(self, symbol: str) -> pd.DataFrame:
        df = ingestor.history_for(symbol)
        asof = self._asof()
        if asof is not None:
            df = df[df["date"] <= asof]
        return df

    def get_quote(self, symbol: str) -> Quote | None:
        symbol = symbol.upper()
        hist = self._history_to(symbol)
        if len(hist) < 2:
            return None
        last = hist.iloc[-1]
        prev = hist.iloc[-2]
        meta = meta_for(symbol)
        price = float(last["close"])
        prev_c = float(prev["close"])
        change = price - prev_c
        return Quote(
            symbol=symbol,
            name=meta["name"],
            price=round(price, 2),
            change=round(change, 2),
            change_pct=round((change / prev_c) * 100, 3) if prev_c else 0.0,
            volume=int(last.get("volume") or 0),
            high=round(float(last["high"]), 2),
            low=round(float(last["low"]), 2),
            open=round(float(last["open"]), 2),
            previous_close=round(prev_c, 2),
            sector=meta["sector"],
            updated_at=datetime.now(timezone.utc),
        )

    def get_quotes(self, symbols: list[str] | None = None) -> list[Quote]:
        if symbols:
            keys = [s.upper() for s in symbols]
        else:
            keys = [x["symbol"] for x in self.list_symbols()]
        out: list[Quote] = []
        for s in keys:
            q = self.get_quote(s)
            if q:
                out.append(q)
        return out

    def get_candles(self, symbol: str, limit: int = 100) -> list[Candle]:
        hist = self._history_to(symbol.upper()).tail(limit)
        candles: list[Candle] = []
        for _, r in hist.iterrows():
            candles.append(
                Candle(
                    t=pd.Timestamp(r["date"]).to_pydatetime().replace(tzinfo=timezone.utc),
                    o=round(float(r["open"]), 2),
                    h=round(float(r["high"]), 2),
                    l=round(float(r["low"]), 2),
                    c=round(float(r["close"]), 2),
                    v=int(r.get("volume") or 0),
                )
            )
        return candles

    def get_returns_matrix(self, symbols: list[str], lookback: int = 60) -> tuple[list[str], list[list[float]]]:
        closes = {}
        for s in symbols:
            hist = self._history_to(s.upper()).tail(lookback + 1)
            if len(hist) > 10:
                closes[s.upper()] = hist["close"].astype(float).tolist()
        valid = list(closes.keys())
        if not valid:
            return [], []
        min_len = min(len(v) for v in closes.values())
        rets = []
        for s in valid:
            series = closes[s][-min_len:]
            r = [(series[i] / series[i - 1] - 1) for i in range(1, len(series))]
            rets.append(r)
        matrix = [list(row) for row in zip(*rets)]
        return valid, matrix

    def indicators(self, symbol: str) -> IndicatorSnapshot | None:
        candles = self.get_candles(symbol, 120)
        if len(candles) < 30:
            return None
        closes = [c.c for c in candles]

        def sma(n: int) -> float:
            return sum(closes[-n:]) / n

        def ema(n: int) -> float:
            k = 2 / (n + 1)
            val = closes[0]
            for p in closes[1:]:
                val = p * k + val * (1 - k)
            return val

        gains, losses = [], []
        for i in range(1, len(closes)):
            d = closes[i] - closes[i - 1]
            gains.append(max(d, 0))
            losses.append(max(-d, 0))
        avg_gain = sum(gains[-14:]) / 14
        avg_loss = sum(losses[-14:]) / 14 or 1e-9
        rsi = 100 - (100 / (1 + avg_gain / avg_loss))
        ema12, ema26 = ema(12), ema(26)
        macd = ema12 - ema26
        macd_series = []
        for i in range(26, len(closes)):
            window = closes[: i + 1]
            e12 = e26 = window[0]
            k12, k26 = 2 / 13, 2 / 27
            for p in window[1:]:
                e12 = p * k12 + e12 * (1 - k12)
                e26 = p * k26 + e26 * (1 - k26)
            macd_series.append(e12 - e26)
        macd_signal = sum(macd_series[-9:]) / min(9, len(macd_series)) if macd_series else macd
        rets = [(closes[i] / closes[i - 1] - 1) for i in range(1, len(closes))]
        mean_r = sum(rets[-20:]) / 20
        var = sum((r - mean_r) ** 2 for r in rets[-20:]) / max(1, min(19, len(rets[-20:]) - 1))
        vol = math.sqrt(var) * math.sqrt(252)
        momentum = (closes[-1] / closes[-20] - 1) * 100 if len(closes) >= 20 else 0
        return IndicatorSnapshot(
            symbol=symbol.upper(),
            rsi=round(rsi, 2),
            sma_20=round(sma(20), 2),
            sma_50=round(sma(min(50, len(closes))), 2),
            ema_12=round(ema12, 2),
            macd=round(macd, 4),
            macd_signal=round(macd_signal, 4),
            volatility=round(vol, 4),
            momentum=round(momentum, 3),
        )

    def replay_position(self) -> dict:
        asof = self._asof()
        return {
            "index": self._replay_idx,
            "n_dates": len(self._dates),
            "asof": str(asof.date()) if asof is not None else None,
            "at_live_edge": self._replay_idx == len(self._dates) - 1 if self._dates else False,
        }


market_data = MarketDataService()
