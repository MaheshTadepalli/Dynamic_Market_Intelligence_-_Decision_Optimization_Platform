"use client";

import { FormEvent, useEffect, useState } from "react";
import Link from "next/link";
import {
  CartesianGrid,
  Cell,
  Pie,
  PieChart,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { api, fmtNum, type OptimizeResult } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { Panel, SectionTitle, Stat } from "@/components/ui";

const DEFAULT_SYMBOLS = ["AAPL", "MSFT", "NVDA", "JPM", "XOM", "UNH", "AMZN", "META"];
const COLORS = ["#1f7a6c", "#1a2633", "#c9851a", "#4d6f8c", "#0f8a5f", "#c43c3c", "#32485d", "#6a8aa4"];

export default function OptimizerPage() {
  const { token } = useAuth();
  const [symbols, setSymbols] = useState(DEFAULT_SYMBOLS.join(", "));
  const [objective, setObjective] = useState("max_sharpe");
  const [capital, setCapital] = useState(1000000);
  const [maxWeight, setMaxWeight] = useState(0.35);
  const [result, setResult] = useState<OptimizeResult | null>(null);
  const [scenarioShock, setScenarioShock] = useState(-10);
  const [scenario, setScenario] = useState<{ pnl_pct: number; contributions: { symbol: string; contribution_pct: number }[] } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [history, setHistory] = useState<{ id: number; name: string; objective: string; created_at: string }[]>([]);

  useEffect(() => {
    if (!token) return;
    api.history(token).then((h) => setHistory(h.slice(0, 6))).catch(() => undefined);
  }, [token, result]);

  async function onOptimize(e: FormEvent) {
    e.preventDefault();
    if (!token) {
      setError("Sign in to run optimization.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const res = await api.optimize(token, {
        name: `Run ${new Date().toLocaleString()}`,
        symbols: symbols.split(",").map((s) => s.trim().toUpperCase()).filter(Boolean),
        objective,
        capital,
        max_weight: maxWeight,
        min_weight: 0,
      });
      setResult(res);
      setScenario(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Optimization failed");
    } finally {
      setBusy(false);
    }
  }

  async function runScenario() {
    if (!token || !result) return;
    const res = await api.scenario(token, {
      symbols: result.allocations.map((a) => a.symbol),
      weights: result.allocations.map((a) => a.weight),
      shock_pct: scenarioShock / 100,
    });
    setScenario(res);
  }

  if (!token) {
    return (
      <Panel>
        <SectionTitle title="Decision optimizer" subtitle="Authenticated workspace required" />
        <p className="text-ink-500">Sign in to run mean-variance / risk-parity optimizations and persist decision runs.</p>
        <Link href="/login" className="mt-4 inline-flex rounded-md bg-ink-900 px-4 py-2 text-sm font-medium text-white">
          Sign in
        </Link>
      </Panel>
    );
  }

  return (
    <div className="space-y-6">
      <div>
        <p className="text-xs font-semibold uppercase tracking-[0.22em] text-signal-accent">Optimizer</p>
        <h1 className="mt-2 font-display text-4xl tracking-tight text-ink-950">Decision optimization desk</h1>
      </div>

      <div className="grid gap-5 lg:grid-cols-5">
        <Panel className="lg:col-span-2">
          <SectionTitle title="Constraints" subtitle="SLSQP portfolio solver" />
          <form onSubmit={onOptimize} className="space-y-4">
            <label className="block text-sm">
              <span className="text-ink-500">Symbols (comma-separated)</span>
              <textarea
                className="mt-1 w-full rounded-md border border-ink-200 bg-white px-3 py-2 font-mono text-sm"
                rows={3}
                value={symbols}
                onChange={(e) => setSymbols(e.target.value)}
              />
            </label>
            <label className="block text-sm">
              <span className="text-ink-500">Objective</span>
              <select
                className="mt-1 w-full rounded-md border border-ink-200 bg-white px-3 py-2"
                value={objective}
                onChange={(e) => setObjective(e.target.value)}
              >
                <option value="max_sharpe">Max Sharpe</option>
                <option value="min_volatility">Min Volatility</option>
                <option value="max_return">Max Return</option>
                <option value="risk_parity">Risk Parity</option>
              </select>
            </label>
            <div className="grid grid-cols-2 gap-3">
              <label className="block text-sm">
                <span className="text-ink-500">Capital</span>
                <input
                  type="number"
                  className="mt-1 w-full rounded-md border border-ink-200 bg-white px-3 py-2"
                  value={capital}
                  onChange={(e) => setCapital(Number(e.target.value))}
                />
              </label>
              <label className="block text-sm">
                <span className="text-ink-500">Max weight</span>
                <input
                  type="number"
                  step="0.01"
                  min={0.05}
                  max={1}
                  className="mt-1 w-full rounded-md border border-ink-200 bg-white px-3 py-2"
                  value={maxWeight}
                  onChange={(e) => setMaxWeight(Number(e.target.value))}
                />
              </label>
            </div>
            {error ? <p className="text-sm text-signal-down">{error}</p> : null}
            <button
              type="submit"
              disabled={busy}
              className="w-full rounded-md bg-signal-accent px-4 py-2.5 text-sm font-semibold text-white hover:bg-[#19685c] disabled:opacity-60"
            >
              {busy ? "Optimizing…" : "Optimize allocation"}
            </button>
          </form>

          {history.length > 0 ? (
            <div className="mt-6">
              <h3 className="text-xs font-semibold uppercase tracking-wider text-ink-400">Recent runs</h3>
              <ul className="mt-2 space-y-2 text-sm">
                {history.map((h) => (
                  <li key={h.id} className="rounded-md border border-ink-100 bg-ink-50/60 px-3 py-2">
                    <div className="font-medium text-ink-800">#{h.id} · {h.objective}</div>
                    <div className="text-xs text-ink-400">{new Date(h.created_at).toLocaleString()}</div>
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
        </Panel>

        <div className="space-y-5 lg:col-span-3">
          {result ? (
            <>
              <div className="grid gap-4 sm:grid-cols-4">
                <Panel>
                  <Stat label="Expected return" value={`${(result.expected_return * 100).toFixed(1)}%`} tone="up" />
                </Panel>
                <Panel delay={40}>
                  <Stat label="Volatility" value={`${(result.volatility * 100).toFixed(1)}%`} />
                </Panel>
                <Panel delay={80}>
                  <Stat label="Sharpe" value={result.sharpe.toFixed(2)} tone="accent" />
                </Panel>
                <Panel delay={120}>
                  <Stat label="Diversification" value={result.diversification_score.toFixed(2)} />
                </Panel>
              </div>

              <div className="grid gap-5 lg:grid-cols-2">
                <Panel delay={160}>
                  <SectionTitle title="Weights" />
                  <div className="h-56">
                    <ResponsiveContainer width="100%" height="100%">
                      <PieChart>
                        <Pie data={result.allocations} dataKey="weight" nameKey="symbol" innerRadius={50} outerRadius={80}>
                          {result.allocations.map((_, i) => (
                            <Cell key={i} fill={COLORS[i % COLORS.length]} />
                          ))}
                        </Pie>
                        <Tooltip formatter={(v) => `${((Number(v) || 0) * 100).toFixed(1)}%`} />
                      </PieChart>
                    </ResponsiveContainer>
                  </div>
                  <table className="mt-2 w-full text-sm">
                    <tbody>
                      {result.allocations.map((a) => (
                        <tr key={a.symbol} className="border-t border-ink-100">
                          <td className="py-2 font-semibold">{a.symbol}</td>
                          <td className="py-2 font-mono tabular-nums">{(a.weight * 100).toFixed(1)}%</td>
                          <td className="py-2 text-right font-mono tabular-nums text-ink-500">${fmtNum(a.amount, 0)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </Panel>

                <Panel delay={200}>
                  <SectionTitle title="Efficient frontier" subtitle="Return vs risk locus" />
                  <div className="h-64">
                    <ResponsiveContainer width="100%" height="100%">
                      <ScatterChart>
                        <CartesianGrid stroke="#e4ebf0" />
                        <XAxis
                          type="number"
                          dataKey="volatility"
                          name="Vol"
                          tick={{ fontSize: 11, fill: "#6a8aa4" }}
                          tickFormatter={(v) => `${(v * 100).toFixed(0)}%`}
                        />
                        <YAxis
                          type="number"
                          dataKey="return"
                          name="Ret"
                          tick={{ fontSize: 11, fill: "#6a8aa4" }}
                          tickFormatter={(v) => `${(v * 100).toFixed(0)}%`}
                        />
                        <Tooltip
                          formatter={(v) => `${((Number(v) || 0) * 100).toFixed(2)}%`}
                          contentStyle={{ borderRadius: 10 }}
                        />
                        <Scatter data={result.efficient_frontier} fill="#1f7a6c" />
                        <Scatter
                          data={[{ volatility: result.volatility, return: result.expected_return }]}
                          fill="#c9851a"
                        />
                      </ScatterChart>
                    </ResponsiveContainer>
                  </div>
                </Panel>
              </div>

              <Panel delay={240}>
                <SectionTitle
                  title="Scenario stress"
                  subtitle="Apply a uniform shock to the optimized book"
                  action={
                    <div className="flex items-center gap-2">
                      <input
                        type="number"
                        className="w-24 rounded-md border border-ink-200 px-2 py-1.5 text-sm"
                        value={scenarioShock}
                        onChange={(e) => setScenarioShock(Number(e.target.value))}
                      />
                      <span className="text-sm text-ink-400">%</span>
                      <button
                        onClick={runScenario}
                        className="rounded-md border border-ink-200 bg-white px-3 py-1.5 text-sm font-medium text-ink-800"
                      >
                        Shock
                      </button>
                    </div>
                  }
                />
                {scenario ? (
                  <div>
                    <div className={`font-mono text-3xl font-semibold tabular-nums ${scenario.pnl_pct >= 0 ? "text-signal-up" : "text-signal-down"}`}>
                      {scenario.pnl_pct >= 0 ? "+" : ""}
                      {scenario.pnl_pct.toFixed(2)}% P&L
                    </div>
                    <div className="mt-3 grid gap-2 sm:grid-cols-2">
                      {scenario.contributions.map((c) => (
                        <div key={c.symbol} className="flex justify-between rounded-md bg-ink-50 px-3 py-2 text-sm">
                          <span className="font-semibold">{c.symbol}</span>
                          <span className="font-mono tabular-nums text-ink-500">{c.contribution_pct.toFixed(2)}%</span>
                        </div>
                      ))}
                    </div>
                  </div>
                ) : (
                  <p className="text-sm text-ink-500">Run a shock to estimate portfolio P&amp;L contribution.</p>
                )}
              </Panel>
            </>
          ) : (
            <Panel>
              <SectionTitle title="Awaiting run" subtitle="Configure constraints and optimize" />
              <p className="text-ink-500">
                The solver estimates expected returns and covariance from the live simulated tape, then allocates under your weight caps.
              </p>
            </Panel>
          )}
        </div>
      </div>
    </div>
  );
}
