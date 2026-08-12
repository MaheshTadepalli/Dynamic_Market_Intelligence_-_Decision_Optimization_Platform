# Dynamic Market Intelligence & Decision Optimization Platform (DMIDOP)

A system that uses **historical market data** to estimate **future returns/risk** and converts those predictions into **portfolio decisions under probabilistic market regimes**.

Not a stock dashboard with ML bolted on — a full data-science decision pipeline behind a production API/UI skeleton.

## Core DS pipeline

```
REAL MARKET DATA (Yahoo Finance → parquet cache)
      ↓
Data Validation (+ leakage checks)
      ↓
Feature Engineering (technicals, returns, vol — lagged only)
      ↓
 ┌─────────────────────────┐
 │ Return Forecasting      │  Ridge / GBM · horizons 1d / 5d / 21d
 │ Volatility Forecasting  │  GBM
 │ Regime Detection        │  Gaussian Mixture (probabilistic)
 │ Risk Estimation         │  Ledoit–Wolf + predicted-vol blend
 └───────────┬─────────────┘
             ↓
      Decision Engine
             ↓
 ┌─────────────────────────┐
 │ Portfolio Allocation    │  Max Sharpe / Min Vol / … on predicted μ, Σ
 │ Risk Management         │  Regime-conditioned risk scaling
 │ Scenario / Stress Test  │  Crash, sector, rates, hist. tail
 └───────────┬─────────────┘
             ↓
        Dashboard / API
             ↓
   Performance Monitor (Lab)
   · model metrics · walk-forward backtest · MLflow
```

## Architecture

| Layer | Stack |
|-------|--------|
| Frontend | Next.js 15, TypeScript, Tailwind, Recharts |
| Backend | FastAPI, SQLAlchemy async, Pydantic |
| DS | pandas, scikit-learn, yfinance, MLflow |
| Risk / opt | NumPy, SciPy SLSQP, Ledoit–Wolf |
| Auth | JWT |
| Data store | SQLite (local) or PostgreSQL (Compose) |
| Deploy | Docker Compose |

## What changed vs v1 simulator

| Before | Now |
|--------|-----|
| Synthetic tape | Real historical OHLCV (configurable universe, e.g. 40 liquid names) |
| RSI/MACD only | Technicials **+** ML return/vol forecasts |
| Heuristic regime | Probabilistic GMM regime on SPY features |
| Hist. mean → optimizer | **Predicted μ** + shrunk **Σ** → optimizer |
| Single shock | Multi-scenario stress suite |
| 15 hardcoded names | Dynamic curated universe |
| SQLite only | Postgres in Compose; SQLite still works locally |
| Simulated ticks | Historical **replay** advancing toward live edge |
| No model lifecycle | Train metrics + **MLflow** runs + Lab UI |
| No validation | OHLCV QA + chronological splits + leakage name checks |

Causal inference is intentionally **not** included yet.

## Quick start (local)

### 1. Backend

```bash
python -m venv .venv
.\.venv\Scripts\activate          # Windows
pip install -r backend/requirements.txt
cd backend
uvicorn app.main:app --reload --port 8000
```

First boot downloads history, validates, trains models (can take a few minutes). Data caches to `backend/data/ohlcv_daily.parquet`.

- API docs: http://localhost:8000/docs  
- Health: http://localhost:8000/health  
- Lab DS routes: `/api/v1/ds/*`

Default admin: `admin@dmidop.local` / `admin123!`

### 2. Frontend

> **Windows note:** folder name contains `&`, which breaks npm shims. `package.json` scripts call Next via `node` directly.

```bash
cd frontend
npm install
npm run dev
```

App: http://localhost:3000 — open **Lab** for forecasts, regime probabilities, model metrics, backtest.

### 3. Docker Compose (API + Postgres + Web)

```bash
docker compose up --build
```

## Key API map

| Area | Endpoints |
|------|-----------|
| Market | `/api/v1/market/quotes`, `/candles/{symbol}`, `/indicators/{symbol}` |
| Intelligence | `/overview`, `/signals`, `/sectors` (technical + ML blended) |
| Decisions | `POST /decisions/optimize` (uses predicted μ/Σ), `/scenario` |
| **DS** | `GET /ds/status`, `/forecasts`, `/regime`, `/metrics` |
| **DS** | `POST /ds/bootstrap`, `/backtest`, `/stress` |

## Environment

See `.env.example`. Important DS knobs:

| Variable | Purpose |
|----------|---------|
| `DATABASE_URL` | SQLite or `postgresql+asyncpg://…` |
| `DATA_DIR` / `MODELS_DIR` | Parquet cache + joblib models |
| `MLFLOW_TRACKING_URI` | Experiment tracking root |
| `UNIVERSE_SIZE` | Equity count (plus benchmarks) |
| `FORECAST_HORIZONS` | e.g. `1,5,21` |
| `MARKET_LOOKBACK_YEARS` | History window for ingest |
| `REPLAY_ENABLED` | Advance as-of date on tick loop |

