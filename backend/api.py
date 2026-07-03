"""
api.py — FastAPI backend for the Resume Kit web app.

Endpoints:
  POST /api/build              → generate PDF from profile JSON + config key
  POST /api/build/docx         → generate ATS-safe DOCX
  POST /api/ats/check          → ATS compatibility report
  POST /api/optimize           → LLM job-description optimizer
  POST /api/import/linkedin-pdf → extract text from a LinkedIn "Save to PDF" export
  GET  /api/linkedin/auth      → start LinkedIn OAuth flow
  GET  /api/linkedin/callback  → finish LinkedIn OAuth and return profile seed

Run locally:
    python api.py
"""
import json
import os
import re
import subprocess
import tempfile
import textwrap
import urllib.parse
import urllib.request
from typing import Optional

import requests
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

import docx_builder as DB
import terminal_engine as E
import config_templates as CT
import profile

app = FastAPI(title="Resume Kit API")

# Allow the Vite dev server to call the API.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT_DIR = os.path.dirname(_HERE)

# Generated files land in the repo root's ./out directory by default.
_OUT_DIR = os.environ.get("RESUME_OUT_DIR") or os.path.join(_ROOT_DIR, "out")
os.makedirs(_OUT_DIR, exist_ok=True)

# Path to the built React frontend; mounted at the very bottom of this file
# so API routes take precedence.
_WEB_DIST = os.path.join(_ROOT_DIR, "frontend", "dist")

# ---------------------------------------------------------------------------
# PDF generation
# ---------------------------------------------------------------------------

@app.post("/api/build")
def api_build(payload: dict):
    """Generate a PDF resume from a profile + config key.

    Body example:
    {
      "profile": { ...profile JSON... },
      "config_key": "executive",
      "overrides": {
        "role_line": "VP of Security Engineering · Strategy · Risk",
        "subject": "VP of Security Engineering",
        "summary": "Custom summary...",
        "current_pick": ["vm_strategy", "assessments", "scanning", "collaboration"],
        "skill_pick": ["leadership", "security", "risk_compliance", "cloud_infra"]
      }
    }
    """
    prof = payload.get("profile")
    if not prof:
        raise HTTPException(status_code=400, detail="profile is required")

    config_key = payload.get("config_key", "executive")
    overrides = payload.get("overrides") or {}

    K = profile.load(data=prof)
    contact = K["CONTACT"]

    # Use override role_line/subject, or fall back to sensible defaults.
    role_line = overrides.pop("role_line", None) or _default_role_line(K, config_key)
    subject = overrides.pop("subject", None) or _default_subject(K, config_key)

    out_path = os.path.join(_OUT_DIR, f"{_safe_name(contact.get('name', 'resume'))}_{config_key}.pdf")

    def render(r):
        CT.render_template(config_key, K, r, role_line=role_line, subject=subject, **overrides)

    n = E.build(out_path, render, contact, role_line, subject)
    return FileResponse(
        out_path,
        media_type="application/pdf",
        filename=os.path.basename(out_path),
        headers={"X-Resume-Pages": str(n)},
    )


@app.post("/api/build/docx")
def api_build_docx(payload: dict):
    """Generate an ATS-safe DOCX from profile JSON + config key."""
    prof = payload.get("profile")
    if not prof:
        raise HTTPException(status_code=400, detail="profile is required")

    config_key = payload.get("config_key", "executive")
    overrides = payload.get("overrides") or {}

    contact = prof.get("contact", {})
    safe_name = re.sub(r"[^a-zA-Z0-9]+", "_", contact.get("name", "resume")).strip("_").lower() or "resume"
    out_path = os.path.join(_OUT_DIR, f"{safe_name}_{config_key}_ats.docx")

    DB.build_ats_docx(prof, config_key, overrides, out_path)
    return FileResponse(
        out_path,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        filename=os.path.basename(out_path),
    )


