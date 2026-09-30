import { useApi } from "../api";
import { Card, ErrorBox, Loading } from "../components/ui";
import { dateTime, int } from "../format";

interface Source {
  source_id: string;
  display_name: string;
  source_type: string;
  enabled: boolean;
  status: string;
  robots_url: string | null;
  terms_url: string | null;
  rate_limit_per_minute: number;
  requires_browser: boolean;
  notes: string;
  data_provenance: string;
}

interface Runs {
  items: { id: string; source: string; status: string; route: string; lead_days: number; started_at: string; records_found: number; records_valid: number; error_message: string | null }[];
  page: { total: number };
}

const STATUS_TONE: Record<string, string> = { IMPLEMENTED: "var(--good)", PENDING_REVIEW: "var(--warning)", DISABLED: "var(--muted)", CONFIGURED: "var(--muted)" };

export default function Sources() {
  const sources = useApi<Source[]>("sources");
  const runs = useApi<Runs>("collections", { page_size: 15 });
  return (
    <>
      <div className="page-head">
        <div>
          <h1>Source monitoring</h1>
          <div className="muted small">Registered airline and OTA sources, their compliance status, and recent collection runs.</div>
        </div>
      </div>
      <div className="notice" style={{ marginBottom: 14 }}>
        Ethical collection policy: robots.txt and Terms of Service are reviewed per source; no CAPTCHA solving, stealth browsing, proxy/IP rotation, or authentication bypass.
        A source is collected <strong>only</strong> when its status is IMPLEMENTED and it is enabled. Every real airline/OTA is currently PENDING_REVIEW, so the demo runs on the simulator.
      </div>
      <Card title="Source registry">
        {sources.loading && <Loading what="sources" />}
        <ErrorBox error={sources.error} />
        {sources.data && (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Source</th>
                  <th>Type</th>
                  <th>Status</th>
                  <th>Data</th>
                  <th className="num">Rate limit/min</th>
                  <th>Compliance notes</th>
                </tr>
              </thead>
              <tbody>
                {sources.data.map((s) => (
                  <tr key={s.source_id}>
                    <td>
                      <strong>{s.source_id}</strong>
                      <div className="muted small">{s.display_name}</div>
                    </td>
                    <td>{s.source_type}</td>
                    <td>
                      <span className="status-dot" style={{ background: STATUS_TONE[s.status] ?? "var(--muted)" }} />
                      {s.status}
                      <div className="muted small">{s.enabled ? "enabled" : "disabled"}</div>
                    </td>
                    <td>
                      <span className={`badge ${s.data_provenance !== "REAL" ? "demo" : ""}`}>{s.data_provenance}</span>
                    </td>
                    <td className="num">{s.rate_limit_per_minute}</td>
                    <td style={{ whiteSpace: "normal", minWidth: 280 }} className="small">
                      {s.notes}
                      {s.robots_url && (
                        <div>
                          <a href={s.robots_url} target="_blank" rel="noreferrer">
                            robots.txt
                          </a>
                          {s.terms_url && (
                            <>
                              {" · "}
                              <a href={s.terms_url} target="_blank" rel="noreferrer">
                                terms
                              </a>
                            </>
                          )}
                        </div>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
      <div style={{ height: 14 }} />
      <Card title="Recent collection runs" subtitle={runs.data ? `${int(runs.data.page.total)} runs recorded (checkpoints)` : undefined}>
        <ErrorBox error={runs.error} />
        {runs.data && (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Started</th>
                  <th>Source</th>
                  <th>Route</th>
                  <th>Window</th>
                  <th>Status</th>
                  <th className="num">Found</th>
                  <th className="num">Normalized</th>
                  <th>Error</th>
                </tr>
              </thead>
              <tbody>
                {runs.data.items.map((r) => (
                  <tr key={r.id}>
                    <td>{dateTime(r.started_at)}</td>
                    <td>{r.source}</td>
                    <td>{r.route}</td>
                    <td>T+{r.lead_days}</td>
                    <td>{r.status}</td>
                    <td className="num">{r.records_found}</td>
                    <td className="num">{r.records_valid}</td>
                    <td className="small muted">{r.error_message ?? ""}</td>
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
