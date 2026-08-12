"use client";

import { useEffect, useMemo, useState } from "react";
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { api, fmtCompact, fmtNum, fmtPct, type Quote } from "@/lib/api";
import { Panel, SectionTitle, Stat } from "@/components/ui";

export default function MarketsPage() {
  const [quotes, setQuotes] = useState<Quote[]>([]);
  const [symbol, setSymbol] = useState("AAPL");
  const [candles, setCandles] = useState<{ t: string; c: number; v: number }[]>([]);
  const [indicators, setIndicators] = useState<{
    rsi: number;
    sma_20: number;
    sma_50: number;
    macd: number;
    macd_signal: number;
    volatility: number;
    momentum: number;
  } | null>(null);

  useEffect(() => {
    let alive = true;
    async function load() {
      const q = await api.quotes();
      if (alive) setQuotes(q.filter((x) => x.sector !== "Index"));
    }
    load();
    const id = setInterval(load, 5000);
    return () => {
      alive = false;
      clearInterval(id);
    };
  }, []);

  useEffect(() => {
    let alive = true;
    async function load() {
      const [c, ind] = await Promise.all([api.candles(symbol, 90), api.indicators(symbol)]);
      if (!alive) return;
      setCandles(
        c.map((x) => ({
          t: new Date(x.t).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
          c: x.c,
          v: x.v,
        }))
      );
      setIndicators(ind);
    }
    load();
    const id = setInterval(load, 5000);
    return () => {
      alive = false;
      clearInterval(id);
    };
  }, [symbol]);

  const selected = useMemo(() => quotes.find((q) => q.symbol === symbol), [quotes, symbol]);

  return (
    <div className="space-y-6">
      <div>
        <p className="text-xs font-semibold uppercase tracking-[0.22em] text-signal-accent">Markets</p>
        <h1 className="mt-2 font-display text-4xl tracking-tight text-ink-950">Universe & microstructure</h1>
      </div>

      <div className="grid gap-5 lg:grid-cols-5">
        <Panel className="lg:col-span-2">
          <SectionTitle title="Watch universe" subtitle="Click a symbol to inspect" />
          <div className="max-h-[520px] space-y-1 overflow-y-auto pr-1">
            {quotes.map((q) => (
              <button
                key={q.symbol}
                onClick={() => setSymbol(q.symbol)}
                className={`flex w-full items-center justify-between rounded-lg px-3 py-2.5 text-left transition ${
                  symbol === q.symbol ? "bg-ink-900 text-white" : "hover:bg-ink-50"
                }`}
              >
                <div>
                  <div className="font-semibold">{q.symbol}</div>
                  <div className={`text-xs ${symbol === q.symbol ? "text-ink-300" : "text-ink-400"}`}>{q.sector}</div>
                </div>
                <div className="text-right">
                  <div className="font-mono text-sm tabular-nums">{fmtNum(q.price)}</div>
                  <div
                    className={`font-mono text-xs tabular-nums ${
                      q.change_pct >= 0
                        ? symbol === q.symbol
                          ? "text-emerald-300"
                          : "text-signal-up"
                        : symbol === q.symbol
                          ? "text-rose-300"
                          : "text-signal-down"
                    }`}
                  >
                    {fmtPct(q.change_pct)}
                  </div>
                </div>
              </button>
            ))}
          </div>
        </Panel>

        <div className="space-y-5 lg:col-span-3">
          <div className="grid gap-4 sm:grid-cols-4">
            <Panel>
              <Stat label="Last" value={selected ? fmtNum(selected.price) : "—"} />
            </Panel>
            <Panel delay={40}>
              <Stat
                label="Change"
                value={selected ? fmtPct(selected.change_pct) : "—"}
                tone={selected && selected.change_pct >= 0 ? "up" : "down"}
              />
            </Panel>
            <Panel delay={80}>
              <Stat label="High / Low" value={selected ? `${fmtNum(selected.high, 1)}` : "—"} hint={selected ? `L ${fmtNum(selected.low, 1)}` : undefined} />
            </Panel>
            <Panel delay={120}>
              <Stat label="Volume" value={selected ? fmtCompact(selected.volume) : "—"} />
            </Panel>
          </div>

          <Panel delay={160}>
            <SectionTitle title={`${symbol} price path`} subtitle="Rolling simulated session" />
            <div className="h-72">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={candles}>
                  <CartesianGrid stroke="#e4ebf0" vertical={false} />
                  <XAxis dataKey="t" tick={{ fontSize: 11, fill: "#6a8aa4" }} minTickGap={30} />
                  <YAxis domain={["auto", "auto"]} tick={{ fontSize: 11, fill: "#6a8aa4" }} width={56} />
                  <Tooltip contentStyle={{ borderRadius: 10, borderColor: "#c7d5e0" }} />
                  <Line type="monotone" dataKey="c" stroke="#1a2633" strokeWidth={2} dot={false} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </Panel>

          <Panel delay={200}>
            <SectionTitle title="Technical snapshot" />
            <div className="grid gap-4 sm:grid-cols-4">
              <Stat label="RSI" value={indicators ? indicators.rsi.toFixed(1) : "—"} />
              <Stat label="SMA 20 / 50" value={indicators ? `${fmtNum(indicators.sma_20, 1)}` : "—"} hint={indicators ? `50: ${fmtNum(indicators.sma_50, 1)}` : undefined} />
              <Stat label="MACD" value={indicators ? indicators.macd.toFixed(3) : "—"} hint={indicators ? `Signal ${indicators.macd_signal.toFixed(3)}` : undefined} />
              <Stat label="Momentum" value={indicators ? fmtPct(indicators.momentum) : "—"} tone={indicators && indicators.momentum >= 0 ? "up" : "down"} />
            </div>
          </Panel>
        </div>
      </div>
    </div>
  );
}
