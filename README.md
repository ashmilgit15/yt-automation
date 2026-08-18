# 🎬 YouTube Automation & Bulk Multi-Engine AI Transcriber

[![FastAPI](https://img.shields.io/badge/FastAPI-009688?style=for-the-badge&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![Next.js](https://img.shields.io/badge/Next.js%2015-000000?style=for-the-badge&logo=nextdotjs&logoColor=white)](https://nextjs.org)
[![Celery](https://img.shields.io/badge/Celery-37814A?style=for-the-badge&logo=celery&logoColor=white)](https://docs.celeryq.dev)
[![Docker](https://img.shields.io/badge/Docker-2496ED?style=for-the-badge&logo=docker&logoColor=white)](https://www.docker.com)
[![NVIDIA CUDA](https://img.shields.io/badge/NVIDIA%20CUDA-76B900?style=for-the-badge&logo=nvidia&logoColor=white)](https://developer.nvidia.com/cuda-toolkit)

An enterprise-grade, high-throughput bulk YouTube transcription and AI synthesis platform. Transcribe individual videos or entire playlists (up to 200 videos per batch) with local GPU acceleration or cloud engines, refine transcripts with an autonomous **AI Cleanup Agent**, and generate chapter breakdowns and action items with an **AI Executive Summarizer Agent**.

---

## 📑 Table of Contents

- [✨ Key Features](#-key-features)
- [🏗️ System Architecture](#️-system-architecture)
- [🚀 Quick Start (Beginner Friendly)](#-quick-start-beginner-friendly)
  - [1. Prerequisites](#1-prerequisites)
  - [2. Clone Repository](#2-clone-repository)
  - [3. Configure Environment (`.env`)](#3-configure-environment-env)
  - [4. Launch with Docker & GPU](#4-launch-with-docker--gpu)
  - [5. Access Dashboard](#5-access-dashboard)
- [⚙️ Transcription Engines](#️-transcription-engines)
- [🤖 Autonomous AI Agents](#-autonomous-ai-agents)
- [📥 Export Formats](#-export-formats)
- [🎮 Dashboard & Controls](#-dashboard--controls)
- [🔧 Manual Development (Without Docker)](#-manual-development-without-docker)
- [❓ Troubleshooting & FAQ](#-troubleshooting--faq)
- [🔒 Security Best Practices](#-security-best-practices)

---

## ✨ Key Features

- **⚡ Multi-Engine STT Flexibility**:
  - **Local GPU Whisper (`faster-whisper-large-v3-turbo-ct2`)**: CTranslate2 INT8 GPU acceleration on your NVIDIA GPU (RTX 3050+), 100% offline, free & private.
  - **Sarvam AI (Saaras v3)**: State of the art for 23 Indian Indic languages (Hindi, Malayalam, Tamil, Telugu, Kannada, Bengali, etc.) with automatic English translation.
  - **Groq Cloud Whisper**: Ultra-low-latency transcription on Groq LPUs.
- **🛡️ Anti-Hallucination & Anti-Drift Engine**:
  - Configured with `condition_on_previous_text=False` to prevent infinite repetition loops on long videos.
  - Built-in **Silero Voice Activity Detection (VAD)** strips silent pauses and background music.
- **🤖 Dual Autonomous AI Agents (Gemini 3.7 Flash via Hack Club AI)**:
  - **AI Cleanup Agent**: Removes stuttering, filler words (`um`, `uh`, `like`), cleans grammatical errors, and aligns timestamps.
  - **AI Executive Summarizer**: Produces an Executive Summary, Key Highlights, Action Items, and Clickable Timestamped Chapter Breakdowns (`01:23 - Title: summary`).
  - **Master Playlist Synthesis**: Combines all playlist videos into an overarching master synthesis document.
- **🎛️ Interactive Lifecycle Controls**:
  - **Pause (⏸️)**, **Resume (▶️)**, and **Cancel (⏹️)** individual tasks or entire playlist batches.
  - **1-Click Delete Cross Marks (✕)** to remove unwanted or failed tasks immediately.
  - **3-Tab Live Preview Modal**: Switch between *Clean Transcript*, *AI Summary & Chapters*, and *Raw Subtitles*.
- **💾 7 Export Formats**:
  - `TXT`, `SRT`, `VTT`, `JSON`, `Clean TXT`, `Summary MD`, and `Summary JSON`.

---

## 🏗️ System Architecture

```
                                  ┌────────────────────────┐
                                  │   Next.js 15 Frontend  │
                                  │   (http://localhost:3000)
                                  └───────────┬────────────┘
                                              │ REST API / SWR Polling
                                              ▼
                                  ┌────────────────────────┐
                                  │   FastAPI Backend API  │
                                  │   (http://localhost:8000)
                                  └─────┬────────────┬─────┘
                                        │            │
                         State / Auth   │            │ Task Dispatch
                                        ▼            ▼
                   ┌────────────────────────┐    ┌────────────────────────┐
                   │  PostgreSQL Database   │    │      Redis Broker      │
                   └────────────────────────┘    └───────────┬────────────┘
                                                             │
                                                             ▼
                                                 ┌────────────────────────┐
                                                 │  Celery Worker (GPU)   │
                                                 │  • faster-whisper INT8 │
                                                 │  • Sarvam STT Engine   │
                                                 │  • Groq Whisper STT    │
                                                 │  • Gemini 3.7 Agents   │
                                                 └────────────────────────┘
```

---

## 🚀 Quick Start (Beginner Friendly)

### 1. Prerequisites

Make sure you have the following installed on your machine:
- [Git](https://git-scm.com/)
- [Docker & Docker Compose](https://docs.docker.com/get-docker/)
- *(Optional for GPU acceleration)* [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html)

### 2. Clone Repository

```bash
git clone https://github.com/ashmilgit15/yt-automation.git
cd yt-automation
```

### 3. Configure Environment (`.env`)

Copy the template `.env.example` to `.env`:

```bash
cp .env.example .env
```

Open `.env` in your code editor and verify/adjust the keys:

```env
# Application & Security
APP_ENV=development
DEBUG=true
API_V1_PREFIX=/api/v1
FRONTEND_ORIGIN=http://localhost:3000
BACKEND_PUBLIC_URL=http://localhost:8000

# Operator Credentials (for UI access)
SESSION_SECRET=ashmil2010
OPERATOR_USERNAME=operator
OPERATOR_PASSWORD=ashmil2010

# Database & Queue
POSTGRES_DB=video_factory
POSTGRES_USER=video_factory
POSTGRES_PASSWORD=ashmil2010
DATABASE_URL=postgresql+psycopg://video_factory:ashmil2010@postgres:5432/video_factory
REDIS_URL=redis://redis:6379/0

# AI Models & Agents
HACKCLUB_API_KEY=your_hackclub_api_key_here
HACKCLUB_BASE_URL=https://ai.hackclub.com/proxy/v1
HACKCLUB_MODEL=google/gemini-3.7-flash

# Cloud STT (Optional)
SARVAM_API_KEY=your_sarvam_api_key_here
GROQ_API_KEY=your_groq_api_key_here

# Local Faster-Whisper GPU Settings
WHISPER_MODEL=deepdml/faster-whisper-large-v3-turbo-ct2
WHISPER_DEVICE=auto
WHISPER_COMPUTE_TYPE=int8_float16
```

### 4. Launch with Docker & GPU

Start all services (Postgres, Redis, Backend API, GPU Celery Worker, Next.js Frontend) with one command:

```bash
docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d
```

> 💡 *If you are running on CPU without an NVIDIA GPU, omit the `-f docker-compose.gpu.yml` flag:*
> ```bash
> docker compose up -d
> ```

### 5. Access Dashboard

Once started, open your browser:
- 🌐 **Web Dashboard**: [http://localhost:3000](http://localhost:3000)
- 🔌 **Swagger API Docs**: [http://localhost:8000/docs](http://localhost:8000/docs)
- 🩺 **Health Check**: [http://localhost:8000/health](http://localhost:8000/health)

Log in with:
- **Username**: `operator` (or whatever you set in `OPERATOR_USERNAME`)
- **Password**: `ashmil2010` (or whatever you set in `OPERATOR_PASSWORD`)

---

## ⚙️ Transcription Engines

| Engine | Best For | Hardware Requirements | Features |
| :--- | :--- | :--- | :--- |
| **Local Faster-Whisper (Large v3 Turbo)** | English & Global Languages | NVIDIA GPU (RTX 3050 6GB recommended) | 100% Free, Private, Zero Rate Limits, VAD Anti-Hallucination |
| **Sarvam AI (Saaras v3)** | Indic Languages (Hindi, Malayalam, Tamil, etc.) | Cloud API | Word-level timestamps, auto-translate to English |
| **Groq Cloud Whisper** | High-speed Cloud Batching | Cloud API | Whisper Large v3 Turbo on Groq LPUs |

---

## 🤖 Autonomous AI Agents

### 1. AI Transcript Cleanup Agent
- **Purpose**: Cleans raw speech into publication-grade transcripts.
- **Features**:
  - Removes stuttering, verbal tics, and filler words (`um`, `uh`, `like`, `you know`).
  - Eliminates infinite repetition loops from background audio or silence.
  - Corrects punctuation, capitalization, and grammar while preserving original timestamps.

### 2. AI Executive Summarizer Agent
- **Purpose**: Generates high-level structured executive overviews.
- **Features**:
  - **Executive Summary**: Comprehensive paragraph summarizing the core narrative.
  - **Key Highlights**: Bullet points of essential concepts.
  - **Action Items**: Checklist of actionable takeaways (`- [ ] ...`).
  - **Chapter Breakdown**: Precise timestamped timecodes (`02:15 - Introduction to Neural Networks: Overview of backpropagation`).

---

## 📥 Export Formats

Click the export buttons directly on completed video cards or in the preview modal:

- 📄 **TXT**: Clean raw transcript text.
- ⏱️ **SRT**: SubRip subtitle format with timecodes (`00:01:23,456 --> 00:01:27,890`).
- 🌐 **VTT**: Web Video Text Tracks for web players.
- 🗄️ **JSON**: Structured segments with word-level timestamps.
- ✨ **Clean TXT**: Post-processed text from the AI Cleanup Agent.
- 📑 **Summary MD**: Full formatted Markdown report with chapters, action items, and quotes.

---

## 🎮 Dashboard & Controls

1. **Direct Single Video Mode**:
   - Paste any direct YouTube URL (`https://www.youtube.com/watch?v=...`) to transcribe instantly.
2. **Playlist Batch Mode**:
   - Paste any YouTube Playlist URL (`https://www.youtube.com/playlist?list=...`), click **Analyse Playlist**, and select/deselect videos.
3. **Task Controls**:
   - **Pause (⏸️)**: Temporarily halts a queued task.
   - **Resume (▶️)**: Resumes paused execution.
   - **Cancel (⏹️)**: Stops processing and releases worker resources.
   - **Cross Mark (✕)**: Deletes the task, removes artifacts from disk, and cleans up the UI.
   - **Retry (🔄)**: Re-queues a failed task with 1 click.

---

## 🔧 Manual Development (Without Docker)

If you prefer running services directly on your host machine:

### 1. Start PostgreSQL & Redis
```bash
docker compose up -d postgres redis
```

### 2. Backend & Worker
```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Terminal 1: Run FastAPI API
uvicorn backend.api.main:app --reload --host 0.0.0.0 --port 8000

# Terminal 2: Run Celery GPU Worker
celery -A backend.worker.celery_app.celery_app worker --loglevel=info --queues=video-jobs
```

### 3. Frontend
```bash
cd frontend
npm install
npm run dev
```

---

## ❓ Troubleshooting & FAQ

### Q1: `CUDA out of memory` during local transcription?
> **Fix**: In your `.env`, ensure `WHISPER_COMPUTE_TYPE=int8_float16` is set. This keeps the VRAM usage under 1.8 GB for `large-v3-turbo`, fitting comfortably on 6GB GPUs like the RTX 3050.

### Q2: How do I install NVIDIA Docker Toolkit on Linux?
> **Arch / CachyOS**:
> ```bash
> sudo pacman -S nvidia-container-toolkit libnvidia-container
> sudo nvidia-ctk runtime configure --runtime=docker
> sudo systemctl restart docker
> ```
> **Ubuntu / Debian**:
> ```bash
> sudo apt-get install -y nvidia-container-toolkit
> sudo nvidia-ctk runtime configure --runtime=docker
> sudo systemctl restart docker
> ```

### Q3: `429 Too Many Requests` on Sarvam AI?
> **Fix**: The backend has built-in exponential backoff and throttled submission workers. If rate limits persist, reduce concurrent playlist items or switch to the Local Faster-Whisper engine.

---

## 🔒 Security Best Practices

- **Never commit `.env`**: `.env` is listed in `.gitignore` and contains sensitive API keys.
- **Never commit `secrets/`**: OAuth credentials and client secrets are kept strictly local.
- **Operator Authentication**: Sessions are signed with HMAC-SHA256 using `SESSION_SECRET`.

---

## 📜 License

Distributed under the MIT License. See `LICENSE` for more information.
