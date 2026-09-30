import { useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { periodLabel } from "../format";
import { SERIES_COLORS } from "./ui";

export interface SeriesDef {
  key: string;
  label: string;
  color?: string;
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type Row = Record<string, any>;

const axisProps = {
  stroke: "var(--axis)",
  tick: { fill: "var(--muted)", fontSize: 11 },
  tickLine: false,
};

function Legend({ series }: { series: SeriesDef[] }) {
  if (series.length < 2) return null;
  return (
    <div className="legend" aria-hidden="true">
      {series.map((s, i) => (
        <span key={s.key}>
          <i style={{ background: s.color ?? SERIES_COLORS[i] }} />
          {s.label}
        </span>
      ))}
    </div>
  );
}

function TooltipBox({ active, payload, label, format, labelFormat }: any) {
  if (!active || !payload?.length) return null;
  return (
    <div className="tooltip">
      <div className="t-title">{labelFormat ? labelFormat(label) : label}</div>
      {payload.map((p: any) => (
        <div className="t-row" key={p.dataKey}>
          <span>
            <i style={{ background: p.color }} />
            {p.name}
          </span>
          <strong className="tnum">{p.value == null ? "–" : format(p.value)}</strong>
        </div>
      ))}
    </div>
  );
}

function DataTable({ rows, xKey, series, format }: { rows: Row[]; xKey: string; series: SeriesDef[]; format: (v: number) => string }) {
  return (
    <div className="table-wrap" style={{ maxHeight: 320, overflowY: "auto" }}>
      <table>
        <thead>
          <tr>
            <th>Period</th>
            {series.map((s) => (
              <th key={s.key} className="num">
                {s.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {[...rows].reverse().map((r) => (
            <tr key={String(r[xKey])}>
              <td>{String(r[xKey])}</td>
              {series.map((s) => (
                <td key={s.key} className="num">
                  {r[s.key] == null ? "–" : format(Number(r[s.key]))}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** Multi-series line chart on ONE axis, with crosshair tooltip, legend, and a table view. */
export function LineSeriesChart({
  rows,
  xKey = "period",
  series,
  height = 280,
  format = (v: number) => v.toFixed(1),
  referenceY,
  referenceLabel,
  caption,
  yDomain,
}: {
  rows: Row[];
  xKey?: string;
  series: SeriesDef[];
  height?: number;
  format?: (v: number) => string;
  referenceY?: number;
  referenceLabel?: string;
  caption?: string;
  yDomain?: [number | string, number | string];
}) {
  const [table, setTable] = useState(false);
  return (
    <div>
      <Legend series={series} />
      {table ? (
        <DataTable rows={rows} xKey={xKey} series={series} format={format} />
      ) : (
        <div style={{ width: "100%", height }} role="img" aria-label={caption ?? series.map((s) => s.label).join(", ")}>
          <ResponsiveContainer>
            <LineChart data={rows} margin={{ top: 8, right: 12, bottom: 0, left: 0 }}>
              <CartesianGrid stroke="var(--grid)" vertical={false} />
              <XAxis dataKey={xKey} {...axisProps} tickFormatter={periodLabel} minTickGap={24} />
              <YAxis {...axisProps} width={48} domain={yDomain ?? ["auto", "auto"]} tickFormatter={(v) => format(v)} axisLine={false} />
              {referenceY != null && (
                <ReferenceLine y={referenceY} stroke="var(--axis)" strokeDasharray="4 4" label={{ value: referenceLabel, fill: "var(--muted)", fontSize: 11, position: "insideTopLeft" }} />
              )}
              <Tooltip content={<TooltipBox format={format} />} cursor={{ stroke: "var(--axis)", strokeWidth: 1 }} />
              {series.map((s, i) => (
                <Line
                  key={s.key}
                  type="monotone"
                  dataKey={s.key}
                  name={s.label}
                  stroke={s.color ?? SERIES_COLORS[i]}
                  strokeWidth={2}
                  dot={false}
                  activeDot={{ r: 4, strokeWidth: 2, stroke: "var(--surface)" }}
                  connectNulls
                  isAnimationActive={false}
                />
              ))}
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}
      <div className="chart-foot">
        <span>{caption}</span>
        <button className="link-btn" onClick={() => setTable((t) => !t)}>
          {table ? "Show chart" : "Show table"}
        </button>
      </div>
    </div>
  );
}

/** Single-measure bar chart (one colour: bars are not categorical identities). */
export function SimpleBarChart({
  rows,
  xKey,
  yKey,
  label,
  height = 240,
  format = (v: number) => v.toFixed(0),
  colorFor,
  caption,
}: {
  rows: Row[];
  xKey: string;
  yKey: string;
  label: string;
  height?: number;
  format?: (v: number) => string;
  colorFor?: (row: Row) => string;
  caption?: string;
}) {
  const [table, setTable] = useState(false);
  return (
    <div>
      {table ? (
        <DataTable rows={rows} xKey={xKey} series={[{ key: yKey, label }]} format={format} />
      ) : (
        <div style={{ width: "100%", height }} role="img" aria-label={caption ?? label}>
          <ResponsiveContainer>
            <BarChart data={rows} margin={{ top: 16, right: 12, bottom: 0, left: 0 }} barCategoryGap="28%">
              <CartesianGrid stroke="var(--grid)" vertical={false} />
              <XAxis dataKey={xKey} {...axisProps} />
              <YAxis {...axisProps} width={56} tickFormatter={(v) => format(v)} axisLine={false} />
              <Tooltip content={<TooltipBox format={format} />} cursor={{ fill: "var(--surface-2)" }} />
              <Bar dataKey={yKey} name={label} radius={[4, 4, 0, 0]} isAnimationActive={false} label={{ position: "top", fill: "var(--ink-2)", fontSize: 11, formatter: (v: number) => format(v) }}>
                {rows.map((r, i) => (
                  <Cell key={i} fill={colorFor ? colorFor(r) : "var(--s1)"} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}
      <div className="chart-foot">
        <span>{caption}</span>
        <button className="link-btn" onClick={() => setTable((t) => !t)}>
          {table ? "Show chart" : "Show table"}
        </button>
      </div>
    </div>
  );
}

/** Merge several index series into rows keyed by period for a multi-line chart. */
export function mergeSeries(named: { key: string; points: { period: string; value: number }[] }[]): Row[] {
  const rows = new Map<string, Row>();
  for (const s of named) {
    for (const p of s.points) {
      const row = rows.get(p.period) ?? { period: p.period };
      row[s.key] = p.value;
      rows.set(p.period, row);
    }
  }
  return [...rows.values()].sort((a, b) => String(a.period).localeCompare(String(b.period)));
}