@app.post("/api/ats/check")
def api_ats_check(payload: dict):
    """Return an ATS compatibility report for the profile + config."""
    prof = payload.get("profile")
    if not prof:
        raise HTTPException(status_code=400, detail="profile is required")

    config_key = payload.get("config_key", "executive")

    contact = prof.get("contact", {})
    jobs_raw = prof.get("jobs", {})
    if isinstance(jobs_raw, dict):
        jobs = []
        for key in ("current", "previous", "early"):
            if jobs_raw.get(key):
                jobs.append(jobs_raw[key])
    else:
        jobs = jobs_raw

    skills = prof.get("skills", {})
    sections = prof.get("sections", {})

    issues = []
    if not contact.get("name"):
        issues.append({"severity": "error", "field": "contact.name", "message": "Name is missing; ATS cannot identify candidate."})
    if not contact.get("email"):
        issues.append({"severity": "error", "field": "contact.email", "message": "Email is missing."})
    if not contact.get("phone"):
        issues.append({"severity": "warning", "field": "contact.phone", "message": "Phone is missing; some ATS parsers require it."})

    if not sections.get("summary", "").strip():
        issues.append({"severity": "warning", "field": "sections.summary", "message": "Summary is empty; adds keyword density."})

    for i, job in enumerate(jobs):
        if not job.get("role"):
            issues.append({"severity": "error", "field": f"jobs[{i}].role", "message": f"Job {i+1} has no role."})
        if not job.get("company"):
            issues.append({"severity": "error", "field": f"jobs[{i}].company", "message": f"Job {i+1} has no company."})
        if not job.get("dates"):
            issues.append({"severity": "warning", "field": f"jobs[{i}].dates", "message": f"Job {i+1} has no dates."})
        else:
            d = job["dates"]
            if not re.search(r"(January|February|March|April|May|June|July|August|September|October|November|December|Present|Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\b", d):
                issues.append({"severity": "warning", "field": f"jobs[{i}].dates", "message": f"Job {i+1} dates may not parse cleanly: '{d}'. Prefer 'Month YYYY – Present'."})

    skill_count = sum(len(v.split(",")) for v in skills.values() if isinstance(v, str) and v.strip())
    if skill_count == 0:
        issues.append({"severity": "error", "field": "skills", "message": "No skills found."})
    elif skill_count < 5:
        issues.append({"severity": "warning", "field": "skills", "message": f"Only {skill_count} skill tokens found; most ATS expect a dedicated skills section."})

    education = sections.get("education", [])
    if not education:
        issues.append({"severity": "warning", "field": "sections.education", "message": "Education section is empty."})

    certs = sections.get("certs", [])
    if not certs:
        issues.append({"severity": "info", "field": "sections.certs", "message": "No certifications listed. Add relevant certs if you hold them."})

    score = max(0, 100 - len([i for i in issues if i["severity"] == "error"]) * 15 - len([i for i in issues if i["severity"] == "warning"]) * 5)

    return JSONResponse({
        "score": score,
        "max_score": 100,
        "config_key": config_key,
        "issues": issues,
        "recommendations": [
            "Submit the DOCX version to ATS forms; use the PDF for human reviewers.",
            "Use standard section headers: Summary, Skills, Work Experience, Education, Certifications.",
            "Keep dates in 'Month YYYY – Present' format consistently.",
            "List skills as bare comma-separated tokens in a dedicated Skills section.",
        ],
    })


def _default_role_line(K, config_key):
    jc = K.get("JOB_CURRENT", {})
    role = jc.get("role", "Security Professional")
    if config_key == "technical":
        return f"{role} · Detection · Automation"
    if config_key == "customer_facing":
        return f"{role} · Solutions Engineering"
    return f"{role} · Strategy · Risk · Compliance"


def _default_subject(K, config_key):
    jc = K.get("JOB_CURRENT", {})
    return jc.get("role", config_key.replace("_", " ").title())


def _safe_name(name):
    return re.sub(r"[^a-zA-Z0-9]+", "_", name).strip("_").lower() or "resume"

# ---------------------------------------------------------------------------
# LLM-powered job-description optimizer
# ---------------------------------------------------------------------------

API_PORT = int(os.environ.get("API_PORT", "8003"))

# Default provider settings (used when the frontend has not sent overrides).
DEFAULT_LLM_SETTINGS = {
    "provider": os.environ.get("LLM_PROVIDER", "ollama"),
    "base_url": os.environ.get("LLM_BASE_URL") or os.environ.get("OLLAMA_URL", "http://host.docker.internal:11434"),
    "api_key": os.environ.get("LLM_API_KEY", ""),
    "model": os.environ.get("LLM_MODEL") or os.environ.get("OLLAMA_MODEL", "llama3.2"),
    "temperature": float(os.environ.get("LLM_TEMPERATURE", "0.4")),
    "timeout": int(os.environ.get("LLM_TIMEOUT", "120")),
}


def _resolve_llm_settings(overrides: Optional[dict] = None) -> dict:
    """Merge env defaults with per-request overrides from the frontend."""
    settings = dict(DEFAULT_LLM_SETTINGS)
    if overrides:
        for key in ("provider", "base_url", "api_key", "model", "temperature", "timeout", "deployment", "api_version"):
            if overrides.get(key) is not None:
                settings[key] = overrides[key]
        # Coerce numeric fields
        try:
            settings["temperature"] = float(settings["temperature"])
        except (TypeError, ValueError):
            settings["temperature"] = 0.4
        try:
            settings["timeout"] = int(settings["timeout"])
        except (TypeError, ValueError):
            settings["timeout"] = 120
    return settings


def _extract_json(text: str) -> dict:
    """Best-effort extract a JSON object from markdown-fenced LLM output."""
    if not text:
        raise ValueError("LLM returned empty response")
    text = text.strip()
    # Strip markdown code fences if present.
    if text.startswith("```"):
        lines = text.splitlines()
        if lines[0].strip().startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    # Find the first top-level JSON object.
    start = text.find("{")
    if start == -1:
        raise ValueError("No JSON object found in LLM response")
    # Track brace depth to find the matching close brace.
    depth = 0
    end = None
    in_string = False
    escape = False
    for i, ch in enumerate(text[start:], start=start):
        if in_string:
            if escape:
                escape = False
                continue
            if ch == "\\":
                escape = True
                continue
            if ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                end = i + 1
                break
    if end is None:
        raise ValueError("Unbalanced braces in LLM response")
    return json.loads(text[start:end])


def _llm_chat(messages, settings: Optional[dict] = None):
    """Call the configured LLM provider and return parsed JSON."""
    s = _resolve_llm_settings(settings)

    # Ollama uses /api/chat and does not support response_format; everyone else
    # in our provider registry uses the OpenAI-compatible /chat/completions path
    # and can accept response_format for JSON mode.
    extra = {}
    if (s.get("provider") or "ollama").lower() != "ollama":
        extra["response_format"] = {"type": "json_object"}

    try:
        from llm_providers import llm_chat as provider_chat
        response = provider_chat(messages, settings=s, **extra)
        return _extract_json(response.content)
    except requests.exceptions.ConnectionError as e:
        raise HTTPException(status_code=503, detail=f"Cannot reach LLM at {s.get('base_url')}: {e}")
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=502, detail=f"Invalid JSON from LLM: {e}")
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"LLM request failed: {e}")


