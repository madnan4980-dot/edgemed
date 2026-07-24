import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
import mimetypes
mimetypes.add_type("image/svg+xml", ".svg")

from services.ai_service import evaluate_consultation, evaluate_followup, order_test, patient_chat_reply
from services.patient_service import session_manager
from services.speech_service import (
    audio_to_base64,
    azure_configured,
    get_voice_info,
    synthesize_speech,
    test_azure_connection,
    transcribe_speech,
)
from routers import report as report_lab
from routers import prescription as prescription_lab
from routers import ecg as ecg_lab

BACKEND_ROOT = Path(__file__).resolve().parent
load_dotenv(BACKEND_ROOT / ".env", override=True)

app = FastAPI(title="EdgeMed — Medical Student Simulation", version="1.0.0")
app.include_router(report_lab.router)
app.include_router(prescription_lab.router)
app.include_router(ecg_lab.router)

origins = os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in origins],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)

REPORTS_DIR = Path(__file__).parent / "data" / "report_images"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/reports", StaticFiles(directory=str(REPORTS_DIR)), name="reports")

ECG_IMAGES_DIR = Path(__file__).parent / "data" / "ecg_images"
ECG_IMAGES_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/ecg-images", StaticFiles(directory=str(ECG_IMAGES_DIR)), name="ecg-images")


class StartSessionRequest(BaseModel):
    language: str = "en"
    category: str | None = None


class LanguageRequest(BaseModel):
    language: str


class ConsultationRequest(BaseModel):
    session_id: str | None = Field(default=None)
    sessionId: str | None = Field(default=None)
    doctor_advice: str | None = Field(default=None)
    doctorAdvice: str | None = Field(default=None)
    medicines: list[str] = Field(default_factory=list)

    def resolved_session_id(self) -> str | None:
        return self.session_id or self.sessionId

    def resolved_doctor_advice(self) -> str | None:
        return self.doctor_advice or self.doctorAdvice


class FollowupRequest(BaseModel):
    session_id: str | None = Field(default=None)
    sessionId: str | None = Field(default=None)
    doctor_report_review: str

    def resolved_session_id(self) -> str | None:
        return self.session_id or self.sessionId


class OrderTestRequest(BaseModel):
    session_id: str | None = Field(default=None)
    sessionId: str | None = Field(default=None)
    test_name: str | None = Field(default=None)
    testName: str | None = Field(default=None)

    def resolved_session_id(self) -> str | None:
        return self.session_id or self.sessionId

    def resolved_test_name(self) -> str | None:
        return self.test_name or self.testName


class ChatRequest(BaseModel):
    session_id: str | None = Field(default=None)
    sessionId: str | None = Field(default=None)
    message: str
    history: list[dict] = Field(default_factory=list)

    def resolved_session_id(self) -> str | None:
        return self.session_id or self.sessionId


class TTSRequest(BaseModel):
    text: str
    language: str = "en"
    gender: str | None = None


@app.get("/api/health")
async def health():
    azure_status = {"configured": azure_configured()}
    if azure_configured():
        azure_status.update(test_azure_connection())
    return {
        "status": "ok",
        "azure_speech": azure_status,
        "ai_configured": bool(os.getenv("GEMINI_API_KEY")),
        "voices": {
            "en": get_voice_info("en"),
            "bn": get_voice_info("bn"),
        },
    }


@app.get("/api/speech/voices")
async def speech_voices():
    return {"en": get_voice_info("en"), "bn": get_voice_info("bn")}


@app.post("/api/session/start")
async def start_session(req: StartSessionRequest):
    try:
        state = await session_manager.create_session(language=req.language, category=req.category)
        return state
    except Exception as exc:
        import logging
        logging.getLogger(__name__).exception("Failed to create session")
        raise HTTPException(status_code=500, detail=f"Session creation failed: {exc}")


@app.get("/api/session/{session_id}")
async def get_session(session_id: str):
    try:
        return session_manager.get_state(session_id)
    except KeyError:
        raise HTTPException(404, "Session not found")


@app.post("/api/session/{session_id}/language")
async def set_language(session_id: str, req: LanguageRequest):
    try:
        return session_manager.set_language(session_id, req.language)
    except KeyError:
        raise HTTPException(404, "Session not found")


@app.post("/api/speech/tts")
async def text_to_speech(req: TTSRequest):
    try:
        audio, error, voice = synthesize_speech(req.text, req.language, req.gender)
    except Exception as exc:
        return {
            "source": "browser",
            "text": req.text,
            "language": req.language,
            "error": f"Speech synthesis failed: {exc}",
            "azure_configured": azure_configured(),
        }

    if audio:
        return {
            "source": "azure",
            "audio_base64": audio_to_base64(audio),
            "mime_type": "audio/mpeg",
            "voice": voice,
        }
    return {
        "source": "browser",
        "text": req.text,
        "language": req.language,
        "error": error or "Azure TTS unavailable",
        "azure_configured": azure_configured(),
    }


@app.post("/api/speech/stt")
async def speech_to_text(language: str = "en", audio: UploadFile = File(...)):
    data = await audio.read()
    text, error = transcribe_speech(data, language)
    if text:
        return {"source": "azure", "text": text}
    return {
        "source": "browser",
        "message": error or "Azure Speech not configured. Use browser Web Speech API.",
        "azure_configured": azure_configured(),
    }


@app.post("/api/consultation/evaluate")
async def evaluate_doctor_consultation(req: ConsultationRequest):
    session_id = req.resolved_session_id()
    if not session_id:
        raise HTTPException(422, "session_id is required")

    try:
        state = session_manager.get_state(session_id)
    except KeyError:
        raise HTTPException(404, "Session not found")

    patient = state["patient"]
    if not patient:
        raise HTTPException(400, "No active patient")

    full_patient = session_manager.get_full_patient(session_id)
    if not full_patient:
        raise HTTPException(404, "Patient data not found")

    language = state.get("language", "en")

    if state["visit_type"] == "followup":
        ctx = session_manager.get_followup_context(session_id) or {}
        evaluation = await evaluate_followup(
            full_patient,
            ctx.get("previous_advice", ""),
            req.resolved_doctor_advice() or "",
            language,
        )
    else:
        evaluation = await evaluate_consultation(
            full_patient,
            req.resolved_doctor_advice() or "",
            req.medicines,
            language,
        )

    new_state = await session_manager.record_consultation(
        session_id,
        req.resolved_doctor_advice() or "",
        req.medicines,
        evaluation,
    )

    return {"evaluation": evaluation, "session": new_state}


@app.post("/api/consultation/order-test")
async def order_test_route(req: OrderTestRequest):
    try:
        state = session_manager.get_state(req.session_id)
    except KeyError:
        raise HTTPException(404, "Session not found")
    patient = session_manager.get_full_patient(req.session_id)
    if not patient:
        raise HTTPException(404, "Patient data not found")
    result = await order_test(patient, req.test_name, state.get("language", "en"))
    return result


@app.post("/api/consultation/chat")
async def chat_route(req: ChatRequest):
    try:
        state = session_manager.get_state(req.session_id)
    except KeyError:
        raise HTTPException(404, "Session not found")
    patient = session_manager.get_full_patient(req.session_id)
    if not patient:
        raise HTTPException(404, "Patient data not found")
    reply = await patient_chat_reply(patient, req.history, req.message, state.get("language", "en"))
    return {"reply": reply}


@app.get("/api/reports/{filename}")
async def get_report(filename: str):
    path = REPORTS_DIR / filename
    if not path.exists():
        raise HTTPException(404, "Report image not found")
    return FileResponse(path)

