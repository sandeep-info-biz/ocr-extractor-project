import argparse

from app.api import run_async_worker_loop


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Async OCR worker for queued parse jobs")
    parser.add_argument("--poll-seconds", type=float, default=0.8, help="Queue poll interval in seconds")
    parser.add_argument("--max-attempts", type=int, default=3, help="Max attempts per queued job")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    run_async_worker_loop(poll_seconds=args.poll_seconds, max_attempts=args.max_attempts)


if __name__ == "__main__":
    main()
