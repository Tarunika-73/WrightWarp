"""Renders the latest backtest into a Markdown report (docs/BACKTEST_REPORT.md)."""
from pathlib import Path

from pymongo.asynchronous.database import AsyncDatabase

from app.index_engine.service import current_run, latest_backtest


def _fmt(value, digits: int = 3) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, float):
        return f"{value:.{digits}f}"
    return str(value)


def render_backtest_markdown(run: dict | None, backtest: dict | None) -> str:
    lines = ["# Backtest Report", ""]
    if backtest is None:
        lines.append("No backtest has been run yet (`python -m app.cli compute-index`).")
        return "\n".join(lines) + "\n"
    label = backtest.get("data_label")
    if label == "DEMO":
        lines += [
            "> **DEMO DATA - NOT OFFICIAL.** Every observation behind these numbers came from the",
            "> WrightWarp market simulator, and the reference series is the simulator's own ground truth.",
            "> The results measure how well the pipeline *recovers a known index* from noisy, gappy,",
            "> partly corrupted observations. They are **not** a validation against official statistics.",
            "",
        ]
    lines += [
        f"- Backtest id: `{backtest['_id']}` (index run `{backtest['run_id']}`)",
        f"- Generated: {backtest['created_at']:%Y-%m-%d %H:%M UTC}",
        f"- Base year: {backtest['base_year']} = 100. Base-year periods are excluded from the error metrics.",
        f"- Headline methodology: {backtest['default_methodology']}",
    ]
    if run:
        lines += [
            f"- Observations: {run.get('observation_count')} total, {run.get('valid_observation_count')} index-eligible, "
            f"{run.get('excluded_observation_count')} excluded by the quality engine",
            f"- Observation days: {run.get('first_observation_date')} .. {run.get('last_observation_date')}",
            f"- Weighting: {run['weighting']['version']} ({run['weighting']['label']})",
        ]
    lines.append("")
    if not backtest.get("references"):
        lines.append(backtest.get("note", "No reference series available."))
    for ref in backtest.get("references", []):
        lines += [f"## Reference: {ref['label']}", "", ref.get("description", ""), ""]
        results = ref["results"]
        if "methodologies" in results:
            lines += [
                "### Overall index by methodology",
                "",
                "| Methodology | Frequency | Periods | MAE (pts) | RMSE (pts) | MAPE % | Bias (pts) | Max abs err | Corr | Direction agreement % |",
                "|---|---|---|---|---|---|---|---|---|---|",
            ]
            for method, by_freq in results["methodologies"].items():
                for freq, m in by_freq.items():
                    if not m:
                        continue
                    lines.append(
                        f"| {method} | {freq} | {m['n_periods']} | {_fmt(m['mae'])} | {_fmt(m['rmse'])} | {_fmt(m['mape_pct'])} | "
                        f"{_fmt(m['bias'])} | {_fmt(m['max_abs_error'])} | {_fmt(m['correlation'])} | {_fmt(m['direction_agreement_pct'], 1)} |"
                    )
            lines += ["", "### Route-level (elementary Jevons) accuracy", "", "| Route | Frequency | MAE | RMSE | MAPE % | Corr |", "|---|---|---|---|---|---|"]
            for route, by_freq in results.get("routes", {}).items():
                for freq, m in by_freq.items():
                    if m:
                        lines.append(f"| {route} | {freq} | {_fmt(m['mae'])} | {_fmt(m['rmse'])} | {_fmt(m['mape_pct'])} | {_fmt(m['correlation'])} |")
            lines += ["", "### Booking-window indices (monthly, headline methodology)", "", "| Window | MAE | RMSE | MAPE % | Corr |", "|---|---|---|---|---|"]
            for window, by_freq in results.get("windows", {}).items():
                m = by_freq.get("monthly")
                if m:
                    lines.append(f"| {window} | {_fmt(m['mae'])} | {_fmt(m['rmse'])} | {_fmt(m['mape_pct'])} | {_fmt(m['correlation'])} |")
            comparison = results.get("methodology_comparison", {})
            if comparison:
                lines += ["", "### How far apart the formulas are", "", "| Frequency | Mean spread (pts) | Max spread (pts) | Latest period | Latest values |", "|---|---|---|---|---|"]
                for freq, c in comparison.items():
                    latest = ", ".join(f"{k} {v}" for k, v in c["latest"].items())
                    lines.append(f"| {freq} | {_fmt(c['mean_spread_points'])} | {_fmt(c['max_spread_points'])} | {c['latest_period']} | {latest} |")
        else:
            for scope, by_freq in results.items():
                for freq, m in by_freq.items():
                    lines.append(f"- {scope} {freq}: " + (", ".join(f"{k}={_fmt(v)}" for k, v in m.items()) if m else "no overlapping periods"))
        lines.append("")
    lines += [
        "## Interpretation limits",
        "",
        "- The simulator's noise model is simple (log-normal noise, AR(1) shocks, fixed seasonal bumps). Real",
        "  fare dynamics (fare buckets, flash sales, capacity shocks) are harsher, so real-data errors will be larger.",
        "- No official CPI airfare series has been loaded, so no statement about agreement with official",
        "  statistics can be made. Load one into the `reference_series` collection to backtest against it.",
        "- Route weights are DEMO values, not DGCA traffic.",
        "",
    ]
    return "\n".join(lines)


async def write_backtest_report(db: AsyncDatabase, path: Path) -> Path:
    content = render_backtest_markdown(await current_run(db), await latest_backtest(db))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path
