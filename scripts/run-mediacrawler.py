from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path


def parse_bool(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}


def parser() -> argparse.ArgumentParser:
    command = argparse.ArgumentParser()
    command.add_argument("--root", required=True)
    command.add_argument("--output", required=True)
    command.add_argument(
        "--platform",
        required=True,
        choices=("xhs", "dy", "ks", "bili", "wb", "tieba", "zhihu"),
    )
    command.add_argument(
        "--login-type",
        default="qrcode",
        choices=("qrcode", "phone", "cookie"),
    )
    command.add_argument("--keywords", required=True)
    command.add_argument("--max-results", type=int, default=20)
    command.add_argument("--cdp-port", type=int, default=9222)
    command.add_argument("--connect-existing", default="true")
    return command


async def run() -> None:
    args = parser().parse_args()
    root = Path(args.root).expanduser().resolve()
    output = Path(args.output).expanduser().resolve()
    if not (root / "main.py").is_file():
        raise SystemExit(f"MediaCrawler root is invalid: {root}")
    output.mkdir(parents=True, exist_ok=True)
    os.chdir(root)
    sys.path.insert(0, str(root))

    import config

    config.ENABLE_CDP_MODE = True
    config.CDP_CONNECT_EXISTING = parse_bool(args.connect_existing)
    config.CDP_DEBUG_PORT = args.cdp_port
    config.CDP_HEADLESS = False
    config.HEADLESS = False
    config.AUTO_CLOSE_BROWSER = False
    config.SAVE_LOGIN_STATE = True
    config.SAVE_DATA_OPTION = "jsonl"
    config.SAVE_DATA_PATH = str(output)
    config.ENABLE_GET_COMMENTS = False
    config.ENABLE_GET_SUB_COMMENTS = False
    config.ENABLE_GET_MEIDAS = False
    config.ENABLE_GET_WORDCLOUD = False
    config.MAX_CONCURRENCY_NUM = 1
    config.CRAWLER_MAX_NOTES_COUNT = max(1, args.max_results)
    config.CRAWLER_MAX_SLEEP_SEC = max(2, int(config.CRAWLER_MAX_SLEEP_SEC))

    sys.argv = [
        "main.py",
        "--platform",
        args.platform,
        "--lt",
        args.login_type,
        "--type",
        "search",
        "--keywords",
        args.keywords,
        "--save_data_option",
        "jsonl",
        "--save_data_path",
        str(output),
        "--crawler_max_notes_count",
        str(max(1, args.max_results)),
        "--max_concurrency_num",
        "1",
        "--get_comment",
        "false",
        "--get_sub_comment",
        "false",
        "--headless",
        "false",
    ]

    import main as mediacrawler_main

    await mediacrawler_main.main()


if __name__ == "__main__":
    asyncio.run(run())
