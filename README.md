# X2RED

X2RED is a local-first editorial studio for turning **user-selected X posts** into reviewed, Xiaohongshu-ready content.

## Working MVP

The current application can:

1. Accept an `x.com`, `twitter.com`, `fxtwitter.com`, or `fixupx.com` post URL.
2. Read the post and author thread through the FxTwitter v2 read-only API.
3. Preserve the raw provider response and normalize posts, relations, and media variants.
4. Download approved X media into a content-addressed local asset store.
5. Generate an editable Chinese editorial draft, with an optional OpenAI-compatible model.
6. Record human approval and create an immutable publish package.
7. Open Xiaohongshu Creator Center in a persistent Playwright profile, fill the approved package, and stop before the final publish click.
8. Receive the current X page from the included Chrome extension.

## Start locally

Requires Python 3.12+.

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\\Scripts\\activate
python -m pip install -e '.[dev]'
cp .env.example .env
uvicorn app.main:app --app-dir apps/api --host 127.0.0.1 --port 8787
```

Open `http://127.0.0.1:8787`.

For browser-assisted Xiaohongshu preparation:

```bash
python -m pip install -e '.[publisher]'
python -m playwright install chromium
```

## Safety defaults

- The API binds to localhost in all documented commands.
- No X account cookie is required or stored.
- Media downloads are restricted to known X/FxTwitter media hosts.
- Xiaohongshu automation never clicks the final publish button.
- A draft must be explicitly approved before a publish package can be prepared.
- Raw provider responses, draft revisions, review events, and package hashes are retained locally.

See [ARCHITECTURE.md](ARCHITECTURE.md), [docs/WORKFLOW.md](docs/WORKFLOW.md), and [docs/SECURITY.md](docs/SECURITY.md).
