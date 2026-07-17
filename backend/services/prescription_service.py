# backend/services/prescription_service.py
#
# Mirrors the shape of ai_service.py (generate_patient) but for the
# Prescription Lab: instead of a chief-complaint dialogue case, Gemma
# generates a lab panel (numeric values only) for a fictional patient, and
# we compute flags/reference ranges ourselves rather than trusting the
# model's arithmetic. The ground_truth (diagnosis + correct management) is
# never sent to the frontend — see routers/prescription.py.

import json
import random
import uuid
from typing import Any

from services.ai_service import generate_text

# ---------------------------------------------------------------------------
# Clinical scenario categories (drive the story/diagnosis Gemma writes).
# Each maps to the *report* categories (below) it's allowed to draw tests from.
# ---------------------------------------------------------------------------

PRESCRIPTION_CATEGORIES = [
    "hepatic",
    "renal",
    "hematologic",
    "endocrine",
    "electrolyte",
    "infectious",
    "cardiac",
    "respiratory",
]

# clinical scenario -> which report categories are fair game for that case
SCENARIO_REPORT_CATEGORIES: dict[str, list[str]] = {
    "hepatic": ["liver_function", "biochemistry", "hematology"],
    "renal": ["renal_function", "biochemistry", "hematology"],
    "hematologic": ["hematology", "coagulation", "inflammatory_markers"],
    "endocrine": ["endocrine", "biochemistry", "lipid_profile"],
    "electrolyte": ["biochemistry", "renal_function", "arterial_blood_gas"],
    "infectious": ["hematology", "inflammatory_markers", "biochemistry"],
    "cardiac": ["cardiac_markers", "lipid_profile", "hematology"],
    "respiratory": ["arterial_blood_gas", "inflammatory_markers", "hematology"],
}

# report categories, in the exact order/keys the frontend's LAB_CATEGORIES expects
REPORT_CATEGORY_KEYS = [
    "hematology",
    "biochemistry",
    "liver_function",
    "renal_function",
    "lipid_profile",
    "coagulation",
    "inflammatory_markers",
    "cardiac_markers",
    "endocrine",
    "arterial_blood_gas",
]

# ---------------------------------------------------------------------------
# Test reference table.
# name -> (category, unit, low, high, decimals, name_bn)
# Values Gemma returns are matched against this table; anything not listed
# here is dropped rather than guessed at.
# ---------------------------------------------------------------------------

