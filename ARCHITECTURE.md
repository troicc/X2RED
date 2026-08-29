# X2RED architecture

## Product boundary

X2RED is a local-first Chinese content research and editorial workstation. It is not a broad timeline mirror, an access-control bypass, or an unattended publishing bot. Discovery is user-triggered, reusable sources retain provenance, generated versions remain reviewable, and the final platform publish action always belongs to the user.

## Three product layers

```text
01 语料素材库
X signals ───────────────┐
MediaCrawler discovery ─┼─> SourceItem ─> platform classification ─> CorpusPool
Web/document/manual ────┘                                      │
                                                               v
                                             frozen CorpusBatch + provenance
                                                               │
02 内容工作台                                                │
                    ┌──────────────────────┬────────────────────┴──────────────┐
                    v                      v                                   v
             Xiaohongshu              WeChat long-form              WeChat light content
                    └──────── immutable edit / render / review / package ──────┘

03 模型与 Skill
OpenAI-compatible text/image models · approved pool memory · style profiles · Guizang · Minimal Zine
```

X signal discovery and Simplified-Chinese platform discovery remain separate discovery experiences, but both converge on the same `SourceItem` boundary. UI selectors preserve platform classification rather than flattening every source into one long list.

Pool memory is a separate expression layer, not another evidence source. Approved cards answer “how should this be written?” and are retrieved by task scope and Agent role; the current source or `CorpusBatch` alone answers “what facts may be stated?”.

## Runtime

```text
Local web UI / optional browser extension
                    |
                    v
                FastAPI API
                    |
      +-------------+-------------+----------------+
      |                           |                |
discovery providers         editorial services   native Skills
      |                           |                |
RawSnapshot / SourceItem    immutable revisions   rendered artifacts
      +-------------+-------------+----------------+
                    |
             SQLite + local files
                    |
          review / frozen package
                    |
      user-controlled publishing handoff
```

The documented server binds to `127.0.0.1`. Model gateways and image generation use explicitly configured OpenAI-compatible endpoints. MediaCrawler runs as a pinned, separate local checkout and may connect to a user-controlled Chrome/Chromium CDP session; it is limited to low-frequency, non-commercial research and does not bypass platform controls.

## Durable domain objects

- `SourceItem`: normalized X, Simplified-Chinese platform, webpage, document, manual source or hidden batch anchor.
- `SourceRelation`: thread, reply, quote, repost and other source relationships.
- `RawSnapshot`: immutable provider/discovery payload and evidence record.
- `Asset` / `AssetVariant`: source media and derived encodes; media failure never deletes source text.
- `CorpusPool` / `CorpusPoolSource`: reusable multi-source content asset and membership.
- `CorpusBatch`: isolated, one-way frozen handoff containing pool revision, full-pool memory, selected source details, focus and provenance.
- `ReviewArtifact`: append-only review artifact; `memory_candidate`, `memory_card` and `memory_event` encode the human-gated memory lifecycle without overwriting old cards.
- `PoolMemorySnapshot`: immutable task selection containing query scope, selected card IDs, role-scoped prompt payload, hash and actual application state.
- `PoolMemoryUsage`: append-only record written only after a configured model consumes a card for a target role and stage.
- `DraftRevision`: immutable editorial revision.
- `PlatformVariant`: immutable Xiaohongshu or WeChat-specific revision; storyboard edits create child variants rather than overwriting parents.
- `ReviewDecision`: explicit human approval or rejection event.
- `PublishTask`: approved frozen payload, package hash, state and result.

## Replaceable boundaries

- X discovery providers can be replaced while preserving normalized source and raw evidence contracts.
- Simplified-Chinese discovery currently uses pinned MediaCrawler; candidates enter X2RED only after user selection and normalization.
- Editorial and prompt-compilation services use deterministic fallback where supported plus optional configured text models.
- Pool-memory retrieval is deterministic and available without a model, but fallback generation remains `applied=false` and creates no usage rows. Model roles receive only the dimensions they need; factual roles receive no style-memory payload.
- Image models generate Minimal Zine raw visual anchors only. Final Chinese typography and layout are local responsibilities.
- Package export is always available; browser publishing helpers stop before the final publish action.
- Local content-addressed storage can later be replaced by another protected asset store.

## Minimal Zine artifact boundary

For each light-content `PlatformVariant`, all final files live under `data/exports/wechat/{variant_id}/`:

- `anchor-XX.png`: raw, text-free image-model output;
- `poster-XX.png`: locally composed final page;
- `article.md`, `manifest.json`, `preview.html`;
- release ZIP containing only approved final artifacts.

`render_missing` fills absent work, `recompose` requires a verified raw anchor and never calls the image model, and `regenerate` explicitly replaces selected raw anchors. A complete artifact set is staged and validated before atomic promotion; failure preserves the previous package and database references.

Prompt compilation is a separate boundary before image generation. The pinned v0.3 Skill snapshot feeds one `VisualPromptCompiler`, and both manual web handoff and API rendering persist the same `VisualPromptSpec`. The spec binds semantic page context and provenance to source/Prompt fingerprints, preserves the upstream recipe, and exposes explicit degraded warnings. `production`, faithful `skill_v03`, and pinned v0.1 `legacy` modes are selected through one feature flag; no database migration or artifact relocation is required to roll back.

Before that compiler boundary, V2 freezes one article-level `VisualBible` and one selected `PageVisualBrief` per page from exactly three candidates. The Bible contains only project rendering invariants; current evidence determines page subjects. A series-level editor blocks repeated subjects/anchors, insufficient layout diversity, visual clichés, compound abstractions and missing evidence. The compiler treats the selected brief as the sole page-level visual authority, and any storyboard-semantic change invalidates prior Prompt/raw/composition traces. `X2RED_VISUAL_BRIEF_MODE=legacy` rolls back this layer without mutating historical variants.

After compilation, V3 introduces a separate image-candidate boundary. API providers request three raw candidates by default; manual web handoff accepts 1–4. Both paths persist the same Prompt-run and candidate schema, including provider/model, hash, dimensions, cost, latency, review and audit state. Contact Sheets contain only original thumbnails and candidate numbers. A candidate must pass the ten-dimension visual gate or receive explicit human approval before selection, and each page permits at most one directed repair with frozen invariants repeated. Selecting or rejecting a candidate never deletes its competitors. Only a complete set of approved selected candidates can rebuild the release package; candidates, Contact Sheets and raw anchors remain outside the ZIP. `X2RED_IMAGE_CANDIDATE_MODE=legacy` rolls back this boundary without deleting audit history.

## Isolation and review invariants

- Corpus-batch context flows one way and one layer deep; shared sources cannot pull an older batch's full memory into a newer one.
- Pool-memory candidates require human preview and approval; uncertain source rights require explicit authorization confirmation.
- Pool-memory cards are superseded or revoked through append-only events rather than physical overwrite.
- Historical memory controls style and structure only. Its names, numbers, dates, results and causal claims cannot cross the current evidence boundary.
- Each generated target freezes or clones an immutable memory selection; only real model consumption creates usage records.
- Source-text success and media success are independent.
- Human edits create new immutable revisions.
- Light-content rendering persists the current candidate and editor text before visual work.
- Final Chinese typography is never delegated to an image model.
- Model success never implies factual, visual or copyright approval.
- X2RED never clicks a final publish button.

## Deliberate non-goals

- Broad timeline or platform mirroring.
- High-frequency or unattended scraping.
- Authentication, CAPTCHA, paywall or access-control bypass.
- Automatic comments, follows or direct messages.
- Treating public availability as republication permission.
- Fully autonomous publishing.
