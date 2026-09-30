import { useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { type IndexSeries, getJSON, useApi } from "../api";
import { LineSeriesChart, mergeSeries } from "../components/charts";
import { Card, DataLabel, ErrorBox, Loading, Segmented } from "../components/ui";
import { inr, int, num, pct } from "../format";

interface RouteRow {
  route_code: string;
  origin: { iata_code: string; city: string };
  destination: { iata_code: string; city: string };
  weight_share: number;
  weighting_label: string;
  valid_observations: number;
  last_observation_date: string | null;
}

interface DailyFares {
  route: string;
  windows: string[];
  series: Record<string, number | string>[];
}

interface WindowFare {
  window: string;
  lead_days: number;
  observation_date: string;
  observations: number;
  valid_observations: number;
  min_fare: number | null;
  median_fare: number | null;
  geometric_mean_fare: number | null;
  max_fare: number | null;
  by_airline: { airline_code: string; min_fare: number }[];
}

type Freq = "weekly" | "monthly";

export default function RoutesPage() {
  const [params, setParams] = useSearchParams();
  const route = params.get("route") ?? "DEL-BOM";
  const setRoute = (r: string) => setParams({ route: r });
  const [freq, setFreq] = useState<Freq>("monthly");
  const routes = useApi<RouteRow[]>("routes");
  const daily = useApi<DailyFares>("fares/daily", { route });
  const [allRoutes, setAllRoutes] = useState<Record<string, IndexSeries>>({});

  useEffect(() => {
    if (!routes.data) return;
    let cancelled = false;
    Promise.all(routes.data.map((r) => getJSON<IndexSeries>(`/api/v1/index/route/${r.route_code}`, { frequency: freq }).then((s) => [r.route_code, s] as const)))
      .then((pairs) => !cancelled && setAllRoutes(Object.fromEntries(pairs)))
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [routes.data, freq]);

  const latestObs = routes.data?.find((r) => r.route_code === route)?.last_observation_date;
  const [travelDate, setTravelDate] = useState<string>("");
  useEffect(() => {
    if (latestObs && !travelDate) setTravelDate(latestObs);
  }, [latestObs, travelDate]);
  const lookup = useApi<WindowFare[]>(travelDate ? "fares/booking-window" : null, { route, travel_date: travelDate });

  const comparisonRows = useMemo(
    () => mergeSeries(Object.entries(allRoutes).map(([k, s]) => ({ key: k, points: s.points }))),
    [allRoutes],
  );
  const routeCodes = routes.data?.map((r) => r.route_code) ?? [];

  return (
    <>
      <div className="page-head">
        <div>
          <h1>
            Route analysis <DataLabel label={Object.values(allRoutes)[0]?.data_label} />
          </h1>
          <div className="muted small">Route indices are elementary Jevons indices: geometric mean of carrier × booking-window price relatives vs the base year.</div>
        </div>
        <div className="controls">
          <label className="field">
            Route
            <select value={route} onChange={(e) => setRoute(e.target.value)}>
              {routeCodes.map((r) => (
                <option key={r}>{r}</option>
              ))}
            </select>
          </label>
          <Segmented label="Frequency" value={freq} onChange={setFreq} options={[{ value: "weekly", label: "Weekly" }, { value: "monthly", label: "Monthly" }]} />
        </div>
      </div>

      <Card title="All routes compared" subtitle={`${freq} route index, base = 100`}>
        {routes.loading && <Loading what="routes" />}
        <ErrorBox error={routes.error} />
        {comparisonRows.length > 0 && (
          <LineSeriesChart rows={comparisonRows} series={routeCodes.map((r) => ({ key: r, label: r }))} referenceY={100} height={320} caption="Six routes on one index axis" />
        )}
      </Card>

      <div style={{ height: 14 }} />

      <div className="grid two">
        <Card title={`${route}: daily fare by booking window`} subtitle="Geometric-mean valid fare per day, last 90 observation days">
          <ErrorBox error={daily.error} />
          {daily.data && (
            <LineSeriesChart
              rows={daily.data.series}
              xKey="date"
              series={daily.data.windows.map((w) => ({ key: w, label: w }))}
              format={(v) => inr(v)}
              caption="INR, one line per booking window"
            />
          )}
        </Card>

        <Card
          title="Fare for a travel date, by booking window"
          subtitle="What did this trip cost when bought X days before travel?"
          actions={
            <label className="field">
              Travel date
              <input type="date" value={travelDate} onChange={(e) => setTravelDate(e.target.value)} />
            </label>
          }
        >
          <ErrorBox error={lookup.error} />
          {lookup.data && (
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Window</th>
                    <th>Bought on</th>
                    <th className="num">Cheapest</th>
                    <th className="num">Median</th>
                    <th className="num">Highest</th>
                    <th className="num">Valid / seen</th>
                  </tr>
                </thead>
                <tbody>
                  {lookup.data.map((w) => (
                    <tr key={w.window}>
                      <td>{w.window}</td>
                      <td>{w.observation_date}</td>
                      <td className="num">{inr(w.min_fare)}</td>
                      <td className="num">{inr(w.median_fare)}</td>
                      <td className="num">{inr(w.max_fare)}</td>
                      <td className="num">
                        {w.valid_observations} / {w.observations}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <p className="small muted" style={{ marginTop: 8 }}>
            Windows with no observations were not collected (future dates, gaps) — nothing is imputed.{" "}
            <Link to={`/api-docs#trace`}>How to trace a value to its observations</Link>
          </p>
        </Card>
      </div>

      <div style={{ height: 14 }} />

      <Card title="Route master data" subtitle="Monitored basket and index weights">
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Route</th>
                <th>From</th>
                <th>To</th>
                <th className="num">Weight share</th>
                <th className="num">Latest index</th>
                <th className="num">Valid observations</th>
                <th>Last observed</th>
              </tr>
            </thead>
            <tbody>
              {routes.data?.map((r) => {
                const pts = allRoutes[r.route_code]?.points;
                const last = pts?.at(-1);
                const prev = pts?.at(-2);
                return (
                  <tr key={r.route_code}>
                    <td>
                      <button className="link-btn" onClick={() => setRoute(r.route_code)}>
                        {r.route_code}
                      </button>
                    </td>
                    <td>{r.origin.city}</td>
                    <td>{r.destination.city}</td>
                    <td className="num">
                      {pct(r.weight_share * 100, 1).replace("+", "")} <span className="badge demo">{r.weighting_label}</span>
                    </td>
                    <td className="num">
                      {num(last?.value, 1)} <span className="muted small">{last && prev ? pct((last.value / prev.value - 1) * 100, 1) : ""}</span>
                    </td>
                    <td className="num">{int(r.valid_observations)}</td>
                    <td>{r.last_observation_date ?? "–"}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </Card>
    </>
  );
}
