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
GEN_RETRIES = 0  # avoid extra retries to keep latency low


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


import re

_CHART_NOTE_PATTERN = re.compile(r"\bfor (the past |several )?\d+\s*(day|week)s?\b.*\bassociated with\b")


def _sounds_clinical_or_too_short(text: str) -> bool:
    if not text or len(text.split()) < MIN_COMPLAINT_WORDS:
        return True
    lowered = text.lower()
    if any(term in lowered for term in FORBIDDEN_CLINICAL_TERMS):
        return True
    return bool(_CHART_NOTE_PATTERN.search(lowered))


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


async def generate_patient(language: str = "en") -> dict[str, Any]:
    category = random.choice(ILLNESS_CATEGORIES)
    age = random.randint(3, 82)
    gender = random.choice(["Male", "Female"])
    prompt = _build_patient_prompt(category, age, gender)
    system = (
        "You are a medical education content generator producing realistic, fictional patient "
        "cases for training doctors in Bangladesh. You are especially careful to write patient "
        "dialogue the way real anxious patients talk — never like a clinical chart note. Short, "
        "clinical-sounding complaints are considered failures."
    )

    for attempt in range(GEN_RETRIES + 1):
        temperature = GEN_TEMPERATURE if attempt == 0 else GEN_TEMPERATURE_RETRY
        raw = await generate_text(
            prompt,
            system=system,
            temperature=temperature,
            max_tokens=GEN_MAX_TOKENS,
        )
        patient = _parse_generated_patient(raw)
        if patient is not None:
            patient = _validate_and_fill_patient(patient, age, gender)
            if patient is not None:
                patient["id"] = f"ai-{uuid.uuid4().hex[:8]}"
                patient.setdefault("report_image", "")
                return patient

    return _fallback_patient(category, age, gender)


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
    return _parse_json_response(raw)


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
    return _parse_json_response(raw)


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