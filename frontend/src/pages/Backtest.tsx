import { useApi } from "../api";
import { LineSeriesChart } from "../components/charts";
import { Card, DataLabel, ErrorBox, Loading } from "../components/ui";
import { dateTime, num } from "../format";

interface Metrics {
  n_periods: number;
  mae: number;
  rmse: number;
  mape_pct: number;
  bias: number;
  max_abs_error: number;
  correlation: number | null;
  direction_agreement_pct: number | null;
  est_change_sd_pct: number | null;
  ref_change_sd_pct: number | null;
}

interface Reference {
  reference_id: string;
  label: string;
  data_label: string;
  description: string;
  results: {
    methodologies?: Record<string, Record<string, Metrics | null>>;
    routes?: Record<string, Record<string, Metrics | null>>;
    windows?: Record<string, Record<string, Metrics | null>>;
    series?: Record<string, { period: string; estimated: number; reference: number }[]>;
    methodology_comparison?: Record<string, { mean_spread_points: number; max_spread_points: number; latest_period: string; latest: Record<string, number> }>;
  };
}

interface Report {
  backtest_id: string;
  run_id: string;
  created_at: string;
  data_label: string;
  default_methodology: string;
  base_year: number;
  references: Reference[];
  note?: string;
}

const f = (v: number | null | undefined, d = 3) => (v == null ? "–" : v.toFixed(d));

export default function Backtest() {
  const { data, error, loading } = useApi<Report>("backtest");
  if (loading) return <Loading what="backtest" />;
  if (error) return <ErrorBox error={error} />;
  const r = data!;
  return (
    <>
      <div className="page-head">
        <div>
          <h1>
            Backtesting <DataLabel label={r.data_label} />
          </h1>
          <div className="muted small">
            Backtest {r.backtest_id.slice(0, 8)} of index run {r.run_id.slice(0, 8)} · {dateTime(r.created_at)} · base-year ({r.base_year}) periods excluded from error metrics
          </div>
        </div>
      </div>
      {r.data_label === "DEMO" && (
        <div className="demo-banner">
          <strong>NOT A VALIDATION</strong>
          <span>
            These numbers compare the index computed from simulated observations with the simulator's own ground truth. They measure how well the pipeline recovers a known
            index from noisy, gappy, partly corrupted data. No official CPI airfare series has been loaded, so no claim about agreement with official statistics is made.
          </span>
        </div>
      )}
      {r.note && <div className="notice">{r.note}</div>}
      {r.references.map((ref) => (
        <div key={ref.reference_id}>
          <Card title={`Reference: ${ref.label}`} subtitle={ref.description}>
            {ref.results.series?.[r.default_methodology] && (
              <LineSeriesChart
                rows={ref.results.series[r.default_methodology]}
                series={[
                  { key: "estimated", label: `Computed (${r.default_methodology})` },
                  { key: "reference", label: "Reference" },
                ]}
                referenceY={100}
                height={300}
                caption="Monthly overall index, computed vs reference"
              />
            )}
          </Card>
          <div style={{ height: 14 }} />
          {ref.results.methodologies && (
            <Card title="Error by methodology and frequency" subtitle="MAE/RMSE/bias in index points; MAPE in %">
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>Methodology</th>
                      <th>Frequency</th>
                      <th className="num">Periods</th>
                      <th className="num">MAE</th>
                      <th className="num">RMSE</th>
                      <th className="num">MAPE %</th>
                      <th className="num">Bias</th>
                      <th className="num">Max |err|</th>
                      <th className="num">Correlation</th>
                      <th className="num">Same direction %</th>
                    </tr>
                  </thead>
                  <tbody>
                    {Object.entries(ref.results.methodologies).flatMap(([m, byFreq]) =>
                      Object.entries(byFreq).map(([freq, x]) =>
                        x ? (
                          <tr key={m + freq}>
                            <td>{m}</td>
                            <td>{freq}</td>
                            <td className="num">{x.n_periods}</td>
                            <td className="num">{f(x.mae)}</td>
                            <td className="num">{f(x.rmse)}</td>
                            <td className="num">{f(x.mape_pct)}</td>
                            <td className="num">{f(x.bias)}</td>
                            <td className="num">{f(x.max_abs_error)}</td>
                            <td className="num">{f(x.correlation, 4)}</td>
                            <td className="num">{f(x.direction_agreement_pct, 1)}</td>
                          </tr>
                        ) : null,
                      ),
                    )}
                  </tbody>
                </table>
              </div>
            </Card>
          )}
          <div style={{ height: 14 }} />
          <div className="grid two">
            {ref.results.routes && (
              <Card title="Route-level accuracy" subtitle="Elementary Jevons route index, monthly">
                <table>
                  <thead>
                    <tr>
                      <th>Route</th>
                      <th className="num">MAE</th>
                      <th className="num">MAPE %</th>
                      <th className="num">Correlation</th>
                    </tr>
                  </thead>
                  <tbody>
                    {Object.entries(ref.results.routes).map(([route, byFreq]) => (
                      <tr key={route}>
                        <td>{route}</td>
                        <td className="num">{f(byFreq.monthly?.mae)}</td>
                        <td className="num">{f(byFreq.monthly?.mape_pct)}</td>
                        <td className="num">{f(byFreq.monthly?.correlation, 4)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </Card>
            )}
            {ref.results.windows && (
              <Card title="Booking-window accuracy" subtitle={`${r.default_methodology}, monthly`}>
                <table>
                  <thead>
                    <tr>
                      <th>Window</th>
                      <th className="num">MAE</th>
                      <th className="num">MAPE %</th>
                      <th className="num">Correlation</th>
                    </tr>
                  </thead>
                  <tbody>
                    {Object.entries(ref.results.windows).map(([w, byFreq]) => (
                      <tr key={w}>
                        <td>{w}</td>
                        <td className="num">{f(byFreq.monthly?.mae)}</td>
                        <td className="num">{f(byFreq.monthly?.mape_pct)}</td>
                        <td className="num">{f(byFreq.monthly?.correlation, 4)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </Card>
            )}
          </div>
          {ref.results.methodology_comparison && (
            <>
              <div style={{ height: 14 }} />
              <Card title="How far apart the formulas are" subtitle="Spread = highest minus lowest methodology value in the same period">
                <table>
                  <thead>
                    <tr>
                      <th>Frequency</th>
                      <th className="num">Mean spread (pts)</th>
                      <th className="num">Max spread (pts)</th>
                      <th>Latest ({"period"})</th>
                    </tr>
                  </thead>
                  <tbody>
                    {Object.entries(ref.results.methodology_comparison).map(([freq, c]) => (
                      <tr key={freq}>
                        <td>{freq}</td>
                        <td className="num">{f(c.mean_spread_points)}</td>
                        <td className="num">{f(c.max_spread_points)}</td>
                        <td className="small">
                          {c.latest_period}: {Object.entries(c.latest).map(([m, v]) => `${m} ${num(v, 2)}`).join(" · ")}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </Card>
            </>
          )}
        </div>
      ))}
    </>
  );
}
