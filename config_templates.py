"""
config_templates.py — pre-built resume configs rendered against a profile.

Each function receives the loaded profile (as a K-like dict) and a
TerminalResume renderer (r) and draws one complete resume.
"""
import terminal_engine as E


def _pick(job, keys):
    """Return bullets from a job dict in key order, skipping missing keys."""
    return [job[k] for k in keys if k in job and job[k]]


def _compact_bullets(job):
    """Return a compact summary of a job for space-constrained sections."""
    if job.get("compact"):
        return [job["compact"]]
    # Otherwise grab the first two non-meta string keys.
    bullets = []
    for k, v in job.items():
        if k in ("role", "company", "dates") or not isinstance(v, str):
            continue
        bullets.append(v)
        if len(bullets) >= 2:
            break
    return bullets


def _render_jobs(r, jobs, current_pick=None, previous_pick=None, max_full=2):
    """Render jobs: first `max_full` get full bullet picks, remainder compact."""
    if not jobs:
        return

    total_h = sum(
        16 + sum(r.bullet_h(b) for b in _bullets_for_render(jobs[i], current_pick if i == 0 else previous_pick if i == 1 else None))
        for i in range(min(len(jobs), max_full))
    )
    total_h += sum(
        16 + sum(r.bullet_h(b) for b in _compact_bullets(jobs[i]))
        for i in range(max_full, len(jobs))
    )

    r.section("Work Experience", min_after=total_h)

    for idx, job in enumerate(jobs):
        if idx < max_full:
            picks = current_pick if idx == 0 else (previous_pick if idx == 1 else None)
            bullets = _pick(job, picks) if picks else _compact_bullets(job)
        else:
            bullets = _compact_bullets(job)
        r.job(job.get("role", ""), job.get("company", ""), job.get("dates", ""), bullets)
        if idx < len(jobs) - 1:
            r.gap()


def _bullets_for_render(job, picks):
    if picks:
        return _pick(job, picks)
    return _compact_bullets(job)


def _many(r, items):
    for i in items:
        r.bullet(i)


def _edu(r, items):
    for degree, school, dates in items:
        r.edu(degree, school, dates)


# ---------------------------------------------------------------------------
# Public templates
# ---------------------------------------------------------------------------

def technical(K, r, role_line=None, subject=None, summary=None,
              current_pick=None, previous_pick=None):
    """Hands-on / engineering-leaning resume."""
    r.masthead()

    r.section("Summary", min_after=60)
    r.para(summary or (
        "Hands-on security engineer with deep experience in vulnerability management, "
        "detection engineering, and enterprise security operations. Strong track record of "
        "building scalable programs, leading cross-functional remediation, and translating "
        "risk into clear action for technical and executive audiences."
    ))

    if K.get("HIGHLIGHTS"):
        r.section_block("Selected Highlights", lambda m=False: _highlights(K, r, m))

    r.section("Skills", min_after=80)
    skill_order = ["security", "scripting", "cloud_infra", "networking", "leadership", "customer_facing"]
    for cat in skill_order:
        if cat in K.get("SKILLS", {}):
            r.skill(cat, K["SKILLS"][cat])

    _render_jobs(
        r, K.get("JOBS", []),
        current_pick=current_pick or ["detections", "investigate", "automation", "mentor"],
        previous_pick=previous_pick or ["monitor", "hunt", "siem_build", "initiative"],
        max_full=2,
    )

    _optional_sections(K, r)
    r.endfile()


def customer_facing(K, r, role_line=None, subject=None, summary=None,
                    current_pick=None, previous_pick=None):
    """Solutions / customer-facing / consulting-leaning resume."""
    r.masthead()

    r.section("Summary", min_after=60)
    r.para(summary or (
        "Security professional who bridges deep technical expertise with executive and "
        "customer-facing communication. Proven in running product demos, scoping solutions, "
        "driving adoption, and leading cross-functional security programs for global enterprises."
    ))

    r.section("Skills", min_after=80)
    skill_order = ["customer_facing", "security", "cloud_infra", "networking", "os", "scripting"]
    for cat in skill_order:
        if cat in K.get("SKILLS", {}):
            r.skill(cat, K["SKILLS"][cat])

    _render_jobs(
        r, K.get("JOBS", []),
        current_pick=current_pick or ["customer_facing", "mentor", "community", "detections", "investigate"],
        previous_pick=previous_pick or ["monitor", "siem_build", "initiative"],
        max_full=2,
    )

    _optional_sections(K, r)
    r.endfile()