def _build_optimizer_prompt(profile_data, job_description, config_key, mode="question", previous_suggestions=None, answers=None):
    # Normalize jobs as list.
    jobs_raw = profile_data.get("jobs", {})
    if isinstance(jobs_raw, dict):
        jobs = []
        for key in ("current", "previous", "early"):
            if jobs_raw.get(key):
                jobs.append(jobs_raw[key])
    else:
        jobs = jobs_raw

    # Build a compact job listing with available bullet keys.
    job_text = []
    for i, job in enumerate(jobs):
        bullets = {k: v for k, v in job.items() if k not in ("role", "company", "dates") and isinstance(v, str)}
        job_text.append({
            "index": i,
            "role": job.get("role", ""),
            "company": job.get("company", ""),
            "dates": job.get("dates", ""),
            "available_bullet_keys": list(bullets.keys()),
            "available_bullets": bullets,
        })

    skills = profile_data.get("skills", {})
    sections = profile_data.get("sections", {})

    previous_text = ""
    if previous_suggestions:
        previous_text = f"""
Previous suggestion (to refine based on the user's answers):
{json.dumps(previous_suggestions, indent=2)}

User's answers to your previous questions:
{json.dumps(answers or {}, indent=2)}
"""

    if mode == "apply":
        return _build_apply_mode_prompt(
            job_description=job_description,
            config_key=config_key,
            profile_data=profile_data,
            jobs=jobs,
            job_text=job_text,
            skills=skills,
            sections=sections,
            previous_text=previous_text,
        )
    return _build_question_mode_prompt(
        job_description=job_description,
        config_key=config_key,
        profile_data=profile_data,
        jobs=jobs,
        job_text=job_text,
        skills=skills,
        sections=sections,
        previous_text=previous_text,
    )


def _base_rules():
    return textwrap.dedent("""\
        No-AI-slop rules:
        - Do not use vague praise: "seasoned", "extensive", "proven track record of excellence", "passionate", "driven".
        - Do not write generic filler: "with a strong commitment to security" or "leveraging best practices".
        - Quantify where possible. If a number is not in the profile, ask for it (question mode) or omit it (apply mode).
        - Mirror exact job-posting terminology only if the candidate actually has that experience.
        - Keep summaries to 2-3 sentences; lead with role-relevant evidence.

        ATS-aware rules:
        - Prefer standard section labels in reasoning: Summary, Skills, Work Experience, Education, Certifications.
        - Recommend dates in "Month YYYY – Present" format.
        - Recommend a dedicated Skills section with bare comma-separated tokens.
        - Avoid suggesting decorative Unicode, multi-column layouts, or tables.
        - The resume already uses a clean single-column design with vector decorations, so the DOCX export will be ATS-safe.
    """)


def _shared_schema():
    return textwrap.dedent("""\
        {
          "summary": "A tailored 2-3 sentence summary. Use active voice, specific verbs, and concrete scope. No unsupported superlatives.",
          "role_line": "A concise positioning line like 'VP of Security Engineering · Strategy · Risk'",
          "subject": "PDF metadata subject, e.g. 'VP of Security Engineering'",
          "current_bullet_keys": ["key1", "key2", ...],
          "previous_bullet_keys": ["key1", "key2", ...],
          "skill_order": ["leadership", "security", ...],
          "rewritten_jobs": [
            {
              "index": 0,
              "rewritten_bullets": {"key1": "Rewritten bullet text", "key2": "..."}
            }
          ],
          "notes": "Brief reasoning for the choices, including ATS considerations."
        }
    """)


def _build_question_mode_prompt(job_description, config_key, profile_data, jobs, job_text, skills, sections, previous_text):
    schema = _shared_schema().rstrip()
    schema = schema[:-1] + ',\n  "questions": [\n    {\n      "id": "question_id",\n      "text": "A specific clarifying question that would help improve the match. Ask about post-2023 updates, quantified impact, relevant tools, team size, scope, or anything missing from the profile that the job posting cares about."\n    }\n  ]\n}'

    return textwrap.dedent(f"""\
        You are an expert resume strategist helping a senior information security professional tailor their resume to a specific job posting.

        Job posting:
        {job_description}

        Resume target config: {config_key}

        Current profile:
        Name: {profile_data.get("contact", {}).get("name", "")}
        Current role: {jobs[0].get("role", "") if jobs else ""}
        Current company: {jobs[0].get("company", "") if jobs else ""}

        Jobs:
        {json.dumps(job_text, indent=2)}

        Skills categories:
        {json.dumps(skills, indent=2)}

        Existing summary:
        {sections.get("summary", "")}

        Certifications:
        {json.dumps(sections.get("certs", []), indent=2)}

        Education:
        {json.dumps(sections.get("education", []), indent=2)}

        Other highlights:
        {json.dumps(sections.get("highlights", []), indent=2)}

        {previous_text}

        Instructions:
        1. Analyze the job posting and identify the top priorities, keywords, and required experiences.
        2. Return a JSON object with the following schema:
           {schema}
        3. Only use bullet keys that exist in the job's available_bullet_keys. If a job has no useful bullets for this role, return an empty list for that job.
        4. skill_order must only include keys from the skills categories provided.
        5. rewritten_jobs should rewrite bullet text to better match job-posting keywords while remaining truthful. Only include jobs where rewriting adds value.
        6. If the profile already looks strong for the role, questions may be empty. Otherwise ask 2-4 targeted questions.
        7. Do not invent facts. Use the existing bullets as source material and only sharpen phrasing.
        8. The Certifications and Education sections above are part of the candidate's profile. Do not report them as missing if they are populated.

        {_base_rules()}

        Return only the JSON object.
    """)


