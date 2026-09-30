import { useState } from "react";
import { type IndexSeries, useApi } from "../api";
import { useMeta } from "../App";
import { LineSeriesChart, mergeSeries } from "../components/charts";
import { Card, DataLabel, ErrorBox, Loading, Segmented } from "../components/ui";
import { int, num } from "../format";

type Freq = "daily" | "weekly" | "monthly";

interface Comparison {
  data_label: string;
  default_methodology: string;
  weighting: { version: string; label: string; source: string };
  methodologies: { methodology: string; label: string; description: string; requires_weights: boolean; points: { period: string; value: number }[] }[];
}

const FREQS = [
  { value: "daily" as Freq, label: "Daily" },
  { value: "weekly" as Freq, label: "Weekly" },
  { value: "monthly" as Freq, label: "Monthly" },
];

export default function IndexPage() {
  const meta = useMeta();
  const [freq, setFreq] = useState<Freq>("monthly");
  const [method, setMethod] = useState("LASPEYRES");
  const limit = freq === "daily" ? 180 : undefined;
  const headline = useApi<IndexSeries>("index", { frequency: freq, methodology: method, limit });
  const comparison = useApi<Comparison>("index/methodologies", { frequency: freq, limit });

  const s = headline.data;
  const last = s?.points.at(-1);
  const prev = s?.points.at(-2);

  return (
    <>
      <div className="page-head">
        <div>
          <h1>
            Airfare Price Index <DataLabel label={s?.data_label} />
          </h1>
          <div className="muted small">Overall index across all monitored routes and booking windows. Base year {meta?.base_year ?? 2024} = 100.</div>
        </div>
        <div className="controls">
          <label className="field">
            Methodology
            <select value={method} onChange={(e) => setMethod(e.target.value)}>
              {(meta?.methodologies ?? []).map((m) => (
                <option key={m.name} value={m.name}>
                  {m.label}
                  {m.name === meta?.default_methodology ? " — headline" : ""}
                </option>
              ))}
            </select>
          </label>
          <Segmented label="Frequency" value={freq} onChange={setFreq} options={FREQS} />
        </div>
      </div>

      <Card
        title={`${method} · ${freq}`}
        subtitle={s ? `Weights ${s.weighting_version} (${s.weighting_label}) · ${s.calculation_version} · run ${s.run_id.slice(0, 8)}` : undefined}
      >
        {headline.loading && <Loading what="index" />}
        <ErrorBox error={headline.error} />
        {s && (
          <>
            <div className="grid kpis" style={{ marginBottom: 6 }}>
              <div>
                <div className="muted small">Latest ({last?.period})</div>
                <div style={{ fontSize: "1.6rem", fontWeight: 650 }} className="tnum">{num(last?.value, 2)}</div>
              </div>
              <div>
                <div className="muted small">Previous period</div>
                <div style={{ fontSize: "1.6rem", fontWeight: 650 }} className="tnum">{num(prev?.value, 2)}</div>
              </div>
              <div>
                <div className="muted small">Observations in latest period</div>
                <div style={{ fontSize: "1.6rem", fontWeight: 650 }} className="tnum">{int(last?.n_obs)}</div>
              </div>
              <div>
                <div className="muted small">Routes covered</div>
                <div style={{ fontSize: "1.6rem", fontWeight: 650 }} className="tnum">{last?.n_routes ?? "–"}</div>
              </div>
            </div>
            <LineSeriesChart rows={s.points} series={[{ key: "value", label: method }]} referenceY={100} referenceLabel="base = 100" height={320} caption={`${s.points.length} ${freq} periods`} />
          </>
        )}
      </Card>

      <div style={{ height: 14 }} />

      <Card title="Methodology comparison" subtitle="The same elementary (Jevons) route indices combined with four upper-level formulas">
        <ErrorBox error={comparison.error} />
        {comparison.data && (
          <>
            <LineSeriesChart
              rows={mergeSeries(comparison.data.methodologies.map((m) => ({ key: m.methodology, points: m.points })))}
              series={comparison.data.methodologies.map((m) => ({ key: m.methodology, label: m.label }))}
              referenceY={100}
              height={300}
              caption="All four formulas on one axis (index points)"
            />
            <div className="table-wrap" style={{ marginTop: 10 }}>
              <table>
                <thead>
                  <tr>
                    <th>Formula</th>
                    <th>Weights</th>
                    <th>What it does</th>
                    <th className="num">Latest</th>
                  </tr>
                </thead>
                <tbody>
                  {comparison.data.methodologies.map((m) => (
                    <tr key={m.methodology}>
                      <td>
                        {m.label} {m.methodology === comparison.data!.default_methodology && <span className="badge">headline</span>}
                      </td>
                      <td>{m.requires_weights ? `${comparison.data!.weighting.version} (${comparison.data!.weighting.label})` : "none"}</td>
                      <td style={{ whiteSpace: "normal" }} className="muted small">{m.description}</td>
                      <td className="num">{num(m.points.at(-1)?.value, 2)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="small muted" style={{ marginTop: 8 }}>
              Route weights are {comparison.data.weighting.label} values ({comparison.data.weighting.source}). Laspeyres, Paasche and Fisher differ only through them.
            </p>
          </>
        )}
      </Card>
    </>
  );
}
