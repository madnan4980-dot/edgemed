import json
import random
import uuid
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import neurokit2 as nk

from services.ai_service import generate_text, _parse_json_response

ECG_IMAGES_DIR = Path(__file__).resolve().parent.parent / "data" / "ecg_images"
ECG_IMAGES_DIR.mkdir(parents=True, exist_ok=True)

# Only rhythms NeuroKit2's rate-driven simulator can actually reproduce
# realistically. We deliberately avoid claiming pathological morphologies
# (STEMI, AFib, etc.) — see the "important refinement" note in the spec.
RHYTHM_RATE_RANGES = {
    "Sinus Bradycardia": (40, 59),
    "Normal Sinus Rhythm": (60, 100),
    "Sinus Tachycardia": (101, 160),
}
RHYTHM_OPTIONS = list(RHYTHM_RATE_RANGES.keys())

# Simplified quadrant method: axis is determined by the polarity (net
# deflection direction) of Lead I and aVF — the standard bedside technique.
# We render both leads with sign-flipped/scaled versions of the same base
# waveform to represent this. This is a deliberate simplification (whole-
# complex polarity flip, not a true vector projection) but the underlying
# quadrant-reading skill it teaches is real and clinically accurate.
AXIS_QUADRANTS = {
    "Normal Axis":            {"lead_i_sign": 1,  "avf_sign": 1},
    "Left Axis Deviation":    {"lead_i_sign": 1,  "avf_sign": -1},
    "Right Axis Deviation":   {"lead_i_sign": -1, "avf_sign": 1},
    "Indeterminate Axis":     {"lead_i_sign": -1, "avf_sign": -1},
}
AXIS_OPTIONS = list(AXIS_QUADRANTS.keys())
AXIS_WEIGHTS = [0.55, 0.25, 0.15, 0.05]  # Normal is most common clinically

DIFFICULTIES = ["beginner", "intermediate", "advanced"]

GEN_SYSTEM = (
    "You are a medical education content generator producing realistic, fictional "
    "OSCE-style ECG interpretation cases for training medical students in Bangladesh. "
    "You never claim the rendered ECG shows pathological morphology it cannot actually "
    "show (e.g. STEMI, AFib) — the strip is a plain rate-based rhythm simulation. Any "
    "clinical severity lives in the vignette (history, vitals, labs), not in fake ECG shape."
)


def _build_case_prompt(rhythm: str, heart_rate: int, difficulty: str, axis: str) -> str:
    return f"""Generate one realistic educational ECG case for a third-year medical student
practicing an OSCE ECG interpretation station, for a doctor-training simulator in
present-day Bangladesh.

The ECG will be rendered as a simplified 3-lead simulation (Lead II for the
rhythm strip; Lead I and aVF for the quadrant axis method) with:
- Rhythm: {rhythm}
- Heart rate: {heart_rate} bpm
- Frontal plane axis (FIXED by the simulation — do not choose your own): {axis}

Build a clinical vignette CONSISTENT with this rhythm/rate/axis and with
difficulty level "{difficulty}". Give the patient a believable Bangladeshi
occupation, home situation, and social context, written in a plain, slightly
worried voice (not a chart note) for chief_complaint_en/bn and history_en/bn.
Where clinically appropriate you may use a supporting detail consistent with
the axis (e.g. long-standing hypertension can support left axis deviation),
but treat {axis} as a fixed fact, never contradict it.

Populate groundTruth with clinically accurate teaching content: intervals, key
findings a student should notice, likely diagnosis, and immediate management.
keyFindings MAY describe rate, regularity, rate-based rhythm classification, AND
the Lead I / aVF quadrant reading (e.g. "Lead I positive, aVF negative — left
axis deviation") since these are genuinely rendered in this simplified 3-lead
simulation. Do NOT invent findings this simulation cannot show: no voltage
criteria, no ST changes, no T-wave morphology, no chamber enlargement beyond what
the vignette implies. Ground clinical "pathology" primarily in the vignette
(history, vitals), not in fake ECG shape.

Return ONLY valid JSON, no markdown fences, no commentary, in exactly this structure:
{{
  "patient": {{"age": <int 18-85>, "gender_en": "Male|Female", "gender_bn": "পুরুষ or মহিলা"}},
  "chief_complaint_en": "<2-4 sentences, plain worried patient voice>",
  "chief_complaint_bn": "<Bengali version, same length/register>",
  "history_en": "<1-2 sentences: occupation, lifestyle, relevant history>",
  "history_bn": "<Bengali version>",
  "vitals": {{"bp": "<systolic/diastolic>", "spo2": <int 88-100>, "temp": <float 36.0-39.5>}},
  "groundTruth": {{
    "axis": "{axis}",
    "intervals": "<e.g. PR 0.16s, QRS 0.08s, QT 0.38s, appropriate for this rate>",
    "keyFindings_en": ["<finding1, may reference rate/rhythm/axis quadrant>", "<finding2>"],
    "keyFindings_bn": ["<বাংলা finding1>", "<বাংলা finding2>"],
    "diagnosis_en": "<likely diagnosis, consistent with {rhythm} at {heart_rate} bpm>",
    "diagnosis_bn": "<Bengali version>",
    "management_en": "<immediate management>",
    "management_bn": "<Bengali version>"
  }}
}}"""


