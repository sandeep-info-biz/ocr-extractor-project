# OCR Extractor Project

## Run on Laptop (optimized)

Use Python `3.11` for best compatibility and speed.

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python main.py api --host 127.0.0.1 --port 8000
```

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

`/test` now returns:
- `token_id`
- `extracted_data` (structured resume JSON)

Feedback + reinforcement flow:
1. Call `POST /test` with resume file.
2. Take `token_id` from response.
3. Call `POST /feedback` with:
   - `token_id`
   - `rating` (1-5)
   - `corrected_data` (optional corrected structured mapping)
   - `retrain_on_submit` (`true`/`false`)

If `corrected_data` is provided, it is added to dataset and model is retrained when `retrain_on_submit=true`.

Feedback-weighted learning:
- User `rating` now influences training weight (`5` has highest weight).
- Corrected entries are stored with feedback metadata and used to prioritize reliable patterns during mapping retrain.

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
