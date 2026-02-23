import argparse
import json
import os
import shutil
import subprocess
import time
from threading import Thread

import requests
import uvicorn


def _in_colab() -> bool:
    return os.path.exists("/content")


def ensure_ocr_system_deps(auto_install: bool = True) -> None:
    tesseract_ok = shutil.which("tesseract") is not None
    poppler_ok = shutil.which("pdftoppm") is not None
    if tesseract_ok and poppler_ok:
        return

    if not auto_install:
        missing = []
        if not tesseract_ok:
            missing.append("tesseract")
        if not poppler_ok:
            missing.append("poppler(pdftoppm)")
        raise RuntimeError(
            "Missing OCR system dependencies: "
            + ", ".join(missing)
            + ". Install in Colab with: apt-get update -y && apt-get install -y tesseract-ocr poppler-utils"
        )

    if not _in_colab():
        raise RuntimeError(
            "Missing OCR system dependencies and auto-install is only enabled for Colab. "
            "Install: tesseract-ocr and poppler-utils."
        )

    print("Installing missing OCR system dependencies (tesseract/poppler)...")
    subprocess.run(["apt-get", "update", "-y"], check=True)
    subprocess.run(["apt-get", "install", "-y", "tesseract-ocr", "poppler-utils"], check=True)

    # Re-check after install
    tesseract_ok = shutil.which("tesseract") is not None
    poppler_ok = shutil.which("pdftoppm") is not None
    if not (tesseract_ok and poppler_ok):
        raise RuntimeError("Dependency install attempted but tools still not found in PATH.")


def run_server(host: str, port: int) -> None:
    uvicorn.run("app.api:app", host=host, port=port, reload=False)


def start_ngrok_tunnel(port: int, auth_token: str | None = None) -> str:
    try:
        from pyngrok import ngrok
    except ImportError as exc:
        raise RuntimeError("pyngrok is not installed. Install it with: pip install pyngrok") from exc

    token = auth_token or os.getenv("NGROK_AUTH_TOKEN")
    if token:
        ngrok.set_auth_token(token)

    ngrok.kill()
    tunnel = ngrok.connect(addr=port, bind_tls=True)
    return tunnel.public_url


def wait_for_server(url: str, timeout_sec: int = 90) -> None:
    started = time.time()
    while time.time() - started < timeout_sec:
        try:
            resp = requests.get(url, timeout=5)
            if resp.ok:
                return
        except Exception:
            pass
        time.sleep(1.5)
    raise TimeoutError(f"Server did not become ready in {timeout_sec}s: {url}")


def is_server_up(url: str) -> bool:
    try:
        resp = requests.get(url, timeout=3)
        return bool(resp.ok)
    except Exception:
        return False


def call_auto_test_llm_colab(
    base_url: str,
    resume_file: str,
    preprocess: bool,
    pdf_dpi: int,
    mode: str,
    llm_base_model_id: str,
    llm_adapter_path: str,
    llm_max_new_tokens: int,
    auto_train: bool,
) -> dict:
    endpoint = f"{base_url}/auto-test-llm-colab"
    data = {
        "preprocess": str(preprocess).lower(),
        "pdf_dpi": str(pdf_dpi),
        "mode": mode,
        "llm_base_model_id": llm_base_model_id,
        "llm_adapter_path": llm_adapter_path,
        "llm_max_new_tokens": str(llm_max_new_tokens),
        "auto_train": str(auto_train).lower(),
    }
    with open(resume_file, "rb") as fh:
        files = {"resume_file": (os.path.basename(resume_file), fh)}
        response = requests.post(endpoint, files=files, data=data, timeout=1800)
    response.raise_for_status()
    return response.json()


def main() -> None:
    parser = argparse.ArgumentParser(description="Colab runner for /auto-test-llm-colab endpoint")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--ngrok-token", default=None, help="Optional ngrok token; else uses NGROK_AUTH_TOKEN env var")
    parser.add_argument("--resume-file", default="", help="Optional local file path in Colab, e.g. /content/resume.pdf")
    parser.add_argument("--preprocess", action="store_true", default=True)
    parser.add_argument("--pdf-dpi", type=int, default=220)
    parser.add_argument("--mode", default="balanced", choices=["fast", "balanced", "resume_bert"])
    parser.add_argument("--llm-base-model-id", default="Qwen/Qwen2.5-3B-Instruct")
    parser.add_argument("--llm-adapter-path", default="models/lora_adapter")
    parser.add_argument("--llm-max-new-tokens", type=int, default=768)
    parser.add_argument("--no-auto-train", action="store_true", help="If set, endpoint runs LLM extraction without mapping retrain")
    parser.add_argument("--link-only", action="store_true", help="Only create ngrok link to existing local API; do not start uvicorn")
    parser.add_argument("--ocr-engine", default="paddle", choices=["paddle", "auto", "tesseract"])
    parser.add_argument(
        "--skip-system-deps-install",
        action="store_true",
        help="Skip auto-install check for tesseract/poppler (not recommended for scanned PDFs).",
    )
    args = parser.parse_args()
    os.environ["OCR_ENGINE"] = args.ocr_engine

    health_url = f"http://127.0.0.1:{args.port}/health"
    server_thread = None
    if args.link_only:
        if not is_server_up(health_url):
            raise RuntimeError(f"--link-only was set but API is not running at {health_url}")
    else:
        ensure_ocr_system_deps(auto_install=not args.skip_system_deps_install)
        if is_server_up(health_url):
            print(f"Detected running API at {health_url}; reusing existing server.")
        else:
            server_thread = Thread(target=run_server, args=(args.host, args.port), daemon=True)
            server_thread.start()
            wait_for_server(health_url, timeout_sec=90)

    public_url = start_ngrok_tunnel(args.port, args.ngrok_token)

    print(f"FastAPI local: http://127.0.0.1:{args.port}")
    print(f"FastAPI public (ngrok): {public_url}")
    print(f"Swagger docs: {public_url}/docs")
    print(f"OCR engine: {args.ocr_engine}")
    print("")
    print("Copy-paste command to call endpoint manually:")
    print(
        "curl -X POST "
        f"'{public_url}/auto-test-llm-colab' "
        "-F 'resume_file=@/content/resume.pdf' "
        "-F 'mode=balanced' "
        "-F 'auto_train=true'"
    )

    if args.resume_file:
        result = call_auto_test_llm_colab(
            base_url=public_url,
            resume_file=args.resume_file,
            preprocess=args.preprocess,
            pdf_dpi=args.pdf_dpi,
            mode=args.mode,
            llm_base_model_id=args.llm_base_model_id,
            llm_adapter_path=args.llm_adapter_path,
            llm_max_new_tokens=args.llm_max_new_tokens,
            auto_train=not args.no_auto_train,
        )
        print("")
        print("Endpoint response:")
        print(json.dumps(result, indent=2, ensure_ascii=False))

    if server_thread is not None:
        server_thread.join()


if __name__ == "__main__":
    main()
