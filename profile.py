"""
profile.py — load a YAML/JSON fact database and expose it like content.py.

This is the data layer for the resume kit. Pass an explicit path or set the
RESUME_PROFILE environment variable. If no profile file is found, the loader
returns empty defaults so the module can still be imported.

Exposes the same names configs expect: CONTACT, JOB_CURRENT, JOB_PREV,
JOB_EARLY, SKILLS, HIGHLIGHTS, EDUCATION, CERTS, SPEAKING, COMMUNITY,
HOMELAB, RESEARCH, PROJECT, PUBLICATION, REFS_LEFT, REFS_RIGHT.

The loader also auto-derives the contact prompt, footer, continuation header,
status bar, and clickable links when they are not explicitly provided.
"""
import os
import json

_HERE = os.path.dirname(os.path.abspath(__file__))
_DEFAULT_PROFILE = os.path.join(_HERE, "profile.yaml")


def _load_yaml(path):
    import yaml
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _as_tuples(items):
    """Normalize list-of-dicts or list-of-lists into tuples where needed."""
    if items is None:
        return []
    out = []
    for item in items:
        if isinstance(item, dict):
            out.append(tuple(item.values()))
        else:
            out.append(tuple(item) if isinstance(item, list) else item)
    return out


def _derive_contact(raw):
    """Fill in computed contact fields when omitted."""
    ct = dict(raw)
    name = ct.get("name", "").strip()
    parts = name.lower().split()
    if ct.get("prompt"):
        prompt = ct["prompt"]
    elif len(parts) > 1:
        prompt = f"{parts[0]}@{parts[-1]}:~$"
    elif len(parts) == 1:
        prompt = f"{parts[0]}@resume:~$"
    else:
        prompt = "user@resume:~$"
    phone = ct.get("phone", "")
    email = ct.get("email", "")
    location = ct.get("location", "")
    linkedin = ct.get("linkedin", "")
    github = ct.get("github", "")

    bar_pieces = [p for p in [phone, email, location, linkedin, github] if p]
    bar = ct.get("bar") or " · ".join(bar_pieces)

    footer = ct.get("footer") or (
        f"{name.lower()} · information security professional" if name else "resume"
    )

    cont_header = ct.get("cont_header") or (
        f"{name.upper()} · {phone} · {email}" if name else ""
    )

    links = list(ct.get("links") or [])
    if not links:
        if phone:
            digits = "".join(ch for ch in phone if ch.isdigit())
            if digits:
                tel = f"tel:+1{digits[-10:]}" if len(digits) >= 10 else f"tel:{digits}"
                links.append((tel, phone))
        if email:
            links.append((f"mailto:{email}", email))
        if linkedin:
            url = linkedin if linkedin.startswith(("http://", "https://")) else f"https://{linkedin}"
            links.append((url, linkedin))
        if github:
            url = github if github.startswith(("http://", "https://")) else f"https://{github}"
            links.append((url, github))

    ct.update({
        "prompt": prompt,
        "footer": footer,
        "cont_header": cont_header,
        "bar": bar,
        "links": links,
    })
    return ct


