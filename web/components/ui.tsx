import Link from "next/link";
import type { ReactNode } from "react";

export function Card({ title, subtitle, action, children, className = "" }: { title?: ReactNode; subtitle?: ReactNode; action?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <section className={`rounded-xl border border-line bg-surface p-5 ${className}`}>
      {(title || action) && (
        <div className="mb-3 flex flex-wrap items-start justify-between gap-2">
          <div>
            {title && <h2 className="font-semibold text-ink">{title}</h2>}
            {subtitle && <p className="mt-0.5 text-sm text-muted">{subtitle}</p>}
          </div>
          {action}
        </div>
      )}
      {children}
    </section>
  );
}

const TONES: Record<string, string> = {
  neutral: "bg-subtle text-muted border-line",
  good: "bg-good-soft text-good border-good/30",
  warn: "bg-warn-soft text-warn border-warn/30",
  bad: "bg-bad-soft text-bad border-bad/30",
  brand: "bg-brand-soft text-brand border-brand/30",
};

export function Badge({ tone = "neutral", children, title }: { tone?: keyof typeof TONES | string; children: ReactNode; title?: string }) {
  return <span title={title} className={`inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-medium ${TONES[tone] ?? TONES.neutral}`}>{children}</span>;
}

export function Notice({ tone = "warn", children }: { tone?: "warn" | "bad" | "good" | "brand"; children: ReactNode }) {
  const styles = { warn: "border-warn/30 bg-warn-soft text-warn", bad: "border-bad/30 bg-bad-soft text-bad", good: "border-good/30 bg-good-soft text-good", brand: "border-brand/30 bg-brand-soft text-brand" };
  return <div role={tone === "bad" ? "alert" : "status"} className={`rounded-lg border p-3 text-sm ${styles[tone]}`}>{children}</div>;
}

export function Meter({ value, target, mastered = 0.85, label }: { value: number; target?: number | null; mastered?: number; label?: string }) {
  const width = Math.max(2, Math.min(100, value * 100));
  const color = value >= mastered ? "bg-good" : target && value >= target ? "bg-brand" : value < 0.4 ? "bg-bad" : "bg-warn";
  return (
    <div className="relative h-2.5 w-full rounded-full bg-subtle" role="meter" aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(value * 100)} aria-label={label}>
      <div className={`h-2.5 rounded-full ${color}`} style={{ width: `${width}%` }} />
      {target != null && <div className="absolute -top-1 h-4.5 w-0.5 bg-ink/70" style={{ left: `${target * 100}%`, height: "18px" }} title={`Goal target ${Math.round(target * 100)}%`} />}
    </div>
  );
}

export function Button({ children, onClick, disabled, kind = "primary", type = "button", className = "" }: { children: ReactNode; onClick?: () => void; disabled?: boolean; kind?: "primary" | "secondary" | "ghost"; type?: "button" | "submit"; className?: string }) {
  const styles = {
    primary: "bg-brand text-white hover:bg-brand-strong",
    secondary: "border border-line bg-surface text-ink hover:border-brand",
    ghost: "text-brand hover:underline",
  };
  return <button type={type} onClick={onClick} disabled={disabled} className={`rounded-lg px-4 py-2 text-sm font-semibold transition disabled:cursor-not-allowed disabled:opacity-50 ${styles[kind]} ${className}`}>{children}</button>;
}

export function NeedStudent() {
  return (
    <Card title="Choose a student profile first">
      <p className="text-sm text-muted">Pick one of the sample profiles or create your own to see a personalised plan.</p>
      <div className="mt-4 flex gap-2">
        <Link href="/" className="rounded-lg bg-brand px-4 py-2 text-sm font-semibold text-white">Pick a profile</Link>
        <Link href="/onboarding" className="rounded-lg border border-line px-4 py-2 text-sm font-semibold">Create my profile</Link>
      </div>
    </Card>
  );
}

export function Loading({ label = "Loading..." }: { label?: string }) {
  return <p className="animate-pulse text-sm text-muted">{label}</p>;
}

export const SLOT_TONE: Record<string, string> = { elective: "brand", lateral: "good", additional: "warn", backlog: "bad" };
export const SLOT_LABEL: Record<string, string> = { elective: "Elective slot", lateral: "Lateral slot", additional: "Additional credit", backlog: "Backlog" };
