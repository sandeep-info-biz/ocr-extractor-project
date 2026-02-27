# OCR Extractor Project

## Target Architecture (Java + Python)

- `Java (Spring Boot)`:
  - Main backend entrypoint
  - Thymeleaf UI
  - File upload form and result rendering
  - Calls Python API for extraction
- `Python (FastAPI)`:
  - OCR + ML extraction logic
  - `/test` endpoint used by Java
  - Optional async worker and training/feedback endpoints

### Run full stack locally

1. Start Python OCR/ML service:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python main.py api --host 127.0.0.1 --port 8000
```

2. Start Java backend + Thymeleaf UI (new terminal):

```bash
mvn spring-boot:run
```

Or use helper scripts:

```bash
./start.sh
./restart.sh
./stop_all.sh
```

Terminal behavior:
- `./start.sh` / `./start_all.sh` default to inline mode (single terminal with background processes).
- For separate macOS Terminal windows: `LAUNCH_MODE=separate ./start.sh`
- In VS Code integrated terminals, use Task: `Start Full Stack (3 terminals)` and `Restart Full Stack`.
- Dev credentials/tokens are auto-generated once and stored in `.run/dev.env`.

3. Open:

- `http://127.0.0.1:8080`
- Swagger UI: `http://127.0.0.1:8000/swagger`
- OpenAPI JSON: `http://127.0.0.1:8000/openapi.json`

Environment variables for Java:

- `PYTHON_SERVICE_BASE_URL` (default `http://127.0.0.1:8000`)
- `PYTHON_SERVICE_TIMEOUT_SECONDS` (default `180`)
- `APP_LOGIN_USERNAME` (required)
- `APP_LOGIN_PASSWORD` (required)

Environment variables for Python API security:

- `CORS_ALLOW_ORIGINS` (comma-separated origins, default `http://127.0.0.1:8080,http://localhost:8080`)
- Choose at least one auth mode:
  - Static token mode: `SIMPLYPARSE_API_TOKEN`
  - Bearer login mode: `API_AUTH_SECRET`, `API_LOGIN_USER`, `API_LOGIN_PASSWORD`

Notes:
- Protected endpoints now require `Authorization`.
- Weak defaults such as `admin/admin123` and `change-me-secret` are rejected.

## Public REST API (for other apps/websites)

Versioned endpoints are available under `/api/v1` and documented in Swagger.

Core endpoints:
- `POST /api/v1/auth/login`
- `GET /api/v1/health`
- `GET /api/v1/models`
- `POST /api/v1/parsers/{parser_id}/documents`
- `GET /api/v1/parsers/{parser_id}/documents/{document_id}`
- `GET /api/v1/documents/{document_id}/file`
- `GET /api/v1/queue/stats`
- `POST /api/v1/extract`
- `POST /api/v1/feedback`
- `POST /api/v1/retrain-mapping`
- `GET /api/v1/analytics/training-feedback`
- `GET /api/v1/analytics/training-feedback/plot`

Auth header format:
- `Authorization: Bearer <token>` (from `/api/v1/auth/login`)
- or `Authorization: Token <token>` (if using `SIMPLYPARSE_API_TOKEN`)

Postman:
- Collection file: `postman/ocr-extractor-api.postman_collection.json`

## Run on Laptop (optimized)

Use Python `3.11` for best compatibility and speed.

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python main.py api --host 127.0.0.1 --port 8000
```

For production-style async processing (recommended), run OCR worker as a separate process:

```bash
# terminal 1
python main.py api --host 127.0.0.1 --port 8000

# terminal 2
python main.py worker --poll-seconds 0.8 --max-attempts 3
```

Optional worker concurrency:

```bash
# example: run 2 OCR jobs in parallel inside worker process
export ASYNC_WORKER_THREADS=2
python main.py worker
```

Why this matters:
- API process only queues jobs and responds quickly.
- Worker process handles heavy OCR/ML extraction.
- Large PDFs no longer block other API endpoints.

Windows OCR prerequisites (for scanned PDFs/images):
1. Install Tesseract OCR and add it to `PATH`.
2. Optional: install Poppler and add `bin` to `PATH` for `pdf2image`.
3. If Poppler is not installed, app now falls back to PyMuPDF rendering for PDF extraction.

Fast test request modes:
- `fast`: regex/rule extraction, lowest latency.
- `balanced`: local spaCy + rules (default).
- `resume_bert`: pretrained resume NER model (`yashpwr/resume-ner-bert-v2`) + rules.

`/test` form fields:
- `resume_file` (required)
- `mode` = `fast|balanced|resume_bert`
- `preprocess` = `true|false`
- `pdf_dpi` (default `220`, lower is faster)

Single LLM endpoint for Colab (OCR -> LLM -> optional mapping retrain):
- `POST /auto-test-llm-colab`
- Form fields:
  - `resume_file` (required)
  - `preprocess` = `true|false`
  - `pdf_dpi` (default `220`)
  - `mode` = `fast|balanced|resume_bert`
  - `llm_base_model_id` (default `Qwen/Qwen2.5-3B-Instruct`)
  - `llm_adapter_path` (default `models/lora_adapter`)
  - `llm_max_new_tokens` (default `768`)
  - `auto_train` = `true|false` (default `true`)
- Flow:
  - OCR extracts raw text
  - LLM generates structured JSON
  - if `auto_train=true`, result is appended to `data/resume_training_seed.json`
  - if `auto_train=true`, mapping model is retrained and saved to `models/resume_mapping_model.json`

`/test` now returns:
- `token_id`
- `extracted_data` (structured resume JSON)

Feedback + reinforcement flow:
1. Call `POST /test` with resume file.
2. Take `token_id` from response.
3. Call `POST /feedback` with:
   - `token_id`
   - `extracted_data` (optional: paste the original extracted JSON directly)
   - `rating` (1-5)
   - `corrected_data` (optional corrected structured mapping)
   - `retrain_on_submit` (`true`/`false`)

Note for feedback payload:
- `raw_text` is not required.
- If `raw_text` is sent inside `extracted_data` or `corrected_data`, it is ignored and not used for feedback training.

`token_id` is required so feedback is always linked to the exact `/test` response.
Training data priority in feedback flow:
- `corrected_data` (if provided)
- otherwise `extracted_data`

Feedback-weighted learning:
- User `rating` now influences training weight (`5` has highest weight).
- Corrected entries are stored with feedback metadata and used to prioritize reliable patterns during mapping retrain.

Async queue observability:
- `GET /dapi/v1/queue/stats`
- Returns queued / processing / failed job counts.

Training/feedback analytics endpoint:
- `GET /analytics/training-feedback`
- Returns graph-ready series for:
  - `accuracy_trend`
  - `rating_trend`
  - `dataset_growth`
  - `model_growth`
  - `retrain_quality`
- Matplotlib image graph:
  - `GET /analytics/training-feedback/plot`
  - Returns a PNG dashboard with all trends + rating distribution.

## Dataset Training (Mapping Calibration)

Use your structured dataset (same schema as API output) to train the local mapping model:

```bash
python scripts/train_mapping_model.py --dataset data/resume_training_seed.json --output models/resume_mapping_model.json
```

After training, extraction automatically uses `models/resume_mapping_model.json` to improve mapping.

Important:
- Dataset file must be valid JSON (no `//` comments).

