const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";

export type Quote = {
  symbol: string;
  name: string;
  price: number;
  change: number;
  change_pct: number;
  volume: number;
  high: number;
  low: number;
  open: number;
  previous_close: number;
  sector: string;
  updated_at: string;
};

export type Candle = { t: string; o: number; h: number; l: number; c: number; v: number };

export type IntelligenceSignal = {
  symbol: string;
  signal: "bullish" | "bearish" | "neutral";
  confidence: number;
  score: number;
  drivers: string[];
  risk_level: "low" | "medium" | "high";
  horizon: string;
  summary: string;
  updated_at: string;
};

export type MarketOverview = {
  as_of: string;
  indices: Quote[];
  movers: Quote[];
  breadth: Record<string, number>;
  regime: string;
  regime_score: number;
};

export type OptimizeResult = {
  id?: number;
  name: string;
  objective: string;
  allocations: {
    symbol: string;
    weight: number;
    amount: number;
    expected_return: number;
    volatility: number;
  }[];
  expected_return: number;
  volatility: number;
  sharpe: number;
  diversification_score: number;
  efficient_frontier: { return: number; volatility: number }[];
  constraints: Record<string, unknown>;
  created_at: string;
};

export type Alert = {
  id: number;
  symbol: string;
  condition: string;
  threshold: number | null;
  message: string;
  is_active: boolean;
  triggered: boolean;
  last_triggered_at: string | null;
  created_at: string;
};

function authHeaders(token?: string | null): HeadersInit {
  const headers: HeadersInit = { "Content-Type": "application/json" };
  if (token) headers.Authorization = `Bearer ${token}`;
  return headers;
}

async function handle<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || `Request failed (${res.status})`);
  }
  return res.json();
}

