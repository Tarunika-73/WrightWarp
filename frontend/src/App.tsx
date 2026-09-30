import { createContext, useContext, useState } from "react";
import { NavLink, Route, Routes, useLocation } from "react-router-dom";
import { type Meta, useApi } from "./api";
import ApiDocs from "./pages/ApiDocs";
import Backtest from "./pages/Backtest";
import BookingWindows from "./pages/BookingWindows";
import DataQuality from "./pages/DataQuality";
import Health from "./pages/Health";
import IndexPage from "./pages/IndexPage";
import Overview from "./pages/Overview";
import RoutesPage from "./pages/RoutesPage";
import Sources from "./pages/Sources";

export const MetaContext = createContext<Meta | null>(null);
export const useMeta = () => useContext(MetaContext);

const NAV = [
  { to: "/", label: "Overview" },
  { to: "/index", label: "Airfare Index" },
  { to: "/routes", label: "Route Analysis" },
  { to: "/booking-windows", label: "Booking Windows" },
  { to: "/sources", label: "Source Monitoring" },
  { to: "/quality", label: "Data Quality" },
  { to: "/backtest", label: "Backtesting" },
  { to: "/api-docs", label: "API & Methodology" },
  { to: "/health", label: "System Health" },
];

function DemoBanner({ meta }: { meta: Meta | null }) {
  if (!meta?.demo_mode) return null;
  return (
    <div className="demo-banner" role="note">
      <strong>DEMO DATA · SIMULATED</strong>
      <span>{meta.data_notice}</span>
    </div>
  );
}

export default function App() {
  const { data: meta } = useApi<Meta>("meta");
  const [open, setOpen] = useState(false);
  const location = useLocation();
  return (
    <MetaContext.Provider value={meta}>
      <div className="shell">
        <aside className={`sidebar ${open ? "open" : ""}`}>
          <div className="brand">
            <div className="brand-mark" aria-hidden="true">W</div>
            <div>
              <div className="brand-name">WrightWarp</div>
              <div className="brand-sub">Airfare Price Index · India</div>
            </div>
          </div>
          <nav className="nav" onClick={() => setOpen(false)}>
            {NAV.map((n) => (
              <NavLink key={n.to} to={n.to} end={n.to === "/"}>
                {n.label}
              </NavLink>
            ))}
          </nav>
          <div className="nav-foot">
            SIH 2026 · PS 26056
            <br />
            MoSPI · Data Informatics &amp; Innovation Division
            <br />
            Prototype — not an official statistic.
          </div>
        </aside>
        <main className="main" key={location.pathname}>
          <button className="menu-btn" onClick={() => setOpen((o) => !o)} aria-label="Toggle navigation">
            ☰ Menu
          </button>
          <DemoBanner meta={meta} />
          <Routes>
            <Route path="/" element={<Overview />} />
            <Route path="/index" element={<IndexPage />} />
            <Route path="/routes" element={<RoutesPage />} />
            <Route path="/booking-windows" element={<BookingWindows />} />
            <Route path="/sources" element={<Sources />} />
            <Route path="/quality" element={<DataQuality />} />
            <Route path="/backtest" element={<Backtest />} />
            <Route path="/api-docs" element={<ApiDocs />} />
            <Route path="/health" element={<Health />} />
            <Route path="*" element={<div className="card">Page not found.</div>} />
          </Routes>
        </main>
      </div>
    </MetaContext.Provider>
  );
}
