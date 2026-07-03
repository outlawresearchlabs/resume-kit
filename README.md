# Resume Kit

Terminal-themed resume kit with AI-powered PDF import, ATS optimizer, and ATS-safe DOCX export.

## Quick start (Docker — easiest)

```bash
docker compose up --build
# → http://localhost:8003
```

Open http://localhost:8003 in your browser, edit your profile, choose a resume target, and click **Generate PDF** or **Generate ATS DOCX**.

Generated files land in the `./out` folder on the host.

### AI import from PDF(s)

In the **AI Import from PDF(s)** panel, select one or more PDFs (current resume, LinkedIn “Save to PDF” export, or both) and click **Parse with AI**. The LLM extracts a structured profile, shows you a preview, asks verification questions, and lets you refine before applying it to the editor.

### Optional: LLM targeting in Docker

The container defaults to Ollama running on the Docker host. Start Ollama first:

```bash
ollama pull llama3.2
ollama serve
```

Then run the app:

```bash
docker compose up
```

For a remote OpenAI-compatible endpoint, edit `docker-compose.yml` or pass environment variables:

```bash
# OpenAI
LLM_PROVIDER=openai LLM_BASE_URL=https://api.openai.com/v1 LLM_API_KEY=sk-... LLM_MODEL=gpt-4o-mini docker compose up

# Anthropic
LLM_PROVIDER=anthropic LLM_API_KEY=sk-ant-... LLM_MODEL=claude-sonnet-4-7 docker compose up

# Azure OpenAI
LLM_PROVIDER=azure AZURE_OPENAI_ENDPOINT=https://... AZURE_OPENAI_API_KEY=... AZURE_OPENAI_DEPLOYMENT=gpt-4o docker compose up

# Ollama on another host (e.g. blubox)
LLM_PROVIDER=ollama LLM_BASE_URL=http://blubox:11434/v1 LLM_MODEL=kimi-k2.7-code:cloud docker compose up
```

If your Ollama host is not `localhost` or `host.docker.internal`, add it to `docker-compose.yml` under `extra_hosts` or pass `--add-host=blubox:<ip>` at runtime.

## Quick start (local dev)

1. **Install Python dependencies**

   ```bash
   python3 -m pip install -r requirements.txt
   ```

2. **Install frontend dependencies**

   ```bash
   cd frontend
   npm install
   ```

3. **Run the backend**

   ```bash
   cd backend
   python api.py
   # → http://localhost:8003
   ```

4. **Run the frontend** (in a new terminal)

   ```bash
   cd frontend
   npm run dev
   # → http://localhost:5173
   ```

5. Open http://localhost:5173, edit your profile, choose a resume target, and generate.

## Repository layout

```
backend/
  api.py                 ← FastAPI backend: /api/build, /api/optimize, /api/import/*
  config_templates.py    ← Resume targets: executive / technical / customer-facing
  configs/               ← Legacy standalone CLI config examples
  content.py             ← Sample placeholder facts for legacy configs
  docx_builder.py        ← ATS-safe DOCX generator
  llm_providers.py       ← Pluggable LLM provider abstraction
  profile.py             ← Profile loader for YAML/JSON
  profile.yaml           ← Sample default profile
  terminal_engine.py     ← ReportLab PDF rendering engine

frontend/
  src/
    App.jsx              ← React profile editor and optimizer UI
    App.css              ← Dark terminal theme
    api.js               ← API client helpers
    main.jsx             ← React entry point
  index.html
  package.json
  vite.config.js

docs/
  terminal_elegance.md   ← Design spec (palette, typography, spacing)

fonts/                   ← SIL-licensed JetBrains Mono + Instrument Sans
out/                     ← Generated PDF/DOCX output
Dockerfile
docker-compose.yml
requirements.txt
```

## Edit your profile

The web app stores your draft in the browser's `localStorage` and can load the sample `backend/profile.yaml` with the **"Load default profile"** button.

You can also edit `backend/profile.yaml` directly. The schema supports:

- `contact` — name, phone, email, location, LinkedIn, GitHub
- `jobs` — a list of roles, each with `role`, `company`, `dates`, and any number of bullet keys. Config templates pick which bullet keys to show.
- `skills` — category-name → comma-separated skills string
- `sections` — summary, highlights, education, certs, awards, community, home lab, research, project, publication, speaking, references

