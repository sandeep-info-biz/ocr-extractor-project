import argparse
import os
from threading import Thread

import uvicorn


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


def main() -> None:
    parser = argparse.ArgumentParser(description="Run FastAPI with ngrok tunnel (Colab-friendly)")
    parser.add_argument("--host", default="0.0.0.0", help="Host for uvicorn")
    parser.add_argument("--port", type=int, default=8000, help="Port for uvicorn and ngrok")
    parser.add_argument("--ngrok-token", default=None, help="Optional ngrok auth token")
    args = parser.parse_args()

    server_thread = Thread(target=run_server, args=(args.host, args.port), daemon=True)
    server_thread.start()

    public_url = start_ngrok_tunnel(args.port, args.ngrok_token)
    print(f"FastAPI local: http://{args.host}:{args.port}")
    print(f"FastAPI public (ngrok): {public_url}")
    print(f"Swagger docs: {public_url}/docs")

    server_thread.join()


if __name__ == "__main__":
    main()