def _load_profile(path=None, data=None):
    """Load profile from file, from explicit dict, or from environment path."""
    if data is not None:
        raw = data
    else:
        path = path or os.environ.get("RESUME_PROFILE") or _DEFAULT_PROFILE
        # If no explicit path was requested and the default file does not exist,
        # return empty defaults so the module can still be imported.
        if not os.path.exists(path):
            raw = {}
        else:
            ext = os.path.splitext(path)[1].lower()
            if ext in (".yaml", ".yml"):
                raw = _load_yaml(path)
            elif ext == ".json":
                raw = _load_json(path)
            else:
                try:
                    raw = _load_yaml(path)
                except Exception:
                    raw = _load_json(path)

    contact = _derive_contact(raw.get("contact", {}))

    jobs_raw = raw.get("jobs", {})
    # Support either a list of jobs or the legacy {current, previous, early} map.
    if isinstance(jobs_raw, list):
        jobs = jobs_raw
    else:
        jobs = []
        for key in ("current", "previous", "early"):
            if jobs_raw.get(key):
                jobs.append(jobs_raw[key])

    sections = raw.get("sections", {})

    def section(key, default=None):
        return sections.get(key, default)

    skills = raw.get("skills", {})

    research = section("research", {})
    if isinstance(research, str):
        research = {"main": research}

    project = section("project")
    if isinstance(project, dict):
        project = f"{project.get('name', '')} - {project.get('desc', '')}".strip(" -")

    publication = None
    publication_raw = section("publication")
    if isinstance(publication_raw, dict):
        publication = (
            publication_raw.get("title", ""),
            str(publication_raw.get("tag", "")),
            publication_raw.get("desc", ""),
            publication_raw.get("url", ""),
        )
    elif isinstance(publication_raw, (list, tuple)) and len(publication_raw) == 4:
        publication = tuple(publication_raw)

    speaking = None
    speaking_raw = section("speaking")
    if isinstance(speaking_raw, dict):
        speaking = (speaking_raw.get("lead", ""), speaking_raw.get("detail", ""))
    elif isinstance(speaking_raw, (list, tuple)) and len(speaking_raw) == 2:
        speaking = tuple(speaking_raw)

    refs = raw.get("references", {})
    refs_left = _as_tuples(refs.get("left", []))
    refs_right = _as_tuples(refs.get("right", []))

    return {
        "CONTACT": contact,
        "JOBS": jobs,
        # Legacy aliases for older configs that import content.py-style names.
        "JOB_CURRENT": jobs[0] if jobs else {},
        "JOB_PREV": jobs[1] if len(jobs) > 1 else {},
        "JOB_EARLY": jobs[2] if len(jobs) > 2 else {},
        "SKILLS": skills,
        "HIGHLIGHTS": section("highlights", []),
        "EDUCATION": _as_tuples(section("education", [])),
        "CERTS": section("certs", []),
        "SPEAKING": speaking,
        "COMMUNITY": section("community", []),
        "HOMELAB": section("homelab", []),
        "RESEARCH": research,
        "PROJECT": project,
        "PUBLICATION": publication,
        "REFS_LEFT": refs_left,
        "REFS_RIGHT": refs_right,
    }


# Expose content.py-compatible module-level names from the default profile.
_VARS = _load_profile()
CONTACT = _VARS["CONTACT"]
JOBS = _VARS["JOBS"]
JOB_CURRENT = _VARS["JOB_CURRENT"]
JOB_PREV = _VARS["JOB_PREV"]
JOB_EARLY = _VARS["JOB_EARLY"]
SKILLS = _VARS["SKILLS"]
HIGHLIGHTS = _VARS["HIGHLIGHTS"]
EDUCATION = _VARS["EDUCATION"]
CERTS = _VARS["CERTS"]
SPEAKING = _VARS["SPEAKING"]
COMMUNITY = _VARS["COMMUNITY"]
HOMELAB = _VARS["HOMELAB"]
RESEARCH = _VARS["RESEARCH"]
PROJECT = _VARS["PROJECT"]
PUBLICATION = _VARS["PUBLICATION"]
REFS_LEFT = _VARS["REFS_LEFT"]
REFS_RIGHT = _VARS["REFS_RIGHT"]


def load(path=None, data=None):
    """Load a fresh profile and return the variable dict."""
    return _load_profile(path=path, data=data)


def reload(path=None, data=None):
    """Reload the module-level profile variables at runtime."""
    global CONTACT, JOBS, JOB_CURRENT, JOB_PREV, JOB_EARLY, SKILLS, HIGHLIGHTS, EDUCATION
    global CERTS, SPEAKING, COMMUNITY, HOMELAB, RESEARCH, PROJECT, PUBLICATION
    global REFS_LEFT, REFS_RIGHT
    v = _load_profile(path=path, data=data)
    CONTACT = v["CONTACT"]
    JOBS = v["JOBS"]
    JOB_CURRENT = v["JOB_CURRENT"]
    JOB_PREV = v["JOB_PREV"]
    JOB_EARLY = v["JOB_EARLY"]
    SKILLS = v["SKILLS"]
    HIGHLIGHTS = v["HIGHLIGHTS"]
    EDUCATION = v["EDUCATION"]
    CERTS = v["CERTS"]
    SPEAKING = v["SPEAKING"]
    COMMUNITY = v["COMMUNITY"]
    HOMELAB = v["HOMELAB"]
    RESEARCH = v["RESEARCH"]
    PROJECT = v["PROJECT"]
    PUBLICATION = v["PUBLICATION"]
    REFS_LEFT = v["REFS_LEFT"]
    REFS_RIGHT = v["REFS_RIGHT"]
