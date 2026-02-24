from pathlib import Path
import re
import os
from functools import lru_cache
from typing import Callable


ProgressCallback = Callable[[int, int], None]


def _read_text_file(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def _ocr_engine() -> str:
    # Default to PaddleOCR as requested for this project.
    value = os.getenv("OCR_ENGINE", "paddle").strip().lower()
    if value not in {"paddle", "auto", "tesseract"}:
        return "paddle"
    return value


def _read_docx(path: Path) -> str:
    try:
        from docx import Document
    except ImportError as exc:
        raise RuntimeError("python-docx is required for .docx support.") from exc
    document = Document(str(path))
    return "\n".join(p.text for p in document.paragraphs if p.text.strip())


def _preprocess_image(image, fast: bool = True):
    try:
        import cv2
        import numpy as np
        from PIL import Image
    except ImportError:
        return image

    img = np.array(image.convert("RGB"))
    gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
    if fast:
        _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    else:
        denoised = cv2.fastNlMeansDenoising(gray, None, 10, 7, 21)
        thresh = cv2.adaptiveThreshold(
            denoised, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 31, 11
        )
    return Image.fromarray(thresh)


def _image_resize_limits() -> tuple[int, int]:
    try:
        max_side = max(1200, int(os.getenv("OCR_MAX_SIDE_LIMIT", "2800")))
    except Exception:
        max_side = 2800
    try:
        max_pixels = max(2_000_000, int(os.getenv("OCR_MAX_PIXELS", "6000000")))
    except Exception:
        max_pixels = 6_000_000
    return max_side, max_pixels


def _resize_for_ocr(image):
    try:
        from PIL import Image
    except ImportError:
        return image

    max_side, max_pixels = _image_resize_limits()
    width, height = image.size
    if width <= 0 or height <= 0:
        return image

    scale_side = min(1.0, max_side / max(width, height))
    scale_pixels = min(1.0, (max_pixels / float(width * height)) ** 0.5)
    scale = min(scale_side, scale_pixels)
    if scale >= 0.999:
        return image

    new_w = max(1, int(width * scale))
    new_h = max(1, int(height * scale))
    resampling = getattr(getattr(Image, "Resampling", Image), "LANCZOS", getattr(Image, "LANCZOS", 1))
    return image.resize((new_w, new_h), resampling)


@lru_cache(maxsize=1)
def _load_paddle_ocr():
    try:
        from paddleocr import PaddleOCR
    except ImportError as exc:
        raise RuntimeError(
            "paddleocr is required for PaddleOCR. Install with: pip install paddleocr paddlepaddle"
        ) from exc

    # Skip remote-source probe to reduce startup latency/noise in restricted environments.
    os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")

    # Prefer lighter OCR pipelines first. Unknown args are gracefully retried via fallbacks.
    candidate_kwargs = [
        {
            "lang": "en",
            "show_log": False,
            "use_angle_cls": False,
            "use_doc_orientation_classify": False,
            "use_doc_unwarping": False,
            "use_textline_orientation": False,
        },
        {"use_angle_cls": True, "lang": "en", "use_gpu": False, "show_log": False},
        {"use_angle_cls": True, "lang": "en", "use_gpu": False},
        {"lang": "en", "use_gpu": False},
        {"lang": "en", "device": "cpu", "show_log": False, "use_doc_orientation_classify": False, "use_doc_unwarping": False, "use_textline_orientation": False},
        {"use_angle_cls": True, "lang": "en", "device": "cpu", "show_log": False},
        {"use_angle_cls": True, "lang": "en", "device": "cpu"},
        {"lang": "en", "device": "cpu"},
        {"lang": "en"},
    ]
    last_error: Exception | None = None
    for kwargs in candidate_kwargs:
        try:
            return PaddleOCR(**kwargs)
        except Exception as exc:
            last_error = exc
            continue

    raise RuntimeError(f"Failed to initialize PaddleOCR with known argument sets: {last_error}")


def _paddle_image_to_text(image) -> str:
    try:
        import numpy as np
    except ImportError as exc:
        raise RuntimeError("numpy is required for PaddleOCR image conversion.") from exc

    ocr = _load_paddle_ocr()
    arr = np.array(image.convert("RGB"))
    result = None
    # PaddleOCR API differs by version. Try compatible call patterns.
    call_attempts = [
        ("ocr_cls", lambda: ocr.ocr(arr, cls=True)),
        ("ocr_no_cls", lambda: ocr.ocr(arr)),
        ("predict", lambda: ocr.predict(arr)),
    ]
    last_error: Exception | None = None
    for _, fn in call_attempts:
        try:
            result = fn()
            break
        except Exception as exc:
            last_error = exc
            continue
    if result is None:
        raise RuntimeError(f"PaddleOCR inference failed for all known call styles: {last_error}")

    chunks = []
    if isinstance(result, list):
        for block in result:
            if isinstance(block, dict):
                rec_texts = block.get("rec_texts", [])
                if isinstance(rec_texts, list):
                    for text in rec_texts:
                        clean = str(text or "").strip()
                        if clean:
                            chunks.append(clean)
                continue
            if not isinstance(block, list):
                continue
            for row in block:
                if not isinstance(row, (list, tuple)) or len(row) < 2:
                    continue
                text_info = row[1]
                if not isinstance(text_info, (list, tuple)) or not text_info:
                    continue
                text = str(text_info[0] or "").strip()
                if text:
                    chunks.append(text)
    return "\n".join(chunks).strip()


def _tesseract_image_to_text(image) -> str:
    try:
        import pytesseract
    except ImportError as exc:
        raise RuntimeError("pytesseract is required for OCR.") from exc
    return pytesseract.image_to_string(image)


def _ocr_image(path: Path, preprocess: bool = True, fast: bool = True) -> str:
    try:
        from PIL import Image
    except ImportError as exc:
        raise RuntimeError("pillow is required for OCR.") from exc

    image = Image.open(path)
    image = _resize_for_ocr(image)
    if preprocess:
        image = _preprocess_image(image, fast=fast)

    engine = _ocr_engine()
    if engine in {"auto", "paddle"}:
        try:
            text = _paddle_image_to_text(image)
            if text.strip():
                return text
        except Exception:
            if engine == "paddle":
                raise
    return _tesseract_image_to_text(image)


def _ocr_pdf(
    path: Path,
    preprocess: bool = True,
    fast: bool = True,
    dpi: int = 220,
    progress_callback: ProgressCallback | None = None,
) -> str:
    try:
        from pdf2image import convert_from_path
    except ImportError as exc:
        raise RuntimeError("pdf2image is required for PDF OCR.") from exc

    thread_count = 1
    if fast:
        try:
            configured = int(os.getenv("OCR_PDF2IMAGE_THREADS", "1"))
        except Exception:
            configured = 1
        thread_count = max(1, min(2, configured))
    pages = convert_from_path(str(path), dpi=dpi, thread_count=thread_count)
    total_pages = len(pages)

    chunks = []
    engine = _ocr_engine()
    use_preprocess = preprocess and engine == "tesseract"
    processed = 0

    def _ocr_single_page(page_img) -> str:
        base_img = _resize_for_ocr(page_img)
        img = _preprocess_image(base_img, fast=fast) if use_preprocess else base_img
        if engine in {"auto", "paddle"}:
            try:
                text = _paddle_image_to_text(img)
                if text.strip():
                    return text
            except Exception:
                if engine == "paddle":
                    raise
        return _tesseract_image_to_text(img)

    for page in pages:
        chunks.append(_ocr_single_page(page))
        processed += 1
        if progress_callback:
            progress_callback(processed, max(1, total_pages))
    return "\n\n[[PAGE_BREAK]]\n\n".join(chunks)


def _extract_pdf_text_native(path: Path, progress_callback: ProgressCallback | None = None) -> str:
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise RuntimeError("pypdf is required for native PDF text extraction.") from exc

    reader = PdfReader(str(path))
    chunks = []
    total = len(reader.pages)
    for idx, page in enumerate(reader.pages, start=1):
        chunks.append(page.extract_text() or "")
        if progress_callback:
            progress_callback(idx, max(1, total))
    return "\n".join(chunks).strip()


def _extract_pdf_text_pymupdf(path: Path, progress_callback: ProgressCallback | None = None) -> str:
    try:
        import fitz
    except ImportError as exc:
        raise RuntimeError("pymupdf is required for PyMuPDF text extraction.") from exc

    chunks = []
    with fitz.open(str(path)) as doc:
        total = len(doc)
        for idx, page in enumerate(doc, start=1):
            chunks.append(page.get_text("text") or "")
            if progress_callback:
                progress_callback(idx, max(1, total))
    return "\n".join(chunks).strip()


def _is_meaningful_pdf_text(text: str) -> bool:
    clean = str(text or "").strip()
    if not clean:
        return False

    # If extracted native text is too short or mostly non-letters,
    # prefer OCR fallback for scanned/image-heavy PDFs.
    alpha_count = sum(ch.isalpha() for ch in clean)
    alnum_count = sum(ch.isalnum() for ch in clean)
    word_count = len(re.findall(r"[A-Za-z]{2,}", clean))

    if alpha_count < 80 and word_count < 20:
        return False
    if alnum_count > 0 and (alpha_count / alnum_count) < 0.25 and word_count < 30:
        return False
    return True


def _detect_pdf_kind(path: Path) -> str:
    # Fast, sample-based gate to avoid unnecessary OCR without full-document scans.
    sample_pages = max(1, min(3, int(os.getenv("PDF_KIND_SAMPLE_PAGES", "2"))))
    try:
        from pypdf import PdfReader

        reader = PdfReader(str(path))
        chunks = []
        for idx, page in enumerate(reader.pages):
            if idx >= sample_pages:
                break
            chunks.append(page.extract_text() or "")
        text = "\n".join(chunks).strip()
        if _is_meaningful_pdf_text(text):
            return "text"
    except Exception:
        pass
    try:
        import fitz

        chunks = []
        with fitz.open(str(path)) as doc:
            for idx, page in enumerate(doc):
                if idx >= sample_pages:
                    break
                chunks.append(page.get_text("text") or "")
        text = "\n".join(chunks).strip()
        if _is_meaningful_pdf_text(text):
            return "text"
    except Exception:
        pass
    return "image"


def _ocr_pdf_pymupdf(
    path: Path,
    preprocess: bool = True,
    fast: bool = True,
    dpi: int = 220,
    progress_callback: ProgressCallback | None = None,
) -> str:
    try:
        import fitz
        from PIL import Image
    except ImportError as exc:
        raise RuntimeError("pymupdf and pillow are required for PyMuPDF OCR.") from exc

    page_count = 0
    with fitz.open(str(path)) as doc:
        page_count = len(doc)
    effective_dpi = max(dpi, 72)
    if page_count >= 20:
        effective_dpi = min(effective_dpi, 110)
    elif page_count >= 12:
        effective_dpi = min(effective_dpi, 130)
    scale = effective_dpi / 72.0
    chunks = []
    engine = _ocr_engine()
    use_preprocess = preprocess and engine == "tesseract"
    processed = 0
    with fitz.open(str(path)) as doc:
        for page in doc:
            pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            img = _resize_for_ocr(img)
            if use_preprocess:
                img = _preprocess_image(img, fast=fast)
            if engine in {"auto", "paddle"}:
                try:
                    text = _paddle_image_to_text(img)
                    if text.strip():
                        chunks.append(text)
                        continue
                except Exception:
                    if engine == "paddle":
                        raise
            chunks.append(_tesseract_image_to_text(img))
            processed += 1
            if progress_callback:
                progress_callback(processed, max(1, page_count))
    return "\n\n[[PAGE_BREAK]]\n\n".join(chunks)


def _extract_pdf_with_fallback(
    path: Path,
    preprocess: bool = True,
    fast: bool = True,
    dpi: int = 220,
    progress_callback: ProgressCallback | None = None,
) -> str:
    errors = []
    kind = _detect_pdf_kind(path)

    if kind == "text":
        try:
            text = _extract_pdf_text_native(path, progress_callback=progress_callback)
            if _is_meaningful_pdf_text(text):
                return text
            if text:
                errors.append("pypdf_text: low_quality_text_fallback_to_ocr")
        except Exception as exc:
            errors.append(f"pypdf_text: {exc}")
        try:
            text = _extract_pdf_text_pymupdf(path, progress_callback=progress_callback)
            if _is_meaningful_pdf_text(text):
                return text
            if text:
                errors.append("pymupdf_text: low_quality_text_fallback_to_ocr")
        except Exception as exc:
            errors.append(f"pymupdf_text: {exc}")

    try:
        text = _ocr_pdf_pymupdf(
            path,
            preprocess=preprocess,
            fast=fast,
            dpi=dpi,
            progress_callback=progress_callback,
        )
        if text.strip():
            return text
    except Exception as exc:
        errors.append(f"pymupdf_ocr: {exc}")

    try:
        text = _ocr_pdf(
            path,
            preprocess=preprocess,
            fast=fast,
            dpi=dpi,
            progress_callback=progress_callback,
        )
        if text.strip():
            return text
    except Exception as exc:
        errors.append(f"pdf2image_ocr: {exc}")

    raise RuntimeError(
        "Failed to extract PDF text. "
        "Install dependencies with `pip install -r requirements.txt`. "
        "For scanned PDFs, ensure Tesseract is installed and in PATH. "
        "Poppler is optional when PyMuPDF fallback is available. "
        f"Attempt errors: {' | '.join(errors)}"
    )


def extract_raw_text(
    path: Path,
    preprocess: bool = True,
    fast: bool = True,
    pdf_dpi: int = 220,
    progress_callback: ProgressCallback | None = None,
) -> str:
    ext = path.suffix.lower()
    if ext == ".txt":
        return _read_text_file(path)
    if ext == ".docx":
        return _read_docx(path)
    if ext in {".png", ".jpg", ".jpeg", ".tiff", ".tif", ".bmp", ".webp", ".gif"}:
        return _ocr_image(path, preprocess=preprocess, fast=fast)
    if ext == ".pdf":
        return _extract_pdf_with_fallback(
            path,
            preprocess=preprocess,
            fast=fast,
            dpi=pdf_dpi,
            progress_callback=progress_callback,
        )
    raise ValueError(f"Unsupported file type: {ext}")
