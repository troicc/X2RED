from __future__ import annotations

import html
import re
from dataclasses import dataclass
from urllib.parse import urlparse

from app.services.wechat_themes import WeChatTheme, get_theme


@dataclass(frozen=True)
class WeChatValidation:
    errors: list[str]
    warnings: list[str]

    @property
    def ok(self) -> bool:
        return not self.errors


class WeChatHtmlRenderer:
    """Render a constrained Markdown subset to WeChat-safe inline HTML.

    The clean fragment intentionally avoids style sheets, scripts, classes,
    layout CSS and browser-only positioning. Preview-only controls live outside
    the fragment returned by ``render_fragment``.
    """

    _forbidden_checks: tuple[tuple[str, str], ...] = (
        (r"<(?:style|script|div|iframe|form|button)\b", "包含公众号正文不应出现的标签"),
        (r"\s(?:class|id)=", "包含 class 或 id 属性"),
        (r"(?:position\s*:|display\s*:\s*(?:grid|flex)|float\s*:)", "包含易被公众号过滤的布局样式"),
        (r"(?:var\(--|@media|@keyframes|animation\s*:)", "包含公众号不支持的动态或变量样式"),
        (r"javascript\s*:", "包含不安全链接"),
    )

    def render_fragment(
        self,
        *,
        title: str,
        summary: str,
        markdown: str,
        theme_id: str,
        author: str = "",
        source_url: str = "",
        mark_keywords: bool = True,
    ) -> str:
        theme = get_theme(theme_id)
        blocks = self._parse_blocks(markdown)
        output: list[str] = [
            self._open_section(theme),
            self._title_block(title, summary, theme),
        ]
        chapter = 0
        for kind, value in blocks:
            if kind == "h1":
                continue
            if kind == "h2":
                chapter += 1
                output.append(self._heading(value, chapter, theme, level=2))
            elif kind == "h3":
                output.append(self._heading(value, chapter, theme, level=3))
            elif kind == "quote":
                output.append(self._quote(value, theme))
            elif kind == "code":
                output.append(self._code(value, theme))
            elif kind == "image":
                output.append(self._image(value[0], value[1], theme))
            elif kind == "ul":
                output.append(self._list(value, theme, ordered=False, mark_keywords=mark_keywords))
            elif kind == "ol":
                output.append(self._list(value, theme, ordered=True, mark_keywords=mark_keywords))
            elif kind == "table":
                output.append(self._table(value, theme))
            else:
                output.append(self._paragraph(value, theme, mark_keywords=mark_keywords))
        output.append(self._signature(author, source_url, theme))
        output.append("</section>")
        return "".join(output)

    def preview_document(self, *, title: str, fragment: str) -> str:
        safe_title = html.escape(title or "公众号文章预览")
        return f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{safe_title}</title><style>
