import { useCallback, useEffect, useRef, useState } from 'react'
import {
  startSession,
  setLanguage,
  evaluateConsultation,
  fetchTTS,
  checkHealth,
  reportUrl,
  orderTest,
  chatWithPatient,
} from './api'
import { t } from './i18n'
import docBg from './doc.jpg'
import Avatar from 'avataaars'
import { getPatientAvatarProps, getPatientGenderInfo } from './patientAvatar'
import ReportLab from './ReportLab'
import PrescriptionLab from './PrescriptionLab'
import EcgDemo from './EcgDemo'
import PatientDashboard from './PatientDashboard'

function useSpeech(lang) {
  const recognitionRef = useRef(null)
  const audioRef = useRef(null)
  const synthUtteranceRef = useRef(null)
  const [isPaused, setIsPaused] = useState(false)

  const stopSpeech = useCallback(() => {
    if (audioRef.current) {
      audioRef.current.pause()
      audioRef.current.currentTime = 0
      audioRef.current = null
    }

    if ('speechSynthesis' in window) {
      window.speechSynthesis.cancel()
    }

    synthUtteranceRef.current = null
    setIsPaused(false)
  }, [])

  useEffect(() => {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition
    if (SpeechRecognition) {
      const rec = new SpeechRecognition()
      rec.continuous = true
      rec.interimResults = true
      rec.lang = lang === 'bn' ? 'bn-BD' : 'en-US'
      recognitionRef.current = rec
    }
    return () => {
      if (recognitionRef.current) {
        recognitionRef.current.stop()
      }
      stopSpeech()
    }
  }, [lang, stopSpeech])

  const pauseSpeech = useCallback(() => {
    if (audioRef.current && !audioRef.current.paused) {
      audioRef.current.pause()
      setIsPaused(true)
      return true
    }

    if ('speechSynthesis' in window && synthUtteranceRef.current) {
      window.speechSynthesis.pause()
      setIsPaused(true)
      return true
    }

    return false
  }, [])

  const resumeSpeech = useCallback(() => {
    if (audioRef.current) {
      audioRef.current.play().catch(() => {})
      setIsPaused(false)
      return true
    }

    if ('speechSynthesis' in window && synthUtteranceRef.current) {
      window.speechSynthesis.resume()
      setIsPaused(false)
      return true
    }

    return false
  }, [])

  const speak = useCallback(async (text, language, gender) => {
    stopSpeech()
    const result = await fetchTTS(text, language, gender)

    if (result.source === 'azure' && result.audio_base64) {
      return new Promise((resolve, reject) => {
        const audio = new Audio(`data:${result.mime_type || 'audio/mpeg'};base64,${result.audio_base64}`)
        audioRef.current = audio
        audio.onended = () => {
          audioRef.current = null
          setIsPaused(false)
          resolve({ source: 'azure', voice: result.voice })
        }
        audio.onerror = () => {
          audioRef.current = null
          setIsPaused(false)
          reject(new Error('Failed to play Azure audio'))
        }
        audio.play().catch((error) => {
          audioRef.current = null
          setIsPaused(false)
          reject(error)
        })
      })
    }

    // Bengali almost never works in browser TTS — warn instead of silent fallback
    if (language === 'bn') {
      throw new Error(
        result.error ||
          'Azure Speech is required for Bengali voice. Add AZURE_SPEECH_KEY to backend/.env'
      )
    }

    if ('speechSynthesis' in window) {
      return new Promise((resolve) => {
        window.speechSynthesis.cancel()
        const utter = new SpeechSynthesisUtterance(text)
        utter.lang = 'en-US'
        utter.rate = 0.92
        const voices = window.speechSynthesis.getVoices()
        const { isMale } = getPatientGenderInfo({ gender_en: gender })
        const voiceScore = (voice) => {
          const name = (voice.name || '').toLowerCase()
          if (isMale) {
            if (name.includes('male')) return 3
            if (name.includes('david') || name.includes('mark') || name.includes('james') || name.includes('daniel')) return 2
            return 0
          }
          if (name.includes('female')) return 3
          if (name.includes('zira') || name.includes('susan') || name.includes('jenny') || name.includes('victoria') || name.includes('hazel')) return 2
          return 0
        }
        const enVoice =
          [...voices.filter((v) => v.lang.startsWith('en'))].sort((a, b) => voiceScore(b) - voiceScore(a))[0] ||
          voices.find((v) => v.lang.startsWith('en'))
        if (enVoice) utter.voice = enVoice
        utter.onend = () => {
          synthUtteranceRef.current = null
          setIsPaused(false)
          resolve({ source: 'browser' })
        }
        utter.onerror = () => {
          synthUtteranceRef.current = null
          setIsPaused(false)
          resolve({ source: 'browser' })
        }
        synthUtteranceRef.current = utter
        window.speechSynthesis.speak(utter)
      })
    }

    throw new Error(result.error || 'No TTS available')
  }, [stopSpeech])

  const startListening = useCallback((onResult, onStop) => {
    const rec = recognitionRef.current
    if (!rec) return false

    rec.lang = lang === 'bn' ? 'bn-BD' : 'en-US'
    let finalTranscript = ''

    rec.onresult = (event) => {
      let interim = ''
      for (let i = event.resultIndex; i < event.results.length; i++) {
        const transcript = event.results[i][0].transcript
        if (event.results[i].isFinal) {
          finalTranscript += transcript + ' '
        } else {
          interim += transcript
        }
      }
      onResult(finalTranscript + interim)
    }

    rec.onerror = (event) => {
      console.error('Speech recognition error', event.error)
      onStop?.()
    }

    rec.onend = () => {
      onStop?.()
    }

    try {
      rec.start()
    } catch (error) {
      console.error('Speech recognition start failed', error)
      onStop?.()
      return false
    }

    return true
  }, [lang])

  const stopListening = useCallback(() => {
    if (recognitionRef.current) {
      try {
        recognitionRef.current.stop()
      } catch (error) {
        console.error('Speech recognition stop failed', error)
      }
    }
  }, [])

  return { speak, startListening, stopListening, pauseSpeech, resumeSpeech, stopSpeech, isPaused }
}