## Validation quality (Lab)

The DS Lab runs a full validation suite (`POST /api/v1/ds/backtest`):

1. **Baselines** — Buy&Hold SPY, Equal Weight, Historical Mean, Momentum, Technical
2. **Costs** — gross → commission (bps) → slippage (bps) → **net**
3. **Uncertainty** — MAE/RMSE, directional accuracy, calibration bins, 80/95% interval coverage, vol forecast error
4. **Portfolio metrics** — CAGR, Sharpe, Sortino, MDD, Calmar, turnover, vol, VaR/CVaR
5. **Ablations** — technical → +ML → +regime → +Ledoit-Wolf → +vol blend → +stress-aware
6. **Regime periods** — bull / bear / high-vol / low-vol / crash / recovery

Claim is only credible if **ML net Sharpe beats meaningful baselines after costs**.

## Walk-forward evaluation (primary benchmark)

The in-app Lab backtest is useful for exploration; the **authoritative out-of-sample test** is the standalone script:

`backend/scripts/run_walk_forward.py`

### Methodology

| Rule | Detail |
|------|--------|
| Data | Same Yahoo OHLCV parquet cache (`backend/data/ohlcv_daily.parquet`) |
| Retrain | Monthly expanding window with **21-trading-day purge** before each rebalance |
| Model | HistGradientBoosting (default) or Ridge on cross-sectional relative targets |
| Portfolio | Top-8 inverse-vol weights, **40% monthly turnover blend**, confidence gate |
| Costs | **10 bps** round-trip (5 commission + 5 slippage) on all net metrics |
| Holdout wall | Months **≥ 2025** use training frozen at **2024-12-31** — holdout rows never enter train/tune/clip |
| Audit | Writes `data/walk_forward_train_audit.csv` and asserts `HOLDOUT AUDIT OK` |

### Strategy labels (important)

- **ML (pure)** — ranking from the trained model only. This is the valid “ML beats baseline” claim.
- **Hybrid ML+Mom** (`--mom-blend 0.25`) — blends ML and momentum ranks (e.g. 75% ML + 25% momentum). Reported separately; hybrid outperformance does **not** prove the ML model alone improved.

### Run (PowerShell, from `backend/`)

```powershell
$env:DATA_DIR="./data"
$env:PYTHONWARNINGS="ignore"
..\.venv\Scripts\python scripts\run_walk_forward.py `
  --start-test 2018 --holdout-start 2025 `
  --commission-bps 5 --slippage-bps 5 `
  --top-k 8 --model hgb --blend 0.40 --min-spread 0.012
```

Optional hybrid row (separate strategy, not pure ML):

```powershell
..\.venv\Scripts\python scripts\run_walk_forward.py ... --mom-blend 0.25
```

Refresh data (extend history / universe):

```powershell
$env:MARKET_LOOKBACK_YEARS="12"
$env:UNIVERSE_SIZE="40"
..\.venv\Scripts\python -c "from app.ds.ingest import ingestor; df=ingestor.fetch(force=True); print(df['date'].min(), df['date'].max(), df['symbol'].nunique())"
```

Outputs: `data/walk_forward_results_v3.csv`, `data/walk_forward_train_audit.csv`

### Results (pure ML, net of costs)

Dataset: **40 symbols**, **121K+ rows**, **2014-07-15 → 2026-08-11**

**Walk-forward 2018–2024 (84 months)**

| Strategy | CAGR | Sharpe | Sortino | Max DD |
|----------|------|--------|---------|--------|
| **ML (pure)** | +32.0% | **1.19** | 2.19 | −37.1% |
| Momentum | +27.0% | 1.10 | 1.90 | −39.8% |
| Equal weight | +23.7% | 1.08 | 1.73 | −34.8% |
| Buy & hold SPY | +13.5% | 0.83 | 1.32 | −24.0% |

→ ML (pure) Sharpe − Momentum Sharpe = **+0.09**

**Holdout 2025–2026 (19 months, training frozen pre-2025)**

| Strategy | CAGR | Sharpe | Max DD |
|----------|------|--------|--------|
| **ML (pure)** | +49.3% | **1.41** | −15.3% |
| Momentum | +52.6% | 1.23 | −14.7% |
| Buy & hold SPY | +17.6% | 1.30 | −7.6% |

→ Sharpe favors ML (+0.18); CAGR favors momentum. Short holdout sample — treat as directional.

**Regime sensitivity:** Both ML and momentum fail in the **2022 bear market** (Sharpe ≈ −1.0, CAGR ≈ −32%). Strong years: 2019, 2021, 2023.

## Project layout

```
backend/
  app/ds/           # ingest, features, models, risk, backtest, pipeline
  app/api/ds.py     # DS REST endpoints
  scripts/run_walk_forward.py
  data/             # parquet cache + walk-forward CSVs
  models/           # trained joblib artifacts
frontend/
  src/app/          # Command, Markets, Intelligence, Optimizer, Lab, Alerts
```

## License

Proprietary — all rights reserved unless otherwise stated.
