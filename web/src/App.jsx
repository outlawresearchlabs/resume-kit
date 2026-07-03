import { useEffect, useMemo, useState } from 'react'
import {
  buildDocx,
  buildResume,
  checkAts,
  fetchLinkedInCallback,
  fetchLinkedInConfig,
  fetchModels,
  healthCheck,
  loadDefaultProfile,
  optimizeProfile,
  optimizerStatus,
  parsePdfsWithAi,
  refinePdfsWithAi,
  startLinkedInAuth,
  testLlmConnection,
} from './api.js'

const STORAGE_KEY = 'resume-kit-profile-v1'
const THEME_KEY = 'resume-kit-theme-v1'
const LLM_SETTINGS_KEY = 'resume-kit-llm-v1'

const LLM_PROVIDERS = [
  { key: 'ollama', label: 'Ollama' },
  { key: 'openai', label: 'OpenAI' },
  { key: 'anthropic', label: 'Anthropic' },
  { key: 'azure', label: 'Azure OpenAI' },
  { key: 'vllm', label: 'vLLM' },
  { key: 'lmstudio', label: 'LM Studio' },
  { key: 'custom', label: 'Custom OpenAI-compatible' },
]

const DEFAULT_LLM_SETTINGS = {
  provider: 'ollama',
  base_url: 'http://blubox:11434',
  api_key: '',
  model: 'llama3.2',
  temperature: 0.4,
  timeout: 120,
}

const DEFAULT_PROFILE = {
  contact: {
    name: '',
    phone: '',
    email: '',
    location: '',
    linkedin: '',
    github: '',
  },
  jobs: [
    { role: '', company: '', dates: '' },
  ],
  skills: {
    leadership: '',
    security: '',
    risk_compliance: '',
    cloud_infra: '',
    networking: '',
    scripting: '',
    customer_facing: '',
  },
  sections: {
    summary: '',
    highlights: ['', '', ''],
    education: [['', '', '']],
    certs: [''],
    awards: [''],
    community: [''],
    homelab: [''],
    research: { main: '' },
    project: { name: '', desc: '' },
    publication: { title: '', tag: '', desc: '', url: '' },
    speaking: { lead: '', detail: '' },
  },
}

const CONFIG_KEYS = [
  { key: 'executive', label: 'Executive / Leadership', role: 'VP of Security Engineering · Strategy · Risk' },
  { key: 'technical', label: 'Technical / Engineering', role: 'Security Engineer · Detection · Automation' },
  { key: 'customer_facing', label: 'Customer-Facing / Solutions', role: 'Security Professional · Solutions Engineering' },
]

const THEMES = [
  { key: 'green', label: 'Phosphor' },
  { key: 'amber', label: 'Amber' },
  { key: 'ice', label: 'Ice' },
]