def _build_apply_mode_prompt(job_description, config_key, profile_data, jobs, job_text, skills, sections, previous_text):
    schema = _shared_schema().rstrip()
    schema = schema[:-1] + ',\n  "skill_rewrites": {"category_name": "rewritten comma-separated skills string"},\n  "questions": []\n}'

    return textwrap.dedent(f"""\
        You are an expert resume strategist and ATS optimizer. Your ONLY goal is to rewrite the candidate's profile so it passes ATS filters and wins a human interview for the job posting below.

        Job posting:
        {job_description}

        Resume target config: {config_key}

        Current profile:
        Name: {profile_data.get("contact", {}).get("name", "")}
        Current role: {jobs[0].get("role", "") if jobs else ""}
        Current company: {jobs[0].get("company", "") if jobs else ""}

        Jobs:
        {json.dumps(job_text, indent=2)}

        Skills categories:
        {json.dumps(skills, indent=2)}

        Existing summary:
        {sections.get("summary", "")}

        Certifications:
        {json.dumps(sections.get("certs", []), indent=2)}

        Education:
        {json.dumps(sections.get("education", []), indent=2)}

        Other highlights:
        {json.dumps(sections.get("highlights", []), indent=2)}

        {previous_text}

        Instructions:
        1. Extract the hard requirements, preferred skills, and repeated keywords from the job posting.
        2. Return a JSON object with the following schema:
           {schema}
        3. Rewrite the summary to open with the exact job-posting keywords the candidate can truthfully claim, framed around evidence from the profile. No vague praise.
        4. Rewrite every job bullet to lead with a relevant keyword from the posting. Only claim what the profile already contains; do not invent companies, tools, or outcomes.
        5. Rewrite skills strings (skill_rewrites) so each category foregrounds the keywords from the posting that the candidate actually has. Use bare comma-separated tokens.
        6. Pick current_bullet_keys and previous_bullet_keys that best match the posting. You may add rewritten bullets for keys that exist in the job's available_bullet_keys. Empty any bullet that is not relevant.
        7. skill_order must only include keys from the skills categories provided. Order by relevance to the posting.
        8. Return an empty questions array. Do not ask the user anything in this mode.
        9. In notes, include: (a) the top ATS keywords you targeted, (b) any gaps that still remain and whether the user should fill them manually.
        10. The Certifications and Education sections above are part of the candidate's profile. Do not report them as missing if they are populated. Only report a certification gap if the job posting explicitly requires a certification the candidate does not have.

        {_base_rules()}

        Return only the JSON object.
    """)


def _validate_suggestions(profile_data, suggestions):
    """Sanitize LLM output against the actual profile to avoid invalid keys."""
    jobs_raw = profile_data.get("jobs", {})
    if isinstance(jobs_raw, dict):
        jobs = []
        for key in ("current", "previous", "early"):
            if jobs_raw.get(key):
                jobs.append(jobs_raw[key])
    else:
        jobs = jobs_raw

    valid_skills = set(profile_data.get("skills", {}).keys())
    skill_order = [s for s in suggestions.get("skill_order", []) if s in valid_skills]

    skill_rewrites = {}
    raw_rewrites = suggestions.get("skill_rewrites", {})
    if isinstance(raw_rewrites, dict):
        for key, value in raw_rewrites.items():
            if key in valid_skills:
                skill_rewrites[key] = (value or "").strip()

    def valid_keys_for_job(idx):
        if idx >= len(jobs):
            return set()
        return {k for k, v in jobs[idx].items() if k not in ("role", "company", "dates") and isinstance(v, str)}

    current_valid = valid_keys_for_job(0)
    previous_valid = valid_keys_for_job(1)

    current_bullet_keys = [k for k in suggestions.get("current_bullet_keys", []) if k in current_valid]
    previous_bullet_keys = [k for k in suggestions.get("previous_bullet_keys", []) if k in previous_valid]

    rewritten_jobs = []
    for rw in suggestions.get("rewritten_jobs", []):
        idx = rw.get("index", 0)
        valid = valid_keys_for_job(idx)
        filtered = {k: v for k, v in rw.get("rewritten_bullets", {}).items() if k in valid}
        if filtered:
            rewritten_jobs.append({"index": idx, "rewritten_bullets": filtered})

    return {
        "summary": (suggestions.get("summary") or "").strip(),
        "role_line": (suggestions.get("role_line") or "").strip(),
        "subject": (suggestions.get("subject") or "").strip(),
        "current_bullet_keys": current_bullet_keys,
        "previous_bullet_keys": previous_bullet_keys,
        "skill_order": skill_order,
        "skill_rewrites": skill_rewrites,
        "rewritten_jobs": rewritten_jobs,
        "questions": suggestions.get("questions", []),
        "notes": (suggestions.get("notes") or "").strip(),
    }


