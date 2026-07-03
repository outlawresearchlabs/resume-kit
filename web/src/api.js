const API_BASE = '' // Vite proxy forwards /api to localhost:8000

export async function buildResume(profile, configKey, overrides = {}) {
  const resp = await fetch(`${API_BASE}/api/build`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ profile, config_key: configKey, overrides }),
  })
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({ detail: resp.statusText }))
    throw new Error(err.detail || `Build failed: ${resp.status}`)
  }
  const blob = await resp.blob()
  const pages = resp.headers.get('X-Resume-Pages') || '?'
  return { blob, filename: filenameFromHeaders(resp) || `${configKey}_resume.pdf`, pages }
}

export async function importResumePdf(file) {
  const form = new FormData()
  form.append('file', file)
  const resp = await fetch(`${API_BASE}/api/import/resume-pdf`, {
    method: 'POST',
    body: form,
  })
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({ detail: resp.statusText }))
    throw new Error(err.detail || `Import failed: ${resp.status}`)
  }
  return resp.json()
}

export async function importLinkedInPdf(file) {
  const form = new FormData()
  form.append('file', file)
  const resp = await fetch(`${API_BASE}/api/import/linkedin-pdf`, {
    method: 'POST',
    body: form,
  })
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({ detail: resp.statusText }))
    throw new Error(err.detail || `Import failed: ${resp.status}`)
  }
  return resp.json()
}

export async function parsePdfsWithAi(files, llmSettings) {
  const form = new FormData()
  for (const file of files) {
    form.append('files', file)
  }
  if (llmSettings) {
    form.append('llm_settings', JSON.stringify(llmSettings))
  }
  const resp = await fetch(`${API_BASE}/api/import/ai-parse`, {
    method: 'POST',
    body: form,
  })
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({ detail: resp.statusText }))
    throw new Error(err.detail || `AI parse failed: ${resp.status}`)
  }
  return resp.json()
}

export async function refinePdfsWithAi(texts, profile, questions, answers, llmSettings) {
  const resp = await fetch(`${API_BASE}/api/import/ai-parse/refine`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      texts,
      profile,
      questions,
      answers,
      llm_settings: llmSettings,
    }),
  })
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({ detail: resp.statusText }))
    throw new Error(err.detail || `AI refine failed: ${resp.status}`)
  }
  return resp.json()
}

export async function fetchLinkedInConfig() {
  const resp = await fetch(`${API_BASE}/api/linkedin/config`)
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({ detail: resp.statusText }))
    throw new Error(err.detail || `Config check failed: ${resp.status}`)
  }
  return resp.json()
}

export async function startLinkedInAuth() {
  const resp = await fetch(`${API_BASE}/api/linkedin/auth`)
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({ detail: resp.statusText }))
    throw new Error(err.detail || `OAuth failed: ${resp.status}`)
  }
  const data = await resp.json()
  window.location.href = data.authorization_url
}

export async function fetchLinkedInCallback(code) {
  const resp = await fetch(`${API_BASE}/api/linkedin/callback?code=${encodeURIComponent(code)}`)
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({ detail: resp.statusText }))
    throw new Error(err.detail || `OAuth callback failed: ${resp.status}`)
  }
  return resp.json()
}

export async function healthCheck() {
  const resp = await fetch(`${API_BASE}/api/health`)
  return resp.ok
}

export async function loadDefaultProfile() {
  const resp = await fetch(`${API_BASE}/api/profile/default`)
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({ detail: resp.statusText }))
    throw new Error(err.detail || `Load failed: ${resp.status}`)
  }
  const data = await resp.json()
  return data.profile
}

export async function optimizeProfile(profile, jobDescription, configKey, mode = 'question', previousSuggestions, answers, llmSettings) {
  const body = {
    profile,
    job_description: jobDescription,
    config_key: configKey,
    mode,
  }
  if (previousSuggestions) {
    body.previous_suggestions = previousSuggestions
    body.answers = answers || {}
  }
  if (llmSettings) {
    body.llm_settings = llmSettings
  }
  const resp = await fetch(`${API_BASE}/api/optimize`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({ detail: resp.statusText }))
    throw new Error(err.detail || `Optimization failed: ${resp.status}`)
  }
  return resp.json()
}

export async function optimizerStatus(llmSettings) {
  const opts = {
    method: llmSettings ? 'POST' : 'GET',
    headers: { 'Content-Type': 'application/json' },
  }
  if (llmSettings) {
    opts.body = JSON.stringify(llmSettings)
  }
  const resp = await fetch(`${API_BASE}/api/optimize/status`, opts)
  if (!resp.ok) return { configured: false, reachable: false }
  return resp.json()
}

export async function fetchModels(llmSettings) {
  const resp = await fetch(`${API_BASE}/api/models`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(llmSettings || {}),
  })
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({ detail: resp.statusText }))
    throw new Error(err.detail || `Model list failed: ${resp.status}`)
  }
  return resp.json()
}

export async function testLlmConnection(llmSettings) {
  const resp = await fetch(`${API_BASE}/api/optimize/ping`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ llm_settings: llmSettings || {} }),
  })
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({ detail: resp.statusText }))
    throw new Error(err.detail || `Ping failed: ${resp.status}`)
  }
  return resp.json()
}

export async function buildDocx(profile, configKey, overrides = {}) {
  const resp = await fetch(`${API_BASE}/api/build/docx`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ profile, config_key: configKey, overrides }),
  })
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({ detail: resp.statusText }))
    throw new Error(err.detail || `DOCX build failed: ${resp.status}`)
  }
  const blob = await resp.blob()
  return { blob, filename: filenameFromHeaders(resp) || `${configKey}_resume_ats.docx` }
}

export async function checkAts(profile, configKey) {
  const resp = await fetch(`${API_BASE}/api/ats/check`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ profile, config_key: configKey }),
  })
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({ detail: resp.statusText }))
    throw new Error(err.detail || `ATS check failed: ${resp.status}`)
  }
  return resp.json()
}

function filenameFromHeaders(resp) {
  const cd = resp.headers.get('content-disposition')
  if (!cd) return null
  const m = cd.match(/filename="?([^";]+)"?/)
  return m ? m[1] : null
}
