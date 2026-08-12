from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, EmailStr, Field


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    full_name: str = ""


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserOut(BaseModel):
    id: int
    email: EmailStr
    full_name: str
    role: str
    is_active: bool

    model_config = {"from_attributes": True}


class Quote(BaseModel):
    symbol: str
    name: str
    price: float
    change: float
    change_pct: float
    volume: int
    high: float
    low: float
    open: float
    previous_close: float
    sector: str
    updated_at: datetime


class Candle(BaseModel):
    t: datetime
    o: float
    h: float
    l: float
    c: float
    v: int


class IndicatorSnapshot(BaseModel):
    symbol: str
    rsi: float
    sma_20: float
    sma_50: float
    ema_12: float
    macd: float
    macd_signal: float
    volatility: float
    momentum: float


class IntelligenceSignal(BaseModel):
    symbol: str
    signal: Literal["bullish", "bearish", "neutral"]
    confidence: float
    score: float
    drivers: list[str]
    risk_level: Literal["low", "medium", "high"]
    horizon: str
    summary: str
    updated_at: datetime


class MarketOverview(BaseModel):
    as_of: datetime
    indices: list[Quote]
    movers: list[Quote]
    breadth: dict[str, float]
    regime: str
    regime_score: float


class OptimizeRequest(BaseModel):
    name: str = "Portfolio Optimization"
    symbols: list[str] = Field(min_length=2)
    objective: Literal["max_sharpe", "min_volatility", "max_return", "risk_parity"] = "max_sharpe"
    capital: float = 1_000_000
    risk_free_rate: float = 0.04
    max_weight: float = 0.35
    min_weight: float = 0.0
    target_return: float | None = None
    forecast_horizon: int = 21
    notes: str = ""


class Allocation(BaseModel):
    symbol: str
    weight: float
    amount: float
    expected_return: float
    volatility: float


class OptimizeResult(BaseModel):
    id: int | None = None
    name: str
    objective: str
    allocations: list[Allocation]
    expected_return: float
    volatility: float
    sharpe: float
    diversification_score: float
    efficient_frontier: list[dict[str, float]]
    constraints: dict[str, Any]
    created_at: datetime


class ScenarioRequest(BaseModel):
    symbols: list[str]
    weights: list[float]
    shock_pct: float = -0.1
    shocked_symbols: list[str] | None = None


class ScenarioResult(BaseModel):
    base_value: float
    shocked_value: float
    pnl: float
    pnl_pct: float
    contributions: list[dict[str, float | str]]


class WatchlistCreate(BaseModel):
    name: str
    symbols: list[str] = []


class WatchlistOut(BaseModel):
    id: int
    name: str
    symbols: list[str]
    created_at: datetime

    model_config = {"from_attributes": True}


class AlertCreate(BaseModel):
    symbol: str
    condition: Literal["above", "below", "bullish", "bearish"]
    threshold: float | None = None
    message: str = ""


class AlertOut(BaseModel):
    id: int
    symbol: str
    condition: str
    threshold: float | None
    message: str
    is_active: bool
    triggered: bool
    last_triggered_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


class DecisionOut(BaseModel):
    id: int
    name: str
    objective: str
    symbols: list
    constraints: dict
    result: dict
    notes: str
    created_at: datetime

    model_config = {"from_attributes": True}
