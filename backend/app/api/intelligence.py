from fastapi import APIRouter, HTTPException, Query

from app.schemas import IntelligenceSignal, MarketOverview
from app.services.intelligence import intelligence

router = APIRouter(prefix="/intelligence", tags=["intelligence"])


@router.get("/overview", response_model=MarketOverview)
async def overview():
    return intelligence.overview()


@router.get("/signals", response_model=list[IntelligenceSignal])
async def signals(symbols: str | None = Query(None)):
    syms = [s.strip() for s in symbols.split(",") if s.strip()] if symbols else None
    return intelligence.signals(syms)


@router.get("/signals/{symbol}", response_model=IntelligenceSignal)
async def signal(symbol: str):
    sig = intelligence.signal_for(symbol)
    if not sig:
        raise HTTPException(404, "Signal unavailable")
    return sig


@router.get("/sectors")
async def sectors():
    return intelligence.sector_heatmap()
