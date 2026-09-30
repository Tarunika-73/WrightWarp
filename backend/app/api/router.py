"""Aggregation point for versioned (``/api/v1/...``) endpoints.

The unversioned ``/health`` endpoints are wired directly in app.main since
they are infrastructure checks, not versioned resources.
"""
from fastapi import APIRouter

from app.api import backtest, collections, cron, fares, index, quality, routes, sources, stats

api_router = APIRouter()
api_router.include_router(stats.router)
api_router.include_router(sources.router)
api_router.include_router(routes.router)
api_router.include_router(collections.router)
api_router.include_router(fares.router)
api_router.include_router(index.router)
api_router.include_router(quality.router)
api_router.include_router(backtest.router)
api_router.include_router(cron.router)
