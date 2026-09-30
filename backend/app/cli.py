"""Operational commands. Run from ``backend/``:

    python -m app.cli seed-demo          # (re)generate DEMO history + compute index + backtest
    python -m app.cli collect-today      # one scheduled-collection pass (demo source)
    python -m app.cli compute-index      # rebuild cells, recompute every index series + backtest
    python -m app.cli backtest-report    # write docs/BACKTEST_REPORT.md from the latest backtest

Connection settings come from the same environment/.env as the API.
The database URI is never printed.
"""
import argparse
import asyncio
import json
import logging

from app.core.config import REPO_ROOT, get_settings
from app.db.indexes import ensure_indexes
from app.db.mongodb import close_mongo_connection, connect_to_mongo, get_database


async def _main(args: argparse.Namespace) -> None:
    await connect_to_mongo()
    db = get_database()
    try:
        await ensure_indexes(db)
        if args.command == "seed-demo":
            from app.demo.seed import seed_demo_history
            from app.index_engine.service import run_index_computation

            summary = await seed_demo_history(db, progress=print)
            print(json.dumps(summary, indent=2, default=str))
            run = await run_index_computation(db)
            print(f"index run {run['_id']}: {run['series_count']} series, {run['cell_count']} cells, label={run['data_label']}")
        elif args.command == "collect-today":
            from app.scheduling.daily import run_daily_collection

            print(json.dumps(await run_daily_collection(db), indent=2, default=str))
        elif args.command == "compute-index":
            from app.index_engine.service import run_index_computation

            run = await run_index_computation(db)
            print(f"index run {run['_id']}: {run['series_count']} series, label={run['data_label']}, {run['duration_seconds']}s")
        elif args.command == "backtest-report":
            from app.index_engine.report import write_backtest_report

            path = await write_backtest_report(db, REPO_ROOT / "docs" / "BACKTEST_REPORT.md")
            print(f"wrote {path}")
    finally:
        await close_mongo_connection()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    parser = argparse.ArgumentParser(prog="python -m app.cli", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", choices=["seed-demo", "collect-today", "compute-index", "backtest-report"])
    args = parser.parse_args()
    get_settings()
    asyncio.run(_main(args))


if __name__ == "__main__":
    main()
