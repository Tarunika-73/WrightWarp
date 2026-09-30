import { useMeta } from "../App";
import { Card } from "../components/ui";

const ENDPOINTS: [string, string, string][] = [
  ["GET", "/health · /health/db", "Liveness and database connectivity"],
  ["GET", "/api/v1/meta", "Data mode (DEMO/REAL), base year, booking windows, methodologies, weighting"],
  ["GET", "/api/v1/stats/overview", "Dashboard headline figures in one call"],
  ["GET", "/api/v1/sources", "Source registry with compliance status"],
  ["GET", "/api/v1/routes · /routes/{route}", "Monitored routes, airports, weight shares"],
  ["GET · POST", "/api/v1/collections", "List collection runs / run one collection for a cleared source"],
  ["GET", "/api/v1/fares · /api/v1/quotes", "Normalized observations, paginated; filters: route, travel_date, lead_days, date_from, date_to, source, quality_status, airline"],
  ["GET", "/api/v1/quotes/{id}/provenance", "Quote → raw observation → collection run"],
  ["GET", "/api/v1/fares/booking-window?route&travel_date", "Fare for a travel date bought T+1 … T+45 days ahead"],
  ["GET", "/api/v1/fares/booking-window/compare", "Average fare and premium per booking window over a date range"],
  ["GET", "/api/v1/fares/daily?route", "Daily geometric-mean fare per booking window"],
  ["GET", "/api/v1/index?methodology&frequency", "Overall index series (also /index/daily, /weekly, /monthly)"],
  ["GET", "/api/v1/index/route/{route}?lead_days", "Route (or route × window) elementary index"],
  ["GET", "/api/v1/index/booking-window?lead_days", "Index of one booking window across routes"],
  ["GET", "/api/v1/index/methodologies", "Jevons / Laspeyres / Paasche / Fisher side by side"],
  ["GET", "/api/v1/index/runs/current", "Reproducibility record of the current computation"],
  ["GET", "/api/v1/index/trace?route&observation_date", "Index point → cells → observations → sources → quality"],
  ["GET", "/api/v1/quality/summary · /quality/rules", "Quality decisions and the rules in force"],
  ["GET", "/api/v1/backtest", "Latest backtest report (DEMO results labelled)"],
  ["GET", "/api/v1/cron/daily", "Scheduled collection + recompute (Bearer CRON_SECRET)"],
];

export default function ApiDocs() {
  const meta = useMeta();
  return (
    <>
      <div className="page-head">
        <div>
          <h1>API &amp; methodology</h1>
          <div className="muted small">
            Interactive documentation: <a href="/docs">Swagger UI</a> · <a href="/redoc">ReDoc</a> · <a href="/openapi.json">OpenAPI JSON</a>
          </div>
        </div>
      </div>

      <div className="grid two">
        <Card title="Pipeline">
          <div className="flow">
            <span>Source adapter</span>→<span>Raw observation</span>→<span>Fare normalization</span>→<span>Quality engine</span>→<span>Flight quote</span>→<span>Daily cell</span>→<span>Route index (Jevons)</span>→
            <span>Overall index (Laspeyres …)</span>
          </div>
          <ul className="list-plain small" style={{ marginTop: 12 }}>
            <li>Raw payloads are stored before anything else; normalization never invents a fare component or a total.</li>
            <li>Each observation gets one quality status; nothing is deleted. Only VALIDATED/PROVISIONAL feed the index.</li>
            <li>A cell is the geometric-mean fare of one observation day × route × booking window × carrier.</li>
            <li>Route relative = geometric mean of carrier×window price relatives vs their {meta?.base_year ?? 2024} base price.</li>
            <li>Routes are combined with the selected formula and route weights; periods are IST calendar days, ISO weeks, and months.</li>
          </ul>
        </Card>
        <Card title="Methodologies">
          <table>
            <tbody>
              {(meta?.methodologies ?? []).map((m) => (
                <tr key={m.name}>
                  <td>
                    <strong>{m.label}</strong>
                    {m.name === meta?.default_methodology && <span className="badge" style={{ marginLeft: 6 }}>headline</span>}
                  </td>
                  <td style={{ whiteSpace: "normal" }} className="small muted">
                    {m.description}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {meta && (
            <p className="small" style={{ marginTop: 8 }}>
              Weights: <strong>{meta.weighting.version}</strong> <span className="badge demo">{meta.weighting.label}</span> — {meta.weighting.description}
            </p>
          )}
        </Card>
      </div>

      <div style={{ height: 14 }} />

      <Card title="Endpoints">
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Method</th>
                <th>Path</th>
                <th>Purpose</th>
              </tr>
            </thead>
            <tbody>
              {ENDPOINTS.map(([m, p, d]) => (
                <tr key={p}>
                  <td>{m}</td>
                  <td>
                    <code>{p}</code>
                  </td>
                  <td style={{ whiteSpace: "normal" }} className="small">
                    {d}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      <div style={{ height: 14 }} />

      <Card title="Tracing a value" className="" subtitle="Every published number can be walked back to what a source showed">
        <div id="trace" className="small">
          <ol className="list-plain">
            <li>
              <code>/api/v1/index/trace?route=DEL-BOM&amp;observation_date=YYYY-MM-DD</code> returns the index point, its cells, and every observation behind it with quality status
              and whether it was included.
            </li>
            <li>
              <code>/api/v1/quotes/&#123;quote_id&#125;/provenance</code> returns the stored raw payload (with its SHA-256 hash) and the collection run (source, time, status).
            </li>
            <li>
              <code>/api/v1/index/runs/current</code> records the weighting version and checksum, methodology, counts, and calculation version used.
            </li>
          </ol>
        </div>
      </Card>
    </>
  );
}