function ScoreRing({ score }) {
  const cls = score >= 75 ? 'score-high' : score >= 50 ? 'score-mid' : 'score-low'
  return <div className={`score-ring ${cls}`}>{score}</div>
}

function StartScreen({ onStart, onReportAnalysis, onPrescriptionLab, onEcgDemo, health, loading, lang, onLangChange }) {
  const azureOk = health?.azure_speech?.ok === true
  const azureConfigured = health?.azure_speech?.configured === true

  return (
    <div className="start-screen">
      <div className="start-card">
        <h1>EdgeMed</h1>
        <p>
          {lang === 'bn'
            ? 'রোগী সিমুলেশন চেম্বারে স্বাগতম। রোগীর কথা শুনুন, রোগ নির্ণয় করুন, ওষুধ লিখুন — এআই প্রফেসর আপনার মূল্যায়ন করবেন।'
            : 'Welcome to the patient simulation chamber. Listen to patients, diagnose, prescribe — an AI professor will evaluate your performance.'}
        </p>
        <div className="lang-toggle" style={{ marginBottom: '1.5rem', display: 'inline-flex' }}>
          <button className={lang === 'en' ? 'active' : ''} onClick={() => onLangChange('en')} disabled={loading}>English</button>
          <button className={lang === 'bn' ? 'active' : ''} onClick={() => onLangChange('bn')} disabled={loading}>বাংলা</button>
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.9rem', marginTop: '1.5rem' }}>
          <button className="start-btn" onClick={() => onStart(lang)} disabled={loading}>
            {loading
              ? (lang === 'bn' ? 'রোগী তৈরি হচ্ছে...' : 'Generating patient...')
              : t(lang, 'checkup')}
          </button>
          <button className="start-btn" onClick={onReportAnalysis} disabled={loading}>
            {t(lang, 'reportAnalysis')}
          </button>
          <button className="start-btn" onClick={onEcgDemo} disabled={loading} style={{ gridColumn: '1 / -1' }}>
            {t(lang, 'ecgDemo')}
          </button>
          <button
            className="start-btn"
            onClick={onPrescriptionLab}
            disabled={loading}
            style={{ gridColumn: '1 / -1' }}
          >
            {lang === 'bn' ? 'প্রেসক্রিপশন ল্যাব' : 'Prescription Lab'}
          </button>
        </div>
        {health && (
          <div className="status-dots">
            <span className="status-dot">
              <span className={`dot ${health.ai_configured ? 'on' : 'off'}`} />
              AI {health.ai_configured ? 'Ready' : 'Fallback'}
            </span>
            <span className="status-dot">
              <span className={`dot ${azureOk ? 'on' : 'off'}`} />
              Azure Speech {azureOk ? 'Ready' : azureConfigured ? 'Error' : 'Not configured'}
            </span>
          </div>
        )}
        {health && !azureOk && (
          <p style={{ marginTop: '1rem', fontSize: '0.8rem', color: '#f87171', lineHeight: 1.5 }}>
            {lang === 'bn'
              ? 'বাংলা TTS-এর জন্য backend/.env-এ AZURE_SPEECH_KEY যোগ করুন।'
              : 'Add AZURE_SPEECH_KEY to backend/.env for Bengali voice (required). English can use browser fallback.'}
            {health.azure_speech?.error && (
              <><br /><span style={{ color: '#94a3b8' }}>{health.azure_speech.error}</span></>
            )}
          </p>
        )}
      </div>
    </div>
  )
}

