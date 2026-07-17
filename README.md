# EdgeMed — Medical Student Simulation

A bilingual (Bengali + English) medical training simulation where students consult virtual patients, speak their diagnoses, prescribe medicines, and get AI-powered feedback. After every 3 patients, a returning patient arrives with lab reports and medical images.

## Stack

- **Frontend:** React + Vite
- **Backend:** FastAPI
- **AI:** Google Gemini API (`gemma-4-31b-it`)
- **Speech:** Azure Cognitive Services (optional) with browser fallback

## Quick Start

### 1. Backend setup

```powershell
cd D:\edgemed\backend

# Create virtual environment
python -m venv venv

# Activate (PowerShell)
.\venv\Scripts\Activate.ps1

# Install dependencies
pip install -r requirements.txt

# Create .env from example and add your API key
copy .env.example .env
```

Edit `backend\.env` and set your keys:

```
GEMINI_API_KEY=your_key_here
GEMINI_MODEL=gemma-4-31b-it

# Optional — Azure Speech for better Bengali TTS/STT
AZURE_SPEECH_KEY=your_azure_key
AZURE_SPEECH_REGION=eastus
```

Start the backend:

```powershell
uvicorn main:app --reload --port 8000
```

### 2. Frontend setup

Open a **new terminal**:

```powershell
cd D:\edgemed\frontend

npm install

npm run dev
```

### 3. Open the app

Go to **http://localhost:5173** in Chrome or Edge (needed for voice features).

## How It Works

1. **Start** — Choose English or Bengali, enter the doctor's chamber
2. **Patient arrives** — See name (Naam), age (Boyosh), vitals, history
3. **Listen** — TTS reads the patient's symptoms aloud
4. **Diagnose** — Hold the mic button and speak, or type your advice
5. **Prescribe** — Add medicines to the prescription list
6. **Submit** — AI professor scores your consultation (0–100)
7. **Follow-up** — After 3 patients, an old patient returns with lab results + X-ray/ECG images
8. **Repeat** — Cycle continues with new and returning patients

## Adding Real Report Images

Place your medical report images in:

```
backend/data/report_images/
```

Update `backend/data/patients.json` — set `report_image` to your filename.

Supported formats: `.svg`, `.png`, `.jpg`, `.webp`

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/health` | Check AI and Azure status |
| POST | `/api/session/start` | Start new simulation |
| POST | `/api/consultation/evaluate` | Submit doctor advice for AI grading |
| POST | `/api/speech/tts` | Text-to-speech (Azure or browser) |
| GET | `/reports/{filename}` | Serve medical report images |

## Project Structure

```
edgemed/
├── backend/
│   ├── main.py              # FastAPI app
│   ├── services/
│   │   ├── ai_service.py    # Gemini AI evaluation
│   │   ├── patient_service.py # Session & patient rotation
│   │   └── speech_service.py  # Azure Speech
│   └── data/
│       ├── patients.json    # Patient cases
│       └── report_images/   # X-ray, ECG, lab reports
└── frontend/
    └── src/
        ├── App.jsx          # Main simulation UI
        ├── api.js           # Backend API client
        └── i18n.js          # Bengali/English labels
```

## Azure Speech Setup (Required for Bengali voice)

1. Go to [Azure Portal](https://portal.azure.com) → **Create a resource** → **Speech**
2. Create a Speech resource (use your credits — F0 free tier works)
3. Go to **Keys and Endpoint** → copy **Key 1** and **Region**
4. Edit `backend\.env`:

```
AZURE_SPEECH_KEY=paste_key_1_here
AZURE_SPEECH_REGION=eastus
```

5. Restart the backend
6. On the start screen, **Azure Speech** should show green **Ready**
7. Visit `http://localhost:8000/api/health` — should show `"azure_speech": {"ok": true, ...}`

Bengali uses `bn-BD-NabanitaNeural` (Bangladesh). English uses `en-US-JennyNeural`.
