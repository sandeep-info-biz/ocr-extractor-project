from pathlib import Path


def _read_text_file(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


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


def _ocr_image(path: Path, preprocess: bool = True, fast: bool = True) -> str:
    try:
        import pytesseract
        from PIL import Image
    except ImportError as exc:
        raise RuntimeError("pytesseract and pillow are required for OCR.") from exc

    image = Image.open(path)
    if preprocess:
        image = _preprocess_image(image, fast=fast)
    return pytesseract.image_to_string(image)


def _ocr_pdf(path: Path, preprocess: bool = True, fast: bool = True, dpi: int = 220) -> str:
    try:
        from pdf2image import convert_from_path
        import pytesseract
    except ImportError as exc:
        raise RuntimeError("pdf2image and pytesseract are required for PDF OCR.") from exc

    pages = convert_from_path(str(path), dpi=dpi, thread_count=2 if fast else 1)
    chunks = []
    for page in pages:
        img = _preprocess_image(page, fast=fast) if preprocess else page
        chunks.append(pytesseract.image_to_string(img))
    return "\n".join(chunks)


def _extract_pdf_text_native(path: Path) -> str:
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise RuntimeError("pypdf is required for native PDF text extraction.") from exc

    reader = PdfReader(str(path))
    chunks = []
    for page in reader.pages:
        chunks.append(page.extract_text() or "")
    return "\n".join(chunks).strip()


def _extract_pdf_text_pymupdf(path: Path) -> str:
    try:
        import fitz
    except ImportError as exc:
        raise RuntimeError("pymupdf is required for PyMuPDF text extraction.") from exc

    chunks = []
    with fitz.open(str(path)) as doc:
        for page in doc:
            chunks.append(page.get_text("text") or "")
    return "\n".join(chunks).strip()


def _ocr_pdf_pymupdf(path: Path, preprocess: bool = True, fast: bool = True, dpi: int = 220) -> str:
    try:
        import fitz
        import pytesseract
        from PIL import Image
    except ImportError as exc:
        raise RuntimeError("pymupdf, pytesseract, and pillow are required for PyMuPDF OCR.") from exc

    scale = max(dpi, 72) / 72.0
    chunks = []
    with fitz.open(str(path)) as doc:
        for page in doc:
            pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            if preprocess:
                img = _preprocess_image(img, fast=fast)
            chunks.append(pytesseract.image_to_string(img))
    return "\n".join(chunks)


def _extract_pdf_with_fallback(path: Path, preprocess: bool = True, fast: bool = True, dpi: int = 220) -> str:
    errors = []

    try:
        text = _extract_pdf_text_native(path)
        if text:
            return text
    except Exception as exc:
        errors.append(f"pypdf_text: {exc}")

    try:
        text = _extract_pdf_text_pymupdf(path)
        if text:
            return text
    except Exception as exc:
        errors.append(f"pymupdf_text: {exc}")

    try:
        text = _ocr_pdf(path, preprocess=preprocess, fast=fast, dpi=dpi)
        if text.strip():
            return text
    except Exception as exc:
        errors.append(f"pdf2image_ocr: {exc}")

    try:
        text = _ocr_pdf_pymupdf(path, preprocess=preprocess, fast=fast, dpi=dpi)
        if text.strip():
            return text
    except Exception as exc:
        errors.append(f"pymupdf_ocr: {exc}")

    raise RuntimeError(
        "Failed to extract PDF text. "
        "Install dependencies with `pip install -r requirements.txt`. "
        "For scanned PDFs, ensure Tesseract is installed and in PATH. "
        "Poppler is optional when PyMuPDF fallback is available. "
        f"Attempt errors: {' | '.join(errors)}"
    )


def extract_raw_text(path: Path, preprocess: bool = True, fast: bool = True, pdf_dpi: int = 220) -> str:
    ext = path.suffix.lower()
    if ext == ".txt":
        return _read_text_file(path)
    if ext == ".docx":
        return _read_docx(path)
    if ext in {".png", ".jpg", ".jpeg", ".tiff", ".bmp"}:
        return _ocr_image(path, preprocess=preprocess, fast=fast)
    if ext == ".pdf":
        return _extract_pdf_with_fallback(path, preprocess=preprocess, fast=fast, dpi=pdf_dpi)
    raise ValueError(f"Unsupported file type: {ext}")
