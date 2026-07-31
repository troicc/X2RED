# X2RED

X2RED is a local-first editorial studio for turning **user-selected X posts** into reviewed, Xiaohongshu-ready content.

## Working MVP

The current application can:

1. Accept an `x.com`, `twitter.com`, `fxtwitter.com`, or `fixupx.com` post URL.
2. Read the post and author thread through the FxTwitter v2 read-only API.
3. Preserve the raw provider response and normalize posts, relations, and media variants.
4. Download selected X media into a content-addressed local asset store.
5. Generate an editable Chinese editorial draft, with an optional OpenAI-compatible model.
6. Record source/media rights decisions and explicit human fact/rights approval.
7. Render Xiaohongshu image cards and create an immutable, hashed publish package.
8. Open Xiaohongshu Creator Center in a persistent Playwright profile, upload/fill the approved package, and stop before the final publish click.
9. Discover candidate posts through search, timelines, quotes, and trends.
10. Receive the current X page from the included Chrome extension.

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

X2RED works without a model by generating a conservative deterministic draft. To use an OpenAI-compatible endpoint, set these values in `.env`:

```env
X2RED_MODEL_BASE_URL=https://your-provider.example/v1
X2RED_MODEL_API_KEY=your-key
X2RED_MODEL_NAME=your-model
```

## Chrome extension

Load `extension/chrome` as an unpacked extension. On an X post, click the extension action or the **Send to X2RED** context-menu entry. It opens the local editor with the current post URL prefilled.

## Docker

```bash
docker compose up
```

The port is published only on `127.0.0.1:8787`. Browser-assisted Xiaohongshu preview is intended to run from the native Python installation because it needs a visible desktop browser.

## Safety defaults

- The API binds to localhost in all documented commands.
- No X account cookie is required or stored.
- Media downloads are restricted to known X/FxTwitter media hosts and capped by size.
- Xiaohongshu automation never clicks the final publish button.
- A draft must be explicitly approved with fact and rights checks before a publish package can be prepared.
- Original media remains blocked until marked owned, licensed, or open-license; limited quotation applies to text only.
- Raw provider responses, draft revisions, review events, rendered cards, and package hashes are retained locally.

See [ARCHITECTURE.md](ARCHITECTURE.md), [docs/WORKFLOW.md](docs/WORKFLOW.md), [docs/API.md](docs/API.md), and [docs/SECURITY.md](docs/SECURITY.md).
