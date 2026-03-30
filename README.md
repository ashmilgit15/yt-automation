# YouTube Automation Factory

Full-stack video automation platform with a Next.js dashboard, FastAPI API, Celery workers, Redis queueing, PostgreSQL persistence, and FFmpeg-based media processing.

> Runtime secrets are intentionally kept out of Git. Keep `.env` and anything inside `secrets/` local-only.

## Table Of Contents

- [What This Project Includes](#what-this-project-includes)
- [Quick Start For Beginners](#quick-start-for-beginners)
- [Step 1: Clone The Repository](#step-1-clone-the-repository)
- [Step 2: Create Your Local Environment File](#step-2-create-your-local-environment-file)
- [Step 3: Add Your Google OAuth File](#step-3-add-your-google-oauth-file)
- [Step 4: Start The App With Docker](#step-4-start-the-app-with-docker)
- [Step 5: Sign In And Use The Dashboard](#step-5-sign-in-and-use-the-dashboard)
- [Environment Variable Guide](#environment-variable-guide)
- [Project Structure](#project-structure)
- [Manual Local Development](#manual-local-development)
- [Troubleshooting](#troubleshooting)
- [Security Notes](#security-notes)

## What This Project Includes

- `frontend/`: Next.js 15 dashboard for creating, reviewing, and monitoring jobs
- `backend/`: FastAPI API, SQLAlchemy models, Celery workers, AI/media services, and YouTube publishing logic
- `docker-compose.yml`: local development stack for Postgres, Redis, API, worker, and frontend
- `secrets/`: local-only folder for Google OAuth files and similar sensitive assets

## Quick Start For Beginners

1. Install `Git` and `Docker Desktop`.
2. Clone this repository.
3. Copy `.env.example` to `.env`.
4. Replace every value that starts with `replace-with-`.
5. Create `secrets/client_secrets.json` from your Google Cloud OAuth download.
6. Run `docker compose up --build`.
7. Open `http://localhost:3000` and sign in with your operator account.

The application now refuses to start if important secrets still contain placeholder values. That is intentional.

## Step 1: Clone The Repository

```bash
git clone https://github.com/ashmilgit15/yt-automation.git
cd yt-automation
```

<details>
<summary>Windows PowerShell note</summary>

If you already downloaded the project as a ZIP, extract it first and then open PowerShell in the project folder.

</details>

## Step 2: Create Your Local Environment File

Create a real `.env` file from the example template:

```bash
cp .env.example .env
```

PowerShell alternative:

```powershell
Copy-Item .env.example .env
```

Open `.env` and replace every placeholder value.

Minimum values you must change before startup:

- `POSTGRES_PASSWORD`
- `DATABASE_URL`
- `SESSION_SECRET`
- `OPERATOR_PASSWORD`

Helpful secret generation examples:

```bash
openssl rand -hex 32
```

```powershell
[guid]::NewGuid().ToString('N') + [guid]::NewGuid().ToString('N')
```

Important:

- Keep the password inside `DATABASE_URL` the same as `POSTGRES_PASSWORD`.
- Do not commit `.env`.
- `.env` is already ignored by Git.

## Step 3: Add Your Google OAuth File

If you want YouTube connection and publishing, create a Google OAuth Web Application client.

1. Open the Google Cloud Console.
2. Create or select a project.
3. Enable the YouTube Data API v3.
4. Configure the OAuth consent screen.
5. Create an OAuth client of type `Web application`.
6. Add this redirect URI:

```text
http://localhost:8000/api/v1/integrations/youtube/oauth/callback
```

7. Add this JavaScript origin:

```text
http://localhost:3000
```

8. Download the JSON credentials file.
9. Save it locally as `secrets/client_secrets.json`.

Create the folder if it does not exist:

```bash
mkdir -p secrets
```

PowerShell alternative:

```powershell
New-Item -ItemType Directory -Force secrets
```

Important:

- `secrets/` is local-only and ignored by Git.
- Never paste the JSON contents into source files.

## Step 4: Start The App With Docker

From the project root, run:

```bash
docker compose up --build
```

First boot can take a while because Docker installs Python packages, Node packages, and FFmpeg.

When everything is healthy, these URLs should work:

- Frontend: `http://localhost:3000`
- Backend API: `http://localhost:8000`
- Health check: `http://localhost:8000/health`

## Step 5: Sign In And Use The Dashboard

1. Open `http://localhost:3000`.
2. Sign in with `OPERATOR_USERNAME` and `OPERATOR_PASSWORD` from `.env`.
3. Connect YouTube from the dashboard if you configured Google OAuth.
4. Create or review jobs from the main interface.

## Environment Variable Guide

<details>
<summary>Core app settings</summary>

- `APP_ENV`: environment name such as `development` or `production`
- `DEBUG`: enables or disables debug-friendly behavior
- `API_V1_PREFIX`: API prefix used by the backend
- `FRONTEND_ORIGIN`: browser origin allowed to call the API
- `BACKEND_PUBLIC_URL`: public backend URL used in integrations
- `ALLOWED_HOSTS`: comma-separated allowed hostnames

</details>

<details>
<summary>Database and queue settings</summary>

- `POSTGRES_DB`: database name used by the Postgres container
- `POSTGRES_USER`: database username used by the Postgres container
- `POSTGRES_PASSWORD`: database password used by the Postgres container
- `DATABASE_URL`: SQLAlchemy connection string used by the backend
- `REDIS_URL`: Redis connection string used by the backend and Celery

</details>

<details>
<summary>Authentication and security settings</summary>

- `SESSION_SECRET`: signs session cookies and encrypts stored secrets
- `OPERATOR_USERNAME`: operator login name
- `OPERATOR_PASSWORD`: operator login password
- `MAX_REQUEST_BODY_BYTES`: request size safety limit

</details>

<details>
<summary>AI and media provider settings</summary>

- `GEMINI_API_KEY`: Google Gemini access key
- `OPENROUTER_API_KEY`: OpenRouter access key
- `FIRECRAWL_API_KEY`: Firecrawl access key
- `GROQ_API_KEY`: Groq access key for transcription
- `PEXELS_API_KEY`: Pexels access key for stock media
- `GENERIC_BACKGROUND_MUSIC_PATH`: optional local fallback music file

</details>

<details>
<summary>YouTube integration settings</summary>

- `YOUTUBE_CLIENT_SECRETS_PATH`: local path to your downloaded OAuth JSON file
- `YOUTUBE_REFRESH_TOKEN`: optional direct refresh token override
- `YOUTUBE_PRIVACY_STATUS`: default privacy value for uploads
- `YOUTUBE_DEFAULT_CATEGORY_ID`: default YouTube category ID
- `YOUTUBE_CHANNEL_LABEL`: label shown in the app for the connected channel

</details>

## Project Structure

```text
.
|-- backend/
|   |-- api/
|   |-- core/
|   |-- models/
|   |-- services/
|   `-- worker/
|-- frontend/
|   |-- src/app/
|   |-- src/components/
|   `-- src/lib/
|-- docker-compose.yml
|-- .env.example
|-- .gitignore
`-- README.md
```

## Manual Local Development

Docker is the easiest path. If you want to run services manually, use the steps below.

<details>
<summary>Backend API</summary>

```bash
python -m venv .venv
. .venv/bin/activate
pip install -r backend/requirements.txt
uvicorn backend.api.main:app --reload --host 0.0.0.0 --port 8000
```

Windows PowerShell activation:

```powershell
.\.venv\Scripts\Activate.ps1
```

</details>

<details>
<summary>Celery worker</summary>

```bash
celery -A backend.worker.celery_app.celery_app worker --loglevel=info --queues=video-jobs
```

</details>

<details>
<summary>Frontend</summary>

```bash
cd frontend
npm install
npm run dev
```

</details>

<details>
<summary>Services you still need in manual mode</summary>

You still need PostgreSQL and Redis running somewhere reachable by `DATABASE_URL` and `REDIS_URL`. Using Docker just for those two services is usually the simplest choice.

</details>

## Troubleshooting

<details>
<summary>The app refuses to start because of placeholder secrets</summary>

Open `.env` and replace any value that still contains text like `replace-with-` or `change-me`.

</details>

<details>
<summary>Docker says a port is already in use</summary>

Stop the program already using the port or change the published port mapping in `docker-compose.yml`.

</details>

<details>
<summary>YouTube OAuth fails</summary>

Check these values carefully:

- Redirect URI: `http://localhost:8000/api/v1/integrations/youtube/oauth/callback`
- JavaScript origin: `http://localhost:3000`
- Local file path: `secrets/client_secrets.json`

</details>

<details>
<summary>Frontend cannot reach the backend</summary>

Check `NEXT_PUBLIC_API_BASE_URL` in `.env` and make sure the backend container is healthy.

</details>

## Security Notes

- `.env` is ignored by Git.
- `secrets/` is ignored by Git.
- `secrets/` is also excluded from Docker build context.
- The backend now blocks startup when placeholder values are still being used for core secrets.
- Do not store API keys, refresh tokens, or OAuth JSON directly in source code.

## Useful Commands

```bash
docker compose up --build
docker compose down
docker compose logs -f backend-api
docker compose logs -f celery-worker
docker compose logs -f frontend
```

## Validation

- `python -m compileall backend`
- `npm run build` inside `frontend/`
