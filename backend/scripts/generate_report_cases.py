"""
backend/scripts/generate_report_cases.py

Scans backend/data/report_images/<category>/*.png (or .jpg) and generates
backend/data/report_lab_cases.json with one case entry per image, using a
clinical template for whichever category folder the image is in.

Run from the backend/ folder:

    python scripts/generate_report_cases.py

This OVERWRITES report_lab_cases.json. The generated clinical text is a
reasonable generic template per category (age/vitals/history are randomized
within a realistic range per case) — review a few entries afterward and
adjust wording if you want case-specific detail instead of the shared
per-category template.
"""

import json
import random
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parent.parent
IMAGES_ROOT = BACKEND_ROOT / "data" / "report_images"
OUTPUT_PATH = BACKEND_ROOT / "data" / "report_lab_cases.json"

VALID_EXTENSIONS = {".png", ".jpg", ".jpeg"}

# One clinical template per category folder name.
# {age} gets substituted per-case; everything else is fixed per category.
TEMPLATES = {
    "normal": {
        "difficulty": "beginner",
        "chief_complaint": "Pre-employment health screening, no respiratory complaints",
        "hpi": "Asymptomatic. Presents for a routine pre-employment medical exam. No cough, fever, or shortness of breath.",
        "pmh": [],
        "medications": [],
        "allergies": ["NKDA"],
        "vitals": {"heart_rate": (68, 84), "respiratory_rate": (14, 18), "spo2": (97, 100), "temp": (36.4, 37.0)},
        "physical_exam": "Clear breath sounds bilaterally. No crackles, wheeze, or dullness to percussion.",
        "lab_results": "Within normal limits.",
        "learning_objectives": [
            "Recognize the appearance of a normal chest radiograph",
            "Identify normal lung markings, cardiac silhouette, and costophrenic angles",
        ],
        "expected_findings": ["Clear lung fields", "Normal cardiac silhouette", "Sharp costophrenic angles"],
        "differential_diagnoses": ["No acute cardiopulmonary process"],
        "common_mistakes": ["Over-calling normal vascular markings as pathology"],
        "teaching_points": ["Knowing what's normal is the foundation for spotting what isn't."],
        "followup_questions": ["What specific landmarks did you check to confirm this film is normal?"],
        "ground_truth": {
            "diagnosis": "Normal chest radiograph",
            "severity": "None",
            "key_findings": ["No acute cardiopulmonary abnormality"],
        },
    },
    "pneumonia": {
        "difficulty": "intermediate",
        "chief_complaint": "Cough and fever for several days",
        "hpi": "Progressive productive cough, subjective fevers, and pleuritic chest pain over the past few days. No hemoptysis.",
        "pmh": ["Type 2 diabetes"],
        "medications": ["Metformin"],
        "allergies": ["NKDA"],
        "vitals": {"heart_rate": (95, 115), "respiratory_rate": (20, 26), "spo2": (90, 95), "temp": (38.0, 39.2)},
        "physical_exam": "Decreased breath sounds and crackles over the affected lung field. No wheeze.",
        "lab_results": "WBC elevated, CRP elevated.",
        "learning_objectives": [
            "Identify a lobar or patchy consolidation on a chest film",
            "Correlate radiographic findings with vitals and exam",
        ],
        "expected_findings": ["Focal consolidation", "Air bronchograms within the consolidation"],
        "differential_diagnoses": ["Community-acquired pneumonia", "Pulmonary infarction", "Atelectasis"],
        "common_mistakes": ["Mistaking consolidation for a mass due to rounded margins", "Overlooking air bronchograms"],
        "teaching_points": ["Air bronchograms strongly suggest an alveolar (airspace) process rather than a mass."],
        "followup_questions": ["What score would you use to decide outpatient vs inpatient management here?"],
        "ground_truth": {
            "diagnosis": "Community-acquired pneumonia",
            "severity": "Moderate",
            "key_findings": ["Focal consolidation", "Air bronchograms"],
        },
    },
    "effusion": {
        "difficulty": "intermediate",
        "chief_complaint": "Progressive shortness of breath",
        "hpi": "Gradually worsening breathlessness over 1-2 weeks, worse lying flat, with a sensation of chest fullness.",
        "pmh": ["Congestive heart failure"],
        "medications": ["Furosemide"],
        "allergies": ["NKDA"],
        "vitals": {"heart_rate": (85, 105), "respiratory_rate": (20, 28), "spo2": (88, 94), "temp": (36.6, 37.4)},
        "physical_exam": "Decreased breath sounds and dullness to percussion at the affected base.",
        "lab_results": "BNP elevated.",
        "learning_objectives": [
            "Recognize blunting of the costophrenic angle as pleural effusion",
            "Distinguish effusion from consolidation",
        ],
        "expected_findings": ["Blunted costophrenic angle", "Meniscus sign"],
        "differential_diagnoses": ["Heart failure with pleural effusion", "Parapneumonic effusion", "Malignant effusion"],
        "common_mistakes": ["Missing a small effusion on a supine or under-penetrated film"],
        "teaching_points": ["A meniscus-shaped fluid line is the classic sign of a free-flowing pleural effusion."],
        "followup_questions": ["Would you recommend a lateral decubitus film here, and why?"],
        "ground_truth": {
            "diagnosis": "Pleural effusion",
            "severity": "Moderate",
            "key_findings": ["Blunted costophrenic angle", "Meniscus sign"],
        },
    },
    "atelectasis": {
        "difficulty": "intermediate",
        "chief_complaint": "Post-operative shortness of breath",
        "hpi": "Two days post-abdominal surgery, now with mild breathlessness and shallow breathing due to pain.",
        "pmh": ["Recent abdominal surgery"],
        "medications": ["Post-op analgesia"],
        "allergies": ["NKDA"],
        "vitals": {"heart_rate": (85, 100), "respiratory_rate": (18, 24), "spo2": (91, 96), "temp": (37.0, 38.0)},
        "physical_exam": "Reduced breath sounds at the base, shallow breathing due to incisional pain.",
        "lab_results": "Unremarkable.",
        "learning_objectives": [
            "Recognize volume loss and shift of structures toward the affected side",
            "Understand atelectasis as a common post-operative finding",
        ],
        "expected_findings": ["Volume loss", "Tracheal or mediastinal shift toward the affected side"],
        "differential_diagnoses": ["Post-operative atelectasis", "Mucus plugging", "Early pneumonia"],
        "common_mistakes": ["Confusing atelectasis with consolidation"],
        "teaching_points": ["Atelectasis pulls structures toward it; effusion and mass tend to push away."],
        "followup_questions": ["What bedside measures would you recommend to prevent this post-operatively?"],
        "ground_truth": {
            "diagnosis": "Post-operative atelectasis",
            "severity": "Mild",
            "key_findings": ["Volume loss", "Shift toward affected side"],
        },
    },
    "pneumothorax": {
        "difficulty": "advanced",
        "chief_complaint": "Sudden onset chest pain and breathlessness",
        "hpi": "Sudden sharp, one-sided chest pain with acute shortness of breath, no preceding trauma reported.",
        "pmh": ["Tall, thin build", "Smoker"],
        "medications": [],
        "allergies": ["NKDA"],
        "vitals": {"heart_rate": (100, 125), "respiratory_rate": (22, 30), "spo2": (86, 93), "temp": (36.5, 37.0)},
        "physical_exam": "Decreased breath sounds and hyperresonance on the affected side, reduced chest expansion.",
        "lab_results": "Not contributory.",
        "learning_objectives": [
            "Identify the visceral pleural line and absence of lung markings peripheral to it",
            "Recognize tension physiology as a medical emergency",
        ],
        "expected_findings": ["Visible pleural line", "Absent peripheral lung markings"],
        "differential_diagnoses": ["Spontaneous pneumothorax", "Tension pneumothorax", "Bullous lung disease"],
        "common_mistakes": ["Missing a small apical pneumothorax", "Not checking for tracheal deviation/tension signs"],
        "teaching_points": ["Tracheal deviation away from the affected side plus hypotension signals tension pneumothorax — treat immediately, don't wait for imaging confirmation."],
        "followup_questions": ["What exam findings would make you suspect this has become a tension pneumothorax?"],
        "ground_truth": {
            "diagnosis": "Spontaneous pneumothorax",
            "severity": "Moderate",
            "key_findings": ["Visceral pleural line", "Absent peripheral markings"],
        },
    },
    "cardiomegaly": {
        "difficulty": "beginner",
        "chief_complaint": "Progressive exertional breathlessness and leg swelling",
        "hpi": "Gradual breathlessness on exertion over several months, with ankle swelling in the evenings.",
        "pmh": ["Hypertension", "Prior myocardial infarction"],
        "medications": ["Lisinopril", "Metoprolol"],
        "allergies": ["NKDA"],
        "vitals": {"heart_rate": (78, 96), "respiratory_rate": (16, 22), "spo2": (93, 97), "temp": (36.5, 37.0)},
        "physical_exam": "Bilateral ankle edema, elevated JVP, displaced apex beat.",
        "lab_results": "BNP elevated.",
        "learning_objectives": [
            "Apply the cardiothoracic ratio to assess heart size",
            "Recognize signs of heart failure on a chest film",
        ],
        "expected_findings": ["Cardiothoracic ratio > 50%", "Possible pulmonary vascular congestion"],
        "differential_diagnoses": ["Dilated cardiomyopathy", "Chronic heart failure", "Pericardial effusion"],
        "common_mistakes": ["Calling cardiomegaly on an AP film without accounting for magnification"],
        "teaching_points": ["Cardiothoracic ratio is only reliable on an upright PA film — AP films exaggerate heart size."],
        "followup_questions": ["Why might this ratio be unreliable if the film was taken AP rather than PA?"],
        "ground_truth": {
            "diagnosis": "Cardiomegaly, likely chronic heart failure",
            "severity": "Moderate",
            "key_findings": ["Cardiothoracic ratio > 50%"],
        },
    },
    "mass": {
        "difficulty": "advanced",
        "chief_complaint": "Persistent cough and unintentional weight loss",
        "hpi": "Chronic cough for over two months with unintentional weight loss and reduced appetite. Long smoking history.",
        "pmh": ["30 pack-year smoking history"],
        "medications": [],
        "allergies": ["NKDA"],
        "vitals": {"heart_rate": (80, 98), "respiratory_rate": (16, 22), "spo2": (93, 97), "temp": (36.6, 37.2)},
        "physical_exam": "Possible focal wheeze or decreased breath sounds over the lesion. Cachexia may be present.",
        "lab_results": "Mild anemia possible.",
        "learning_objectives": [
            "Identify a solitary pulmonary mass and its concerning features",
            "Build an appropriate malignancy-focused differential",
        ],
        "expected_findings": ["Well- or ill-defined pulmonary mass > 3cm"],
        "differential_diagnoses": ["Primary lung malignancy", "Metastasis", "Granuloma", "Abscess"],
        "common_mistakes": ["Failing to recommend CT chest for further characterization", "Anchoring on infection without considering malignancy risk factors"],
        "teaching_points": ["Any new mass in a smoker over 40 needs malignancy actively excluded, not assumed benign."],
        "followup_questions": ["What imaging or workup would you order next to characterize this lesion?"],
        "ground_truth": {
            "diagnosis": "Suspicious pulmonary mass, malignancy must be excluded",
            "severity": "Significant",
            "key_findings": ["Solitary pulmonary mass"],
        },
    },
    "nodule": {
        "difficulty": "advanced",
        "chief_complaint": "Incidental finding on routine imaging",
        "hpi": "Asymptomatic. Nodule found incidentally on a chest film obtained for an unrelated reason.",
        "pmh": ["Former smoker"],
        "medications": [],
        "allergies": ["NKDA"],
        "vitals": {"heart_rate": (70, 88), "respiratory_rate": (14, 18), "spo2": (96, 100), "temp": (36.4, 37.0)},
        "physical_exam": "Unremarkable.",
        "lab_results": "Not contributory.",
        "learning_objectives": [
            "Identify a solitary pulmonary nodule < 3cm",
            "Understand risk-stratification for an incidental nodule",
        ],
        "expected_findings": ["Solitary well-defined nodule < 3cm"],
        "differential_diagnoses": ["Benign granuloma", "Early primary lung malignancy", "Hamartoma"],
        "common_mistakes": ["Not comparing with prior imaging to check for growth", "Ignoring an incidental nodule instead of arranging follow-up"],
        "teaching_points": ["Nodule management hinges heavily on size, growth over time, and patient risk factors — always look for prior films to compare."],
        "followup_questions": ["What follow-up interval and imaging would you recommend for this nodule?"],
        "ground_truth": {
            "diagnosis": "Solitary pulmonary nodule, indeterminate",
            "severity": "Low-moderate",
            "key_findings": ["Solitary well-defined nodule"],
        },
    },
}