export const PATIENT_CATEGORIES = [
  { id: 'cardiac', icon: '❤️', label_en: 'Chest Pain / Heart', label_bn: 'বুকে ব্যথা / হৃদরোগ' },
  { id: 'respiratory', icon: '🫁', label_en: 'Cough / Breathing', label_bn: 'কাশি / শ্বাসকষ্ট' },
  { id: 'gastrointestinal', icon: '🤢', label_en: 'Stomach Ache', label_bn: 'পেট ব্যথা' },
  { id: 'infectious', icon: '🤒', label_en: 'Fever / Infection', label_bn: 'জ্বর / সংক্রমণ' },
  { id: 'endocrine', icon: '💧', label_en: 'Thirst / Fatigue', label_bn: 'তেষ্টা / দুর্বলতা' },
  { id: 'neurologic', icon: '🧠', label_en: 'Headache / Dizziness', label_bn: 'মাথাব্যথা / মাথা ঘোরা' },
]

function CategorySelect({ lang, loading, onSelect, onBack }) {
  return (
    <div className="start-screen">
      <div className="start-card" style={{ maxWidth: 640 }}>
        <h1>{lang === 'bn' ? 'কেস বেছে নিন' : 'Choose a Case'}</h1>
        <p>
          {lang === 'bn'
            ? 'কোন ধরনের রোগীর সমস্যা নিয়ে অনুশীলন করতে চান?'
            : 'What kind of patient complaint do you want to practice?'}
        </p>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.9rem', marginTop: '1.5rem' }}>
          {PATIENT_CATEGORIES.map((c) => (
            <button
              key={c.id}
              className="start-btn"
              onClick={() => onSelect(c.id)}
              disabled={loading}
              style={{ textAlign: 'left' }}
            >
              <span style={{ marginRight: '0.5rem' }}>{c.icon}</span>
              {lang === 'bn' ? c.label_bn : c.label_en}
            </button>
          ))}
          <button
            className="start-btn"
            onClick={() => onSelect(null)}
            disabled={loading}
            style={{ gridColumn: '1 / -1' }}
          >
            {loading
              ? (lang === 'bn' ? 'রোগী তৈরি হচ্ছে...' : 'Generating patient...')
              : (lang === 'bn' ? '🎲 যেকোনো কেস' : '🎲 Surprise me')}
          </button>
        </div>
        <button className="rx-back-btn" style={{ marginTop: '1.5rem' }} onClick={onBack}>
          {lang === 'bn' ? 'ফিরে যান' : 'Back'}
        </button>
      </div>
    </div>
  )
}

function getScreenFromPath(pathname = window.location.pathname) {
  if (pathname.startsWith('/report-analysis')) return 'report'
  if (pathname.startsWith('/prescription-lab')) return 'prescription'
  if (pathname.startsWith('/ecg-demo')) return 'ecg'
  if (pathname.startsWith('/select-category')) return 'category'
  if (pathname.startsWith('/simulation') || pathname.startsWith('/checkup')) return 'simulation'
  return 'start'
}

function getPathForScreen(screen) {
  switch (screen) {
    case 'report':
      return '/report-analysis'
    case 'prescription':
      return '/prescription-lab'
    case 'ecg':
      return '/ecg-demo'
    case 'category':
      return '/select-category'
    case 'simulation':
      return '/simulation'
    default:
      return '/'
  }
}

