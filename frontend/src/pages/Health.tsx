import { useApi } from "../api";
import { useMeta } from "../App";
import { Card, ErrorBox } from "../components/ui";
import { dateTime, int } from "../format";

interface Health {
  status: string;
  service: string;
  database?: string;
}

interface Run {
  run_id: string;
  created_at: string;
  duration_seconds: number;
  calculation_version: string;
  data_label: string;
  series_count: number;
  cell_count: number;
  observation_count: number;
  weighting: { version: string; label: string; checksum_sha256: string };
  first_observation_date: string;
  last_observation_date: string;
}

interface Overview {
  last_collection_at: string | null;
  last_scheduled_job: { started_at: string; requests: number; outcomes: Record<string, number>; quotes_normalized: number; duration_seconds: number; index_error?: string } | null;
}

function Status({ ok, label }: { ok: boolean | null; label: string }) {
  const color = ok == null ? "var(--muted)" : ok ? "var(--good)" : "var(--critical)";
  return (
    <span>
      <span className="status-dot" style={{ background: color }} />
      {ok == null ? "checking…" : ok ? "OK" : "FAIL"} · {label}
    </span>
  );
}

export default function HealthPage() {
  const meta = useMeta();
  const api = useApi<Health>("/health");
  const db = useApi<Health>("/health/db");
  const run = useApi<Run>("index/runs/current");
  const overview = useApi<Overview>("stats/overview");
  const job = overview.data?.last_scheduled_job;
  return (
    <>
      <div className="page-head">
        <div>
          <h1>System health</h1>
          <div className="muted small">Environment: {meta?.environment ?? "…"}</div>
        </div>
      </div>
      <div className="grid three">
        <Card title="API">
          <Status ok={api.loading ? null : api.data?.status === "ok"} label={api.data?.service ?? "wrightwarp-api"} />
          <ErrorBox error={api.error} />
        </Card>
        <Card title="Database">
          <Status ok={db.loading ? null : db.data?.status === "ok"} label={db.data?.database ?? "MongoDB"} />
          <ErrorBox error={db.error} />
        </Card>
        <Card title="Scheduled collection">
          {job ? (
            <div className="small">
              <Status ok={!job.index_error && !(job.outcomes.FAILED > 0)} label={`last run ${dateTime(job.started_at)}`} />
              <div className="muted">
                {job.requests} requests · {int(job.quotes_normalized)} quotes · {job.duration_seconds}s · {Object.entries(job.outcomes).map(([k, v]) => `${k} ${v}`).join(", ")}
              </div>
            </div>
          ) : (
            <p className="small muted">No scheduled job has run yet. It runs daily via Vercel Cron (or <code>python -m app.cli collect-today</code>).</p>
          )}
        </Card>
      </div>
      <div style={{ height: 14 }} />
      <Card title="Current index computation">
        <ErrorBox error={run.error} />
        {run.data && (
          <table>
            <tbody>
              <tr><td>Run id</td><td><code>{run.data.run_id}</code></td></tr>
              <tr><td>Computed</td><td>{dateTime(run.data.created_at)} ({run.data.duration_seconds}s)</td></tr>
              <tr><td>Data label</td><td>{run.data.data_label}</td></tr>
              <tr><td>Calculation version</td><td>{run.data.calculation_version}</td></tr>
              <tr><td>Series / cells / observations</td><td>{int(run.data.series_count)} / {int(run.data.cell_count)} / {int(run.data.observation_count)}</td></tr>
              <tr><td>Observation window</td><td>{run.data.first_observation_date} → {run.data.last_observation_date}</td></tr>
              <tr><td>Weighting</td><td>{run.data.weighting.version} ({run.data.weighting.label}) · sha256 {run.data.weighting.checksum_sha256.slice(0, 12)}…</td></tr>
              <tr><td>Last collection</td><td>{dateTime(overview.data?.last_collection_at)}</td></tr>
            </tbody>
          </table>
        )}
      </Card>
    </>
  );
}
