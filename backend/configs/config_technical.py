"""
config_technical.py — example: a technical / engineering-leaning resume.

Uses the sample profile in content.py. Copy this file, rename it for your
target role, change the picks, and replace content.py with your own facts.

Run:  python config_technical.py     →  ../out/Example_Technical_Resume.pdf
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import terminal_engine as E
import content as K

ROLE_LINE = "Security Engineer · Detection · Automation"
SUBJECT = "Security Engineer"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "out", "Example_Technical_Resume.pdf")

# Pick bullets for the current job by key — this is the technical variant:
CURRENT_PICK = ['detections', 'investigate', 'automation', 'mentor']
# Skill categories to show, in order (order signals positioning — lead with your target):
SKILL_PICK = ['security', 'scripting', 'cloud_infra', 'networking', 'leadership', 'customer_facing']


def render(r):
    r.masthead()

    r.section("Summary", min_after=60)
    r.para("Two or three sentences that position you for THIS role. Lead with your "
           "strongest evidence, keep it honest, and end with what you're aiming at.")

    r.section_block("Selected Highlights", lambda m=False: _many(r, K.HIGHLIGHTS, m))

    r.section("Skills", min_after=80)
    for cat in SKILL_PICK:
        r.skill(cat, K.SKILLS[cat])

    cur = [K.JOB_CURRENT[k] for k in CURRENT_PICK]
    r.section("Work Experience", min_after=16 + sum(r.bullet_h(b) for b in cur))
    r.job(K.JOB_CURRENT['role'], K.JOB_CURRENT['company'], K.JOB_CURRENT['dates'], cur); r.gap()
    r.job(K.JOB_PREV['role'], K.JOB_PREV['company'], K.JOB_PREV['dates'],
          [K.JOB_PREV['hunt'], K.JOB_PREV['siem_build'], K.JOB_PREV['initiative'], K.JOB_PREV['monitor']]); r.gap()
    r.job(K.JOB_EARLY['role'], K.JOB_EARLY['company'], K.JOB_EARLY['dates'], [K.JOB_EARLY['compact']])

    r.section_block("Independent Security Research", lambda m=False: _many(r, [K.RESEARCH['main']], m))
    r.section_block("Home Lab", lambda m=False: _many(r, K.HOMELAB, m))
    r.section_block("Projects", lambda m=False: _para(r, K.PROJECT, m))
    r.section_block("Education", lambda m=False: _edu(r, m))
    r.section_block("Certifications", lambda m=False: _many(r, K.CERTS, m))
    r.section_block("Speaking", lambda m=False: _speaking(r, m))
    r.section_block("Community", lambda m=False: _many(r, K.COMMUNITY, m))
    r.section_block("Publications", lambda m=False: _pub(r, m))
    r.section_block("References", lambda m=False: _refs(r, m))
    r.endfile()


# ---- small adapters between content shapes and the engine (reused by every config) ----
def _many(r, items, measure):
    h = sum(r.bullet_h(i) for i in items)
    if not measure:
        for i in items: r.bullet(i)
    return h

def _para(r, text, measure):
    h = r.para_h(text)
    if not measure: r.para(text)
    return h

def _edu(r, measure):
    h = (E.LH * 2 + 5) * len(K.EDUCATION)
    if not measure:
        for d, s, dt in K.EDUCATION: r.edu(d, s, dt)
    return h

def _speaking(r, measure):
    h = E.LH + 2
    if not measure: r.speaking_line(*K.SPEAKING)
    return h

def _pub(r, measure):
    h = E.LH * 3 + 4
    if not measure: r.publication(*K.PUBLICATION)
    return h

def _refs(r, measure):
    h = max(len(K.REFS_LEFT), len(K.REFS_RIGHT)) * (E.LH * 3 + 4)
    if not measure: r.refs_two_col(K.REFS_LEFT, K.REFS_RIGHT)
    return h


if __name__ == "__main__":
    n = E.build(os.path.abspath(OUT), render, K.CONTACT, ROLE_LINE, SUBJECT)
    print(f"Built {os.path.basename(OUT)} — {n} pages")
