import { useState } from "react";
import { Link } from "react-router-dom";
import { type IndexPoint, useApi } from "../api";
import { LineSeriesChart, SimpleBarChart } from "../components/charts";
import { Card, DataLabel, Delta, ErrorBox, Kpi, Loading, Segmented } from "../components/ui";
import { dateTime, inr, int, num, periodLabel } from "../format";

interface Mover {
  route: string;
  latest_value: number;
  latest_price?: number;
  change_30d_pct: number | null;
}

interface Overview {
  index_available: boolean;
  data_label?: string;
  methodology?: string;
  base_year?: number;
  calculated_at?: string;
  weighting?: { version: string; label: string };
  current_index?: IndexPoint;
  change_1d_pct?: number | null;
  change_7d_pct?: number | null;
  change_mom_pct?: number | null;
  change_yoy_pct?: number | null;
  daily_trend?: IndexPoint[];
  weekly_trend?: IndexPoint[];
  monthly_trend?: IndexPoint[];
  top_increases?: Mover[];
  top_decreases?: Mover[];
  routes?: Mover[];
  booking_windows?: { window: string; latest_value: number | null; latest_period: string | null }[];
  quality?: { observation_count: number; valid_observation_count: number; excluded_observation_count: number; by_quality_status: Record<string, number> };
  active_sources: { source_id: string; display_name: string; data_provenance: string }[];
  last_collection_at: string | null;
  observation_period?: { first: string; last: string };
}

interface WindowCompare {
  windows: { window: string; geometric_mean_fare: number; premium_vs_longest_window_pct: number | null }[];
  date_from: string;
  date_to: string;
}

type Trend = "daily" | "weekly" | "monthly";

function MoverList({ items, empty }: { items: Mover[]; empty: string }) {
  if (!items.length) return <p className="muted small">{empty}</p>;
  return (
    <table>
      <tbody>
        {items.map((m) => (
          <tr key={m.route}>
            <td>
              <Link to={`/routes?route=${m.route}`}>{m.route}</Link>
            </td>
            <td className="num">{inr(m.latest_price)}</td>
            <td className="num">
              <Delta value={m.change_30d_pct} />
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export default function Overview() {
  const { data, error, loading } = useApi<Overview>("stats/overview");
  const windows = useApi<WindowCompare>("fares/booking-window/compare");
  const [trend, setTrend] = useState<Trend>("daily");

  if (loading) return <Loading what="overview" />;
  if (error) return <ErrorBox error={error} />;
  if (!data) return null;
  if (!data.index_available) {
    return (
      <Card title="No index computed yet">
        <p>Seed the demo history and compute the index: <code>python -m app.cli seed-demo</code></p>
      </Card>
    );
  }

  const trendPoints = (trend === "daily" ? data.daily_trend : trend === "weekly" ? data.weekly_trend : data.monthly_trend) ?? [];
  const q = data.quality!;
  const cur = data.current_index!;
  const validPct = q.observation_count ? (100 * q.valid_observation_count) / q.observation_count : 0;

  return (
    <>
      <div className="page-head">
        <div>
          <h1>
            Airfare Price Index — Overview <DataLabel label={data.data_label} />
          </h1>
          <div className="muted small">
            {data.methodology} index over 6 domestic routes · base {data.base_year} = 100 · weights {data.weighting?.version} ({data.weighting?.label}) · computed {dateTime(data.calculated_at)}
          </div>
        </div>
      </div>

      <div className="grid kpis">
        <Kpi label="Current index" value={num(cur.value, 1)} sub={`${periodLabel(cur.period)} · base ${data.base_year} = 100`} />
        <Kpi label="Change vs previous day" value={<Delta value={data.change_1d_pct} />} sub={<>7-day: <Delta value={data.change_7d_pct} /></>} />
        <Kpi label="Month on month" value={<Delta value={data.change_mom_pct} />} sub={<>Year on year: <Delta value={data.change_yoy_pct} /></>} />
        <Kpi label="Observations" value={int(q.observation_count)} sub={`${num(validPct, 1)}% passed quality checks`} />
        <Kpi label="Active sources" value={data.active_sources.length} sub={data.active_sources.map((s) => `${s.source_id} (${s.data_provenance})`).join(", ") || "none"} />
        <Kpi label="Last collection" value={<span style={{ fontSize: "1rem" }}>{dateTime(data.last_collection_at)}</span>} sub={`Observed ${data.observation_period?.first} → ${data.observation_period?.last}`} />
      </div>

      <div className="grid two" style={{ marginBottom: 14 }}>
        <Card
          title="Index trend"
          subtitle={`${data.methodology}, all routes and booking windows`}
          actions={
            <Segmented<Trend>
              label="Trend frequency"
              value={trend}
              onChange={setTrend}
              options={[
                { value: "daily", label: "Daily (90d)" },
                { value: "weekly", label: "Weekly" },
                { value: "monthly", label: "Monthly" },
              ]}
            />
          }
        >
          <LineSeriesChart rows={trendPoints} series={[{ key: "value", label: "Index" }]} referenceY={100} referenceLabel={`${data.base_year} = 100`} caption="Index points (base year = 100)" />
        </Card>
        <Card title="Booking-window effect" subtitle={windows.data ? `Average fare by days before travel, ${windows.data.date_from} → ${windows.data.date_to}` : undefined}>
          {windows.data ? (
            <SimpleBarChart
              rows={windows.data.windows.map((w) => ({ window: w.window, fare: w.geometric_mean_fare }))}
              xKey="window"
              yKey="fare"
              label="Geometric-mean fare (INR)"
              format={(v) => inr(v)}
              caption="All routes, geometric mean of valid fares"
            />
          ) : (
            <ErrorBox error={windows.error} />
          )}
          {windows.data && (
            <p className="small muted" style={{ marginTop: 6 }}>
              Buying at T+1 cost {num(windows.data.windows[0]?.premium_vs_longest_window_pct ?? null, 0)}% more than at T+45 over this period.
            </p>
          )}
        </Card>
      </div>

      <div className="grid three">
        <Card title="Largest 30-day increases" subtitle="Route index, latest vs 30 days earlier">
          <MoverList items={data.top_increases ?? []} empty="No route rose." />
        </Card>
        <Card title="Largest 30-day decreases">
          <MoverList items={(data.top_decreases ?? []).filter((m) => (m.change_30d_pct ?? 0) < 0)} empty="No route fell over the last 30 days." />
        </Card>
        <Card title="Data quality" subtitle="Every observation is kept; only VALIDATED / PROVISIONAL enter the index">
          <table>
            <tbody>
              {Object.entries(q.by_quality_status)
                .sort((a, b) => b[1] - a[1])
                .map(([status, n]) => (
                  <tr key={status}>
                    <td>{status}</td>
                    <td className="num">{int(n)}</td>
                    <td className="num muted">{num((100 * n) / q.observation_count, 2)}%</td>
                  </tr>
                ))}
            </tbody>
          </table>
          <p className="small" style={{ marginTop: 8 }}>
            <Link to="/quality">Open quality monitor →</Link>
          </p>
        </Card>
      </div>
    </>
  );
}
