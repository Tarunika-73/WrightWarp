"""Scheduled and administrative endpoints (Bearer CRON_SECRET).

``GET /api/v1/cron/daily`` is what Vercel Cron calls (Vercel Cron issues
GET requests with ``Authorization: Bearer $CRON_SECRET``). It runs one
collection pass over every cleared source and recomputes the index.
"""
from fastapi import APIRouter, Depends
from pymongo.asynchronous.database import AsyncDatabase

from app.api.deps import get_db, require_cron_secret
from app.index_engine.service import run_index_computation
from app.scheduling.daily import run_daily_collection

router = APIRouter(tags=["scheduled jobs"], dependencies=[Depends(require_cron_secret)])


@router.get("/cron/daily", summary="Daily scheduled collection + index recomputation (Vercel Cron)")
async def cron_daily(db: AsyncDatabase = Depends(get_db)):
    summary = await run_daily_collection(db)
    summary.pop("_id", None)
    return summary


@router.post("/admin/recompute-index", summary="Rebuild daily cells and recompute every index series")
async def recompute_index(db: AsyncDatabase = Depends(get_db)):
    run = await run_index_computation(db)
    return {"run_id": run["_id"], "series_count": run["series_count"], "cell_count": run["cell_count"], "duration_seconds": run["duration_seconds"], "data_label": run["data_label"]}