export const api = {
  async login(email: string, password: string) {
    const body = new URLSearchParams();
    body.set("username", email);
    body.set("password", password);
    const res = await fetch(`${API_BASE}/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body,
    });
    return handle<{ access_token: string }>(res);
  },
  me(token: string) {
    return fetch(`${API_BASE}/auth/me`, { headers: authHeaders(token) }).then(handle<{ email: string; full_name: string; role: string }>);
  },
  overview() {
    return fetch(`${API_BASE}/intelligence/overview`).then(handle<MarketOverview>);
  },
  quotes(symbols?: string[]) {
    const q = symbols?.length ? `?symbols=${symbols.join(",")}` : "";
    return fetch(`${API_BASE}/market/quotes${q}`).then(handle<Quote[]>);
  },
  candles(symbol: string, limit = 80) {
    return fetch(`${API_BASE}/market/candles/${symbol}?limit=${limit}`).then(handle<Candle[]>);
  },
  indicators(symbol: string) {
    return fetch(`${API_BASE}/market/indicators/${symbol}`).then(
      handle<{ rsi: number; sma_20: number; sma_50: number; macd: number; macd_signal: number; volatility: number; momentum: number }>
    );
  },
  signals(symbols?: string[]) {
    const q = symbols?.length ? `?symbols=${symbols.join(",")}` : "";
    return fetch(`${API_BASE}/intelligence/signals${q}`).then(handle<IntelligenceSignal[]>);
  },
  sectors() {
    return fetch(`${API_BASE}/intelligence/sectors`).then(
      handle<{ sector: string; change_pct: number; count: number }[]>
    );
  },
  symbols() {
    return fetch(`${API_BASE}/market/symbols`).then(handle<{ symbol: string; name: string; sector: string }[]>);
  },
  optimize(token: string, payload: Record<string, unknown>) {
    return fetch(`${API_BASE}/decisions/optimize`, {
      method: "POST",
      headers: authHeaders(token),
      body: JSON.stringify(payload),
    }).then(handle<OptimizeResult>);
  },
  scenario(token: string, payload: Record<string, unknown>) {
    return fetch(`${API_BASE}/decisions/scenario`, {
      method: "POST",
      headers: authHeaders(token),
      body: JSON.stringify(payload),
    }).then(
      handle<{ base_value: number; shocked_value: number; pnl: number; pnl_pct: number; contributions: { symbol: string; weight: number; shock_pct: number; contribution_pct: number }[] }>
    );
  },
  history(token: string) {
    return fetch(`${API_BASE}/decisions/history`, { headers: authHeaders(token) }).then(
      handle<{ id: number; name: string; objective: string; created_at: string; result: OptimizeResult }[]>
    );
  },
  alerts(token: string) {
    return fetch(`${API_BASE}/alerts`, { headers: authHeaders(token) }).then(handle<Alert[]>);
  },
  createAlert(token: string, payload: { symbol: string; condition: string; threshold?: number; message?: string }) {
    return fetch(`${API_BASE}/alerts`, {
      method: "POST",
      headers: authHeaders(token),
      body: JSON.stringify(payload),
    }).then(handle<Alert>);
  },
  evaluateAlerts(token: string) {
    return fetch(`${API_BASE}/alerts/evaluate`, { method: "POST", headers: authHeaders(token) }).then(handle<Alert[]>);
  },
  deleteAlert(token: string, id: number) {
    return fetch(`${API_BASE}/alerts/${id}`, { method: "DELETE", headers: authHeaders(token) }).then(handle<{ ok: boolean }>);
  },
  dsStatus() {
    return fetch(`${API_BASE}/ds/status`).then(handle<DSStatus>);
  },
  dsMetrics() {
    return fetch(`${API_BASE}/ds/metrics`).then(handle<DSMetrics>);
  },
  dsForecasts(horizon = 21) {
    return fetch(`${API_BASE}/ds/forecasts?horizon=${horizon}`).then(handle<ForecastRow[]>);
  },
  dsRegime() {
    return fetch(`${API_BASE}/ds/regime`).then(handle<{ regime: string; probabilities: Record<string, number>; score: number }>);
  },
  dsBootstrap(token: string, forceRefresh = false) {
    return fetch(`${API_BASE}/ds/bootstrap?force_refresh=${forceRefresh}&train=true`, {
      method: "POST",
      headers: authHeaders(token),
    }).then(handle<DSStatus>);
  },
  dsBacktest(token: string, horizon = 21, commissionBps = 5, slippageBps = 5) {
    return fetch(
      `${API_BASE}/ds/backtest?horizon=${horizon}&commission_bps=${commissionBps}&slippage_bps=${slippageBps}`,
      {
        method: "POST",
        headers: authHeaders(token),
      }
    ).then(handle<ValidationSuite>);
  },
  dsStress(token: string, symbols: string[], weights: number[]) {
    return fetch(`${API_BASE}/ds/stress`, {
      method: "POST",
      headers: authHeaders(token),
      body: JSON.stringify({ symbols, weights }),
    }).then(handle<{ scenarios: { name: string; pnl_pct: number }[]; worst_scenario: string }>);
  },
};

export type ForecastRow = {
  symbol: string;
  name: string;
  sector: string;
  date: string;
  close: number;
  horizon_days: number;
  predicted_return: number;
  predicted_return_annualized: number;
  predicted_volatility: number;
  rsi_14: number;
  macd: number;
  momentum_21d: number;
};

export type DSStatus = {
  ok: boolean;
  status: string;
  error?: string | null;
  validation?: Record<string, unknown>;
  trained_at?: string;
  mlflow_run_id?: string | null;
  metrics?: { horizon: number | null; model_type: string; mae: number; rmse: number; r2: number; extras?: Record<string, number> }[];
  regime?: { regime: string; probabilities: Record<string, number>; score: number };
  n_forecasts?: number;
};

export type DSMetrics = {
  model_metrics: DSStatus["metrics"];
  validation: Record<string, unknown>;
  trained_at?: string;
  mlflow_run_id?: string | null;
  status: string;
  replay: { index: number | null; n_dates: number; asof: string | null; at_live_edge: boolean };
};

export type BacktestResult = {
  n_days: number;
  n_rebalances: number;
  strategy: { ann_return: number; ann_vol: number; sharpe: number; max_drawdown: number; hit_rate: number };
  equal_weight: { ann_return: number; ann_vol: number; sharpe: number; max_drawdown: number; hit_rate: number };
  spy: { ann_return: number; ann_vol: number; sharpe: number; max_drawdown: number; hit_rate: number };
  equity_curve: { date: string; strategy: number; spy: number }[];
};

export type PortfolioMetrics = {
  cagr: number;
  total_return: number;
  ann_return: number;
  volatility: number;
  sharpe: number;
  sortino: number;
  max_drawdown: number;
  calmar: number;
  var_5: number;
  cvar_5: number;
  hit_rate: number;
  ann_turnover: number;
  n_days: number;
};

export type ValidationSuite = {
  as_of: string;
  config: Record<string, number>;
  summary: {
    ml_net_sharpe?: number;
    ew_net_sharpe?: number;
    bh_net_sharpe?: number;
    ml_beats_ew_after_costs?: boolean | null;
    ml_beats_buyhold_after_costs?: boolean | null;
    gross_to_net_sharpe_gap?: number | null;
  };
  comparison: {
    strategy: string;
    role: string;
    net_cagr?: number;
    net_sharpe?: number;
    net_sortino?: number;
    max_drawdown?: number;
    calmar?: number;
    volatility?: number;
    var_5?: number;
    cvar_5?: number;
    ann_turnover?: number;
    gross_sharpe?: number;
    cost_drag?: number;
    error?: string;
  }[];
  ablation: {
    step: string;
    label?: string;
    net_sharpe?: number;
    net_cagr?: number;
    max_drawdown?: number;
    delta_sharpe?: number | null;
    error?: string;
  }[];
  regime_periods: {
    period: string;
    n_days: number;
    insufficient?: boolean;
    ml_net?: PortfolioMetrics;
    equal_weight_net?: PortfolioMetrics;
    ml_beats_ew_sharpe?: boolean;
  }[];
  uncertainty: {
    ok?: boolean;
    mae?: number;
    rmse?: number;
    r2?: number;
    directional_accuracy?: number;
    prediction_intervals?: {
      cover_80: number;
      cover_95: number;
      well_calibrated_80: boolean;
      well_calibrated_95: boolean;
    };
    volatility_forecast?: { mae: number; rmse: number; r2: number };
    calibration_bins?: { bin: number; mean_predicted: number; mean_realized: number }[];
  };
  equity_curves_net: Record<string, { date: string; value: number }[]>;
  caveats?: string[];
};

export function fmtPct(n: number, digits = 2) {
  const sign = n > 0 ? "+" : "";
  return `${sign}${n.toFixed(digits)}%`;
}

export function fmtNum(n: number, digits = 2) {
  return n.toLocaleString(undefined, { maximumFractionDigits: digits, minimumFractionDigits: digits });
}

export function fmtCompact(n: number) {
  return Intl.NumberFormat(undefined, { notation: "compact", maximumFractionDigits: 1 }).format(n);
}
