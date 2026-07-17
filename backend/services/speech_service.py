import base64
import html
import logging
import os
from pathlib import Path

import httpx
from dotenv import load_dotenv

# Always load .env from backend root — not dependent on cwd
BACKEND_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(BACKEND_ROOT / ".env", override=True)

logger = logging.getLogger(__name__)

# Primary + fallback voices per language and gender
VOICE_CONFIG = {
    "en": {
        "female": [
            {"locale": "en-US", "voice": "en-US-JennyNeural"},
        ],
        "male": [
            {"locale": "en-US", "voice": "en-US-GuyNeural"},
        ],
    },
    "bn": {
        "female": [
            {"locale": "bn-BD", "voice": "bn-BD-NabanitaNeural"},
            {"locale": "bn-IN", "voice": "bn-IN-TanishaaNeural"},
        ],
        "male": [
            {"locale": "bn-IN", "voice": "bn-IN-BashkarNeural"},
        ],
    },
}

STT_LOCALE = {"en": "en-US", "bn": "bn-BD"}


def _azure_key() -> str:
    return os.getenv("AZURE_SPEECH_KEY", "").strip()


def _azure_region() -> str:
    return os.getenv("AZURE_SPEECH_REGION", "eastus").strip()


def azure_configured() -> bool:
    return bool(_azure_key() and _azure_region())


def _voice_gender(gender: str | None) -> str:
    return "male" if str(gender or "").strip().lower() == "male" else "female"


def _voices_for_language(language: str, gender: str | None) -> list[dict]:
    language_voices = VOICE_CONFIG.get(language, VOICE_CONFIG["en"])
    gender_key = _voice_gender(gender)
    return language_voices.get(gender_key, language_voices.get("female", []))


def get_voice_info(language: str) -> dict:
    voices = _voices_for_language(language, None)
    primary = voices[0] if voices else {"locale": "en-US", "voice": "en-US-JennyNeural"}
    return {
        "language": language,
        **primary,
        "azure_configured": azure_configured(),
        "region": _azure_region() if azure_configured() else None,
    }


def _escape_ssml(text: str) -> str:
    return html.escape(text, quote=False)


def _build_ssml(text: str, locale: str, voice: str) -> str:
    escaped = _escape_ssml(text.strip())
    return (
        f"<?xml version='1.0' encoding='UTF-8'?>"
        f"<speak version='1.0' xmlns='http://www.w3.org/2001/10/synthesis' "
        f"xml:lang='{locale}'>"
        f"<voice name='{voice}'>"
        f"<prosody rate='0.92' pitch='-2%'>{escaped}</prosody>"
        f"</voice></speak>"
    )


def _azure_tts_request(ssml: str) -> tuple[bytes | None, str | None]:
    region = _azure_region()
    url = f"https://{region}.tts.speech.microsoft.com/cognitiveservices/v1"
    headers = {
        "Ocp-Apim-Subscription-Key": _azure_key(),
        "Content-Type": "application/ssml+xml; charset=utf-8",
        "X-Microsoft-OutputFormat": "audio-16khz-128kbitrate-mono-mp3",
        "User-Agent": "EdgeMed",
    }

    try:
        with httpx.Client(timeout=30.0) as client:
            resp = client.post(url, headers=headers, content=ssml.encode("utf-8"))
            if resp.status_code == 200:
                return resp.content, None
            return None, f"HTTP {resp.status_code}: {resp.text[:300]}"
    except Exception as exc:
        logger.exception("Azure TTS request failed")
        return None, str(exc)


def synthesize_speech(text: str, language: str, gender: str | None = None) -> tuple[bytes | None, str | None, str | None]:
    """
    Returns (audio_bytes, error_message, voice_used).
    Tries each voice in the fallback chain for the requested language and gender.
    """
    if not azure_configured():
        return None, "AZURE_SPEECH_KEY is not set in backend/.env", None

    if not text or not text.strip():
        return None, "No text provided for speech synthesis", None

    voices = _voices_for_language(language, gender)
    errors: list[str] = []

    for cfg in voices:
        ssml = _build_ssml(text, cfg["locale"], cfg["voice"])
        audio, err = _azure_tts_request(ssml)
        if audio:
            logger.info("Azure TTS ok: voice=%s locale=%s", cfg["voice"], cfg["locale"])
            return audio, None, cfg["voice"]
        errors.append(f"{cfg['voice']}: {err}")

    combined = "; ".join(errors)
    logger.error("All Azure TTS voices failed: %s", combined)
    return None, combined, None


def test_azure_connection() -> dict:
    """Quick connectivity check for health endpoint."""
    if not azure_configured():
        return {"ok": False, "configured": False, "error": "AZURE_SPEECH_KEY not configured"}

    for lang, phrase in [("en", "Hello"), ("bn", "নমস্কার")]:
        audio, err, _ = synthesize_speech(phrase, lang)
        if not audio:
            return {"ok": False, "configured": True, "error": f"{lang} TTS failed: {err}"}

    def _first_voice_name(language: str) -> str:
        voices = _voices_for_language(language, None)
        if not voices:
            return "en-US-JennyNeural" if language == "en" else "bn-BD-NabanitaNeural"
        return voices[0].get("voice", "en-US-JennyNeural" if language == "en" else "bn-BD-NabanitaNeural")

    return {
        "ok": True,
        "configured": True,
        "region": _azure_region(),
        "voices": {
            "en": _first_voice_name("en"),
            "bn": _first_voice_name("bn"),
        },
    }


def transcribe_speech(audio_bytes: bytes, language: str) -> tuple[str | None, str | None]:
    if not azure_configured():
        return None, "AZURE_SPEECH_KEY is not set"

    try:
        import azure.cognitiveservices.speech as speechsdk

        speech_config = speechsdk.SpeechConfig(
            subscription=_azure_key(),
            region=_azure_region(),
        )
        speech_config.speech_recognition_language = STT_LOCALE.get(language, "en-US")

        audio_format = speechsdk.audio.AudioStreamFormat(
            samples_per_second=16000,
            bits_per_sample=16,
            channels=1,
        )
        push_stream = speechsdk.audio.PushAudioInputStream(stream_format=audio_format)
        push_stream.write(audio_bytes)
        push_stream.close()

        audio_config = speechsdk.audio.AudioConfig(stream=push_stream)
        recognizer = speechsdk.SpeechRecognizer(
            speech_config=speech_config,
            audio_config=audio_config,
        )
        result = recognizer.recognize_once_async().get()

        if result.reason == speechsdk.ResultReason.RecognizedSpeech:
            return result.text, None
        return None, f"Recognition failed: {result.reason}"
    except Exception as exc:
        logger.exception("Azure STT failed")
        return None, str(exc)


def audio_to_base64(audio: bytes) -> str:
    return base64.b64encode(audio).decode("utf-8")
