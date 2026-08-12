"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { api, fmtCompact, fmtNum, fmtPct, type IntelligenceSignal, type MarketOverview, type Quote } from "@/lib/api";
import { Badge, Panel, SectionTitle, Stat } from "@/components/ui";

export default function CommandCenterPage() {
  const [overview, setOverview] = useState<MarketOverview | null>(null);
  const [signals, setSignals] = useState<IntelligenceSignal[]>([]);
  const [candles, setCandles] = useState<{ t: string; c: number }[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    async function load() {
      try {
        const [ov, sig, c] = await Promise.all([
          api.overview(),
          api.signals(),
          api.candles("SPY", 60),
        ]);
        if (!alive) return;
        setOverview(ov);
        setSignals(sig.slice(0, 6));
        setCandles(c.map((x) => ({ t: new Date(x.t).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }), c: x.c })));
        setError(null);
      } catch (e) {
        if (alive) setError(e instanceof Error ? e.message : "Failed to load");
      }
    }
    load();
    const id = setInterval(load, 5000);
    return () => {
      alive = false;
      clearInterval(id);
    };
  }, []);

  return (
    <div className="space-y-6">
      <div className="animate-rise">
        <p className="text-xs font-semibold uppercase tracking-[0.22em] text-signal-accent">Command Center</p>
        <h1 className="mt-2 max-w-3xl font-display text-4xl leading-tight tracking-tight text-ink-950 md:text-5xl">
          Dynamic Market Intelligence & Decision Optimization
        </h1>
        <p className="mt-3 max-w-2xl text-base text-ink-500">
          Historical market data → return/risk forecasts → regime-aware portfolio decisions.
        </p>
      </div>

      {error ? (
        <Panel className="border-rose-200 bg-rose-50/80 text-signal-down">
          API unavailable: {error}. Start the backend on port 8000.
        </Panel>
      ) : null}

      <div className="grid gap-4 md:grid-cols-4">
        <Panel delay={40}>
          <Stat
            label="Market regime"
            value={overview?.regime.split(" ")[0] || "—"}
            hint={overview?.regime}
            tone="accent"
          />
        </Panel>
        <Panel delay={80}>
          <Stat
            label="Regime score"
            value={overview ? overview.regime_score.toFixed(2) : "—"}
            tone={overview && overview.regime_score >= 0 ? "up" : "down"}
          />
        </Panel>
        <Panel delay={120}>
          <Stat
            label="Advancers"
            value={overview ? String(overview.breadth.advancers) : "—"}
            hint={overview ? `${overview.breadth.decliners} decliners` : undefined}
            tone="up"
          />
        </Panel>
        <Panel delay={160}>
          <Stat
            label="Avg change"
            value={overview ? fmtPct(overview.breadth.avg_change_pct) : "—"}
            tone={overview && overview.breadth.avg_change_pct >= 0 ? "up" : "down"}
          />
        </Panel>
      </div>

      <div className="grid gap-5 lg:grid-cols-5">
        <Panel className="lg:col-span-3" delay={180}>
          <SectionTitle title="SPY microstructure" subtitle="Simulated live tape — 5m cadence" />
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={candles}>
                <defs>
                  <linearGradient id="spyFill" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#1f7a6c" stopOpacity={0.35} />
                    <stop offset="100%" stopColor="#1f7a6c" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid stroke="#e4ebf0" vertical={false} />
                <XAxis dataKey="t" tick={{ fontSize: 11, fill: "#6a8aa4" }} minTickGap={28} />
                <YAxis domain={["auto", "auto"]} tick={{ fontSize: 11, fill: "#6a8aa4" }} width={56} />
                <Tooltip
                  contentStyle={{ borderRadius: 10, borderColor: "#c7d5e0", background: "rgba(255,255,255,0.95)" }}
                />
                <Area type="monotone" dataKey="c" stroke="#1f7a6c" fill="url(#spyFill)" strokeWidth={2} />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </Panel>

        <Panel className="lg:col-span-2" delay={220}>
          <SectionTitle title="Index tape" subtitle="Benchmark pulse" />
          <div className="space-y-3">
            {(overview?.indices || []).map((q) => (
              <IndexRow key={q.symbol} quote={q} />
            ))}
          </div>
          <div className="mt-5 flex gap-2">
            <Link href="/optimizer" className="rounded-md bg-ink-900 px-3 py-2 text-sm font-medium text-white">
              Run optimizer
            </Link>
            <Link href="/intelligence" className="rounded-md border border-ink-200 bg-white px-3 py-2 text-sm font-medium text-ink-700">
              View signals
            </Link>
          </div>
        </Panel>
      </div>

      <div className="grid gap-5 lg:grid-cols-2">
        <Panel delay={260}>
          <SectionTitle title="Top movers" subtitle="Absolute percentage leaders" />
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="text-xs uppercase tracking-wider text-ink-400">
                <tr>
                  <th className="pb-2 font-medium">Symbol</th>
                  <th className="pb-2 font-medium">Price</th>
                  <th className="pb-2 font-medium">Change</th>
                  <th className="pb-2 font-medium">Volume</th>
                </tr>
              </thead>
              <tbody>
                {(overview?.movers || []).map((m) => (
                  <tr key={m.symbol} className="border-t border-ink-100">
                    <td className="py-2.5 font-semibold text-ink-900">{m.symbol}</td>
                    <td className="py-2.5 font-mono tabular-nums">{fmtNum(m.price)}</td>
                    <td className={`py-2.5 font-mono tabular-nums ${m.change_pct >= 0 ? "text-signal-up" : "text-signal-down"}`}>
                      {fmtPct(m.change_pct)}
                    </td>
                    <td className="py-2.5 font-mono text-ink-500 tabular-nums">{fmtCompact(m.volume)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Panel>

        <Panel delay={300}>
          <SectionTitle title="Priority signals" subtitle="Scored by conviction × magnitude" />
          <div className="space-y-3">
            {signals.map((s) => (
              <div key={s.symbol} className="rounded-lg border border-ink-100 bg-ink-50/60 p-3">
                <div className="flex items-center justify-between gap-3">
                  <div className="font-semibold text-ink-900">{s.symbol}</div>
                  <Badge tone={s.signal === "bullish" ? "up" : s.signal === "bearish" ? "down" : "neutral"}>
                    {s.signal}
                  </Badge>
                </div>
                <p className="mt-1 text-sm text-ink-500">{s.summary}</p>
                <div className="mt-2 flex gap-3 text-xs text-ink-400">
                  <span>Conf {(s.confidence * 100).toFixed(0)}%</span>
                  <span>Score {s.score.toFixed(2)}</span>
                  <span>Risk {s.risk_level}</span>
                </div>
              </div>
            ))}
          </div>
        </Panel>
      </div>
    </div>
  );
}

function IndexRow({ quote }: { quote: Quote }) {
  return (
    <div className="flex items-center justify-between rounded-lg border border-ink-100 bg-ink-50/50 px-3 py-2.5">
      <div>
        <div className="font-semibold text-ink-900">{quote.symbol}</div>
        <div className="text-xs text-ink-400">{quote.name}</div>
      </div>
      <div className="text-right">
        <div className="font-mono font-semibold tabular-nums text-ink-900">{fmtNum(quote.price)}</div>
        <div className={`font-mono text-xs tabular-nums ${quote.change_pct >= 0 ? "text-signal-up" : "text-signal-down"}`}>
          {fmtPct(quote.change_pct)}
        </div>
      </div>
    </div>
  );
}
