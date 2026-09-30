import type { ReactNode } from "react";
import type { ApiError } from "../api";

export const SERIES_COLORS = ["var(--s1)", "var(--s2)", "var(--s3)", "var(--s4)", "var(--s5)", "var(--s6)"];

export function Card({ title, subtitle, actions, children, className = "" }: { title?: ReactNode; subtitle?: ReactNode; actions?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <section className={`card ${className}`}>
      {(title || actions) && (
        <div className="card-head">
          <div>
            {title && <h2>{title}</h2>}
            {subtitle && <div className="muted small">{subtitle}</div>}
          </div>
          {actions && <div className="controls">{actions}</div>}
        </div>
      )}
      {children}
    </section>
  );
}

export function Kpi({ label, value, sub, tone }: { label: string; value: ReactNode; sub?: ReactNode; tone?: "up" | "down" }) {
  return (
    <div className="card kpi">
      <div className="label">{label}</div>
      <div className={`value tnum ${tone ?? ""}`}>{value}</div>
      {sub && <div className="sub">{sub}</div>}
    </div>
  );
}

export function DataLabel({ label }: { label?: string | null }) {
  if (!label) return null;
  return <span className={`badge ${label === "DEMO" ? "demo" : ""}`}>{label === "DEMO" ? "DEMO DATA" : label}</span>;
}

export function Loading({ what = "data" }: { what?: string }) {
  return <div className="loading">Loading {what}…</div>;
}

export function ErrorBox({ error }: { error: ApiError | Error | null }) {
  if (!error) return null;
  const code = (error as ApiError).code;
  if (code === "INDEX_NOT_COMPUTED") {
    return <div className="notice">The index has not been computed yet. Run <code>python -m app.cli seed-demo</code> (or wait for the scheduled job).</div>;
  }
  return <div className="notice error">Could not load: {error.message}</div>;
}

export function Segmented<T extends string>({ value, options, onChange, label }: { value: T; options: { value: T; label: string }[]; onChange: (v: T) => void; label?: string }) {
  return (
    <div className="seg" role="group" aria-label={label}>
      {options.map((o) => (
        <button key={o.value} className={o.value === value ? "on" : ""} aria-pressed={o.value === value} onClick={() => onChange(o.value)}>
          {o.label}
        </button>
      ))}
    </div>
  );
}

export function Delta({ value, digits = 2, invert = false }: { value: number | null | undefined; digits?: number; invert?: boolean }) {
  if (value == null) return <span className="muted">–</span>;
  const rising = value > 0;
  // For consumers a price rise is the "bad" direction; arrows + sign carry meaning, not colour alone.
  const cls = value === 0 ? "" : (rising !== invert ? "up" : "down");
  return (
    <span className={`tnum ${cls}`}>
      {value > 0 ? "▲" : value < 0 ? "▼" : "•"} {value > 0 ? "+" : value < 0 ? "−" : ""}
      {Math.abs(value).toFixed(digits)}%
    </span>
  );
}
