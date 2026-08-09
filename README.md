# Viral Video AI

Instagram Reels videolarini joylashdan **oldin** tahlil qilishga mo‘ljallangan Telegram-first AI platforma. U million ko‘rishni kafolatlamaydi: video, ssenariy, auditoriya konteksti va keyinchalik real Insights ma’lumotlari asosida viral ehtimol, retention xavflari hamda amaliy tahrir tavsiyalarini beradi.

![Viral Video AI dashboard](https://img.shields.io/badge/status-MVP%20foundation-7565ef)

## Hozir tayyor bo‘lgan MVP

- **O‘zbekcha, responsive product dashboard / Mini App UI** — bosh sahifa, video tahlili, score hisoboti, retention timeline, yaxshilangan ssenariy, montajchi briefi, idea validator, kontent-reja, raqobatchilar, post-faktum natijalar va sozlamalar ekranlari.
- **Ishlaydigan demo oqim** — video tanlash / drag-and-drop, AI tahlil bosqichlari, timeline segmentlari, report tablari, copy/export toastlari va g‘oya tahlili foydalanuvchi interfeysida ishlaydi.
- **FastAPI API** — async analysis job yaratish, xavfsizroq video upload, hajm/format/davomiylik tekshiruvi, `ffprobe` metadata tekshiruvi va status polling.
- **Telegram bot** — onboarding, asosiy menyu, MP4/MOV/AVI qabul qilish, tahlil statusi va Telegram ichida qisqa hisobotni yuboradigan Aiogram oqimi.
- **Tushunarli scoring engine** — account type bo‘yicha og‘irliklar, 0–100 score, confidence va “fakt / akkaunt tarixi / AI xulosasi / ma’lumot yetarli emas” kabi evidence label’lari.
- **Testlar** — scoring og‘irliklari, async analysis lifecycle va idea fact-check signalini qoplaydi.

> Hozirgi AI engine **deterministik MVP fallback** sifatida ishlaydi: u mavjud kontekstga qarab xulosa beradi va video/STT ma’lumoti yo‘q joyda confidence’ni pasaytiradi. Production’da `jobs.process_analysis` chegarasiga FFmpeg, Whisper/STT, OCR, multimodal vision, audio va LLM workerlarini ulanadi. Bu dizayn video ko‘rilmaganda “video ko‘rildi” degan noto‘g‘ri da’vo qilmaslik uchun tanlangan.

## Interfeys bo‘limlari

| Bo‘lim | Qiymat |
| --- | --- |
| `Videoni tahlil qilish` | Video upload, kontekst, processing state va limit ko‘rsatkichi |
| `Video hisoboti` | Viral Score, Hook/Retention/Visual/Audio score, segment timeline, ssenariy, CTA va montaj briefi |
| `G‘oyani tekshirish` | Idea Score, potensial, hooklar, ssenariy strukturasi va fact-check kerak bo‘lgan joylar |
| `Kontent-reja` | Haftalik plan, content pillars, hook va posting time konteksti |
| `Raqobatchilar` | Ochiq kontent signallari, formatlar va differensiatsiya bo‘shlig‘i |
| `Natijalarim` | AI prognozi ↔ real natija learning loop dizayni |
| `AI tavsiyalar` | Shaxsiy signal manbasi bilan izohlangan tavsiyalar |

## Tez boshlash

### 1. Web dashboard

```bash
npm install
npm run dev
```

Vite server `http://localhost:5173` da ochiladi. Production bundle tekshiruvi:

```bash
npm run lint
npm run build
```

### 2. API

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r backend/requirements-dev.txt
PYTHONPATH=backend uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

API documentation: `http://localhost:8000/docs`. Frontend browser tomondan faqat relative `/api` URL ishlatadi; Vite development proxy bu path’ni API’ga yo‘naltiradi. Production reverse proxy ham `/api` ni API service’ga route qilishi kerak.

`POST /v1/analyses` kontekstga asoslangan tahlil job’ini boshlaydi. `GET /v1/analyses/{id}` status va reportni qaytaradi. `POST /v1/ideas/check` g‘oya validatoridir. `POST /v1/analyses/upload` esa `file` va string ko‘rinishidagi `context` JSON form field qabul qiladi.

### 3. Telegram bot

1. `.env.example` faylidan nusxa oling va tokenni faqat local/secret storage’da saqlang.
2. `TELEGRAM_BOT_TOKEN` environment variable’ini bering.
3. API environment bilan:

```bash
PYTHONPATH=backend python -m app.bot
```

Bot polling rejimida ishlaydi. Production’da HTTPS webhook, webhook secret, PostgreSQL hamda Redis queue ishlatilishi kerak.

### Docker Compose

```bash
cp .env.example .env
# .env ichiga TELEGRAM_BOT_TOKEN yozing
docker compose up --build
```

`backend/Dockerfile` ichida metadata uchun `ffmpeg/ffprobe` o‘rnatiladi. Docker Compose hozir API va botning local MVP compose’idir; production uchun alohida Redis, PostgreSQL, S3-compatible storage va worker service qo‘shiladi.

## API lifecycle

```text
Telegram / Mini App
        │
        ├─ upload video → format / size validation → object storage
        │                                      │
        │                                      ▼
        │                         analysis job: queued
        │                                      │
        │          FFmpeg → STT → OCR/Vision → score → report
        │                                      │
        ▼                                      ▼
Telegram report / Dashboard  ←  completed + evidence labels
```

MVP worker quyidagi davlatlar bilan mos keladi:

```text
uploaded → queued → processing → transcribing → visual_analysis
→ scoring → report_generation → completed | failed
```

## Scoring tamoyili

Boshlang‘ich vaznlar:

- Hook — 15%
- Retention — 20%
- Shareability — 15%
- Saveability — 10%
- Rewatch — 10%
- Visual — 8%
- Audio — 5%
- Script clarity — 7%
- Audience fit — 5%
- CTA — 5%

`backend/app/scoring.py` vaznlarni account type bo‘yicha ochiq ravishda moslaydi. Masalan, education/expert kontentida save va clarity, entertainment’da share va rewatch, product/local business’da CTA ustunroq. Keyingi bosqichda `Predictions` va real Insights asosida workspace-specific model qo‘shiladi.

## Fakt va xulosa shaffofligi

Har reportda `evidence` beriladi:

- `verified_fact` — tasdiqlangan fakt;
- `account_history` — foydalanuvchining o‘z Insights ma’lumoti;
- `external_source` — tashqi manba;
- `ai_inference` — model / heuristika xulosasi;
- `insufficient_data` — yetarli signal yo‘q.

Bu kontent tavsiyasi, taxmin va tekshirilgan faktni aralashtirmaslik uchun muhim. Viral Score va ko‘rishlar prognozi **kafolat emas**.

## Production checklist

Quyidagilar MVP’dan oldin production release uchun majburiy:

- PostgreSQL migrationlar: `Users`, `Workspaces`, `Videos`, `VideoAnalysis`, `VideoSegments`, `InstagramMetrics`, `Predictions`;
- Redis + Celery/BullMQ task queue va ajratilgan FFmpeg / AI workerlar;
- S3-compatible private storage, presigned URL, malware scan va lifecycle deletion;
- Instagram Business API OAuth, token encryption/KMS, renewal va account disconnect;
- STT (o‘zbek/rus/aralash nutq), OCR, scene detection, audio analysis va multimodal model gateway;
- per-user rate limit, RBAC, audit logs, billing/usage limits, Sentry va product analytics;
- fact-check/research provider, source date validation va citation storage;
- signed Telegram webhook, HTTPS, idempotency va retry/dead-letter queue;
- Privacy Policy, Terms of Use hamda foydalanuvchi ma’lumotini o‘chirish oqimi.

## Testlar

```bash
PYTHONPATH=backend .venv/bin/pytest backend/tests -q
```

## Repository tuzilishi

```text
src/                       # React / Vite Mini App-style dashboard
backend/app/
  main.py                  # FastAPI API
  bot.py                   # Telegram onboarding + video report flow
  scoring.py               # transparent score calculation
  analyzer.py              # report + idea validator fallback
  video.py                 # upload validation and ffprobe metadata
  jobs.py                  # async processing boundary
backend/tests/             # API/scoring tests
```
