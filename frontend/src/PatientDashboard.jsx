import { useState } from 'react'
import { reportUrl } from './api'
import { t } from './i18n'

export default function PatientDashboard({
  patient,
  session,
  lang,
  tab,
  onTabChange,
  onClose,
  onOrderTest,
  testResult,
  orderingTest,
  orderError,
  chatMessages,
  onChat,
  chatLoading,
  chatError,
}) {
  const [testName, setTestName] = useState('')
  const [message, setMessage] = useState('')

  const QUICK_TESTS = [
    'Complete blood count',
    'Chest X-ray',
    'ECG',
    'Basic metabolic panel',
    'Urinalysis',
    'CRP',
  ]

  const categoryLabel = session?.category || (lang === 'bn' ? 'যেকোনো' : 'Any')
  const isBn = lang === 'bn'

  const handleOrder = async () => {
    if (!testName.trim()) return
    await onOrderTest(testName.trim())
    setTestName('')
  }

  const handleChat = async () => {
    if (!message.trim()) return
    await onChat(message.trim())
    setMessage('')
  }

  const tabNames = [
    { id: 'overview', label: isBn ? 'সারাংশ' : 'Overview' },
    { id: 'order', label: isBn ? 'পরীক্ষা করুন' : 'Order Test' },
    { id: 'chat', label: isBn ? 'রোগীর সঙ্গে কথা' : 'Patient Chat' },
  ]

  return (
    <div className="dashboard-modal" role="dialog" aria-modal="true">
      <div className="dashboard-backdrop" onClick={onClose} />
      <div className="dashboard-shell">
        <div className="dashboard-header">
          <div>
            <div className="dashboard-title">{isBn ? 'রোগী পরীক্ষা' : 'Patient Explore'}</div>
            <div className="dashboard-subtitle">
              {isBn
                ? 'রোগীর তথ্য, ল্যাব নির্দেশ এবং প্রশ্ন-উত্তর সেশন'
                : 'Review patient details, order tests, and chat with the patient.'}
            </div>
          </div>
          <button className="dashboard-modal-close" onClick={onClose}>
            ×
          </button>
        </div>

        <div className="dashboard-meta-row">
          <div className="dashboard-badge">{isBn ? 'ক্যাটাগরি' : 'Category'}</div>
          <span>{categoryLabel}</span>
          <div className="dashboard-badge">{isBn ? 'পরিদর্শন' : 'Visit'}</div>
          <span>{patient.visit_type === 'followup' ? (isBn ? 'ফলোআপ' : 'Follow-up') : (isBn ? 'প্রাথমিক' : 'Initial')}</span>
        </div>

        <div className="dashboard-tabs">
          {tabNames.map((item) => (
            <button
              key={item.id}
              className={`dashboard-tab ${tab === item.id ? 'active' : ''}`}
              onClick={() => onTabChange(item.id)}
              type="button"
            >
              {item.label}
            </button>
          ))}
        </div>

        {tab === 'overview' && (
          <div className="dashboard-section">
            <div className="dashboard-grid">
              <div className="dashboard-card">
                <div className="label">{t(lang, 'naam')}</div>
                <div className="value">{isBn ? patient.name_bn : patient.name_en}</div>
              </div>
              <div className="dashboard-card">
                <div className="label">{t(lang, 'boyosh')}</div>
                <div className="value">{patient.age} {isBn ? 'বছর' : 'yrs'}</div>
              </div>
              <div className="dashboard-card">
                <div className="label">{t(lang, 'gender')}</div>
                <div className="value">{isBn ? patient.gender_bn : patient.gender_en}</div>
              </div>
              <div className="dashboard-card">
                <div className="label">{t(lang, 'blood')}</div>
                <div className="value">{patient.blood_group}</div>
              </div>
              <div className="dashboard-card">
                <div className="label">{t(lang, 'weight')}</div>
                <div className="value">{patient.weight_kg} kg</div>
              </div>
            </div>

            <div className="dashboard-section-inner">
              <h3>{t(lang, 'complaint')}</h3>
              <p>{isBn ? patient.chief_complaint_bn : patient.chief_complaint_en}</p>
            </div>
            <div className="dashboard-section-inner">
              <h3>{t(lang, 'history')}</h3>
              <p>{isBn ? patient.history_bn : patient.history_en}</p>
            </div>
            <div className="dashboard-grid">
              <div className="dashboard-card">
                <div className="label">{t(lang, 'bp')}</div>
                <div className="value">{patient.vitals.bp}</div>
              </div>
              <div className="dashboard-card">
                <div className="label">{t(lang, 'pulse')}</div>
                <div className="value">{patient.vitals.pulse}</div>
              </div>
              <div className="dashboard-card">
                <div className="label">{t(lang, 'temp')}</div>
                <div className="value">{patient.vitals.temp}°C</div>
              </div>
              <div className="dashboard-card">
                <div className="label">{t(lang, 'spo2')}</div>
                <div className="value">{patient.vitals.spo2}%</div>
              </div>
            </div>
          </div>
        )}

        {tab === 'order' && (
          <div className="dashboard-section">
            <div className="dashboard-section-inner">
              <h3>{isBn ? 'পরীক্ষা নির্দেশ করুন' : 'Order a Test'}</h3>
              <p className="dashboard-help-text">
                {isBn
                  ? 'রোগীর জন্য একটি উপযুক্ত পরীক্ষার নাম লিখুন, তারপর Gemma থেকে রেজাল্ট দেখুন।'
                  : 'Type a test name and see a realistic result from the patient scenario.'}
              </p>
            </div>
            <div className="test-buttons">
              {QUICK_TESTS.map((name) => (
                <button
                  key={name}
                  type="button"
                  className="test-button"
                  onClick={async () => {
                    await onOrderTest(name)
                    setDashboardTab('order')
                  }}
                  disabled={orderingTest}
                >
                  {name}
                </button>
              ))}
            </div>
            <div className="dashboard-message-input-row">
              <input
                value={testName}
                onChange={(e) => setTestName(e.target.value)}
                placeholder={isBn ? 'যেমন: সম্পূর্ণ রক্তের পরীক্ষা' : 'e.g. Complete blood count'}
              />
              <button onClick={handleOrder} disabled={orderingTest || !testName.trim()}>
                {orderingTest ? (isBn ? 'পরীক্ষা চলছে...' : 'Ordering...') : (isBn ? 'পরীক্ষা নির্দেশ' : 'Order')}
              </button>
            </div>
            {orderError && <p className="dashboard-error">{orderError}</p>}
            {testResult && (
              <div className="dashboard-section-inner">
                <h4>{isBn ? 'প্রায়োগিক ফলাফল' : 'Test Result'}</h4>
                <div className="dashboard-card" style={{ width: '100%' }}>
                  <div className="label">{isBn ? 'পরীক্ষার নাম' : 'Test'}</div>
                  <div className="value">{testResult.test_name}</div>
                </div>
                {testResult.report_type !== 'xray' && (
                  <>
                    <div className="dashboard-card" style={{ width: '100%' }}>
                      <div className="label">{isBn ? 'স্থিতি' : 'Status'}</div>
                      <div className="value">{testResult.status}</div>
                    </div>
                    <div className="dashboard-card" style={{ width: '100%' }}>
                      <div className="label">{isBn ? 'সারাংশ' : 'Summary'}</div>
                      <div className="value">{isBn ? testResult.summary_bn : testResult.summary_en}</div>
                    </div>
                  </>
                )}
                {testResult.report_image && (
                  <div className="dashboard-card" style={{ width: '100%' }}>
                    <div className="label">{isBn ? 'এক্স-রে চিত্র' : 'X-ray Image'}</div>
                    <img
                      className="dashboard-report-image"
                      src={reportUrl(testResult.report_image)}
                      alt={isBn ? 'এক্স-রে চিত্র' : 'X-ray image'}
                    />
                  </div>
                )}
              </div>
            )}
          </div>
        )}

        {tab === 'chat' && (
          <div className="dashboard-section">
            <div className="dashboard-section-inner">
              <h3>{isBn ? 'রোগীর সঙ্গে কথা বলুন' : 'Chat with the Patient'}</h3>
              <p className="dashboard-help-text">
                {isBn
                  ? 'ডাক্তারের প্রশ্ন করুন, রোগী সংক্ষিপ্ত এবং বাস্তবভাবে জবাব দেবে।'
                  : 'Ask the patient a question and receive a short, character-driven reply.'}
              </p>
            </div>
            <div className="dashboard-message-list">
              {chatMessages.map((message, index) => (
                <div key={index} className={`dashboard-message ${message.role}`}>
                  <div className="message-role">{message.role === 'doctor' ? (isBn ? 'আপনি' : 'Doctor') : (isBn ? 'রোগী' : 'Patient')}</div>
                  <div className="message-content">{message.content}</div>
                </div>
              ))}
            </div>
            <div className="dashboard-message-input-row">
              <input
                value={message}
                onChange={(e) => setMessage(e.target.value)}
                placeholder={isBn ? 'রোল-আপ প্রশ্ন লিখুন...' : 'Ask a short patient question...'}
              />
              <button onClick={handleChat} disabled={chatLoading || !message.trim()}>
                {chatLoading ? (isBn ? 'জবাব অপেক্ষা...' : 'Waiting...') : (isBn ? 'প্রশ্ন পাঠান' : 'Send')}
              </button>
            </div>
            {chatError && <p className="dashboard-error">{chatError}</p>}
          </div>
        )}
      </div>
    </div>
  )
}
