import json
import os
import random
import uuid
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv

BACKEND_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(BACKEND_ROOT / ".env", override=True)

GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta"

ILLNESS_CATEGORIES = [
    "cardiac",
    "respiratory",
    "gastrointestinal",
    "infectious",
    "endocrine",
    "neurologic",
]

CATEGORY_HINTS = {
    "cardiac": "heart-related complaints such as chest discomfort, a heavy/tight feeling in the chest, palpitations-type sensations described in plain language, or symptoms brought on by exertion",
    "respiratory": "breathing/lung-related complaints such as persistent cough, breathing difficulty, or chest congestion",
    "gastrointestinal": "stomach/digestive complaints such as abdominal pain, nausea, vomiting, or bowel changes",
    "infectious": "fever/infection-related complaints such as ongoing fever, body aches, or suspected mosquito-borne illness",
    "endocrine": "hormonal/metabolic complaints such as unusual thirst, frequent urination, fatigue, or unexplained weight change",
    "neurologic": "brain/nerve-related complaints such as headache, dizziness, weakness, numbness, or trouble speaking",
}

COMMON_TESTS = [
    "CBC w/ differential", "Basic Metabolic Panel", "Liver Function (LFT)",
    "TSH", "Vitamin B12 / Folate", "Urinalysis", "CRP", "Troponin", "ECG",
]

FORBIDDEN_CLINICAL_TERMS = [
    "shortness of breath",
    "chest tightness",
    "on exertion",
    "dyspnea",
    "palpitations",
    "syncope",
    "malaise",
    "erythema",
    "edema",
    "tachycardia",
]

MIN_COMPLAINT_WORDS = 60

# Generation tuning. Lower temperature + smaller max_tokens cuts both latency
# and the odds of the model drifting into a clinical/chart-note register.
GEN_TEMPERATURE = 0.7
GEN_TEMPERATURE_RETRY = 0.55  # tighter on retry, favors format compliance
GEN_MAX_TOKENS = 300
GEN_RETRIES = 2

PATIENT_TEMPLATES_PATH = BACKEND_ROOT / "data" / "patients.json"
REPORT_IMAGES_ROOT = BACKEND_ROOT / "data" / "report_images"

IMAGING_TEST_KEYWORDS = ["x-ray", "xray", "chest x-ray", "chest xray", "cxr"]

REPORT_CASES_PATH = BACKEND_ROOT / "data" / "report_lab_cases.json"

DIAGNOSIS_KEYWORD_TO_FOLDER = {
    "pneumonia": "pneumonia",
    "consolidation": "pneumonia",
    "infiltrate": "pneumonia",
    "pneumonitis": "pneumonia",
    "tb": "pneumonia",
    "tuberculosis": "pneumonia",
    "effusion": "effusion",
    "pleural fluid": "effusion",
    "atelectasis": "atelectasis",
    "collapse": "atelectasis",
    "pneumothorax": "pneumothorax",
    "cardiomegaly": "cardiomegaly",
    "cardiac": "cardiomegaly",
    "heart failure": "cardiomegaly",
    "chf": "cardiomegaly",
    "cardiomyopathy": "cardiomegaly",
    "angina": "cardiomegaly",
    "coronary": "cardiomegaly",
    "mass": "mass",
    "tumor": "mass",
    "tumour": "mass",
    "malignan": "mass",
    "nodule": "nodule",
}


