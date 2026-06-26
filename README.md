# ClipForge

**AI-powered gaming highlight extractor.** Upload a gameplay video — ClipForge's multi-modal ML pipeline analyzes audio, motion, and game state to find your best moments, then delivers them as ready-to-share clips.

---

## What it does

1. Upload a gameplay video (up to **5 GB**, any format)
2. A four-signal ML pipeline scores every second of footage
3. Non-maximum suppression finds the top 3 non-overlapping highlights
4. 30-second clips are rendered and delivered as downloadable MP4s
5. Live progress is streamed to the browser over WebSocket in real time

---

## Architecture

```
Browser
  │
  ├─ PUT raw video ────────────────────────────────────────► S3 (raw/)
  │
  ├─ POST /api/upload/confirm ──► FastAPI ──► Celery task queued
  │                                │
  │                                └──► PostgreSQL  (Job PENDING → PROCESSING)
  │
  │         Celery Worker
  │           │
  │           ├─ Download from S3
  │           ├─ ffmpeg: normalize to 30 FPS CFR + extract 22050 Hz mono audio
  │           │
  │           ├─ [ML] RMS loudness      ─┐
  │           ├─ [ML] CNN spectrogram   ─┤
  │           ├─ [ML] Optical flow      ─┤─► Score fusion ─► NMS ─► Top 3 windows
  │           └─ [ML] HUD death mask   ─┘
  │                                              │
  │           ffmpeg clip render ◄───────────────┘
  │           Upload clips ──────────────────────────────────► S3 (processed/)
  │           Write Highlight rows ──────────────────────────► PostgreSQL
  │           Write progress ────────────────────────────────► Redis
  │
  └─ WS /ws/jobs/{id} ◄──── Redis polling (0.5 s) ◄──── FastAPI WebSocket
```

---

## ML Pipeline

### Four signals scored per second

| Signal | Method | Default weight |
|--------|--------|---------------|
| **RMS audio energy** | librosa loudness, normalized [0, 1] | 0.4 |
| **CNN classification** | HighlightCNN on mel-spectrograms → P(highlight) | semantic gate |
| **Optical flow motion** | Farneback dense flow, deviation from 5 s rolling baseline | 0.4 |
| **HUD death mask** | Top-right crop brightness < 40 → dead/killcam | binary multiplier |

### Fusion formula

```
base_activity  =  RMS_WEIGHT × rms  +  MOTION_WEIGHT × motion
semantic_gate  =  0.5 + (CNN × 0.5)          # dampens, never zeros
final_score    =  base_activity × semantic_gate × death_mask
```

Scores are smoothed with a 3-frame rolling average, then the **non-maximum suppression** window search finds the highest-scoring 30-second spans with a 30-second suppression radius between picks.

### CNN model — `HighlightCNN`

```
Input: (1, 64, 44)  mel-spectrogram (64 freq bands × 44 time steps)
  Conv2d(1→16)  + BN + ReLU + MaxPool2d
  Conv2d(16→32) + BN + ReLU + MaxPool2d
  Conv2d(32→64) + BN + ReLU + MaxPool2d
  Flatten → Linear(2560→128) + ReLU + Dropout(0.3)
  Linear(128→1) + Sigmoid
Output: 0.0 – 1.0 (highlight probability)
```

Trained val accuracy: **88.9%** | Hard-negative block rate: **61%**  
Weights stored in S3 and pulled at worker startup (not baked into the image).

### Validation framing

The RMS baseline achieves high raw accuracy because training labels were generated via RMS percentile thresholds — the CNN approximates the same rule it was trained on. The CNN's independent contribution is measured by its **hard-negative block rate: 61% of clips specifically chosen to fool volume-based detection** (spawn voicelines, victory fanfare, killcam audio) were correctly rejected by the CNN using spectral texture features that RMS cannot access. This is why the CNN operates as a semantic gate rather than an additive signal — it earns its weight by catching what loudness misses, not by duplicating it.

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | React 18, React Router 6, Axios, React Dropzone, Tailwind CSS, Vite |
| Backend API | FastAPI, SQLAlchemy 2.0 (async), asyncpg, Alembic, slowapi |
| Task queue | Celery 5, Redis broker + result backend |
| ML | PyTorch 2.6 (CPU), torchaudio, librosa, OpenCV |
| Video | FFmpeg + ffprobe |
| Auth | JWT (HS256), bcrypt, httpOnly refresh-token cookies |
| Storage | AWS S3 (presigned upload + download URLs) |
| Databases | PostgreSQL 15, Redis 7 |
| Infra | Docker Compose, Nginx (SPA + reverse proxy) |

---

## Database schema

```
User ──< RefreshToken
User ──< Job ──< Highlight

Job:       id, user_id, status (PENDING|PROCESSING|COMPLETE|FAILED),
           s3_input_key, celery_task_id, progress_pct, progress_stage,
           duration_seconds, error_message, is_deleted, created_at, completed_at

Highlight: id, job_id, index (0 = best), s3_output_key,
           start_second, end_second, duration_seconds, score,
           low_confidence, created_at
```

---

## API reference

### Auth

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/auth/register` | Create account |
| POST | `/api/auth/login` | Login → access token + refresh cookie |
| POST | `/api/auth/refresh` | Rotate refresh token (httpOnly cookie) |
| POST | `/api/auth/logout` | Revoke refresh token |

### Upload

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/upload/presign` | Create Job + get S3 presigned PUT URL |
| POST | `/api/upload/confirm` | Verify upload in S3, queue Celery task |