API retrain endpoint:
- `POST /retrain-mapping`
- Accepts `new_entries` in the same resume JSON format.
- Appends entries to `data/resume_training_seed.json`, retrains mapping model, and returns updated counts.

Example request body:

```json
{
  "new_entries": [
    {
      "first_name": "Sample",
      "last_name": "User",
      "phone_number": "9999999999",
      "email": "sample@example.com",
      "date_of_birth": "1998-01-01",
      "gender": "Male",
      "religion": "",
      "marital_status": "Single",
      "nationality_country_name": "India",
      "country_region": "Maharashtra",
      "city": "Pune",
      "postal_code": "411001",
      "languages": ["English", "Hindi"],
      "industry_type": "Information Technology",
      "designation_or_position": "Backend Engineer",
      "total_experience": 4,
      "gulf_expierence": false,
      "passport_number": "A1234567",
      "passport_expiry_date": "2030-01-01",
      "skills": ["Python", "FastAPI"],
      "education": [
        {
          "degree": "B.Tech",
          "field_of_study": "Computer Science",
          "institution": "Sample University",
          "graduation_year": 2022
        }
      ],
      "education_degree": "B.Tech",
      "about_description_summary": "Backend engineer with API development experience.",
      "linkedin_url": "https://linkedin.com/in/sampleuser",
      "raw_text": "Sample User Backend Engineer Email sample@example.com Phone 9999999999 Pune Skills Python FastAPI B.Tech Sample University"
    }
  ],
  "append_to_existing": true,
  "run_check": true
}
```

## Kaggle Export From Feedback Logs

Generate a Kaggle-ready JSONL dataset from feedback history:

```bash
python scripts/export_kaggle_dataset.py --out-dir data/kaggle_export --min-rating 4
```

This exporter:
- Uses `data/feedback_log.json` as the primary source.
- Backfills `raw_text` from `data/feedback_sessions.json` when needed.
- Backfills `document_id` from `data/async_documents.json` when needed.
- Keeps only entries with `corrected_data`.
- Filters by `rating` (`--min-rating`).
- Deduplicates by normalized `raw_text` fingerprint (keeps latest correction).
- Creates deterministic splits by fingerprint hash.

Output files:
- `data/kaggle_export/kaggle_all.jsonl`
- `data/kaggle_export/kaggle_train.jsonl`
- `data/kaggle_export/kaggle_val.jsonl`
- `data/kaggle_export/kaggle_test.jsonl`
- `data/kaggle_export/manifest.json`

Useful options:
- `--min-rating 5`
- `--train-pct 85 --val-pct 10`
- `--no-dedup`

## Run on Colab with ngrok

Use these commands in Google Colab:

```bash
!apt-get update -y
!apt-get install -y poppler-utils tesseract-ocr
!pip install -r requirements.txt
!python colab_ngrok.py --ngrok-token "<YOUR_NGROK_AUTH_TOKEN>" --port 8000
```

After it starts, copy the printed `FastAPI public (ngrok)` URL.

- Swagger UI: `<PUBLIC_URL>/docs`
- Health check: `<PUBLIC_URL>/health`

If you prefer env var instead of CLI token:

```bash
import os
os.environ["NGROK_AUTH_TOKEN"] = "<YOUR_NGROK_AUTH_TOKEN>"
!python colab_ngrok.py --port 8000
```

Notes:
- `poppler-utils` is required by `pdf2image` for scanned/image PDFs.
- If Poppler is missing, the app falls back to `pypdf`/`pymupdf` extraction and PyMuPDF OCR path.
