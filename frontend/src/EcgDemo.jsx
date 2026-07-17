import { useCallback, useEffect, useRef, useState } from 'react'
import { fetchEcgCase, evaluateEcgInterpretation, ecgImageUrl } from './api'
import { t } from './i18n'
import './PrescriptionLab.css'

const RHYTHM_OPTIONS = ['Normal Sinus Rhythm', 'Sinus Bradycardia', 'Sinus Tachycardia']
const AXIS_OPTIONS = ['Normal Axis', 'Left Axis Deviation', 'Right Axis Deviation', 'Indeterminate Axis']

function ScoreBar({ label, value, max }) {
  const pct = Math.max(0, Math.min(100, (value / max) * 100))
  return (
    <div className="rx-score-row">
      <div className="rx-score-row-top">
        <span>{label}</span>
        <span>{value}/{max}</span>
      </div>
      <div className="rx-score-track">
        <div className="rx-score-fill" style={{ width: `${pct}%` }} />
      </div>
    </div>
  )
}

export default function EcgDemo({ lang = 'en', onBack }) {
  const [caseData, setCaseData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState(null)

  const [heartRate, setHeartRate] = useState('')
  const [rhythm, setRhythm] = useState('')
  const [axis, setAxis] = useState('')
  const [intervals, setIntervals] = useState('')
  const [findings, setFindings] = useState('')
  const [diagnosis, setDiagnosis] = useState('')
  const [management, setManagement] = useState('')

  const [evaluation, setEvaluation] = useState(null)
  const [submitting, setSubmitting] = useState(false)

  const [nextCaseData, setNextCaseData] = useState(null)
  const [nextCaseLoading, setNextCaseLoading] = useState(false)

  const loadRequestIdRef = useRef(0)
  const preloadRequestIdRef = useRef(0)
  const preloadedForRef = useRef(null)

  const resetAnswers = () => {
    setHeartRate('')
    setRhythm('')
    setAxis('')
    setIntervals('')
    setFindings('')
    setDiagnosis('')
    setManagement('')
    setEvaluation(null)
  }

  const loadCase = useCallback(async () => {
    const requestId = ++loadRequestIdRef.current
    setLoading(true)
    setLoadError(null)
    resetAnswers()
    preloadedForRef.current = null
    preloadRequestIdRef.current++
    setNextCaseData(null)
    setNextCaseLoading(false)
    try {
      const data = await fetchEcgCase(lang)
      if (requestId !== loadRequestIdRef.current) return
      setCaseData(data)
    } catch (e) {
      if (requestId !== loadRequestIdRef.current) return
      setLoadError(t(lang, 'ecgError'))
    }
    if (requestId === loadRequestIdRef.current) setLoading(false)
  }, [lang])

  useEffect(() => { loadCase() }, [loadCase])

  useEffect(() => {
    if (!evaluation || !caseData) return
    if (preloadedForRef.current === caseData.case_id) return
    preloadedForRef.current = caseData.case_id

    const requestId = ++preloadRequestIdRef.current
    setNextCaseLoading(true)
    fetchEcgCase(lang)
      .then((data) => {
        if (requestId !== preloadRequestIdRef.current) return
        setNextCaseData(data)
        setNextCaseLoading(false)
      })
      .catch(() => {
        if (requestId !== preloadRequestIdRef.current) return
        setNextCaseLoading(false)
      })
  }, [evaluation, caseData, lang])

  const handleSubmit = async () => {
    if (!caseData || !rhythm.trim() || !diagnosis.trim()) return
    setSubmitting(true)
    try {
      const result = await evaluateEcgInterpretation({
        caseId: caseData.case_id,
        heartRate, rhythm, axis, intervals, findings, diagnosis, management,
      })
      setEvaluation(result)
    } catch (e) {
      alert('Evaluation failed. Check backend and API key.')
    }
    setSubmitting(false)
  }

  const handleNextCase = () => {
    if (nextCaseData) {
      preloadRequestIdRef.current++
      setCaseData(nextCaseData)
      setNextCaseData(null)
      setNextCaseLoading(false)
      resetAnswers()
      preloadedForRef.current = null
    } else {
      loadCase()
    }
  }

  return (
    <div className="rx-lab">
      <div className="rx-topbar">
        <div className="rx-topbar-title">
          <h1>{t(lang, 'ecgLabTitle')}</h1>
          <p>{t(lang, 'ecgLabSubtitle')}</p>
        </div>
        <button className="rx-back-btn" onClick={onBack}>{t(lang, 'backToStart')}</button>
      </div>

      <div className="rx-disclaimer">
        <span className="rx-disclaimer-icon">!</span>
        <span><strong>{lang === 'bn' ? 'প্রশিক্ষণ সিমুলেশন — ' : 'Training simulation — '}</strong>{t(lang, 'ecgDisclaimer')}</span>
      </div>

      {loading && <div className="rx-loading">{t(lang, 'ecgLoadingCase')}</div>}
      {!loading && loadError && <div className="rx-loading rx-error">{loadError}</div>}

      {!loading && !loadError && caseData && (
        <div className="rx-grid">
          {/* Left — case info + ECG strip */}
          <div className="rx-doc">
            <div className="rx-watermark"><span>Training Simulation</span></div>
            <div className="rx-doc-body">
              <div className="rx-letterhead">
                <div className="rx-letterhead-brand">
                  <div className="rx-letterhead-crest">♥</div>
                  <div>
                    <h2>{t(lang, 'ecgLabTitle')}</h2>
                    <small>Case #{caseData.case_id?.slice(0, 8)}</small>
                  </div>
                </div>
              </div>

              <div className="rx-info-strip">
                <div><span className="rx-label">Age</span><span className="rx-value">{caseData.patient?.age}</span></div>
                <div><span className="rx-label">Gender</span><span className="rx-value">
                  {lang === 'bn' ? caseData.patient?.gender_bn : caseData.patient?.gender_en}
                </span></div>
                <div><span className="rx-label">Difficulty</span><span className="rx-value">{caseData.difficulty}</span></div>
              </div>

              <div className="rx-section-title">{t(lang, 'ecgChiefComplaint')}</div>
              <p className="rx-note-text">{lang === 'bn' ? caseData.chief_complaint_bn : caseData.chief_complaint_en}</p>

              <div className="rx-section-title">{t(lang, 'ecgHistory')}</div>
              <p className="rx-note-text">{lang === 'bn' ? caseData.history_bn : caseData.history_en}</p>

              <div className="rx-section-title">{t(lang, 'ecgVitals')}</div>
              <div className="rx-vitals-row">
                <div className="rx-vital"><div className="rx-vital-val">{caseData.vitals?.heartRate}</div><div className="rx-vital-lbl">HR</div></div>
                <div className="rx-vital"><div className="rx-vital-val">{caseData.vitals?.bp}</div><div className="rx-vital-lbl">BP</div></div>
                <div className="rx-vital"><div className="rx-vital-val">{caseData.vitals?.spo2}%</div><div className="rx-vital-lbl">SpO2</div></div>
                <div className="rx-vital"><div className="rx-vital-val">{caseData.vitals?.temp}°C</div><div className="rx-vital-lbl">Temp</div></div>
              </div>

              <div className="rx-section-title">{t(lang, 'ecgStripLabel')}</div>
              <div className="rx-ecg-strip">
                <img src={ecgImageUrl(caseData.ecg_image)} alt="ECG rhythm strip" />
              </div>
            </div>
          </div>

          {/* Right — interpretation form / evaluation */}
          <div className="rx-doc">
            <div className="rx-watermark"><span>Training Simulation</span></div>
            <div className="rx-doc-body">
              {!evaluation ? (
                <>
                  <div className="rx-field-label" style={{ marginTop: 0 }}>{t(lang, 'ecgHeartRate')}</div>
                  <input className="rx-input" value={heartRate} onChange={(e) => setHeartRate(e.target.value)} placeholder={t(lang, 'ecgHeartRatePh')} inputMode="numeric" />

                  <div className="rx-field-label">{t(lang, 'ecgRhythm')}</div>
                  <select className="rx-input rx-select" value={rhythm} onChange={(e) => setRhythm(e.target.value)}>
                    <option value="">{t(lang, 'ecgRhythmPh')}</option>
                    {RHYTHM_OPTIONS.map((r) => <option key={r} value={r}>{r}</option>)}
                  </select>

                  <div className="rx-field-label">{t(lang, 'ecgAxis')}</div>
                  <select className="rx-input rx-select" value={axis} onChange={(e) => setAxis(e.target.value)}>
                    <option value="">{t(lang, 'ecgAxisPh')}</option>
                    {AXIS_OPTIONS.map((a) => <option key={a} value={a}>{a}</option>)}
                  </select>

                  <div className="rx-field-label">{t(lang, 'ecgIntervals')}</div>
                  <input className="rx-input" value={intervals} onChange={(e) => setIntervals(e.target.value)} placeholder={t(lang, 'ecgIntervalsPh')} />

                  <div className="rx-field-label">{t(lang, 'ecgFindings')}</div>
                  <textarea className="rx-textarea" value={findings} onChange={(e) => setFindings(e.target.value)} placeholder={t(lang, 'ecgFindingsPh')} />

                  <div className="rx-field-label">{t(lang, 'ecgDiagnosis')}</div>
                  <input className="rx-input" value={diagnosis} onChange={(e) => setDiagnosis(e.target.value)} placeholder={t(lang, 'ecgDiagnosisPh')} />

                  <div className="rx-field-label">{t(lang, 'ecgManagement')}</div>
                  <textarea className="rx-textarea" value={management} onChange={(e) => setManagement(e.target.value)} placeholder={t(lang, 'ecgManagementPh')} />

                  <button
                    className="rx-submit-btn"
                    onClick={handleSubmit}
                    disabled={submitting || !rhythm.trim() || !diagnosis.trim()}
                  >
                    {submitting ? t(lang, 'ecgEvaluating') : t(lang, 'ecgSubmit')}
                  </button>
                </>
              ) : (
                <div className="rx-evaluation">
                  <div className="rx-eval-stamp-row">
                    <div className="rx-eval-stamp">{evaluation.overallScore}</div>
                    <div className="rx-eval-stamp-label">
                      {t(lang, 'ecgOverallScore')}
                      <small>{t(lang, 'ecgBreakdown')}</small>
                    </div>
                  </div>

                  <ScoreBar label={t(lang, 'ecgRateAcc')} value={evaluation.rateAccuracy} max={20} />
                  <ScoreBar label={t(lang, 'ecgRhythmAcc')} value={evaluation.rhythmAccuracy} max={20} />
                  <ScoreBar label={t(lang, 'ecgAxisIntervals')} value={evaluation.axisIntervals} max={20} />
                  <ScoreBar label={t(lang, 'ecgReasoning')} value={evaluation.clinicalReasoning} max={20} />
                  <ScoreBar label={t(lang, 'ecgMgmtScore')} value={evaluation.management} max={20} />

                  {evaluation.strengths?.length > 0 && (
                    <>
                      <div className="rx-section-title">{t(lang, 'ecgStrengths')}</div>
                      <ul className="rx-eval-list">{evaluation.strengths.map((x, i) => <li key={i}>{x}</li>)}</ul>
                    </>
                  )}
                  {evaluation.missedFindings?.length > 0 && (
                    <>
                      <div className="rx-section-title">{t(lang, 'ecgMissed')}</div>
                      <ul className="rx-eval-list">{evaluation.missedFindings.map((x, i) => <li key={i}>{x}</li>)}</ul>
                    </>
                  )}
                  {evaluation.clinicalExplanation && (
                    <>
                      <div className="rx-section-title">{t(lang, 'ecgExplanation')}</div>
                      <p className="rx-eval-text">{evaluation.clinicalExplanation}</p>
                    </>
                  )}
                  {evaluation.commonMistakes?.length > 0 && (
                    <>
                      <div className="rx-section-title">{t(lang, 'ecgMistakes')}</div>
                      <ul className="rx-eval-list">{evaluation.commonMistakes.map((x, i) => <li key={i}>{x}</li>)}</ul>
                    </>
                  )}
                  {evaluation.differentialDiagnosis?.length > 0 && (
                    <>
                      <div className="rx-section-title">{t(lang, 'ecgDifferential')}</div>
                      <ul className="rx-eval-list">{evaluation.differentialDiagnosis.map((x, i) => <li key={i}>{x}</li>)}</ul>
                    </>
                  )}
                  {evaluation.vivaQuestion && (
                    <>
                      <div className="rx-section-title">{t(lang, 'ecgViva')}</div>
                      <p className="rx-eval-text">{evaluation.vivaQuestion}</p>
                    </>
                  )}

                  <button className="rx-next-case-btn" onClick={handleNextCase}>
                    {nextCaseLoading ? (lang === 'bn' ? 'পরবর্তী কেস প্রস্তুত হচ্ছে...' : 'Loading next case...') : t(lang, 'ecgNextCase')}
                  </button>
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}