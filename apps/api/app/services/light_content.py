from __future__ import annotations

import hashlib
import html
import json
import random
import re
import zipfile
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

import httpx
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.domain.models import DraftRevision, SourceItem
from app.domain.platforms import PlatformVariant, PlatformVariantState
from app.services.editorial import EditorialService
from app.services.publication_safety import strip_internal_markers
from app.services.skills import binding_for


class LightContentError(RuntimeError):
    pass


@dataclass(frozen=True)
class LightRenderValidation:
    errors: list[str]
    warnings: list[str]


RECIPE_LABELS = {
    "comfort": "人生慰藉",
    "mature_life": "中老年生活共鸣",
    "seasonal": "节气时令",
    "photo_quote": "照片短句",
    "short_commentary": "一句短评",
}

RECIPE_GUIDES = {
    "comfort": (
        "面向高压生活中的普通读者，给出克制、具体、不说教的安慰。"
        "不要承诺一切会变好，不制造焦虑，也不使用鸡汤口号。"
    ),
    "mature_life": (
        "面向中年与年长读者，语气平等、有生活经验但不居高临下。"
        "围绕关系、节奏、三餐、睡眠、家庭与自我照顾；不做诊断和医疗功效承诺。"
    ),
    "seasonal": (
        "围绕中国节气、物候、入伏、换季或当下饮食习惯，写成文化与生活提醒。"
        "饮食建议必须说明因人因地调整，不声称治病、排毒、降三高或替代医疗。"
    ),
    "photo_quote": (
        "让照片或单一物件承担主要叙事，文字极少，像一本安静杂志里的页间句。"
        "不要解释照片，不写完整长段。"
    ),
    "short_commentary": (
        "从来源中抓住一个现实矛盾，写一句判断和一小段解释。"
        "立场清晰但不煽动，不把复杂问题压成廉价金句。"
    ),
}

ACCENTS = (
    "#1646d8",
    "#d63c2f",
    "#f0b429",
    "#5c3ac7",
    "#16845b",
    "#df4f86",
)

PAPER_TONES = {
    "zen": "#e9e0d0",
    "olive": "#e7e1cf",
    "vermillion": "#eadfce",
    "graphite": "#e4dfd5",
    "editorial_blue": "#eee7d9",
    "receipt": "#ede9df",
    "auto": "#e9e1d3",
}


def _poster_copy_key(value: Any) -> str:
    return re.sub(r"[^0-9a-zA-Z\u4e00-\u9fff]+", "", str(value or "")).casefold()


def _poster_copy_near_duplicate(first: Any, second: Any) -> bool:
    left = _poster_copy_key(first)
    right = _poster_copy_key(second)
    if not left or not right:
        return False
    if left == right:
        return True
    shorter = min(len(left), len(right))
    longer = max(len(left), len(right))
    if shorter < 10 or shorter / max(longer, 1) < 0.72:
        return False
    if left in right or right in left:
        return True
    return SequenceMatcher(None, left, right).ratio() >= 0.88


def poster_copy_issues(posters: list[dict[str, Any]]) -> list[str]:
    """Return cross-page copy collisions that make a carousel read like a splice."""

    issues: list[str] = []
    for index, poster in enumerate(posters, start=1):
        phrase = poster.get("phrase")
        note = poster.get("note")
        if not _poster_copy_key(phrase):
            issues.append(f"page_{index}_missing_phrase")
        if note and _poster_copy_near_duplicate(phrase, note):
            issues.append(f"page_{index}_phrase_repeats_own_note")

    for left_index, left in enumerate(posters):
        for right_index in range(left_index + 1, len(posters)):
            right = posters[right_index]
            comparisons = (
                ("phrase", "phrase"),
                ("phrase", "note"),
                ("note", "phrase"),
                ("note", "note"),
            )
            for left_field, right_field in comparisons:
                left_value = left.get(left_field)
                right_value = right.get(right_field)
                if not left_value or not right_value:
                    continue
                if _poster_copy_near_duplicate(left_value, right_value):
                    issues.append(
                        f"page_{left_index + 1}_{left_field}_repeats_"
                        f"page_{right_index + 1}_{right_field}"
                    )
    return list(dict.fromkeys(issues))


