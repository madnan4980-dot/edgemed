// I don't have your actual api.js, so the functions below are inferred from how
// they're called in App.jsx (startSession, setLanguage, evaluateConsultation,
// fetchTTS, checkHealth, reportUrl). If your real file differs (different base URL,
// different endpoint paths), just paste fetchRandomCase / evaluateReport / xrayUrl
// at the bottom of your real file instead of replacing the whole thing.

const API_BASE = import.meta.env.VITE_API_BASE || 'http://localhost:8000'

export async function checkHealth() {
  const res = await fetch(`${API_BASE}/api/health`)
  if (!res.ok) throw new Error('Health check failed')
  return res.json()
}

export async function startSession(language) {
  const res = await fetch(`${API_BASE}/api/session/start`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ language }),
  })
  if (!res.ok) throw new Error('Failed to start session')
  return res.json()
}

export async function setLanguage(sessionId, language) {
  const res = await fetch(`${API_BASE}/api/session/${sessionId}/language`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ language }),
  })
  if (!res.ok) throw new Error('Failed to set language')
  return res.json()
}

export async function evaluateConsultation(sessionId, advice, medicines) {
  const res = await fetch(`${API_BASE}/api/consultation/evaluate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ session_id: sessionId, doctor_advice: advice, medicines }),
  })
  if (!res.ok) throw new Error('Failed to evaluate consultation')
  return res.json()
}

export async function orderTest(sessionId, testName) {
  const res = await fetch(`${API_BASE}/api/consultation/order-test`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ session_id: sessionId, test_name: testName }),
  })
  if (!res.ok) throw new Error('Failed to order test')
  return res.json()
}

export async function chatWithPatient(sessionId, message, history) {
  const res = await fetch(`${API_BASE}/api/consultation/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ session_id: sessionId, message, history }),
  })
  if (!res.ok) throw new Error('Failed to chat with patient')
  return res.json()
}

export async function fetchTTS(text, language, gender) {
  const res = await fetch(`${API_BASE}/api/speech/tts`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text, language, gender }),
  })
  if (!res.ok) throw new Error('TTS request failed')
  return res.json()
}

export function reportUrl(imagePath) {
  return `${API_BASE}/api/reports/${encodeURIComponent(imagePath)}`
}

export function xrayUrl(imagePath) {
  return reportUrl(imagePath)
}

// ---------------- Medical Report Lab ----------------

export async function fetchRandomCase() {
  const res = await fetch(`${API_BASE}/api/report-lab/random`)
  if (!res.ok) throw new Error('Failed to fetch case')
  return res.json()
}

export async function evaluateReport({ caseId, findings, diagnosis, differentials, management }) {
  const res = await fetch(`${API_BASE}/api/report-lab/evaluate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      case_id: caseId,
      findings,
      diagnosis,
      differentials,
      management,
    }),
  })
  if (!res.ok) throw new Error('Failed to evaluate report')
  return res.json()
}

export async function fetchPrescriptionCase(lang = 'en') {
  const res = await fetch(`${API_BASE}/api/prescription-lab/new?language=${lang}`)
  if (!res.ok) throw new Error('Failed to fetch case')
  return res.json()
}

export async function evaluatePrescription({ caseId, diagnosis, plan, medicines }) {
  const res = await fetch(`${API_BASE}/api/prescription-lab/evaluate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ case_id: caseId, diagnosis, plan, medicines }),
  })
  if (!res.ok) throw new Error('Failed to evaluate prescription')
  return res.json()
}

// ---------------- Interactive Tutoring ----------------

async function loadImageAsBase64(imagePath) {
  if (!imagePath) {
    throw new Error('No image path provided')
  }

  const imageUrl = imagePath.startsWith('http') ? imagePath : `${API_BASE}/api/reports/${encodeURIComponent(imagePath)}`
  const res = await fetch(imageUrl)
  if (!res.ok) throw new Error('Failed to load X-ray image')

  const blob = await res.blob()
  const arrayBuffer = await blob.arrayBuffer()
  const bytes = new Uint8Array(arrayBuffer)
  let binary = ''
  bytes.forEach((byte) => {
    binary += String.fromCharCode(byte)
  })

  return {
    image_base64: btoa(binary),
    image_mime: blob.type || (imagePath.toLowerCase().endsWith('.png') ? 'image/png' : 'image/jpeg'),
  }
}

export async function startInteractiveTutoring({ caseId, findings, imagePath }) {
  const imageData = await loadImageAsBase64(imagePath)
  const res = await fetch(`${API_BASE}/api/report-lab/interactive/start`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      case_id: caseId,
      student_findings: findings,
      image_base64: imageData.image_base64,
      image_mime: imageData.image_mime,
    }),
  })
  if (!res.ok) throw new Error('Failed to start interactive tutoring')
  return res.json()
}

export async function continueInteractiveTutoring(conversationId, studentResponse, { caseId, imagePath } = {}) {
  const imageData = await loadImageAsBase64(imagePath)
  const res = await fetch(`${API_BASE}/api/report-lab/interactive/continue`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      case_id: caseId,
      conversationId,
      studentResponse,
      image_base64: imageData.image_base64,
      image_mime: imageData.image_mime,
    }),
  })
  if (!res.ok) throw new Error('Failed to continue interactive tutoring')
  return res.json()
}

// ---------------- ECG Simulation Lab ----------------

export async function fetchEcgCase(lang = 'en') {
  const res = await fetch(`${API_BASE}/api/ecg-lab/new?language=${lang}`)
  if (!res.ok) throw new Error('Failed to fetch ECG case')
  return res.json()
}

export async function evaluateEcgInterpretation({ caseId, heartRate, rhythm, axis, intervals, findings, diagnosis, management }) {
  const res = await fetch(`${API_BASE}/api/ecg-lab/evaluate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      case_id: caseId,
      heartRate, rhythm, axis, intervals, findings, diagnosis, management,
    }),
  })
  if (!res.ok) throw new Error('Failed to evaluate ECG interpretation')
  return res.json()
}

export function ecgImageUrl(imagePath) {
  return `${API_BASE}/ecg-images/${imagePath}`
}
