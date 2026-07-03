# syntax=docker/dockerfile:1

# ---------------------------------------------------------------------------
# Stage 1: build the React frontend
# ---------------------------------------------------------------------------
FROM node:20-alpine AS frontend
WORKDIR /app/web
COPY web/package*.json ./
RUN npm ci
COPY web/ ./
RUN npm run build

# ---------------------------------------------------------------------------
# Stage 2: Python runtime with built frontend baked in
# ---------------------------------------------------------------------------
FROM python:3.11-slim
WORKDIR /app

# Install pdftotext for LinkedIn / resume PDF text extraction.
RUN apt-get update && apt-get install -y --no-install-recommends poppler-utils \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend code, profile data, fonts, and the built frontend
COPY *.py ./
COPY *.yaml ./
COPY fonts ./fonts
COPY --from=frontend /app/web/dist ./web/dist

# Generated resumes are written here; mount a volume if you want persistence
RUN mkdir -p /app/out
VOLUME ["/app/out"]

EXPOSE 8003
ENV API_PORT=8003 \
    RELOAD=false \
    LLM_PROVIDER=ollama \
    LLM_BASE_URL=http://blubox:11434/v1 \
    LLM_API_KEY= \
    LLM_MODEL=llama3.2 \
    LLM_TEMPERATURE=0.4 \
    LLM_TIMEOUT=120 \
    OLLAMA_URL=http://blubox:11434 \
    OLLAMA_MODEL=llama3.2

CMD ["python", "api.py"]
