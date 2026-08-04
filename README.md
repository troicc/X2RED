# X2RED

X2RED is a local-first **Chinese content research, corpus, and multi-platform editorial studio**. It turns selected X and Simplified-Chinese platform signals into reusable, traceable source assets and reviewed Xiaohongshu or WeChat deliverables.

> **Project context for humans and AI agents:** read [AGENTS.md](AGENTS.md) and [docs/ai-context/README.md](docs/ai-context/README.md) before modifying the current feature branch. The context package records the active three-layer product architecture, implementation progress, workflows, decisions, risks, local update commands and handoff protocol. Current PR/commit/CI fields are volatile and must still be rechecked on GitHub.

## Working application

The product is organized into three layers:

1. **语料素材库** — X signal discovery, local MediaCrawler discovery for Simplified-Chinese platforms, platform-classified `SourceItem` records, reusable corpus pools and frozen batches.
2. **内容工作台** — Xiaohongshu, writing projects, WeChat long-form, WeChat light-content storyboards, review, previews and release packages.
3. **模型与 Skill** — OpenAI-compatible text/image models, style profiles, the pinned Guizang runtime and the pinned Minimal Zine runtime.

The current application can:

1. Monitor or import X posts, threads and full X Articles, preserving raw responses, evidence, relations and source media.
2. Discover Xiaohongshu, Douyin, Kuaishou, Bilibili, Weibo, Tieba and Zhihu material through a pinned local MediaCrawler checkout.
3. Normalize every selected discovery result, public webpage, document or manual input into the shared `SourceItem` model.
4. Classify sources by platform instead of collapsing them into one unstructured selector.
5. Build reusable `CorpusPool` assets and freeze each generation handoff as an isolated, reproducible `CorpusBatch` with memory and provenance.
6. Dispatch a source or frozen batch to Xiaohongshu, WeChat long-form or WeChat light-content workspaces.
7. Generate content through either a quick editorial pipeline or an artifact-driven multi-Agent writing studio.
8. Train personal style profiles from authorized samples, held-out samples and author feedback.
9. Create immutable draft and platform-specific revisions from the same evidence base.
10. Render Xiaohongshu cards with the fast renderer or the complete upstream Guizang Editorial/Swiss runtime.
11. Generate text-free Minimal Zine visual anchors with an image model, then compose final Chinese typography locally.
12. Generate WeChat Markdown/HTML, covers, previews, manifests and ZIP release packages from one frozen version.
13. Record source/media rights decisions and explicit human approval before publishing.
14. Open platform preparation flows while stopping before the final publish action.

## One-command start

Requires Python 3.12+ and Node.js/npm for the optional Guizang native runtime.

macOS / Linux:

```bash
chmod +x scripts/start.sh
./scripts/start.sh
```

Windows:

```bat
scripts\start.cmd
```

The startup scripts create `.venv`, install X2RED, apply database migrations, prepare the pinned MediaCrawler checkout and bind the service to `127.0.0.1:8787`.

Open `http://127.0.0.1:8787`.

