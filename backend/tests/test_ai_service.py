import asyncio
import json
import unittest
from unittest.mock import patch

from services import ai_service


class FakeResponse:
    def __init__(self, payload):
        self._payload = payload
        self.status_code = 200

    def json(self):
        return self._payload


class FakeAsyncClient:
    def __init__(self, *args, **kwargs):
        self.timeout = kwargs.get("timeout")
        self.request_payload = None
        self.request_params = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def post(self, url, params=None, json=None):
        self.request_url = url
        self.request_params = params
        self.request_payload = json
        return FakeResponse({"candidates": [{"content": {"parts": [{"text": "ok"}]}}]})


class AIServiceTests(unittest.TestCase):
    def test_generate_text_passes_temperature_and_max_tokens(self):
        async def run_test():
            with patch("services.ai_service._gemini_key", return_value="test-key"), patch(
                "services.ai_service.httpx.AsyncClient", FakeAsyncClient
            ):
                client = await ai_service.generate_text("hello", temperature=0.7, max_tokens=256)

            self.assertEqual(client, "ok")

        asyncio.run(run_test())

    def test_validate_and_fill_patient_rejects_clinical_complaints(self):
        data = {
            "chief_complaint_en": "Shortness of breath on exertion",
            "history_en": "Works in construction",
            "vitals": {"bp": "120/80", "pulse": 72, "temp": 37.0, "spo2": 98},
        }

        self.assertIsNone(ai_service._validate_and_fill_patient(data, age=40, gender="Male"))

    def test_generate_patient_uses_full_case_prompt(self):
        async def run_test():
            async def fake_generate_text(prompt, system="", temperature=0.4, max_tokens=2048):
                self.assertIn("YOU choose every aspect", prompt)
                self.assertIn("module", prompt)
                self.assertIn("condition", prompt)
                self.assertIn("difficulty", prompt)
                return json.dumps({
                    "module": "chest_xray",
                    "condition": "Pneumonia",
                    "difficulty": "Medium",
                    "personality": "anxious",
                    "name_en": "Rina Begum",
                    "name_bn": "রিনা বেগম",
                    "age": 48,
                    "gender_en": "Female",
                    "gender_bn": "মহিলা",
                    "blood_group": "O+",
                    "weight_kg": 54,
                    "chief_complaint_en": "Doctor, this cough has been hanging around for a while and I feel really worried about it. I keep thinking it might just be stress, but it has been going on for several days and I cannot sleep properly at night. My chest feels strange and I am scared that something serious might be happening. I do not know how to explain it properly and I keep wondering whether this is dangerous, especially because my mother had a similar problem before she became very ill. I feel tired and I cannot stop thinking about what might be wrong.",
                    "chief_complaint_bn": "ডাক্তার, এই কাশি কিছুদিন ধরে ঘুরে ঘুরে আসছে আর আমি সত্যি খুব চিন্তিত। আমি ভাবি এটা হয়তো চাপের কারণে, কিন্তু কয়েক দিন ধরে চলেছে আর রাতে ঠিকমতো ঘুমাতে পারি না। আমার বুক অদ্ভুত লাগছে আর মনে হচ্ছে কিছু গুরুতর হচ্ছে। আমি কীভাবে বলব বুঝতে পারছি না আর ভাবছি এটা আসলে বিপজ্জনক কিছু কিনা।",
                    "history_en": "Works in a school office and has mild family history of respiratory illness.",
                    "history_bn": "স্কুলে অফিসে কাজ করেন এবং শ্বাসতন্ত্রের কিছু পারিবারিক ইতিহাস আছে।",
                    "followup_complaint_en": "I returned with the report and I still feel unwell, which worries me because I expected something to look clearer by now. I keep wondering whether the results mean this is serious or whether I am just overreacting, and that uncertainty is making me uneasy. I keep thinking about it when I try to sleep and it feels as if the whole situation is getting heavier by the day.",
                    "followup_complaint_bn": "রিপোর্ট নিয়ে এসেছি, তবু ভালো লাগছে না, যা আমাকে চিন্তিত করছে কারণ আমি মনে করেছিলাম এখন কিছু স্পষ্ট হবে। আমি ভাবছি রিপোর্টে কি সত্যি কোনো গুরুতর কিছু ধরা পড়েছে নাকি আমি শুধু বেশি চিন্তা করছি, আর এই অনিশ্চয়তা আমাকে খুব অস্বস্তিতে ফেলে দিচ্ছে। রাতে ঘুমাতে গেলে সেটাই বারবার মনে হয় আর মনে হয় এই অবস্থা দিনকে দিন আরও ভারি হচ্ছে।",
                    "vitals": {"bp": "120/80", "pulse": 78, "temp": 38.0, "spo2": 94},
                    "correct_diagnosis_en": "Community-acquired pneumonia",
                    "correct_diagnosis_bn": "কমিউনিটি-অ্যাকোয়ার্ড নিউমোনিয়া",
                    "recommended_medicines": ["Amoxicillin"],
                    "report_type": "xray",
                    "lab_results_en": "Chest x-ray shows infiltrate.",
                    "lab_results_bn": "বুকের এক্স-রেতে ইনফিল্ট্রেট দেখা যাচ্ছে।",
                })

            with patch("services.ai_service.generate_text", side_effect=fake_generate_text):
                patient = await ai_service.generate_patient(language="en")

            self.assertEqual(patient["template_condition"], "Pneumonia")
            self.assertEqual(patient["source"], "gemma")
            self.assertEqual(patient["chief_complaint_en"].startswith("Doctor"), True)

        asyncio.run(run_test())

    def test_evaluate_consultation_sets_source_tag(self):
        async def run_test():
            async def fake_generate_text(prompt, system="", temperature=0.4, max_tokens=2048):
                return json.dumps({"score": 88, "verdict_en": "Good", "verdict_bn": "ভাল", "strengths": ["Clear"], "improvements": ["More detail"], "medicine_feedback_en": "Fine", "medicine_feedback_bn": "ঠিক আছে", "missed_critical": []})

            with patch("services.ai_service.generate_text", side_effect=fake_generate_text):
                result = await ai_service.evaluate_consultation({"name_en": "Test", "age": 40, "chief_complaint_en": "Complaint", "history_en": "History", "vitals": {}, "correct_diagnosis_en": "X", "recommended_medicines": ["A"]}, "Advice", ["A"], "en")

            self.assertEqual(result["source"], "gemma")

        asyncio.run(run_test())


if __name__ == "__main__":
    unittest.main()
