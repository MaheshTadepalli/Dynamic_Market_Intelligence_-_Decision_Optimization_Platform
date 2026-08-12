"""Data science pipeline API: forecasts, regime, backtest, metrics, stress."""

from fastapi import APIRouter, Depends, HTTPException, Query

from app.core.deps import get_current_user
from app.ds.pipeline import pipeline
from app.models import User
from app.services.market_data import market_data

router = APIRouter(prefix="/ds", tags=["data-science"])


@router.get("/status")
async def ds_status():
    return pipeline.snapshot()


@router.post("/bootstrap")
async def ds_bootstrap(
    force_refresh: bool = False,
    train: bool = True,
    user: User = Depends(get_current_user),
):
    _ = user
    return pipeline.bootstrap(force_refresh=force_refresh, train=train)


@router.get("/forecasts")
async def ds_forecasts(
    symbols: str | None = Query(None),
    horizon: int = Query(21, ge=1, le=63),
):
    if not pipeline.ready:
        raise HTTPException(503, "DS pipeline not ready — call POST /ds/bootstrap")
    syms = [s.strip().upper() for s in symbols.split(",") if s.strip()] if symbols else None
    return pipeline.forecasts(syms, horizon=horizon)


@router.get("/regime")
async def ds_regime():
    if not pipeline.ready:
        raise HTTPException(503, "DS pipeline not ready")
    return pipeline.regime()


@router.get("/metrics")
async def ds_metrics():
    snap = pipeline.snapshot()
    return {
        "model_metrics": snap.get("metrics", []),
        "validation": snap.get("validation"),
        "trained_at": snap.get("trained_at"),
        "mlflow_run_id": snap.get("mlflow_run_id"),
        "status": snap.get("status"),
        "replay": market_data.replay_position(),
    }


@router.post("/backtest")
async def ds_backtest(
    horizon: int = Query(21, ge=1, le=63),
    commission_bps: float = Query(5.0, ge=0, le=50),
    slippage_bps: float = Query(5.0, ge=0, le=50),
    user: User = Depends(get_current_user),
):
    _ = user
    if not pipeline.ready:
        raise HTTPException(503, "DS pipeline not ready")
    try:
        return pipeline.backtest(
            horizon=horizon,
            commission_bps=commission_bps,
            slippage_bps=slippage_bps,
        )
    except Exception as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post("/validate")
async def ds_validate(
    horizon: int = Query(21, ge=1, le=63),
    commission_bps: float = Query(5.0, ge=0, le=50),
    slippage_bps: float = Query(5.0, ge=0, le=50),
    user: User = Depends(get_current_user),
):
    """Alias for full validation suite (baselines, costs, ablations, regimes)."""
    return await ds_backtest(
        horizon=horizon,
        commission_bps=commission_bps,
        slippage_bps=slippage_bps,
        user=user,
    )


@router.post("/stress")
async def ds_stress(
    payload: dict,
    user: User = Depends(get_current_user),
):
    _ = user
    symbols = payload.get("symbols") or []
    weights = payload.get("weights") or []
    if len(symbols) < 2 or len(symbols) != len(weights):
        raise HTTPException(400, "symbols and weights required and must match")
    return pipeline.stress_test(symbols, weights, scenarios=payload.get("scenarios"))


@router.get("/validation")
async def ds_validation():
    snap = pipeline.snapshot()
    return snap.get("validation") or {"ok": False, "issues": ["not run"]}
