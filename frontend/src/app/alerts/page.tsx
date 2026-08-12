"use client";

import { FormEvent, useEffect, useState } from "react";
import Link from "next/link";
import { api, type Alert } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { Badge, Panel, SectionTitle } from "@/components/ui";

export default function AlertsPage() {
  const { token } = useAuth();
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [symbol, setSymbol] = useState("NVDA");
  const [condition, setCondition] = useState("above");
  const [threshold, setThreshold] = useState(120);
  const [message, setMessage] = useState("");
  const [status, setStatus] = useState<string | null>(null);

  async function refresh() {
    if (!token) return;
    setAlerts(await api.alerts(token));
  }

  useEffect(() => {
    refresh().catch(() => undefined);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  async function onCreate(e: FormEvent) {
    e.preventDefault();
    if (!token) return;
    await api.createAlert(token, {
      symbol,
      condition,
      threshold: condition === "above" || condition === "below" ? threshold : undefined,
      message,
    });
    setMessage("");
    setStatus("Alert created");
    await refresh();
  }

  async function onEvaluate() {
    if (!token) return;
    const fired = await api.evaluateAlerts(token);
    setStatus(fired.length ? `${fired.length} alert(s) triggered` : "No alerts triggered");
    await refresh();
  }

  if (!token) {
    return (
      <Panel>
        <SectionTitle title="Alert desk" subtitle="Sign in required" />
        <Link href="/login" className="inline-flex rounded-md bg-ink-900 px-4 py-2 text-sm font-medium text-white">
          Sign in
        </Link>
      </Panel>
    );
  }

  return (
    <div className="space-y-6">
      <div>
        <p className="text-xs font-semibold uppercase tracking-[0.22em] text-signal-accent">Alerts</p>
        <h1 className="mt-2 font-display text-4xl tracking-tight text-ink-950">Threshold & signal alerts</h1>
      </div>

      <div className="grid gap-5 lg:grid-cols-5">
        <Panel className="lg:col-span-2">
          <SectionTitle title="Create alert" />
          <form onSubmit={onCreate} className="space-y-3">
            <label className="block text-sm">
              <span className="text-ink-500">Symbol</span>
              <input
                className="mt-1 w-full rounded-md border border-ink-200 px-3 py-2 uppercase"
                value={symbol}
                onChange={(e) => setSymbol(e.target.value)}
              />
            </label>
            <label className="block text-sm">
              <span className="text-ink-500">Condition</span>
              <select
                className="mt-1 w-full rounded-md border border-ink-200 px-3 py-2"
                value={condition}
                onChange={(e) => setCondition(e.target.value)}
              >
                <option value="above">Price above</option>
                <option value="below">Price below</option>
                <option value="bullish">Bullish signal</option>
                <option value="bearish">Bearish signal</option>
              </select>
            </label>
            {(condition === "above" || condition === "below") && (
              <label className="block text-sm">
                <span className="text-ink-500">Threshold</span>
                <input
                  type="number"
                  className="mt-1 w-full rounded-md border border-ink-200 px-3 py-2"
                  value={threshold}
                  onChange={(e) => setThreshold(Number(e.target.value))}
                />
              </label>
            )}
            <label className="block text-sm">
              <span className="text-ink-500">Message</span>
              <input
                className="mt-1 w-full rounded-md border border-ink-200 px-3 py-2"
                value={message}
                onChange={(e) => setMessage(e.target.value)}
                placeholder="Optional note"
              />
            </label>
            <button type="submit" className="w-full rounded-md bg-ink-900 px-4 py-2.5 text-sm font-semibold text-white">
              Save alert
            </button>
          </form>
          <button
            onClick={onEvaluate}
            className="mt-3 w-full rounded-md border border-ink-200 bg-white px-4 py-2.5 text-sm font-medium text-ink-800"
          >
            Evaluate now
          </button>
          {status ? <p className="mt-3 text-sm text-signal-accent">{status}</p> : null}
        </Panel>

        <Panel className="lg:col-span-3">
          <SectionTitle title="Active alerts" subtitle={`${alerts.length} configured`} />
          <div className="space-y-3">
            {alerts.length === 0 ? (
              <p className="text-sm text-ink-500">No alerts yet.</p>
            ) : (
              alerts.map((a) => (
                <div key={a.id} className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-ink-100 bg-ink-50/60 px-4 py-3">
                  <div>
                    <div className="font-semibold text-ink-900">
                      {a.symbol} · {a.condition}
                      {a.threshold != null ? ` ${a.threshold}` : ""}
                    </div>
                    <div className="text-sm text-ink-500">{a.message || "No message"}</div>
                    <div className="mt-1 text-xs text-ink-400">
                      {a.last_triggered_at
                        ? `Last fired ${new Date(a.last_triggered_at).toLocaleString()}`
                        : "Not triggered"}
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <Badge tone={a.triggered ? "warn" : "neutral"}>{a.triggered ? "triggered" : "armed"}</Badge>
                    <button
                      onClick={async () => {
                        await api.deleteAlert(token, a.id);
                        await refresh();
                      }}
                      className="rounded-md border border-ink-200 bg-white px-2.5 py-1 text-xs text-ink-600"
                    >
                      Delete
                    </button>
                  </div>
                </div>
              ))
            )}
          </div>
        </Panel>
      </div>
    </div>
  );
}