export default function App() {
  const [profile, setProfile] = useState(() => loadProfile())
  const [configKey, setConfigKey] = useState('executive')
  const [roleLine, setRoleLine] = useState(CONFIG_KEYS[0].role)
  const [subject, setSubject] = useState('')
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')
  const [backendOk, setBackendOk] = useState(false)
  const [theme, setTheme] = useState(() => loadTheme())

  // Optimizer state
  const [jobDescription, setJobDescription] = useState('')
  const [optimizerMode, setOptimizerMode] = useState('question')
  const [suggestions, setSuggestions] = useState(null)
  const [questions, setQuestions] = useState([])
  const [answers, setAnswers] = useState({})
  const [llmOk, setLlmOk] = useState(false)
  const [llmInfo, setLlmInfo] = useState(null)

  // AI settings state
  const [llmSettings, setLlmSettings] = useState(() => loadLlmSettings())
  const [llmModels, setLlmModels] = useState([])
  const [llmModelsBusy, setLlmModelsBusy] = useState(false)
  const [llmSettingsOpen, setLlmSettingsOpen] = useState(false)
  const [llmPingResult, setLlmPingResult] = useState(null)

  // ATS state
  const [atsReport, setAtsReport] = useState(null)
  const [atsBusy, setAtsBusy] = useState(false)

  // AI import state
  const [aiImportFiles, setAiImportFiles] = useState([])
  const [aiImportBusy, setAiImportBusy] = useState(false)
  const [aiImportDraft, setAiImportDraft] = useState(null)
  const [aiImportTexts, setAiImportTexts] = useState([])
  const [aiImportQuestions, setAiImportQuestions] = useState([])
  const [aiImportAnswers, setAiImportAnswers] = useState({})
  const [aiImportNotes, setAiImportNotes] = useState('')

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme)
    saveTheme(theme)
  }, [theme])

  useEffect(() => {
    healthCheck().then(setBackendOk).catch(() => setBackendOk(false))
    optimizerStatus(llmSettings).then((s) => {
      setLlmOk(s?.reachable)
      setLlmInfo(s)
      if (s?.models) setLlmModels(s.models)
    }).catch(() => setLlmOk(false))
  }, [])

  useEffect(() => {
    saveLlmSettings(llmSettings)
  }, [llmSettings])

  useEffect(() => {
    saveProfile(profile)
  }, [profile])

  // Handle LinkedIn OAuth callback on page load.
  useEffect(() => {
    const params = new URLSearchParams(window.location.search)
    const code = params.get('code')
    if (!code) return
    setBusy(true)
    setMessage('Completing LinkedIn sign-in...')
    fetchLinkedInCallback(code)
      .then((data) => {
        const seed = data.contact_seed
        setProfile((p) => ({
          ...p,
          contact: { ...p.contact, ...seed, linkedin: seed.linkedin ? `linkedin.com/in/${seed.linkedin}` : p.contact.linkedin },
        }))
        setMessage('LinkedIn contact info imported. Fill in the rest of your profile.')
        window.history.replaceState({}, '', window.location.pathname)
      })
      .catch((e) => setMessage(`LinkedIn import failed: ${e.message}`))
      .finally(() => setBusy(false))
  }, [])

  const config = CONFIG_KEYS.find((c) => c.key === configKey) || CONFIG_KEYS[0]

  function updateContact(field, value) {
    setProfile((p) => ({ ...p, contact: { ...p.contact, [field]: value } }))
  }

  function updateJob(index, field, value) {
    setProfile((p) => {
      const jobs = p.jobs.map((j, i) => (i === index ? { ...j, [field]: value } : j))
      return { ...p, jobs }
    })
  }

  function removeJobBullet(index, key) {
    setProfile((p) => {
      const jobs = p.jobs.map((j, i) => {
        if (i !== index) return j
        const next = { ...j }
        delete next[key]
        return next
      })
      return { ...p, jobs }
    })
  }

  function addJob() {
    setProfile((p) => ({ ...p, jobs: [...p.jobs, { role: '', company: '', dates: '' }] }))
  }

  function removeJob(index) {
    setProfile((p) => ({ ...p, jobs: p.jobs.filter((_, i) => i !== index) }))
  }

  function moveJob(index, direction) {
    setProfile((p) => {
      const jobs = [...p.jobs]
      const target = index + direction
      if (target < 0 || target >= jobs.length) return p
      const [moved] = jobs.splice(index, 1)
      jobs.splice(target, 0, moved)
      return { ...p, jobs }
    })
  }

  function updateSkill(key, value) {
    setProfile((p) => ({ ...p, skills: { ...p.skills, [key]: value } }))
  }

  function updateSection(field, value) {
    setProfile((p) => ({ ...p, sections: { ...p.sections, [field]: value } }))
  }

  function addBullet(field) {
    setProfile((p) => ({ ...p, sections: { ...p.sections, [field]: [...(p.sections[field] || []), ''] } }))
  }

  function updateBullet(field, idx, value) {
    setProfile((p) => {
      const arr = [...(p.sections[field] || [])]
      arr[idx] = value
      return { ...p, sections: { ...p.sections, [field]: arr } }
    })
  }

  function removeBullet(field, idx) {
    setProfile((p) => {
      const arr = (p.sections[field] || []).filter((_, i) => i !== idx)
      return { ...p, sections: { ...p.sections, [field]: arr } }
    })
  }

  function addEducation() {
    setProfile((p) => ({
      ...p,
      sections: { ...p.sections, education: [...(p.sections.education || []), ['', '', '']] },
    }))
  }

  function updateEducation(idx, subIdx, value) {
    setProfile((p) => {
      const arr = (p.sections.education || []).map((row) => [...row])
      arr[idx][subIdx] = value
      return { ...p, sections: { ...p.sections, education: arr } }
    })
  }

  function removeEducation(idx) {
    setProfile((p) => ({
      ...p,
      sections: { ...p.sections, education: (p.sections.education || []).filter((_, i) => i !== idx) },
    }))
  }

  function onGenerate() {
    setBusy(true)
    setMessage('')
    const overrides = { role_line: roleLine || undefined, subject: subject || undefined }
    buildResume(profile, configKey, overrides)
      .then(({ blob, filename }) => {
        const url = URL.createObjectURL(blob)
        const a = document.createElement('a')
        a.href = url
        a.download = filename
        document.body.appendChild(a)
        a.click()
        a.remove()
        URL.revokeObjectURL(url)
        setMessage('Resume generated successfully.')
      })
      .catch((e) => setMessage(`Error: ${e.message}`))
      .finally(() => setBusy(false))
  }

  function onOptimize(round = 1) {
    if (!jobDescription.trim()) {
      setMessage('Paste a job description first.')
      return
    }
    setBusy(true)
    setMessage(round === 1 ? 'Analyzing job description...' : 'Refining with your answers...')
    optimizeProfile(profile, jobDescription, configKey, optimizerMode, round === 2 ? suggestions : null, round === 2 ? answers : null, llmSettings)
      .then((data) => {
        setSuggestions(data.suggestions)
        setQuestions(data.questions || [])
        if (optimizerMode === 'apply') {
          setMessage('Apply-mode optimization complete. Review the direct profile edits below, then apply or generate.')
        } else if ((data.questions || []).length === 0) {
          setMessage('Optimization complete. Review suggestions below, then apply or generate.')
        } else {
          setMessage('Optimization complete. Please answer the clarifying questions, then refine.')
          setAnswers({})
        }
      })
      .catch((e) => setMessage(`Optimization failed: ${e.message}`))
      .finally(() => setBusy(false))
  }

  function applySuggestions() {
    if (!suggestions) return
    setProfile((p) => {
      const next = { ...p, sections: { ...p.sections }, skills: { ...p.skills } }
      if (suggestions.summary) {
        next.sections.summary = suggestions.summary
      }
      if (suggestions.skill_rewrites && Object.keys(suggestions.skill_rewrites).length > 0) {
        Object.assign(next.skills, suggestions.skill_rewrites)
      }
      if (suggestions.rewritten_jobs && suggestions.rewritten_jobs.length > 0) {
        next.jobs = next.jobs.map((job, idx) => {
          const rw = suggestions.rewritten_jobs.find((r) => r.index === idx)
          if (!rw || !rw.rewritten_bullets) return job
          return { ...job, ...rw.rewritten_bullets }
        })
      }
      if (suggestions.highlight_rewrites && suggestions.highlight_rewrites.length > 0) {
        next.sections.highlights = suggestions.highlight_rewrites
      }
      if (suggestions.education_rewrites && suggestions.education_rewrites.length > 0) {
        next.sections.education = suggestions.education_rewrites
      }
      return next
    })
    if (suggestions.role_line) setRoleLine(suggestions.role_line)
    if (suggestions.subject) setSubject(suggestions.subject)
    setSuggestions(null)
    setMessage('Suggestions applied to your profile.')
  }

  function updateAnswer(id, value) {
    setAnswers((a) => ({ ...a, [id]: value }))
  }

  function updateLlmSetting(field, value) {
    setLlmSettings((s) => ({ ...s, [field]: value }))
  }

  function onListModels() {
    setLlmModelsBusy(true)
    setMessage('')
    fetchModels(llmSettings)
      .then((data) => {
        setLlmModels(data.models || [])
        setMessage(`Found ${(data.models || []).length} model(s).`)
      })
      .catch((e) => setMessage(`Model list failed: ${e.message}`))
      .finally(() => setLlmModelsBusy(false))
  }

  function onTestConnection() {
    setLlmModelsBusy(true)
    setMessage('')
    setLlmPingResult(null)
    testLlmConnection(llmSettings)
      .then((s) => {
        setLlmPingResult(s)
        setLlmOk(s?.reachable)
        if (s?.reachable) {
          setMessage(`Ping OK · ${s.provider} · ${s.model} · "${s.response_preview || 'no response'}"`)
        } else {
          setMessage(`Connection failed · ${s.provider} · ${s.model} · ${s?.error || 'unknown'}`)
        }
      })
      .catch((e) => setMessage(`Connection test failed: ${e.message}`))
      .finally(() => setLlmModelsBusy(false))
  }

  function onGenerateDocx() {
    setAtsBusy(true)
    setMessage('')
    buildDocx(profile, configKey)
      .then(({ blob, filename }) => {
        const url = URL.createObjectURL(blob)
        const a = document.createElement('a')
        a.href = url
        a.download = filename
        document.body.appendChild(a)
        a.click()
        a.remove()
        URL.revokeObjectURL(url)
        setMessage('ATS-compatible DOCX generated successfully.')
      })
      .catch((e) => setMessage(`DOCX error: ${e.message}`))
      .finally(() => setAtsBusy(false))
  }

  function onCheckAts() {
    setAtsBusy(true)
    setMessage('')
    checkAts(profile, configKey)
      .then((data) => {
        setAtsReport(data)
        setMessage('ATS compatibility report updated.')
      })
      .catch((e) => setMessage(`ATS check error: ${e.message}`))
      .finally(() => setAtsBusy(false))
  }

  function onAiImportFileSelect(e) {
    const selected = Array.from(e.target.files || [])
    setAiImportFiles((prev) => {
      const existing = new Set(prev.map((f) => f.name))
      const added = selected.filter((f) => !existing.has(f.name))
      return [...prev, ...added]
    })
    // Reset the input so the same file can be selected again if removed.
    e.target.value = ''
  }

  function removeAiImportFile(name) {
    setAiImportFiles((prev) => prev.filter((f) => f.name !== name))
  }

  function onAiImportParse() {
    if (aiImportFiles.length === 0) {
      setMessage('Select one or more PDFs first.')
      return
    }
    setAiImportBusy(true)
    setMessage('AI is reading your PDFs...')
    parsePdfsWithAi(aiImportFiles, llmSettings)
      .then((data) => {
        setAiImportTexts(data.texts || [])
        setAiImportDraft(data.profile)
        setAiImportQuestions(data.questions || [])
        setAiImportNotes(data.notes || '')
        setAiImportAnswers({})
        if ((data.questions || []).length === 0) {
          setMessage('AI import complete. Review the parsed profile below, then apply.')
        } else {
          setMessage('AI import draft ready. Answer the questions to refine, or apply now.')
        }
      })
      .catch((e) => setMessage(`AI import failed: ${e.message}`))
      .finally(() => setAiImportBusy(false))
  }

  function onAiImportRefine() {
    if (!aiImportDraft) return
    setAiImportBusy(true)
    setMessage('AI is refining with your answers...')
    refinePdfsWithAi(aiImportTexts, aiImportDraft, aiImportQuestions, aiImportAnswers, llmSettings)
      .then((data) => {
        setAiImportDraft(data.profile)
        setAiImportQuestions(data.questions || [])
        setAiImportNotes(data.notes || '')
        setAiImportAnswers({})
        if ((data.questions || []).length === 0) {
          setMessage('Refinement complete. Review and apply.')
        } else {
          setMessage('Refinement complete. New questions remain below.')
        }
      })
      .catch((e) => setMessage(`AI refine failed: ${e.message}`))
      .finally(() => setAiImportBusy(false))
  }

  function onAiImportApply() {
    if (!aiImportDraft) return
    const merged = deepMerge(DEFAULT_PROFILE, aiImportDraft)
    setProfile(merged)
    if (merged.contact?.name) {
      const role = CONFIG_KEYS.find((c) => c.key === configKey)
      setRoleLine(role?.role || '')
    }
    setAiImportFiles([])
    setAiImportDraft(null)
    setAiImportTexts([])
    setAiImportQuestions([])
    setAiImportAnswers({})
    setAiImportNotes('')
    setMessage('AI import applied to your profile. Review and edit before generating.')
  }

  function onAiImportDiscard() {
    setAiImportFiles([])
    setAiImportDraft(null)
    setAiImportTexts([])
    setAiImportQuestions([])
    setAiImportAnswers({})
    setAiImportNotes('')
    setMessage('AI import discarded.')
  }

  function updateAiImportAnswer(id, value) {
    setAiImportAnswers((a) => ({ ...a, [id]: value }))
  }

  function generateAtsTargetedResume() {
    if (!jobDescription.trim()) {
      setMessage('Paste a job description in the "Target this role" panel first.')
      return
    }
    setBusy(true)
    setMessage('Optimizing profile against job description for ATS + interview...')
    optimizeProfile(profile, jobDescription, configKey, 'apply', null, null, llmSettings)
      .then((data) => {
        setSuggestions(data.suggestions)
        setQuestions(data.questions || [])
        setMessage('ATS/interview optimization complete. Click "Apply suggestions to your profile" to update your fields.')
      })
      .catch((e) => setMessage(`Optimization failed: ${e.message}`))
      .finally(() => setBusy(false))
  }

  function onLinkedInConnect() {
    setBusy(true)
    setMessage('Checking LinkedIn OAuth configuration...')
    fetchLinkedInConfig()
      .then((cfg) => {
        if (!cfg.configured) {
          setMessage(`LinkedIn OAuth is not configured. Set LINKEDIN_CLIENT_ID and LINKEDIN_CLIENT_SECRET on the server, then restart. Redirect URI would be: ${cfg.redirect_uri}`)
          return
        }
        setMessage('Redirecting to LinkedIn...')
        startLinkedInAuth()
      })
      .catch((e) => setMessage(`LinkedIn check failed: ${e.message}`))
      .finally(() => setBusy(false))
  }

  function onLoadDefault() {
    setBusy(true)
    setMessage('Loading default profile...')
    loadDefaultProfile()
      .then((data) => {
        if (!data || !data.contact) {
          setMessage('No default profile found. Fill in your details manually.')
          return
        }
        setProfile(deepMerge(DEFAULT_PROFILE, data))
        setMessage('Default profile loaded. Edit and generate.')
      })
      .catch((e) => setMessage(`Load failed: ${e.message}`))
      .finally(() => setBusy(false))
  }

  function onClearProfile() {
    if (!window.confirm('Clear all profile data and start fresh? This cannot be undone.')) return
    setProfile(DEFAULT_PROFILE)
    setRoleLine(CONFIG_KEYS[0].role)
    setSubject('')
    setSuggestions(null)
    setQuestions([])
    setAnswers({})
    setAtsReport(null)
    setMessage('Profile cleared. Start fresh.')
  }

  return (
    <div className="app">
      <header className="app-header">
        <div>
          <h1 className="cursor-blink">Resume Kit</h1>
          <p>Terminal Elegance · Data-driven profile editor</p>
        </div>
        <div className="header-meta">
          <div className="theme-switcher">
            {THEMES.map((t) => (
              <button
                key={t.key}
                className={theme === t.key ? 'active' : ''}
                onClick={() => setTheme(t.key)}
                aria-label={`Switch to ${t.label} theme`}
              >
                {t.label}
              </button>
            ))}
          </div>
          <span className={`status-pill ${backendOk ? 'ok' : 'bad'}`}>
            {backendOk ? 'backend online' : 'backend offline'}
          </span>
        </div>
      </header>

      {message && <div className="message">{message}</div>}

      <div className="toolbar">
        <label>
          Resume target
          <select
            value={configKey}
            onChange={(e) => {
              const key = e.target.value
              setConfigKey(key)
              const cfg = CONFIG_KEYS.find((c) => c.key === key)
              setRoleLine(cfg.role)
            }}
          >
            {CONFIG_KEYS.map((c) => (
              <option key={c.key} value={c.key}>
                {c.label}
              </option>
            ))}
          </select>
        </label>
        <label>
          Role line
          <input value={roleLine} onChange={(e) => setRoleLine(e.target.value)} placeholder={config.role} />
        </label>
        <label>
          PDF subject
          <input value={subject} onChange={(e) => setSubject(e.target.value)} placeholder="e.g. VP of Security Engineering" />
        </label>
      </div>

      <main className="editor">
        <section className="card optimizer-card">
          <h2>Target this role</h2>
          <div className={`status-pill ${llmOk ? 'ok' : 'bad'}`}>
            {llmOk ? `LLM online (${llmInfo?.model || 'unknown'})` : 'LLM offline — start Ollama or set LLM_BASE_URL'}
          </div>
          <textarea
            rows={8}
            value={jobDescription}
            onChange={(e) => setJobDescription(e.target.value)}
            placeholder="Paste the full job description here. The LLM will tailor your resume to this posting."
          />
          <div className="optimizer-actions">
            <label>
              Mode
              <select value={optimizerMode} onChange={(e) => setOptimizerMode(e.target.value)}>
                <option value="question">Question mode — ask clarifying questions</option>
                <option value="apply">ATS + Interview apply mode — rewrite profile directly</option>
              </select>
            </label>
            <button type="button" className="secondary" onClick={() => onOptimize(1)} disabled={busy}>
              {optimizerMode === 'apply' ? 'Analyze job description' : '1. Analyze job description'}
            </button>
            {questions.length > 0 && optimizerMode === 'question' && (
              <button type="button" className="secondary" onClick={() => onOptimize(2)} disabled={busy}>
                2. Refine with answers
              </button>
            )}
          </div>

          <button
            type="button"
            className="primary big ats-target-button"
            onClick={generateAtsTargetedResume}
            disabled={busy || !jobDescription.trim()}
          >
            {busy ? 'Optimizing for ATS…' : 'Optimize for this job (ATS + interview)'}
          </button>

          {questions.length > 0 && (
            <div className="questions">
              <h3>Clarifying questions</h3>
              {questions.map((q) => (
                <label key={q.id}>
                  {q.text}
                  <textarea
                    rows={3}
                    value={answers[q.id] || ''}
                    onChange={(e) => updateAnswer(q.id, e.target.value)}
                    placeholder="Your answer helps the LLM tailor the resume more accurately."
                  />
                </label>
              ))}
            </div>
          )}

          {suggestions && (
            <div className="suggestions">
              <h3>Suggested targeting</h3>
              {suggestions.role_line && (
                <label>
                  Role line
                  <input value={suggestions.role_line} readOnly />
                </label>
              )}
              {suggestions.subject && (
                <label>
                  PDF subject
                  <input value={suggestions.subject} readOnly />
                </label>
              )}
              {suggestions.summary && (
                <label>
                  Summary
                  <textarea rows={4} value={suggestions.summary} readOnly />
                </label>
              )}
              {suggestions.skill_order && suggestions.skill_order.length > 0 && (
                <div className="suggestion-row">
                  <strong>Skill order:</strong> {suggestions.skill_order.join(' → ')}
                </div>
              )}
              {suggestions.skill_rewrites && Object.keys(suggestions.skill_rewrites).length > 0 && (
                <div className="suggestion-row">
                  <strong>Skill rewrites:</strong>
                  <ul className="skill-rewrite-list">
                    {Object.entries(suggestions.skill_rewrites).map(([k, v]) => (
                      <li key={k}><strong>{k}:</strong> {v}</li>
                    ))}
                  </ul>
                </div>
              )}
              {suggestions.current_bullet_keys && suggestions.current_bullet_keys.length > 0 && (
                <div className="suggestion-row">
                  <strong>Current job bullets:</strong> {suggestions.current_bullet_keys.join(', ')}
                </div>
              )}
              {suggestions.previous_bullet_keys && suggestions.previous_bullet_keys.length > 0 && (
                <div className="suggestion-row">
                  <strong>Previous job bullets:</strong> {suggestions.previous_bullet_keys.join(', ')}
                </div>
              )}
              {suggestions.notes && (
                <div className="suggestion-notes">
                  <strong>Notes:</strong> {suggestions.notes}
                </div>
              )}
              <div className="optimizer-actions">
                <button type="button" className="primary" onClick={applySuggestions} disabled={busy}>
                  Apply suggestions to profile
                </button>
              </div>
            </div>
          )}

          <div className="llm-settings-toggle">
            <button type="button" className="secondary" onClick={() => setLlmSettingsOpen((o) => !o)}>
              {llmSettingsOpen ? 'Hide AI settings' : 'Configure AI provider'}
            </button>
          </div>

          {llmSettingsOpen && (
            <div className="llm-settings">
              <h3>AI provider settings</h3>
              <div className="grid-2">
                <label>
                  Provider
                  <select
                    value={llmSettings.provider}
                    onChange={(e) => updateLlmSetting('provider', e.target.value)}
                  >
                    {LLM_PROVIDERS.map((p) => (
                      <option key={p.key} value={p.key}>{p.label}</option>
                    ))}
                  </select>
                </label>
                <label>
                  Model
                  <input
                    value={llmSettings.model}
                    onChange={(e) => updateLlmSetting('model', e.target.value)}
                    placeholder="e.g. llama3.2 or gpt-4o-mini"
                  />
                </label>
                <label>
                  Base URL
                  <input
                    value={llmSettings.base_url}
                    onChange={(e) => updateLlmSetting('base_url', e.target.value)}
                    placeholder="http://blubox:11434"
                  />
                </label>
                <label>
                  API key
                  <input
                    type="password"
                    value={llmSettings.api_key}
                    onChange={(e) => updateLlmSetting('api_key', e.target.value)}
                    placeholder="Required for OpenAI / Anthropic / Azure"
                  />
                </label>
                <label>
                  Temperature
                  <input
                    type="number"
                    min="0"
                    max="2"
                    step="0.1"
                    value={llmSettings.temperature}
                    onChange={(e) => updateLlmSetting('temperature', parseFloat(e.target.value))}
                  />
                </label>
                <label>
                  Timeout (seconds)
                  <input
                    type="number"
                    min="10"
                    max="600"
                    step="10"
                    value={llmSettings.timeout}
                    onChange={(e) => updateLlmSetting('timeout', parseInt(e.target.value, 10))}
                  />
                </label>
              </div>

              <div className="optimizer-actions">
                <button type="button" className="secondary" onClick={onTestConnection} disabled={llmModelsBusy}>
                  {llmModelsBusy ? 'Pinging…' : 'Test connection'}
                </button>
                <button type="button" className="secondary" onClick={onListModels} disabled={llmModelsBusy}>
                  {llmModelsBusy ? 'Listing…' : 'List models'}
                </button>
              </div>

              {llmPingResult && (
                <div className={`ping-result ${llmPingResult.reachable ? 'ok' : 'bad'}`}>
                  {llmPingResult.reachable
                    ? `✓ ${llmPingResult.provider} · ${llmPingResult.model} responded: "${llmPingResult.response_preview || 'pong'}"`
                    : `✗ ${llmPingResult.provider} · ${llmPingResult.model}: ${llmPingResult.error || 'unreachable'}`}
                </div>
              )}

              {llmModels.length > 0 && (
                <div className="model-list">
                  <h4>Available models</h4>
                  <ul>
                    {llmModels.slice(0, 50).map((m, i) => (
                      <li key={i}>
                        {m.name}
                        {m.size_gb != null && ` · ${m.size_gb} GB`}
                        <button
                          type="button"
                          className="link"
                          onClick={() => updateLlmSetting('model', m.name)}
                        >
                          use
                        </button>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          )}
        </section>

        <section className="card ats-card">
          <h2>ATS Compatibility</h2>
          <p className="ats-intro">
            Applicant Tracking Systems prefer plain, structured documents with standard section headers and no graphics. Use this panel to generate an ATS-safe DOCX and check common parser issues.
          </p>
          <div className="optimizer-actions">
            <button type="button" className="secondary" onClick={onCheckAts} disabled={atsBusy}>
              Check ATS compatibility
            </button>
            <button type="button" className="secondary" onClick={onGenerateDocx} disabled={atsBusy}>
              Generate ATS DOCX
            </button>
          </div>

          {atsReport && (
            <div className="ats-report">
              <h3>Report</h3>
              <div className={`ats-score ${atsReport.score >= 80 ? 'ok' : atsReport.score >= 60 ? 'warn' : 'bad'}`}>
                ATS score: <strong>{atsReport.score ?? 0}/100</strong>
              </div>
              {atsReport.issues?.length > 0 && (
                <ul className="ats-issues">
                  {atsReport.issues.map((issue, i) => (
                    <li key={i} className={`issue-${issue.severity || 'info'}`}>
                      <strong>{issue.severity?.toUpperCase() || 'INFO'}:</strong> {issue.message}
                    </li>
                  ))}
                </ul>
              )}
              {atsReport.recommendations?.length > 0 && (
                <ul className="ats-findings">
                  {atsReport.recommendations.map((finding, i) => (
                    <li key={i}>{finding}</li>
                  ))}
                </ul>
              )}
            </div>
          )}
        </section>

        <section className="card">
          <h2>Contact</h2>
          <div className="grid-2">
            {['name', 'phone', 'email', 'location', 'linkedin', 'github'].map((f) => (
              <label key={f}>
                {f}
                <input value={profile.contact[f] || ''} onChange={(e) => updateContact(f, e.target.value)} />
              </label>
            ))}
          </div>
        </section>

        <section className="card">
          <h2>Work Experience</h2>
          {profile.jobs.map((job, idx) => (
            <div key={idx} className="job-block">
              <div className="job-header">
                <h3>Job {idx + 1}</h3>
                <div className="job-controls">
                  <button type="button" className="secondary" onClick={() => moveJob(idx, -1)} disabled={idx === 0}>↑</button>
                  <button type="button" className="secondary" onClick={() => moveJob(idx, 1)} disabled={idx === profile.jobs.length - 1}>↓</button>
                  {profile.jobs.length > 1 && (
                    <button type="button" className="danger" onClick={() => removeJob(idx)}>remove</button>
                  )}
                </div>
              </div>
              <JobFields job={job} onChange={(f, v) => updateJob(idx, f, v)} />
              <h4>Bullets</h4>
              <BulletEditor job={job} onChange={(f, v) => updateJob(idx, f, v)} onRemove={(key) => removeJobBullet(idx, key)} />
            </div>
          ))}
          <button type="button" className="secondary" onClick={addJob}>+ add job</button>
        </section>

        <section className="card">
          <h2>Skills</h2>
          <div className="skills-grid">
            {Object.entries(profile.skills).map(([key, value]) => (
              <label key={key}>
                {key}
                <textarea
                  rows={2}
                  value={value || ''}
                  onChange={(e) => updateSkill(key, e.target.value)}
                  placeholder="Comma-separated skills"
                />
              </label>
            ))}
          </div>
        </section>

        <section className="card">
          <h2>Summary</h2>
          <textarea
            rows={4}
            value={profile.sections.summary || ''}
            onChange={(e) => updateSection('summary', e.target.value)}
            placeholder="2-3 sentences positioning you for this role"
          />

          <h2>Highlights</h2>
          <StringListEditor items={profile.sections.highlights || []} onChange={(idx, v) => updateBullet('highlights', idx, v)} onAdd={() => addBullet('highlights')} onRemove={(idx) => removeBullet('highlights', idx)} />

          <h2>Education</h2>
          {(profile.sections.education || []).map((row, i) => (
            <div key={i} className="row">
              <input value={row[0] || ''} onChange={(e) => updateEducation(i, 0, e.target.value)} placeholder="Degree / credential" />
              <input value={row[1] || ''} onChange={(e) => updateEducation(i, 1, e.target.value)} placeholder="School" />
              <input value={row[2] || ''} onChange={(e) => updateEducation(i, 2, e.target.value)} placeholder="Dates" />
              <button type="button" onClick={() => removeEducation(i)}>remove</button>
            </div>
          ))}
          <button type="button" className="secondary" onClick={addEducation}>+ add education</button>

          <h2>Certifications</h2>
          <StringListEditor items={profile.sections.certs || []} onChange={(idx, v) => updateBullet('certs', idx, v)} onAdd={() => addBullet('certs')} onRemove={(idx) => removeBullet('certs', idx)} />

          <h2>Awards</h2>
          <StringListEditor items={profile.sections.awards || []} onChange={(idx, v) => updateBullet('awards', idx, v)} onAdd={() => addBullet('awards')} onRemove={(idx) => removeBullet('awards', idx)} />

          <h2>Community</h2>
          <StringListEditor items={profile.sections.community || []} onChange={(idx, v) => updateBullet('community', idx, v)} onAdd={() => addBullet('community')} onRemove={(idx) => removeBullet('community', idx)} />

          <h2>Home Lab</h2>
          <StringListEditor items={profile.sections.homelab || []} onChange={(idx, v) => updateBullet('homelab', idx, v)} onAdd={() => addBullet('homelab')} onRemove={(idx) => removeBullet('homelab', idx)} />

          <h2>Independent Research</h2>
          <textarea
            rows={2}
            value={profile.sections.research?.main || ''}
            onChange={(e) => updateSection('research', { main: e.target.value })}
          />

          <h2>Project</h2>
          <div className="grid-2">
            <input value={profile.sections.project?.name || ''} onChange={(e) => updateSection('project', { ...profile.sections.project, name: e.target.value })} placeholder="Project name" />
            <input value={profile.sections.project?.desc || ''} onChange={(e) => updateSection('project', { ...profile.sections.project, desc: e.target.value })} placeholder="One-line description" />
          </div>

          <h2>Publication</h2>
          <div className="grid-2">
            <input value={profile.sections.publication?.title || ''} onChange={(e) => updateSection('publication', { ...profile.sections.publication, title: e.target.value })} placeholder="Title" />
            <input value={profile.sections.publication?.tag || ''} onChange={(e) => updateSection('publication', { ...profile.sections.publication, tag: e.target.value })} placeholder="Year / tag" />
            <input value={profile.sections.publication?.desc || ''} onChange={(e) => updateSection('publication', { ...profile.sections.publication, desc: e.target.value })} placeholder="Publisher / description" />
            <input value={profile.sections.publication?.url || ''} onChange={(e) => updateSection('publication', { ...profile.sections.publication, url: e.target.value })} placeholder="URL" />
          </div>

          <h2>Speaking</h2>
          <div className="grid-2">
            <input value={profile.sections.speaking?.lead || ''} onChange={(e) => updateSection('speaking', { ...profile.sections.speaking, lead: e.target.value })} placeholder="Speaker, Conference (Year):" />
            <input value={profile.sections.speaking?.detail || ''} onChange={(e) => updateSection('speaking', { ...profile.sections.speaking, detail: e.target.value })} placeholder="Talk title" />
          </div>
        </section>

        <section className="card import-card ai-import-card">
          <h2>AI Import from PDF(s)</h2>
          <p className="ats-intro">
            Upload your current resume, a LinkedIn “Save to PDF” export, or both. The AI reads the text, builds a structured profile, asks you verification questions, and then populates the editor.
          </p>
          <div className="import-actions">
            <label className="file-button">
              Choose PDF(s)
              <input
                type="file"
                accept=".pdf"
                multiple
                onChange={onAiImportFileSelect}
              />
            </label>
            <button type="button" className="secondary" onClick={onLoadDefault}>
              Load default profile
            </button>
            <button type="button" className="secondary" onClick={onLinkedInConnect}>
              Connect LinkedIn (basic fields)
            </button>
            <button type="button" className="secondary danger" onClick={onClearProfile}>
              Clear / start fresh
            </button>
          </div>

          {aiImportFiles.length > 0 && (
            <div className="ai-import-files">
              <h4>Files to import</h4>
              <ul>
                {aiImportFiles.map((file) => (
                  <li key={file.name}>
                    <span className="file-name">{file.name}</span>
                    <button
                      type="button"
                      className="file-remove"
                      onClick={() => removeAiImportFile(file.name)}
                      title="Remove"
                    >
                      ×
                    </button>
                  </li>
                ))}
              </ul>
              <button
                type="button"
                className="primary"
                onClick={onAiImportParse}
                disabled={aiImportBusy || aiImportFiles.length === 0}
              >
                {aiImportBusy ? 'Reading PDFs…' : 'Parse with AI'}
              </button>
            </div>
          )}

          {aiImportDraft && (
            <div className="ai-import-panel">
              <h3>AI-parsed profile preview</h3>
              <AiImportPreview draft={aiImportDraft} />

              {aiImportQuestions.length > 0 && (
                <div className="ai-import-questions">
                  <h3>Verification questions</h3>
                  {aiImportQuestions.map((q) => (
                    <label key={q.id}>
                      {q.text}
                      <textarea
                        rows={3}
                        value={aiImportAnswers[q.id] || ''}
                        onChange={(e) => updateAiImportAnswer(q.id, e.target.value)}
                        placeholder="Your answer helps the AI fill gaps or resolve ambiguities."
                      />
                    </label>
                  ))}
                  <div className="ai-import-actions">
                    <button
                      type="button"
                      className="secondary"
                      onClick={onAiImportRefine}
                      disabled={aiImportBusy}
                    >
                      {aiImportBusy ? 'Refining…' : 'Refine with answers'}
                    </button>
                  </div>
                </div>
              )}

              {aiImportNotes && (
                <div className="ai-import-notes">
                  <strong>AI notes:</strong> {aiImportNotes}
                </div>
              )}

              <div className="ai-import-actions">
                <button type="button" className="primary" onClick={onAiImportApply} disabled={aiImportBusy}>
                  Apply to my profile
                </button>
                <button type="button" className="secondary" onClick={onAiImportDiscard} disabled={aiImportBusy}>
                  Discard
                </button>
              </div>
            </div>
          )}
        </section>
      </main>

      <footer className="app-footer">
        <button className="primary big" onClick={onGenerate} disabled={busy}>
          {busy ? 'Generating…' : 'Generate PDF'}
        </button>
        <button className="secondary big" onClick={onGenerateDocx} disabled={atsBusy}>
          {atsBusy ? 'Generating ATS DOCX…' : 'Generate ATS DOCX'}
        </button>
      </footer>
    </div>
  )
}

function AiImportPreview({ draft }) {
  const contact = draft.contact || {}
  const jobs = draft.jobs || []
  const skills = draft.skills || {}
  const sections = draft.sections || {}

  return (
    <div className="ai-import-preview">
      <div className="ai-preview-section">
        <h4>Contact</h4>
        <ul>
          <li><strong>Name:</strong> {contact.name || '—'}</li>
          <li><strong>Phone:</strong> {contact.phone || '—'}</li>
          <li><strong>Email:</strong> {contact.email || '—'}</li>
          <li><strong>Location:</strong> {contact.location || '—'}</li>
          <li><strong>LinkedIn:</strong> {contact.linkedin || '—'}</li>
          <li><strong>GitHub:</strong> {contact.github || '—'}</li>
        </ul>
      </div>

      <div className="ai-preview-section">
        <h4>Summary</h4>
        <p>{sections.summary || '—'}</p>
      </div>

      <div className="ai-preview-section">
        <h4>Work Experience</h4>
        {jobs.length === 0 && <p>—</p>}
        {jobs.map((job, idx) => {
          const bullets = Object.entries(job).filter(([k]) => !['role', 'company', 'dates'].includes(k) && typeof job[k] === 'string')
          return (
            <div key={idx} className="ai-preview-job">
              <strong>{job.role || 'Role'} · {job.company || 'Company'} · {job.dates || 'Dates'}</strong>
              <ul>
                {bullets.map(([k, v]) => (
                  <li key={k}>{v}</li>
                ))}
                {bullets.length === 0 && <li>No bullets parsed.</li>}
              </ul>
            </div>
          )
        })}
      </div>

      <div className="ai-preview-section">
        <h4>Skills</h4>
        <ul>
          {Object.entries(skills).map(([k, v]) => (
            <li key={k}><strong>{k}:</strong> {v || '—'}</li>
          ))}
        </ul>
      </div>

      <div className="ai-preview-section">
        <h4>Education</h4>
        {(sections.education || []).length === 0 && <p>—</p>}
        {(sections.education || []).map((row, idx) => (
          <p key={idx}>{(row || []).join(' · ')}</p>
        ))}
      </div>

      {(sections.certs || []).some(Boolean) && (
        <div className="ai-preview-section">
          <h4>Certifications</h4>
          <ul>{(sections.certs || []).filter(Boolean).map((c, i) => <li key={i}>{c}</li>)}</ul>
        </div>
      )}

      {(sections.awards || []).some(Boolean) && (
        <div className="ai-preview-section">
          <h4>Awards</h4>
          <ul>{(sections.awards || []).filter(Boolean).map((a, i) => <li key={i}>{a}</li>)}</ul>
        </div>
      )}
    </div>
  )
}

function JobFields({ job, onChange }) {
  return (
    <div className="grid-3">
      <label>
        Role
        <input value={job.role || ''} onChange={(e) => onChange('role', e.target.value)} />
      </label>
      <label>
        Company
        <input value={job.company || ''} onChange={(e) => onChange('company', e.target.value)} />
      </label>
      <label>
        Dates
        <input value={job.dates || ''} onChange={(e) => onChange('dates', e.target.value)} />
      </label>
    </div>
  )
}

function BulletEditor({ job, onChange, onRemove }) {
  const bullets = useMemo(() => {
    const { role, company, dates, ...rest } = job
    return Object.entries(rest).filter(([, v]) => typeof v === 'string')
  }, [job])

  const [newKey, setNewKey] = useState('')
  const [newValue, setNewValue] = useState('')

  function add() {
    if (!newKey.trim()) return
    onChange(newKey.trim(), newValue)
    setNewKey('')
    setNewValue('')
  }

  return (
    <div className="bullet-editor">
      {bullets.map(([key, value]) => (
        <div key={key} className="bullet-row">
          <input className="key" value={key} readOnly />
          <textarea rows={2} value={value || ''} onChange={(e) => onChange(key, e.target.value)} />
          <div className="bullet-actions">
            <button type="button" className="secondary" onClick={() => onChange(key, '')}>clear</button>
            <button type="button" className="danger" onClick={() => onRemove(key)}>remove</button>
          </div>
        </div>
      ))}
      <div className="bullet-row add">
        <input className="key" value={newKey} onChange={(e) => setNewKey(e.target.value)} placeholder="new bullet key" />
        <textarea rows={2} value={newValue} onChange={(e) => setNewValue(e.target.value)} placeholder="bullet text" />
        <button type="button" className="secondary" onClick={add}>+ add</button>
      </div>
    </div>
  )
}

function StringListEditor({ items, onChange, onAdd, onRemove }) {
  return (
    <div className="string-list">
      {items.map((item, i) => (
        <div key={i} className="row">
          <input value={item || ''} onChange={(e) => onChange(i, e.target.value)} />
          <button type="button" onClick={() => onRemove(i)}>remove</button>
        </div>
      ))}
      <button type="button" className="secondary" onClick={onAdd}>+ add</button>
    </div>
  )
}

function loadProfile() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return DEFAULT_PROFILE
    return deepMerge(DEFAULT_PROFILE, JSON.parse(raw))
  } catch {
    return DEFAULT_PROFILE
  }
}

function saveProfile(profile) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(profile))
  } catch {
    // ignore
  }
}

function deepMerge(base, patch) {
  if (Array.isArray(base)) {
    return patch && Array.isArray(patch) ? patch : base
  }
  if (base && typeof base === 'object') {
    const out = { ...base }
    if (patch && typeof patch === 'object') {
      for (const key of Object.keys(patch)) {
        out[key] = deepMerge(base[key], patch[key])
      }
    }
    return out
  }
  return patch !== undefined ? patch : base
}

function loadTheme() {
  try {
    return localStorage.getItem(THEME_KEY) || 'green'
  } catch {
    return 'green'
  }
}

function saveTheme(theme) {
  try {
    localStorage.setItem(THEME_KEY, theme)
  } catch {
    // ignore
  }
}

function loadLlmSettings() {
  try {
    const raw = localStorage.getItem(LLM_SETTINGS_KEY)
    if (!raw) return DEFAULT_LLM_SETTINGS
    return { ...DEFAULT_LLM_SETTINGS, ...JSON.parse(raw) }
  } catch {
    return DEFAULT_LLM_SETTINGS
  }
}

function saveLlmSettings(settings) {
  try {
    localStorage.setItem(LLM_SETTINGS_KEY, JSON.stringify(settings))
  } catch {
    // ignore
  }
}
