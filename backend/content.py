"""
content.py — sample placeholder resume facts.

This file exists only as a backwards-compatible example for the legacy CLI configs
in configs/. The web app stores and manages its own profile in browser storage.
All values below are fictional example data and should be replaced by the user.
"""

# ---------------------------------------------------------------- identity
CONTACT = {
    'name': 'Jordan Reyes',
    'prompt': 'jordan@reyes:~$',
    'phone': '+1 555-010-4242',
    'email': 'jordan@example.com',
    'location': 'Springfield, USA',
    'linkedin': 'linkedin.com/in/example',
    'github': 'github.com/example',
    'footer': 'jordan reyes · security engineer',
    'cont_header': 'JORDAN REYES · +1 555-010-4242 · jordan@example.com',
    'bar': '+1 555-010-4242 · jordan@example.com · Springfield, USA · linkedin.com/in/example · github.com/example',
    'links': [
        ('tel:+15550104242', '+1 555-010-4242'),
        ('mailto:jordan@example.com', 'jordan@example.com'),
        ('https://linkedin.com/in/example', 'linkedin.com/in/example'),
        ('https://github.com/example', 'github.com/example'),
    ],
}

# ---------------------------------------------------------------- jobs
JOB_CURRENT = {
    'role': 'Security Engineer',
    'company': 'Example Corp',
    'dates': '2023 - Current',
    'detections': 'Designed and tuned detection logic in the SIEM, cutting false positives while expanding coverage for current attacker techniques.',
    'investigate': 'Investigated security events across network, endpoint, and log sources, identifying indicators of compromise and recommending containment steps.',
    'automation': 'Built internal automation that triages routine alerts, adopted as the default workflow across two teams.',
    'mentor': 'Mentor junior engineers and lead internal knowledge-sharing sessions.',
    'community': 'Represent the company at industry events and meetups.',
}

JOB_PREV = {
    'role': 'SOC Analyst',
    'company': 'Sample Managed Security',
    'dates': '2021 - 2023',
    'monitor': 'Monitored and investigated alerts across a 24/7 SOC serving managed-services customers.',
    'hunt': 'Ran hypothesis-driven threat hunts and documented findings against MITRE ATT&CK.',
    'siem_build': 'Helped build and maintain open source SIEM/SOAR tooling for internal use.',
    'initiative': 'Independently identified a critical misconfiguration outside assigned duties and coordinated the fix across teams.',
}

JOB_EARLY = {
    'role': 'IT Support Specialist',
    'company': 'Demo Managed Services',
    'dates': '2019 - 2021',
    'compact': 'Delivered managed IT and security services for small-business customers; implemented hardening standards and designed backup and network architecture.',
}

# ---------------------------------------------------------------- skills
SKILLS = {
    'leadership': 'Security Strategy, Risk Management, Executive Communication, Team Leadership, Program Management',
    'security': 'Vulnerability Management, SIEM, EDR, Threat Detection, MITRE ATT&CK, Penetration Testing',
    'risk_compliance': 'Risk Assessment, Compliance, Security Policies, Standards & Guidelines',
    'cloud_infra': 'AWS, Azure, Microsoft 365, Docker, Infrastructure as Code, Network Architecture',
    'networking': 'TCP/IP, DNS, Firewalls, VPN',
    'scripting': 'Python, Bash, PowerShell',
    'customer_facing': 'Executive Presentations, Technical-to-Business Translation, Stakeholder Communication',
}

HIGHLIGHTS = [
    'Led detection engineering improvements across a multi-cloud environment',
    'Experienced in vulnerability management and compliance alignment',
    'Built automation to reduce alert triage overhead',
]

EDUCATION = [
    ('B.S. Computer Science', 'Example University', '2019'),
]

CERTS = [
    'CompTIA Security+',
]

SPEAKING = {}
COMMUNITY = []
HOMELAB = []
RESEARCH = {}
PROJECT = {}
PUBLICATION = {}
REFS_LEFT = []
REFS_RIGHT = []
