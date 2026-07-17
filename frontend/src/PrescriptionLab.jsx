import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { fetchPrescriptionCase, evaluatePrescription } from './api'
import './PrescriptionLab.css'

// Self-contained strings, same pattern as ReportLab.jsx.
const STR = {
  en: {
    backToStart: 'Back',
    title: 'Prescription Lab',
    subtitle: 'Read the labs, write the prescription. Gemma grades your reasoning, not just the answer.',
    disclaimer: 'Simulated training exercise. This lab report and prescription pad are AI-generated for practice only — not a real patient, clinic, or clinical document.',
    loadingCase: 'Generating patient case...',
    caseInfo: 'Patient',
    labName: 'MedLearn Diagnostic Laboratory',
    labTagline: 'Simulated Report · Training Use Only',
    hospitalName: 'MedLearn Teaching Hospital',
    doctorName: 'Dr. [Your Name]',
    doctorRole: 'Trainee Physician',
    age: 'Age', gender: 'Gender',
    chiefComplaint: 'Chief Complaint', history: 'History',
    vitals: 'Vitals', labPanel: 'Laboratory Panel',
    testName: 'Test', value: 'Value', reference: 'Reference Range',
    difficulty: 'Difficulty',
    diagnosis: 'Diagnosis', diagnosisPh: 'What do you think is going on?',
    plan: 'Management Plan',
    planPh: 'Write your investigations, monitoring, and follow-up plan...',
    medicines: 'Rx — Medicines', addMedicine: 'Add a medicine, then Enter',
    noMedicine: 'No medicines added yet',
    submit: 'Submit Prescription', evaluating: 'Evaluating...',
    padFooter: 'Substitute with equivalent generics as required · Not valid for dispensing',
    overallScore: 'Overall Score', breakdown: 'Score Breakdown',
    labInterpretation: 'Lab Interpretation', diagnosisAccuracy: 'Diagnosis',
    medicationSafety: 'Medication Safety', management: 'Management', communication: 'Communication',
    strengths: 'Strengths', missed: 'Missed Findings', safetyFlags: 'Safety Flags',
    pearls: 'Clinical Pearls', nextQuestion: 'Follow-up Question', nextCase: 'Next Case →',
    error: 'Could not load a case. Check that the backend is running.',
    // --- expanded report vocabulary ---
    catHematology: 'Hematology (CBC)',
    catBiochemistry: 'Biochemistry / Metabolic Panel',
    catLiverFunction: 'Liver Function Tests (LFT)',
    catRenalFunction: 'Renal Function Tests (RFT)',
    catLipidProfile: 'Lipid Profile',
    catCoagulation: 'Coagulation Profile',
    catInflammatory: 'Inflammatory Markers',
    catCardiac: 'Cardiac Markers',
    catEndocrine: 'Endocrine / Thyroid Panel',
    catUrinalysis: 'Urinalysis',
    catABG: 'Arterial Blood Gas (ABG)',
    imaging: 'Imaging Findings',
    ecg: 'ECG Findings',
    microbiology: 'Microbiology',
    physicianNotes: "Pathologist's Note",
    specimenId: 'Specimen ID',
    collected: 'Collected',
    reported: 'Reported',
    reportedBy: 'Verified By',
    page: 'Page',
    of: 'of',
    continued: 'Continued on next page →',
    demographicsContd: 'Laboratory Report — continued',
    height: 'Height', weight: 'Weight', bmi: 'BMI', rr: 'Resp. Rate',
  },
  bn: {
    backToStart: 'ফিরে যান',
    title: 'প্রেসক্রিপশন ল্যাব',
    subtitle: 'ল্যাব রিপোর্ট পড়ুন, প্রেসক্রিপশন লিখুন। জেমা শুধু উত্তর নয়, আপনার যুক্তিও মূল্যায়ন করবে।',
    disclaimer: 'এটি একটি প্রশিক্ষণ অনুশীলন। এই ল্যাব রিপোর্ট ও প্রেসক্রিপশন প্যাড AI দ্বারা তৈরি — এটি কোনো প্রকৃত রোগী, ক্লিনিক বা বৈধ চিকিৎসা নথি নয়।',
    loadingCase: 'রোগীর কেস তৈরি হচ্ছে...',
    caseInfo: 'রোগী',
    labName: 'মেডলার্ন ডায়াগনস্টিক ল্যাবরেটরি',
    labTagline: 'সিমুলেটেড রিপোর্ট · শুধুমাত্র প্রশিক্ষণের জন্য',
    hospitalName: 'মেডলার্ন টিচিং হাসপাতাল',
    doctorName: 'ডা. [আপনার নাম]',
    doctorRole: 'শিক্ষানবিশ চিকিৎসক',
    age: 'বয়স', gender: 'লিঙ্গ',
    chiefComplaint: 'প্রধান সমস্যা', history: 'ইতিহাস',
    vitals: 'ভাইটালস', labPanel: 'ল্যাব প্যানেল',
    testName: 'পরীক্ষা', value: 'মান', reference: 'রেফারেন্স রেঞ্জ',
    difficulty: 'কঠিনতা',
    diagnosis: 'রোগ নির্ণয়', diagnosisPh: 'আপনার মতে সমস্যাটা কী?',
    plan: 'ব্যবস্থাপনা পরিকল্পনা',
    planPh: 'আপনার পরীক্ষা, মনিটরিং ও ফলো-আপ পরিকল্পনা লিখুন...',
    medicines: 'Rx — ওষুধ', addMedicine: 'ওষুধ যোগ করুন, তারপর Enter',
    noMedicine: 'এখনো কোনো ওষুধ যোগ করা হয়নি',
    submit: 'প্রেসক্রিপশন জমা দিন', evaluating: 'মূল্যায়ন হচ্ছে...',
    padFooter: 'প্রয়োজনে সমমানের জেনেরিক দিয়ে প্রতিস্থাপন করুন · বিতরণের জন্য বৈধ নয়',
    overallScore: 'সামগ্রিক স্কোর', breakdown: 'স্কোর বিভাজন',
    labInterpretation: 'ল্যাব ব্যাখ্যা', diagnosisAccuracy: 'রোগ নির্ণয়',
    medicationSafety: 'ওষুধের নিরাপত্তা', management: 'ব্যবস্থাপনা', communication: 'যোগাযোগ',
    strengths: 'শক্তিশালী দিক', missed: 'বাদ পড়া বিষয়', safetyFlags: 'নিরাপত্তা সতর্কতা',
    pearls: 'ক্লিনিক্যাল টিপস', nextQuestion: 'পরবর্তী প্রশ্ন', nextCase: 'পরবর্তী কেস →',
    error: 'কেস লোড করা যায়নি। ব্যাকএন্ড চালু আছে কিনা দেখুন।',
    // --- expanded report vocabulary ---
    catHematology: 'হেমাটোলজি (সিবিসি)',
    catBiochemistry: 'বায়োকেমিস্ট্রি / মেটাবলিক প্যানেল',
    catLiverFunction: 'লিভার ফাংশন টেস্ট (LFT)',
    catRenalFunction: 'রেনাল ফাংশন টেস্ট (RFT)',
    catLipidProfile: 'লিপিড প্রোফাইল',
    catCoagulation: 'কোয়াগুলেশন প্রোফাইল',
    catInflammatory: 'ইনফ্ল্যামেটরি মার্কার',
    catCardiac: 'কার্ডিয়াক মার্কার',
    catEndocrine: 'এন্ডোক্রাইন / থাইরয়েড প্যানেল',
    catUrinalysis: 'ইউরিনালাইসিস',
    catABG: 'আর্টেরিয়াল ব্লাড গ্যাস (ABG)',
    imaging: 'ইমেজিং ফলাফল',
    ecg: 'ইসিজি ফলাফল',
    microbiology: 'মাইক্রোবায়োলজি',
    physicianNotes: 'প্যাথোলজিস্ট নোট',
    specimenId: 'নমুনা আইডি',
    collected: 'সংগ্রহের সময়',
    reported: 'রিপোর্টের সময়',
    reportedBy: 'যাচাইকারী',
    page: 'পৃষ্ঠা',
    of: 'এর',
    continued: 'পরবর্তী পৃষ্ঠায় চলবে →',
    demographicsContd: 'ল্যাব রিপোর্ট — চলমান',
    height: 'উচ্চতা', weight: 'ওজন', bmi: 'বিএমআই', rr: 'শ্বাসের হার',
  },
}

