# backend/routers/report.py
#
# Wire in to main.py:
#
#     from routers import report as report_lab
#     app.include_router(report_lab.router)
#
# No new static mount needed — X-ray images live in the same
# data/report_images/ folder you already mount at /reports.

import json
import random
from pathlib import Path
from typing import Any, List, Optional
from datetime import datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from services.ai_service import generate_text, generate_text_with_image

router = APIRouter(prefix="/api/report-lab", tags=["report-lab"])

BACKEND_ROOT = Path(__file__).resolve().parent.parent
CASES_PATH = BACKEND_ROOT / "data" / "report_lab_cases.json"

# In-memory conversation history storage
# Structure: { conversationId: {"case_id": "...", "history": [...], "findings": {...}, "checklist": [...]} }
CONVERSATIONS: dict[str, dict] = {}

HIDDEN_KEYS = {
    "ground_truth",
    "expected_findings",
    "differential_diagnoses",
    "common_mistakes",
    "teaching_points",
    "followup_questions",
}


def _load_cases() -> List[dict]:
    if not CASES_PATH.exists():
        raise HTTPException(status_code=500, detail="data/report_lab_cases.json not found")
    with open(CASES_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _find_case(case_id: str) -> dict:
    for case in _load_cases():
        if case.get("case_id") == case_id:
            return case
    raise HTTPException(status_code=404, detail="Case not found")


def _public_case_view(case: dict) -> dict:
    """Strip answer-key fields before sending a case to the frontend."""
    return {k: v for k, v in case.items() if k not in HIDDEN_KEYS}


# ---------- Schemas ----------

class EvaluateRequest(BaseModel):
    case_id: str
    findings: str
    diagnosis: str
    differentials: List[str] = []
    management: Optional[str] = ""


class EvaluateResponse(BaseModel):
    overallScore: int
    imageInterpretation: int
    diagnosis: int
    management: int
    reasoning: int
    communication: int
    strengths: List[str]
    missedFindings: List[str]
    clinicalPearls: List[str]
    nextQuestion: str


class InteractiveTutoringStartRequest(BaseModel):
    case_id: str
    student_findings: str
    image_base64: str
    image_mime: str = "image/png"


class InteractiveTutoringStartResponse(BaseModel):
    tutorMessage: str
    nextQuestion: str
    conversationId: str
    findings: List[str] = []
    checklist: List[dict] = []  # [{"finding": "...", "found": bool}, ...]


class InteractiveTutoringContinueRequest(BaseModel):
    case_id: str
    conversationId: str
    studentResponse: str
    image_base64: str
    image_mime: str = "image/png"


class InteractiveTutoringContinueResponse(BaseModel):
    tutorMessage: str
    nextQuestion: str
    teachingPoints: List[str] = []
    shouldContinue: bool
    findings: List[str] = []
    checklist: List[dict] = []


# ---------- Routes ----------

@router.get("/random")
def get_random_case():
    cases = _load_cases()
    if not cases:
        raise HTTPException(status_code=500, detail="No cases available")
    case = random.choice(cases)
    return _public_case_view(case)


@router.post("/evaluate", response_model=EvaluateResponse)
async def evaluate_case(payload: EvaluateRequest):
    case = _find_case(payload.case_id)
    ground_truth = case.get("ground_truth", {})

    prompt = _build_prompt(case, ground_truth, payload)
    raw = await generate_text(prompt, system=_SYSTEM_PROMPT, temperature=0.4, max_tokens=900)
    parsed = _parse_json_response(raw)
    return EvaluateResponse(**_coerce_defaults(parsed))


@router.post("/interactive/start", response_model=InteractiveTutoringStartResponse)
async def start_interactive_tutoring(payload: InteractiveTutoringStartRequest):
    """Start an interactive tutoring session using Gemma's multimodal vision with memory."""
    case = _find_case(payload.case_id)
    ground_truth = case.get("ground_truth", {})
    
    # Generate conversation ID and initialize history
    conversation_id = f"tutoring-{payload.case_id}-{random.getrandbits(32):08x}"
    
    # Build initial checklist from expected findings
    expected_findings = case.get('expected_findings', [])
    checklist = [{"finding": f, "found": False} for f in expected_findings]
    
    # Build conversation history structure
    CONVERSATIONS[conversation_id] = {
        "case_id": payload.case_id,
        "history": [
            {"role": "system", "content": _INTERACTIVE_SYSTEM_PROMPT},
        ],
        "findings": {},
        "checklist": checklist,
        "created_at": datetime.now().isoformat(),
    }
    
    prompt = _build_interactive_start_prompt(
        case=case,
        ground_truth=ground_truth,
        student_findings=payload.student_findings,
        checklist=checklist
    )
    
    raw = await generate_text_with_image(
        prompt=prompt,
        image_base64=payload.image_base64,
        image_mime=payload.image_mime,
        system=_INTERACTIVE_SYSTEM_PROMPT,
        temperature=0.6,
        max_tokens=800
    )
    
    # Store in conversation history
    CONVERSATIONS[conversation_id]["history"].append({
        "role": "user",
        "content": payload.student_findings
    })
    CONVERSATIONS[conversation_id]["history"].append({
        "role": "assistant",
        "content": raw
    })
    
    return InteractiveTutoringStartResponse(
        tutorMessage=raw,
        nextQuestion="What specific anatomical region or finding would you like to examine next?",
        conversationId=conversation_id,
        findings=[],
        checklist=checklist
    )


@router.post("/interactive/continue", response_model=InteractiveTutoringContinueResponse)
async def continue_interactive_tutoring(payload: InteractiveTutoringContinueRequest):
    """Continue the interactive tutoring dialogue with full conversation memory."""
    case = _find_case(payload.case_id)
    ground_truth = case.get("ground_truth", {})
    
    # Retrieve conversation
    if payload.conversationId not in CONVERSATIONS:
        raise HTTPException(status_code=404, detail="Conversation not found")
    
    conv = CONVERSATIONS[payload.conversationId]
    checklist = conv["checklist"]
    history = conv["history"]
    
    # Build prompt with full conversation history
    prompt = _build_interactive_followup_prompt(
        case=case,
        ground_truth=ground_truth,
        student_response=payload.studentResponse,
        conversation_history=history,
        checklist=checklist
    )
    
    raw = await generate_text_with_image(
        prompt=prompt,
        image_base64=payload.image_base64,
        image_mime=payload.image_mime,
        system=_INTERACTIVE_SYSTEM_PROMPT,
        temperature=0.6,
        max_tokens=800
    )
    
    # Store new exchange in conversation history
    conv["history"].append({
        "role": "user",
        "content": payload.studentResponse
    })
    conv["history"].append({
        "role": "assistant",
        "content": raw
    })
    
    # Extract findings from student response (basic pattern matching)
    findings = _extract_findings_from_response(payload.studentResponse, checklist)
    conv["findings"].update(findings)
    
    return InteractiveTutoringContinueResponse(
        tutorMessage=raw,
        nextQuestion="What else did you observe or would you like to explore?",
        teachingPoints=ground_truth.get("teaching_points", []),
        shouldContinue=True,
        findings=list(findings.keys()),
        checklist=checklist
    )


_SYSTEM_PROMPT = (
    "You are an experienced radiology attending mentoring a medical student. "
    "You already know the correct answer for this case — you are NOT diagnosing the "
    "image yourself. Your job is to grade the student's reasoning against the known "
    "answer, and teach. Be encouraging but honest. Respond with ONLY valid JSON, no "
    "markdown fences, no commentary."
)


_INTERACTIVE_SYSTEM_PROMPT = (
    "You are an experienced radiology professor conducting an interactive teaching session. "
    "You have a verified diagnosis and expected findings for this case. The student has submitted "
    "their interpretation. Your role is to:\n"
    "1. Acknowledge what they got right\n"
    "2. Gently guide them toward findings they missed\n"
    "3. Ask pointed questions about specific anatomical regions\n"
    "4. Reference the actual image — point to specific areas\n"
    "5. NOT simply reveal the answer — make them think and look\n\n"
    "Be encouraging, Socratic, and educational. Use the image as your teaching tool."
)


def _build_prompt(case: dict, ground_truth: dict, payload: EvaluateRequest) -> str:
    return f"""CASE GROUND TRUTH (do not reveal verbatim — use it to grade and teach):
- Confirmed diagnosis: {ground_truth.get('diagnosis')}
- Severity: {ground_truth.get('severity')}
- Key radiographic findings: {ground_truth.get('key_findings')}
- Expected findings the student should have noticed: {case.get('expected_findings')}
- Correct differential diagnoses: {case.get('differential_diagnoses')}
- Common student mistakes on this case: {case.get('common_mistakes')}
- Teaching points to weave in: {case.get('teaching_points')}

Grade the student on 5 axes, each out of 20 (sum = overall out of 100):
- imageInterpretation: did they correctly identify the key radiographic findings?
- diagnosis: is their primary diagnosis correct or defensible?
- management: is their management plan appropriate for this diagnosis/severity?
- reasoning: did they connect findings to diagnosis logically?
- communication: is their write-up clear and clinically structured?

Point out what they missed without simply stating the answer outright when possible —
nudge them toward it. End with ONE viva-style follow-up question.

Student submission for case {payload.case_id}:

Observed findings:
{payload.findings}

Likely diagnosis:
{payload.diagnosis}

Differential diagnoses considered:
{', '.join(payload.differentials) if payload.differentials else '(none listed)'}

Recommended management:
{payload.management or '(none provided)'}

Return ONLY valid JSON with this exact structure:
{{
  "overallScore": <int 0-100>,
  "imageInterpretation": <int 0-20>,
  "diagnosis": <int 0-20>,
  "management": <int 0-20>,
  "reasoning": <int 0-20>,
  "communication": <int 0-20>,
  "strengths": ["..."],
  "missedFindings": ["..."],
  "clinicalPearls": ["..."],
  "nextQuestion": "..."
}}"""


def _parse_json_response(raw: str) -> dict[str, Any]:
    # Same permissive extraction style as ai_service._parse_json_response,
    # so a stray markdown fence or preamble doesn't blow up the request.
    text = raw.strip()
    if text.startswith("```"):
        text = text.replace("```json", "").replace("```", "").strip()
    try:
        start = text.index("{")
        end = text.rindex("}") + 1
        return json.loads(text[start:end])
    except (ValueError, json.JSONDecodeError):
        return {}


def _coerce_defaults(parsed: dict[str, Any]) -> dict[str, Any]:
    # If the model call failed or produced unusable JSON, fail soft instead of 500ing.
    defaults = {
        "overallScore": 60,
        "imageInterpretation": 12,
        "diagnosis": 12,
        "management": 12,
        "reasoning": 12,
        "communication": 12,
        "strengths": [],
        "missedFindings": [],
        "clinicalPearls": [],
        "nextQuestion": "What would you look for on a follow-up film to confirm resolution?",
    }
    defaults.update(parsed)
    return defaults


def _build_interactive_start_prompt(case: dict, ground_truth: dict, student_findings: str, checklist: list) -> str:
    """Build initial Socratic tutoring prompt with checklist tracking."""
    findings_status = "\n".join([
        f"  {'✓' if item['found'] else '✗'} {item['finding']}" 
        for item in checklist
    ])
    
    return f"""CASE INFORMATION (verified, do not reveal directly):
- Confirmed diagnosis: {ground_truth.get('diagnosis')}
- Key radiographic findings to look for: {ground_truth.get('key_findings')}
- Expected observations: {case.get('expected_findings')}
- Common mistakes on this case: {case.get('common_mistakes')}
- Teaching points: {case.get('teaching_points')}

FINDINGS CHECKLIST (internal tracking, not shown to student):
{findings_status}

THE STUDENT'S INITIAL INTERPRETATION:
{student_findings}

YOUR TASK:
You are looking at the X-ray image together with the student. Your role is to:

1. Start by acknowledging what they did well (if anything)
2. Ask them to look more carefully at specific regions they haven't examined yet
3. Use phrases like: "Look at the [region]... what do you notice?" or "Can you point out where you see [finding]?"
4. Guide them through systematic observation without telling them the answer
5. Reference the checklist to decide what region to guide them to next
6. If they're on track, encourage them deeper; if they're off-track, gently redirect

Ask ONE focused question about a specific region or finding to guide their next observation.

Begin your teaching now. Be warm, encouraging, and Socratic."""


def _build_interactive_followup_prompt(case: dict, ground_truth: dict, student_response: str, conversation_history: list, checklist: list) -> str:
    """Build follow-up prompt with full conversation context and checklist."""
    # Build conversation transcript (excluding system message)
    transcript = "\n".join([
        f"{msg['role'].upper()}: {msg['content']}"
        for msg in conversation_history[1:]  # Skip system message
    ])
    
    findings_status = "\n".join([
        f"  {'✓' if item['found'] else '✗'} {item['finding']}" 
        for item in checklist
    ])
    
    return f"""CASE INFORMATION (verified, do not reveal directly):
- Confirmed diagnosis: {ground_truth.get('diagnosis')}
- Key radiographic findings to look for: {ground_truth.get('key_findings')}
- Expected observations: {case.get('expected_findings')}
- Teaching points: {case.get('teaching_points')}

FINDINGS CHECKLIST (internal tracking):
{findings_status}

CONVERSATION SO FAR:
{transcript}

STUDENT'S LATEST RESPONSE:
{student_response}

YOUR TASK:
Continue the Socratic dialogue. You are looking at the X-ray image together with the student.

Based on the conversation history and checklist:

1. Acknowledge progress they've made (what findings they've correctly identified)
2. If they've identified a key finding, ask them to explain WHY it matters clinically
3. If they're still missing important findings, guide them to the next unchecked region
4. Ask ONE more focused question to deepen their observation and reasoning
5. Reference specific anatomical landmarks or regions in the image
6. Remember what you already asked them about — don't repeat

Keep building their diagnostic reasoning step-by-step. Be encouraging and educational.
Guide them toward the findings they haven't yet noticed."""


def _extract_findings_from_response(student_response: str, checklist: list) -> dict[str, bool]:
    """Extract findings mentioned by student and update checklist status."""
    findings = {}
    response_lower = student_response.lower()
    
    for item in checklist:
        finding_lower = item["finding"].lower()
        # Simple keyword matching — in production, use NLP
        if finding_lower in response_lower or _fuzzy_match(finding_lower, response_lower):
            item["found"] = True
            findings[item["finding"]] = True
    
    return findings


def _fuzzy_match(finding: str, text: str) -> bool:
    """Basic fuzzy matching for finding keywords."""
    # Match common variations
    variations = {
        "consolidation": ["opac", "consolid", "infiltrate"],
        "effusion": ["fluid", "blunt", "meniscus"],
        "pneumothorax": ["pleural line", "collapse", "pneumo"],
        "cardiomegaly": ["enlarged heart", "cardia", "cardiothoracic"],
        "pleural": ["pleural", "costofrenic"],
        "air bronchogram": ["air broncho"],
    }
    
    for key, patterns in variations.items():
        if key in finding.lower():
            return any(pattern in text for pattern in patterns)
    
    return False