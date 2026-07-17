# backend/routers/prescription.py
#
# Wire in to main.py:
#
#     from routers import prescription as prescription_lab
#     app.include_router(prescription_lab.router)
#
# Unlike report-lab (cases pulled from a static JSON file), prescription
# cases are generated live by Gemma per request — so we keep the full case
# (including ground_truth) in a small in-memory store just long enough for
# the matching /evaluate call, and only ever send the public view to the
# frontend.

from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from services.prescription_service import evaluate_prescription, generate_prescription_case

router = APIRouter(prefix="/api/prescription-lab", tags=["prescription-lab"])

_CASE_STORE: Dict[str, Dict[str, Any]] = {}
_MAX_STORE = 200  # simple bound so a long-running server doesn't leak memory


def _remember(case: Dict[str, Any]) -> None:
    if len(_CASE_STORE) >= _MAX_STORE:
        _CASE_STORE.pop(next(iter(_CASE_STORE)))
    _CASE_STORE[case["case_id"]] = case


def _public_case_view(case: Dict[str, Any]) -> Dict[str, Any]:
    """Strip the answer key before sending a case to the frontend."""
    return {k: v for k, v in case.items() if k != "ground_truth"}


# ---------- Schemas ----------

class EvaluateRequest(BaseModel):
    case_id: str
    diagnosis: str
    plan: str
    medicines: List[str] = []


class EvaluateResponse(BaseModel):
    overallScore: int
    labInterpretation: int
    diagnosisAccuracy: int
    medicationSafety: int
    management: int
    communication: int
    strengths: List[str]
    missedFindings: List[str]
    safetyFlags: List[str]
    clinicalPearls: List[str]
    nextQuestion: str


# ---------- Routes ----------

@router.get("/new")
async def new_case(language: str = "en"):
    case = await generate_prescription_case(language)
    _remember(case)
    return _public_case_view(case)


@router.post("/evaluate", response_model=EvaluateResponse)
async def evaluate(payload: EvaluateRequest):
    case = _CASE_STORE.get(payload.case_id)
    if not case:
        raise HTTPException(
            status_code=404,
            detail="Case not found or expired — request a new case and resubmit.",
        )

    result = await evaluate_prescription(
        case,
        payload.diagnosis,
        payload.plan,
        payload.medicines,
        language="en",
    )
    return EvaluateResponse(**result)