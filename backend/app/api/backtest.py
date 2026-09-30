"""Backtest endpoints."""
from fastapi import APIRouter, Depends
from pymongo.asynchronous.database import AsyncDatabase

from app.api.deps import get_db, require_cron_secret
from app.core.errors import IndexNotAvailableError
from app.index_engine.service import latest_backtest, run_index_computation

router = APIRouter(prefix="/backtest", tags=["backtest"])


@router.get("", summary="Latest backtest report (DEMO results are labelled as such)")
async def get_backtest(db: AsyncDatabase = Depends(get_db)):
    report = await latest_backtest(db)
    if report is None:
        raise IndexNotAvailableError("No backtest has been run yet")
    report["backtest_id"] = report.pop("_id")
    return report


@router.post("/run", dependencies=[Depends(require_cron_secret)], summary="Recompute the index and re-run the backtest (protected)")
async def run_backtest(db: AsyncDatabase = Depends(get_db)):
    run = await run_index_computation(db, rebuild=False)
    return {"run_id": run["_id"], "backtest_id": run.get("backtest_id"), "duration_seconds": run["duration_seconds"]}
