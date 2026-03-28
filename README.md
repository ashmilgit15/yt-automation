# YouTube Automation Factory

Full-stack video automation platform with a Next.js command dashboard, FastAPI API, Celery workers, Redis queueing, PostgreSQL persistence, and FFmpeg-based composition.

## Stack

- `frontend/`: Next.js App Router dashboard with live job polling and quality-gate review UI
- `backend/`: FastAPI API, SQLAlchemy models, Celery tasks, AI/media services, and YouTube publisher
- `docker-compose.yml`: Postgres, Redis, FastAPI, Celery, and Next.js services

## Build Notes

- The first Docker build can take several minutes because FFmpeg and Python AI/media dependencies must be installed.
- Local builds currently use the lighter Edge TTS fallback by default. The app still works without installing Kokoro inside Docker.

## Quick Start

1. Copy `.env.example` to `.env` and fill in your API keys.
2. Change `OPERATOR_PASSWORD` and `SESSION_SECRET` to strong values before exposing the app anywhere beyond your local machine.
3. In Google Cloud, create an OAuth Web Application client and add `http://localhost:8000/api/v1/integrations/youtube/oauth/callback` as an authorized redirect URI.
4. Download that OAuth client file and save it as `secrets/client_secrets.json`.
5. Optionally add a loopable music track at `backend/assets/background-music.mp3`.
6. Run `docker compose up --build` from the project root.
7. Open `http://localhost:3000`, sign in through the operator access panel, then use the YouTube connection panel and click `Connect YouTube` once.

## Key API Routes

- `POST /api/v1/jobs`
- `GET /api/v1/jobs`
- `GET /api/v1/jobs/{job_id}`
- `POST /api/v1/jobs/{job_id}/review`
- `GET /api/v1/auth/session`
- `POST /api/v1/auth/login`
- `POST /api/v1/auth/logout`
- `POST /api/v1/webhook/n8n`
- `POST /api/v1/integrations/youtube/credentials`
- `GET /api/v1/integrations/youtube/status`
- `GET /api/v1/integrations/youtube/oauth/start`

## Validation Completed

- `python -m compileall backend`
- `npm run build` inside `frontend/`
