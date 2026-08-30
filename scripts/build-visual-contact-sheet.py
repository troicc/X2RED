#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image, ImageDraw


def build_contact_sheet(source_dir: Path, output: Path) -> int:
    sources = [
        path
        for path in sorted(source_dir.glob("*.png"))
        if path.resolve() != output.resolve()
    ]
    if not sources:
        raise RuntimeError("no PNG screenshots found for contact sheet")
    cards: list[tuple[str, Image.Image]] = []
    for source in sources:
        with Image.open(source) as opened:
            image = opened.convert("RGB")
        image.thumbnail((600, 520), Image.Resampling.LANCZOS)
        cards.append((source.name, image))
    columns = 2
    cell_width, cell_height = 640, 580
    rows = (len(cards) + columns - 1) // columns
    sheet = Image.new("RGB", (columns * cell_width, rows * cell_height), "#ece7de")
    draw = ImageDraw.Draw(sheet)
    for index, (label, image) in enumerate(cards):
        column, row = index % columns, index // columns
        left = column * cell_width + (cell_width - image.width) // 2
        top = row * cell_height + 42
        draw.rounded_rectangle(
            (column * cell_width + 14, row * cell_height + 14, (column + 1) * cell_width - 14, (row + 1) * cell_height - 14),
            radius=18,
            fill="#ffffff",
            outline="#c9c1b5",
            width=2,
        )
        draw.text((column * cell_width + 28, row * cell_height + 24), label, fill="#2a2926")
        sheet.paste(image, (left, top))
    output.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(output, format="PNG", optimize=True)
    return len(cards)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    count = build_contact_sheet(args.source_dir, args.output)
    print(f"visual contact sheet: {count} screenshots -> {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
