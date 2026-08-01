# X2RED

X2RED is a local-first **signal intelligence and multi-platform editorial studio** for finding useful material, building reviewed Chinese writing, and producing Xiaohongshu and WeChat assets.

## Working application

The current application can:

1. Import X posts, threads and full X Articles.
2. Preserve raw provider responses, structured blocks, relationships and source media.
3. Monitor profiles, searches, quote streams and trends on a durable schedule.
4. Store metric snapshots and score content against a frozen author-relative baseline.
5. Run L1 candidate analysis, limited L2 deep decomposition and reusable pattern extraction.
6. Generate content through either a quick editorial pipeline or an artifact-driven multi-Agent writing studio.
7. Train personal style profiles from authorized samples, held-out samples and author feedback.
8. Discover public Simplified-Chinese material through GDELT, RSS/Atom and sitemaps.
9. Import selected public article pages with robots.txt checks, per-host rate limits, provenance and a default `limited_quote` rights state.
10. Create immutable platform-specific versions from the same source and evidence base.
11. Render Xiaohongshu cards with the existing fast renderer or the complete upstream Guizang Editorial/Swiss runtime.
12. Generate Minimal Zine posters through the complete upstream Prompt Compiler and an explicitly configured image model.
13. Generate WeChat long-form Markdown, validated inline HTML, covers, previews and ZIP release packages.
14. Record source/media rights decisions and explicit human approval before publishing.
15. Open platform preparation flows while stopping before the final publish action.

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

The startup scripts create `.venv`, install X2RED, apply database migrations and bind the service to `127.0.0.1:8787`.

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

## Public material research

Open **原料库** and choose the intended use:

- 中老年生活
- 人生慰藉
- 节气时令
- 照片叙事
- 一句短评

Discovery supports:

- GDELT DOC Chinese-language article candidates;
- public RSS and Atom feeds;
- public sitemaps;
- direct public article URLs.

The importer:

- allows only public HTTP/HTTPS URLs;
- rejects localhost, private, link-local and reserved addresses;
- validates every article and robots.txt redirect;
- respects robots.txt;
- rate-limits requests by host;
- caps page size;
- does not bypass authentication, paywalls, CAPTCHAs or access controls;
- retains canonical URL, site/author, capture time and extraction metadata;
- marks imported pages as `limited_quote` by default.

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

In **公众号工作台 → 轻内容图组**, generate or select a light-content version and choose **用原版 Minimal Zine 生图**.

The native chain:

1. reads the complete upstream `SKILL.md`;
2. selects layout, anchor, typography, accent, texture and mood per page;
3. compiles the four-part Standard Mode image prompt;
4. calls the configured image model;
5. stores the final prompt, recipe, interpretation, model and generated file.

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

1. Complete or select a source/draft.
2. Open **公众号工作台**.
3. Choose long-form editing or the independent light-content lab.
4. Review candidates, independent Agent reports and human revisions.
5. Render the deterministic six-route visual output or the configured native Minimal Zine output.
6. Generate the final package and publish manually.

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
- Public-web research does not bypass access controls.
- Imported web material defaults to limited quotation rather than unrestricted reuse.
- Xiaohongshu automation never clicks the final publish button.
- WeChat output defaults to local package generation and manual publishing.
- Review Agents return reports and do not silently overwrite the draft.
- A draft must be explicitly approved with fact and rights checks before publishing.
- Raw sources, metric evidence, score baselines, Agent runs, artifacts, revisions, variants, review events, rendered assets and package hashes are retained locally.

See [ARCHITECTURE.md](ARCHITECTURE.md), [docs/SIGNAL_TO_STORY.md](docs/SIGNAL_TO_STORY.md), [docs/MULTIPLATFORM_SKILL_PACKS.md](docs/MULTIPLATFORM_SKILL_PACKS.md), [docs/WORKFLOW.md](docs/WORKFLOW.md), [docs/API.md](docs/API.md), and [docs/SECURITY.md](docs/SECURITY.md).