class LightContentService:
    """Create short WeChat content and sparse 3:5 zine-style poster series."""

    width = 1200
    height = 2000

    def __init__(self, settings: Settings, editorial: EditorialService) -> None:
        self.settings = settings
        self.editorial = editorial

    async def create_variant(
        self,
        db: Session,
        *,
        source: SourceItem,
        draft: DraftRevision | None,
        recipe: str,
        image_count: int,
        seasonal_topic: str,
        audience: str,
        tone: str,
        theme: str,
        author: str,
    ) -> PlatformVariant:
        if recipe not in RECIPE_LABELS:
            raise LightContentError("不支持的轻内容配方")
        count = min(max(int(image_count), 3), 6)
        title_binding = binding_for(db, "wechat.title_summary", self.settings.model_name)
        visual_binding = binding_for(db, "visual.art_direction", self.settings.model_name)
        output: dict[str, Any] | None = None
        if (
            title_binding.enabled
            and visual_binding.enabled
            and self.settings.model_base_url
            and (title_binding.model_name or self.settings.model_name)
        ):
            output = await self._generate_model_copy(
                source=source,
                draft=draft,
                recipe=recipe,
                image_count=count,
                seasonal_topic=seasonal_topic,
                audience=audience,
                tone=tone,
                model_name=title_binding.model_name,
                reasoning_effort=title_binding.reasoning_effort,
            )
        if output is None:
            output = self._fallback_copy(
                source=source,
                draft=draft,
                recipe=recipe,
                image_count=count,
                seasonal_topic=seasonal_topic,
                audience=audience,
            )
            generator = "light-content-structured-fallback"
        else:
            generator = "light-content-model-skill-pack"

        normalized = self._normalize_output(
            output,
            source=source,
            recipe=recipe,
            image_count=count,
            seasonal_topic=seasonal_topic,
        )
        metadata = {
            "generator": generator,
            "content_mode": "light_series",
            "recipe": recipe,
            "recipe_label": RECIPE_LABELS[recipe],
            "audience": audience.strip(),
            "tone": tone.strip(),
            "seasonal_topic": seasonal_topic.strip(),
            "author": author.strip(),
            "poster_specs": normalized["posters"],
            "source_skill": {
                "repository": "LiamGvchi/gc-minimal-zine-poster",
                "skill_name": "gc-minimal-zine-poster-v0-1",
                "license": "MIT",
                "integration_mode": "native-adaptation",
            },
            "safety": {
                "medical_claims_forbidden": recipe in {"mature_life", "seasonal"},
                "human_review_required": True,
            },
        }
        variant = PlatformVariant(
            source_id=source.id,
            base_draft_id=draft.id if draft else None,
            platform="wechat",
            format="light_series",
            version=self._next_version(db, source.id),
            title=normalized["title"][:160],
            subtitle=normalized["subtitle"][:240],
            summary=normalized["summary"][:1000],
            body_markdown=normalized["body_markdown"][:50000],
            tags=normalized["tags"][:1000],
            theme=theme,
            skill_profile_json=json.dumps(
                {
                    "wechat.title_summary": {
                        "enabled": title_binding.enabled,
                        "model": title_binding.model_name or self.settings.model_name,
                        "reasoning_effort": title_binding.reasoning_effort,
                    },
                    "visual.art_direction": {
                        "enabled": visual_binding.enabled,
                        "model": visual_binding.model_name or self.settings.model_name,
                        "reasoning_effort": visual_binding.reasoning_effort,
                    },
                    "gc-minimal-zine-poster-v0-1": {
                        "enabled": True,
                        "integration_mode": "native-adaptation",
                    },
                },
                ensure_ascii=False,
            ),
            metadata_json=json.dumps(metadata, ensure_ascii=False),
            status=PlatformVariantState.draft.value,
            created_by="model" if generator.endswith("skill-pack") else "system",
        )
        db.add(variant)
        db.flush()
        return variant

    def render_variant(
        self,
        db: Session,
        variant: PlatformVariant,
        *,
        package: bool = True,
    ) -> tuple[PlatformVariant, LightRenderValidation, dict[str, str]]:
        if variant.platform != "wechat" or variant.format != "light_series":
            raise LightContentError("当前版本不是公众号轻内容图组")
        source = db.get(SourceItem, variant.source_id)
        if source is None:
            raise LightContentError("轻内容版本关联来源不存在")
        metadata = self._json_object(variant.metadata_json)
        specs = metadata.get("poster_specs")
        if not isinstance(specs, list) or not specs:
            raise LightContentError("图组故事板不存在")

        output_dir = self.settings.export_dir / "wechat" / variant.id
        output_dir.mkdir(parents=True, exist_ok=True)
        hero_image = self._hero_image(source)
        files: dict[str, str] = {}
        rendered_specs: list[dict[str, Any]] = []
        for index, raw in enumerate(specs[:6], start=1):
            spec = raw if isinstance(raw, dict) else {}
            path = output_dir / f"poster-{index:02d}.png"
            prompt = self._compile_prompt(spec, index=index, total=len(specs))
            spec = {**spec, "final_prompt": prompt}
            self._render_poster(
                path,
                spec=spec,
                theme=variant.theme,
                hero_image=hero_image,
                index=index,
                total=len(specs),
            )
            files[f"poster_{index:02d}"] = str(path.resolve())
            rendered_specs.append(spec)

        metadata["poster_specs"] = rendered_specs
        metadata["render_engine"] = "x2red-minimal-zine-pillow"
        metadata["validation"] = {
            "errors": [],
            "warnings": ["轻内容中的时令、饮食和生活建议仍需人工核对。"]
            if metadata.get("recipe") in {"seasonal", "mature_life"}
            else [],
        }
        variant.metadata_json = json.dumps(metadata, ensure_ascii=False)

        article_md = output_dir / "article.md"
        article_md.write_text(variant.body_markdown, encoding="utf-8")
        files["markdown"] = str(article_md.resolve())
        manifest = output_dir / "manifest.json"
        manifest.write_text(
            json.dumps(
                {
                    "variant_id": variant.id,
                    "platform": "wechat",
                    "format": "light_series",
                    "title": variant.title,
                    "summary": variant.summary,
                    "recipe": metadata.get("recipe"),
                    "posters": [Path(value).name for key, value in files.items() if key.startswith("poster_")],
                    "poster_specs": rendered_specs,
                    "source_skill": metadata.get("source_skill"),
                    "safety": metadata.get("safety"),
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        files["manifest"] = str(manifest.resolve())
        preview = output_dir / "preview.html"
        preview.write_text(self._preview_document(variant, rendered_specs), encoding="utf-8")
        files["preview"] = str(preview.resolve())
        variant.body_html = self._body_fragment(variant)

        if package:
            archive_path = output_dir / f"wechat-light-series-{variant.id}.zip"
            with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                for value in files.values():
                    path = Path(value)
                    if path.is_file():
                        archive.write(path, arcname=path.name)
            files["package"] = str(archive_path.resolve())
            variant.status = PlatformVariantState.packaged.value
        else:
            variant.status = PlatformVariantState.rendered.value
        variant.output_paths_json = json.dumps(files, ensure_ascii=False)
        variant.error = ""
        db.flush()
        return (
            variant,
            LightRenderValidation(
                errors=[],
                warnings=list(metadata["validation"]["warnings"]),
            ),
            files,
        )

    async def _generate_model_copy(
        self,
        *,
        source: SourceItem,
        draft: DraftRevision | None,
        recipe: str,
        image_count: int,
        seasonal_topic: str,
        audience: str,
        tone: str,
        model_name: str,
        reasoning_effort: str,
    ) -> dict[str, Any] | None:
        source_text = draft.body if draft and draft.body.strip() else source.text_original
        prompt = f"""
把下面材料制作成微信公众号“轻内容图组”，不是长文。

内容配方：{RECIPE_LABELS[recipe]}
配方要求：{RECIPE_GUIDES[recipe]}
目标读者：{audience or '普通中文读者'}
语气：{tone or '安静、克制、有生活感'}
时令主题：{seasonal_topic or '无指定'}
图片数量：{image_count}

硬性要求：
1. 正文总长 120-500 个中文字符，2-5 个短段，不写长篇分析。
2. 每张图只保留一句 6-24 字主句和最多 36 字小注；各页语义递进但可单独阅读。
3. 不使用“治愈一切、一定会、必须、排毒、降三高、养生秘方”等承诺。
4. 中老年读者不是被教育对象；避免“老人就该”“上了年纪只能”。
5. 时令饮食只写文化习惯与日常选择，明确因地区、体感和个人情况调整。
6. 只从来源提炼现实判断，不编造人物、数字、节气日期或营养功效。
7. 视觉隐喻必须是可画的单一物件或小场景，例如窗、茶杯、树影、旧椅、碗、果实、月亮、门、衣角。

来源：
{source_text[:12000]}

只输出 JSON：
{{
  "title":"公众号标题，12-24字",
  "subtitle":"一句副标题",
  "summary":"60-120字摘要",
  "body_markdown":"120-500字短正文",
  "tags":["标签"],
  "posters":[
    {{"phrase":"6-24字主句","note":"0-36字小注","visual_metaphor":"单一可画物件","layout":"center-fragment|lower-fragment|lower-left-float|upper-right-block|dual-panel|irregular-cutout|type-led|single-specimen","accent":"#1646d8","mood":"quiet|summer|solitude|childhood|seaside|afternoon|night|memory"}}
  ]
}}
""".strip()
        try:
            return await self.editorial._chat_json(
                system_prompt=(
                    "你是中文轻内容主编和视觉编辑。你擅长少字、照片感、共鸣短评与节气内容，"
                    "但拒绝廉价鸡汤、健康夸大和对中老年读者的刻板表达。"
                ),
                user_prompt=prompt,
                temperature=0.5,
                reasoning_effort=reasoning_effort,
                model_name=model_name,
            )
        except (httpx.HTTPError, KeyError, TypeError, ValueError, json.JSONDecodeError):
            return None

    def _fallback_copy(
        self,
        *,
        source: SourceItem,
        draft: DraftRevision | None,
        recipe: str,
        image_count: int,
        seasonal_topic: str,
        audience: str,
    ) -> dict[str, Any]:
        source_text = draft.body if draft and draft.body.strip() else source.text_original
        sentences = [
            item.strip()
            for item in re.split(r"(?<=[。！？!?])|\n+", source_text)
            if item.strip()
        ]
        source_seed = sentences[0][:36] if sentences else "日子正在慢慢向前"
        phrase_sets = {
            "comfort": [
                "慢一点，也是在向前",
                "允许今天只完成今天",
                "把力气留给真正重要的事",
                "日子不必时时都有答案",
                "累的时候，先把自己接住",
                "平静不是停下，而是找回节奏",
            ],
            "mature_life": [
                "人到后来，更要照顾自己的节奏",
                "少替别人操心，多给自己留白",
                "吃好一顿饭，也是一种踏实",
                "关系不必多，真心就好",
                "能安稳睡下，就是寻常的福气",
                "把日子过稳，比证明自己重要",
            ],
            "seasonal": [
                f"{seasonal_topic or '顺着时令'}，把日子过得从容",
                "三餐有度，也要听自己的体感",
                "早晚温差里，记得添减衣物",
                "节气是提醒，不是生活命令",
                "一碗当季食物，装着地方的记忆",
                "顺时生活，也要因人因地调整",
            ],
            "photo_quote": [
                source_seed,
                "有些答案，藏在安静的片刻里",
                "风景没有说话，人却慢了下来",
                "把这一刻，留给自己",
                "普通的一天，也值得被记住",
                "光落下来的地方，时间会变慢",
            ],
            "short_commentary": [
                source_seed,
                "真正稀缺的，往往不是方法，而是余地",
                "越是着急的时代，越需要慢一点判断",
                "很多问题，不是更努力就会消失",
                "一句话容易传播，边界仍然要保留",
                "共鸣可以很短，事实不能被省略",
            ],
        }
        phrases = phrase_sets[recipe][:image_count]
        metaphors = ["旧窗与一束光", "一只茶杯", "树影", "木椅", "一只碗", "远处月亮"]
        layouts = [
            "center-fragment",
            "lower-fragment",
            "lower-left-float",
            "upper-right-block",
            "single-specimen",
            "type-led",
            "irregular-cutout",
        ]
        note_sets = {
            "comfort": [
                "先承认今天已经很累",
                "把下一条消息晚一点再回",
                "给情绪留出落地的时间",
                "边界不是拒绝，而是停止透支",
                "休息不需要先证明自己值得",
                "明天的事，留给明天处理",
            ],
            "mature_life": [
                "不是退让，是把力气用在值得的地方",
                "少一点勉强，日子才有回旋余地",
                "具体的一餐，比空泛安慰更可靠",
                "关系的分量，不由人数决定",
                "睡得安稳，也是身体给出的答案",
                "生活不是一场永远要赢的比赛",
            ],
            "seasonal": [
                "天气是参考，身体感受也是",
                "同一节气，各地过法并不相同",
                "早晚变化比日期更值得留意",
                "传统习惯不等于统一处方",
                "当季食物也要按个人情况选择",
                "顺时而过，不必机械照搬",
            ],
            "photo_quote": [
                "画面之外，还留着没有说完的话",
                "安静不是空白，而是允许停顿",
                "光影替这一刻留下了注脚",
                "先不解释，只把感受留住",
                "普通生活也有被看见的价值",
                "时间慢下来，细节才会浮出来",
            ],
            "short_commentary": [
                "先指出矛盾，再保留事实边界",
                "方法很多，真正稀缺的是余地",
                "越急着下结论，越容易漏掉条件",
                "努力不能替代对问题的准确判断",
                "传播可以简短，证据不能省略",
                "一句判断之后，还要允许继续追问",
            ],
        }
        posters = []
        for index, phrase in enumerate(phrases):
            posters.append(
                {
                    "phrase": phrase,
                    "note": note_sets[recipe][index % len(note_sets[recipe])],
                    "visual_metaphor": metaphors[index % len(metaphors)],
                    "layout": layouts[index % len(layouts)],
                    "accent": ACCENTS[index % len(ACCENTS)],
                    "mood": "memory" if recipe in {"mature_life", "seasonal"} else "quiet",
                }
            )
        title = {
            "comfort": "给忙碌生活的一点安静",
            "mature_life": "人到后来，日子要按自己的节奏过",
            "seasonal": seasonal_topic or "顺着时令，安顿好一日三餐",
            "photo_quote": "照片里，那些没有说完的话",
            "short_commentary": "一句话说不完，但可以先说清一点",
        }[recipe]
        body = {
            "comfort": "生活并不会因为一句话立刻变轻，但一句合适的话，能让人暂时放下自责。慢一点，先照顾今天，再考虑更远的地方。",
            "mature_life": "年岁增长不是退场，而是更清楚什么值得花力气。把三餐、睡眠、关系和自己的情绪照顾好，日子就有了稳稳的底。",
            "seasonal": f"{seasonal_topic or '时令变化'}提醒我们观察天气、食物和身体感受。传统习惯可以参考，但三餐与作息仍要因地区、体感和个人情况调整。",
            "photo_quote": "有些内容不需要长篇解释。一张照片，一句短话，足够让忙碌的人停一下，也给平常生活留下一点被看见的空间。",
            "short_commentary": f"{source_seed}。短评的价值不是替复杂问题下结论，而是指出一个值得继续想的方向，并把事实边界留下。",
        }[recipe]
        return {
            "title": title,
            "subtitle": RECIPE_LABELS[recipe],
            "summary": body[:120],
            "body_markdown": body,
            "tags": [RECIPE_LABELS[recipe], "轻内容", "生活方式"],
            "posters": posters,
            "audience": audience,
        }

    def _normalize_output(
        self,
        raw: dict[str, Any],
        *,
        source: SourceItem,
        recipe: str,
        image_count: int,
        seasonal_topic: str,
    ) -> dict[str, Any]:
        fallback = self._fallback_copy(
            source=source,
            draft=None,
            recipe=recipe,
            image_count=image_count,
            seasonal_topic=seasonal_topic,
            audience="",
        )
        title = strip_internal_markers(str(raw.get("title") or fallback["title"])).strip()
        subtitle = strip_internal_markers(str(raw.get("subtitle") or fallback["subtitle"])).strip()
        summary = strip_internal_markers(str(raw.get("summary") or fallback["summary"])).strip()
        body = strip_internal_markers(str(raw.get("body_markdown") or fallback["body_markdown"])).strip()
        tags_raw = raw.get("tags")
        if isinstance(tags_raw, list):
            tags = ",".join(str(item).strip() for item in tags_raw if str(item).strip())
        else:
            tags = str(tags_raw or ",".join(fallback["tags"]))
        posters_raw = raw.get("posters")
        posters: list[dict[str, Any]] = []
        if isinstance(posters_raw, list):
            for index, item in enumerate(posters_raw[:image_count]):
                if not isinstance(item, dict):
                    continue
                phrase = strip_internal_markers(str(item.get("phrase") or "")).strip()[:36]
                if not phrase:
                    continue
                accent = str(item.get("accent") or ACCENTS[index % len(ACCENTS)])
                if not re.fullmatch(r"#[0-9a-fA-F]{6}", accent):
                    accent = ACCENTS[index % len(ACCENTS)]
                posters.append(
                    {
                        "phrase": phrase,
                        "note": strip_internal_markers(str(item.get("note") or "")).strip()[:48],
                        "visual_metaphor": str(item.get("visual_metaphor") or "纸上的小物件").strip()[:80],
                        "photo_direction": str(item.get("photo_direction") or "").strip()[:240],
                        "layout": str(item.get("layout") or "center-fragment"),
                        "accent": accent,
                        "mood": str(item.get("mood") or "quiet"),
                        "evidence_basis": strip_internal_markers(
                            str(item.get("evidence_basis") or "")
                        ).strip()[:240],
                        "source_refs": [
                            str(value).strip()[:80]
                            for value in item.get("source_refs", [])[:8]
                            if str(value).strip()
                        ]
                        if isinstance(item.get("source_refs"), list)
                        else [],
                    }
                )
        for item in fallback["posters"]:
            if len(posters) >= image_count:
                break
            posters.append(item)
        return {
            "title": title[:160],
            "subtitle": subtitle[:240],
            "summary": summary[:1000],
            "body_markdown": body[:50000],
            "tags": tags[:1000],
            "posters": posters[:image_count],
        }

    def _compile_prompt(self, spec: dict[str, Any], *, index: int, total: int) -> str:
        phrase = str(spec.get("phrase") or "").strip()
        metaphor = str(spec.get("visual_metaphor") or "small paper object").strip()
        layout = str(spec.get("layout") or "center-fragment")
        accent = str(spec.get("accent") or ACCENTS[(index - 1) % len(ACCENTS)])
        mood = str(spec.get("mood") or "quiet")
        return (
            f"Tall 3:5 aged-paper editorial poster, flat scanned-paper view, 78%-88% negative space. "
            f"One small visual cluster using {layout}, occupying about 12%-20% of the canvas.\n\n"
            f"The single imageable anchor is {metaphor}, treated as a faded photo fragment, old printed specimen, "
            f"or torn-paper cutout with soft xerox grain and slight ink wear.\n\n"
            f"Use one short Chinese phrase exactly: ‘{phrase}’. Small serif or typewriter typography, optional archive microtext. "
            f"One unmistakable saturated color anchor in {accent}, about 1%-2% of the whole canvas, visible at thumbnail size.\n\n"
            f"Quiet {mood} mood, matte absorbent paper, diffuse light, low-to-medium contrast. "
            f"Avoid commercial advertising, logo, CTA, glossy mockup, cinematic light, 3D, neon, cute cartoon, dense scrapbook, and long text. "
            f"Poster {index} of {total}."
        )

    def _render_poster(
        self,
        path: Path,
        *,
        spec: dict[str, Any],
        theme: str,
        hero_image: str,
        index: int,
        total: int,
    ) -> None:
        seed_value = f"{spec.get('phrase')}:{index}:{theme}"
        seed = int(hashlib.sha256(seed_value.encode()).hexdigest()[:12], 16)
        rng = random.Random(seed)
        paper = PAPER_TONES.get(theme, PAPER_TONES["auto"])
        canvas = Image.new("RGB", (self.width, self.height), paper)
        noise = Image.effect_noise((self.width, self.height), 18).convert("L")
        noise = ImageEnhance.Contrast(noise).enhance(0.35)
        texture = Image.merge("RGB", (noise, noise, noise))
        canvas = Image.blend(canvas, texture, 0.075)
        draw = ImageDraw.Draw(canvas)
        accent = str(spec.get("accent") or ACCENTS[(index - 1) % len(ACCENTS)])
        ink = "#23201d"
        muted = "#746f66"
        phrase = str(spec.get("phrase") or "").strip()
        note = str(spec.get("note") or "").strip()
        layout = str(spec.get("layout") or "center-fragment")

        cluster = self._cluster_box(layout, rng)
        self._draw_anchor(
            canvas,
            draw,
            cluster=cluster,
            hero_image=hero_image,
            accent=accent,
            rng=rng,
            index=index,
        )

        title_font = self._font(64 if len(phrase) <= 16 else 54, bold=False, serif=True)
        note_font = self._font(25, bold=False, serif=False)
        micro_font = self._font(18, bold=False, serif=False)
        text_x, text_y, max_width = self._text_position(layout, cluster)
        lines = self._wrap(draw, phrase, title_font, max_width)
        for line in lines[:3]:
            draw.text((text_x, text_y), line, font=title_font, fill=ink)
            text_y += int(getattr(title_font, "size", 56) * 1.28)
        if note:
            text_y += 22
            for line in self._wrap(draw, note, note_font, max_width)[:2]:
                draw.text((text_x, text_y), line, font=note_font, fill=muted)
                text_y += 40

        micro = f"LIGHT NOTE / {index:02d}—{total:02d}   PAPER MEMORY   {spec.get('mood', 'QUIET').upper()}"
        draw.text((76, self.height - 78), micro, font=micro_font, fill=muted)
        draw.text((self.width - 148, 64), f"{index:02d}", font=self._font(22, bold=True, serif=False), fill=accent)
        for _ in range(26):
            x = rng.randrange(40, self.width - 40)
            y = rng.randrange(40, self.height - 40)
            radius = rng.choice((1, 1, 2, 3))
            draw.ellipse((x, y, x + radius, y + radius), fill="#746f6638")
        canvas = canvas.filter(ImageFilter.GaussianBlur(radius=0.15))
        canvas.save(path, format="PNG", optimize=True)

    def _draw_anchor(
        self,
        canvas: Image.Image,
        draw: ImageDraw.ImageDraw,
        *,
        cluster: tuple[int, int, int, int],
        hero_image: str,
        accent: str,
        rng: random.Random,
        index: int,
    ) -> None:
        left, top, right, bottom = cluster
        width = right - left
        height = bottom - top
        hero = Path(hero_image) if hero_image else None
        if hero and hero.is_file() and index % 2 == 1:
            try:
                with Image.open(hero).convert("RGB") as source:
                    ratio = max(width / source.width, height / source.height)
                    resized = source.resize(
                        (max(int(source.width * ratio), width), max(int(source.height * ratio), height))
                    )
                    crop_left = max((resized.width - width) // 2, 0)
                    crop_top = max((resized.height - height) // 2, 0)
                    crop = resized.crop((crop_left, crop_top, crop_left + width, crop_top + height))
                    crop = ImageEnhance.Color(crop).enhance(0.12)
                    crop = ImageEnhance.Contrast(crop).enhance(0.78)
                    crop = crop.filter(ImageFilter.GaussianBlur(radius=0.45))
                    canvas.paste(crop, (left, top))
                draw.rectangle(cluster, outline="#4a464055", width=2)
                draw.rectangle(
                    (right - max(width // 5, 34), top, right, bottom),
                    fill=accent,
                )
                return
            except OSError:
                pass
        form = index % 5
        if form == 0:
            draw.ellipse(cluster, fill=accent)
            draw.ellipse((left + width * 0.22, top + height * 0.18, right - width * 0.18, bottom - height * 0.24), fill="#e8dfd0")
        elif form == 1:
            draw.rounded_rectangle(cluster, radius=18, fill="#bbb2a4", outline="#4a4640", width=2)
            draw.rectangle((left + width * 0.62, top, right, bottom), fill=accent)
            draw.line((left + 24, bottom - 34, right - 18, top + 46), fill="#5b554d", width=4)
        elif form == 2:
            points = [
                (left + width * 0.5, top),
                (right, top + height * 0.4),
                (left + width * 0.72, bottom),
                (left, top + height * 0.68),
            ]
            draw.polygon(points, fill=accent)
            draw.line((left - 30, bottom + 22, right + 35, top - 12), fill="#5b554d", width=2)
        elif form == 3:
            draw.rectangle(cluster, fill="#aaa398")
            for row in range(8):
                y = top + 20 + row * max(height // 10, 12)
                draw.line((left + 18, y, right - 18, y + rng.randrange(-5, 6)), fill="#6c665e", width=2)
            draw.ellipse((right - 90, top + 24, right - 24, top + 90), fill=accent)
        else:
            draw.arc(cluster, start=185, end=355, fill="#56514a", width=5)
            draw.line((left + width * 0.5, top + 20, left + width * 0.5, bottom - 20), fill="#56514a", width=4)
            draw.ellipse((left + width * 0.42, top + height * 0.18, left + width * 0.58, top + height * 0.34), fill=accent)

    def _cluster_box(self, layout: str, rng: random.Random) -> tuple[int, int, int, int]:
        width = rng.randint(250, 410)
        height = rng.randint(230, 430)
        positions = {
            "center-fragment": (self.width // 2 - width // 2, 620),
            "lower-fragment": (self.width // 2 - width // 2, 1040),
            "lower-left-float": (110, 1200),
            "upper-right-block": (self.width - width - 110, 260),
            "dual-panel": (self.width // 2 - width // 2, 760),
            "irregular-cutout": (150, 520),
            "type-led": (self.width - width - 140, 1080),
            "single-specimen": (self.width // 2 - width // 2, 860),
        }
        left, top = positions.get(layout, positions["center-fragment"])
        return left, top, left + width, top + height

    def _text_position(
        self,
        layout: str,
        cluster: tuple[int, int, int, int],
    ) -> tuple[int, int, int]:
        _, _, _, bottom = cluster
        if layout == "lower-left-float":
            return 650, 360, 430
        if layout == "lower-fragment":
            return 120, 220, 900
        if layout == "upper-right-block":
            return 96, 900, 720
        if layout == "type-led":
            return 100, 340, 720
        if layout == "irregular-cutout":
            return 600, 1060, 470
        if layout == "single-specimen":
            return 120, 360, 930
        return 120, min(bottom + 120, 1320), 900

    def _preview_document(self, variant: PlatformVariant, specs: list[dict[str, Any]]) -> str:
        cards = "".join(
            f'<figure><img src="/api/platforms/variants/{variant.id}/files/poster_{index:02d}" alt="{html.escape(str(spec.get("phrase") or "轻内容海报"))}"><figcaption>{html.escape(str(spec.get("phrase") or ""))}</figcaption></figure>'
            for index, spec in enumerate(specs, start=1)
        )
        return f"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{html.escape(variant.title)}</title><style>
body{{margin:0;background:#ece8df;color:#24211e;font-family:-apple-system,BlinkMacSystemFont,'PingFang SC',sans-serif}}main{{max-width:1180px;margin:auto;padding:48px 24px}}h1{{font-size:34px}}p{{max-width:760px;line-height:1.9;color:#59534b}}.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:24px;margin-top:30px}}figure{{margin:0;padding:12px;background:#fff;box-shadow:0 18px 50px #322a2015}}img{{display:block;width:100%;aspect-ratio:3/5;object-fit:cover}}figcaption{{padding:12px 4px 4px;font-size:13px;color:#6c655b}}</style></head><body><main><h1>{html.escape(variant.title)}</h1><p>{html.escape(variant.summary)}</p><section class="grid">{cards}</section></main></body></html>"""

    @staticmethod
    def _body_fragment(variant: PlatformVariant) -> str:
        paragraphs = [
            item.strip()
            for item in re.split(r"\n\s*\n", variant.body_markdown)
            if item.strip()
        ]
        return "".join(
            f'<p style="margin:0 0 18px;font-size:16px;line-height:1.9;color:#2a2723;">{html.escape(item)}</p>'
            for item in paragraphs
        )

    @staticmethod
    def _hero_image(source: SourceItem) -> str:
        for asset in source.assets:
            path = Path(asset.local_path) if asset.local_path else None
            if asset.kind == "image" and path and path.is_file():
                return str(path)
        return ""

    @staticmethod
    def _json_object(value: str) -> dict[str, Any]:
        try:
            parsed = json.loads(value or "{}")
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}

    @staticmethod
    def _next_version(db: Session, source_id: str) -> int:
        value = db.scalar(
            select(func.max(PlatformVariant.version)).where(
                PlatformVariant.source_id == source_id,
                PlatformVariant.platform == "wechat",
            )
        )
        return int(value or 0) + 1

    @staticmethod
    def _font(
        size: int,
        *,
        bold: bool,
        serif: bool,
    ) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
        if serif:
            candidates = [
                "/System/Library/Fonts/Songti.ttc",
                "/System/Library/Fonts/STSong.ttf",
                "/usr/share/fonts/opentype/noto/NotoSerifCJK-Regular.ttc",
                "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf",
            ]
        else:
            candidates = [
                "/System/Library/Fonts/PingFang.ttc",
                "/System/Library/Fonts/STHeiti Medium.ttc",
                "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc" if bold else "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
                "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            ]
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
        if not text:
            return []
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
