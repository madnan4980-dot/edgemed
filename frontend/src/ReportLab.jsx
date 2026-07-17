import { useCallback, useEffect, useRef, useState } from 'react'
import { fetchRandomCase, evaluateReport, startInteractiveTutoring, continueInteractiveTutoring, reportUrl } from './api'

const STR = {
  en: {
    backToStart: 'Back',
    title: 'Medical Report Lab',
    subtitle: 'Interpret the chest X-ray. Gemma evaluates your reasoning .',
    loadingCase: 'Loading case...',
    caseInfo: 'Case Information',
    age: 'Age', gender: 'Gender', chiefComplaint: 'Chief Complaint',
    hpi: 'History of Present Illness', pmh: 'Past Medical History',
    medications: 'Medications', allergies: 'Allergies',
    vitals: 'Vitals', physicalExam: 'Physical Examination', labResults: 'Lab Results',
    learningObjectives: 'Learning Objectives',
    difficulty: 'Difficulty', estTime: 'Est. Time', min: 'min',
    xray: 'Chest X-ray', zoomIn: '+', zoomOut: '–', resetZoom: 'Reset',
    findings: 'Observed Findings', findingsPh: 'Describe what you see on the film...',
    diagnosis: 'Likely Diagnosis', diagnosisPh: 'Your primary diagnosis',
    differentials: 'Differential Diagnoses', addDifferential: 'Add a differential + Enter',
    noDifferential: 'No differentials added yet',
    management: 'Recommended Management', managementPh: 'Your management plan...',
    submit: 'Submit for Evaluation', evaluating: 'Evaluating...',
    overallScore: 'Overall Score',
    breakdown: 'Score Breakdown',
    imageInterpretation: 'Image Interpretation', diagnosisScore: 'Diagnosis',
    managementScore: 'Management', reasoning: 'Reasoning', communication: 'Communication',
    strengths: 'Strengths', missed: 'Missed Findings', pearls: 'Clinical Pearls',
    nextQuestion: 'Follow-up Question', nextCase: 'Next Case →',
    error: 'Could not load case. Check that the backend is running.',
  },
  bn: {
    backToStart: 'ফিরে যান',
    title: 'মেডিকেল রিপোর্ট ল্যাব',
    subtitle: 'বুকের এক্স-রে নিজে বিশ্লেষণ করুন। জেমা আপনার যুক্তি মূল্যায়ন করবে — ছবি নয়।',
    loadingCase: 'কেস লোড হচ্ছে...',
    caseInfo: 'কেসের তথ্য',
    age: 'বয়স', gender: 'লিঙ্গ', chiefComplaint: 'প্রধান সমস্যা',
    hpi: 'বর্তমান অসুস্থতার ইতিহাস', pmh: 'পূর্ববর্তী চিকিৎসা ইতিহাস',
    medications: 'ওষুধ', allergies: 'এলার্জি',
    vitals: 'ভাইটালস', physicalExam: 'শারীরিক পরীক্ষা', labResults: 'ল্যাব ফলাফল',
    learningObjectives: 'শেখার উদ্দেশ্য',
    difficulty: 'কঠিনতা', estTime: 'আনুমানিক সময়', min: 'মিনিট',
    xray: 'বুকের এক্স-রে', zoomIn: '+', zoomOut: '–', resetZoom: 'রিসেট',
    findings: 'পর্যবেক্ষিত ফলাফল', findingsPh: 'ফিল্মে যা দেখছেন তা বর্ণনা করুন...',
    diagnosis: 'সম্ভাব্য রোগ নির্ণয়', diagnosisPh: 'আপনার প্রধান রোগ নির্ণয়',
    differentials: 'ডিফারেনশিয়াল ডায়াগনসিস', addDifferential: 'ডিফারেনশিয়াল যোগ করুন + Enter',
    noDifferential: 'এখনো কোনো ডিফারেনশিয়াল যোগ করা হয়নি',
    management: 'সুপারিশকৃত ব্যবস্থাপনা', managementPh: 'আপনার ব্যবস্থাপনা পরিকল্পনা...',
    submit: 'মূল্যায়নের জন্য জমা দিন', evaluating: 'মূল্যায়ন হচ্ছে...',
    overallScore: 'সামগ্রিক স্কোর',
    breakdown: 'স্কোর বিভাজন',
    imageInterpretation: 'ছবি ব্যাখ্যা', diagnosisScore: 'রোগ নির্ণয়',
    managementScore: 'ব্যবস্থাপনা', reasoning: 'যুক্তি', communication: 'যোগাযোগ',
    strengths: 'শক্তিশালী দিক', missed: 'বাদ পড়া ফলাফল', pearls: 'ক্লিনিক্যাল টিপস',
    nextQuestion: 'পরবর্তী প্রশ্ন', nextCase: 'পরবর্তী কেস →',
    error: 'কেস লোড করা যায়নি। ব্যাকএন্ড চালু আছে কিনা দেখুন।',
  },
}

