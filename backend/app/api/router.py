"""Aggregation point for versioned (``/api/v1/...``) endpoints.

The unversioned ``/health`` endpoint is wired directly in app.main since
it is an infrastructure check, not a versioned resource.
"""
from fastapi import APIRouter

from app.api import collections, sources

api_router = APIRouter()
api_router.include_router(sources.router)
api_router.include_router(collections.router)
