from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user
from app.db.session import get_db
from app.models import Alert, User, Watchlist
from app.schemas import AlertCreate, AlertOut, WatchlistCreate, WatchlistOut
from app.services.intelligence import intelligence
from app.services.market_data import market_data

router = APIRouter(tags=["workspace"])


@router.get("/watchlists", response_model=list[WatchlistOut])
async def list_watchlists(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Watchlist).where(Watchlist.user_id == user.id))
    return result.scalars().all()


@router.post("/watchlists", response_model=WatchlistOut)
async def create_watchlist(
    payload: WatchlistCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    wl = Watchlist(user_id=user.id, name=payload.name, symbols=[s.upper() for s in payload.symbols])
    db.add(wl)
    await db.commit()
    await db.refresh(wl)
    return wl


@router.delete("/watchlists/{watchlist_id}")
async def delete_watchlist(
    watchlist_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Watchlist).where(Watchlist.id == watchlist_id, Watchlist.user_id == user.id)
    )
    wl = result.scalar_one_or_none()
    if not wl:
        raise HTTPException(404, "Watchlist not found")
    await db.delete(wl)
    await db.commit()
    return {"ok": True}


@router.get("/alerts", response_model=list[AlertOut])
async def list_alerts(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Alert).where(Alert.user_id == user.id).order_by(Alert.created_at.desc()))
    return result.scalars().all()


@router.post("/alerts", response_model=AlertOut)
async def create_alert(
    payload: AlertCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    alert = Alert(
        user_id=user.id,
        symbol=payload.symbol.upper(),
        condition=payload.condition,
        threshold=payload.threshold,
        message=payload.message,
    )
    db.add(alert)
    await db.commit()
    await db.refresh(alert)
    return alert


@router.delete("/alerts/{alert_id}")
async def delete_alert(
    alert_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Alert).where(Alert.id == alert_id, Alert.user_id == user.id))
    alert = result.scalar_one_or_none()
    if not alert:
        raise HTTPException(404, "Alert not found")
    await db.delete(alert)
    await db.commit()
    return {"ok": True}


@router.post("/alerts/evaluate", response_model=list[AlertOut])
async def evaluate_alerts(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Alert).where(Alert.user_id == user.id, Alert.is_active.is_(True)))
    alerts = list(result.scalars().all())
    triggered: list[Alert] = []
    now = datetime.now(timezone.utc)
    for alert in alerts:
        fire = False
        if alert.condition in ("above", "below"):
            quote = market_data.get_quote(alert.symbol)
            if quote and alert.threshold is not None:
                if alert.condition == "above" and quote.price >= alert.threshold:
                    fire = True
                if alert.condition == "below" and quote.price <= alert.threshold:
                    fire = True
        else:
            sig = intelligence.signal_for(alert.symbol)
            if sig and sig.signal == alert.condition:
                fire = True
        if fire:
            alert.triggered = True
            alert.last_triggered_at = now
            triggered.append(alert)
    await db.commit()
    for a in triggered:
        await db.refresh(a)
    return triggered
