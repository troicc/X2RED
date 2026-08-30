from __future__ import annotations

import argparse
import importlib.util
import sys
import tempfile
from pathlib import Path

from sqlalchemy import text

ROOT = Path(__file__).resolve().parents[3]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="x2red")
    sub = parser.add_subparsers(dest="command")

    serve = sub.add_parser("serve", help="start the local web application")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8787)
    serve.add_argument("--reload", action="store_true")
    serve.add_argument("--skip-migrate", action="store_true")

    check_parser = sub.add_parser("check", help="validate the local environment")
    check_parser.add_argument(
        "--network",
        action="store_true",
        help="also verify the configured FxTwitter endpoint",
    )
    check_parser.add_argument(
        "--publisher",
        action="store_true",
        help="also launch a headless Playwright Chromium smoke check",
    )
    sub.add_parser("migrate", help="upgrade the local database schema")
    return parser


def migrate() -> int:
    from app.core.config import get_settings
    from app.db.schema import upgrade_database

    upgrade_database(get_settings().database_url)
    print("database migrations are up to date")
    return 0


def _check_writable(path: Path, label: str) -> None:
    path.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(prefix=".x2red-check-", dir=path, delete=True):
        pass
    print(f"{label}: {path.resolve()} [writable]")


def _check_network(base_url: str, timeout_seconds: float) -> None:
    import httpx

    url = base_url.rstrip("/") + "/2/trends"
    response = httpx.get(
        url,
        params={"type": "trending", "count": 1},
        timeout=max(5.0, timeout_seconds),
        follow_redirects=False,
        headers={"Accept": "application/json", "User-Agent": "X2RED environment check"},
    )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise RuntimeError("FxTwitter returned a non-object response")
    print(f"FxTwitter: {base_url} [reachable, HTTP {response.status_code}]")


def _check_publisher() -> None:
    if importlib.util.find_spec("playwright") is None:
        raise RuntimeError(
            "Playwright is not installed; run: pip install -e '.[publisher]'"
        )
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(headless=True)
        except Exception as exc:
            raise RuntimeError(
                "Chromium is not installed; run: python -m playwright install chromium"
            ) from exc
        browser.close()
    print("publisher: Playwright Chromium [ready]")


def check(*, network: bool = False, publisher: bool = False) -> int:
    from app.core.config import get_settings
    from app.db.schema import assert_schema_current
    from app.db.session import engine

    migrate()
    settings = get_settings()
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))
    assert_schema_current(engine)
    print(f"database: {settings.database_url} [connected]")
    _check_writable(settings.media_dir, "media")
    _check_writable(settings.raw_dir, "raw snapshots")
    _check_writable(settings.export_dir, "exports")
    _check_writable(settings.browser_profile_dir, "browser profile")
    if network:
        _check_network(settings.fxtwitter_base_url, settings.request_timeout_seconds)
    if publisher:
        _check_publisher()
    print("X2RED environment check passed")
    return 0


def main() -> int:
    args = build_parser().parse_args()
    command_name = args.command or "serve"
    if command_name == "check":
        return check(network=args.network, publisher=args.publisher)
    if command_name == "migrate":
        return migrate()
    if command_name == "serve":
        import uvicorn

        from app.core.config import get_settings
        from app.core.http_security import is_loopback_host

        settings = get_settings()
        if not is_loopback_host(args.host):
            if not settings.local_api_token and not settings.allow_insecure_non_loopback:
                print(
                    "refusing non-loopback bind without X2RED_LOCAL_API_TOKEN; "
                    "set a token or explicitly set X2RED_ALLOW_INSECURE_NON_LOOPBACK=true",
                    file=sys.stderr,
                )
                return 2
            print(
                "warning: X2RED is binding to a non-loopback interface; "
                "verify firewall, Origin policy, and local API token settings",
                file=sys.stderr,
            )

        if not args.skip_migrate:
            migrate()
        uvicorn.run(
            "app.main:app",
            app_dir=str(ROOT / "apps/api"),
            host=args.host,
            port=args.port,
            reload=args.reload,
        )
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
