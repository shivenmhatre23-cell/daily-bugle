# AGENTS.md — Contributor Guide for Autonomous Agents

## 1. Overview & Operating Principles
- You are an autonomous full-stack AI engineer contributing to the **Daily Bugle News Engine**.
- Write clean, modular, minimal-diff code. Avoid sweeping refactors or unnecessary churn.
- Maintain the strict separation of concerns across the 4 core domains (Backend/DB, AI/ML, Frontend, and Data/Integration).
- Do not introduce heavy external dependencies (e.g., node frameworks, extra heavy ML packages) without explicit instruction.

## 2. Environment & Tooling
- **Backend Runtime:** Python 3.10+
- **Backend Framework:** FastAPI, Uvicorn, SQLAlchemy
- **Database:** SQLite (`daily_bugle.db`) / PostgreSQL compatible
- **AI/ML Layer:** Lightweight heuristics, spatial/temporal formulas, and mockable LLM hooks
- **Frontend:** Vanilla HTML5, JavaScript (ES6+), Tailwind CSS (CDN), Leaflet.js

## 3. Essential Commands & Verification
- **Install Dependencies:** `pip install -r requirements.txt`
- **Run Backend Server:** `uvicorn backend.app:app --host 0.0.0.0 --port 8000 --reload`
- **Seed Demo Data:** `python scripts/seed.py`
- **Frontend Server (if serving via Python):** `python -m http.server 3000 --directory frontend`
- **Verify Lint / Syntax:** `python -m py_compile backend/*.py ai/*.py scripts/*.py`

## 4. Repository Directory Map
- `/backend`:
  - `app.py`: FastAPI application, CORS setup, and REST API endpoints (`/api/reports`, `/api/feed`).
  - `database.py`: SQLAlchemy engine, session maker, and ORM models (`Source`, `Cluster`, `Report`).
  - `clustering.py`: Spatio-temporal and lexical matching logic (`haversine_distance`, `find_matching_cluster`).
- `/ai`:
  - `credibility.py`: Category tagging, spam detection heuristics, urgency and plausibility scoring.
  - `reputation.py`: Trust calculation formula, source diversity weighting, penalty adjustments.
- `/frontend`:
  - `index.html`: Main dashboard UI (Citizen Ingestion, Live Feed, Filters).
  - `app.js`: Client-side state handling, polling (`/api/feed`), and form submissions.
  - `styles.css`: Base layout styles and utilities.
- `/data`:
  - `seed_reports.json`: Test dataset with verified clusters, uncorroborated alerts, and spam bursts.
- `/scripts`:
  - `seed.py`: Automated ingestion runner for demo bootstrap.

## 5. Architectural & Domain Rules
- **No Direct DB Mutations in AI Layer:** The AI scoring functions in `/ai` must remain pure functions taking objects/strings and returning scores or dictionaries. They must not query or write to the database directly.
- **Explainable Scores:** Never hardcode black-box percentage labels. Every score returned to the user or investigator must include an explainability breakdown array (`signal`, `delta`).
- **Cluster Centroid Math:** When reports are merged into an existing cluster, the centroid latitude and longitude must update incrementally, and `last_updated` must be updated to the current UTC timestamp.
- **Frontend Decoupling:** The frontend communicates with the backend solely via the `/api` HTTP endpoints. Do not attempt to read local SQLite files from JavaScript.

## 6. Prohibitions & Guardrails
- **Do not commit API keys or production secrets** to any file.
- **Do not delete or overwrite the seed dataset** (`data/seed_reports.json`) with arbitrary mock data; append only if adding test scenarios.
- **Do not replace Vanilla JS with a heavy frontend framework** (React, Vue, Angular) unless explicitly directed by the project lead.
- **Do not introduce database schema breaking changes** without updating both `backend/database.py` and the serialization logic in `backend/app.py`.

## 7. Definition of Done (Self-Verification Loop)
Before concluding any modification or feature addition:
1. Confirm all Python files pass syntax checks: `python -m py_compile backend/app.py ai/credibility.py`.
2. Ensure the backend boots cleanly on port 8000 without missing module errors.
3. Validate that running `python scripts/seed.py` successfully posts events to `/api/reports` and populates the database.
4. Ensure the frontend feed updates and displays status badges (`VERIFIED`, `FLAGGED`, `NOISE`) with working explainability popups.