@app.post("/api/optimize")
def api_optimize(payload: dict):
    """Tailor a resume to a job description using an LLM.

    Body:
    {
      "profile": { ...profile JSON... },
      "job_description": "Full job posting text...",
      "config_key": "executive",
      "mode": "question" | "apply",
      "previous_suggestions": { ...optional, from prior round... },
      "answers": { "question_id": "answer", ... }
    }

    Returns:
    {
      "suggestions": { summary, role_line, subject, current_bullet_keys, previous_bullet_keys, skill_order, skill_rewrites, rewritten_jobs, questions, notes },
      "questions": [...]
    }
    """
    profile_data = payload.get("profile")
    job_description = payload.get("job_description", "").strip()
    config_key = payload.get("config_key", "executive")
    mode = payload.get("mode", "question")
    previous_suggestions = payload.get("previous_suggestions")
    answers = payload.get("answers")
    llm_settings = payload.get("llm_settings")

    if not profile_data:
        raise HTTPException(status_code=400, detail="profile is required")
    if not job_description:
        raise HTTPException(status_code=400, detail="job_description is required")
    if mode not in ("question", "apply"):
        raise HTTPException(status_code=400, detail="mode must be 'question' or 'apply'")

    prompt = _build_optimizer_prompt(profile_data, job_description, config_key, mode, previous_suggestions, answers)
    messages = [
        {"role": "system", "content": "You are a concise, truthful resume strategist. Return only valid JSON."},
        {"role": "user", "content": prompt},
    ]

    raw = _llm_chat(messages, settings=llm_settings)
    suggestions = _validate_suggestions(profile_data, raw)

    return JSONResponse({
        "suggestions": suggestions,
        "questions": suggestions["questions"],
        "config_key": config_key,
    })


@app.get("/api/optimize/status")
def api_optimize_status_get():
    return _api_optimize_status({})


@app.post("/api/optimize/status")
def api_optimize_status_post(payload: dict):
    return _api_optimize_status(payload or {})


def _api_optimize_status(overrides: dict):
    """Check whether the configured LLM endpoint is reachable."""
    s = _resolve_llm_settings(overrides)
    base_url = s.get("base_url", "")
    try:
        from llm_providers import get_provider
        provider = get_provider(s)
        models = provider.list_models()
        return {
            "configured": True,
            "base_url": base_url,
            "model": s.get("model"),
            "provider": s.get("provider"),
            "reachable": True,
            "models": models,
        }
    except Exception as e:
        return {
            "configured": bool(base_url),
            "base_url": base_url,
            "model": s.get("model"),
            "provider": s.get("provider"),
            "reachable": False,
            "error": str(e),
        }


@app.post("/api/optimize/ping")
def api_optimize_ping(payload: dict):
    """Send a tiny chat request to verify the configured model actually responds.

    Body: { "llm_settings": { ... } }
    Returns: { "reachable": bool, "model", "provider", "response_preview", "error" }
    """
    settings = payload.get("llm_settings") or {}
    s = _resolve_llm_settings(settings)
    try:
        from llm_providers import llm_chat
        response = llm_chat(
            [
                {"role": "system", "content": "You are a concise connection test. Reply with exactly the word 'pong'."},
                {"role": "user", "content": "ping"},
            ],
            settings=s,
        )
        content = (response.content or "").strip()
        return {
            "reachable": True,
            "model": s.get("model"),
            "provider": s.get("provider"),
            "base_url": s.get("base_url"),
            "response_preview": content[:120],
        }
    except Exception as e:
        return {
            "reachable": False,
            "model": s.get("model"),
            "provider": s.get("provider"),
            "base_url": s.get("base_url"),
            "error": str(e),
        }


@app.post("/api/models")
def api_models(payload: dict):
    """List available models from the LLM endpoint described in the payload.

    Body:
    {
      "provider": "ollama",
      "base_url": "http://blubox:11434",
      "api_key": ""
    }
    """
    settings = payload or {}
    try:
        from llm_providers import get_provider
        provider = get_provider(settings)
        models = provider.list_models()
        return JSONResponse({
            "provider": settings.get("provider") or DEFAULT_LLM_SETTINGS["provider"],
            "base_url": provider.base_url,
            "models": models,
        })
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Could not list models: {e}")


# ---------------------------------------------------------------------------
# LinkedIn PDF import (manual upload of LinkedIn "Save to PDF" export)
# ---------------------------------------------------------------------------

@app.post("/api/import/resume-pdf")
def api_import_resume_pdf(file: UploadFile = File(...)):
    """Extract raw text from any resume PDF to seed the profile editor."""
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are accepted")

    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        tmp.write(file.file.read())
        tmp_path = tmp.name

    try:
        text = _pdf_to_text(tmp_path)
    finally:
        try:
            os.remove(tmp_path)
        except OSError:
            pass

    return JSONResponse({
        "filename": file.filename,
        "text": text,
        "note": "Paste relevant sections into the profile editor. PDF text extraction preserves paragraphs but may lose formatting; review and restructure bullets manually.",
    })


@app.post("/api/import/linkedin-pdf")
def api_import_linkedin_pdf(file: UploadFile = File(...)):
    """Extract raw text from a LinkedIn 'Save to PDF' profile export."""
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are accepted")

    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        tmp.write(file.file.read())
        tmp_path = tmp.name

    try:
        text = _pdf_to_text(tmp_path)
    finally:
        try:
            os.remove(tmp_path)
        except OSError:
            pass

    return JSONResponse({
        "filename": file.filename,
        "text": text,
        "note": "Paste relevant sections into the profile editor; LinkedIn PDFs do not include bullet descriptions.",
    })


@app.get("/api/linkedin/config")
def api_linkedin_config():
    """Return whether LinkedIn OAuth is configured on the backend."""
    return JSONResponse({
        "configured": bool(LINKEDIN_CLIENT_ID and LINKEDIN_CLIENT_SECRET),
        "redirect_uri": LINKEDIN_REDIRECT_URI,
    })