function App() {
  const [screen, setScreen] = useState(() => getScreenFromPath(window.location.pathname))
  const [session, setSession] = useState(null)
  const [lang, setLang] = useState('en')
  const [advice, setAdvice] = useState('')
  const [medicines, setMedicines] = useState([])
  const [medicineInput, setMedicineInput] = useState('')
  const [evaluation, setEvaluation] = useState(null)
  const [loading, setLoading] = useState(false)
  const [recording, setRecording] = useState(false)
  const [speaking, setSpeaking] = useState(false)
  const [health, setHealth] = useState(null)
  const [speechError, setSpeechError] = useState(null)
  const [dashboardOpen, setDashboardOpen] = useState(false)
  const [dashboardTab, setDashboardTab] = useState('overview')
  const [testResult, setTestResult] = useState(null)
  const [orderingTest, setOrderingTest] = useState(false)
  const [orderError, setOrderError] = useState(null)
  const [chatMessages, setChatMessages] = useState([])
  const [chatLoading, setChatLoading] = useState(false)
  const [chatError, setChatError] = useState(null)
  const patient = session?.patient
  const { speak, startListening, stopListening, pauseSpeech, resumeSpeech, stopSpeech, isPaused } = useSpeech(lang)
  const patientSpokenRef = useRef(null)
  const startingRef = useRef(false)

  const navigateToScreen = useCallback((nextScreen, options = {}) => {
    if (screen !== nextScreen) {
      stopSpeech()
    }

    const nextPath = getPathForScreen(nextScreen)
    const method = options.replace ? 'replaceState' : 'pushState'

    if (window.location.pathname !== nextPath) {
      window.history[method](null, '', nextPath)
    }

    setScreen(nextScreen)
  }, [screen, stopSpeech])

  useEffect(() => {
    const handlePopState = () => {
      setScreen(getScreenFromPath(window.location.pathname))
    }

    window.addEventListener('popstate', handlePopState)
    return () => window.removeEventListener('popstate', handlePopState)
  }, [])

  useEffect(() => {
    checkHealth().then(setHealth).catch(() => {})
  }, [])

  useEffect(() => {
    return () => {
      stopSpeech()
    }
  }, [stopSpeech])

  useEffect(() => {
    if (!patient) return
    const spokenKey = patient.id ? `${patient.id}:${patient.visit_type || 'initial'}` : null
    if (spokenKey && spokenKey === patientSpokenRef.current) return
    patientSpokenRef.current = spokenKey

    const speakComplaint = async () => {
      if (!patient) return
      setSpeaking(true)
      setSpeechError(null)
      const text = lang === 'bn' ? patient.chief_complaint_bn : patient.chief_complaint_en
      try {
        await speak(text, lang, patient?.gender_en)
      } catch (err) {
        setSpeechError(err.message)
      }
      setSpeaking(false)
    }

    speakComplaint()
  }, [patient, lang, speak])

  const handleStart = async (language, category = null) => {
    if (startingRef.current) return
    startingRef.current = true

    setLang(language)
    setLoading(true)
    patientSpokenRef.current = null
    try {
      const data = await startSession(language, category)
      setSession(data)
      navigateToScreen('simulation')
      setEvaluation(null)
      setAdvice('')
      setMedicines([])
      setDashboardOpen(false)
      setDashboardTab('overview')
      setTestResult(null)
      setChatMessages([])
    } catch (e) {
      console.error('Failed to start session', e)
      alert(`Failed to start session. ${e?.message || 'Check that the backend is running on port 8000.'}`)
    } finally {
      setLoading(false)
      startingRef.current = false
    }
  }

  const handleReportAnalysis = () => {
    navigateToScreen('report')
  }

  const handleEcgDemo = () => {
    navigateToScreen('ecg')
  }

  const handleBackToStart = () => {
    navigateToScreen('start', { replace: true })
  }

  const handleLangSwitch = async (newLang) => {
    setLang(newLang)
    if (session?.session_id) {
      const data = await setLanguage(session.session_id, newLang)
      setSession(data)
    }
  }

  const openDashboard = () => setDashboardOpen(true)
  const closeDashboard = () => setDashboardOpen(false)
  const handleOrderTest = async (testName) => {
    if (!session?.session_id) return
    setOrderingTest(true)
    setOrderError(null)
    try {
      const result = await orderTest(session.session_id, testName)
      setTestResult(result)
    } catch (error) {
      setOrderError(error?.message || 'Failed to order test')
    } finally {
      setOrderingTest(false)
    }
  }

  const handleChat = async (message) => {
    if (!session?.session_id) return
    const nextHistory = [...chatMessages, { role: 'doctor', content: message }]
    setChatLoading(true)
    setChatError(null)
    try {
      const result = await chatWithPatient(session.session_id, message, nextHistory)
      setChatMessages([...nextHistory, { role: 'patient', content: result.reply }])
    } catch (error) {
      setChatError(error?.message || 'Failed to chat with patient')
    } finally {
      setChatLoading(false)
    }
  }

  const isFollowup = patient?.visit_type === 'followup'

  const handleListen = async () => {
    if (!patient || speaking) return
    setSpeaking(true)
    setSpeechError(null)
    const text = lang === 'bn' ? patient.chief_complaint_bn : patient.chief_complaint_en
    try {
      await speak(text, lang, patient?.gender_en)
    } catch (err) {
      setSpeechError(err.message)
    }
    setSpeaking(false)
  }

  const toggleRecording = () => {
    console.log('toggleRecording called, recording=', recording)
    if (recording) {
      setRecording(false)
      stopListening()
      return
    }

    setSpeechError(null)
    setRecording(true)
    const started = startListening(
      (text) => setAdvice(text),
      () => setRecording(false)
    )
    console.log('startListening returned', started)
    if (!started) {
      setRecording(false)
      setSpeechError('Speech recognition unavailable.')
    }
  }

  const addMedicine = () => {
    const trimmed = medicineInput.trim()
    if (trimmed && !medicines.includes(trimmed)) {
      setMedicines([...medicines, trimmed])
    }
    setMedicineInput('')
  }

  const handleSubmit = async () => {
    if (!advice.trim() || !session) return
    setLoading(true)
    setEvaluation(null)
    try {
      const result = await evaluateConsultation(session.session_id, advice, medicines)
      setEvaluation(result.evaluation)
      setSession(result.session)
      setAdvice('')
      setMedicines([])
    } catch (e) {
      alert('Evaluation failed. Check backend and API key.')
    }
    setLoading(false)
  }

  const handleNext = () => {
    setEvaluation(null)
    setAdvice('')
    setMedicines([])
  }

  if (screen === 'start') {
    return (
      <StartScreen
        onStart={() => navigateToScreen('category')}
        onReportAnalysis={handleReportAnalysis}
        onPrescriptionLab={() => navigateToScreen('prescription')}
        onEcgDemo={handleEcgDemo}
        health={health}
        loading={loading}
        lang={lang}
        onLangChange={handleLangSwitch}
      />
    )
  }

  if (screen === 'category') {
    return (
      <CategorySelect
        lang={lang}
        loading={loading}
        onSelect={(category) => handleStart(lang, category)}
        onBack={() => navigateToScreen('start', { replace: true })}
      />
    )
  }
  if (screen === 'report') {
    return <ReportLab lang={lang} onBack={handleBackToStart} />
  }

  if (screen === 'prescription') {
    return <PrescriptionLab lang={lang} onBack={handleBackToStart} />
  }

  if (screen === 'ecg') {
    return <EcgDemo lang={lang} onBack={handleBackToStart} />
  }

  if (loading && !session) {
    return <div className="loading">Loading...</div>
  }

  return (
    <div className="chamber">
      <header className="header">
        <div>
          <h1>{t(lang, 'title')}</h1>
          <p>{t(lang, 'subtitle')}</p>
        </div>
        <div className="header-right">
          <span className="stat-badge">
            {t(lang, 'patientsSeen')}: <strong>{session?.consultation_count ?? 0}</strong>
          </span>
          <div className="lang-toggle">
            <button className={lang === 'en' ? 'active' : ''} onClick={() => handleLangSwitch('en')}>EN</button>
            <button className={lang === 'bn' ? 'active' : ''} onClick={() => handleLangSwitch('bn')}>বাং</button>
          </div>
        </div>
      </header>

      <div className="main-grid">
        {/* Left — Patient Info */}
        <div className="panel">
          <div className="panel-title">{t(lang, 'naam')} / {t(lang, 'boyosh')}</div>
          {patient && (
            <>
              <div className="info-row">
                <span className="info-label">{t(lang, 'naam')}</span>
                <span className="info-value">{lang === 'bn' ? patient.name_bn : patient.name_en}</span>
              </div>
              <div className="info-row">
                <span className="info-label">{t(lang, 'boyosh')}</span>
                <span className="info-value">{patient.age} {lang === 'bn' ? 'বছর' : 'yrs'}</span>
              </div>
              <div className="info-row">
                <span className="info-label">{t(lang, 'gender')}</span>
                <span className="info-value">{lang === 'bn' ? patient.gender_bn : patient.gender_en}</span>
              </div>
              <div className="info-row">
                <span className="info-label">{t(lang, 'blood')}</span>
                <span className="info-value">{patient.blood_group}</span>
              </div>
              <div className="info-row">
                <span className="info-label">{t(lang, 'weight')}</span>
                <span className="info-value">{patient.weight_kg} kg</span>
              </div>

              <div className="panel-title" style={{ marginTop: '1rem' }}>{t(lang, 'vitals')}</div>
              <div className="vitals-grid">
                <div className="vital-card">
                  <div className="val">{patient.vitals.bp}</div>
                  <div className="lbl">{t(lang, 'bp')}</div>
                </div>
                <div className="vital-card">
                  <div className="val">{patient.vitals.pulse}</div>
                  <div className="lbl">{t(lang, 'pulse')}</div>
                </div>
                <div className="vital-card">
                  <div className="val">{patient.vitals.temp}°C</div>
                  <div className="lbl">{t(lang, 'temp')}</div>
                </div>
                <div className="vital-card">
                  <div className="val">{patient.vitals.spo2}%</div>
                  <div className="lbl">{t(lang, 'spo2')}</div>
                </div>
              </div>

              {!isFollowup && (
                <>
                  <div className="panel-title" style={{ marginTop: '1rem' }}>{t(lang, 'history')}</div>
                  <p style={{ fontSize: '0.85rem', lineHeight: 1.5, color: 'var(--text-dim)' }}>
                    {lang === 'bn' ? patient.history_bn : patient.history_en}
                  </p>
                </>
              )}

              {isFollowup && (
                <div className="report-section">
                  <div className="panel-title">{t(lang, 'labResults')}</div>
                  <div className="lab-text">
                    {lang === 'bn' ? patient.lab_results_bn : patient.lab_results_en}
                  </div>
                  {patient.report_image && (
                    <>
                      <div className="panel-title" style={{ marginTop: '0.75rem' }}>{t(lang, 'reportImage')}</div>
                      <img
                        className="report-img"
                        src={reportUrl(patient.report_image)}
                        alt="Medical report"
                      />
                    </>
                  )}
                </div>
              )}

              {session?.history?.length > 0 && (
                <>
                  <div className="panel-title" style={{ marginTop: '1rem' }}>Recent</div>
                  {session.history.map((h, i) => (
                    <div key={i} className="history-item">
                      <strong>{h.patient_name}</strong> — {h.evaluation?.score ?? '?'}%
                    </div>
                  ))}
                </>
              )}
            </>
          )}
        </div>

        {/* Center — Avatar & Patient Speech */}
        <div className="panel stage" style={{ backgroundImage: `linear-gradient(rgba(5, 11, 20, 0.72), rgba(5, 11, 20, 0.72)), url(${docBg})` }}>
          {isFollowup && <div className="followup-banner">{t(lang, 'followup')}</div>}

          <div className="avatar-container">
            {patient && (
              <Avatar
                style={{ width: 180, height: 260 }}
                className="avatar"
                {...getPatientAvatarProps(patient)}
              />
            )}
          </div>

          {patient && (
            <div className="speech-bubble">
              {lang === 'bn' ? patient.chief_complaint_bn : patient.chief_complaint_en}
            </div>
          )}

          <div className="speech-note">
            {speaking
              ? (isPaused
                ? (lang === 'bn' ? 'প্লেব্যাক থেমে আছে।' : 'Playback paused.')
                : (lang === 'bn' ? 'রোগী বলেন...' : 'Patient is speaking...'))
              : (lang === 'bn' ? 'রোগীর সমস্যাগুলো শোনা হচ্ছে।' : 'Patient is describing their issue.')}
          </div>

          {patient && (
            <div style={{ display: 'flex', justifyContent: 'center', gap: '0.75rem', marginTop: '0.75rem' }}>
              <button
                className="mic-btn"
                onClick={isPaused ? resumeSpeech : pauseSpeech}
                disabled={!patient || loading || (!speaking && !isPaused)}
                style={{ padding: '0.6rem 1rem', width: 'auto' }}
              >
                {isPaused ? (lang === 'bn' ? '▶ চালিয়ে যান' : '▶ Resume') : (lang === 'bn' ? '⏸ থামুন' : '⏸ Pause')}
              </button>
              <button
                className="mic-btn"
                onClick={openDashboard}
                disabled={!patient || loading}
                style={{ padding: '0.6rem 1rem', width: 'auto' }}
              >
                {lang === 'bn' ? 'রোগী অন্বেষণ' : 'Explore Patient'}
              </button>
            </div>
          )}

          {speechError && (
            <p style={{ marginTop: '0.75rem', fontSize: '0.8rem', color: '#f87171', textAlign: 'center', maxWidth: 360 }}>
              {speechError}
            </p>
          )}
        </div>

        {dashboardOpen && patient && (
          <PatientDashboard
            patient={patient}
            session={session}
            lang={lang}
            tab={dashboardTab}
            onTabChange={setDashboardTab}
            onClose={closeDashboard}
            onOrderTest={handleOrderTest}
            testResult={testResult}
            orderingTest={orderingTest}
            orderError={orderError}
            chatMessages={chatMessages}
            onChat={handleChat}
            chatLoading={chatLoading}
            chatError={chatError}
          />
        )}

        {/* Right — Doctor Input */}
        <div className="panel doctor-panel">
          <div className="panel-title">{t(lang, 'yourDiagnosis')}</div>

          <textarea
            value={advice}
            onChange={(e) => setAdvice(e.target.value)}
            placeholder={isFollowup ? t(lang, 'reportReview') : t(lang, 'placeholder')}
          />

          <button
            className={`mic-btn ${recording ? 'recording' : ''}`}
            onClick={toggleRecording}
            disabled={speaking || loading}
          >
            🎤 {recording ? t(lang, 'stopSpeak') : t(lang, 'speak')}
          </button>

          {!isFollowup && (
            <>
              <div className="panel-title">{t(lang, 'medicines')}</div>
              <div className="medicine-input-row">
                <input
                  value={medicineInput}
                  onChange={(e) => setMedicineInput(e.target.value)}
                  placeholder={t(lang, 'addMedicine')}
                  onKeyDown={(e) => e.key === 'Enter' && addMedicine()}
                />
                <button onClick={addMedicine}>+</button>
              </div>
              <div className="medicine-tags">
                {medicines.length === 0 && (
                  <span style={{ fontSize: '0.8rem', color: 'var(--text-dim)' }}>{t(lang, 'noMedicine')}</span>
                )}
                {medicines.map((m, i) => (
                  <span key={i} className="medicine-tag">
                    {m}
                    <button onClick={() => setMedicines(medicines.filter((_, j) => j !== i))}>×</button>
                  </span>
                ))}
              </div>
            </>
          )}

          {!evaluation ? (
            <button className="submit-btn" onClick={handleSubmit} disabled={loading || !advice.trim()}>
              {loading ? t(lang, 'evaluating') : t(lang, 'submit')}
            </button>
          ) : (
            <div className="evaluation">
              <ScoreRing score={evaluation.score ?? 0} />
              <p className="eval-text">
                {lang === 'bn' ? evaluation.verdict_bn : evaluation.verdict_en}
              </p>
              {evaluation.strengths?.length > 0 && (
                <>
                  <div className="panel-title">{t(lang, 'strengths')}</div>
                  <ul className="eval-list">
                    {evaluation.strengths.map((s, i) => <li key={i}>{s}</li>)}
                  </ul>
                </>
              )}
              {evaluation.improvements?.length > 0 && (
                <>
                  <div className="panel-title">{t(lang, 'improvements')}</div>
                  <ul className="eval-list">
                    {evaluation.improvements.map((s, i) => <li key={i}>{s}</li>)}
                  </ul>
                </>
              )}
              {(evaluation.medicine_feedback_en || evaluation.medicine_feedback_bn) && (
                <>
                  <div className="panel-title">{t(lang, 'medicineFeedback')}</div>
                  <p className="eval-text" style={{ fontSize: '0.85rem' }}>
                    {lang === 'bn' ? evaluation.medicine_feedback_bn : evaluation.medicine_feedback_en}
                  </p>
                </>
              )}
              <button className="submit-btn" onClick={handleNext} style={{ marginTop: '0.75rem' }}>
                {t(lang, 'nextPatient')} →
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

export default App