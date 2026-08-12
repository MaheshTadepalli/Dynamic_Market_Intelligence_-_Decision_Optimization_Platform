import clsx from "clsx";

export function Panel({
  children,
  className,
  delay = 0,
}: {
  children: React.ReactNode;
  className?: string;
  delay?: number;
}) {
  return (
    <section
      className={clsx(
        "animate-rise rounded-xl border border-ink-200/80 bg-white/75 p-5 shadow-panel backdrop-blur-sm",
        className
      )}
      style={{ animationDelay: `${delay}ms` }}
    >
      {children}
    </section>
  );
}

export function SectionTitle({
  title,
  subtitle,
  action,
}: {
  title: string;
  subtitle?: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="mb-4 flex items-start justify-between gap-4">
      <div>
        <h2 className="font-display text-2xl tracking-tight text-ink-950">{title}</h2>
        {subtitle ? <p className="mt-1 text-sm text-ink-500">{subtitle}</p> : null}
      </div>
      {action}
    </div>
  );
}

export function Stat({
  label,
  value,
  hint,
  tone = "neutral",
}: {
  label: string;
  value: string;
  hint?: string;
  tone?: "up" | "down" | "neutral" | "accent";
}) {
  return (
    <div>
      <div className="text-xs uppercase tracking-[0.14em] text-ink-400">{label}</div>
      <div
        className={clsx(
          "mt-1 font-mono text-2xl font-semibold tabular-nums",
          tone === "up" && "text-signal-up",
          tone === "down" && "text-signal-down",
          tone === "accent" && "text-signal-accent",
          tone === "neutral" && "text-ink-900"
        )}
      >
        {value}
      </div>
      {hint ? <div className="mt-1 text-xs text-ink-450 text-ink-500">{hint}</div> : null}
    </div>
  );
}

export function Badge({
  children,
  tone = "neutral",
}: {
  children: React.ReactNode;
  tone?: "up" | "down" | "warn" | "neutral";
}) {
  return (
    <span
      className={clsx(
        "inline-flex items-center rounded px-2 py-0.5 text-xs font-semibold uppercase tracking-wide",
        tone === "up" && "bg-emerald-50 text-signal-up",
        tone === "down" && "bg-rose-50 text-signal-down",
        tone === "warn" && "bg-amber-50 text-signal-warn",
        tone === "neutral" && "bg-ink-100 text-ink-600"
      )}
    >
      {children}
    </span>
  );
}