# ---------------------------------------------------------------------------
# AI-powered PDF import: parse resume / LinkedIn PDFs into structured profile
# ---------------------------------------------------------------------------

@app.post("/api/import/ai-parse")
def api_import_ai_parse(
    files: list[UploadFile] = File(...),
    llm_settings: Optional[str] = Form(None),
):
    """Upload one or more PDFs and ask the LLM to build a structured profile.

    Form fields:
      files[]        : PDF files
      llm_settings   : JSON string with optional provider/model override

    Returns:
      {
        "texts": [{"filename": "...", "text": "..."}],
        "profile": { ...structured profile JSON... },
        "questions": [{"id": "...", "text": "..."}],
        "notes": "..."
      }
    """
    if not files:
        raise HTTPException(status_code=400, detail="At least one PDF file is required")

    settings = _parse_llm_settings_form(llm_settings)
    texts = _extract_texts_from_files(files)
    if not texts:
        raise HTTPException(status_code=400, detail="No readable text found in uploaded PDFs")

    prompt = _build_ai_import_prompt(texts)
    messages = [
        {"role": "system", "content": "You are an expert resume parser and ATS-aware profile builder. Return only valid JSON."},
        {"role": "user", "content": prompt},
    ]

    raw = _llm_chat(messages, settings=settings)
    parsed = _validate_ai_import_profile(raw)
    return JSONResponse({
        "texts": texts,
        "profile": parsed["profile"],
        "questions": parsed.get("questions", []),
        "notes": parsed.get("notes", ""),
    })


@app.post("/api/import/ai-parse/refine")
def api_import_ai_parse_refine(payload: dict):
    """Refine an AI-parsed profile based on the user's answers.

    Body:
    {
      "texts": [{"filename": "...", "text": "..."}],
      "profile": { ...current draft profile... },
      "questions": [{"id": "...", "text": "..."}],
      "answers": { "question_id": "answer", ... },
      "llm_settings": { ... }
    }

    Returns the same shape as /api/import/ai-parse.
    """
    texts = payload.get("texts") or []
    profile_data = payload.get("profile")
    questions = payload.get("questions") or []
    answers = payload.get("answers") or {}
    llm_settings = payload.get("llm_settings")

    if not profile_data:
        raise HTTPException(status_code=400, detail="profile is required")
    if not texts:
        raise HTTPException(status_code=400, detail="texts are required")

    prompt = _build_ai_import_refine_prompt(texts, profile_data, questions, answers)
    messages = [
        {"role": "system", "content": "You are an expert resume parser and ATS-aware profile builder. Return only valid JSON."},
        {"role": "user", "content": prompt},
    ]

    raw = _llm_chat(messages, settings=llm_settings)
    parsed = _validate_ai_import_profile(raw)
    return JSONResponse({
        "texts": texts,
        "profile": parsed["profile"],
        "questions": parsed.get("questions", []),
        "notes": parsed.get("notes", ""),
    })


def _parse_llm_settings_form(value: Optional[str]) -> dict:
    if not value:
        return {}
    try:
        return json.loads(value)
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=400, detail=f"llm_settings is not valid JSON: {e}")


def _extract_texts_from_files(files: list[UploadFile]) -> list[dict]:
    """Extract text from uploaded PDFs, returning a list of {filename, text}."""
    out = []
    for file in files:
        if not file.filename.lower().endswith(".pdf"):
            continue
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            tmp.write(file.file.read())
            tmp_path = tmp.name
        try:
            text = _pdf_to_text(tmp_path)
            if text.strip():
                out.append({"filename": file.filename, "text": text})
        finally:
            try:
                os.remove(tmp_path)
            except OSError:
                pass
    return out


def _ai_import_schema():
    return textwrap.dedent("""\
        {
          "profile": {
            "contact": {
              "name": "Full name",
              "phone": "Phone number",
              "email": "Email address",
              "location": "City, State or Remote",
              "linkedin": "linkedin.com/in/... or blank",
              "github": "github.com/... or blank"
            },
            "jobs": [
              {
                "role": "Job title",
                "company": "Company name",
                "dates": "Month YYYY – Month YYYY or Present",
                "bullet_key_1": "Achievement or responsibility sentence",
                "bullet_key_2": "Another sentence"
              }
            ],
            "skills": {
              "leadership": "comma-separated leadership skills",
              "security": "comma-separated security skills",
              "risk_compliance": "comma-separated risk/compliance skills",
              "cloud_infra": "comma-separated cloud/infrastructure skills",
              "networking": "comma-separated networking skills",
              "scripting": "comma-separated scripting/programming skills",
              "customer_facing": "comma-separated customer-facing skills"
            },
            "sections": {
              "summary": "2-3 sentence professional summary",
              "highlights": ["highlight 1", "highlight 2"],
              "education": [["Degree", "School", "Dates"]],
              "certs": ["Certification 1"],
              "awards": ["Award 1"],
              "community": ["Community item 1"],
              "homelab": ["Homelab item 1"],
              "research": {"main": "Research description"},
              "project": {"name": "Project name", "desc": "One-line description"},
              "publication": {"title": "", "tag": "", "desc": "", "url": ""},
              "speaking": {"lead": "Speaker, Conference (Year):", "detail": "Talk title"}
            }
          },
          "questions": [
            {"id": "q1", "text": "Specific clarifying question about missing or ambiguous information"}
          ],
          "notes": "Brief notes on what was parsed and any ATS considerations."
        }
    """)


