from fastapi import APIRouter, HTTPException, Query

from app.schemas import Candle, IndicatorSnapshot, Quote
from app.services.market_data import market_data

router = APIRouter(prefix="/market", tags=["market"])


@router.get("/symbols")
async def list_symbols():
    return market_data.list_symbols()


@router.get("/quotes", response_model=list[Quote])
async def quotes(symbols: str | None = Query(None, description="Comma-separated symbols")):
    syms = [s.strip() for s in symbols.split(",") if s.strip()] if symbols else None
    return market_data.get_quotes(syms)


@router.get("/quotes/{symbol}", response_model=Quote)
async def quote(symbol: str):
    q = market_data.get_quote(symbol)
    if not q:
        raise HTTPException(404, "Symbol not found")
    return q


@router.get("/candles/{symbol}", response_model=list[Candle])
async def candles(symbol: str, limit: int = Query(100, ge=10, le=300)):
    data = market_data.get_candles(symbol, limit)
    if not data:
        raise HTTPException(404, "Symbol not found")
    return data


@router.get("/indicators/{symbol}", response_model=IndicatorSnapshot)
async def indicators(symbol: str):
    ind = market_data.indicators(symbol)
    if not ind:
        raise HTTPException(404, "Insufficient data")
    return ind
