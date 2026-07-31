# Editorial workflow

## 1. Intake

Paste a supported X URL or use the Chrome extension. Choose:

- **Thread**: focal post plus the author's thread. This is the default.
- **Conversation**: thread plus available replies. Use this only when discussion context matters.

X2RED stores the exact FxTwitter response in `data/raw` and normalizes the source graph into SQLite.

## 2. Assets

Media returned by FxTwitter is represented as `Asset` and `AssetVariant`. The default selector prefers MP4/H.264 variants at or below 1080p. Downloads are restricted to known X/FxTwitter media hosts and saved by SHA-256 under `data/assets`.

A failed media download does not discard the source text. The UI shows the failure on that asset so it can be retried or handled manually.

## 3. Editorial drafting

The deterministic fallback works without an AI account. It creates an editable Chinese structure and explicitly warns that source-only claims still require external verification.

When `X2RED_MODEL_BASE_URL`, `X2RED_MODEL_API_KEY`, and `X2RED_MODEL_NAME` are configured, X2RED calls an OpenAI-compatible `/chat/completions` endpoint. Invalid model output falls back to the deterministic editor.

Every save creates a new immutable `DraftRevision`; earlier versions remain in the database.

## 4. Review

A draft must receive an explicit `approved` review event before package creation. Rejecting a version does not delete it. Edit the draft, save a new version, and approve that version instead.

## 5. Publish package

The package contains:

- `publish.json`: frozen title, body, tags, source and asset paths.
- `caption.txt`: copy-ready body and hashtags.
- `media/`: ordered copies of ready local assets.

The package SHA-256 is saved in `PublishTask`.

## 6. Xiaohongshu preview

Install the optional publisher dependencies and Chromium, then press **Open Xiaohongshu preview**. A persistent browser profile opens Creator Center and attempts to upload and fill the approved package.

X2RED deliberately never clicks the final publish button. Review the account, title, body, media order, disclosure, rights, and platform preview before publishing manually.