### Jobs & Highlights

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/jobs` | List user's jobs (Redis-cached, 10 s TTL) |
| GET | `/api/jobs/{id}` | Job detail + highlights |
| DELETE | `/api/jobs/{id}` | Soft-delete, revoke task, purge S3 |
| GET | `/api/highlights/{id}/download` | Get presigned S3 download URL |
| WS | `/ws/jobs/{id}` | Live progress stream |

### Rate limits

| Endpoint | Limit |
|----------|-------|
| Login | 10 / min |
| Refresh | 20 / min |
| Upload presign / confirm | 5 / min each |
| Highlight download | 30 / min |
| Jobs list | 60 / min |

---

## Project structure

```
ClipForge/
├── backend/
│   ├── app/
│   │   ├── api/              # Route handlers (auth, upload, jobs, highlights, ws)
│   │   ├── core/
│   │   │   ├── config.py     # Pydantic settings (from .env)
│   │   │   └── security.py   # JWT + bcrypt helpers
│   │   ├── db/
│   │   │   ├── models.py     # SQLAlchemy ORM models
│   │   │   ├── session.py    # Async engine + session factory
│   │   │   └── migrations/   # Alembic versions
│   │   ├── ml/
│   │   │   ├── model.py      # HighlightCNN definition
│   │   │   ├── inference.py  # CNN mel-spectrogram inference
│   │   │   ├── features.py   # RMS audio extraction
│   │   │   ├── motion.py     # Optical flow + death mask
│   │   │   └── scorer.py     # Score fusion + NMS window detection
│   │   └── worker/
│   │       ├── celery_app.py # Celery configuration
│   │       └── tasks.py      # Main processing task
│   ├── Dockerfile
│   ├── Dockerfile.worker
│   ├── entrypoint.sh
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── pages/            # Landing, LoginRegister, Dashboard, JobDetail, Settings
│   │   ├── components/       # Navbar, UploadModal, ProgressBar, VideoPlayer
│   │   ├── hooks/
│   │   │   ├── useAuth.jsx   # Auth context + silent token refresh
│   │   │   └── useJobSocket.js # WebSocket + exponential backoff reconnect
│   │   └── services/
│   │       └── api.js        # Axios instance + 401 intercept → auto-refresh
│   ├── nginx.conf
│   ├── Dockerfile
│   └── package.json
├── data/                     # Training data (labeled/manual clips)
├── docker-compose.yml
└── .env
```

---

## Setup

### Prerequisites

- Docker + Docker Compose
- AWS account with an S3 bucket
- AWS credentials with read/write access to that bucket

### 1. Configure environment

Copy `.env` and fill in secrets:

```bash
cp .env .env.local
```

Required values:

```env
DATABASE_URL=postgresql://clipforge:clipforge@postgres:5432/clipforge
REDIS_URL=redis://redis:6379/0

SECRET_KEY=<64-char random string>
REFRESH_SECRET_KEY=<64-char random string>

AWS_ACCESS_KEY_ID=<your key>
AWS_SECRET_ACCESS_KEY=<your secret>
AWS_REGION=us-east-2
S3_BUCKET_NAME=<your bucket>

CELERY_BROKER_URL=redis://redis:6379/1
CELERY_RESULT_BACKEND=redis://redis:6379/2
```

Optional tuning:

```env
MAX_UPLOAD_SIZE_BYTES=5368709120   # 5 GB ceiling
DEFAULT_HIGHLIGHTS=3
DEFAULT_CLIP_DURATION_SECONDS=30
MIN_SCORE_THRESHOLD=0.3
RMS_WEIGHT=0.4
MOTION_WEIGHT=0.4
CNN_WEIGHT=0.2                     # acts as semantic gate, not additive
```

### 2. Upload model weights

The CNN weights must be in S3 before the worker starts:

```bash
aws s3 cp path/to/highlight_cnn.pt s3://<your-bucket>/models/highlight_cnn.pt
```

### 3. Run

```bash
docker-compose up --build
```

Services:
- Frontend → `http://localhost`
- API → `http://localhost:8000`
- API docs → `http://localhost:8000/docs`

The API container runs `alembic upgrade head` automatically on startup.

### 4. Development (frontend hot-reload)

```bash
cd frontend
npm install
npm run dev          # Vite dev server at http://localhost:5173
```

Point `VITE_API_URL` in `frontend/.env` at your local API.

---

## Auth flow

```
Register / Login
  └─► access token (30 min, stored in memory)
      refresh token (30 days, httpOnly cookie, SHA-256 hash stored in DB)

Every request:  Authorization: Bearer <access_token>

On 401:
  └─► POST /auth/refresh (cookie sent automatically)
      └─► new access + refresh token pair issued
          old refresh token revoked (JTI rotation)
          original request retried transparently
```

---

## Upload flow

```
1. POST /api/upload/presign  →  { job_id, presigned_url, s3_key }
2. PUT  <presigned_url>      →  file bytes stream directly to S3 (bypasses API)
3. POST /api/upload/confirm  →  Celery task dispatched, job → PROCESSING
4. WS   /ws/jobs/{job_id}    →  live progress until COMPLETE or FAILED
```

---

## Training data

Labeled clips live in `data/` and were used to train `HighlightCNN`. The manual annotation split covers positive examples (kills, ultimates, team fights) and hard negatives (gunshots without context, menu screens, killcam footage).

---

## License

MIT