// Category keys the frontend understands, in report order.
// Backend can send `case.lab_groups = { hematology: [...], biochemistry: [...], ... }`.
// Any category can be omitted; only categories with data are rendered.
const LAB_CATEGORIES = [
  ['hematology', 'catHematology'],
  ['biochemistry', 'catBiochemistry'],
  ['liver_function', 'catLiverFunction'],
  ['renal_function', 'catRenalFunction'],
  ['lipid_profile', 'catLipidProfile'],
  ['coagulation', 'catCoagulation'],
  ['inflammatory_markers', 'catInflammatory'],
  ['cardiac_markers', 'catCardiac'],
  ['endocrine', 'catEndocrine'],
  ['urinalysis', 'catUrinalysis'],
  ['arterial_blood_gas', 'catABG'],
]

function chunk(arr, size) {
  const out = []
  for (let i = 0; i < arr.length; i += size) out.push(arr.slice(i, i + size))
  return out
}

// Deterministic pseudo-metadata so every case reads like a real, fully-populated
// report even if the backend hasn't started sending specimen_id/collected_at yet.
function pseudoMeta(caseId) {
  const seed = String(caseId ?? '0').split('').reduce((a, c) => a + c.charCodeAt(0), 0)
  const specimen = `SPC-${String(1000 + (seed % 8999)).padStart(4, '0')}`
  const collectHour = 7 + (seed % 4)
  const collectMin = (seed * 7) % 60
  const reportHour = collectHour + 1 + (seed % 2)
  const reportMin = (seed * 13) % 60
  const pad = (n) => String(n).padStart(2, '0')
  return {
    specimen,
    collected: `${pad(collectHour)}:${pad(collectMin)}`,
    reported: `${pad(reportHour)}:${pad(reportMin)}`,
  }
}