function ScoreBar({ label, value, max }) {
  const pct = Math.max(0, Math.min(100, (value / max) * 100))
  return (
    <div className="score-bar-row">
      <div className="score-bar-label">
        <span>{label}</span>
        <span>{value}/{max}</span>
      </div>
      <div className="score-bar-track">
        <div className="score-bar-fill" style={{ width: `${pct}%` }} />
      </div>
    </div>
  )
}

function XrayViewer({ src, alt }) {
  const [zoom, setZoom] = useState(1)
  const [pos, setPos] = useState({ x: 0, y: 0 })
  const dragRef = useRef(null)

  const onWheel = (e) => {
    e.preventDefault()
    setZoom((z) => Math.min(4, Math.max(1, z - e.deltaY * 0.0015)))
  }

  const onMouseDown = (e) => {
    dragRef.current = { startX: e.clientX, startY: e.clientY, origin: { ...pos } }
  }
  const onMouseMove = (e) => {
    if (!dragRef.current || zoom === 1) return
    const dx = e.clientX - dragRef.current.startX
    const dy = e.clientY - dragRef.current.startY
    setPos({ x: dragRef.current.origin.x + dx, y: dragRef.current.origin.y + dy })
  }
  const onMouseUp = () => { dragRef.current = null }

  return (
    <div className="xray-viewer">
      <div
        className="xray-viewport"
        onWheel={onWheel}
        onMouseDown={onMouseDown}
        onMouseMove={onMouseMove}
        onMouseUp={onMouseUp}
        onMouseLeave={onMouseUp}
      >
        <img
          className="xray-image"
          src={src}
          alt={alt}
          draggable={false}
          style={{ transform: `translate(${pos.x}px, ${pos.y}px) scale(${zoom})` }}
        />
      </div>
      <div className="xray-controls">
        <button onClick={() => setZoom((z) => Math.min(4, z + 0.25))}>+</button>
        <button onClick={() => setZoom((z) => Math.max(1, z - 0.25))}>–</button>
        <button onClick={() => { setZoom(1); setPos({ x: 0, y: 0 }) }}>Reset</button>
      </div>
    </div>
  )
}