TEST_INFO: dict[str, dict[str, Any]] = {
    # ---- Hematology (CBC + indices + differential) ----
    "Hemoglobin":        {"category": "hematology", "unit": "g/dL",       "low": 12.0, "high": 16.0, "decimals": 1, "name_bn": "হিমোগ্লোবিন"},
    "Hematocrit":        {"category": "hematology", "unit": "%",         "low": 36,   "high": 46,   "decimals": 0, "name_bn": "হেমাটোক্রিট"},
    "RBC Count":         {"category": "hematology", "unit": "x10^12/L",  "low": 4.2,  "high": 5.4,  "decimals": 2, "name_bn": "আরবিসি কাউন্ট"},
    "MCV":                {"category": "hematology", "unit": "fL",       "low": 80,   "high": 100,  "decimals": 0, "name_bn": "এমসিভি"},
    "MCH":                {"category": "hematology", "unit": "pg",       "low": 27,   "high": 33,   "decimals": 1, "name_bn": "এমসিএইচ"},
    "MCHC":               {"category": "hematology", "unit": "g/dL",     "low": 32,   "high": 36,   "decimals": 1, "name_bn": "এমসিএইচসি"},
    "RDW":                {"category": "hematology", "unit": "%",        "low": 11.5, "high": 14.5, "decimals": 1, "name_bn": "আরডিডব্লিউ"},
    "WBC":                {"category": "hematology", "unit": "x10^9/L",  "low": 4.0,  "high": 11.0, "decimals": 1, "name_bn": "ডব্লিউবিসি"},
    "Neutrophils":        {"category": "hematology", "unit": "%",        "low": 40,   "high": 70,   "decimals": 0, "name_bn": "নিউট্রোফিল"},
    "Lymphocytes":        {"category": "hematology", "unit": "%",        "low": 20,   "high": 40,   "decimals": 0, "name_bn": "লিম্ফোসাইট"},
    "Monocytes":          {"category": "hematology", "unit": "%",        "low": 2,    "high": 8,    "decimals": 0, "name_bn": "মনোসাইট"},
    "Eosinophils":        {"category": "hematology", "unit": "%",        "low": 1,    "high": 4,    "decimals": 0, "name_bn": "ইওসিনোফিল"},
    "Basophils":          {"category": "hematology", "unit": "%",        "low": 0,    "high": 1,    "decimals": 1, "name_bn": "বাসোফিল"},
    "Platelets":          {"category": "hematology", "unit": "x10^9/L",  "low": 150,  "high": 450,  "decimals": 0, "name_bn": "প্লাটিলেট"},
    "MPV":                 {"category": "hematology", "unit": "fL",      "low": 7.5,  "high": 11.5, "decimals": 1, "name_bn": "এমপিভি"},

    # ---- Biochemistry / metabolic panel ----
    "Sodium":              {"category": "biochemistry", "unit": "mmol/L", "low": 135, "high": 145, "decimals": 0, "name_bn": "সোডিয়াম"},
    "Potassium":            {"category": "biochemistry", "unit": "mmol/L", "low": 3.5, "high": 5.1, "decimals": 1, "name_bn": "পটাসিয়াম"},
    "Chloride":              {"category": "biochemistry", "unit": "mmol/L", "low": 98,  "high": 107, "decimals": 0, "name_bn": "ক্লোরাইড"},
    "Carbon Dioxide":         {"category": "biochemistry", "unit": "mmol/L", "low": 22,  "high": 29,  "decimals": 0, "name_bn": "কার্বন ডাই অক্সাইড (CO2)"},
    "Fasting Glucose":         {"category": "biochemistry", "unit": "mg/dL",  "low": 70,  "high": 100, "decimals": 0, "name_bn": "ফাস্টিং গ্লুকোজ"},
    "Calcium":                  {"category": "biochemistry", "unit": "mg/dL",  "low": 8.5, "high": 10.5,"decimals": 1, "name_bn": "ক্যালসিয়াম"},

    # ---- Liver function tests ----
    "ALT":                        {"category": "liver_function", "unit": "U/L",   "low": 7,   "high": 56,  "decimals": 0, "name_bn": "এএলটি"},
    "AST":                         {"category": "liver_function", "unit": "U/L",   "low": 10,  "high": 40,  "decimals": 0, "name_bn": "এএসটি"},
    "Total Bilirubin":              {"category": "liver_function", "unit": "mg/dL", "low": 0.1, "high": 1.2, "decimals": 1, "name_bn": "মোট বিলিরুবিন"},
    "Alkaline Phosphatase":          {"category": "liver_function", "unit": "U/L",  "low": 44,  "high": 147, "decimals": 0, "name_bn": "অ্যালকালাইন ফসফেটেজ"},
    "Albumin":                        {"category": "liver_function", "unit": "g/dL", "low": 3.5, "high": 5.0, "decimals": 1, "name_bn": "অ্যালবুমিন"},

    # ---- Renal function tests ----
    "Creatinine":                       {"category": "renal_function", "unit": "mg/dL",           "low": 0.6, "high": 1.3, "decimals": 1, "name_bn": "ক্রিয়েটিনিন"},
    "Urea":                               {"category": "renal_function", "unit": "mg/dL",           "low": 7,   "high": 20,  "decimals": 0, "name_bn": "ইউরিয়া (BUN)"},
    "BUN/Creatinine Ratio":                {"category": "renal_function", "unit": "",                "low": 10,  "high": 20,  "decimals": 0, "name_bn": "BUN/ক্রিয়েটিনিন অনুপাত"},
    "eGFR":                                  {"category": "renal_function", "unit": "mL/min/1.73m2", "low": 90,  "high": 120, "decimals": 0, "name_bn": "ইজিএফআর"},

    # ---- Lipid profile ----
    "Total Cholesterol":  {"category": "lipid_profile", "unit": "mg/dL", "low": 125, "high": 200, "decimals": 0, "name_bn": "মোট কোলেস্টেরল"},
    "LDL Cholesterol":      {"category": "lipid_profile", "unit": "mg/dL", "low": 0,   "high": 100, "decimals": 0, "name_bn": "এলডিএল কোলেস্টেরল"},
    "HDL Cholesterol":        {"category": "lipid_profile", "unit": "mg/dL", "low": 40,  "high": 60,  "decimals": 0, "name_bn": "এইচডিএল কোলেস্টেরল"},
    "Triglycerides":            {"category": "lipid_profile", "unit": "mg/dL", "low": 0,   "high": 150, "decimals": 0, "name_bn": "ট্রাইগ্লিসারাইড"},

    # ---- Coagulation profile ----
    "PT":            {"category": "coagulation", "unit": "sec",    "low": 11,  "high": 13.5, "decimals": 1, "name_bn": "পিটি"},
    "INR":             {"category": "coagulation", "unit": "",      "low": 0.8, "high": 1.1,  "decimals": 2, "name_bn": "আইএনআর"},
    "aPTT":              {"category": "coagulation", "unit": "sec",  "low": 25,  "high": 35,   "decimals": 0, "name_bn": "এপিটিটি"},
    "Fibrinogen":          {"category": "coagulation", "unit": "mg/dL","low": 200, "high": 400,  "decimals": 0, "name_bn": "ফাইব্রিনোজেন"},
    "D-dimer":               {"category": "coagulation", "unit": "ng/mL FEU", "low": 0, "high": 500, "decimals": 0, "name_bn": "ডি-ডাইমার"},

    # ---- Inflammatory markers ----
    "CRP":     {"category": "inflammatory_markers", "unit": "mg/L",  "low": 0.0, "high": 5.0, "decimals": 1, "name_bn": "সিআরপি"},
    "ESR":       {"category": "inflammatory_markers", "unit": "mm/hr","low": 0,   "high": 20,  "decimals": 0, "name_bn": "ইএসআর"},
    "IL-6":        {"category": "inflammatory_markers", "unit": "pg/mL","low": 0,  "high": 7,   "decimals": 1, "name_bn": "ইন্টারলিউকিন-৬"},

    # ---- Cardiac markers ----
    "hs-Troponin T": {"category": "cardiac_markers", "unit": "ng/L",   "low": 0, "high": 14,  "decimals": 1, "name_bn": "এইচএস-ট্রোপোনিন টি"},
    "NT-proBNP":       {"category": "cardiac_markers", "unit": "pg/mL", "low": 0, "high": 125, "decimals": 0, "name_bn": "এনটি-প্রোবিএনপি"},
    "CK-MB":             {"category": "cardiac_markers", "unit": "ng/mL","low": 0, "high": 5,   "decimals": 1, "name_bn": "সিকে-এমবি"},

    # ---- Endocrine / thyroid panel ----
    "TSH":       {"category": "endocrine", "unit": "mIU/L", "low": 0.4, "high": 4.0, "decimals": 2, "name_bn": "টিএসএইচ"},
    "HbA1c":       {"category": "endocrine", "unit": "%",   "low": 4.0, "high": 5.6, "decimals": 1, "name_bn": "এইচবিএ১সি"},
    "Free T4":       {"category": "endocrine", "unit": "ng/dL", "low": 0.8, "high": 1.8, "decimals": 2, "name_bn": "ফ্রি টি৪"},

    # ---- Arterial blood gas ----
    "pH":              {"category": "arterial_blood_gas", "unit": "",     "low": 7.35, "high": 7.45, "decimals": 2, "name_bn": "পিএইচ"},
    "PaCO2":             {"category": "arterial_blood_gas", "unit": "mmHg","low": 35,   "high": 45,   "decimals": 0, "name_bn": "PaCO2"},
    "PaO2":                {"category": "arterial_blood_gas", "unit": "mmHg","low": 80,   "high": 100,  "decimals": 0, "name_bn": "PaO2"},
    "HCO3":                  {"category": "arterial_blood_gas", "unit": "mmol/L","low": 22, "high": 26,  "decimals": 0, "name_bn": "বাইকার্বোনেট (HCO3-)"},
    "O2 Saturation":           {"category": "arterial_blood_gas", "unit": "%",   "low": 95,  "high": 100, "decimals": 0, "name_bn": "অক্সিজেন স্যাচুরেশন"},
    "Base Excess":               {"category": "arterial_blood_gas", "unit": "mmol/L","low": -2, "high": 2, "decimals": 1, "name_bn": "বেস এক্সেস"},
}

