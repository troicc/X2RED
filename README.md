# X2RED

X2RED is a local-first **signal intelligence and editorial studio** for discovering valuable X content and turning user-selected sources into reviewed, Xiaohongshu-ready work.

## Working application

The current application can:

1. Accept an `x.com`, `twitter.com`, `fxtwitter.com`, or `fixupx.com` post URL.
2. Read a post and author thread through the FxTwitter v2 read-only API.
3. Receive full X Articles from the companion X2PDF extension, including structured blocks and media.
4. Preserve raw provider responses and normalize posts, relations, articles, and media variants.
5. Monitor profiles, searches, quote streams, and trends on a durable schedule.
6. Store metric snapshots and score content against a frozen author-relative baseline using R, M, V, and growth velocity signals.
7. Run low-cost L1 candidate analysis and limited L2 deep decomposition, then retain reusable pattern cards.
8. Generate content through either the quick editorial pipeline or an artifact-driven multi-Agent writing studio.
9. Train personal style profiles from authorized original samples, held-out samples, and real author feedback.
10. Record source/media rights decisions and explicit human fact approval.
11. Render Xiaohongshu image cards and create an immutable, hashed publish package.
12. Open Xiaohongshu Creator Center in a persistent Playwright profile, upload/fill the approved package, and stop before the final publish click.

See [Signal-to-Story Studio](docs/SIGNAL_TO_STORY.md) for monitoring, scoring, L1/L2 analysis, multi-Agent writing, and personal style training.

## One-command start

Requires Python 3.12+.

macOS / Linux:

```bash
chmod +x scripts/start.sh
./scripts/start.sh
```

Windows:

```bat
scripts\start.cmd
```

The startup scripts create `.venv`, install the application, apply all database migrations, and bind the service to `127.0.0.1:8787`.

Open `http://127.0.0.1:8787`.

## Manual installation

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
python -m pip install -e '.[dev]'
cp .env.example .env             # Windows: copy .env.example .env
x2red check
x2red serve
```

`x2red serve` applies Alembic migrations before starting unless `--skip-migrate` is explicitly supplied.

For browser-assisted Xiaohongshu preparation:

```bash
python -m pip install -e '.[publisher]'
python -m playwright install chromium
```

Then prepare and approve a draft in the local interface, generate a publish package, and choose **打开小红书预览**. X2RED fills as much as possible but deliberately leaves the final publish action to the user.

## Optional model configuration

Deterministic ingestion, scheduling, snapshots, and scoring work without a model. L1/L2 intelligence, personal style training, and high-quality multi-Agent writing require an OpenAI-compatible endpoint:

```env
X2RED_MODEL_BASE_URL=https://your-provider.example/v1
X2RED_MODEL_API_KEY=your-key
X2RED_MODEL_NAME=your-model
```

Scheduler and automatic analysis defaults can be adjusted in `.env`:

```env
X2RED_SCHEDULER_ENABLED=true
X2RED_SCHEDULER_TIMEZONE=Asia/Shanghai
X2RED_AUTO_L1_GRADES=T1,T2,T3
X2RED_AUTO_L2_GRADES=T2,T3
X2RED_AUTO_L2_DAILY_LIMIT=5
```

## Chrome extension

Load `extension/chrome` as an unpacked extension. On an X post, click the extension action or the **Send to X2RED** context-menu entry. It opens the local editor with the current post URL prefilled.

For X Articles, use X2PDF 0.13+ and choose **发送到 X2RED** after the article has loaded.

## Docker

```bash
docker compose up
```

The port is published only on `127.0.0.1:8787`. Browser-assisted Xiaohongshu preview is intended to run from the native Python installation because it needs a visible desktop browser.

## Safety defaults

- The API binds to localhost in all documented commands.
- No X account cookie is required or stored by X2RED.
- Media downloads are restricted to known X/FxTwitter media hosts and capped by size.
- Xiaohongshu automation never clicks the final publish button.
- Multi-Agent studio mode stops for author confirmation at the brief, outline, and revision-plan gates.
- Review Agents return reports and do not silently overwrite the draft.
- A draft must be explicitly approved with fact checks before a publish package can be prepared.
- Original media remains blocked until marked owned, licensed, or open-license; limited quotation applies to text only.
- Raw provider responses, metric evidence, frozen score baselines, Agent runs, artifacts, draft revisions, review events, rendered cards, and package hashes are retained locally.

See [ARCHITECTURE.md](ARCHITECTURE.md), [docs/SIGNAL_TO_STORY.md](docs/SIGNAL_TO_STORY.md), [docs/WORKFLOW.md](docs/WORKFLOW.md), [docs/API.md](docs/API.md), and [docs/SECURITY.md](docs/SECURITY.md).
