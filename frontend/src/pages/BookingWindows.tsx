import { useEffect, useState } from "react";
import { type IndexSeries, getJSON, useApi } from "../api";
import { useMeta } from "../App";
import { LineSeriesChart, SimpleBarChart, mergeSeries } from "../components/charts";
import { Card, DataLabel, ErrorBox, Segmented } from "../components/ui";
import { inr, int, num, pct } from "../format";

interface Compare {
  route: string;
  date_from: string;
  date_to: string;
  windows: { window: string; lead_days: number; geometric_mean_fare: number; min_fare: number; max_fare: number; observations: number; premium_vs_longest_window_pct: number | null }[];
}

type Freq = "weekly" | "monthly";

export default function BookingWindows() {
  const meta = useMeta();
  const [route, setRoute] = useState("");
  const [freq, setFreq] = useState<Freq>("monthly");
  const compare = useApi<Compare>("fares/booking-window/compare", { route: route || undefined });
  const [series, setSeries] = useState<IndexSeries[]>([]);
  const windows = meta?.booking_windows ?? [];

  useEffect(() => {
    if (!windows.length) return;
    let cancelled = false;
    Promise.all(windows.map((w) => getJSON<IndexSeries>("/api/v1/index/booking-window", { lead_days: w.days, frequency: freq })))
      .then((s) => !cancelled && setSeries(s))
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [windows.length, freq]);

  return (
    <>
      <div className="page-head">
        <div>
          <h1>
            Booking-window analysis <DataLabel label={series[0]?.data_label} />
          </h1>
          <div className="muted small">How the fare depends on how many days before travel the ticket is bought (T+1 … T+45).</div>
        </div>
        <label className="field">
          Route
          <select value={route} onChange={(e) => setRoute(e.target.value)}>
            <option value="">All routes</option>
            {(meta?.routes ?? []).map((r) => (
              <option key={r}>{r}</option>
            ))}
          </select>
        </label>
      </div>

      <div className="grid two">
        <Card title="Average fare by booking window" subtitle={compare.data ? `${compare.data.route}, ${compare.data.date_from} → ${compare.data.date_to}` : undefined}>
          <ErrorBox error={compare.error} />
          {compare.data && (
            <SimpleBarChart
              rows={compare.data.windows.map((w) => ({ window: w.window, fare: w.geometric_mean_fare }))}
              xKey="window"
              yKey="fare"
              label="Geometric-mean fare (INR)"
              format={(v) => inr(v)}
              caption="Last 30 observation days"
            />
          )}
        </Card>
        <Card title="Premium over buying at T+45" subtitle="How much more a late purchase costs">
          {compare.data && (
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Window</th>
                    <th className="num">Avg fare</th>
                    <th className="num">Range</th>
                    <th className="num">Premium</th>
                    <th className="num">Observations</th>
                  </tr>
                </thead>
                <tbody>
                  {compare.data.windows.map((w) => (
                    <tr key={w.window}>
                      <td>{w.window}</td>
                      <td className="num">{inr(w.geometric_mean_fare)}</td>
                      <td className="num muted">
                        {inr(w.min_fare)} – {inr(w.max_fare)}
                      </td>
                      <td className="num">{pct(w.premium_vs_longest_window_pct, 1)}</td>
                      <td className="num">{int(w.observations)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>
      </div>

      <div style={{ height: 14 }} />

      <Card
        title="Booking-window price indices"
        subtitle={`${meta?.default_methodology ?? "LASPEYRES"} across routes, each window against its own ${meta?.base_year ?? 2024} level (= 100)`}
        actions={<Segmented label="Frequency" value={freq} onChange={setFreq} options={[{ value: "weekly", label: "Weekly" }, { value: "monthly", label: "Monthly" }]} />}
      >
        {series.length > 0 && (
          <LineSeriesChart
            rows={mergeSeries(series.map((s) => ({ key: s.scope_key, points: s.points })))}
            series={series.map((s) => ({ key: s.scope_key, label: s.scope_key }))}
            referenceY={100}
            height={320}
            caption="Index points; a window above 100 is dearer than its own base-year level"
          />
        )}
        <p className="small muted" style={{ marginTop: 8 }}>
          Latest values: {series.map((s) => `${s.scope_key} ${num(s.points.at(-1)?.value, 1)}`).join(" · ")}
        </p>
      </Card>
    </>
  );
}
