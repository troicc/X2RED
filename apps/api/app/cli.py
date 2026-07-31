from __future__ import annotations

import argparse
from pathlib import Path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="x2red")
    sub = parser.add_subparsers(dest="command")

    serve = sub.add_parser("serve", help="start the local web application")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8787)
    serve.add_argument("--reload", action="store_true")

    sub.add_parser("check", help="validate the local environment")
    return parser


def check() -> int:
    from app.core.config import get_settings
    from app.db.base import Base
    from app.db.session import engine

    settings = get_settings()
    Base.metadata.create_all(engine)
    print(f"database: {settings.database_url}")
    print(f"media: {settings.media_dir.resolve()}")
    print(f"raw snapshots: {settings.raw_dir.resolve()}")
    print(f"exports: {settings.export_dir.resolve()}")
    print("X2RED environment check passed")
    return 0


def main() -> int:
    args = build_parser().parse_args()
    command = args.command or "serve"
    if command == "check":
        return check()
    if command == "serve":
        import uvicorn

        uvicorn.run(
            "app.main:app",
            app_dir=str(Path(__file__).resolve().parents[2]),
            host=args.host,
            port=args.port,
            reload=args.reload,
        )
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
