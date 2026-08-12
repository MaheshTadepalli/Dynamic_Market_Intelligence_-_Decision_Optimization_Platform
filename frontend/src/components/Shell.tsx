"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Activity, Bell, BrainCircuit, FlaskConical, LayoutDashboard, LogOut, Target } from "lucide-react";
import clsx from "clsx";
import { useAuth } from "@/lib/auth";

const nav = [
  { href: "/", label: "Command", icon: LayoutDashboard },
  { href: "/markets", label: "Markets", icon: Activity },
  { href: "/intelligence", label: "Intelligence", icon: BrainCircuit },
  { href: "/optimizer", label: "Optimizer", icon: Target },
  { href: "/lab", label: "Lab", icon: FlaskConical },
  { href: "/alerts", label: "Alerts", icon: Bell },
];

export function Shell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const { email, logout, token } = useAuth();

  return (
    <div className="min-h-screen bg-mesh">
      <div className="pointer-events-none fixed inset-0 bg-[url('data:image/svg+xml;utf8,<svg xmlns=%22http://www.w3.org/2000/svg%22 width=%2240%22 height=%2240%22 viewBox=%220 0 40 40%22><path d=%22M0 39.5h40M39.5 0v40%22 stroke=%22%231a2633%22 stroke-opacity=%220.04%22 fill=%22none%22/></svg>')] opacity-70" />
      <header className="relative z-20 border-b border-ink-200/70 bg-white/55 backdrop-blur-md">
        <div className="mx-auto flex max-w-[1400px] items-center justify-between gap-6 px-5 py-4">
          <Link href="/" className="group flex items-baseline gap-3">
            <span className="font-display text-3xl tracking-tight text-ink-950 transition group-hover:text-signal-accent">
              DMIDOP
            </span>
            <span className="hidden text-xs font-medium uppercase tracking-[0.18em] text-ink-400 sm:inline">
              Market Intelligence
            </span>
          </Link>
          <nav className="flex flex-wrap items-center gap-1">
            {nav.map((item) => {
              const Icon = item.icon;
              const active = pathname === item.href;
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className={clsx(
                    "inline-flex items-center gap-2 rounded-md px-3 py-2 text-sm font-medium transition",
                    active
                      ? "bg-ink-900 text-ink-50"
                      : "text-ink-600 hover:bg-ink-100 hover:text-ink-900"
                  )}
                >
                  <Icon size={15} />
                  {item.label}
                </Link>
              );
            })}
          </nav>
          <div className="flex items-center gap-3 text-sm">
            <span className="hidden items-center gap-2 text-ink-500 md:inline-flex">
              <span className="animate-pulse-dot inline-block h-2 w-2 rounded-full bg-signal-accent" />
              Live feed
            </span>
            {token ? (
              <button
                onClick={logout}
                className="inline-flex items-center gap-2 rounded-md border border-ink-200 bg-white/80 px-3 py-2 text-ink-700 hover:border-ink-400"
              >
                <LogOut size={14} />
                <span className="hidden sm:inline">{email}</span>
              </button>
            ) : (
              <Link
                href="/login"
                className="rounded-md bg-ink-900 px-3 py-2 font-medium text-white hover:bg-ink-800"
              >
                Sign in
              </Link>
            )}
          </div>
        </div>
      </header>
      <main className="relative z-10 mx-auto max-w-[1400px] px-5 py-8">{children}</main>
    </div>
  );
}