def _ai_import_rules():
    return textwrap.dedent("""\
        Parsing rules:
        - Extract exact facts only. Do not invent companies, titles, dates, degrees, or skills.
        - If the same fact appears in multiple files, prefer the most detailed or most recent source.
        - If facts conflict, note the conflict in notes and choose the source that looks like the primary resume.
        - Convert MM/YYYY dates to "Month YYYY". Use "Present" for current roles.
        - Use bare comma-separated skill tokens (no sentences).
        - For work bullets, use short, active-voice sentences. Quantify where the source provides numbers.

        No-AI-slop rules:
        - No vague praise: "seasoned", "extensive", "proven track record", "passionate", "driven".
        - No filler: "leveraging best practices", "with a strong commitment to".
        - Keep the summary to 2-3 evidence-based sentences.

        ATS-aware rules:
        - Standard section labels: Summary, Skills, Work Experience, Education, Certifications.
        - Use Month YYYY – Present dates.
        - Skills must be bare comma-separated tokens.
        - Avoid tables, multi-column layouts, and decorative Unicode.
    """)


def _build_ai_import_prompt(texts: list[dict]) -> str:
    source_text = "\n\n".join(
        f"--- FILE: {t['filename']} ---\n{t['text'][:8000]}"
        for t in texts
    )
    return textwrap.dedent(f"""\
        You are parsing uploaded resume/LinkedIn PDF(s) into a structured profile for a resume builder.

        Source text:
        {source_text}

        Return ONLY a JSON object matching this schema:
        {_ai_import_schema()}

        {_ai_import_rules()}

        Instructions:
        1. Populate as many fields as the source text supports. Leave fields blank if the source does not contain the information.
        2. Ask 2-5 targeted questions for missing, ambiguous, or conflicting information that would meaningfully improve the resume.
        3. If the source has no bullet-style descriptions for a job, infer 2-4 concise bullets from the role/company context, but mark them as inferred in notes.
        4. Return only the JSON object.
    """)


def _build_ai_import_refine_prompt(texts: list[dict], profile_data: dict, questions: list, answers: dict) -> str:
    source_text = "\n\n".join(
        f"--- FILE: {t['filename']} ---\n{t['text'][:4000]}"
        for t in texts
    )
    return textwrap.dedent(f"""\
        You previously parsed these PDFs into a profile draft. Revise the profile using the user's answers.

        Source text:
        {source_text}

        Current profile draft:
        {json.dumps(profile_data, indent=2)}

        Previous questions and user's answers:
        {json.dumps([{"question": q, "answer": answers.get(q.get("id"), "")} for q in questions], indent=2)}

        Return ONLY a JSON object matching this schema:
        {_ai_import_schema()}

        {_ai_import_rules()}

        Instructions:
        1. Update the profile draft with the user's answers.
        2. Preserve facts already present unless the user explicitly corrects them.
        3. Ask any remaining clarifying questions (2-5 total). If nothing remains unclear, return an empty questions array.
        4. Return only the JSON object.
    """)


def _validate_ai_import_profile(raw: dict) -> dict:
    """Sanitize LLM output so it matches the frontend profile schema."""
    if not isinstance(raw, dict):
        raise HTTPException(status_code=502, detail="LLM returned non-object JSON")

    parsed = raw.get("profile", raw)
    if not isinstance(parsed, dict):
        raise HTTPException(status_code=502, detail="LLM returned profile that is not an object")

    # Ensure top-level keys exist with correct types.
    contact = parsed.get("contact", {})
    if not isinstance(contact, dict):
        contact = {}

    jobs = parsed.get("jobs", [])
    if not isinstance(jobs, list):
        jobs = []
    jobs = [j for j in jobs if isinstance(j, dict)]
    if not jobs:
        jobs = [{"role": "", "company": "", "dates": ""}]

    skills = parsed.get("skills", {})
    if not isinstance(skills, dict):
        skills = {}

    sections = parsed.get("sections", {})
    if not isinstance(sections, dict):
        sections = {}

    # Normalize arrays.
    def norm_list(key, default=None):
        val = sections.get(key, default)
        if not isinstance(val, list):
            return default if default is not None else []
        return val

    def norm_edu():
        val = sections.get("education", [["", "", ""]])
        if not isinstance(val, list):
            return [["", "", ""]]
        return [list(row) if isinstance(row, (list, tuple)) else ["", "", str(row)] for row in val]

    research = sections.get("research", {})
    if isinstance(research, str):
        research = {"main": research}
    elif not isinstance(research, dict):
        research = {"main": ""}

    project = sections.get("project", {})
    if isinstance(project, str):
        project = {"name": "", "desc": project}
    elif not isinstance(project, dict):
        project = {"name": "", "desc": ""}

    publication = sections.get("publication", {})
    if isinstance(publication, str):
        publication = {"title": "", "tag": "", "desc": publication, "url": ""}
    elif not isinstance(publication, dict):
        publication = {"title": "", "tag": "", "desc": "", "url": ""}

    speaking = sections.get("speaking", {})
    if isinstance(speaking, str):
        speaking = {"lead": "", "detail": speaking}
    elif not isinstance(speaking, dict):
        speaking = {"lead": "", "detail": ""}

    clean_profile = {
        "contact": {
            "name": str(contact.get("name", "")).strip(),
            "phone": str(contact.get("phone", "")).strip(),
            "email": str(contact.get("email", "")).strip(),
            "location": str(contact.get("location", "")).strip(),
            "linkedin": str(contact.get("linkedin", "")).strip(),
            "github": str(contact.get("github", "")).strip(),
        },
        "jobs": jobs,
        "skills": {k: str(v or "").strip() for k, v in skills.items()},
        "sections": {
            "summary": str(sections.get("summary", "")).strip(),
            "highlights": norm_list("highlights", [""]),
            "education": norm_edu(),
            "certs": norm_list("certs", [""]),
            "awards": norm_list("awards", [""]),
            "community": norm_list("community", [""]),
            "homelab": norm_list("homelab", [""]),
            "research": research,
            "project": project,
            "publication": publication,
            "speaking": speaking,
        },
    }

    questions = raw.get("questions", [])
    if not isinstance(questions, list):
        questions = []
    questions = [q for q in questions if isinstance(q, dict) and q.get("text")]

    return {
        "profile": clean_profile,
        "questions": questions,
        "notes": str(raw.get("notes", "")).strip(),
    }


