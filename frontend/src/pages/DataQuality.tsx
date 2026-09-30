import { useMemo } from "react";
import { useApi } from "../api";
import { LineSeriesChart, SimpleBarChart } from "../components/charts";
import { Card, ErrorBox, Kpi, Loading } from "../components/ui";
import { int, num } from "../format";

interface Summary {
  total_observations: number;
  index_eligible: number;
  excluded: number;
  eligible_statuses: string[];
  by_status: { status: string; count: number }[];
  by_source: Record<string, number | string>[];
  top_reasons: { status: string; rule: string; count: number }[];
  timeline: Record<string, number | string>[];
}

interface Rules {
  version: string;
  severity_order: string[];
  rules: { rule: string; outcome: string; detail: string }[];
}

// Status colours carry meaning (good -> critical); every bar is also labelled.
const STATUS_COLOR: Record<string, string> = {
  VALIDATED: "var(--good)",
  PROVISIONAL: "var(--s1)",
  SOLD_OUT: "var(--muted)",
  DUPLICATE: "var(--muted)",
  REVIEW_REQUIRED: "var(--warning)",
  OUTLIER: "var(--serious)",
  MISSING: "var(--serious)",
  REJECTED: "var(--critical)",
};

export default function DataQuality() {
  const summary = useApi<Summary>("quality/summary", { days: 90 });
  const rules = useApi<Rules>("quality/rules");

  const timeline = useMemo(
    () =>
      (summary.data?.timeline ?? []).map((row) => {
        const total = Object.entries(row).reduce((acc, [k, v]) => (k === "date" ? acc : acc + Number(v)), 0);
        const excluded = total - Number(row.VALIDATED ?? 0) - Number(row.PROVISIONAL ?? 0);
        return { date: row.date, excluded_pct: total ? (100 * excluded) / total : 0 };
      }),
    [summary.data],
  );

  if (summary.loading) return <Loading what="quality summary" />;
  if (summary.error) return <ErrorBox error={summary.error} />;
  const s = summary.data!;

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Data quality</h1>
          <div className="muted small">
            Every observation receives exactly one quality decision and is kept. Only {s.eligible_statuses.join(" and ")} observations enter the index.
          </div>
        </div>
      </div>

      <div className="grid kpis">
        <Kpi label="Observations" value={int(s.total_observations)} />
        <Kpi label="Index-eligible" value={int(s.index_eligible)} sub={`${num((100 * s.index_eligible) / s.total_observations, 2)}%`} />
        <Kpi label="Excluded (kept on record)" value={int(s.excluded)} sub={`${num((100 * s.excluded) / s.total_observations, 2)}%`} />
        <Kpi label="Rules version" value={<span style={{ fontSize: "1rem" }}>{rules.data?.version ?? "–"}</span>} />
      </div>

      <div className="grid two">
        <Card title="Decisions by status" subtitle="All observations, all time">
          <SimpleBarChart
            rows={s.by_status.map((b) => ({ status: b.status, count: b.count }))}
            xKey="status"
            yKey="count"
            label="Observations"
            format={(v) => int(v)}
            colorFor={(r) => STATUS_COLOR[String(r.status)] ?? "var(--muted)"}
            caption="Colour follows severity; labels carry the meaning"
          />
        </Card>
        <Card title="Share excluded per day" subtitle="Last 90 observation days">
          <LineSeriesChart rows={timeline} xKey="date" series={[{ key: "excluded_pct", label: "Excluded %" }]} format={(v) => `${v.toFixed(1)}%`} caption="Excluded ÷ all observations that day" yDomain={[0, "auto"]} />
        </Card>
      </div>

      <div style={{ height: 14 }} />

      <div className="grid two">
        <Card title="Why observations were excluded" subtitle="Top rules that fired">
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Status</th>
                  <th>Rule</th>
                  <th className="num">Count</th>
                </tr>
              </thead>
              <tbody>
                {s.top_reasons.map((r) => (
                  <tr key={`${r.status}-${r.rule}`}>
                    <td>
                      <span className="status-dot" style={{ background: STATUS_COLOR[r.status] }} />
                      {r.status}
                    </td>
                    <td>
                      <code>{r.rule}</code>
                    </td>
                    <td className="num">{int(r.count)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
        <Card title="By source">
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Source</th>
                  {s.by_status.map((b) => (
                    <th key={b.status} className="num">
                      {b.status}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {s.by_source.map((row) => (
                  <tr key={String(row.source)}>
                    <td>{row.source}</td>
                    {s.by_status.map((b) => (
                      <td key={b.status} className="num">
                        {int(Number(row[b.status] ?? 0))}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      </div>

      <div style={{ height: 14 }} />

      <Card title="Rules in force" subtitle={rules.data ? `Severity order: ${rules.data.severity_order.join(" > ")}` : undefined}>
        {rules.data && (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Rule</th>
                  <th>Outcome</th>
                  <th>Check</th>
                </tr>
              </thead>
              <tbody>
                {rules.data.rules.map((r) => (
                  <tr key={r.rule}>
                    <td>
                      <code>{r.rule}</code>
                    </td>
                    <td>{r.outcome}</td>
                    <td style={{ whiteSpace: "normal" }} className="small">
                      {r.detail}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </>
  );
}
