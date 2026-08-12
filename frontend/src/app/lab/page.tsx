"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { api, type DSMetrics, type ForecastRow, type ValidationSuite } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { Badge, Panel, SectionTitle, Stat } from "@/components/ui";

const CURVE_COLORS: Record<string, string> = {
  ml_full: "#1f7a6c",
  equal_weight: "#1a2633",
  buy_hold_spy: "#c9851a",
  momentum: "#4d6f8c",
  technical: "#c43c3c",
};

export default function LabPage() {
  const { token } = useAuth();
  const [metrics, setMetrics] = useState<DSMetrics | null>(null);
  const [forecasts, setForecasts] = useState<ForecastRow[]>([]);
  const [regime, setRegime] = useState<{ regime: string; probabilities: Record<string, number>; score: number } | null>(null);
  const [suite, setSuite] = useState<ValidationSuite | null>(null);
  const [status, setStatus] = useState<string>("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function refresh() {
    try {
      const [m, f, r] = await Promise.all([api.dsMetrics(), api.dsForecasts(21), api.dsRegime()]);
      setMetrics(m);
      setForecasts(f.filter((x) => x.sector !== "Index").slice(0, 12));
      setRegime(r);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "DS pipeline not ready yet");
    }
  }

  useEffect(() => {
    refresh();
    const id = setInterval(refresh, 20000);
    return () => clearInterval(id);
  }, []);

  async function onValidate() {
    if (!token) return;
    setBusy(true);
    setStatus("Running validation suite (baselines · costs · ablations · regimes)…");
    try {
      const res = await api.dsBacktest(token, 21, 5, 5);
      setSuite(res);
      const s = res.summary;
      setStatus(
        `Done. ML net Sharpe ${s.ml_net_sharpe?.toFixed(2)} · beats EW after costs: ${String(s.ml_beats_ew_after_costs)}`
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : "Validation failed");
    } finally {
      setBusy(false);
    }
  }

  const curveData = useMemo(() => {
    if (!suite?.equity_curves_net) return [];
    const keys = Object.keys(suite.equity_curves_net);
    if (!keys.length) return [];
    const byDate = new Map<string, Record<string, number | string>>();
    for (const key of keys) {
      for (const pt of suite.equity_curves_net[key]) {
        const row = byDate.get(pt.date) || { date: pt.date };
        row[key] = pt.value;
        byDate.set(pt.date, row);
      }
    }
    return Array.from(byDate.values()).sort((a, b) => String(a.date).localeCompare(String(b.date)));
  }, [suite]);

  return (
    <div className="space-y-6">
      <div>
        <p className="text-xs font-semibold uppercase tracking-[0.22em] text-signal-accent">Performance monitor</p>
        <h1 className="mt-2 font-display text-4xl tracking-tight text-ink-950">Validation lab</h1>
        <p className="mt-2 max-w-3xl text-ink-500">
          Quality over features: baselines, transaction costs, uncertainty, ablations, and regime-period stress.
        </p>
      </div>

      {error ? (
        <Panel className="border-amber-200 bg-amber-50/80 text-signal-warn">{error}</Panel>
      ) : null}

      <div className="flex flex-wrap gap-2">
        {token ? (
          <button
            onClick={onValidate}
            disabled={busy}
            className="rounded-md bg-ink-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-60"
          >
            {busy ? "Validating…" : "Run full validation suite"}
          </button>
        ) : (
          <Link href="/login" className="rounded-md bg-ink-900 px-4 py-2 text-sm font-medium text-white">
            Sign in to validate
          </Link>
        )}
        {status ? <span className="self-center text-sm text-signal-accent">{status}</span> : null}
      </div>

      <div className="grid gap-4 md:grid-cols-4">
        <Panel>
          <Stat label="Pipeline" value={metrics?.status || "—"} tone="accent" />
        </Panel>
        <Panel delay={40}>
          <Stat label="Regime" value={regime?.regime?.replace("_", "-") || "—"} />
        </Panel>
        <Panel delay={80}>
          <Stat
            label="ML beats EW (net)"
            value={suite ? String(suite.summary.ml_beats_ew_after_costs) : "—"}
            tone={suite?.summary.ml_beats_ew_after_costs ? "up" : suite ? "down" : "neutral"}
          />
        </Panel>
        <Panel delay={120}>
          <Stat
            label="Gross→net Sharpe gap"
            value={suite?.summary.gross_to_net_sharpe_gap != null ? suite.summary.gross_to_net_sharpe_gap.toFixed(2) : "—"}
          />
        </Panel>
      </div>

      {suite ? (
        <>
          {suite.caveats?.length ? (
            <Panel className="border-ink-200 bg-ink-50/80">
              <SectionTitle title="Methodology caveats" subtitle="Read before claiming superiority" />
              <ul className="space-y-1 text-sm text-ink-600">
                {suite.caveats.map((c) => (
                  <li key={c}>• {c}</li>
                ))}
              </ul>
            </Panel>
          ) : null}

          <Panel delay={140}>
            <SectionTitle
              title="Baseline comparison (net of costs)"
              subtitle={`${suite.config.commission_bps}bps commission + ${suite.config.slippage_bps}bps slippage`}
            />
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead className="text-xs uppercase tracking-wider text-ink-400">
                  <tr>
                    <th className="pb-2">Strategy</th>
                    <th className="pb-2">Role</th>
                    <th className="pb-2">CAGR</th>
                    <th className="pb-2">Sharpe</th>
                    <th className="pb-2">Sortino</th>
                    <th className="pb-2">MDD</th>
                    <th className="pb-2">Calmar</th>
                    <th className="pb-2">Vol</th>
                    <th className="pb-2">VaR5</th>
                    <th className="pb-2">CVaR5</th>
                    <th className="pb-2">Turnover</th>
                    <th className="pb-2">Gross Sh</th>
                  </tr>
                </thead>
                <tbody>
                  {suite.comparison.map((r) => (
                    <tr key={r.strategy} className="border-t border-ink-100">
                      <td className="py-2 font-semibold">{r.strategy}</td>
                      <td className="py-2">
                        <Badge tone={r.role === "baseline" ? "neutral" : "up"}>{r.role || "—"}</Badge>
                      </td>
                      {r.error ? (
                        <td className="py-2 text-signal-down" colSpan={10}>
                          {r.error}
                        </td>
                      ) : (
                        <>
                          <td className="py-2 font-mono tabular-nums">{((r.net_cagr || 0) * 100).toFixed(1)}%</td>
                          <td className="py-2 font-mono tabular-nums">{r.net_sharpe?.toFixed(2)}</td>
                          <td className="py-2 font-mono tabular-nums">{r.net_sortino?.toFixed(2)}</td>
                          <td className="py-2 font-mono tabular-nums">{((r.max_drawdown || 0) * 100).toFixed(1)}%</td>
                          <td className="py-2 font-mono tabular-nums">{r.calmar?.toFixed(2)}</td>
                          <td className="py-2 font-mono tabular-nums">{((r.volatility || 0) * 100).toFixed(1)}%</td>
                          <td className="py-2 font-mono tabular-nums">{((r.var_5 || 0) * 100).toFixed(2)}%</td>
                          <td className="py-2 font-mono tabular-nums">{((r.cvar_5 || 0) * 100).toFixed(2)}%</td>
                          <td className="py-2 font-mono tabular-nums">{r.ann_turnover?.toFixed(2)}</td>
                          <td className="py-2 font-mono tabular-nums text-ink-400">{r.gross_sharpe?.toFixed(2)}</td>
                        </>
                      )}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Panel>

          <Panel delay={180}>
            <SectionTitle title="Ablation ladder" subtitle="Which component improves net Sharpe?" />
            <div className="space-y-2">
              {suite.ablation.map((a) => (
                <div key={a.step} className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-ink-100 bg-ink-50/50 px-4 py-3">
                  <div>
                    <div className="font-semibold text-ink-900">{a.label || a.step}</div>
                    <div className="text-xs text-ink-400">{a.step}</div>
                  </div>
                  {a.error ? (
                    <span className="text-sm text-signal-down">{a.error}</span>
                  ) : (
                    <div className="flex gap-4 font-mono text-sm tabular-nums">
                      <span>Sharpe {a.net_sharpe?.toFixed(2)}</span>
                      <span>CAGR {((a.net_cagr || 0) * 100).toFixed(1)}%</span>
                      <span className={a.delta_sharpe != null && a.delta_sharpe >= 0 ? "text-signal-up" : "text-signal-down"}>
                        Δ {a.delta_sharpe == null ? "—" : a.delta_sharpe.toFixed(2)}
                      </span>
                    </div>
                  )}
                </div>
              ))}
            </div>
          </Panel>

          <Panel delay={200}>
            <SectionTitle title="Regime periods" subtitle="When the system works vs fails (net metrics)" />
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead className="text-xs uppercase tracking-wider text-ink-400">
                  <tr>
                    <th className="pb-2">Period</th>
                    <th className="pb-2">Days</th>
                    <th className="pb-2">ML Sharpe</th>
                    <th className="pb-2">ML CAGR</th>
                    <th className="pb-2">ML MDD</th>
                    <th className="pb-2">EW Sharpe</th>
                    <th className="pb-2">Beats EW?</th>
                  </tr>
                </thead>
                <tbody>
                  {suite.regime_periods.map((p) => (
                    <tr key={p.period} className="border-t border-ink-100">
                      <td className="py-2 font-semibold capitalize">{p.period.replace("_", " ")}</td>
                      <td className="py-2 font-mono">{p.n_days}</td>
                      {p.insufficient ? (
                        <td className="py-2 text-ink-400" colSpan={5}>
                          insufficient sample
                        </td>
                      ) : (
                        <>
                          <td className="py-2 font-mono tabular-nums">{p.ml_net?.sharpe.toFixed(2)}</td>
                          <td className="py-2 font-mono tabular-nums">{((p.ml_net?.cagr || 0) * 100).toFixed(1)}%</td>
                          <td className="py-2 font-mono tabular-nums">{((p.ml_net?.max_drawdown || 0) * 100).toFixed(1)}%</td>
                          <td className="py-2 font-mono tabular-nums">{p.equal_weight_net?.sharpe.toFixed(2)}</td>
                          <td className="py-2">
                            <Badge tone={p.ml_beats_ew_sharpe ? "up" : "down"}>
                              {String(p.ml_beats_ew_sharpe)}
                            </Badge>
                          </td>
                        </>
                      )}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Panel>

          <div className="grid gap-5 lg:grid-cols-2">
            <Panel delay={220}>
              <SectionTitle title="Forecast uncertainty" subtitle="Holdout MAE/RMSE, calibration, intervals" />
              {suite.uncertainty?.ok ? (
                <div className="space-y-3 text-sm">
                  <div className="grid grid-cols-2 gap-3 font-mono tabular-nums">
                    <div>MAE {suite.uncertainty.mae}</div>
                    <div>RMSE {suite.uncertainty.rmse}</div>
                    <div>R² {suite.uncertainty.r2}</div>
                    <div>Dir.acc {((suite.uncertainty.directional_accuracy || 0) * 100).toFixed(1)}%</div>
                  </div>
                  <div className="rounded-lg border border-ink-100 bg-ink-50/60 p-3">
                    <div className="text-xs uppercase tracking-wider text-ink-400">Prediction intervals</div>
                    <div className="mt-1 font-mono text-sm">
                      80% cover {suite.uncertainty.prediction_intervals?.cover_80}{" "}
                      <Badge tone={suite.uncertainty.prediction_intervals?.well_calibrated_80 ? "up" : "warn"}>
                        {suite.uncertainty.prediction_intervals?.well_calibrated_80 ? "ok" : "miscal"}
                      </Badge>
                    </div>
                    <div className="font-mono text-sm">
                      95% cover {suite.uncertainty.prediction_intervals?.cover_95}{" "}
                      <Badge tone={suite.uncertainty.prediction_intervals?.well_calibrated_95 ? "up" : "warn"}>
                        {suite.uncertainty.prediction_intervals?.well_calibrated_95 ? "ok" : "miscal"}
                      </Badge>
                    </div>
                  </div>
                  {suite.uncertainty.volatility_forecast ? (
                    <div className="text-ink-600">
                      Vol forecast MAE {suite.uncertainty.volatility_forecast.mae} · R²{" "}
                      {suite.uncertainty.volatility_forecast.r2}
                    </div>
                  ) : null}
                </div>
              ) : (
                <p className="text-sm text-ink-500">Uncertainty block unavailable.</p>
              )}
            </Panel>

            <Panel delay={240}>
              <SectionTitle title="Net equity curves" subtitle="After commission + slippage" />
              <div className="h-64">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={curveData}>
                    <CartesianGrid stroke="#e4ebf0" vertical={false} />
                    <XAxis dataKey="date" tick={{ fontSize: 10, fill: "#6a8aa4" }} minTickGap={40} />
                    <YAxis tick={{ fontSize: 11, fill: "#6a8aa4" }} tickFormatter={(v) => `${(Number(v) * 100).toFixed(0)}%`} />
                    <Tooltip formatter={(v) => `${((Number(v) || 0) * 100).toFixed(1)}%`} />
                    <Legend />
                    {Object.keys(suite.equity_curves_net || {}).map((k) => (
                      <Line
                        key={k}
                        type="monotone"
                        dataKey={k}
                        stroke={CURVE_COLORS[k] || "#6a8aa4"}
                        strokeWidth={k === "ml_full" ? 2.5 : 1.5}
                        dot={false}
                      />
                    ))}
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </Panel>
          </div>
        </>
      ) : null}

      <Panel delay={260}>
        <SectionTitle title="Model training metrics" subtitle="Chronological holdout from last train" />
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="text-xs uppercase tracking-wider text-ink-400">
              <tr>
                <th className="pb-2">Model</th>
                <th className="pb-2">H</th>
                <th className="pb-2">MAE</th>
                <th className="pb-2">RMSE</th>
                <th className="pb-2">R²</th>
                <th className="pb-2">Dir</th>
                <th className="pb-2">Cover80</th>
              </tr>
            </thead>
            <tbody>
              {(metrics?.model_metrics || []).map((m, i) => (
                <tr key={i} className="border-t border-ink-100">
                  <td className="py-2 font-medium">{m.model_type}</td>
                  <td className="py-2 font-mono">{m.horizon ?? "—"}</td>
                  <td className="py-2 font-mono tabular-nums">{m.mae.toFixed(4)}</td>
                  <td className="py-2 font-mono tabular-nums">{m.rmse.toFixed(4)}</td>
                  <td className="py-2 font-mono tabular-nums">{m.r2.toFixed(3)}</td>
                  <td className="py-2 font-mono tabular-nums">
                    {m.extras?.directional_acc != null ? `${(Number(m.extras.directional_acc) * 100).toFixed(1)}%` : "—"}
                  </td>
                  <td className="py-2 font-mono tabular-nums">
                    {m.extras?.cover_80 != null ? Number(m.extras.cover_80).toFixed(2) : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Panel>

      <Panel delay={280}>
        <SectionTitle title="Latest 21d forecasts" subtitle="Point estimates — use uncertainty block for reliability" />
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="text-xs uppercase tracking-wider text-ink-400">
              <tr>
                <th className="pb-2">Symbol</th>
                <th className="pb-2">Pred</th>
                <th className="pb-2">Ann</th>
                <th className="pb-2">Pred vol</th>
              </tr>
            </thead>
            <tbody>
              {forecasts.map((f) => (
                <tr key={f.symbol} className="border-t border-ink-100">
                  <td className="py-2 font-semibold">{f.symbol}</td>
                  <td className={`py-2 font-mono ${f.predicted_return >= 0 ? "text-signal-up" : "text-signal-down"}`}>
                    {(f.predicted_return * 100).toFixed(2)}%
                  </td>
                  <td className="py-2 font-mono">{(f.predicted_return_annualized * 100).toFixed(1)}%</td>
                  <td className="py-2 font-mono">{(f.predicted_volatility * 100).toFixed(2)}%</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Panel>
    </div>
  );
}
