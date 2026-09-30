export const inr = (v: number | null | undefined, digits = 0) =>
  v == null ? "–" : `₹${v.toLocaleString("en-IN", { maximumFractionDigits: digits, minimumFractionDigits: digits })}`;

export const num = (v: number | null | undefined, digits = 1) =>
  v == null ? "–" : v.toLocaleString("en-IN", { maximumFractionDigits: digits, minimumFractionDigits: digits });

export const int = (v: number | null | undefined) => (v == null ? "–" : v.toLocaleString("en-IN"));

export const pct = (v: number | null | undefined, digits = 2) =>
  v == null ? "–" : `${v > 0 ? "+" : v < 0 ? "−" : ""}${Math.abs(v).toFixed(digits)}%`;

export const dateTime = (iso: string | null | undefined) => {
  if (!iso) return "–";
  const d = new Date(iso);
  return d.toLocaleString("en-IN", { dateStyle: "medium", timeStyle: "short", timeZone: "Asia/Kolkata" }) + " IST";
};

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/** Short axis label for a period key: 2026-09 -> "Sep 26", 2026-09-28 -> "28 Sep", 2026-W40 -> "W40 26". */
export const periodLabel = (p: string) => {
  if (/^\d{4}-\d{2}$/.test(p)) return `${MONTHS[+p.slice(5, 7) - 1]} ${p.slice(2, 4)}`;
  if (/^\d{4}-\d{2}-\d{2}$/.test(p)) return `${+p.slice(8, 10)} ${MONTHS[+p.slice(5, 7) - 1]}`;
  if (/^\d{4}-W\d{2}$/.test(p)) return `${p.slice(5)} ’${p.slice(2, 4)}`;
  return p;
};
