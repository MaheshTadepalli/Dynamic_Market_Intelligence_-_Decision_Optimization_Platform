"use client";

import { useEffect, useState } from "react";
import { api, fmtPct, type IntelligenceSignal } from "@/lib/api";
import { Badge, Panel, SectionTitle, Stat } from "@/components/ui";

export default function IntelligencePage() {
  const [signals, setSignals] = useState<IntelligenceSignal[]>([]);
  const [sectors, setSectors] = useState<{ sector: string; change_pct: number; count: number }[]>([]);
  const [overviewRegime, setOverviewRegime] = useState({ regime: "—", score: 0 });

  useEffect(() => {
    let alive = true;
    async function load() {
      const [sig, sec, ov] = await Promise.all([api.signals(), api.sectors(), api.overview()]);
      if (!alive) return;
      setSignals(sig);
      setSectors(sec);
      setOverviewRegime({ regime: ov.regime, score: ov.regime_score });
    }
    load();
    const id = setInterval(load, 6000);
    return () => {
      alive = false;
      clearInterval(id);
    };
  }, []);

  const bullish = signals.filter((s) => s.signal === "bullish").length;
  const bearish = signals.filter((s) => s.signal === "bearish").length;

  return (
    <div className="space-y-6">
      <div>
        <p className="text-xs font-semibold uppercase tracking-[0.22em] text-signal-accent">Intelligence</p>
        <h1 className="mt-2 font-display text-4xl tracking-tight text-ink-950">Signal engine & sector heat</h1>
      </div>

      <div className="grid gap-4 md:grid-cols-4">
        <Panel>
          <Stat label="Regime" value={overviewRegime.regime.split("/")[0].trim()} tone="accent" />
        </Panel>
        <Panel delay={40}>
          <Stat label="Score" value={overviewRegime.score.toFixed(2)} tone={overviewRegime.score >= 0 ? "up" : "down"} />
        </Panel>
        <Panel delay={80}>
          <Stat label="Bullish" value={String(bullish)} tone="up" />
        </Panel>
        <Panel delay={120}>
          <Stat label="Bearish" value={String(bearish)} tone="down" />
        </Panel>
      </div>

      <Panel delay={160}>
        <SectionTitle title="Sector heatmap" subtitle="Average session change by sector" />
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {sectors.map((s) => {
            const intensity = Math.min(1, Math.abs(s.change_pct) / 2);
            const up = s.change_pct >= 0;
            return (
              <div
                key={s.sector}
                className="rounded-lg border border-ink-100 p-4"
                style={{
                  background: up
                    ? `rgba(15,138,95,${0.08 + intensity * 0.25})`
                    : `rgba(196,60,60,${0.08 + intensity * 0.25})`,
                }}
              >
                <div className="text-sm font-semibold text-ink-900">{s.sector}</div>
                <div className={`mt-2 font-mono text-2xl tabular-nums ${up ? "text-signal-up" : "text-signal-down"}`}>
                  {fmtPct(s.change_pct)}
                </div>
                <div className="mt-1 text-xs text-ink-500">{s.count} names</div>
              </div>
            );
          })}
        </div>
      </Panel>

      <Panel delay={200}>
        <SectionTitle title="Ranked intelligence signals" subtitle="RSI · MACD · SMA structure · momentum" />
        <div className="grid gap-3 lg:grid-cols-2">
          {signals.map((s) => (
            <div key={s.symbol} className="rounded-xl border border-ink-100 bg-ink-50/50 p-4">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="font-display text-xl text-ink-950">{s.symbol}</div>
                <div className="flex gap-2">
                  <Badge tone={s.signal === "bullish" ? "up" : s.signal === "bearish" ? "down" : "neutral"}>
                    {s.signal}
                  </Badge>
                  <Badge tone={s.risk_level === "high" ? "warn" : "neutral"}>{s.risk_level} risk</Badge>
                </div>
              </div>
              <p className="mt-2 text-sm text-ink-600">{s.summary}</p>
              <ul className="mt-3 space-y-1 text-sm text-ink-500">
                {s.drivers.map((d) => (
                  <li key={d}>• {d}</li>
                ))}
              </ul>
              <div className="mt-3 flex gap-4 font-mono text-xs text-ink-400">
                <span>score {s.score.toFixed(2)}</span>
                <span>conf {(s.confidence * 100).toFixed(0)}%</span>
                <span>{s.horizon}</span>
              </div>
            </div>
          ))}
        </div>
      </Panel>
    </div>
  );
}
