"""Real historical market data ingestion (Yahoo Finance) with local parquet cache."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

from app.core.config import get_settings
from app.ds.universe import UNIVERSE_META, equity_symbols, index_symbols, list_universe
from app.ds.validation import validate_ohlcv

logger = logging.getLogger(__name__)


class MarketIngestor:
    def __init__(self) -> None:
        settings = get_settings()
        self.data_dir = Path(settings.data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.cache_path = self.data_dir / "ohlcv_daily.parquet"
        self.meta_path = self.data_dir / "ingest_meta.json"
        self.lookback_years = settings.market_lookback_years
        self.universe_size = settings.universe_size
        self._panel: pd.DataFrame | None = None

    def symbols(self) -> list[str]:
        eqs = equity_symbols(limit=max(10, self.universe_size - 7))
        return eqs + index_symbols()

    def load_cached(self) -> pd.DataFrame | None:
        if self.cache_path.exists():
            df = pd.read_parquet(self.cache_path)
            df["date"] = pd.to_datetime(df["date"])
            self._panel = df
            return df
        return None

    def fetch(self, force: bool = False, symbols: list[str] | None = None) -> pd.DataFrame:
        if not force and self.cache_path.exists():
            cached = self.load_cached()
            if cached is not None and not cached.empty:
                age_days = (datetime.now(timezone.utc).date() - cached["date"].max().date()).days
                if age_days <= 1:
                    logger.info("Using fresh parquet cache (%s rows)", len(cached))
                    return cached

        try:
            import yfinance as yf
        except ImportError as exc:
            raise RuntimeError("yfinance is required for real market data") from exc

        syms = symbols or self.symbols()
        end = datetime.now(timezone.utc).date()
        start = end - timedelta(days=365 * self.lookback_years + 30)
        logger.info("Downloading %d symbols from %s to %s", len(syms), start, end)

        frames: list[pd.DataFrame] = []
        # Batch download for speed
        raw = yf.download(
            tickers=" ".join(syms),
            start=str(start),
            end=str(end + timedelta(days=1)),
            group_by="ticker",
            auto_adjust=True,
            threads=True,
            progress=False,
        )

        if isinstance(raw.columns, pd.MultiIndex):
            for sym in syms:
                if sym not in raw.columns.get_level_values(0):
                    continue
                part = raw[sym].dropna(how="all").copy()
                if part.empty:
                    continue
                part = part.reset_index()
                part.columns = [str(c).lower().replace(" ", "_") for c in part.columns]
                date_col = "date" if "date" in part.columns else part.columns[0]
                part = part.rename(columns={date_col: "date"})
                part["symbol"] = sym
                keep = [c for c in ["date", "symbol", "open", "high", "low", "close", "volume"] if c in part.columns]
                frames.append(part[keep])
        else:
            # Single ticker edge case
            part = raw.dropna(how="all").reset_index()
            part.columns = [str(c).lower().replace(" ", "_") for c in part.columns]
            date_col = "date" if "date" in part.columns else part.columns[0]
            part = part.rename(columns={date_col: "date"})
            part["symbol"] = syms[0]
            keep = [c for c in ["date", "symbol", "open", "high", "low", "close", "volume"] if c in part.columns]
            frames.append(part[keep])

        if not frames:
            cached = self.load_cached()
            if cached is not None:
                logger.warning("Download empty; falling back to cache")
                return cached
            raise RuntimeError("No market data downloaded and no cache available")

        df = pd.concat(frames, ignore_index=True)
        df["date"] = pd.to_datetime(df["date"]).dt.tz_localize(None)
        for col in ["open", "high", "low", "close", "volume"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        df = df.dropna(subset=["close"]).sort_values(["symbol", "date"]).reset_index(drop=True)

        report = validate_ohlcv(df)
        if not report.ok:
            raise RuntimeError(f"Data validation failed: {report.issues}")

        df.to_parquet(self.cache_path, index=False)
        import json

        meta = {
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "n_rows": len(df),
            "n_symbols": int(df["symbol"].nunique()),
            "date_start": str(df["date"].min().date()),
            "date_end": str(df["date"].max().date()),
            "validation": report.to_dict(),
        }
        self.meta_path.write_text(json.dumps(meta, indent=2))
        self._panel = df
        return df

    def get_panel(self, force_refresh: bool = False) -> pd.DataFrame:
        if self._panel is not None and not force_refresh:
            return self._panel
        if force_refresh or not self.cache_path.exists():
            return self.fetch(force=force_refresh)
        return self.load_cached()  # type: ignore[return-value]

    def pivot_closes(self, symbols: list[str] | None = None) -> pd.DataFrame:
        df = self.get_panel()
        if symbols:
            df = df[df["symbol"].isin([s.upper() for s in symbols])]
        wide = df.pivot(index="date", columns="symbol", values="close").sort_index()
        return wide.ffill().dropna(how="all")

    def history_for(self, symbol: str, limit: int | None = None) -> pd.DataFrame:
        df = self.get_panel()
        g = df[df["symbol"] == symbol.upper()].sort_values("date")
        return g.tail(limit) if limit else g

    def latest_quotes_frame(self) -> pd.DataFrame:
        df = self.get_panel()
        last = df.sort_values("date").groupby("symbol").tail(2)
        return last


ingestor = MarketIngestor()