*{{box-sizing:border-box}}body{{margin:0;background:#eef1f5;color:#111827;font-family:-apple-system,BlinkMacSystemFont,'PingFang SC',sans-serif}}
.preview-shell{{width:min(760px,calc(100vw - 32px));margin:76px auto 48px;background:#fff;border-radius:20px;box-shadow:0 22px 70px rgba(20,28,45,.12);overflow:hidden}}
.preview-toolbar{{position:fixed;z-index:10;top:14px;left:50%;transform:translateX(-50%);display:flex;align-items:center;justify-content:space-between;gap:20px;width:min(760px,calc(100vw - 32px));padding:11px 14px;border:1px solid #dfe4ec;border-radius:14px;background:rgba(255,255,255,.94);backdrop-filter:blur(16px);box-shadow:0 8px 30px rgba(20,28,45,.1)}}
.preview-toolbar strong{{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}}button{{border:0;border-radius:10px;padding:10px 15px;color:white;background:#315efb;font-weight:700;cursor:pointer}}#copy-state{{font-size:12px;color:#657084}}
</style></head><body><header class="preview-toolbar"><strong>{safe_title}</strong><span id="copy-state">公众号富文本预览</span><button type="button" onclick="copyArticle()">复制到公众号</button></header><main class="preview-shell" id="article-fragment">{fragment}</main><script>
async function copyArticle(){{const box=document.getElementById('article-fragment');const state=document.getElementById('copy-state');try{{const blob=new Blob([box.innerHTML],{{type:'text/html'}});const plain=new Blob([box.innerText],{{type:'text/plain'}});await navigator.clipboard.write([new ClipboardItem({{'text/html':blob,'text/plain':plain}})]);state.textContent='已复制，打开公众号编辑器粘贴';}}catch(error){{const range=document.createRange();range.selectNodeContents(box);const selection=getSelection();selection.removeAllRanges();selection.addRange(range);document.execCommand('copy');selection.removeAllRanges();state.textContent='已复制（兼容模式）';}}}}
</script></body></html>"""

    def validate(self, fragment: str) -> WeChatValidation:
        errors: list[str] = []
        warnings: list[str] = []
        lowered = fragment.lower()
        for pattern, message in self._forbidden_checks:
            if re.search(pattern, lowered, flags=re.I):
                errors.append(message)
        if not fragment.lstrip().startswith("<section") or not fragment.rstrip().endswith("</section>"):
            errors.append("公众号正文必须是单个 section 根片段")
        if len(re.sub(r"<[^>]+>", "", fragment).strip()) < 80:
            errors.append("正文内容过短或渲染为空")
        if "<span leaf=\"\">" not in fragment:
            warnings.append("未检测到公众号兼容的 span leaf 文字包装")
        if re.search(r"(?:^|>)\s*#{1,6}\s", fragment):
            errors.append("仍残留 Markdown 标题标记")
        if "```" in fragment:
            errors.append("仍残留 Markdown 代码围栏")
        if len(re.findall(r"<h2\b", fragment)) == 0:
            warnings.append("文章没有二级章节，长文可能缺少阅读分段")
        for paragraph in re.findall(r"<p\b[^>]*>(.*?)</p>", fragment, flags=re.S | re.I):
            text = re.sub(r"<[^>]+>", "", paragraph)
            if len(text) > 420:
                warnings.append("存在超过 420 字的单段，建议拆段")
                break
        external_links = re.findall(r'href="(https?://[^"]+)"', fragment, flags=re.I)
        if len(external_links) > 8:
            warnings.append("正文包含较多外链，公众号发布前建议整理到文末来源")
        return WeChatValidation(errors=self._unique(errors), warnings=self._unique(warnings))

    @staticmethod
    def _open_section(theme: WeChatTheme) -> str:
        style = (
            f"margin:0 auto;padding:28px 22px 40px;max-width:677px;"
            f"background:{theme.paper};color:{theme.text};font-family:-apple-system,BlinkMacSystemFont,"
            "'PingFang SC','Microsoft YaHei',sans-serif;font-size:16px;line-height:1.82;"
            "letter-spacing:0.02em;word-break:break-word;"
        )
        return f'<section style="{style}">'

    def _title_block(self, title: str, summary: str, theme: WeChatTheme) -> str:
        safe_title = self._leaf(title.strip() or "未命名文章")
        title_html = (
            f'<h1 style="margin:4px 0 18px;padding:0;color:{theme.text};font-size:30px;line-height:1.28;'
            f'font-weight:800;letter-spacing:-0.02em;text-align:left;">{safe_title}</h1>'
        )
        if not summary.strip():
            return title_html
        summary_html = self._inline(summary.strip(), theme, mark_keywords=False)
        return (
            title_html
            + f'<section style="margin:0 0 34px;padding:18px 18px 16px;border-left:4px solid {theme.accent};'
            f'border-radius:0 12px 12px 0;background:{theme.accent_soft};color:{theme.text};">'
            f'<p style="margin:0;font-size:15px;line-height:1.75;">{summary_html}</p></section>'
        )

    def _heading(
        self,
        text: str,
        chapter: int,
        theme: WeChatTheme,
        *,
        level: int,
    ) -> str:
        clean = text.strip()
        if level == 3:
            return (
                f'<h3 style="margin:28px 0 12px;padding:0 0 0 12px;border-left:3px solid {theme.accent};'
                f'color:{theme.text};font-size:18px;line-height:1.5;font-weight:750;">'
                f'{self._leaf(clean)}</h3>'
            )
        number = f"{chapter:02d}"
        if theme.heading_style == "minimal":
            style = f"margin:38px 0 18px;padding:0 0 10px;border-bottom:1px solid {theme.rule};"
        elif theme.heading_style == "serif":
            style = f"margin:42px 0 20px;padding:0;text-align:center;"
        elif theme.heading_style == "ticket":
            style = f"margin:38px 0 18px;padding:12px 14px;border:1px solid {theme.rule};border-radius:8px;background:{theme.accent_soft};"
        else:
            style = f"margin:38px 0 18px;padding:13px 16px;border-radius:10px;background:{theme.accent_soft};"
        return (
            f'<h2 style="{style}color:{theme.text};font-size:22px;line-height:1.45;font-weight:800;">'
            f'<span leaf="" style="margin-right:9px;color:{theme.accent};font-size:13px;letter-spacing:0.12em;">{number}</span>'
            f'{self._leaf(clean)}</h2>'
        )

    def _paragraph(self, text: str, theme: WeChatTheme, *, mark_keywords: bool) -> str:
        return (
            f'<p style="margin:0 0 18px;color:{theme.text};font-size:16px;line-height:1.88;'
            f'text-align:justify;">{self._inline(text.strip(), theme, mark_keywords=mark_keywords)}</p>'
        )

    def _quote(self, text: str, theme: WeChatTheme) -> str:
        return (
            f'<blockquote style="margin:24px 0;padding:17px 18px;border-left:4px solid {theme.accent};'
            f'border-radius:0 10px 10px 0;background:{theme.quote};color:{theme.text};">'
            f'<p style="margin:0;font-size:15px;line-height:1.8;">'
            f'{self._inline(text, theme, mark_keywords=True)}</p></blockquote>'
        )

    def _code(self, text: str, theme: WeChatTheme) -> str:
        return (
            f'<pre style="margin:22px 0;padding:17px 18px;overflow-x:auto;border-radius:10px;'
            f'background:{theme.code_background};color:{theme.code_text};font-family:SFMono-Regular,Consolas,'
            f'monospace;font-size:13px;line-height:1.65;white-space:pre-wrap;word-break:break-word;">'
            f'<code>{self._leaf(text, escape=True)}</code></pre>'
        )

    def _image(self, alt: str, src: str, theme: WeChatTheme) -> str:
        safe_src = html.escape(src, quote=True)
        caption = (
            f'<p style="margin:8px 0 22px;color:{theme.muted};font-size:12px;line-height:1.55;'
            f'text-align:center;">{self._leaf(alt)}</p>'
            if alt.strip()
            else ""
        )
        return (
            f'<section style="margin:24px 0;text-align:center;">'
            f'<img src="{safe_src}" alt="{html.escape(alt, quote=True)}" style="display:block;margin:0 auto;'
            f'max-width:100%;height:auto;border-radius:10px;" />{caption}</section>'
        )

    def _list(
        self,
        items: list[str],
        theme: WeChatTheme,
        *,
        ordered: bool,
        mark_keywords: bool,
    ) -> str:
        tag = "ol" if ordered else "ul"
        rows = "".join(
            f'<li style="margin:0 0 10px;padding-left:4px;color:{theme.text};font-size:15px;line-height:1.75;">'
            f'{self._inline(item, theme, mark_keywords=mark_keywords)}</li>'
            for item in items
        )
        return f'<{tag} style="margin:8px 0 22px;padding-left:24px;">{rows}</{tag}>'

    def _table(self, rows: list[list[str]], theme: WeChatTheme) -> str:
        if not rows:
            return ""
        head, *body = rows
        header_cells = "".join(
            f'<th style="padding:10px 9px;border:1px solid {theme.rule};background:{theme.accent_soft};'
            f'color:{theme.text};font-size:13px;line-height:1.5;text-align:left;">{self._leaf(cell)}</th>'
            for cell in head
        )
        body_rows = "".join(
            "<tr>"
            + "".join(
                f'<td style="padding:10px 9px;border:1px solid {theme.rule};color:{theme.text};'
                f'font-size:13px;line-height:1.55;vertical-align:top;">{self._leaf(cell)}</td>'
                for cell in row
            )
            + "</tr>"
            for row in body
        )
        return (
            f'<section style="margin:22px 0;overflow-x:auto;"><table style="width:100%;border-collapse:collapse;'
            f'border-spacing:0;"><thead><tr>{header_cells}</tr></thead><tbody>{body_rows}</tbody></table></section>'
        )

    def _signature(self, author: str, source_url: str, theme: WeChatTheme) -> str:
        if not author.strip() and not source_url.strip():
            return ""
        values: list[str] = []
        if author.strip():
            values.append(f"作者：{author.strip()}")
        if source_url.strip() and self._safe_url(source_url):
            safe_url = html.escape(source_url, quote=True)
            values.append(
                f'<a href="{safe_url}" style="color:{theme.accent};text-decoration:none;">'
                f'{self._leaf("查看原始来源")}</a>'
            )
        return (
            f'<section style="margin:38px 0 0;padding-top:18px;border-top:1px solid {theme.rule};'
            f'color:{theme.muted};font-size:12px;line-height:1.7;">'
            + "<br>".join(self._leaf(value) if not value.startswith("<a ") else value for value in values)
            + "</section>"
        )

    def _inline(self, text: str, theme: WeChatTheme, *, mark_keywords: bool) -> str:
        tokens: dict[str, str] = {}

        def stash(value: str) -> str:
            key = f"X2REDTOKEN{len(tokens)}X"
            tokens[key] = value
            return key

        value = text.strip()
        value = re.sub(
            r"`([^`]+)`",
            lambda match: stash(
                f'<code style="padding:2px 5px;border-radius:5px;background:{theme.accent_soft};'
                f'color:{theme.accent};font-family:SFMono-Regular,Consolas,monospace;font-size:0.9em;">'
                f'{self._leaf(match.group(1))}</code>'
            ),
            value,
        )
        value = re.sub(
            r"\[([^\]]+)\]\((https?://[^\s)]+)\)",
            lambda match: stash(
                f'<a href="{html.escape(match.group(2), quote=True)}" style="color:{theme.accent};'
                f'text-decoration:underline;text-decoration-color:{theme.rule};text-underline-offset:3px;">'
                f'{self._leaf(match.group(1))}</a>'
            )
            if self._safe_url(match.group(2))
            else self._leaf(match.group(1)),
            value,
        )
        value = html.escape(value)
        value = re.sub(
            r"\*\*([^*]+)\*\*",
            lambda match: (
                f'<span leaf="" style="font-weight:750;color:{theme.accent};">{match.group(1)}</span>'
            ),
            value,
        )
        value = re.sub(
            r"==([^=]+)==|\+\+([^+]+)\+\+",
            lambda match: (
                f'<span leaf="" style="border-bottom:3px solid {theme.accent}55;font-weight:650;">'
                f'{match.group(1) or match.group(2)}</span>'
            ),
            value,
        )
        if mark_keywords and "<span leaf=" not in value:
            value = self._auto_mark(value, theme)
        value = f'<span leaf="">{value}</span>'
        for key, token in tokens.items():
            value = value.replace(key, token)
        return value

    def _auto_mark(self, escaped_text: str, theme: WeChatTheme) -> str:
        patterns = (
            r"(?<![A-Za-z0-9])(?:\d+(?:\.\d+)?%|\d+(?:\.\d+)?\s*(?:倍|秒|毫秒|ms|μs|GB|MB|B))",
            r"(?<![A-Za-z])(?:CUDA|GPU|CPU|API|AI|LLM|VSA|TMA|TMEM|Triton|Transformer)(?![A-Za-z])",
        )
        output = escaped_text
        marked = 0
        for pattern in patterns:
            def repl(match: re.Match[str]) -> str:
                nonlocal marked
                if marked >= 3:
                    return match.group(0)
                marked += 1
                return (
                    f'<span leaf="" style="border-bottom:3px solid {theme.accent}55;font-weight:700;">'
                    f'{match.group(0)}</span>'
                )
            output = re.sub(pattern, repl, output, count=max(0, 3 - marked))
            if marked >= 3:
                break
        return output

    @staticmethod
    def _leaf(text: str, *, escape: bool = True) -> str:
        value = html.escape(str(text)) if escape else str(text)
        return f'<span leaf="">{value}</span>'

    @staticmethod
    def _safe_url(value: str) -> bool:
        parsed = urlparse(value.strip())
        return parsed.scheme in {"http", "https"} and bool(parsed.netloc)

    @classmethod
    def _parse_blocks(cls, markdown: str) -> list[tuple[str, object]]:
        lines = markdown.replace("\r\n", "\n").replace("\r", "\n").split("\n")
        blocks: list[tuple[str, object]] = []
        paragraph: list[str] = []
        code: list[str] = []
        in_code = False
        list_kind = ""
        list_items: list[str] = []
        table_rows: list[list[str]] = []

        def flush_paragraph() -> None:
            nonlocal paragraph
            text = " ".join(item.strip() for item in paragraph if item.strip()).strip()
            if text:
                blocks.append(("p", text))
            paragraph = []

        def flush_list() -> None:
            nonlocal list_kind, list_items
            if list_items:
                blocks.append((list_kind or "ul", list_items))
            list_kind = ""
            list_items = []

        def flush_table() -> None:
            nonlocal table_rows
            if table_rows:
                blocks.append(("table", table_rows))
            table_rows = []

        for raw_line in lines:
            line = raw_line.rstrip()
            if line.strip().startswith("```"):
                flush_paragraph(); flush_list(); flush_table()
                if in_code:
                    blocks.append(("code", "\n".join(code).rstrip()))
                    code = []
                    in_code = False
                else:
                    in_code = True
                continue
            if in_code:
                code.append(line)
                continue
            stripped = line.strip()
            if not stripped:
                flush_paragraph(); flush_list(); flush_table()
                continue
            image = re.fullmatch(r"!\[([^\]]*)\]\(([^)]+)\)", stripped)
            if image:
                flush_paragraph(); flush_list(); flush_table()
                blocks.append(("image", (image.group(1), image.group(2))))
                continue
            heading = re.match(r"^(#{1,3})\s+(.+)$", stripped)
            if heading:
                flush_paragraph(); flush_list(); flush_table()
                blocks.append((f"h{len(heading.group(1))}", heading.group(2).strip()))
                continue
            if stripped.startswith(">"):
                flush_paragraph(); flush_list(); flush_table()
                blocks.append(("quote", stripped.lstrip("> ").strip()))
                continue
            unordered = re.match(r"^[-*+]\s+(.+)$", stripped)
            ordered = re.match(r"^\d+[.)]\s+(.+)$", stripped)
            if unordered or ordered:
                flush_paragraph(); flush_table()
                kind = "ol" if ordered else "ul"
                if list_kind and list_kind != kind:
                    flush_list()
                list_kind = kind
                list_items.append((ordered or unordered).group(1).strip())
                continue
            if stripped.startswith("|") and stripped.endswith("|"):
                flush_paragraph(); flush_list()
                cells = [cell.strip() for cell in stripped.strip("|").split("|")]
                if all(re.fullmatch(r":?-{3,}:?", cell) for cell in cells):
                    continue
                table_rows.append(cells)
                continue
            flush_list(); flush_table()
            paragraph.append(stripped)
        if in_code and code:
            blocks.append(("code", "\n".join(code).rstrip()))
        flush_paragraph(); flush_list(); flush_table()
        return blocks

    @staticmethod
    def _unique(values: list[str]) -> list[str]:
        output: list[str] = []
        for value in values:
            if value not in output:
                output.append(value)
        return output
