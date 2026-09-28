# Assurley — full-stack website and claims workflow

This repository implements the approved Assurley experience with the uploaded Assurley artwork, a responsive public website, customer claim submission/tracking, and an authenticated claims-operations workspace. It contains no seeded claims, fabricated testimonials, invented performance statistics, or embedded admin credential.

## What is included

- Responsive marketing website using the finalized Assurley teal / mint / ivory visual system
- Purposeful workflow motion with `prefers-reduced-motion` support
- Guided customer claim submission with validation and multi-file upload
- Claim tracking protected by claim ID + submission email
- Operations access protected by a server-side secret
- Searchable claims table, review drawer, human approval/rejection, and settlement completion
- Tesseract OCR for uploaded image documents
- Honest `Not evaluated` risk state until a validated risk model/rule engine is connected
- Timeline/audit events for submission, document handling, decision, and settlement
- Responsive desktop/tablet/mobile layouts and keyboard-friendly controls
- SEO description, OpenGraph metadata, favicon, semantic landmarks, focus states, and skip navigation

## Architecture

- Frontend: dependency-free HTML/CSS/JavaScript, so the production build has no client-framework supply-chain/runtime dependency
- Backend: FastAPI + SQLAlchemy
- Authoritative production database: PostgreSQL through `DATABASE_URL`
- Local development database: SQLite only as a zero-infrastructure fallback
- Document storage: configurable persistent filesystem mount through `UPLOAD_DIR`; swap this adapter for the already-approved object storage service in cloud deployment
- OCR: real Tesseract processing for image uploads
- Human-controlled final decisions

## Run locally

### API

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export ADMIN_KEY='replace-with-a-long-random-secret'
uvicorn app.main:app --reload --port 8000
```

### Website

```bash
cd frontend
npm run build
npm run preview
```

Open `http://localhost:4173`.

For development without building:

```bash
npm run dev
```

## Frontend deployment configuration

Edit `frontend/src/config.js` before the production build, or overwrite the generated `dist/config.js` during deployment:

```js
window.ASSURLEY_API_URL = 'https://api.your-domain.example';
window.ASSURLEY_INSTAGRAM_URL = 'https://www.instagram.com/YOUR_OFFICIAL_HANDLE/';
```

The Instagram destination is intentionally not invented; the footer shows a non-clickable pending state until the official profile URL is provided.

## Backend production configuration

Set at minimum:

- `DATABASE_URL=postgresql+psycopg://...`
- `ADMIN_KEY` to a long random secret held in a secret manager
- `ALLOWED_ORIGINS` to the deployed frontend origin(s)
- `UPLOAD_DIR` to persistent storage, or replace the storage adapter with S3-compatible/object storage
- `MAX_UPLOAD_MB` as required by policy
- `ENABLE_DOCS=false` if public API documentation should be disabled

## Production notes

The repository preserves the approved PostgreSQL direction and human decision control. The local SQLite fallback is not the target production database. A validated ML/risk model and external LLM integration are deliberately not fabricated in this build; the UI exposes the absence of a configured result rather than displaying made-up AI scores.