function normalizeLabGroups(caseData) {
  const source = caseData?.lab_groups
  const groups = []
  if (source && typeof source === 'object') {
    LAB_CATEGORIES.forEach(([key, labelKey]) => {
      const items = source[key]
      if (Array.isArray(items) && items.length > 0) {
        groups.push({ key, labelKey, items })
      }
    })
  }
  // Legacy fallback: a single flat lab_panel array, same as the original component.
  if (groups.length === 0 && Array.isArray(caseData?.lab_panel) && caseData.lab_panel.length > 0) {
    groups.push({ key: 'legacy', labelKey: 'labPanel', items: caseData.lab_panel })
  }
  return groups
}

function buildPages(caseData) {
  if (!caseData) return []
  const labGroups = normalizeLabGroups(caseData)
  const groupChunks = chunk(labGroups, 2)

  const extras = []
  if (caseData.imaging_findings_en || caseData.imaging_findings_bn) {
    extras.push({ type: 'imaging', labelKey: 'imaging', en: caseData.imaging_findings_en, bn: caseData.imaging_findings_bn })
  }
  if (caseData.ecg_findings_en || caseData.ecg_findings_bn) {
    extras.push({ type: 'ecg', labelKey: 'ecg', en: caseData.ecg_findings_en, bn: caseData.ecg_findings_bn })
  }
  if (caseData.microbiology_en || caseData.microbiology_bn) {
    extras.push({ type: 'microbiology', labelKey: 'microbiology', en: caseData.microbiology_en, bn: caseData.microbiology_bn })
  }
  if (caseData.physician_notes_en || caseData.physician_notes_bn) {
    extras.push({ type: 'notes', labelKey: 'physicianNotes', en: caseData.physician_notes_en, bn: caseData.physician_notes_bn })
  }

  const pages = [{ type: 'header' }]
  groupChunks.forEach((groups) => pages.push({ type: 'labs', groups }))
  if (extras.length > 0) pages.push({ type: 'extra', items: extras })
  return pages
}

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

function flagClass(flag) {
  if (flag === 'critical-high') return 'rx-flag-critical rx-flag-high'
  if (flag === 'critical-low') return 'rx-flag-critical rx-flag-low'
  if (flag === 'high') return 'rx-flag-high'
  if (flag === 'low') return 'rx-flag-low'
  return ''
}

