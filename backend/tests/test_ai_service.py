import asyncio
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


if __name__ == "__main__":
    unittest.main()
