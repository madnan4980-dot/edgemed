import asyncio
import unittest
from unittest.mock import patch

from services.patient_service import SessionManager


class PatientServiceTests(unittest.TestCase):
    def test_create_session_uses_full_patient_from_session(self):
        async def run_test():
            manager = SessionManager()
            fake_patient = {
                "id": "p-test",
                "name_en": "Test Patient",
                "name_bn": "টেস্ট রোগী",
                "age": 40,
                "gender_en": "Female",
                "gender_bn": "মহিলা",
                "blood_group": "O+",
                "weight_kg": 60,
                "vitals": {"bp": "120/80", "pulse": 72, "temp": 37.0, "spo2": 98},
                "chief_complaint_en": "Chest pain",
                "chief_complaint_bn": "বুকে ব্যথা",
                "history_en": "No notable history",
                "history_bn": "কোন বিশেষ ইতিহাস নেই",
                "correct_diagnosis_en": "Stable angina",
                "correct_diagnosis_bn": "স্থিতিশীল অ্যানজাইনা",
                "recommended_medicines": ["Aspirin"],
            }

            async def fake_generate_patient(language=None):
                return fake_patient

            with patch("services.patient_service.generate_patient", new=fake_generate_patient):
                state = await manager.create_session(language="en")

            full_patient = manager.get_full_patient(state["session_id"])
            self.assertIsNotNone(full_patient)
            self.assertEqual(full_patient["id"], "p-test")
            self.assertEqual(full_patient["correct_diagnosis_en"], "Stable angina")

        asyncio.run(run_test())


if __name__ == "__main__":
    unittest.main()
