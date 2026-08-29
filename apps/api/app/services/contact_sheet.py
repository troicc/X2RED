from __future__ import annotations

import io
import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps


class ContactSheetError(RuntimeError):
    pass


class ContactSheetRenderer:
    """Render compact numbered candidates without overlaying editorial copy."""

    version = "x2red-contact-sheet-v1"
    canvas_width = 1120
    cell_width = 520
    cell_height = 520
    gap = 26
    outer = 26
    label_height = 46

    def render(
        self,
        candidates: list[tuple[int, bytes]],
        output_path: Path,
        *,
        selected_index: int | None = None,
    ) -> Path:
        if not 1 <= len(candidates) <= 4:
            raise ContactSheetError("Contact Sheet 每次必须包含 1 到 4 张候选")
        columns = 2 if len(candidates) > 1 else 1
        rows = math.ceil(len(candidates) / columns)
        width = (
            self.canvas_width
            if columns == 2
            else self.cell_width + self.outer * 2
        )
        height = self.outer * 2 + rows * (self.cell_height + self.label_height) + (rows - 1) * self.gap
        canvas = Image.new("RGB", (width, height), "#e8e2d6")
        draw = ImageDraw.Draw(canvas)
        font = ImageFont.load_default(size=24)

        for position, (candidate_index, image_bytes) in enumerate(candidates):
            row = position // columns
            column = position % columns
            x = self.outer + column * (self.cell_width + self.gap)
            y = self.outer + row * (self.cell_height + self.label_height + self.gap)
            image = self._decode(image_bytes)
            fitted = ImageOps.contain(
                image,
                (self.cell_width, self.cell_height),
                Image.Resampling.LANCZOS,
            )
            plate = Image.new("RGB", (self.cell_width, self.cell_height), "#f5f1e8")
            plate.paste(
                fitted,
                ((self.cell_width - fitted.width) // 2, (self.cell_height - fitted.height) // 2),
            )
            canvas.paste(plate, (x, y))
            border = "#b72b25" if candidate_index == selected_index else "#6b665e"
            draw.rectangle(
                (x, y, x + self.cell_width - 1, y + self.cell_height - 1),
                outline=border,
                width=5 if candidate_index == selected_index else 2,
            )
            label = f"#{candidate_index}"
            draw.rounded_rectangle(
                (x, y + self.cell_height + 8, x + 72, y + self.cell_height + 40),
                radius=7,
                fill=border,
            )
            draw.text(
                (x + 14, y + self.cell_height + 11),
                label,
                fill="#fffdf7",
                font=font,
            )

        output_path.parent.mkdir(parents=True, exist_ok=True)
        canvas.save(output_path, format="PNG", optimize=True)
        return output_path

    @staticmethod
    def _decode(image_bytes: bytes) -> Image.Image:
        try:
            with Image.open(io.BytesIO(image_bytes)) as opened:
                image = ImageOps.exif_transpose(opened)
                image.load()
        except (OSError, ValueError, Image.DecompressionBombError) as exc:
            raise ContactSheetError("候选图片无法生成 Contact Sheet") from exc
        return image.convert("RGB")
