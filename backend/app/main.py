"""Car or Air app entry point. Only wires routers together.

Do not add routes here: engine routes go in api/cases.py (owner A), AI routes in
api/ai.py (owner B). That keeps the two of you out of each other's files.
"""
from __future__ import annotations

import threading
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from .api import ai, cases
from .core import forecaster, history


def _warm_up() -> None:
    """Load the forecaster and the weather archive once, so the first request is not slow."""
    try:
        forecaster.model_name()
        history.archive()
    except Exception:
        pass  # the app still works; each part loads on first use and has its own fallback


@asynccontextmanager
async def lifespan(_: FastAPI):
    threading.Thread(target=_warm_up, daemon=True).start()
    yield


app = FastAPI(title="Car or Air", version="0.2.0", lifespan=lifespan)
app.include_router(cases.router)
app.include_router(ai.router)


@app.get("/api/health")
def health():
    return {"ok": True, "disclaimer": cases.DISCLAIMER, "forecaster": forecaster.model_name()}


STATIC = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if STATIC.exists():
    app.mount("/", StaticFiles(directory=STATIC, html=True), name="frontend")
