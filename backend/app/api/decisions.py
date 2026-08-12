from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user
from app.db.session import get_db
from app.models import DecisionRun, User
from app.schemas import DecisionOut, OptimizeRequest, OptimizeResult, ScenarioRequest, ScenarioResult
from app.services.optimizer import optimizer

router = APIRouter(prefix="/decisions", tags=["decisions"])


@router.post("/optimize", response_model=OptimizeResult)
async def optimize(
    payload: OptimizeRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        result = optimizer.optimize(payload)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc

    run = DecisionRun(
        user_id=user.id,
        name=payload.name,
        objective=payload.objective,
        symbols=payload.symbols,
        constraints=result.constraints,
        result=result.model_dump(mode="json"),
        notes=payload.notes,
    )
    db.add(run)
    await db.commit()
    await db.refresh(run)
    result.id = run.id
    return result


@router.post("/scenario", response_model=ScenarioResult)
async def scenario(payload: ScenarioRequest, user: User = Depends(get_current_user)):
    _ = user
    try:
        return optimizer.scenario(payload)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get("/history", response_model=list[DecisionOut])
async def history(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(DecisionRun).where(DecisionRun.user_id == user.id).order_by(DecisionRun.created_at.desc())
    )
    return result.scalars().all()


@router.get("/history/{run_id}", response_model=DecisionOut)
async def history_item(
    run_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(DecisionRun).where(DecisionRun.id == run_id, DecisionRun.user_id == user.id)
    )
    run = result.scalar_one_or_none()
    if not run:
        raise HTTPException(404, "Decision run not found")
    return run
