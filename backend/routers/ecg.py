from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from services.ecg_service import evaluate_ecg_interpretation, generate_ecg_case

router = APIRouter(prefix="/api/ecg-lab", tags=["ecg-lab"])

# In-memory case store (same lightweight pattern as the other labs) — swap
# for whatever store prescription.py actually uses if it differs.
_CASES: dict[str, dict] = {}


class EvaluateEcgRequest(BaseModel):
    case_id: str
    heartRate: str = ""
    rhythm: str = ""
    axis: str = ""
    intervals: str = ""
    findings: str = ""
    diagnosis: str = ""
    management: str = Field(default="")


@router.get("/new")
async def new_ecg_case(language: str = "en"):
    try:
        case = await generate_ecg_case(language)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to generate ECG case: {exc}")

    _CASES[case["case_id"]] = case

    # Strip the answer key before sending to the client.
    public_case = {k: v for k, v in case.items() if k != "groundTruth"}
    return public_case


@router.post("/evaluate")
async def evaluate_ecg(req: EvaluateEcgRequest):
    case = _CASES.get(req.case_id)
    if not case:
        raise HTTPException(404, "Case not found or expired")

    try:
        evaluation = await evaluate_ecg_interpretation(case, req.dict(), language="en")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to evaluate ECG interpretation: {exc}")

    return evaluation