"""Car or Air app entry point. Only wires routers together.

Do not add routes here: engine routes go in api/cases.py (owner A), AI routes in
api/ai.py (owner B). That keeps the two of you out of each other's files.
"""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from .api import ai, cases

app = FastAPI(title="Car or Air", version="0.1.0")
app.include_router(cases.router)
app.include_router(ai.router)


@app.get("/api/health")
def health():
    return {"ok": True, "disclaimer": cases.DISCLAIMER}


STATIC = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if STATIC.exists():
    app.mount("/", StaticFiles(directory=STATIC, html=True), name="frontend")