def _build_eval_prompt(case: dict, answers: dict, language: str) -> str:
    gt = case.get("groundTruth", {})
    lang_note = "Respond in Bengali for the prose fields." if language == "bn" else "Respond in English for the prose fields."
    return f"""You are an experienced cardiology professor running an OSCE ECG station.
This is an EDUCATIONAL SIMULATION — the strip was generated from simulation
parameters (rhythm: {case.get('rhythm')}, heart rate: {gt.get('heartRate')} bpm),
not a real patient. Evaluate the student's interpretation against the ground
truth below. Do not just reveal the answer — teach, the way a good attending
would after a viva.

Ground truth: {json.dumps(gt)}
Clinical vignette: chief complaint = {case.get('chief_complaint_en')}, history = {case.get('history_en')}, vitals = {json.dumps(case.get('vitals', {}))}

Student's answer:
- Heart rate: {answers.get('heartRate')}
- Rhythm: {answers.get('rhythm')}
- Axis: {answers.get('axis')}
- Intervals: {answers.get('intervals')}
- Findings: {answers.get('findings')}
- Likely diagnosis: {answers.get('diagnosis')}
- Immediate management: {answers.get('management')}

{lang_note}

Return ONLY valid JSON, no markdown fences, no commentary, in exactly this structure:
{{
  "overallScore": <0-100 integer>,
  "rateAccuracy": <0-20 integer>,
  "rhythmAccuracy": <0-20 integer>,
  "axisIntervals": <0-20 integer>,
  "clinicalReasoning": <0-20 integer>,
  "management": <0-20 integer>,
  "strengths": ["<strength1>", "<strength2>"],
  "missedFindings": ["<missed1>", "<missed2>"],
  "clinicalExplanation": "<2-4 sentence teaching explanation>",
  "commonMistakes": ["<mistake1>"],
  "differentialDiagnosis": ["<dx1>", "<dx2>"],
  "vivaQuestion": "<one follow-up teaching question, per the spec's 'Now the student is learning' style>"
}}"""


# ---------------- Case generation ----------------

async def generate_ecg_case(language: str = "en") -> dict:
    difficulty = random.choice(DIFFICULTIES)
    rhythm = random.choice(RHYTHM_OPTIONS)
    lo, hi = RHYTHM_RATE_RANGES[rhythm]
    heart_rate = random.randint(lo, hi)
    axis = random.choices(AXIS_OPTIONS, weights=AXIS_WEIGHTS)[0]

    prompt = _build_case_prompt(rhythm, heart_rate, difficulty, axis)
    raw = await generate_text(prompt, system=GEN_SYSTEM, temperature=0.7, max_tokens=900)
    case = _parse_json_response(raw)

    if not isinstance(case, dict) or "groundTruth" not in case:
        case = _fallback_ecg_case(rhythm, heart_rate, difficulty, axis)

    # Clamp/repair server-side so rendered leads and vignette always match
    # the claimed rhythm/axis, even if the model drifts. Axis in particular
    # is server-authoritative — it's determined by how we render Lead I/aVF,
    # not by anything the model decides.
    case["rhythm"] = rhythm
    case["difficulty"] = difficulty
    case.setdefault("groundTruth", {})["heartRate"] = heart_rate
    case["groundTruth"]["rhythm"] = rhythm
    case["groundTruth"]["axis"] = axis
    case.setdefault("vitals", {})["heartRate"] = heart_rate

    case["ecg_image"] = generate_ecg_image(heart_rate, rhythm, axis)
    case["case_id"] = str(uuid.uuid4())
    return case


def _fallback_ecg_case(rhythm: str, heart_rate: int, difficulty: str, axis: str) -> dict:
    """Used only if AI generation fails or returns malformed JSON."""
    return {
        "patient": {"age": 58, "gender_en": "Male", "gender_bn": "পুরুষ"},
        "chief_complaint_en": "Doctor, I've been feeling my heart race and I feel a bit dizzy.",
        "chief_complaint_bn": "ডাক্তার, আমার হৃদস্পন্দন দ্রুত মনে হচ্ছে আর মাথা ঘুরছে।",
        "history_en": "Office worker with a history of hypertension.",
        "history_bn": "উচ্চ রক্তচাপের ইতিহাস সহ অফিস কর্মী।",
        "vitals": {"bp": "138/88", "spo2": 97, "temp": 37.0},
        "difficulty": difficulty,
        "groundTruth": {
            "axis": axis,
            "intervals": "PR 0.16s, QRS 0.08s, QT 0.36s",
            "keyFindings_en": [f"Regular rhythm at {heart_rate} bpm", f"Consistent with {rhythm}", f"Lead I/aVF pattern consistent with {axis.lower()}"],
            "keyFindings_bn": [f"নিয়মিত ছন্দ {heart_rate} bpm", f"{rhythm}-এর সাথে সামঞ্জস্যপূর্ণ"],
            "diagnosis_en": rhythm,
            "diagnosis_bn": rhythm,
            "management_en": "Monitor vitals, treat underlying cause, reassess.",
            "management_bn": "ভাইটালস পর্যবেক্ষণ করুন, মূল কারণের চিকিৎসা করুন, পুনর্মূল্যায়ন করুন।",
        },
    }