function flagArrow(flag) {
  if (flag === 'critical-high') return '⇑'
  if (flag === 'critical-low') return '⇓'
  if (flag === 'high') return '↑'
  if (flag === 'low') return '↓'
  return null
}

function LabPanelTable({ items, s, lang }) {
  return (
    <table className="rx-lab-table">
      <thead>
        <tr>
          <th>{s.testName}</th>
          <th>{s.value}</th>
          <th>{s.reference}</th>
        </tr>
      </thead>
      <tbody>
        {items.map((item, i) => {
          const name = (lang === 'bn' && item.name_bn) ? item.name_bn : item.name
          const arrow = flagArrow(item.flag)
          return (
            <tr key={i} className={item.flag === 'critical-high' || item.flag === 'critical-low' ? 'rx-row-critical' : ''}>
              <td>{name}</td>
              <td className={flagClass(item.flag)}>
                {item.value} {item.unit}
                {arrow && <span className="rx-flag-arrow">{arrow}</span>}
              </td>
              <td className="rx-ref-range">{item.reference_range}</td>
            </tr>
          )
        })}
      </tbody>
    </table>
  )
}

export default function PrescriptionLab({ lang = 'en', onBack }) {
  const s = STR[lang] || STR.en
  const [caseData, setCaseData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState(null)

  const [diagnosis, setDiagnosis] = useState('')
  const [plan, setPlan] = useState('')
  const [medicines, setMedicines] = useState([])
  const [medicineInput, setMedicineInput] = useState('')

  const [evaluation, setEvaluation] = useState(null)
  const [submitting, setSubmitting] = useState(false)

  const [reportPage, setReportPage] = useState(0)

  const [nextCaseData, setNextCaseData] = useState(null)
  const [nextCaseLoading, setNextCaseLoading] = useState(false)

  // Guards against overlapping/duplicate fetches (e.g. React StrictMode double-invoke
  // in dev, or any re-render re-triggering an effect) silently overwriting fresher state
  // with a stale response.
  const loadRequestIdRef = useRef(0)
  const preloadRequestIdRef = useRef(0)
  const preloadedForRef = useRef(null) // case_id we've already started preloading for

  const loadCase = useCallback(async () => {
    const requestId = ++loadRequestIdRef.current
    setLoading(true)
    setLoadError(null)
    setEvaluation(null)
    setDiagnosis('')
    setPlan('')
    setMedicines([])
    setReportPage(0)
    // A fresh case invalidates any in-flight preload tied to the old case.
    preloadedForRef.current = null
    preloadRequestIdRef.current++
    setNextCaseData(null)
    setNextCaseLoading(false)
    try {
      const data = await fetchPrescriptionCase(lang)
      if (requestId !== loadRequestIdRef.current) return // superseded, ignore
      setCaseData(data)
    } catch (e) {
      if (requestId !== loadRequestIdRef.current) return
      setLoadError(STR[lang]?.error || STR.en.error)
    }
    if (requestId === loadRequestIdRef.current) setLoading(false)
  }, [lang])

  useEffect(() => {
    loadCase()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loadCase])

  // Pre-load the next case in the background as soon as evaluation is in, so
  // "Next Case" is instant. Keyed by case_id so it fires exactly once per case,
  // even if this effect re-runs.
  useEffect(() => {
    if (!evaluation || !caseData) return
    if (preloadedForRef.current === caseData.case_id) return
    preloadedForRef.current = caseData.case_id

    const requestId = ++preloadRequestIdRef.current
    setNextCaseLoading(true)
    fetchPrescriptionCase(lang)
      .then((data) => {
        if (requestId !== preloadRequestIdRef.current) return // superseded
        setNextCaseData(data)
        setNextCaseLoading(false)
      })
      .catch(() => {
        if (requestId !== preloadRequestIdRef.current) return
        setNextCaseLoading(false)
      })
  }, [evaluation, caseData, lang])

  const pages = useMemo(() => buildPages(caseData), [caseData])
  const currentPage = pages[reportPage] || pages[0]
  const meta = useMemo(() => pseudoMeta(caseData?.case_id), [caseData?.case_id])

  const addMedicine = () => {
    const trimmed = medicineInput.trim()
    if (trimmed && !medicines.includes(trimmed)) {
      setMedicines([...medicines, trimmed])
    }
    setMedicineInput('')
  }

  const handleSubmit = async () => {
    if (!caseData || !diagnosis.trim() || !plan.trim()) return
    setSubmitting(true)
    try {
      const result = await evaluatePrescription({
        caseId: caseData.case_id,
        diagnosis,
        plan,
        medicines,
      })
      setEvaluation(result)
    } catch (e) {
      alert('Evaluation failed. Check backend and API key.')
    }
    setSubmitting(false)
  }

  const handleNextCase = () => {
    if (nextCaseData) {
      preloadRequestIdRef.current++ // cancel any late preload response for the old case
      setCaseData(nextCaseData)
      setNextCaseData(null)
      setNextCaseLoading(false)
      setEvaluation(null)
      setDiagnosis('')
      setPlan('')
      setMedicines([])
      setReportPage(0)
      preloadedForRef.current = null
    } else {
      // Preload hasn't finished (or failed) — fetch a fresh case directly.
      loadCase()
    }
  }

  const today = new Date().toLocaleDateString(lang === 'bn' ? 'bn-BD' : 'en-US', {
    year: 'numeric', month: 'short', day: 'numeric',
  })

  const vitalsList = caseData ? [
    { label: 'Temp', val: caseData.vitals?.temp != null ? `${caseData.vitals.temp}°C` : null },
    { label: 'Pulse', val: caseData.vitals?.pulse != null ? caseData.vitals.pulse : null },
    { label: 'BP', val: caseData.vitals?.bp || null },
    { label: 'SpO2', val: caseData.vitals?.spo2 != null ? `${caseData.vitals.spo2}%` : null },
    { label: s.rr, val: caseData.vitals?.rr != null ? caseData.vitals.rr : null },
    { label: s.height, val: caseData.vitals?.height != null ? `${caseData.vitals.height} cm` : null },
    { label: s.weight, val: caseData.vitals?.weight != null ? `${caseData.vitals.weight} kg` : null },
    { label: s.bmi, val: caseData.vitals?.bmi != null ? caseData.vitals.bmi : null },
  ].filter((v) => v.val != null) : []

  return (
    <div className="rx-lab">
      <div className="rx-topbar">
        <div className="rx-topbar-title">
          <h1>{s.title}</h1>
          <p>{s.subtitle}</p>
        </div>
        <button className="rx-back-btn" onClick={onBack}>{s.backToStart}</button>
      </div>

      <div className="rx-disclaimer">
        <span className="rx-disclaimer-icon">!</span>
        <span><strong>{lang === 'bn' ? 'প্রশিক্ষণ সিমুলেশন — ' : 'Training simulation — '}</strong>{s.disclaimer}</span>
      </div>

      {loading && <div className="rx-loading">{s.loadingCase}</div>}
      {!loading && loadError && <div className="rx-loading rx-error">{loadError}</div>}

      {!loading && !loadError && caseData && (
        <div className="rx-grid">
          {/* Left — Lab report (paginated) */}
          <div className="rx-doc">
            <div className="rx-watermark"><span>Training Simulation</span></div>
            <div className="rx-doc-body">
              <div className="rx-letterhead">
                <div className="rx-letterhead-brand">
                  <div className="rx-letterhead-crest">+</div>
                  <div>
                    <h2>{s.labName}</h2>
                    <small>{s.labTagline}</small>
                  </div>
                </div>
                <div className="rx-letterhead-meta">
                  {today}<br />Case #{caseData.case_id ?? '—'}
                </div>
              </div>

              {currentPage?.type !== 'header' && (
                <div className="rx-running-header">
                  <span>{caseData.patient?.age} {s.age.toLowerCase()} · {lang === 'bn' ? caseData.patient?.gender_bn : caseData.patient?.gender_en}</span>
                  <span>{s.demographicsContd}</span>
                </div>
              )}

              {currentPage?.type === 'header' && (
                <>
                  <div className="rx-info-strip">
                    <div><span className="rx-label">{s.age}</span><span className="rx-value">{caseData.patient?.age}</span></div>
                    <div><span className="rx-label">{s.gender}</span><span className="rx-value">
                      {lang === 'bn' ? caseData.patient?.gender_bn : caseData.patient?.gender_en}
                    </span></div>
                    <div><span className="rx-label">{s.difficulty}</span><span className="rx-value">{caseData.difficulty}</span></div>
                  </div>

                  <div className="rx-specimen-meta">
                    <div><span className="rx-label">{s.specimenId}</span><span className="rx-value rx-mono">{caseData.specimen_id || meta.specimen}</span></div>
                    <div><span className="rx-label">{s.collected}</span><span className="rx-value rx-mono">{caseData.collected_at || meta.collected}</span></div>
                    <div><span className="rx-label">{s.reported}</span><span className="rx-value rx-mono">{caseData.reported_at || meta.reported}</span></div>
                  </div>

                  <div className="rx-section-title">{s.chiefComplaint}</div>
                  <p className="rx-note-text">
                    {lang === 'bn' ? caseData.chief_complaint_bn : caseData.chief_complaint_en}
                  </p>

                  {(caseData.history_en || caseData.history_bn) && (
                    <>
                      <div className="rx-section-title">{s.history}</div>
                      <p className="rx-note-text">
                        {lang === 'bn' ? caseData.history_bn : caseData.history_en}
                      </p>
                    </>
                  )}

                  <div className="rx-section-title">{s.vitals}</div>
                  <div className="rx-vitals-row">
                    {vitalsList.map((v, i) => (
                      <div className="rx-vital" key={i}>
                        <div className="rx-vital-val">{v.val}</div>
                        <div className="rx-vital-lbl">{v.label}</div>
                      </div>
                    ))}
                  </div>
                </>
              )}

              {currentPage?.type === 'labs' && currentPage.groups.map((group) => (
                <div key={group.key}>
                  <div className="rx-section-title">{s[group.labelKey] || s.labPanel}</div>
                  <LabPanelTable items={group.items} s={s} lang={lang} />
                </div>
              ))}

              {currentPage?.type === 'extra' && currentPage.items.map((item) => (
                <div key={item.type}>
                  <div className="rx-section-title">{s[item.labelKey]}</div>
                  <p className="rx-note-text">{lang === 'bn' ? (item.bn || item.en) : (item.en || item.bn)}</p>
                </div>
              ))}

              {reportPage === pages.length - 1 && (
                <div className="rx-specimen-meta rx-verified-by">
                  <div><span className="rx-label">{s.reportedBy}</span><span className="rx-value">{caseData.reported_by || s.doctorRole}</span></div>
                </div>
              )}

              {pages.length > 1 && (
                <div className="rx-page-footer">
                  {reportPage < pages.length - 1 && (
                    <div className="rx-continued-note">{s.continued}</div>
                  )}
                  <div className="rx-page-nav">
                    <button
                      onClick={() => setReportPage((p) => Math.max(0, p - 1))}
                      disabled={reportPage === 0}
                      aria-label="Previous page"
                    >‹</button>
                    <span className="rx-page-count">{s.page} {reportPage + 1} {s.of} {pages.length}</span>
                    <button
                      onClick={() => setReportPage((p) => Math.min(pages.length - 1, p + 1))}
                      disabled={reportPage === pages.length - 1}
                      aria-label="Next page"
                    >›</button>
                  </div>
                </div>
              )}
            </div>
          </div>

          {/* Right — Prescription pad / evaluation */}
          <div className="rx-doc">
            <div className="rx-watermark"><span>Training Simulation</span></div>
            <div className="rx-doc-body">
              {!evaluation ? (
                <>
                  <div className="rx-pad-header">
                    <div className="rx-pad-doctor">
                      <h2>{s.doctorName}</h2>
                      <small>{s.doctorRole}</small>
                    </div>
                    <div className="rx-pad-hospital">
                      <strong>{s.hospitalName}</strong>
                      {today}
                    </div>
                  </div>

                  <div className="rx-field-label">{s.diagnosis}</div>
                  <input
                    className="rx-input"
                    value={diagnosis}
                    onChange={(e) => setDiagnosis(e.target.value)}
                    placeholder={s.diagnosisPh}
                  />

                  <div className="rx-rx-symbol">℞</div>

                  <div className="rx-field-label" style={{ marginTop: 0 }}>{s.medicines}</div>
                  <div className="rx-medicine-add">
                    <input
                      value={medicineInput}
                      onChange={(e) => setMedicineInput(e.target.value)}
                      placeholder={s.addMedicine}
                      onKeyDown={(e) => e.key === 'Enter' && addMedicine()}
                    />
                    <button onClick={addMedicine} aria-label="Add medicine">+</button>
                  </div>
                  <ul className="rx-medicine-list">
                    {medicines.length === 0 && <li className="rx-empty" style={{ border: 'none' }}>{s.noMedicine}</li>}
                    {medicines.map((m, i) => (
                      <li key={i}>
                        <span>{m}</span>
                        <button onClick={() => setMedicines(medicines.filter((_, j) => j !== i))} aria-label="Remove medicine">×</button>
                      </li>
                    ))}
                  </ul>

                  <div className="rx-field-label">{s.plan}</div>
                  <textarea className="rx-textarea" value={plan} onChange={(e) => setPlan(e.target.value)} placeholder={s.planPh} />

                  <button
                    className="rx-submit-btn"
                    onClick={handleSubmit}
                    disabled={submitting || !diagnosis.trim() || !plan.trim()}
                  >
                    {submitting ? s.evaluating : s.submit}
                  </button>

                  <div className="rx-pad-footer-note">{s.padFooter}</div>
                </>
              ) : (
                <div className="rx-evaluation">
                  <div className="rx-eval-stamp-row">
                    <div className="rx-eval-stamp">{evaluation.overallScore}</div>
                    <div className="rx-eval-stamp-label">
                      {s.overallScore}
                      <small>{s.breakdown}</small>
                    </div>
                  </div>

                  <ScoreBar label={s.labInterpretation} value={evaluation.labInterpretation} max={20} />
                  <ScoreBar label={s.diagnosisAccuracy} value={evaluation.diagnosisAccuracy} max={20} />
                  <ScoreBar label={s.medicationSafety} value={evaluation.medicationSafety} max={20} />
                  <ScoreBar label={s.management} value={evaluation.management} max={20} />
                  <ScoreBar label={s.communication} value={evaluation.communication} max={20} />

                  {evaluation.strengths?.length > 0 && (
                    <>
                      <div className="rx-section-title">{s.strengths}</div>
                      <ul className="rx-eval-list">{evaluation.strengths.map((x, i) => <li key={i}>{x}</li>)}</ul>
                    </>
                  )}
                  {evaluation.safetyFlags?.length > 0 && (
                    <>
                      <div className="rx-section-title" style={{ color: 'var(--danger)' }}>{s.safetyFlags}</div>
                      <ul className="rx-eval-list rx-danger-list">{evaluation.safetyFlags.map((x, i) => <li key={i}>{x}</li>)}</ul>
                    </>
                  )}
                  {evaluation.missedFindings?.length > 0 && (
                    <>
                      <div className="rx-section-title">{s.missed}</div>
                      <ul className="rx-eval-list">{evaluation.missedFindings.map((x, i) => <li key={i}>{x}</li>)}</ul>
                    </>
                  )}
                  {evaluation.clinicalPearls?.length > 0 && (
                    <>
                      <div className="rx-section-title">{s.pearls}</div>
                      <ul className="rx-eval-list">{evaluation.clinicalPearls.map((x, i) => <li key={i}>{x}</li>)}</ul>
                    </>
                  )}
                  {evaluation.nextQuestion && (
                    <>
                      <div className="rx-section-title">{s.nextQuestion}</div>
                      <p className="rx-eval-text">{evaluation.nextQuestion}</p>
                    </>
                  )}

                  <button className="rx-next-case-btn" onClick={handleNextCase}>
                    {nextCaseLoading ? (lang === 'bn' ? 'পরবর্তী কেস প্রস্তুত হচ্ছে...' : 'Loading next case...') : s.nextCase}
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