## Manual installation

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
python -m pip install -e '.[dev]'
python -m playwright install chromium
cp .env.example .env             # Windows: copy .env.example .env
x2red check
x2red serve
```

`x2red serve` applies Alembic migrations before starting unless `--skip-migrate` is explicitly supplied.

## Text-model configuration

L1/L2 intelligence, personal style training, multi-Agent writing, platform adaptation and native Guizang HTML composition require an OpenAI-compatible text endpoint:

```env
X2RED_MODEL_BASE_URL=https://your-provider.example/v1
X2RED_MODEL_API_KEY=your-key
X2RED_MODEL_NAME=your-model
```

## Image-model configuration

The full Minimal Zine action requires an OpenAI-compatible `/images/generations` endpoint. The image endpoint may share the text-model provider:

```env
X2RED_IMAGE_BASE_URL=
X2RED_IMAGE_API_KEY=
X2RED_IMAGE_MODEL=glm-image
X2RED_IMAGE_SIZE=1024x1536
```

When `IMAGE_BASE_URL` or `IMAGE_API_KEY` is empty, X2RED reuses the corresponding text-provider setting. Without `X2RED_IMAGE_MODEL`, the application keeps the reviewed prompt but does not falsely label a local placeholder as an original Skill render.

## Simplified-Chinese material research

Open **语料素材库 → 简中原料发现**, choose a platform and run a low-frequency keyword search. X2RED invokes the pinned `NanmiCoder/MediaCrawler` checkout in local search mode for:

- Xiaohongshu;
- Douyin;
- Kuaishou;
- Bilibili;
- Weibo;
- Tieba;
- Zhihu.

MediaCrawler reuses a user-controlled local Chrome/Chromium CDP session and its legitimate platform login state. X2RED does not copy or modify the upstream source, bypass login/CAPTCHA/access controls, fetch comments, or bulk-download media. This integration is restricted to local, low-frequency, non-commercial research and learning under the upstream license.

Relevant settings include:

```env
X2RED_MATERIAL_SEARCH_PROVIDER=mediacrawler
X2RED_MEDIACRAWLER_ROOT=./.vendor/MediaCrawler
X2RED_MEDIACRAWLER_PLATFORM=xhs
X2RED_MEDIACRAWLER_LOGIN_TYPE=qrcode
X2RED_MEDIACRAWLER_CONNECT_EXISTING=true
X2RED_MEDIACRAWLER_CDP_PORT=9222
```

Users review discovery candidates before importing them. X2RED retains the platform, author, canonical URL, text, metrics, discovery query and sanitized raw snapshot while excluding sensitive login fields.

Direct public-web imports remain available. The importer:

- allows only public HTTP/HTTPS URLs;
- rejects localhost, private, link-local and reserved addresses;
- validates every article and robots.txt redirect;
- rate-limits requests by host;
- caps page size;
- first extracts ordinary public HTML with Trafilatura;
- starts a new no-login, no-cookie Playwright context when the public HTML does not contain enough article text;
- validates browser navigation and subresources against the same public-address gate;
- does not bypass authentication, paywalls, CAPTCHAs or access controls;
- retains canonical URL, site/author, capture time, discovery source and extraction method;
- marks imported pages as `limited_quote` by default.

Detailed provider and browser settings are documented in [docs/MATERIAL_SEARCH_PROVIDERS.md](docs/MATERIAL_SEARCH_PROVIDERS.md).

A public page being readable does not automatically grant republication rights. Publication and image reuse still require human review.

## Full Guizang Xiaohongshu runtime

Open **创作工作台 → 制图** and select:

- **Guizang Editorial · 原生完整链**
- **Guizang Swiss · 原生完整链**

The first run installs the exact pinned upstream checkout under:

```text
data/native-skills/guizang-social-card-skill
```

The native chain uses the upstream SKILL, references, 28 layout recipes, theme presets, seed templates, assets, Node dependencies and validator. X2RED generates page plans and poster sections against those contracts, screenshots the actual `.poster.xhs` elements with Playwright, and permits one bounded repair from validator output.

Guizang is AGPL-3.0 and remains a separate checkout with its LICENSE, Git metadata, upstream source link and local source path visible in **模型与 Skill**. X2RED does not relabel it as MIT.

## Full Minimal Zine runtime

In **公众号工作台 → 轻内容图组**, move through task setup, copy candidates, visual storyboard and final delivery. Rendering always starts from the currently selected candidate and current editor text, not merely an older saved version ID.

The native chain:

1. reads the complete upstream `SKILL.md`;
2. freezes each page's phrase, note, metaphor, layout, anchor, accent, texture, mood, focus and zoom in an immutable child `PlatformVariant`;
3. compiles a strict text-free visual prompt and calls the configured image model only for raw visual anchors;
4. stores raw `anchor-XX.png` files separately from final `poster-XX.png` files;
5. composes Chinese text and page numbers locally with a cmap-verified CJK font;
6. supports `render_missing`, local-only `recompose`, and model-calling `regenerate` modes;
7. atomically rebuilds `article.md`, `manifest.json`, `preview.html` and the release ZIP under `data/exports/wechat/{variant_id}/`.

The release ZIP uses an explicit allowlist and excludes raw anchors. Negative prompts, constrained high-risk edge cleanup and local recomposition reduce watermark/badge risk but cannot prove that an image model will never emit one; final visual, copyright and factual review remains mandatory.

The upstream project is MIT and is installed as a pinned separate checkout under `data/native-skills/gc-minimal-zine-poster-v0-1`.

## Native Skill installation and licenses

Open **模型与 Skill → 原版 Skill 运行时** to install or reinstall a pinned upstream version, inspect its license, open its source repository and see the local source path.

Detailed notices:

- [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)
- [THIRD_PARTY_NATIVE_SKILLS.md](THIRD_PARTY_NATIVE_SKILLS.md)

## Xiaohongshu workflow

1. Import a source or collect one from 原料库.
2. Use the quick editorial flow or complete a multi-Agent writing project.
3. Review the immutable draft in **创作工作台 → 文案**.
4. Open **制图** and choose the fast renderer or a Guizang native mode.
5. Review facts and rights, generate a package and inspect the preview.
6. X2RED stops before the final publish action.

## WeChat workflow

1. Select a classified source or freeze a corpus-pool batch.
2. Open **公众号工作台** and choose long-form or light content.
3. Review candidates, independent Agent reports and human revisions.
4. Persist the current candidate/editor before entering the visual storyboard.
5. Freeze storyboard edits as an immutable child version, then render missing pages, recompose locally or explicitly regenerate selected raw anchors.
6. Inspect the final page set, provenance, preview, manifest and ZIP.
7. Complete factual, visual and rights review, then publish manually.

## Scheduler configuration

```env
X2RED_SCHEDULER_ENABLED=true
X2RED_SCHEDULER_TIMEZONE=Asia/Shanghai
X2RED_AUTO_L1_GRADES=T1,T2,T3
X2RED_AUTO_L2_GRADES=T2,T3
X2RED_AUTO_L2_DAILY_LIMIT=5
```

## Safety defaults

- The API binds to localhost in documented commands.
- No X account cookie is required or stored.
- Public-web imports use a clean browser context and do not bypass access controls.
- MediaCrawler may reuse a user-controlled local browser login only for low-frequency, non-commercial research; X2RED never bypasses platform controls.
- Imported web material defaults to limited quotation rather than unrestricted reuse.
- Xiaohongshu automation never clicks the final publish button.
- WeChat output defaults to local package generation and manual publishing.
- Review Agents return reports and do not silently overwrite the draft.
- A draft must be explicitly approved with fact and rights checks before publishing.
- Raw sources, metric evidence, score baselines, Agent runs, artifacts, revisions, variants, review events, rendered assets and package hashes are retained locally.

See [ARCHITECTURE.md](ARCHITECTURE.md), [docs/SIGNAL_TO_STORY.md](docs/SIGNAL_TO_STORY.md), [docs/MULTIPLATFORM_SKILL_PACKS.md](docs/MULTIPLATFORM_SKILL_PACKS.md), [docs/WORKFLOW.md](docs/WORKFLOW.md), [docs/API.md](docs/API.md), and [docs/SECURITY.md](docs/SECURITY.md).
