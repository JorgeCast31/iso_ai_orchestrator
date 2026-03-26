"""
Start the ISO Orchestrator local server.

Usage:
    python run_server.py
    python run_server.py --port 8080
"""
import argparse
import logging

import uvicorn

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)


def main() -> None:
    parser = argparse.ArgumentParser(description="ISO Orchestrator local server")
    parser.add_argument("--host", default="127.0.0.1", help="Bind address (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8000, help="Port (default: 8000)")
    parser.add_argument("--reload", action="store_true", help="Enable hot-reload (dev mode)")
    args = parser.parse_args()

    print(f"\n  ISO Orchestrator")
    print(f"  ─────────────────────────────────────")
    print(f"  UI:  http://{args.host}:{args.port}/")
    print(f"  API: http://{args.host}:{args.port}/api/docs")
    print(f"  ─────────────────────────────────────\n")

    uvicorn.run(
        "src.api:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
    )


if __name__ == "__main__":
    main()
