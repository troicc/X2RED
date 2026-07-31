# X2RED architecture

## Product boundary

X2RED is an editorial workstation, not a timeline scraper or unattended publishing bot. Every source enters because the user selected it, every generated draft is reviewable, and every Xiaohongshu publication requires a final human click.

## Runtime

```text
Chrome extension / local web UI
            |
            v
FastAPI intake and editorial API
            |
  +---------+----------+----------------+
  |                    |                |
FxTwitter provider   Asset store    Editorial service
  |                    |                |
Raw snapshots       SHA-256 files   Draft revisions
  +--------------------+----------------+
                       |
                  SQLite database
                       |
                  Review approval
                       |
                  Publish package
                       |
          Playwright XHS preparation
          (never clicks final publish)
```

## Replaceable boundaries

- `XSourceProvider`: FxTwitter today; official X API, self-hosted FxEmbed, or manual capture later.
- `EditorialService`: deterministic local fallback plus optional OpenAI-compatible model gateway.
- `Publisher`: package export is always available; Playwright is an optional desktop adapter.
- `AssetStore`: local content-addressed files now; encrypted external storage can be added later.

## Durable domain objects

- `SourceItem`: one X post or tombstone.
- `SourceRelation`: thread, reply, quote, or repost relationship.
- `RawSnapshot`: immutable provider response and payload hash.
- `Asset` and `AssetVariant`: original media plus available encodes.
- `DraftRevision`: immutable editorial versions.
- `ReviewDecision`: explicit approval or rejection event.
- `PublishTask`: approved frozen payload, package hash, state, and result.

## Workflow states

```text
source: available | unavailable | deleted | private
asset: discovered | downloading | ready | failed
review: pending | approved | rejected
publish: draft | approved | packaged | awaiting_user_confirmation | published | failed
```

## Deliberate non-goals for v0.1

- Broad timeline mirroring.
- Automatic trend-to-post pipelines.
- Automatic comments, follows, or direct messages.
- Storing a user's X cookie.
- Clicking the final Xiaohongshu publish button.
