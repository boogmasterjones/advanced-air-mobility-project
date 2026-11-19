"""LLM routes. Owner: B (Jaden). Intake now; brief and evidence later."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ..contracts import BriefIn, IntakeIn, IntakeOut
from ..llm import provider

router = APIRouter(prefix="/api")


@router.post("/intake", response_model=IntakeOut)
def intake(body: IntakeIn):
    return IntakeOut(result=provider.intake(body.text))


@router.post("/brief")
def brief(body: BriefIn):
    raise HTTPException(501, "Brief not built yet; see task B4")


@router.get("/evidence")
def evidence():
    raise HTTPException(501, "Evidence not built yet; see task B6")