# Backward-compat alias — some older code/tests may still import this name.
REFERENCE_RANGES: dict[str, tuple[str, float, float]] = {
    name: (info["unit"], info["low"], info["high"]) for name, info in TEST_INFO.items()
}

GEN_MAX_TOKENS = 1100


def _round(value: float, decimals: int) -> float | int:
    r = round(value, decimals)
    return int(r) if decimals == 0 else r


def _flag(name: str, value: float) -> str:
    info = TEST_INFO.get(name)
    if not info:
        return "normal"
    lo, hi = info["low"], info["high"]
    span = hi - lo if hi > lo else 1
    if value < lo:
        # more than 25% below the low end of the range -> flag as critical
        return "critical-low" if (lo - value) > span * 0.5 else "low"
    if value > hi:
        return "critical-high" if (value - hi) > span * 0.5 else "high"
    return "normal"


def _build_lab_item(name: str, value: float) -> dict[str, Any] | None:
    info = TEST_INFO.get(name)
    if not info:
        return None
    decimals = info["decimals"]
    val = _round(float(value), decimals)
    lo = _round(info["low"], decimals)
    hi = _round(info["high"], decimals)
    return {
        "name": name,
        "name_bn": info["name_bn"],
        "value": val,
        "unit": info["unit"],
        "reference_range": f"{lo}-{hi}" if not info["unit"] else f"{lo}-{hi}",
        "flag": _flag(name, float(value)),
    }


