from unittest.mock import patch

from fastapi.testclient import TestClient

from main import app


client = TestClient(app)


def test_tts_route_returns_browser_fallback_when_speech_raises():
    with patch("main.synthesize_speech", side_effect=RuntimeError("speech exploded")):
        response = client.post(
            "/api/speech/tts",
            json={"text": "hello", "language": "en"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["source"] == "browser"
    assert "speech exploded" in body["error"]
