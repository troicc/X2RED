from __future__ import annotations

import hashlib
import math
import random
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont, ImageOps


VISUAL_STYLE_LABELS = {
    "minimal_zine": "极简杂志",
    "photo_editorial": "照片编辑",
    "classical_ink": "古典水墨",
    "dark_contemplative": "深色沉思",
    "seasonal_folk": "节气民艺",
    "old_newspaper": "旧报刊",
}

RECIPE_STYLE_DEFAULTS = {
    "comfort": "dark_contemplative",
    "mature_life": "photo_editorial",
    "seasonal": "seasonal_folk",
    "photo_quote": "photo_editorial",
    "short_commentary": "old_newspaper",
}


class LightVisualRenderer:
    width = 1200
    height = 2000

    def render(
        self,
        path: Path,
        *,
        spec: dict[str, Any],
        visual_style: str,
        hero_image: str,
        recipe: str,
        index: int,
        total: int,
    ) -> str:
        style = self.resolve_style(visual_style, recipe)
        seed_text = f"{style}:{spec.get('phrase')}:{spec.get('visual_metaphor')}:{index}"
        seed = int(hashlib.sha256(seed_text.encode("utf-8")).hexdigest()[:12], 16)
        rng = random.Random(seed)
        canvas = getattr(self, f"_render_{style}")(
            spec=spec,
            hero_image=hero_image,
            recipe=recipe,
            index=index,
            total=total,
            rng=rng,
        )
        canvas.save(path, format="PNG", optimize=True)
        return style

    @staticmethod
    def resolve_style(visual_style: str, recipe: str) -> str:
        value = str(visual_style or "auto")
        if value in VISUAL_STYLE_LABELS:
            return value
        return RECIPE_STYLE_DEFAULTS.get(recipe, "minimal_zine")

    def compile_prompt(
        self,
        spec: dict[str, Any],
        *,
        visual_style: str,
        recipe: str,
        index: int,
        total: int,
    ) -> str:
        style = self.resolve_style(visual_style, recipe)
        phrase = str(spec.get("phrase") or "").strip()
        note = str(spec.get("note") or "").strip()
        metaphor = str(spec.get("visual_metaphor") or "a single ordinary object").strip()
        photo_direction = str(spec.get("photo_direction") or "").strip()
        style_prompts = {
            "minimal_zine": (
                "Tall 3:5 aged-paper minimal zine poster, 78%-90% negative space, one tiny visual "
                "specimen, xerox grain, risograph ink wear, restrained serif typography"
            ),
            "photo_editorial": (
                "Tall 3:5 documentary editorial photograph, full-bleed or large cropped photo, quiet natural "
                "light, film grain, magazine caption system, minimal Chinese typography"
            ),
            "classical_ink": (
                "Tall 3:5 contemporary Chinese ink editorial poster, xuan paper, diluted ink wash, one poetic "
                "object or landscape fragment, cinnabar seal, generous breathing room"
            ),
            "dark_contemplative": (
                "Tall 3:5 dark contemplative editorial poster, charcoal paper, warm spotlight, bronze rule, "
                "museum-like object fragment, deep shadows, dignified serif Chinese typography"
            ),
            "seasonal_folk": (
                "Tall 3:5 Chinese seasonal folk editorial poster, traditional festival palette, paper-cut or "
                "woodblock-inspired botanical and food motifs, clear solar-term rhythm, warm lived-in texture"
            ),
            "old_newspaper": (
                "Tall 3:5 old Chinese newspaper opinion poster, yellowed newsprint, halftone photo, column rules, "
                "bold editorial headline, one vermilion correction mark, dry ink texture"
            ),
        }
        return (
            f"{style_prompts[style]}.\n"
            f"Visual anchor: {metaphor}. {photo_direction}\n"
            f"Use only this Chinese headline exactly: ‘{phrase}’. Optional small note: ‘{note}’.\n"
            "No logo, no brand mark, no CTA, no app interface, no glossy mockup, no dense long paragraph. "
            f"Poster {index} of {total}; style family: {VISUAL_STYLE_LABELS[style]}."
        )

    def _render_minimal_zine(
        self,
        *,
        spec: dict[str, Any],
        hero_image: str,
        recipe: str,
        index: int,
        total: int,
        rng: random.Random,
    ) -> Image.Image:
        canvas = self._paper("#e9e0d0", noise=15, blend=0.075)
        draw = ImageDraw.Draw(canvas)
        accent = self._accent(spec, "#1646d8")
        phrase, note = self._copy(spec)
        x = rng.choice((110, 145, 620))
        y = rng.choice((280, 390, 1040))
        box = (x, y, x + rng.randint(250, 390), y + rng.randint(210, 390))
        hero = self._hero_crop(hero_image, (box[2] - box[0], box[3] - box[1]), color=0.12, contrast=0.76)
        if hero is not None and index % 2:
            canvas.paste(hero, (box[0], box[1]))
            draw.rectangle(box, outline="#4c474055", width=2)
            draw.rectangle((box[2] - 54, box[1], box[2], box[3]), fill=accent)
        else:
            self._small_specimen(draw, box, accent, index)
        text_x = 110 if x > 400 else 610
        text_y = 420 if y > 760 else min(box[3] + 110, 1320)
        self._draw_text(
            draw,
            phrase,
            note,
            x=text_x,
            y=text_y,
            width=470 if text_x > 400 else 930,
            title_size=62,
            title_color="#25211e",
            note_color="#716960",
            serif=True,
        )
        draw.text((78, self.height - 82), f"NOTE {index:02d}/{total:02d}", font=self._font(19), fill="#777067")
        draw.ellipse((self.width - 105, 72, self.width - 73, 104), fill=accent)
        return canvas.filter(ImageFilter.GaussianBlur(0.12))

    def _render_photo_editorial(
        self,
        *,
        spec: dict[str, Any],
        hero_image: str,
        recipe: str,
        index: int,
        total: int,
        rng: random.Random,
    ) -> Image.Image:
        hero = self._hero_crop(hero_image, (self.width, self.height), color=0.72, contrast=0.93)
        if hero is None:
            hero = self._synthetic_photo(rng, warm=recipe in {"mature_life", "comfort"})
        canvas = hero
        overlay = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
        o = ImageDraw.Draw(overlay)
        o.rectangle((0, 0, self.width, 330), fill=(15, 18, 20, 55))
        o.rectangle((0, 1120, self.width, self.height), fill=(13, 15, 16, 165))
        o.rectangle((0, 0, 18, self.height), fill=self._hex_rgba(self._accent(spec, "#e55439"), 230))
        canvas = Image.alpha_composite(canvas.convert("RGBA"), overlay).convert("RGB")
        draw = ImageDraw.Draw(canvas)
        phrase, note = self._copy(spec)
        draw.text((72, 86), f"PHOTO ESSAY · {index:02d}/{total:02d}", font=self._font(22, bold=True), fill="#f5f1e8")
        self._draw_text(
            draw,
            phrase,
            note,
            x=72,
            y=1260,
            width=1045,
            title_size=76,
            title_color="#fffaf0",
            note_color="#ded8cc",
            serif=True,
            max_lines=4,
        )
        draw.line((72, 1840, 1128, 1840), fill="#e8e0d188", width=2)
        draw.text((72, 1870), str(spec.get("visual_metaphor") or "生活现场")[:42], font=self._font(20), fill="#ded8cc")
        return canvas

    def _render_classical_ink(
        self,
        *,
        spec: dict[str, Any],
        hero_image: str,
        recipe: str,
        index: int,
        total: int,
        rng: random.Random,
    ) -> Image.Image:
        canvas = self._paper("#eee6d5", noise=10, blend=0.045)
        wash = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
        w = ImageDraw.Draw(wash)
        for layer in range(7):
            base_y = 1080 + layer * 70
            points = [(0, self.height)]
            for x in range(-80, self.width + 160, 130):
                wave = math.sin((x / 170) + layer) * 70
                points.append((x, base_y + wave + rng.randint(-55, 55)))
            points.extend([(self.width, self.height)])
            shade = 22 + layer * 7
            w.polygon(points, fill=(28, 31, 29, max(12, 48 - layer * 5)))
        for _ in range(8):
            cx = rng.randint(80, 1120)
            cy = rng.randint(220, 1480)
            r = rng.randint(45, 180)
            w.ellipse((cx - r, cy - r, cx + r, cy + r), fill=(33, 36, 32, rng.randint(5, 16)))
        wash = wash.filter(ImageFilter.GaussianBlur(18))
        canvas = Image.alpha_composite(canvas.convert("RGBA"), wash).convert("RGB")
        draw = ImageDraw.Draw(canvas)
        phrase, note = self._copy(spec)
        accent = self._accent(spec, "#a33a28")
        draw.rectangle((930, 180, 1000, 250), fill=accent)
        draw.text((946, 193), "记", font=self._font(32, bold=True, serif=True), fill="#f5e9d5")
        self._draw_text(
            draw,
            phrase,
            note,
            x=112,
            y=330,
            width=760,
            title_size=68,
            title_color="#252a27",
            note_color="#635f57",
            serif=True,
            max_lines=4,
        )
        self._draw_ink_branch(draw, rng, accent)
        draw.text((1050, 1620), f"{index:02d}", font=self._font(26, serif=True), fill="#5b5a55")
        draw.text((1048, 1682), f"共{total}页", font=self._font(18, serif=True), fill="#77736b")
        return canvas

    def _render_dark_contemplative(
        self,
        *,
        spec: dict[str, Any],
        hero_image: str,
        recipe: str,
        index: int,
        total: int,
        rng: random.Random,
    ) -> Image.Image:
        canvas = self._paper("#171816", noise=28, blend=0.09)
        glow = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
        g = ImageDraw.Draw(glow)
        cx, cy = rng.randint(720, 980), rng.randint(480, 830)
        for radius in range(420, 30, -24):
            alpha = max(0, int(2 + (420 - radius) * 0.025))
            g.ellipse((cx - radius, cy - radius, cx + radius, cy + radius), fill=(214, 174, 104, alpha))
        glow = glow.filter(ImageFilter.GaussianBlur(42))
        canvas = Image.alpha_composite(canvas.convert("RGBA"), glow).convert("RGB")
        draw = ImageDraw.Draw(canvas)
        phrase, note = self._copy(spec)
        accent = self._accent(spec, "#b58a4b")
        hero = self._hero_crop(hero_image, (410, 520), color=0.08, contrast=1.1)
        if hero is not None:
            hero = ImageOps.colorize(hero.convert("L"), black="#171816", white="#c5b99f")
            canvas.paste(hero, (680, 360))
            draw.rectangle((680, 360, 1090, 880), outline=accent, width=2)
        else:
            draw.ellipse((760, 430, 990, 660), outline=accent, width=4)
            draw.line((875, 660, 875, 910), fill=accent, width=3)
            draw.ellipse((842, 875, 908, 941), fill=accent)
        draw.text((80, 76), "QUIET EDITION", font=self._font(20, bold=True), fill=accent)
        draw.line((80, 118, 1120, 118), fill="#75644a", width=1)
        self._draw_text(
            draw,
            phrase,
            note,
            x=80,
            y=1040,
            width=990,
            title_size=78,
            title_color="#eee5d4",
            note_color="#aca28f",
            serif=True,
            max_lines=4,
        )
        draw.text((80, 1900), f"{index:02d} / {total:02d}", font=self._font(20), fill="#8b7b62")
        return canvas

    def _render_seasonal_folk(
        self,
        *,
        spec: dict[str, Any],
        hero_image: str,
        recipe: str,
        index: int,
        total: int,
        rng: random.Random,
    ) -> Image.Image:
        palettes = [
            ("#f0d99b", "#233f35", "#c7462f"),
            ("#d8e1c3", "#304f3c", "#dc6f31"),
            ("#e8d5c5", "#58372d", "#b3282d"),
            ("#d5e2e1", "#24445b", "#d6962f"),
        ]
        paper, ink, default_accent = palettes[(index - 1) % len(palettes)]
        canvas = self._paper(paper, noise=13, blend=0.055)
        draw = ImageDraw.Draw(canvas)
        accent = self._accent(spec, default_accent)
        self._folk_border(draw, ink, accent)
        phrase, note = self._copy(spec)
        draw.text((94, 92), "时令生活", font=self._font(24, bold=True, serif=True), fill=ink)
        draw.text((1030, 92), f"{index:02d}", font=self._font(24, bold=True), fill=accent)
        self._draw_seasonal_motif(draw, rng, ink, accent, index)
        self._draw_text(
            draw,
            phrase,
            note,
            x=120,
            y=1060,
            width=950,
            title_size=78,
            title_color=ink,
            note_color="#5f5a4e",
            serif=True,
            max_lines=4,
        )
        draw.rectangle((120, 1780, 1080, 1786), fill=ink)
        draw.text((120, 1822), "顺时而食，也要因人、因地、因体感调整", font=self._font(22, serif=True), fill=ink)
        return canvas

    def _render_old_newspaper(
        self,
        *,
        spec: dict[str, Any],
        hero_image: str,
        recipe: str,
        index: int,
        total: int,
        rng: random.Random,
    ) -> Image.Image:
        canvas = self._paper("#dfd3b7", noise=22, blend=0.095)
        draw = ImageDraw.Draw(canvas)
        ink = "#24231f"
        accent = self._accent(spec, "#a8332b")
        phrase, note = self._copy(spec)
        draw.rectangle((70, 70, 1130, 1928), outline=ink, width=4)
        draw.text((90, 92), "今日短评", font=self._font(32, bold=True, serif=True), fill=ink)
        draw.text((920, 98), f"第{index}版 / 共{total}版", font=self._font(20), fill=ink)
        draw.line((90, 154, 1110, 154), fill=ink, width=4)
        draw.line((90, 174, 1110, 174), fill=ink, width=1)
        self._draw_text(
            draw,
            phrase,
            "",
            x=92,
            y=235,
            width=1010,
            title_size=84,
            title_color=ink,
            note_color=ink,
            serif=False,
            max_lines=4,
        )
        image_box = (92, 690, 1108, 1260)
        hero = self._hero_crop(hero_image, (image_box[2] - image_box[0], image_box[3] - image_box[1]), color=0.0, contrast=1.25)
        if hero is not None:
            hero = hero.convert("L").point(lambda p: 255 if p > 135 else 35)
            hero = ImageOps.colorize(hero, black=ink, white="#d9ceb3")
            canvas.paste(hero, (image_box[0], image_box[1]))
        else:
            self._newspaper_placeholder(draw, image_box, rng, accent)
        draw.rectangle(image_box, outline=ink, width=3)
        if note:
            columns = self._split_columns(note, 3)
            for col_index, text in enumerate(columns):
                x = 92 + col_index * 345
                draw.line((x, 1330, x + 300, 1330), fill=ink, width=2)
                for line_no, line in enumerate(self._wrap(draw, text, self._font(24, serif=True), 300)[:9]):
                    draw.text((x, 1360 + line_no * 40), line, font=self._font(24, serif=True), fill=ink)
        draw.ellipse((1035, 1810, 1090, 1865), outline=accent, width=8)
        draw.line((1005, 1800, 1115, 1875), fill=accent, width=5)
        return canvas

    def _paper(self, color: str, *, noise: int, blend: float) -> Image.Image:
        canvas = Image.new("RGB", (self.width, self.height), color)
        texture = Image.effect_noise((self.width, self.height), noise).convert("L")
        texture = ImageEnhance.Contrast(texture).enhance(0.45)
        rgb = Image.merge("RGB", (texture, texture, texture))
        return Image.blend(canvas, rgb, blend)

    def _synthetic_photo(self, rng: random.Random, *, warm: bool) -> Image.Image:
        base = Image.new("RGB", (self.width, self.height), "#756b59" if warm else "#50606a")
        layer = Image.new("RGBA", base.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(layer)
        for _ in range(18):
            x = rng.randint(-250, self.width)
            y = rng.randint(-250, self.height)
            r = rng.randint(180, 650)
            color = (224, 183, 124, rng.randint(12, 42)) if warm else (128, 170, 186, rng.randint(12, 40))
            draw.ellipse((x, y, x + r, y + r), fill=color)
        draw.rectangle((160, 520, 520, 1560), fill=(42, 39, 34, 100))
        draw.rectangle((610, 260, 1030, 1120), fill=(226, 218, 194, 48))
        layer = layer.filter(ImageFilter.GaussianBlur(80))
        image = Image.alpha_composite(base.convert("RGBA"), layer).convert("RGB")
        return ImageEnhance.Contrast(image).enhance(0.92)

    @staticmethod
    def _accent(spec: dict[str, Any], fallback: str) -> str:
        value = str(spec.get("accent") or fallback)
        return value if len(value) == 7 and value.startswith("#") else fallback

    @staticmethod
    def _hex_rgba(value: str, alpha: int) -> tuple[int, int, int, int]:
        try:
            return int(value[1:3], 16), int(value[3:5], 16), int(value[5:7], 16), alpha
        except (TypeError, ValueError):
            return 48, 75, 190, alpha

    @staticmethod
    def _copy(spec: dict[str, Any]) -> tuple[str, str]:
        return str(spec.get("phrase") or "").strip(), str(spec.get("note") or "").strip()

    def _hero_crop(
        self,
        hero_image: str,
        size: tuple[int, int],
        *,
        color: float,
        contrast: float,
    ) -> Image.Image | None:
        path = Path(hero_image) if hero_image else None
        if not path or not path.is_file():
            return None
        try:
            with Image.open(path).convert("RGB") as source:
                return ImageOps.fit(source, size, method=Image.Resampling.LANCZOS).filter(
                    ImageFilter.GaussianBlur(0.25)
                ) if color >= 0.95 and contrast == 1 else ImageEnhance.Contrast(
                    ImageEnhance.Color(
                        ImageOps.fit(source, size, method=Image.Resampling.LANCZOS)
                    ).enhance(color)
                ).enhance(contrast)
        except OSError:
            return None

    def _draw_text(
        self,
        draw: ImageDraw.ImageDraw,
        phrase: str,
        note: str,
        *,
        x: int,
        y: int,
        width: int,
        title_size: int,
        title_color: str,
        note_color: str,
        serif: bool,
        max_lines: int = 3,
    ) -> None:
        title_font = self._font(title_size, bold=False, serif=serif)
        note_font = self._font(max(24, int(title_size * 0.34)), serif=serif)
        for line in self._wrap(draw, phrase, title_font, width)[:max_lines]:
            draw.text((x, y), line, font=title_font, fill=title_color)
            y += int(title_size * 1.28)
        if note:
            y += 24
            for line in self._wrap(draw, note, note_font, width)[:3]:
                draw.text((x, y), line, font=note_font, fill=note_color)
                y += int(getattr(note_font, "size", 26) * 1.55)

    @staticmethod
    def _small_specimen(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], accent: str, index: int) -> None:
        left, top, right, bottom = box
        if index % 3 == 0:
            draw.ellipse(box, fill=accent)
            draw.ellipse((left + 60, top + 50, right - 40, bottom - 70), fill="#e9e0d0")
        elif index % 3 == 1:
            draw.rectangle(box, fill="#aaa195", outline="#46413b", width=2)
            draw.rectangle((right - 65, top, right, bottom), fill=accent)
            for row in range(6):
                y = top + 35 + row * 36
                draw.line((left + 28, y, right - 90, y), fill="#625c53", width=2)
        else:
            draw.polygon([(left, bottom), ((left + right) // 2, top), (right, bottom)], fill=accent)
            draw.line((left - 20, top + 40, right + 20, bottom - 20), fill="#4c4740", width=3)

    @staticmethod
    def _draw_ink_branch(draw: ImageDraw.ImageDraw, rng: random.Random, accent: str) -> None:
        points = [(1000, 760), (910, 900), (820, 1060), (730, 1240)]
        draw.line(points, fill="#30332f", width=8)
        for x, y in points[1:]:
            for direction in (-1, 1):
                length = rng.randint(80, 155)
                draw.line((x, y, x + direction * length, y - rng.randint(60, 130)), fill="#41433e", width=4)
                draw.ellipse((x + direction * length - 18, y - 145, x + direction * length + 18, y - 109), fill=accent)

    @staticmethod
    def _folk_border(draw: ImageDraw.ImageDraw, ink: str, accent: str) -> None:
        draw.rectangle((70, 70, 1130, 1930), outline=ink, width=3)
        for x in range(92, 1110, 64):
            draw.polygon([(x, 72), (x + 18, 92), (x + 36, 72)], fill=accent if (x // 64) % 2 else ink)
            draw.polygon([(x, 1928), (x + 18, 1908), (x + 36, 1928)], fill=accent if (x // 64) % 2 else ink)

    @staticmethod
    def _draw_seasonal_motif(draw: ImageDraw.ImageDraw, rng: random.Random, ink: str, accent: str, index: int) -> None:
        cx, cy = 600, 620
        if index % 3 == 1:
            draw.ellipse((cx - 210, cy - 210, cx + 210, cy + 210), fill=accent)
            draw.arc((cx - 300, cy - 120, cx + 300, cy + 260), 15, 165, fill=ink, width=16)
            for angle in range(0, 360, 30):
                x = cx + int(math.cos(math.radians(angle)) * 280)
                y = cy + int(math.sin(math.radians(angle)) * 280)
                draw.line((cx, cy, x, y), fill=ink, width=3)
        elif index % 3 == 2:
            draw.arc((330, 370, 870, 920), 0, 180, fill=ink, width=18)
            draw.line((360, 650, 840, 650), fill=ink, width=10)
            for offset in (-120, 0, 120):
                draw.ellipse((cx + offset - 55, 500, cx + offset + 55, 610), fill=accent)
        else:
            for offset in range(-230, 231, 90):
                draw.line((cx, 850, cx + offset, 380), fill=ink, width=8)
                draw.ellipse((cx + offset - 45, 360, cx + offset + 45, 450), fill=accent)

    @staticmethod
    def _newspaper_placeholder(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], rng: random.Random, accent: str) -> None:
        left, top, right, bottom = box
        draw.rectangle(box, fill="#c8bea4")
        for row in range(12):
            y = top + 20 + row * 42
            length = rng.randint(420, right - left - 60)
            draw.line((left + 28, y, left + length, y), fill="#5a554a", width=4)
        draw.rectangle((right - 210, top + 50, right - 65, top + 195), outline=accent, width=12)

    @staticmethod
    def _split_columns(text: str, count: int) -> list[str]:
        chars = list(text)
        size = max(1, math.ceil(len(chars) / count))
        values = ["".join(chars[index * size:(index + 1) * size]) for index in range(count)]
        return values

    @staticmethod
    def _font(size: int, *, bold: bool = False, serif: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
        candidates = (
            [
                "/System/Library/Fonts/Songti.ttc",
                "/System/Library/Fonts/STSong.ttf",
                "/usr/share/fonts/opentype/noto/NotoSerifCJK-Regular.ttc",
                "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf",
            ]
            if serif
            else [
                "/System/Library/Fonts/PingFang.ttc",
                "/System/Library/Fonts/STHeiti Medium.ttc",
                "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc" if bold else "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
                "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            ]
        )
        for candidate in candidates:
            path = Path(candidate)
            if path.is_file():
                try:
                    return ImageFont.truetype(str(path), size=size)
                except OSError:
                    continue
        return ImageFont.load_default()

    @staticmethod
    def _wrap(
        draw: ImageDraw.ImageDraw,
        text: str,
        font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
        max_width: int,
    ) -> list[str]:
        lines: list[str] = []
        current = ""
        for char in text:
            candidate = current + char
            if current and draw.textlength(candidate, font=font) > max_width:
                lines.append(current)
                current = char
            else:
                current = candidate
        if current:
            lines.append(current)
        return lines
