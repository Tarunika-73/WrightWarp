"""Vercel entrypoint.

Vercel's FastAPI runtime looks for an ``app`` instance in ``index.py`` at the
project root. The application itself lives in ``backend/app`` (imported as the
top-level package ``app``), so the backend directory goes on ``sys.path`` first.
Locally, keep using ``uvicorn app.main:app`` from ``backend/``.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "backend"))

from app.main import app  # noqa: E402

__all__ = ["app"]