def _group_lab_items(items: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """Bucket flat lab items into the category keys the frontend's
    LAB_CATEGORIES expects (lab_groups.hematology, .biochemistry, etc.)."""
    groups: dict[str, list[dict[str, Any]]] = {key: [] for key in REPORT_CATEGORY_KEYS}
    for item in items:
        info = TEST_INFO.get(item["name"])
        if not info:
            continue
        groups[info["category"]].append(item)
    return {k: v for k, v in groups.items() if v}


# ---------------------------------------------------------------------------
# Fallback cases — used only if Gemma is unavailable or returns something we
# can't validate. Kept small since this is a safety net, not the primary
# content source.
# ---------------------------------------------------------------------------

FALLBACK_CASES: dict[str, dict[str, Any]] = {
    "hepatic": {
        "patient": {"name_en": "Rafiq Islam", "name_bn": "রফিক ইসলাম", "age": 41, "gender_en": "Male", "gender_bn": "পুরুষ"},
        "chief_complaint_en": "Yellowing of the eyes and skin over the past week, with dark urine and no appetite.",
        "chief_complaint_bn": "গত এক সপ্তাহ ধরে চোখ ও ত্বক হলুদ হয়ে যাচ্ছে, প্রস্রাব গাঢ় রঙের, এবং খাওয়ার রুচি নেই।",
        "history_en": "Rickshaw puller, frequent roadside food, no known alcohol use.",
        "history_bn": "রিকশাচালক, প্রায়ই রাস্তার পাশের খাবার খান, মদ্যপানের ইতিহাস নেই।",
        "vitals": {"bp": "118/76", "pulse": 88, "temp": 37.6, "spo2": 97, "rr": 18},
        "lab_values": {"ALT": 210, "AST": 180, "Total Bilirubin": 4.2, "Alkaline Phosphatase": 160, "Albumin": 3.1, "Platelets": 210, "WBC": 7.2, "Hemoglobin": 13.4},
        "ground_truth": {
            "diagnosis_en": "Acute viral hepatitis (likely Hepatitis A/E)",
            "diagnosis_bn": "একিউট ভাইরাল হেপাটাইটিস (সম্ভবত হেপাটাইটিস এ/ই)",
            "correct_management_en": "Supportive care, hydration, rest, avoid hepatotoxic drugs, monitor LFTs, send viral hepatitis serology.",
            "correct_management_bn": "সহায়ক চিকিৎসা, পর্যাপ্ত তরল, বিশ্রাম, লিভারের ক্ষতিকর ওষুধ পরিহার, এলএফটি মনিটর, ভাইরাল হেপাটাইটিস সেরোলজি।",
            "recommended_medicines": ["Paracetamol (caution, reduced dose)", "Oral rehydration solution"],
            "key_lab_clues": ["Markedly elevated ALT/AST", "Elevated bilirubin"],
        },
    },
    "renal": {
        "patient": {"name_en": "Salma Begum", "name_bn": "সালমা বেগম", "age": 58, "gender_en": "Female", "gender_bn": "মহিলা"},
        "chief_complaint_en": "Reduced urine output and leg swelling for 3 days, feeling increasingly tired.",
        "chief_complaint_bn": "গত তিনদিন ধরে প্রস্রাব কমে গেছে এবং পায়ে ফোলাভাব, ক্রমশ ক্লান্তি বাড়ছে।",
        "history_en": "Known hypertensive, on NSAIDs for knee pain for the past two weeks.",
        "history_bn": "উচ্চ রক্তচাপের রোগী, গত দুই সপ্তাহ ধরে হাঁটুর ব্যথার জন্য এনএসএআইডি খাচ্ছিলেন।",
        "vitals": {"bp": "152/96", "pulse": 92, "temp": 37.0, "spo2": 96, "rr": 20},
        "lab_values": {"Creatinine": 3.1, "Urea": 68, "Potassium": 5.8, "Sodium": 132, "eGFR": 22, "Hemoglobin": 10.2, "BUN/Creatinine Ratio": 22},
        "ground_truth": {
            "diagnosis_en": "Acute kidney injury, likely NSAID-induced on a background of hypertension",
            "diagnosis_bn": "একিউট কিডনি ইনজুরি, সম্ভবত এনএসএআইডি জনিত, উচ্চ রক্তচাপের প্রেক্ষাপটে",
            "correct_management_en": "Stop NSAIDs immediately, monitor potassium closely (hyperkalemia risk), IV fluids as appropriate, urgent renal function follow-up, consider nephrology referral.",
            "correct_management_bn": "এনএসএআইডি সঙ্গে সঙ্গে বন্ধ করুন, পটাসিয়াম নিবিড়ভাবে পর্যবেক্ষণ করুন, প্রয়োজনে শিরায় তরল, জরুরি রেনাল ফাংশন ফলো-আপ, নেফ্রোলজি রেফারেল বিবেচনা করুন।",
            "recommended_medicines": ["Stop NSAIDs", "Antihypertensive adjustment (avoid ACEi/ARB acutely)"],
            "key_lab_clues": ["Elevated creatinine/urea", "Low eGFR", "Elevated potassium"],
        },
    },
    "cardiac": {
        "patient": {"name_en": "Abdul Karim", "name_bn": "আব্দুল করিম", "age": 61, "gender_en": "Male", "gender_bn": "পুরুষ"},
        "chief_complaint_en": "Crushing chest pain radiating to the left arm for the past 2 hours, with sweating and shortness of breath.",
        "chief_complaint_bn": "গত ২ ঘণ্টা ধরে বুকে চাপা ব্যথা, বাম হাতে ছড়িয়ে পড়ছে, সাথে ঘাম ও শ্বাসকষ্ট।",
        "history_en": "Long-standing smoker, known diabetic, father died of a heart attack at age 55.",
        "history_bn": "দীর্ঘদিনের ধূমপায়ী, ডায়াবেটিসের রোগী, বাবা ৫৫ বছর বয়সে হার্ট অ্যাটাকে মারা গিয়েছিলেন।",
        "vitals": {"bp": "148/94", "pulse": 104, "temp": 36.9, "spo2": 94, "rr": 24},
        "lab_values": {"hs-Troponin T": 340, "CK-MB": 12.5, "NT-proBNP": 210, "Total Cholesterol": 260, "LDL Cholesterol": 175, "HDL Cholesterol": 32},
        "ground_truth": {
            "diagnosis_en": "Acute ST-elevation myocardial infarction (STEMI)",
            "diagnosis_bn": "একিউট এসটি-ইলিভেশন মায়োকার্ডিয়াল ইনফার্কশন (STEMI)",
            "correct_management_en": "Immediate ECG, aspirin + P2Y12 inhibitor loading, urgent cardiology referral for reperfusion (PCI), oxygen if hypoxic, monitor troponin trend.",
            "correct_management_bn": "তাৎক্ষণিক ইসিজি, অ্যাসপিরিন + P2Y12 ইনহিবিটর লোডিং, রিপারফিউশনের জন্য জরুরি কার্ডিওলজি রেফারেল (PCI), হাইপক্সিয়া থাকলে অক্সিজেন, ট্রোপোনিন ট্রেন্ড মনিটর।",
            "recommended_medicines": ["Aspirin", "Clopidogrel or Ticagrelor", "Atorvastatin (high intensity)"],
            "key_lab_clues": ["Markedly elevated hs-Troponin T", "Elevated CK-MB", "Dyslipidemia (high LDL, low HDL)"],
        },
    },
    "respiratory": {
        "patient": {"name_en": "Nasrin Akter", "name_bn": "নাসরিন আক্তার", "age": 34, "gender_en": "Female", "gender_bn": "মহিলা"},
        "chief_complaint_en": "Sudden severe shortness of breath and rapid breathing since this morning, feeling lightheaded.",
        "chief_complaint_bn": "আজ সকাল থেকে হঠাৎ তীব্র শ্বাসকষ্ট ও দ্রুত শ্বাস-প্রশ্বাস, মাথা ঘোরাচ্ছে।",
        "history_en": "Known asthmatic since childhood, ran out of inhaler three days ago.",
        "history_bn": "শৈশব থেকে হাঁপানির রোগী, তিন দিন আগে ইনহেলার শেষ হয়ে গেছে।",
        "vitals": {"bp": "126/82", "pulse": 118, "temp": 37.1, "spo2": 89, "rr": 32},
        "lab_values": {"pH": 7.29, "PaCO2": 52, "PaO2": 58, "HCO3": 21, "O2 Saturation": 89, "WBC": 9.8},
        "ground_truth": {
            "diagnosis_en": "Acute severe asthma exacerbation with respiratory acidosis (impending respiratory failure)",
            "diagnosis_bn": "একিউট সিভিয়ার অ্যাজমা এক্সাসারবেশন, শ্বাসতান্ত্রিক অ্যাসিডোসিসসহ (শ্বাসযন্ত্র বিকলতার আশঙ্কা)",
            "correct_management_en": "High-flow oxygen, nebulized bronchodilators, systemic corticosteroids, close monitoring for escalation to non-invasive/invasive ventilation.",
            "correct_management_bn": "হাই-ফ্লো অক্সিজেন, নেবুলাইজড ব্রঙ্কোডাইলেটর, সিস্টেমিক করটিকোস্টেরয়েড, নন-ইনভেসিভ/ইনভেসিভ ভেন্টিলেশনের প্রয়োজন হলে তার জন্য নিবিড় পর্যবেক্ষণ।",
            "recommended_medicines": ["Salbutamol nebulizer", "Ipratropium bromide nebulizer", "IV Hydrocortisone"],
            "key_lab_clues": ["Low pH with elevated PaCO2 (respiratory acidosis)", "Low PaO2/O2 saturation"],
        },
    },
}


def _fallback_case(category: str) -> dict[str, Any]:
    template = FALLBACK_CASES.get(category, FALLBACK_CASES["hepatic"])
    case = json.loads(json.dumps(template))  # deep copy
    lab_items = [
        item for item in (
            _build_lab_item(name, val) for name, val in case.pop("lab_values").items()
        ) if item is not None
    ]
    case["lab_panel"] = lab_items
    case["lab_groups"] = _group_lab_items(lab_items)
    case["case_id"] = f"rx-{uuid.uuid4().hex[:8]}"
    case["difficulty"] = "intermediate"
    return case


def _build_prompt(category: str, age: int, gender: str) -> str:
    report_categories = SCENARIO_REPORT_CATEGORIES.get(category, ["biochemistry", "hematology"])
    pool_lines = []
    for cat_key in report_categories:
        names = [name for name, info in TEST_INFO.items() if info["category"] == cat_key]
        pool_lines.append(f"- {cat_key}: {', '.join(names)}")
    pool_text = "\n".join(pool_lines)

    return f"""Generate one realistic prescription-lab case for a medical student training simulator
in present-day Bangladesh. Category (your reference only, never state it outright): {category}.
Patient age: ~{age}. Gender: {gender}.

Choose 6 to 10 tests ONLY from the following allowed pools (use these exact names). You do not
need every pool, but prefer drawing from at least two of them for a realistic, multi-system picture:
{pool_text}

Give each chosen test a single numeric "value" (no units, no ranges — just a realistic number)
that is internally consistent with a real case of this category, with at least 2-4 tests clearly
abnormal in a way that points toward one specific diagnosis.

Also write a short 2-3 sentence patient chief complaint in plain, worried non-medical language
(not a chart note), a brief 1-2 sentence history (occupation/lifestyle/relevant history), and
vitals.

Return ONLY valid JSON, no markdown fences, no commentary, in exactly this structure:
{{
  "patient": {{"name_en": "<Bangladeshi name>", "name_bn": "<same in Bengali script>", "age": {age}, "gender_en": "{gender}", "gender_bn": "<পুরুষ or মহিলা>"}},
  "chief_complaint_en": "<2-3 sentences, plain worried language>",
  "chief_complaint_bn": "<Bengali version, same length/tone>",
  "history_en": "<1-2 sentences>",
  "history_bn": "<Bengali version>",
  "vitals": {{"bp": "<systolic/diastolic>", "pulse": <int 55-130>, "temp": <float 36.0-40.0>, "spo2": <int 80-100>, "rr": <int 12-34>}},
  "lab_values": {{"<test name>": <number>, "<test name>": <number>}},
  "ground_truth": {{
    "diagnosis_en": "<diagnosis>",
    "diagnosis_bn": "<Bengali version>",
    "correct_management_en": "<2-3 sentence management plan, this is the answer key>",
    "correct_management_bn": "<Bengali version>",
    "recommended_medicines": ["<medicine 1>", "<medicine 2>"],
    "key_lab_clues": ["<which abnormal values are diagnostic and why>"]
  }}
}}"""


async def generate_prescription_case(language: str = "en") -> dict[str, Any]:
    category = random.choice(PRESCRIPTION_CATEGORIES)
    age = random.randint(18, 75)
    gender = random.choice(["Male", "Female"])
    prompt = _build_prompt(category, age, gender)
    system = (
        "You are a medical education content generator producing realistic, fictional lab-based "
        "patient cases for training medical students in Bangladesh to write safe, accurate "
        "prescriptions. Values must be internally consistent and medically plausible."
    )

    raw = await generate_text(prompt, system=system, temperature=0.6, max_tokens=GEN_MAX_TOKENS)
    parsed = _parse_json_response(raw)

    if not _looks_valid(parsed):
        return _fallback_case(category)

    try:
        lab_items = [
            item for item in (
                _build_lab_item(name, float(val))
                for name, val in parsed["lab_values"].items()
            ) if item is not None
        ]
        if len(lab_items) < 3:
            return _fallback_case(category)
        return {
            "case_id": f"rx-{uuid.uuid4().hex[:8]}",
            "difficulty": random.choice(["intermediate", "advanced"]),
            "patient": parsed["patient"],
            "chief_complaint_en": parsed["chief_complaint_en"],
            "chief_complaint_bn": parsed["chief_complaint_bn"],
            "history_en": parsed.get("history_en", ""),
            "history_bn": parsed.get("history_bn", ""),
            "vitals": parsed["vitals"],
            "lab_panel": lab_items,
            "lab_groups": _group_lab_items(lab_items),
            "ground_truth": parsed["ground_truth"],
        }
    except (KeyError, TypeError, ValueError):
        return _fallback_case(category)


def _looks_valid(parsed: dict[str, Any]) -> bool:
    if not isinstance(parsed, dict):
        return False
    required = ("patient", "chief_complaint_en", "vitals", "lab_values", "ground_truth")
    return all(k in parsed for k in required)


async def evaluate_prescription(
    case: dict[str, Any],
    diagnosis_text: str,
    plan_text: str,
    medicines: list[str],
    language: str,
) -> dict[str, Any]:
    ground_truth = case.get("ground_truth", {})
    lang_note = "Respond with both English and Bengali feedback fields regardless of language."

    prompt = f"""You are a senior medical professor grading a medical student's prescription for a
simulated case. You already know the correct answer — do not re-diagnose from scratch, use the
ground truth below to grade and teach.

Case lab panel: {json.dumps(case.get('lab_panel', []))}
Case vitals: {json.dumps(case.get('vitals', {}))}
Patient chief complaint: {case.get('chief_complaint_en')}

GROUND TRUTH (do not reveal verbatim, use to grade):
- Correct diagnosis: {ground_truth.get('diagnosis_en')}
- Correct management: {ground_truth.get('correct_management_en')}
- Recommended medicines: {', '.join(ground_truth.get('recommended_medicines', []))}
- Key diagnostic lab clues: {ground_truth.get('key_lab_clues')}

{lang_note}

Student's diagnosis: {diagnosis_text}
Student's prescription / management plan: {plan_text}
Student's prescribed medicines: {', '.join(medicines) if medicines else '(none specified)'}

Grade on 5 axes, each out of 20 (sum = overall out of 100):
- labInterpretation: did they correctly read and connect the abnormal lab values?
- diagnosisAccuracy: is their diagnosis correct or clinically defensible?
- medicationSafety: are the prescribed medicines appropriate, safe, and free of dangerous
  omissions (e.g. missing a drug that must be stopped, wrong drug for renal/hepatic impairment)?
- management: is the overall plan (investigations, monitoring, referral) appropriate?
- communication: is the write-up clear and clinically structured?

Point out what they missed without simply handing them the diagnosis where possible — nudge
them toward it. End with ONE viva-style follow-up question.

Return ONLY valid JSON with this exact structure:
{{
  "overallScore": <int 0-100>,
  "labInterpretation": <int 0-20>,
  "diagnosisAccuracy": <int 0-20>,
  "medicationSafety": <int 0-20>,
  "management": <int 0-20>,
  "communication": <int 0-20>,
  "strengths": ["..."],
  "missedFindings": ["..."],
  "safetyFlags": ["..."],
  "clinicalPearls": ["..."],
  "nextQuestion": "..."
}}"""

    raw = await generate_text(prompt, temperature=0.4, max_tokens=900)
    parsed = _parse_json_response(raw)
    return _coerce_defaults(parsed)


def _parse_json_response(raw: str) -> dict[str, Any]:
    # Same permissive extraction style used in ai_service.py / routers/report.py.
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
    defaults = {
        "overallScore": 60,
        "labInterpretation": 12,
        "diagnosisAccuracy": 12,
        "medicationSafety": 12,
        "management": 12,
        "communication": 12,
        "strengths": [],
        "missedFindings": [],
        "safetyFlags": [],
        "clinicalPearls": [],
        "nextQuestion": "Which single lab value most changed your management plan, and why?",
    }
    defaults.update(parsed)
    return defaults