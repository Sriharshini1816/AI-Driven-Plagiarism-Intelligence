# Academic Integrity Review (AIR)

**AI-powered assignment analysis powered by IBM watsonx.ai Granite models.**

> ⚠️ **Disclaimer:** AIR provides *recommendations only*. All final academic misconduct decisions must be made by qualified human instructors following institutional policy. This system cannot and does not determine guilt.

---

## Table of Contents
1. [Features](#features)
2. [Architecture](#architecture)
3. [Quick Start (Local)](#quick-start-local)
4. [AGENT_INSTRUCTIONS — Institutional Customisation](#agent_instructions)
5. [Deployment on IBM Cloud Lite](#deployment-on-ibm-cloud-lite)
6. [Database Schema](#database-schema)
7. [API Reference](#api-reference)
8. [Privacy & Compliance](#privacy--compliance)

---

## Features

| Feature | Description |
|---|---|
| **Semantic Similarity** | TF-IDF cosine similarity against reference corpus; Granite embeddings-ready |
| **Citation Analysis** | APA, MLA, IEEE, Harvard density checking & reference section detection |
| **Style Consistency** | Statistical deviation of sentence length, vocabulary richness, passive voice |
| **AI Pattern Detection** | Granite model flags potential AI-generated text patterns |
| **Explainable Flags** | Every flag includes a plain-language reason and suggested instructor action |
| **Instructor Feedback** | Cleared / Under Review / Referred decisions recorded with audit trail |
| **Dark / Light Mode** | Persisted via `localStorage`; fully responsive Bootstrap 5.3 UI |

---

## Architecture

```
academic-integrity-review/
├── app.py                    ← Flask application + REST API
├── models.py                 ← SQLAlchemy ORM (Submission, AnalysisReport, Flag, InstructorFeedback)
├── modules/
│   ├── watsonx_client.py     ← IBM watsonx.ai Granite integration
│   ├── analyser.py           ← Orchestrates all analysis modules
│   ├── document_parser.py    ← PDF / DOCX / TXT text extraction
│   ├── similarity.py         ← TF-IDF semantic similarity
│   ├── citation_checker.py   ← Citation density & reference detection
│   └── style_analyser.py     ← Writing-style consistency
├── templates/
│   ├── base.html             ← Shared layout + navbar
│   ├── index.html            ← Upload page
│   ├── dashboard.html        ← Instructor dashboard
│   ├── review.html           ← Per-submission review & flags
│   └── 404.html
├── static/
│   ├── css/main.css
│   └── js/{main,upload,dashboard,review}.js
├── .env.template             ← All configuration variables (copy to .env)
├── requirements.txt
├── Procfile                  ← Gunicorn for IBM Cloud / Heroku
├── manifest.yml              ← IBM Cloud Foundry manifest
└── runtime.txt
```

---

## Quick Start (Local)

### Prerequisites
- Python 3.11+
- IBM Cloud account with watsonx.ai service (Lite tier available)

### 1. Clone & install

```bash
cd academic-integrity-review
python -m venv .venv
# Windows:
.venv\Scripts\activate
# Linux/macOS:
source .venv/bin/activate

pip install -r requirements.txt
python -m spacy download en_core_web_sm
```

### 2. Configure credentials

```bash
cp .env.template .env
# Edit .env — add IBM_CLOUD_API_KEY, WATSONX_PROJECT_ID, etc.
```

### 3. Run

```bash
python app.py
# Open http://localhost:5000
```

---

## AGENT_INSTRUCTIONS

All institutional customisation is done via environment variables in `.env`. **No code changes required.**

| Variable | Default | Description |
|---|---|---|
| `IBM_CLOUD_API_KEY` | — | IBM Cloud IAM API key |
| `WATSONX_PROJECT_ID` | — | watsonx.ai project ID |
| `WATSONX_URL` | `https://us-south.ml.cloud.ibm.com` | Regional endpoint |
| `GRANITE_MODEL_ID` | `ibm/granite-13b-instruct-v2` | Granite model to use |
| `WATSONX_MAX_TOKENS` | `1500` | Token budget per API call |
| `SIMILARITY_THRESHOLD` | `0.75` | Cosine similarity flag threshold (0–1) |
| `MIN_CITATION_DENSITY` | `2.5` | Minimum citations per 1000 words |
| `STYLE_DEVIATION_TOLERANCE` | `0.30` | Style consistency deviation (0–1) |
| `REPORT_FORMAT` | `detailed` | `detailed` \| `summary` \| `instructor_only` |
| `PRIVACY_MODE` | `full` | `full` \| `anonymised` \| `hash_only` |
| `INTEGRITY_POLICY_TEXT` | — | Policy text shown to students on upload |
| `FLAGGING_CONFIDENCE` | `medium` | `low` (flag more) \| `medium` \| `high` (flag less) |
| `ENABLE_INSTRUCTOR_FEEDBACK` | `true` | Toggle feedback panel |
| `ENABLE_STYLE_ANALYSIS` | `true` | Toggle style consistency checks |
| `FLASK_SECRET_KEY` | — | **Must be changed** for production |
| `DATABASE_URL` | `sqlite:///academic_integrity.db` | Use PostgreSQL URL in production |
| `MAX_CONTENT_LENGTH` | `16777216` | Max upload size in bytes (default 16 MB) |

---

## Deployment on IBM Cloud Lite

### Prerequisites
- IBM Cloud CLI: https://cloud.ibm.com/docs/cli
- Cloud Foundry plugin: `ibmcloud cf install-plugin`

### Steps

```bash
# 1. Login
ibmcloud login --sso
ibmcloud target --cf

# 2. Set environment variables (never commit .env to git)
ibmcloud cf set-env air-academic-integrity IBM_CLOUD_API_KEY "your_key"
ibmcloud cf set-env air-academic-integrity WATSONX_PROJECT_ID "your_project_id"
ibmcloud cf set-env air-academic-integrity WATSONX_URL "https://us-south.ml.cloud.ibm.com"
ibmcloud cf set-env air-academic-integrity FLASK_SECRET_KEY "$(python -c 'import secrets; print(secrets.token_hex(32))')"
ibmcloud cf set-env air-academic-integrity FLASK_ENV "production"

# 3. Push the application
ibmcloud cf push

# 4. View logs
ibmcloud cf logs air-academic-integrity --recent
```

### IBM Cloud Lite Limits
- **512 MB RAM** — sufficient for the default configuration
- **1 GB disk** — the manifest requests this
- **No persistent disk** — uploads and the SQLite database are ephemeral on CF.
  For production, bind an **IBM Cloudant** or **IBM Databases for PostgreSQL** service
  and set `DATABASE_URL` accordingly.

### Production Database (PostgreSQL)
```bash
# Create an IBM Databases for PostgreSQL Lite instance
ibmcloud resource service-instance-create air-postgres databases-for-postgresql lite us-south

# Get connection string and set it:
ibmcloud cf set-env air-academic-integrity DATABASE_URL "postgresql://user:pass@host:port/db?sslmode=require"
ibmcloud cf restage air-academic-integrity
```

---

## Database Schema

```sql
-- submissions: one row per uploaded assignment
CREATE TABLE submissions (
  id               INTEGER PRIMARY KEY,
  student_name     VARCHAR(200)  NOT NULL,
  student_id       VARCHAR(100)  NOT NULL,
  course_code      VARCHAR(100)  NOT NULL,
  assignment_title VARCHAR(300)  NOT NULL,
  filename         VARCHAR(300)  NOT NULL,   -- server-side path
  original_filename VARCHAR(300) NOT NULL,
  file_type        VARCHAR(20)   NOT NULL,   -- pdf|docx|txt
  word_count       INTEGER       DEFAULT 0,
  submitted_at     DATETIME      NOT NULL,
  status           VARCHAR(30)   DEFAULT 'pending'  -- pending|processing|complete|error
);

-- analysis_reports: one-to-one with submissions
CREATE TABLE analysis_reports (
  id                  INTEGER PRIMARY KEY,
  submission_id       INTEGER UNIQUE REFERENCES submissions(id),
  overall_risk        VARCHAR(20)  DEFAULT 'unknown',   -- low|medium|high
  similarity_score    FLOAT        DEFAULT 0.0,
  citation_score      FLOAT        DEFAULT 0.0,
  style_score         FLOAT        DEFAULT 0.0,
  ai_summary          TEXT         DEFAULT '',
  watsonx_raw_response TEXT        DEFAULT '',
  analysed_at         DATETIME     NOT NULL
);

-- flags: many per submission
CREATE TABLE flags (
  id            INTEGER PRIMARY KEY,
  submission_id INTEGER REFERENCES submissions(id),
  flag_type     VARCHAR(50)  NOT NULL,   -- similarity|citation|style|ai_pattern
  severity      VARCHAR(20)  DEFAULT 'medium',  -- low|medium|high
  passage       TEXT         NOT NULL,
  reason        TEXT         NOT NULL,
  confidence    FLOAT        DEFAULT 0.0,
  start_char    INTEGER      DEFAULT 0,
  end_char      INTEGER      DEFAULT 0,
  reviewed      BOOLEAN      DEFAULT FALSE,
  created_at    DATETIME     NOT NULL
);

-- instructor_feedback: audit trail of instructor decisions
CREATE TABLE instructor_feedback (
  id              INTEGER PRIMARY KEY,
  submission_id   INTEGER REFERENCES submissions(id),
  instructor_name VARCHAR(200) NOT NULL,
  decision        VARCHAR(50)  NOT NULL,   -- cleared|under_review|referred
  notes           TEXT         DEFAULT '',
  created_at      DATETIME     NOT NULL
);
```

---

## API Reference

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/` | Upload page |
| `GET` | `/dashboard` | Instructor dashboard |
| `GET` | `/review/<id>` | Per-submission review |
| `POST` | `/api/submit` | Upload assignment (multipart/form-data) |
| `GET` | `/api/submission/<id>/status` | Polling endpoint |
| `GET` | `/api/submission/<id>/flags` | All flags as JSON |
| `POST` | `/api/submission/<id>/flag/<fid>/review` | Mark flag reviewed |
| `POST` | `/api/submission/<id>/feedback` | Add instructor decision |
| `GET` | `/api/submissions` | List all submissions |
| `DELETE` | `/api/submission/<id>` | Delete submission (GDPR) |

---

## Privacy & Compliance

- **`PRIVACY_MODE=anonymised`** — student names are hidden from the review UI; IDs only
- **`PRIVACY_MODE=hash_only`** — only hashed identifiers displayed
- **DELETE endpoint** — permanently removes all submission data and the uploaded file for GDPR right-to-erasure compliance
- Uploaded files are stored on the local filesystem under `static/uploads/` with UUID-prefixed names
- No student data is sent to IBM watsonx.ai beyond the document text and the flag signals; no PII is included in prompts
