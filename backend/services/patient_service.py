import asyncio
import uuid
from typing import Any

from services.ai_service import generate_patient

FOLLOWUP_AFTER = 3  # returning patient after every N new consultations


class SessionManager:
    def __init__(self) -> None:
        self.sessions: dict[str, dict[str, Any]] = {}

    async def create_session(self, language: str = "en") -> dict[str, Any]:
        session_id = str(uuid.uuid4())

        self.sessions[session_id] = {
            "id": session_id,
            "language": language,
            "consultation_count": 0,
            "current_patient": None,
            "current_visit_type": None,
            "pending_followups": [],
            "history": [],
            "_next_patient_task": None,
        }
        await self._advance_patient(session_id)
        self._start_prefetch(session_id)
        return self.get_state(session_id)

    def get_state(self, session_id: str) -> dict[str, Any]:
        session = self.sessions.get(session_id)
        if not session:
            raise KeyError("Session not found")

        patient = session.get("current_patient")
        return {
            "session_id": session_id,
            "language": session["language"],
            "consultation_count": session["consultation_count"],
            "visit_type": session.get("current_visit_type", "initial"),
            "patient": self._public_patient(patient, session.get("current_visit_type")),
            "history": session["history"][-5:],
        }

    def get_full_patient(self, session_id: str) -> dict[str, Any] | None:
        """Returns the complete patient record including the evaluation answer key."""
        session = self.sessions.get(session_id)
        if not session:
            return None
        return session.get("current_patient")

    def _start_prefetch(self, session_id: str) -> None:
        """Kick off generating the next initial-visit patient in the background.
        Guarded so we never orphan (and risk garbage-collecting) an
        already-running prefetch task, e.g. when a followup visit was served
        instead and the previous prefetch is still pending."""
        session = self.sessions.get(session_id)
        if not session:
            return
        existing = session.get("_next_patient_task")
        if existing is not None and not existing.done():
            return

        task = asyncio.create_task(generate_patient(session["language"]))
        task.add_done_callback(self._log_prefetch_errors)
        session["_next_patient_task"] = task

    @staticmethod
    def _log_prefetch_errors(task: asyncio.Task) -> None:
        if task.cancelled():
            return
        exc = task.exception()
        if exc is not None:
            import logging
            logging.getLogger(__name__).exception(
                "Background patient prefetch failed", exc_info=exc
            )

    def set_language(self, session_id: str, language: str) -> dict[str, Any]:
        session = self.sessions[session_id]
        session["language"] = language
        return self.get_state(session_id)

    async def record_consultation(
        self,
        session_id: str,
        doctor_advice: str,
        medicines: list[str],
        evaluation: dict[str, Any],
    ) -> dict[str, Any]:
        session = self.sessions[session_id]
        patient = session["current_patient"]
        visit_type = session.get("current_visit_type", "initial")

        record = {
            "patient_id": patient["id"],
            "patient_name": patient["name_en"],
            "visit_type": visit_type,
            "doctor_advice": doctor_advice,
            "medicines": medicines,
            "evaluation": evaluation,
        }
        session["history"].append(record)

        if visit_type == "initial":
            session["consultation_count"] += 1
            session["pending_followups"].append({
                "patient": patient,
                "previous_advice": doctor_advice,
                "previous_medicines": medicines,
                "return_after": session["consultation_count"] + FOLLOWUP_AFTER,
            })

        await self._advance_patient(session_id)
        self._start_prefetch(session_id)
        return self.get_state(session_id)

    async def _advance_patient(self, session_id: str) -> None:
        session = self.sessions[session_id]
        count = session["consultation_count"]

        due_followup = None
        remaining = []
        for item in session["pending_followups"]:
            if item["return_after"] <= count and due_followup is None:
                due_followup = item
            else:
                remaining.append(item)
        session["pending_followups"] = remaining

        if due_followup:
            session["current_patient"] = due_followup["patient"]
            session["current_visit_type"] = "followup"
            session["_followup_context"] = {
                "previous_advice": due_followup["previous_advice"],
                "previous_medicines": due_followup["previous_medicines"],
            }
            return

        task = session.get("_next_patient_task")
        if task is not None:
            try:
                session["current_patient"] = await task
            except Exception:
                session["current_patient"] = await generate_patient(session["language"])
        else:
            session["current_patient"] = await generate_patient(session["language"])

        session["current_visit_type"] = "initial"
        session["_next_patient_task"] = None
        session.pop("_followup_context", None)

    def get_followup_context(self, session_id: str) -> dict[str, Any] | None:
        session = self.sessions.get(session_id)
        if not session:
            return None
        return session.get("_followup_context")

    def _public_patient(self, patient: dict | None, visit_type: str | None) -> dict | None:
        if not patient:
            return None

        base = {
            "id": patient["id"],
            "name_en": patient["name_en"],
            "name_bn": patient["name_bn"],
            "age": patient["age"],
            "gender_en": patient["gender_en"],
            "gender_bn": patient["gender_bn"],
            "blood_group": patient["blood_group"],
            "weight_kg": patient["weight_kg"],
            "vitals": patient["vitals"],
            "visit_type": visit_type or "initial",
        }

        if visit_type == "followup":
            base["chief_complaint_en"] = patient.get(
                "followup_complaint_en",
                "Doctor, I came back with the test results you asked for. "
                "I still don't feel well from before.",
            )
            base["chief_complaint_bn"] = patient.get(
                "followup_complaint_bn",
                "ডাক্তার, আপনি যে পরীক্ষা বলেছিলেন তার রিপোর্ট নিয়ে এসেছি। "
                "আগের সমস্যা এখনো আছে।",
            )
            base["lab_results_en"] = patient.get("lab_results_en", "")
            base["lab_results_bn"] = patient.get("lab_results_bn", "")
            base["report_type"] = patient.get("report_type", "lab")
            base["report_image"] = patient.get("report_image", "")
        else:
            base["chief_complaint_en"] = patient["chief_complaint_en"]
            base["chief_complaint_bn"] = patient["chief_complaint_bn"]
            base["history_en"] = patient["history_en"]
            base["history_bn"] = patient["history_bn"]

        return base


session_manager = SessionManager()