# ---------------- Waveform rendering ----------------

def generate_ecg_image(heart_rate: int, rhythm: str, axis: str, noise: float = 0.015) -> str:
    """Render a simplified 3-lead composite: Lead II (rhythm strip) plus
    Lead I and aVF (for the quadrant axis method). Lead I/aVF are generated
    as sign-flipped/scaled copies of an independently-simulated base waveform
    — a deliberate simplification (whole-complex polarity, not a true vector
    projection) that still teaches the real bedside quadrant technique:
    reading net deflection direction in Lead I and aVF to classify axis."""
    duration = 10
    sampling_rate = 500
    small_box = 0.04
    big_box = 0.2

    paper_bg = "#FFFBF5"
    grid_minor = "#F3B9C2"
    grid_major = "#E8828F"
    trace_color = "#161A22"

    quad = AXIS_QUADRANTS.get(axis, AXIS_QUADRANTS["Normal Axis"])

    def make_lead(sign: int, seed: int):
        sig = nk.ecg_simulate(
            duration=duration,
            sampling_rate=sampling_rate,
            heart_rate=heart_rate,
            noise=noise,
            method="ecgsyn",
            random_state=seed,
        )
        return sig * sign

    leads = [
        ("II", make_lead(1, seed=1)),
        ("I", make_lead(quad["lead_i_sign"], seed=2)),
        ("aVF", make_lead(quad["avf_sign"], seed=3)),
    ]
    time = [i / sampling_rate for i in range(len(leads[0][1]))]

    fig_width = max(11, duration * 2.2)
    fig, axes = plt.subplots(3, 1, figsize=(fig_width, 5.2), dpi=150, sharex=True)
    fig.patch.set_facecolor(paper_bg)

    n_small = int(round(duration / small_box))
    n_big = int(round(duration / big_box))

    for ax, (label, sig) in zip(axes, leads):
        ax.set_facecolor(paper_bg)
        ax.set_xlim(0, duration)
        ax.set_xticks([i * small_box for i in range(n_small + 1)], minor=True)
        ax.set_xticks([i * big_box for i in range(n_big + 1)])
        ax.grid(which="minor", color=grid_minor, linewidth=0.4)
        ax.grid(which="major", color=grid_major, linewidth=0.8)
        ax.plot(time, sig, color=trace_color, linewidth=1.3)
        ax.set_yticks([])
        ax.set_xticklabels([])
        for spine in ax.spines.values():
            spine.set_visible(False)
        ax.text(0.01, 0.82, label, transform=ax.transAxes,
                fontsize=13, fontweight="bold", color=trace_color, family="serif")

    axes[-1].text(0.985, -0.15, "25 mm/s   10 mm/mV  (simplified simulation)",
                  transform=axes[-1].transAxes, fontsize=7.5, color="#6B6558",
                  ha="right", family="monospace")

    filename = f"ecg_{uuid.uuid4().hex[:10]}.png"
    fig.tight_layout(pad=0.6)
    fig.savefig(ECG_IMAGES_DIR / filename, facecolor=fig.get_facecolor())
    plt.close(fig)
    return filename


# ---------------- Evaluation ----------------

async def evaluate_ecg_interpretation(case: dict, answers: dict, language: str = "en") -> dict:
    prompt = _build_eval_prompt(case, answers, language)
    raw = await generate_text(prompt, temperature=0.4, max_tokens=1200)
    result = _parse_json_response(raw)

    # _parse_json_response's failure fallback uses score/verdict_en keys (built
    # for the consultation flow) — normalize to this endpoint's shape if hit.
    if "overallScore" not in result:
        result = {
            "overallScore": result.get("score", 60),
            "rateAccuracy": 10, "rhythmAccuracy": 10, "axisIntervals": 10,
            "clinicalReasoning": 10, "management": 10,
            "strengths": [],
            "missedFindings": [],
            "clinicalExplanation": result.get("verdict_en", raw[:500]),
            "commonMistakes": [],
            "differentialDiagnosis": [],
            "vivaQuestion": "",
        }
    return result