def _pdf_to_text(path):
    try:
        result = subprocess.run(
            ["pdftotext", "-layout", path, "-"],
            capture_output=True, text=True, check=True,
        )
        return result.stdout
    except FileNotFoundError:
        raise HTTPException(status_code=500, detail="pdftotext not found. Install poppler-utils (brew install poppler).")
    except subprocess.CalledProcessError as e:
        raise HTTPException(status_code=500, detail=f"PDF extraction failed: {e.stderr}")

# ---------------------------------------------------------------------------
# LinkedIn OAuth (basic profile seed only)
# ---------------------------------------------------------------------------

LINKEDIN_CLIENT_ID = os.environ.get("LINKEDIN_CLIENT_ID", "")
LINKEDIN_CLIENT_SECRET = os.environ.get("LINKEDIN_CLIENT_SECRET", "")
LINKEDIN_REDIRECT_URI = os.environ.get("LINKEDIN_REDIRECT_URI", f"http://localhost:{API_PORT}/api/linkedin/callback")


@app.get("/api/linkedin/auth")
def api_linkedin_auth():
    """Redirect the user to LinkedIn's OAuth consent screen."""
    if not LINKEDIN_CLIENT_ID:
        raise HTTPException(
            status_code=500,
            detail="LINKEDIN_CLIENT_ID not configured. Set it in your environment.",
        )
    params = urllib.parse.urlencode({
        "response_type": "code",
        "client_id": LINKEDIN_CLIENT_ID,
        "redirect_uri": LINKEDIN_REDIRECT_URI,
        "state": "resume_kit_local",
        "scope": "openid profile email",
    })
    url = f"https://www.linkedin.com/oauth/v2/authorization?{params}"
    return JSONResponse({"authorization_url": url})


@app.get("/api/linkedin/callback")
def api_linkedin_callback(code: str, state: Optional[str] = None):
    """Exchange LinkedIn OAuth code for a token and fetch basic profile info."""
    if not LINKEDIN_CLIENT_ID or not LINKEDIN_CLIENT_SECRET:
        raise HTTPException(
            status_code=500,
            detail="LINKEDIN_CLIENT_ID and LINKEDIN_CLIENT_SECRET not configured.",
        )

    token_data = urllib.parse.urlencode({
        "grant_type": "authorization_code",
        "code": code,
        "client_id": LINKEDIN_CLIENT_ID,
        "client_secret": LINKEDIN_CLIENT_SECRET,
        "redirect_uri": LINKEDIN_REDIRECT_URI,
    }).encode("utf-8")

    token_req = urllib.request.Request(
        "https://www.linkedin.com/oauth/v2/accessToken",
        data=token_data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )

    try:
        with urllib.request.urlopen(token_req) as resp:
            token_resp = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to exchange LinkedIn code: {e}")

    access_token = token_resp.get("access_token")
    if not access_token:
        raise HTTPException(status_code=400, detail=f"No access_token in LinkedIn response: {token_resp}")

    user_req = urllib.request.Request(
        "https://api.linkedin.com/v2/userinfo",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    try:
        with urllib.request.urlopen(user_req) as resp:
            user = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to fetch LinkedIn profile: {e}")

    # Normalize to our contact schema.
    seed = {
        "name": user.get("name", ""),
        "email": user.get("email", ""),
        "location": "",
        "linkedin": user.get("vanity_name") or user.get("sub", ""),
        "github": "",
        "phone": "",
    }

    return JSONResponse({
        "contact_seed": seed,
        "raw": user,
        "note": "OAuth provides name, email, and vanity name only. Work history must be entered manually or imported via LinkedIn PDF export.",
    })


@app.get("/api/health")
def api_health():
    return {"status": "ok"}


@app.get("/api/profile/default")
def api_profile_default():
    """Return the default profile.yaml as JSON for the frontend to load."""
    default_path = os.environ.get("RESUME_PROFILE") or profile._DEFAULT_PROFILE
    if os.path.exists(default_path):
        data = profile._load_yaml(default_path)
    else:
        data = {}
    return JSONResponse({"profile": data, "source": default_path})


# Mount the built React frontend as the last step so all /api/* routes remain
# reachable. With html=True, unknown paths fall back to index.html for the
# single-page React app.
if os.path.isdir(_WEB_DIST):
    app.mount("/", StaticFiles(directory=_WEB_DIST, html=True), name="static")


if __name__ == "__main__":
    import uvicorn
    reload = os.environ.get("RELOAD", "false").lower() in ("1", "true", "yes")
    uvicorn.run("api:app", host="0.0.0.0", port=API_PORT, reload=reload)
