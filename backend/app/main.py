import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select

from app.api import auth, decisions, ds, intelligence, market, workspace
from app.core.config import get_settings
from app.core.security import hash_password
from app.db.session import AsyncSessionLocal, Base, engine
from app.ds.pipeline import pipeline
from app.models import User
from app.services.market_data import market_data

settings = get_settings()


async def _tick_loop(stop: asyncio.Event) -> None:
    while not stop.is_set():
        market_data.tick()
        try:
            await asyncio.wait_for(stop.wait(), timeout=settings.market_tick_seconds)
        except asyncio.TimeoutError:
            continue


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with AsyncSessionLocal() as db:
        result = await db.execute(select(User).where(User.email == settings.default_admin_email))
        if not result.scalar_one_or_none():
            db.add(
                User(
                    email=settings.default_admin_email,
                    full_name="Platform Admin",
                    hashed_password=hash_password(settings.default_admin_password),
                    role="admin",
                )
            )
            await db.commit()

    # Bootstrap real-data DS pipeline in a worker thread (download + train can be slow)
    def _boot():
        try:
            pipeline.bootstrap(force_refresh=False, train=True)
            market_data.bootstrap()
        except Exception as exc:  # noqa: BLE001
            print(f"[DMIDOP] pipeline bootstrap warning: {exc}")

    loop = asyncio.get_event_loop()
    boot_task = loop.run_in_executor(None, _boot)

    stop = asyncio.Event()
    tick_task = asyncio.create_task(_tick_loop(stop))
    yield
    stop.set()
    await tick_task
    await boot_task


app = FastAPI(
    title="Dynamic Market Intelligence & Decision Optimization Platform",
    description=(
        "Uses historical market data to estimate future returns/risk and convert those "
        "predictions into portfolio decisions under probabilistic market regimes."
    ),
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

prefix = settings.api_prefix
app.include_router(auth.router, prefix=prefix)
app.include_router(market.router, prefix=prefix)
app.include_router(intelligence.router, prefix=prefix)
app.include_router(decisions.router, prefix=prefix)
app.include_router(workspace.router, prefix=prefix)
app.include_router(ds.router, prefix=prefix)


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "service": settings.app_name,
        "env": settings.app_env,
        "ds_status": pipeline.status,
        "ds_ready": pipeline.ready,
    }