def executive(K, r, role_line=None, subject=None, summary=None,
              current_pick=None, previous_pick=None):
    """Leadership / VP / CISO-leaning resume."""
    r.masthead()

    r.section("Summary", min_after=60)
    r.para(summary or (
        "Seasoned information security leader with a track record of designing and operating "
        "enterprise security programs for global organizations. Combines strategic vision, "
        "policy and risk management, vulnerability and compliance disciplines, and the ability "
        "to align security with business outcomes and executive stakeholders."
    ))

    if K.get("HIGHLIGHTS"):
        r.section_block("Selected Highlights", lambda m=False: _highlights(K, r, m))

    r.section("Skills", min_after=80)
    skill_order = ["leadership", "security", "risk_compliance", "cloud_infra", "scripting", "customer_facing"]
    for cat in skill_order:
        if cat in K.get("SKILLS", {}):
            r.skill(cat, K["SKILLS"][cat])

    _render_jobs(
        r, K.get("JOBS", []),
        current_pick=current_pick or ["vm_strategy", "assessments", "scanning", "collaboration", "mentor"],
        previous_pick=previous_pick or ["liaison", "vuln_id", "remediation", "tracking", "communication"],
        max_full=2,
    )

    _optional_sections(K, r)
    r.endfile()


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------

TEMPLATES = {
    "technical": technical,
    "customer_facing": customer_facing,
    "executive": executive,
}


def render_template(key, K, r, **overrides):
    """Dispatch to a template and pass through overrides."""
    if key not in TEMPLATES:
        raise ValueError(f"Unknown template: {key}. Choose from {list(TEMPLATES)}")
    return TEMPLATES[key](K, r, **overrides)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _highlights(K, r, measure):
    items = K.get("HIGHLIGHTS", [])
    h = sum(r.bullet_h(i) for i in items)
    if not measure:
        _many(r, items)
    return h


def _optional_sections(K, r):
    research = K.get("RESEARCH", {})
    if research and research.get("main"):
        r.section_block("Independent Security Research", lambda m=False: _research(K, r, m))

    homelab = K.get("HOMELAB", [])
    if homelab:
        r.section_block("Home Lab", lambda m=False: _many_simple(K, r, "HOMELAB", m))

    project = K.get("PROJECT")
    if project:
        r.section_block("Projects", lambda m=False: _project(K, r, m))

    education = K.get("EDUCATION", [])
    if education:
        r.section_block("Education", lambda m=False: _edu_section(K, r, m))

    certs = K.get("CERTS", [])
    if certs:
        r.section_block("Certifications", lambda m=False: _many_simple(K, r, "CERTS", m))

    awards = K.get("AWARDS", [])
    if awards:
        r.section_block("Awards", lambda m=False: _many_simple(K, r, "AWARDS", m))

    speaking = K.get("SPEAKING")
    if speaking:
        r.section_block("Speaking", lambda m=False: _speaking(K, r, m))

    community = K.get("COMMUNITY", [])
    if community:
        r.section_block("Community", lambda m=False: _many_simple(K, r, "COMMUNITY", m))

    publication = K.get("PUBLICATION")
    if publication:
        r.section_block("Publications", lambda m=False: _publication(K, r, m))

    if K.get("REFS_LEFT") or K.get("REFS_RIGHT"):
        r.section_block("References", lambda m=False: _refs(K, K.get("REFS_LEFT", []), K.get("REFS_RIGHT", [])) or 0)


def _research(K, r, measure):
    items = [K["RESEARCH"]["main"]]
    h = sum(r.bullet_h(i) for i in items)
    if not measure:
        _many(r, items)
    return h


def _many_simple(K, r, key, measure):
    items = K.get(key, [])
    h = sum(r.bullet_h(i) for i in items)
    if not measure:
        _many(r, items)
    return h


def _project(K, r, measure):
    text = K.get("PROJECT", "")
    h = r.para_h(text)
    if not measure:
        r.para(text)
    return h


def _edu_section(K, r, measure):
    items = K.get("EDUCATION", [])
    h = (E.LH * 2 + 5) * len(items)
    if not measure:
        _edu(r, items)
    return h


def _speaking(K, r, measure):
    lead, detail = K["SPEAKING"]
    h = E.LH + 2
    if not measure:
        r.speaking_line(lead, detail)
    return h


def _publication(K, r, measure):
    title, tag, desc, url = K["PUBLICATION"]
    h = E.LH * 3 + 4
    if not measure:
        r.publication(title, tag, desc, url)
    return h


def _refs(r, left, right):
    r.refs_two_col(left, right)