export default function ReportLab({ lang = 'en', onBack }) {
  const s = STR[lang] || STR.en
  const [caseData, setCaseData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState(null)

  const [findings, setFindings] = useState('')
  const [diagnosis, setDiagnosis] = useState('')
  const [differentials, setDifferentials] = useState([])
  const [diffInput, setDiffInput] = useState('')
  const [management, setManagement] = useState('')

  const [evaluation, setEvaluation] = useState(null)
  const [submitting, setSubmitting] = useState(false)
  
  // Interactive tutoring state
  const [conversationId, setConversationId] = useState(null)
  const [conversation, setConversation] = useState([])
  const [studentResponse, setStudentResponse] = useState('')
  const [tutorResponse, setTutorResponse] = useState('')
  const [isAnswering, setIsAnswering] = useState(false)

  const loadCase = useCallback(async () => {
    setLoading(true)
    setLoadError(null)
    setEvaluation(null)
    setFindings('')
    setDiagnosis('')
    setDifferentials([])
    setManagement('')
    try {
      const data = await fetchRandomCase()
      setCaseData(data)
    } catch (e) {
      setLoadError(s.error)
    }
    setLoading(false)
  }, [s.error])

  useEffect(() => { loadCase() }, [loadCase])

  const addDifferential = () => {
    const trimmed = diffInput.trim()
    if (trimmed && !differentials.includes(trimmed)) {
      setDifferentials([...differentials, trimmed])
    }
    setDiffInput('')
  }

  const handleSubmit = async () => {
    if (!caseData || !findings.trim() || !diagnosis.trim()) return
    setSubmitting(true)
    try {
      const result = await startInteractiveTutoring({
        caseId: caseData.case_id,
        findings,
        diagnosis,
        differentials,
        management,
        imagePath: caseData.image,
      })
      setConversationId(result.conversation_id)
      setTutorResponse(result.response || result.next_question || '')
      setConversation([
        { role: 'student', content: findings },
        { role: 'tutor', content: result.response || result.next_question || '' },
      ])
      setEvaluation({ isInteractive: true })
    } catch (e) {
      alert('Tutoring session failed. Check backend and API key.')
    }
    setSubmitting(false)
  }

  const handleContinueConversation = async () => {
    if (!conversationId || !studentResponse.trim()) return
    setIsAnswering(true)
    try {
      const result = await continueInteractiveTutoring(conversationId, studentResponse)
      setTutorResponse(result.response || result.next_question || '')
      setConversation((prev) => [
        ...prev,
        { role: 'student', content: studentResponse },
        { role: 'tutor', content: result.response || result.next_question || '' },
      ])
      setStudentResponse('')
    } catch (e) {
      alert('Failed to continue conversation. Check backend.')
    }
    setIsAnswering(false)
  }

  return (
    <div className="chamber">
      <header className="header">
        <div>
          <h1>{s.title}</h1>
          <p>{s.subtitle}</p>
        </div>
        <div className="header-right">
          <button className="submit-btn" style={{ width: 'auto' }} onClick={onBack}>
            {s.backToStart}
          </button>
        </div>
      </header>

      {loading && <div className="loading">{s.loadingCase}</div>}
      {!loading && loadError && (
        <div className="loading" style={{ color: 'var(--danger)' }}>{loadError}</div>
      )}

      {!loading && !loadError && caseData && (
        <div className="main-grid report-lab-grid">
          {/* Left — Case info */}
          <div className="panel">
            <div className="panel-title">{s.caseInfo}</div>
            <div className="info-row">
              <span className="info-label">{s.age}</span>
              <span className="info-value">{caseData.patient?.age}</span>
            </div>
            <div className="info-row">
              <span className="info-label">{s.gender}</span>
              <span className="info-value">{caseData.patient?.gender}</span>
            </div>
            <div className="info-row">
              <span className="info-label">{s.difficulty}</span>
              <span className="info-value">{caseData.difficulty}</span>
            </div>
            <div className="info-row">
              <span className="info-label">{s.estTime}</span>
              <span className="info-value">{caseData.estimated_time_minutes} {s.min}</span>
            </div>

            <div className="panel-title" style={{ marginTop: '1rem' }}>{s.chiefComplaint}</div>
            <p className="lab-text">{caseData.clinical_presentation?.chief_complaint}</p>

            <div className="panel-title" style={{ marginTop: '1rem' }}>{s.hpi}</div>
            <p className="lab-text">{caseData.clinical_presentation?.history_of_present_illness}</p>

            {caseData.clinical_presentation?.past_medical_history?.length > 0 && (
              <>
                <div className="panel-title" style={{ marginTop: '1rem' }}>{s.pmh}</div>
                <ul className="eval-list">
                  {caseData.clinical_presentation.past_medical_history.map((x, i) => <li key={i}>{x}</li>)}
                </ul>
              </>
            )}

            <div className="panel-title" style={{ marginTop: '1rem' }}>{s.vitals}</div>
            <div className="vitals-grid">
              <div className="vital-card"><div className="val">{caseData.vitals?.temperature_c}°C</div><div className="lbl">Temp</div></div>
              <div className="vital-card"><div className="val">{caseData.vitals?.heart_rate}</div><div className="lbl">HR</div></div>
              <div className="vital-card"><div className="val">{caseData.vitals?.respiratory_rate}</div><div className="lbl">RR</div></div>
              <div className="vital-card"><div className="val">{caseData.vitals?.spo2}%</div><div className="lbl">SpO2</div></div>
            </div>

            {caseData.physical_exam && (
              <>
                <div className="panel-title" style={{ marginTop: '1rem' }}>{s.physicalExam}</div>
                <p className="lab-text">{caseData.physical_exam}</p>
              </>
            )}

            {caseData.lab_results && (
              <>
                <div className="panel-title" style={{ marginTop: '1rem' }}>{s.labResults}</div>
                <p className="lab-text">{caseData.lab_results}</p>
              </>
            )}

            {caseData.learning_objectives?.length > 0 && (
              <>
                <div className="panel-title" style={{ marginTop: '1rem' }}>{s.learningObjectives}</div>
                <ul className="eval-list">
                  {caseData.learning_objectives.map((x, i) => <li key={i}>{x}</li>)}
                </ul>
              </>
            )}
          </div>

          {/* Center — X-ray viewer */}
          <div className="panel stage report-lab-stage">
            <div className="panel-title">{s.xray}</div>
            <XrayViewer src={reportUrl(caseData.image)} alt={s.xray} />
          </div>

          {/* Right — Student input / feedback */}
          <div className="panel doctor-panel">
            {!evaluation ? (
              <>
                <div className="panel-title">{s.findings}</div>
                <textarea value={findings} onChange={(e) => setFindings(e.target.value)} placeholder={s.findingsPh} />

                <div className="panel-title">{s.diagnosis}</div>
                <input
                  className="text-input"
                  value={diagnosis}
                  onChange={(e) => setDiagnosis(e.target.value)}
                  placeholder={s.diagnosisPh}
                />

                <div className="panel-title">{s.differentials}</div>
                <div className="medicine-input-row">
                  <input
                    value={diffInput}
                    onChange={(e) => setDiffInput(e.target.value)}
                    placeholder={s.addDifferential}
                    onKeyDown={(e) => e.key === 'Enter' && addDifferential()}
                  />
                  <button onClick={addDifferential}>+</button>
                </div>
                <div className="medicine-tags">
                  {differentials.length === 0 && (
                    <span style={{ fontSize: '0.8rem', color: 'var(--text-dim)' }}>{s.noDifferential}</span>
                  )}
                  {differentials.map((d, i) => (
                    <span key={i} className="medicine-tag">
                      {d}
                      <button onClick={() => setDifferentials(differentials.filter((_, j) => j !== i))}>×</button>
                    </span>
                  ))}
                </div>

                <div className="panel-title">{s.management}</div>
                <textarea value={management} onChange={(e) => setManagement(e.target.value)} placeholder={s.managementPh} />

                <button
                  className="submit-btn"
                  onClick={handleSubmit}
                  disabled={submitting || !findings.trim() || !diagnosis.trim()}
                >
                  {submitting ? s.evaluating : s.submit}
                </button>
              </>
            ) : evaluation?.isInteractive ? (
              <div className="evaluation">
                <div className="panel-title">{s.learningObjectives}</div>
                
                {/* Conversation history */}
                <div className="conversation-history" style={{ maxHeight: '300px', overflowY: 'auto', marginBottom: '1rem', padding: '0.75rem', backgroundColor: 'var(--bg-secondary)', borderRadius: '4px' }}>
                  {conversation.map((msg, i) => (
                    <div key={i} style={{ marginBottom: '0.75rem' }}>
                      <div style={{ fontWeight: 'bold', fontSize: '0.85rem', color: msg.role === 'student' ? 'var(--accent)' : 'var(--text)' }}>
                        {msg.role === 'student' ? 'You' : 'Tutor'}:
                      </div>
                      <p style={{ margin: '0.25rem 0 0 0', fontSize: '0.9rem', lineHeight: '1.4' }}>{msg.content}</p>
                    </div>
                  ))}
                </div>

                {/* Follow-up question input */}
                <div className="panel-title" style={{ marginTop: '0.5rem' }}>{s.nextQuestion}</div>
                <textarea
                  value={studentResponse}
                  onChange={(e) => setStudentResponse(e.target.value)}
                  placeholder="Answer the question..."
                  style={{ marginBottom: '0.75rem' }}
                />

                <div style={{ display: 'flex', gap: '0.5rem' }}>
                  <button
                    className="submit-btn"
                    onClick={handleContinueConversation}
                    disabled={isAnswering || !studentResponse.trim()}
                    style={{ flex: 1 }}
                  >
                    {isAnswering ? 'Responding...' : 'Answer'}
                  </button>
                  <button className="submit-btn" onClick={loadCase} style={{ flex: 1 }}>
                    {s.nextCase}
                  </button>
                </div>
              </div>
            ) : (
              <div className="evaluation">
                <div className="score-ring score-high" style={{ borderColor: undefined }}>
                  {evaluation.overallScore}
                </div>
                <div className="panel-title" style={{ textAlign: 'center' }}>{s.overallScore}</div>

                <div className="panel-title" style={{ marginTop: '1rem' }}>{s.breakdown}</div>
                <ScoreBar label={s.imageInterpretation} value={evaluation.imageInterpretation} max={20} />
                <ScoreBar label={s.diagnosisScore} value={evaluation.diagnosis} max={20} />
                <ScoreBar label={s.managementScore} value={evaluation.management} max={20} />
                <ScoreBar label={s.reasoning} value={evaluation.reasoning} max={20} />
                <ScoreBar label={s.communication} value={evaluation.communication} max={20} />

                {evaluation.strengths?.length > 0 && (
                  <>
                    <div className="panel-title" style={{ marginTop: '1rem' }}>{s.strengths}</div>
                    <ul className="eval-list">{evaluation.strengths.map((x, i) => <li key={i}>{x}</li>)}</ul>
                  </>
                )}
                {evaluation.missedFindings?.length > 0 && (
                  <>
                    <div className="panel-title" style={{ marginTop: '1rem' }}>{s.missed}</div>
                    <ul className="eval-list">{evaluation.missedFindings.map((x, i) => <li key={i}>{x}</li>)}</ul>
                  </>
                )}
                {evaluation.clinicalPearls?.length > 0 && (
                  <>
                    <div className="panel-title" style={{ marginTop: '1rem' }}>{s.pearls}</div>
                    <ul className="eval-list">{evaluation.clinicalPearls.map((x, i) => <li key={i}>{x}</li>)}</ul>
                  </>
                )}
                {evaluation.nextQuestion && (
                  <>
                    <div className="panel-title" style={{ marginTop: '1rem' }}>{s.nextQuestion}</div>
                    <p className="eval-text">{evaluation.nextQuestion}</p>
                  </>
                )}

                <button className="submit-btn" style={{ marginTop: '0.75rem' }} onClick={loadCase}>
                  {s.nextCase}
                </button>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}