def _load_report_case_images() -> list[dict[str, Any]]:
    """Read the SAME file report.py's _load_cases() reads, so any image path
    we pick is guaranteed to already have been verified to exist on disk by
    scripts/generate_report_cases.py."""
    try:
        with REPORT_CASES_PATH.open("r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def _pick_xray_image(patient: dict[str, Any]) -> str | None:
    """Pick a real chest X-ray asset consistent with the patient's condition,
    falling back to a normal film if nothing category-specific is found."""
    if not REPORT_IMAGES_ROOT.exists():
        return None

    haystack = " ".join(
        str(patient.get(field, "")) for field in ("template_condition", "correct_diagnosis_en", "condition")
    ).lower()

    candidate_categories: list[str] = []
    for keyword, folder in DIAGNOSIS_KEYWORD_TO_FOLDER.items():
        if keyword in haystack:
            candidate_categories.append(folder)

    def _images_in(category: str) -> list[Path]:
        folder = REPORT_IMAGES_ROOT / category
        if not folder.is_dir():
            return []
        return [f for f in folder.iterdir() if f.suffix.lower() in {".png", ".jpg", ".jpeg", ".svg"}]

    pool: list[tuple[str, Path]] = []
    for category in dict.fromkeys(candidate_categories):
        for img in _images_in(category):
            pool.append((category, img))

    if pool:
        category, img = random.choice(pool)
        return f"{category}/{img.name}"

    for fallback_category in ("normal", "no_finding"):
        images = _images_in(fallback_category)
        if images:
            return f"{fallback_category}/{random.choice(images).name}"

    # Last resort: any image from any subfolder under report_images.
    any_images: list[tuple[str, Path]] = []
    for folder in REPORT_IMAGES_ROOT.iterdir():
        if folder.is_dir():
            for img in _images_in(folder.name):
                any_images.append((folder.name, img))

    if any_images:
        category, img = random.choice(any_images)
        return f"{category}/{img.name}"

    return None


def _report_image_exists(image_path: str | None) -> bool:
    if not image_path:
        return False
    return (REPORT_IMAGES_ROOT / image_path).is_file()


def _gemini_key() -> str:
    return os.getenv("GEMINI_API_KEY", "").strip()


def _gemini_model() -> str:
    return os.getenv("GEMINI_MODEL", "gemma-4-31b-it").strip()


async def generate_text(prompt: str, system: str = "", temperature: float = 0.4, max_tokens: int = 2048) -> str:
    api_key = _gemini_key()
    if not api_key:
        return _fallback_response(prompt)

    full_prompt = f"{system}\n\n{prompt}" if system else prompt
    url = f"{GEMINI_BASE}/models/{_gemini_model()}:generateContent"
    payload = {
        "contents": [{"parts": [{"text": full_prompt}]}],
        "generationConfig": {
            "temperature": temperature,
            "maxOutputTokens": max_tokens,
            "thinkingConfig": {"thinkingLevel": "MINIMAL"},
        },
    }

    async with httpx.AsyncClient(timeout=20.0) as client:
        resp = await client.post(url, params={"key": api_key}, json=payload)
        if resp.status_code != 200:
            return _fallback_response(prompt)
        data = resp.json()
        try:
            parts = data["candidates"][0]["content"]["parts"]
            answer_parts = [p["text"] for p in parts if not p.get("thought") and "text" in p]
            return "".join(answer_parts)
        except (KeyError, IndexError):
            return _fallback_response(prompt)


async def generate_text_with_image(prompt: str, image_base64: str, image_mime: str = "image/png", system: str = "", temperature: float = 0.4, max_tokens: int = 2048) -> str:
    """Generate text response with an image using Gemini's multimodal API."""
    api_key = _gemini_key()
    if not api_key:
        return _fallback_response(prompt)

    full_prompt = f"{system}\n\n{prompt}" if system else prompt
    url = f"{GEMINI_BASE}/models/{_gemini_model()}:generateContent"
    
    # Build multimodal parts: image + text
    payload = {
        "contents": [{
            "parts": [
                {
                    "inlineData": {
                        "mimeType": image_mime,
                        "data": image_base64
                    }
                },
                {"text": full_prompt}
            ]
        }],
        "generationConfig": {
            "temperature": temperature,
            "maxOutputTokens": max_tokens,
            "thinkingConfig": {"thinkingLevel": "MINIMAL"},
        },
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(url, params={"key": api_key}, json=payload)
        if resp.status_code != 200:
            return _fallback_response(prompt)
        data = resp.json()
        try:
            parts = data["candidates"][0]["content"]["parts"]
            answer_parts = [p["text"] for p in parts if not p.get("thought") and "text" in p]
            return "".join(answer_parts)
        except (KeyError, IndexError):
            return _fallback_response(prompt)


def _parse_generated_patient(raw: str) -> dict[str, Any] | None:
    parsed = _parse_json_response(raw)
    return parsed if isinstance(parsed, dict) else None


async def order_test(patient: dict[str, Any], test_name: str, language: str = "en") -> dict[str, Any]:
    normalized = test_name.strip().lower()

    # --- Imaging tests: use a real X-ray asset instead of having Gemma invent one ---
    if any(kw in normalized for kw in IMAGING_TEST_KEYWORDS):
        image_path = None
        if patient.get("report_type") == "xray" and patient.get("report_image"):
            candidate = patient["report_image"]
            if _report_image_exists(candidate):
                image_path = candidate

        if not image_path:
            image_path = _pick_xray_image(patient)

        return {
            "test_name": test_name,
            "report_type": "xray",
            "report_image": image_path or "",
        }

    # --- Lab / non-imaging tests: elaborate, numeric, multi-component results ---
    if "ecg" in normalized or "ekg" in normalized:
        prompt = f"""You are a hospital electrocardiography reporting system generating one realistic,
detailed ECG result for a training simulator.

Patient's real underlying diagnosis (reference only): {patient.get('correct_diagnosis_en')}
Patient history: {patient.get('history_en')}
Test ordered: {test_name}

Generate a concise ECG interpretation line with at least five components: heart rate,
rhythm, axis, PR interval, QRS duration, QTc, and any ST/T changes or abnormal findings.
Use plain clinical phrases and include a short flag when something is abnormal.

Return ONLY valid JSON:
{{
  "status": "normal" or "abnormal",
  "summary_en": "<ECG interpretation line with rate, rhythm, axis, intervals, and findings>",
  "summary_bn": "<Bengali version, same interpretation and values>"
}}"""
    else:
        prompt = f"""You are a hospital laboratory system generating one realistic, ELABORATE test
result for a training simulator — like a real lab report, not a one-word summary.

Patient's real underlying diagnosis (reference only): {patient.get('correct_diagnosis_en')}
Patient history: {patient.get('history_en')}
Test ordered: {test_name}

Generate 3-6 specific named components appropriate for this test. For CBC, include Hgb, WBC,
Platelet count, MCV, MCHC, RDW. For Basic Metabolic Panel, include Sodium, Potassium, Chloride,
Bicarbonate, BUN, Creatinine, Glucose, Calcium. For Urinalysis, include Color, Clarity, pH,
Specific gravity, RBC, WBC, Protein, Glucose, Nitrite, Leukocyte esterase. For CRP, include
CRP value and optionally ESR or fibrinogen.

Each component should have a realistic numeric value, correct unit, and a short flag when
abnormal (e.g. "low", "high", "microcytic"). If this test is plausibly abnormal given the
diagnosis, make the relevant component(s) abnormal with clinically consistent values;
components unrelated to the diagnosis should stay normal. Don't make every ordered test
abnormal — most unrelated tests should come back normal.

Format summary_en/summary_bn as ONE comma-separated line combining all components, e.g.:
"Hgb 9.2 g/dL (low), MCV 72 fL (microcytic), RDW 17% (high)."

Return ONLY valid JSON:
{{
  "status": "normal" or "abnormal",
  "summary_en": "<comma-separated components with real numbers and units, as above>",
  "summary_bn": "<Bengali version, same numbers/units>"
}}"""
    raw = await generate_text(prompt, temperature=0.45, max_tokens=300)
    result = _parse_json_response(raw)
    result["test_name"] = test_name
    result.setdefault("status", "normal")
    result.setdefault("summary_en", "Within normal limits.")
    result.setdefault("summary_bn", "স্বাভাবিক সীমার মধ্যে।")
    return result


async def patient_chat_reply(
    patient: dict[str, Any], history: list[dict[str, str]], message: str, language: str = "en"
) -> str:
    lang_hint = "Respond in Bengali." if language == "bn" else "Respond in English."
    convo = "\n".join(f"{h.get('role')}: {h.get('content')}" for h in history[-6:])
    prompt = f"""You are roleplaying AS the patient in a doctor-training simulator, staying fully in
character. Never reveal your diagnosis directly or use clinical terms — describe sensations and
worries the way a real patient would, consistent with your case below.

Your case: {patient.get('chief_complaint_en')}
Your history: {patient.get('history_en')}

Conversation so far:
{convo}

The doctor just asked: \"{message}\"

Reply as the patient only, 1-3 short sentences, plain worried language, no medical jargon. {lang_hint}"""
    raw = await generate_text(prompt, temperature=0.75, max_tokens=150)
    return raw.strip()


# In-memory recency tracker so Gemma doesn't repeat the same condition back
# to back across a session. This only informs the prompt — it never decides
# anything on Gemma's behalf.
_RECENT_CONDITIONS: list[str] = []
_RECENT_CONDITIONS_MAXLEN = 8


def _remember_condition(condition: str) -> None:
    if not condition:
        return
    _RECENT_CONDITIONS.append(condition)
    while len(_RECENT_CONDITIONS) > _RECENT_CONDITIONS_MAXLEN:
        _RECENT_CONDITIONS.pop(0)


def _load_inspiration_pool() -> list[dict[str, Any]]:
    """Optional seed conditions Gemma may draw from or ignore — a diversity
    hint, not a selection mechanism. Safe to return [] if the file is absent."""
    try:
        with PATIENT_TEMPLATES_PATH.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except (FileNotFoundError, json.JSONDecodeError):
        return []
    return [item for item in payload if isinstance(item, dict)] if isinstance(payload, list) else []


ALLOWED_MODULES = ["chest_xray", "laboratory", "imaging", "ecg", "prescription", "general"]


import re

_CHART_NOTE_PATTERN = re.compile(r"\bfor (the past |several )?\d+\s*(day|week)s?\b.*\bassociated with\b")


def _sounds_clinical_or_too_short(text: str) -> bool:
    if not text or len(text.split()) < MIN_COMPLAINT_WORDS:
        return True
    lowered = text.lower()
    if any(term in lowered for term in FORBIDDEN_CLINICAL_TERMS):
        return True
    return bool(_CHART_NOTE_PATTERN.search(lowered))


def _explain_violation(text: str) -> str | None:
    if not text or len(text.split()) < MIN_COMPLAINT_WORDS:
        return f"A complaint field was too short — needs at least {MIN_COMPLAINT_WORDS} words, minimum 4 sentences."
    lowered = text.lower()
    hit = next((term for term in FORBIDDEN_CLINICAL_TERMS if term in lowered), None)
    if hit:
        return f"A complaint field used the forbidden clinical term '{hit}' — describe the sensation in plain, non-medical language instead."
    if _CHART_NOTE_PATTERN.search(lowered):
        return "A complaint field read like a clinical chart note — rewrite as a rambling, worried patient voice."
    return None


# ---------------------------------------------------------------------------
# Fallback patient pool — one hand-written, properly vague & worried case per
# illness category. Used only if AI generation fails or repeatedly violates
# the "sounds like a real patient, not a chart note" rules. Kept varied and
# rule-compliant so a fallback never reads worse than a real generated case.
# ---------------------------------------------------------------------------

FALLBACK_PATIENTS: dict[str, dict[str, Any]] = {
    "cardiac": {
        "name_en": "Abdul Karim",
        "name_bn": "আব্দুল করিম",
        "blood_group": "B+",
        "weight_kg": 72,
        "chief_complaint_en": (
            "Doctor... I don't really know how to explain this properly. For the last few days "
            "something in my chest just feels heavy, like someone left a brick sitting there, and "
            "it comes and goes without any warning. When I climb the stairs at the market I have to "
            "stop halfway because I feel so worn out, which never used to happen before. My wife "
            "keeps telling me to rest more but I can't stop thinking about my older brother, he had "
            "some kind of heart problem a few years back and I'm honestly a little scared it might "
            "be the same thing happening to me now."
        ),
        "chief_complaint_bn": (
            "ডাক্তার... ঠিক কীভাবে বলব বুঝতে পারছি না। গত কয়েকদিন ধরে বুকের ভেতর কিছু একটা ভারী "
            "লাগছে, যেন কেউ একটা ইট রেখে দিয়েছে, আর এটা হঠাৎ হঠাৎ আসে যায়। বাজারে সিঁড়ি বেয়ে ওঠার সময় "
            "মাঝপথে থামতে হয়, এত তাড়াতাড়ি ক্লান্ত হয়ে যাই, আগে তো এমন হতো না। আমার স্ত্রী বারবার বিশ্রাম "
            "নিতে বলছেন, কিন্তু আমার বড় ভাইয়ের কথা মনে পড়ে যায়, কয়েক বছর আগে তারও হার্টের কোনো সমস্যা "
            "হয়েছিল, আর সত্যি বলতে আমার একটু ভয় করছে যে আমারও হয়তো একই কিছু হচ্ছে।"
        ),
        "history_en": "Works as a market trader, spends most of the day on his feet, smokes occasionally.",
        "history_bn": "বাজারে ব্যবসা করেন, সারাদিন দাঁড়িয়ে কাজ করতে হয়, মাঝেমধ্যে ধূমপান করেন।",
        "followup_complaint_en": (
            "Doctor, I brought the report you asked for. I looked at it but I don't understand most "
            "of it, honestly. The heaviness in my chest is still there some days, and I keep "
            "wondering if the results mean something serious."
        ),
        "followup_complaint_bn": (
            "ডাক্তার, আপনি যে রিপোর্টটা করতে বলেছিলেন সেটা নিয়ে এসেছি। দেখলাম কিন্তু বেশিরভাগ কিছু বুঝিনি, "
            "সত্যি বলতে। বুকের ভারী ভাবটা মাঝে মাঝে এখনো থাকে, আর ভাবছি রিপোর্টে কি খারাপ কিছু ধরা পড়েছে।"
        ),
        "vitals": {"bp": "148/94", "pulse": 90, "temp": 37.0, "spo2": 95},
        "correct_diagnosis_en": "Unstable angina / possible acute coronary syndrome — urgent cardiac workup needed.",
        "correct_diagnosis_bn": "অস্থির এনজাইনা / সম্ভাব্য একিউট করোনারি সিনড্রোম — জরুরি হার্ট পরীক্ষা প্রয়োজন।",
        "recommended_medicines": ["Aspirin 75mg", "Atorvastatin 20mg"],
        "report_type": "ecg",
        "report_image": "ecg_abnormal.svg",
        "lab_results_en": "ECG shows ST depression in lateral leads; troponin mildly elevated.",
        "lab_results_bn": "ইসিজিতে ল্যাটারাল লিডে এসটি ডিপ্রেশন দেখা যাচ্ছে; ট্রোপোনিন সামান্য বেশি।",
    },
    "respiratory": {
        "name_en": "Fatema Begum",
        "name_bn": "ফাতেমা বেগম",
        "blood_group": "O+",
        "weight_kg": 54,
        "chief_complaint_en": (
            "Doctor, I've had this cough for almost two weeks now and it just won't go away no matter "
            "what I try. Some nights it gets so bad I can't lie down properly and I end up sitting "
            "up for hours just to breathe a little easier. My neighbour said it might be because of "
            "the dust from the construction site next door, but I don't know, I've also lost my "
            "appetite and I feel tired all the time, which is scaring me a bit because my mother had "
            "some lung illness when she was around my age."
        ),
        "chief_complaint_bn": (
            "ডাক্তার, প্রায় দুই সপ্তাহ ধরে এই কাশিটা লেগেই আছে, কিছুতেই যাচ্ছে না। কিছু রাতে এত খারাপ হয়ে যায় "
            "যে শুয়ে থাকতে পারি না, ঘণ্টার পর ঘণ্টা বসে থাকতে হয় একটু সহজে শ্বাস নেওয়ার জন্য। পাশের বাড়ির "
            "প্রতিবেশী বলল হয়তো পাশের নির্মাণ কাজের ধুলার কারণে হচ্ছে, কিন্তু জানি না, খাওয়ার রুচিও চলে গেছে "
            "আর সবসময় ক্লান্ত লাগে, এটা একটু ভয় লাগছে কারণ আমার মায়েরও আমার বয়সে ফুসফুসের কী একটা সমস্যা "
            "হয়েছিল।"
        ),
        "history_en": "Housewife, lives near an active construction site, no prior lung conditions reported.",
        "history_bn": "গৃহিণী, নির্মাণ কাজের পাশে বাস করেন, আগে ফুসফুসের কোনো সমস্যার ইতিহাস নেই।",
        "followup_complaint_en": (
            "Doctor, here is the report from the test. I still get out of breath doing small chores "
            "around the house and I'm worried the paper says something bad about my lungs."
        ),
        "followup_complaint_bn": (
            "ডাক্তার, পরীক্ষার রিপোর্টটা নিয়ে এসেছি। এখনো ঘরের ছোটখাটো কাজ করতেও হাঁপিয়ে যাই, আর চিন্তা হচ্ছে "
            "কাগজে ফুসফুস নিয়ে খারাপ কিছু লেখা আছে কিনা।"
        ),
        "vitals": {"bp": "118/76", "pulse": 98, "temp": 38.2, "spo2": 91},
        "correct_diagnosis_en": "Community-acquired pneumonia / possible early TB — chest imaging and sputum test needed.",
        "correct_diagnosis_bn": "কমিউনিটি-অ্যাকোয়ার্ড নিউমোনিয়া / সম্ভাব্য প্রাথমিক টিবি — বুকের ইমেজিং ও থুতু পরীক্ষা প্রয়োজন।",
        "recommended_medicines": ["Amoxicillin-Clavulanate", "Paracetamol"],
        "report_type": "xray",
        "report_image": "xray_infiltrate.svg",
        "lab_results_en": "Chest X-ray shows patchy infiltrate in right lower lobe.",
        "lab_results_bn": "বুকের এক্স-রেতে ডান নিচের লোবে প্যাচি ইনফিল্ট্রেট দেখা যাচ্ছে।",
    },
    "gastrointestinal": {
        "name_en": "Mizanur Rahman",
        "name_bn": "মিজানুর রহমান",
        "blood_group": "A+",
        "weight_kg": 68,
        "chief_complaint_en": (
            "Doctor, my stomach has been giving me trouble for maybe three weeks and I really don't "
            "know what's causing it anymore. There's this burning feeling that comes up around here, "
            "especially after I eat anything spicy, and some days I feel sick enough that I skip "
            "meals altogether. I tried some antacid tablets from the pharmacy but they only help for "
            "a little while. My uncle passed away from something in his stomach a few years ago and "
            "I keep thinking about that, so I finally decided I should come and get it checked "
            "properly instead of guessing anymore."
        ),
        "chief_complaint_bn": (
            "ডাক্তার, আমার পেটের সমস্যাটা প্রায় তিন সপ্তাহ ধরে চলছে, আর সত্যিই বুঝতে পারছি না কী কারণে হচ্ছে। "
            "এখানে একটা জ্বালাপোড়া অনুভূতি হয়, বিশেষ করে ঝাল কিছু খেলে, আর কিছুদিন এত খারাপ লাগে যে খাবারই "
            "বাদ দিয়ে দিই। ফার্মেসি থেকে কিছু অ্যান্টাসিড খেয়েছিলাম কিন্তু সাময়িক উপকার হয়। আমার চাচা কয়েক "
            "বছর আগে পেটের কোনো সমস্যায় মারা গিয়েছিলেন, সেই কথাটাই বারবার মনে পড়ছে, তাই এবার ভাবলাম আন্দাজ "
            "না করে ভালোভাবে দেখিয়ে নেওয়াই ভালো।"
        ),
        "history_en": "Works long hours at a small shop, irregular meal times, occasional NSAID use for back pain.",
        "history_bn": "দোকানে দীর্ঘ সময় কাজ করেন, খাওয়ার সময় অনিয়মিত, কোমর ব্যথার জন্য মাঝে মাঝে ব্যথানাশক খান।",
        "followup_complaint_en": (
            "Doctor, I got the test done like you said. The burning is a little better some days but "
            "not gone, and I keep worrying the report is going to say something serious about my "
            "stomach."
        ),
        "followup_complaint_bn": (
            "ডাক্তার, আপনি বলার মতো পরীক্ষাটা করিয়েছি। জ্বালাপোড়াটা কিছুদিন একটু কম থাকে কিন্তু পুরোপুরি "
            "যায়নি, আর ভয় হচ্ছে রিপোর্টে পেট নিয়ে গুরুতর কিছু আছে কিনা।"
        ),
        "vitals": {"bp": "122/80", "pulse": 84, "temp": 37.0, "spo2": 98},
        "correct_diagnosis_en": "Peptic ulcer disease, likely NSAID/H. pylori related — endoscopy recommended.",
        "correct_diagnosis_bn": "পেপটিক আলসার, সম্ভবত এনএসএআইডি/এইচ. পাইলোরি জনিত — এন্ডোস্কোপি সুপারিশ করা হচ্ছে।",
        "recommended_medicines": ["Omeprazole 20mg", "Clarithromycin"],
        "report_type": "ultrasound",
        "report_image": "ultrasound_normal.svg",
        "lab_results_en": "H. pylori stool antigen positive; abdominal ultrasound otherwise unremarkable.",
        "lab_results_bn": "এইচ. পাইলোরি স্টুল অ্যান্টিজেন পজিটিভ; পেটের আল্ট্রাসাউন্ডে অন্য কোনো সমস্যা নেই।",
    },
    "infectious": {
        "name_en": "Shirin Akter",
        "name_bn": "শিরিন আক্তার",
        "blood_group": "AB+",
        "weight_kg": 49,
        "chief_complaint_en": (
            "Doctor, I've had a fever coming and going for the past five days and honestly I don't "
            "understand why it won't just break. My whole body aches, even my joints feel strange, "
            "and I get these cold shivers followed by feeling too hot a little while later. My "
            "neighbour's daughter had something similar last month and everyone in the area is "
            "talking about mosquitoes, so I'm honestly scared it might be that, especially since I "
            "noticed some small red spots on my arm yesterday that I've never had before."
        ),
        "chief_complaint_bn": (
            "ডাক্তার, গত পাঁচদিন ধরে জ্বর আসছে যাচ্ছে আর সত্যি বলতে বুঝতে পারছি না কেন এটা কমছেই না। সারা "
            "শরীর ব্যথা করছে, এমনকি গাঁটেও কেমন যেন লাগছে, আর হঠাৎ ঠান্ডা লাগে তারপর কিছুক্ষণ পর খুব গরম "
            "লাগে। প্রতিবেশীর মেয়েরও গত মাসে এরকম কিছু হয়েছিল আর এলাকায় সবাই মশার কথা বলছে, তাই সত্যি "
            "বলতে একটু ভয় লাগছে এটা সেরকম কিছু কিনা, বিশেষ করে গতকাল হাতে কিছু ছোট লাল দাগ দেখেছি যা আগে "
            "কখনো ছিল না।"
        ),
        "history_en": "Lives in a densely populated neighbourhood with recent local dengue cases reported.",
        "history_bn": "ঘনবসতিপূর্ণ এলাকায় থাকেন, এলাকায় সম্প্রতি ডেঙ্গুর কিছু কেস পাওয়া গেছে।",
        "followup_complaint_en": (
            "Doctor, here is the blood report from yesterday. The fever has come down a little but I "
            "still feel very weak, and I'm scared about what the numbers in the report mean."
        ),
        "followup_complaint_bn": (
            "ডাক্তার, গতকালের রক্ত পরীক্ষার রিপোর্টটা নিয়ে এসেছি। জ্বর একটু কমেছে কিন্তু এখনো খুব দুর্বল "
            "লাগছে, আর রিপোর্টের সংখ্যাগুলো নিয়ে ভয় লাগছে।"
        ),
        "vitals": {"bp": "100/65", "pulse": 105, "temp": 39.1, "spo2": 96},
        "correct_diagnosis_en": "Suspected dengue fever — CBC with platelet monitoring required.",
        "correct_diagnosis_bn": "সন্দেহজনক ডেঙ্গু জ্বর — প্লেটলেট মনিটরিং সহ সিবিসি প্রয়োজন।",
        "recommended_medicines": ["Paracetamol (no NSAIDs)", "Oral rehydration solution"],
        "report_type": "lab",
        "report_image": "",
        "lab_results_en": "Platelet count 92,000/uL, hematocrit rising, NS1 antigen positive.",
        "lab_results_bn": "প্লেটলেট কাউন্ট ৯২,০০০/uL, হেমাটোক্রিট বাড়ছে, এনএস১ অ্যান্টিজেন পজিটিভ।",
    },
    "endocrine": {
        "name_en": "Nasima Khatun",
        "name_bn": "নাসিমা খাতুন",
        "blood_group": "B-",
        "weight_kg": 61,
        "chief_complaint_en": (
            "Doctor, I don't know exactly how to put this but something has felt off with me for a "
            "couple of months now. I'm thirsty all the time no matter how much water I drink, and I "
            "have to use the bathroom constantly which is embarrassing at work. I've also lost some "
            "weight without trying, which my sister noticed before I even did, and it scares me a "
            "little because I remember my mother going through something similar before she was "
            "diagnosed with sugar problems, and I keep wondering if the same thing is starting with "
            "me now."
        ),
        "chief_complaint_bn": (
            "ডাক্তার, ঠিক কীভাবে বলব জানি না কিন্তু গত কয়েক মাস ধরে শরীরে কেমন যেন একটা গড়বড় অনুভব করছি। "
            "যতই পানি খাই না কেন সবসময় তেষ্টা লাগে, আর বারবার বাথরুমে যেতে হয় যা অফিসে বিব্রতকর। "
            "চেষ্টা ছাড়াই কিছু ওজনও কমে গেছে, যা আমার আগে বোনই খেয়াল করেছে আমার আগে, আর একটু ভয় লাগছে কারণ "
            "আমার মায়েরও এরকম কিছু হয়েছিল সুগারের সমস্যা ধরা পড়ার আগে, তাই ভাবছি আমারও কি একই কিছু শুরু "
            "হচ্ছে।"
        ),
        "history_en": "Office worker, sedentary lifestyle, family history of diabetes on mother's side.",
        "history_bn": "অফিসে কাজ করেন, বসে থাকার কাজ বেশি, মায়ের দিক থেকে ডায়াবেটিসের পারিবারিক ইতিহাস আছে।",
        "followup_complaint_en": (
            "Doctor, I had the blood test done. I'm still just as thirsty as before and I'm nervous "
            "about what the sugar numbers on this report actually mean for me."
        ),
        "followup_complaint_bn": (
            "ডাক্তার, রক্ত পরীক্ষাটা করিয়েছি। আগের মতোই তেষ্টা লাগছে, আর এই রিপোর্টের সুগারের সংখ্যাগুলো "
            "আমার জন্য আসলে কী বোঝায় তা নিয়ে চিন্তিত।"
        ),
        "vitals": {"bp": "128/82", "pulse": 88, "temp": 36.9, "spo2": 98},
        "correct_diagnosis_en": "New-onset type 2 diabetes mellitus — HbA1c and fasting glucose confirm diagnosis.",
        "correct_diagnosis_bn": "নতুন ধরা পড়া টাইপ ২ ডায়াবেটিস — এইচবিএ১সি ও ফাস্টিং গ্লুকোজ নির্ণয় নিশ্চিত করছে।",
        "recommended_medicines": ["Metformin 500mg", "Lifestyle and diet counseling"],
        "report_type": "lab",
        "report_image": "",
        "lab_results_en": "Fasting glucose 182 mg/dL, HbA1c 8.1%.",
        "lab_results_bn": "ফাস্টিং গ্লুকোজ ১৮২ mg/dL, এইচবিএ১সি ৮.১%।",
    },
    "neurologic": {
        "name_en": "Habibur Rahman",
        "name_bn": "হাবিবুর রহমান",
        "blood_group": "O-",
        "weight_kg": 75,
        "chief_complaint_en": (
            "Doctor, this is a bit hard to explain but I've been getting these headaches for about "
            "ten days now, mostly on one side, and sometimes everything around me feels like it's "
            "spinning slightly when I stand up too fast. Yesterday my hand felt strange for a few "
            "minutes, kind of tingly and weak, and it went away on its own but it really frightened "
            "me. My colleague at work said his father had a stroke that started with something "
            "similar, so I couldn't stop thinking about it all night and decided I had to come in "
            "today."
        ),
        "chief_complaint_bn": (
            "ডাক্তার, এটা একটু ব্যাখ্যা করা কঠিন কিন্তু প্রায় দশদিন ধরে আমার মাথাব্যথা হচ্ছে, বেশিরভাগ এক "
            "পাশে, আর মাঝে মাঝে হঠাৎ দাঁড়ালে চারপাশ একটু ঘুরতে থাকে বলে মনে হয়। গতকাল আমার হাতটা কেমন যেন "
            "অদ্ভুত লাগছিল কয়েক মিনিটের জন্য, শিরশির করছিল আর দুর্বল লাগছিল, নিজে থেকেই ঠিক হয়ে গেছে কিন্তু "
            "সত্যিই ভয় পেয়েছিলাম। অফিসের সহকর্মী বলল তার বাবার স্ট্রোক এরকম কিছু দিয়েই শুরু হয়েছিল, তাই "
            "সারারাত সেটাই মাথায় ঘুরছিল আর আজ আসতেই হলো।"
        ),
        "history_en": "Office employee, high stress job, occasional high blood pressure readings at home.",
        "history_bn": "অফিসে চাকরি করেন, চাপের কাজ, বাড়িতে মাঝে মাঝে রক্তচাপ বেশি পাওয়া গেছে।",
        "followup_complaint_en": (
            "Doctor, I had the scan done. I still get these headaches now and then, and I'm anxious "
            "about whether the scan found something in my brain."
        ),
        "followup_complaint_bn": (
            "ডাক্তার, স্ক্যানটা করিয়ে এনেছি। এখনো মাঝে মাঝে মাথাব্যথা হয়, আর চিন্তিত আছি স্ক্যানে মস্তিষ্কে "
            "কিছু ধরা পড়েছে কিনা।"
        ),
        "vitals": {"bp": "156/98", "pulse": 82, "temp": 37.0, "spo2": 97},
        "correct_diagnosis_en": "Transient ischemic attack suspected — urgent CT/MRI and stroke workup needed.",
        "correct_diagnosis_bn": "ট্রানজিয়েন্ট ইস্কেমিক অ্যাটাক সন্দেহ — জরুরি সিটি/এমআরআই ও স্ট্রোক পরীক্ষা প্রয়োজন।",
        "recommended_medicines": ["Aspirin 75mg", "Antihypertensive (per BP control)"],
        "report_type": "ct",
        "report_image": "ct_normal.svg",
        "lab_results_en": "CT brain shows no acute hemorrhage; carotid Doppler pending.",
        "lab_results_bn": "সিটি ব্রেইনে তীব্র রক্তক্ষরণের প্রমাণ নেই; ক্যারোটিড ডপলার অপেক্ষমাণ।",
    },
}


def _fallback_patient(category: str, age: int, gender: str) -> dict[str, Any]:
    template = FALLBACK_PATIENTS.get(category, FALLBACK_PATIENTS["cardiac"])
    patient = dict(template)
    patient["id"] = f"p-{uuid.uuid4().hex[:6]}"
    patient["age"] = age
    patient["gender_en"] = gender
    patient["gender_bn"] = "পুরুষ" if gender == "Male" else "মহিলা"
    return patient


def _validate_and_fill_patient(data: dict[str, Any], age: int, gender: str) -> dict[str, Any] | None:
    if not isinstance(data, dict):
        return None

    complaint = data.get("chief_complaint_en", "") or ""
    followup = data.get("followup_complaint_en", "") or ""
    if _sounds_clinical_or_too_short(complaint):
        return None
    if followup and _sounds_clinical_or_too_short(followup):
        return None

    patient = dict(data)
    fallback = _fallback_patient("cardiac", age, gender)
    for key, default in fallback.items():
        if key == "vitals":
            patient.setdefault("vitals", default.copy())
        elif key not in patient or patient[key] in (None, ""):
            patient[key] = default

    patient["age"] = int(patient.get("age", age) or age)
    patient["weight_kg"] = float(patient.get("weight_kg", fallback["weight_kg"]) or fallback["weight_kg"])
    patient["recommended_medicines"] = patient.get("recommended_medicines") or fallback["recommended_medicines"]
    return patient


def _build_patient_prompt(category: str, age: int, gender: str) -> str:
    return f"""Generate one realistic patient case for a doctor-training simulator in present-day
Bangladesh. The DOCTOR must do the diagnostic work — your job is to make the patient describe
their problem the way an actual worried, non-medical person would, NOT the way a doctor would
chart it.

Illness category (for YOUR reference only — the patient must never name or hint at the diagnosis): {category}
Patient age: approximately {age}
Patient gender: {gender}

MANDATORY RULES for chief_complaint_en / chief_complaint_bn — read carefully, these are checked
programmatically and the case will be rejected if violated:
1. MINIMUM 4 full sentences, MINIMUM 60 words. The patient should be vague and rambling —
    use a worried, nervous tone rather than a neat clinical summary. Include at least one
    explicit hesitation (for example: "um", "...", "I don't know how to explain this").
2. The patient describes SENSATIONS, FEARS and everyday observations in plain language;
    DO NOT use medical terms, clinical labels, or technical phrasing.
3. NEVER use these words or close equivalents: {', '.join(FORBIDDEN_CLINICAL_TERMS)}
4. NEVER produce a chart-note style symptom list or timeframe (e.g. "symptom X and symptom Y
    for a few days, associated with symptom Z"). That register is explicitly forbidden —
    patients speak in sensations, worries, and hesitations, not shorthand lists.
5. Show visible fear, confusion, or worry — mention what they're scared it might be, what a
    neighbour/relative said, or how it's disrupting work/family life; concrete small details
    (a neighbour's comment, a recent event) help sell the nervous tone.
6. Include at least one trailing thought or self-questioning line (e.g., "I keep thinking it's
    nothing, but I'm worried...") so the voice reads like a real anxious person, not a
    rehearsed description.

GOOD EXAMPLE (cardiac case, patient does NOT know this) — study this length and tone closely:
"Doctor... I don't know how to say it properly. My chest feels tight, like something is sitting
on it. When I climb up at the construction site, I get out of breath very quickly. It's been like
this for a few days. I feel worn out even when I haven't done much. My wife keeps asking if I'm
okay and honestly I'm a little scared, my father passed suddenly around my age and I keep
thinking about that."

Now write the case. Give the patient a believable Bangladeshi occupation, home situation, and
social context. Keep the underlying clinical picture (vitals, labs, diagnosis) medically accurate
and internally consistent with {category}. Bengali translations should be natural, idiomatic, and
the SAME length and worried tone as the English — not a short literal translation.

Return ONLY valid JSON, no markdown fences, no commentary, in exactly this structure:
{{
  "name_en": "<full Bangladeshi name>",
  "name_bn": "<same name in Bengali script>",
  "age": {age},
  "gender_en": "{gender}",
  "gender_bn": "<পুরুষ or মহিলা>",
  "blood_group": "<A+/A-/B+/B-/AB+/AB-/O+/O->",
  "weight_kg": <realistic integer for this age/gender>,
  "chief_complaint_en": "<minimum 4 sentences, per rules above>",
  "chief_complaint_bn": "<Bengali version, same length and register>",
  "history_en": "<2-3 sentences: occupation, lifestyle, relevant family/social history>",
  "history_bn": "<Bengali version>",
  "followup_complaint_en": "<2-3 sentences the patient says when returning with test results, plain worried language, same rules as above>",
  "followup_complaint_bn": "<Bengali version>",
  "vitals": {{"bp": "<systolic/diastolic>", "pulse": <int 55-130>, "temp": <float 36.0-40.5>, "spo2": <int 88-100>}},
  "correct_diagnosis_en": "<diagnosis + next steps — this field CAN be clinical, it's the answer key>",
  "correct_diagnosis_bn": "<Bengali version>",
  "recommended_medicines": ["<medicine 1>", "<medicine 2>"],
  "report_type": "<one of: lab, xray, ct, ultrasound, ecg, clinical>",
  "lab_results_en": "<relevant findings with realistic values>",
  "lab_results_bn": "<Bengali version>"
}}"""


def _build_full_case_prompt(language: str = "en", category: str | None = None) -> str:
     inspiration = _load_inspiration_pool()
     inspiration_conditions = sorted({str(t.get("condition")) for t in inspiration if t.get("condition")})
     avoid_note = (
          f"Avoid repeating these recently-used conditions: {', '.join(_RECENT_CONDITIONS)}."
          if _RECENT_CONDITIONS else ""
     )
     language_hint = "Bengali" if language == "bn" else "English"

     category_instruction = ""
     if category and category in CATEGORY_HINTS:
          category_instruction = f"""
IMPORTANT — CATEGORY CONSTRAINT: The student specifically chose to practice **{category}**
cases. The condition you design MUST fall within this category: {CATEGORY_HINTS[category]}.
Do not pick a condition from a different body system, even if it seems interesting. You still
choose the exact condition, difficulty, module, and patient details yourself — just within
this category.
"""

     return f"""You are designing a complete patient case for a doctor-training simulator in
present-day Bangladesh. YOU choose every aspect of the scenario — module, condition,
difficulty, patient demographics, and personality — then write the patient's dialogue.
The DOCTOR using this simulator must do the diagnostic work; your job is both to design
a good teaching case AND to voice the patient realistically.

{category_instruction}

Choose a module from: {', '.join(ALLOWED_MODULES)} (pick whichever best fits the
condition you choose — e.g. a respiratory case suits chest_xray, a cardiac rhythm
case suits ecg, a general complaint suits laboratory or prescription).

For inspiration only, conditions previously used in this simulator include:
{', '.join(inspiration_conditions) or 'none on record'}. You are free to pick any of
these, a variation, or an entirely different realistic condition appropriate for a
Bangladeshi primary/secondary care setting — prioritize variety and clinical relevance
over sticking to this list. {avoid_note}

Pick age (realistic for the condition), gender, and a personality (e.g. anxious,
reserved, talkative, guarded, practical) that fits how a real person with this
condition and background might present.

MANDATORY RULES for chief_complaint_en / chief_complaint_bn — checked programmatically,
case is rejected if violated:
1. MINIMUM 4 full sentences, MINIMUM {MIN_COMPLAINT_WORDS} words. Vague and rambling,
    worried/nervous tone, at least one explicit hesitation ("um", "...", "I don't know
    how to explain this").
2. Describe SENSATIONS, FEARS, everyday observations in plain language — NO medical
    terms, clinical labels, or technical phrasing.
3. NEVER use these words or close equivalents: {', '.join(FORBIDDEN_CLINICAL_TERMS)}
4. NEVER produce a chart-note style symptom list or timeframe (e.g. "symptom X and Y
    for a few days, associated with symptom Z").
5. Show visible fear/confusion/worry — mention what they're scared it might be, what a
    neighbour/relative said, or how it's disrupting work/family life.
6. Include at least one trailing thought or self-questioning line.

Keep the underlying clinical picture (vitals, labs, diagnosis) medically accurate and
internally consistent with the condition you chose. Write chief_complaint_en/bn and
history_en/bn in {language_hint} as the primary language; always populate both *_en
and *_bn fields regardless (translate naturally, not literally).

Return ONLY valid JSON, no markdown fences, no commentary, in exactly this structure:
{{
  "module": "<one of: {', '.join(ALLOWED_MODULES)}>",
  "condition": "<the condition/diagnosis category you chose, short label>",
  "difficulty": "<Easy|Medium|Hard>",
  "personality": "<one word/short phrase describing how this patient presents>",
  "name_en": "<full Bangladeshi name>",
  "name_bn": "<same name in Bengali script>",
  "age": <realistic int for this condition>,
  "gender_en": "Male|Female",
  "gender_bn": "<পুরুষ or মহিলা>",
  "blood_group": "<A+/A-/B+/B-/AB+/AB-/O+/O->",
  "weight_kg": <realistic integer>,
  "chief_complaint_en": "<minimum 4 sentences, per rules above>",
  "chief_complaint_bn": "<Bengali version, same length and register>",
  "history_en": "<2-3 sentences: occupation, lifestyle, relevant family/social history>",
  "history_bn": "<Bengali version>",
  "followup_complaint_en": "<2-3 sentences when returning with test results, same rules>",
  "followup_complaint_bn": "<Bengali version>",
  "vitals": {{"bp": "<systolic/diastolic>", "pulse": <int 55-130>, "temp": <float 36.0-40.5>, "spo2": <int 88-100>}},
  "correct_diagnosis_en": "<diagnosis + next steps — this field CAN be clinical, it's the answer key>",
  "correct_diagnosis_bn": "<Bengali version>",
  "recommended_medicines": ["<medicine 1>", "<medicine 2>"],
  "report_type": "<one of: lab, xray, ct, ultrasound, ecg, clinical>",
  "lab_results_en": "<relevant findings with realistic values>",
  "lab_results_bn": "<Bengali version>"
}}"""


async def generate_patient(language: str = "en", category: str | None = None) -> dict[str, Any]:
    system = (
        "You are a medical education content designer AND generator producing realistic, "
        "fictional patient cases for training doctors in Bangladesh. You choose the clinical "
        "scenario yourself — condition, difficulty, demographics, personality — then write "
        "patient dialogue the way real anxious patients talk, never like a clinical chart note. "
        "Short, clinical-sounding complaints, short/invalid complaints, scenario choices that ignore the instructions, "
        "or picking a condition outside a requested category are all considered failures."
    )

    last_violation = None
    for attempt in range(GEN_RETRIES + 1):
        temperature = GEN_TEMPERATURE if attempt == 0 else GEN_TEMPERATURE_RETRY
        prompt = _build_full_case_prompt(language, category)
        if last_violation:
            prompt += f"\n\nYour previous attempt was rejected for this specific reason: {last_violation}\nFix that specific issue and try again, still designing your own scenario within the required category."

        raw = await generate_text(prompt, system=system, temperature=temperature, max_tokens=GEN_MAX_TOKENS + 200)
        patient = _parse_generated_patient(raw)
        if patient is None:
            last_violation = "Response was not valid JSON matching the required structure."
            continue

        complaint = patient.get("chief_complaint_en", "") or ""
        followup = patient.get("followup_complaint_en", "") or ""
        violation = _explain_violation(complaint) or (_explain_violation(followup) if followup else None)
        if violation:
            last_violation = violation
            continue

        gender = patient.get("gender_en") if patient.get("gender_en") in ("Male", "Female") else "Male"
        age = int(patient.get("age") or 40)
        patient = _validate_and_fill_patient(patient, age, gender)
        if patient is not None:
            patient["id"] = f"ai-{uuid.uuid4().hex[:8]}"
            patient.setdefault("report_image", "")
            condition = patient.get("condition") or patient.get("correct_diagnosis_en") or patient.get("report_type") or "unspecified"
            patient["template_condition"] = condition
            patient["source"] = "gemma"
            _remember_condition(str(condition))
            return patient

    fallback_category = category if category in ILLNESS_CATEGORIES else random.choice(ILLNESS_CATEGORIES)
    age = random.randint(20, 70)
    gender = random.choice(["Male", "Female"])
    fallback = _fallback_patient(fallback_category, age, gender)
    fallback["template_condition"] = fallback_category
    fallback["source"] = "fallback"
    return fallback


def _fallback_response(prompt: str) -> str:
    if "evaluate" in prompt.lower() or "score" in prompt.lower():
        return json.dumps({
            "score": 70,
            "verdict_en": "Reasonable approach. Consider ordering relevant investigations.",
            "verdict_bn": "যুক্তিসঙ্গত পদ্ধতি। প্রাসঙ্গিক পরীক্ষা করার কথা বিবেচনা করুন।",
            "strengths": ["Good clinical reasoning"],
            "improvements": ["Order confirmatory tests", "Document follow-up plan"],
            "medicine_feedback_en": "Medication choices are acceptable for initial management.",
            "medicine_feedback_bn": "প্রাথমিক চিকিৎসার জন্য ওষুধের পছন্দ গ্রহণযোগ্য।",
        })
    return "AI response unavailable. Please configure GEMINI_API_KEY."


async def evaluate_consultation(
    patient: dict[str, Any],
    doctor_advice: str,
    medicines: list[str],
    language: str,
) -> dict[str, Any]:
    lang_note = "Respond in Bengali for verdict_bn fields and English for verdict_en fields."
    if language == "bn":
        lang_note = "Prioritize Bengali in all feedback fields."

    prompt = f"""You are a senior medical professor evaluating a medical student's consultation.

Patient case:
- Name: {patient.get('name_en')}
- Age: {patient.get('age')}
- Chief complaint: {patient.get('chief_complaint_en')}
- History: {patient.get('history_en')}
- Vitals: {json.dumps(patient.get('vitals', {}))}
- Correct diagnosis (reference): {patient.get('correct_diagnosis_en')}
- Recommended medicines: {', '.join(patient.get('recommended_medicines', []))}

Doctor's spoken advice: {doctor_advice}
Doctor's prescribed medicines: {', '.join(medicines) if medicines else 'None specified'}
Evaluate all aspects of the consultation, especially:
1. Clinical reasoning: Did the student identify the correct problem, interpret the case appropriately, and propose an evidence-based plan?
2. Communication: Was the advice clear, structured, patient-centered, and easy for a non-medical patient to understand?
3. Guideline alignment: Compare the student's assessment and plan against published guidance from NICE, ESC, AHA, ACC, or other relevant specialty guidelines.

Cite at least one guideline source explicitly in the English verdict and one in the Bengali verdict. Use phrasing like "According to NICE NG125..." or "AHA/ACC guideline recommends..." in English, and equivalent Bengali citations in Bengali.
{lang_note}

Return ONLY valid JSON with this exact structure:
{{
  "score": <0-100 integer>,
  "verdict_en": "<2-3 sentence evaluation in English>",
  "verdict_bn": "<2-3 sentence evaluation in Bengali>",
  "strengths": ["<strength1>", "<strength2>"],
  "improvements": ["<improvement1>", "<improvement2>"],
  "medicine_feedback_en": "<medicine evaluation in English>",
  "medicine_feedback_bn": "<medicine evaluation in Bengali>",
  "missed_critical": ["<any missed critical steps>"]
}}"""

    raw = await generate_text(prompt)
    result = _parse_json_response(raw)
    result.setdefault("source", "gemma")
    return result


async def evaluate_followup(
    patient: dict[str, Any],
    previous_advice: str,
    doctor_report_review: str,
    language: str,
) -> dict[str, Any]:
    prompt = f"""You are evaluating a medical student reviewing a returning patient's test results.

Patient: {patient.get('name_en')}, Age {patient.get('age')}
Original complaint: {patient.get('chief_complaint_en')}
Doctor's previous advice: {previous_advice}
Lab results: {patient.get('lab_results_en')}
Correct interpretation: {patient.get('correct_diagnosis_en')}

Doctor's current assessment of reports: {doctor_report_review}

Return ONLY valid JSON:
{{
  "score": <0-100>,
  "verdict_en": "<evaluation>",
  "verdict_bn": "<বাংলায় মূল্যায়ন>",
  "report_interpretation_en": "<did they read the report correctly?>",
  "report_interpretation_bn": "<রিপোর্ট সঠিকভাবে ব্যাখ্যা করেছেন কিনা>",
  "recommended_action_en": "<next steps>",
  "recommended_action_bn": "<পরবর্তী পদক্ষেপ>",
  "improvements": ["<areas to improve>"]
}}"""

    raw = await generate_text(prompt)
    result = _parse_json_response(raw)
    result.setdefault("source", "gemma")
    return result


def _parse_json_response(raw: str) -> dict[str, Any]:
    text = raw.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
        text = text.replace("```json", "").replace("```", "").strip()

    try:
        start = text.index("{")
        end = text.rindex("}") + 1
        return json.loads(text[start:end])
    except (ValueError, json.JSONDecodeError):
        return {
            "score": 65,
            "verdict_en": raw[:500],
            "verdict_bn": "মূল্যায়ন সম্পন্ন হয়েছে।",
            "improvements": ["Review case again with supervisor"],
        }