## Resume targets (config templates)

Three built-in templates select different bullets and skill order:

| Key | Best for | Default role line |
| --- | --- | --- |
| `executive` | VP / CISO / leadership | `VP of Security Engineer · Strategy · Risk · Compliance` |
| `technical` | Hands-on engineering | `Security Engineer · Detection · Automation` |
| `customer_facing` | Solutions / consulting | `Security Professional · Solutions Engineering` |

Override the role line, subject, summary, and bullet selections in the web app.

## LinkedIn import

- **OAuth (basic fields):** click "Connect LinkedIn" in the web app. This seeds name, email, and LinkedIn vanity name. You must create a LinkedIn app and set `LINKEDIN_CLIENT_ID` and `LINKEDIN_CLIENT_SECRET` environment variables.
- **AI PDF import:** download your profile as PDF from LinkedIn (Profile → More → Save to PDF), then upload it in the **AI Import from PDF(s)** panel. The LLM parses it into structured profile fields and asks you to verify.

### Setting up LinkedIn OAuth

1. Create an app at https://developer.linkedin.com/.
2. Add `http://localhost:8003/api/linkedin/callback` as a redirect URI.
3. Request the **Sign In with LinkedIn using OpenID Connect** product.
4. Run the backend with credentials:

   ```bash
   cd backend
   LINKEDIN_CLIENT_ID=xxx LINKEDIN_CLIENT_SECRET=yyy python api.py
   ```

## Targeting a job posting with the LLM optimizer

Paste a job description into the **"Target this role"** panel and click **Analyze job description**. The LLM returns a tailored summary, suggested role line, skill order, and rewritten bullets. If it needs more context, it asks 2–4 clarifying questions; answer them and click **Refine with answers** for a second pass. Click **Apply suggestions to profile** when you're happy.

You can also use **Optimize for this job (ATS + interview)** to run the apply-mode optimizer in one click.

The optimizer follows the resume-kit "no AI slop" rules:

- No vague praise ("seasoned", "proven track record", "passionate").
- No unsupported superlatives; it quantifies or asks for the number.
- Only uses bullet keys and skill categories that already exist in your profile.

Configure the model with environment variables:

```bash
cd backend
LLM_BASE_URL=http://localhost:11434/v1 LLM_MODEL=llama3.2 python api.py
# or any OpenAI-compatible endpoint:
LLM_BASE_URL=https://api.openai.com/v1 LLM_API_KEY=sk-... LLM_MODEL=gpt-4o-mini python api.py
```

## ATS / DOCX export

Many applicant tracking systems parse DOCX more reliably than PDF, so the app also generates a stripped-down **ATS DOCX**:

- Single-column layout.
- Standard section headers: Summary, Skills, Work Experience, Education, Certifications.
- Dates normalized to `Month YYYY – Present`.
- Skills as bare comma-separated tokens.
- No tables, graphics, or decorative Unicode.

Click **Check ATS compatibility** in the web app for a quick report, then **Generate ATS DOCX** to download the submission file. Use the PDF for human reviewers and the DOCX for ATS forms.

## What the design guarantees

- **ATS-safe:** every decorative mark (chevrons, nodes, cursor, traces) is vector-drawn, never a text glyph, so text extraction is surgically clean. Section headers extract as standard keywords (SUMMARY, SKILLS, WORK EXPERIENCE…). Fonts are embedded.
- **No orphans:** jobs keep their header and all bullets together; section headers never strand at a page bottom; page totals are computed in a two-pass build.
- **Clickable contact:** phone, email, and profile links in the status bar are live hyperlinks.
- The aesthetic is documented in `docs/terminal_elegance.md`.

## Legacy CLI usage

The original Python configs in `backend/configs/` still work and are useful for scripting or batch generation:

```bash
cd backend/configs
python config_technical.py         # → ../../out/Example_Technical_Resume.pdf
python config_customer_facing.py   # → ../../out/Example_Customer_Facing_Resume.pdf
```

These import from `backend/content.py` and `backend/terminal_engine.py`.

## License

The kit code: free to use, modify, and share. Fonts are included under the SIL Open Font License (see `fonts/*-OFL.txt`).