DEFAULT_TEMPLATE_KEY = "normal"


def random_in(range_tuple, is_float=False):
    lo, hi = range_tuple
    if is_float:
        return round(random.uniform(lo, hi), 1)
    return random.randint(lo, hi)


def build_case(case_id: str, image_rel_path: str, category: str, template: dict) -> dict:
    age = random.randint(22, 78)
    gender = random.choice(["Male", "Female"])
    v = template["vitals"]
    return {
        "case_id": case_id,
        "image": image_rel_path,
        "view_position": "PA",
        "difficulty": template["difficulty"],
        "estimated_time_minutes": random.choice([6, 8, 10]),
        "patient": {"id": f"P-{random.randint(1000, 9999)}", "age": age, "gender": gender},
        "clinical_presentation": {
            "chief_complaint": template["chief_complaint"],
            "history_of_present_illness": template["hpi"],
            "past_medical_history": template["pmh"],
            "medications": template["medications"],
            "allergies": template["allergies"],
        },
        "vitals": {
            "temperature_c": random_in(v["temp"], is_float=True),
            "heart_rate": random_in(v["heart_rate"]),
            "respiratory_rate": random_in(v["respiratory_rate"]),
            "blood_pressure": f"{random.randint(110, 145)}/{random.randint(70, 92)}",
            "spo2": random_in(v["spo2"]),
        },
        "physical_exam": template["physical_exam"],
        "lab_results": template["lab_results"],
        "learning_objectives": template["learning_objectives"],
        "expected_findings": template["expected_findings"],
        "differential_diagnoses": template["differential_diagnoses"],
        "common_mistakes": template["common_mistakes"],
        "teaching_points": template["teaching_points"],
        "followup_questions": template["followup_questions"],
        "ground_truth": template["ground_truth"],
    }


def main():
    if not IMAGES_ROOT.exists():
        raise SystemExit(f"Images folder not found: {IMAGES_ROOT}")

    cases = []
    counter = 1

    for category_dir in sorted(p for p in IMAGES_ROOT.iterdir() if p.is_dir()):
        category = category_dir.name.lower()
        template = TEMPLATES.get(category, TEMPLATES[DEFAULT_TEMPLATE_KEY])

        image_files = sorted(
            f for f in category_dir.iterdir()
            if f.is_file() and f.suffix.lower() in VALID_EXTENSIONS
        )

        for img in image_files:
            case_id = f"case_{counter:03d}"
            image_rel_path = f"{category_dir.name}/{img.name}"
            cases.append(build_case(case_id, image_rel_path, category, template))
            counter += 1

        print(f"{category}: {len(image_files)} images")

    if not cases:
        raise SystemExit("No images found under data/report_images/<category>/. Nothing generated.")

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(cases, f, ensure_ascii=False, indent=2)

    print(f"\nWrote {len(cases)} cases to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()