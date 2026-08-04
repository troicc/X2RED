# X2RED workflow

## 1. Discover or import material

X2RED has three legitimate source paths:

1. **X signal discovery** monitors selected profiles, searches, quote streams or trends; candidates retain metric snapshots and may receive L1/L2 analysis.
2. **Simplified-Chinese platform discovery** runs a low-frequency, user-triggered search through the pinned local MediaCrawler checkout for Xiaohongshu, Douyin, Kuaishou, Bilibili, Weibo, Tieba or Zhihu.
3. **Web, document and manual import** accepts user-selected public inputs without bypassing authentication, paywalls, CAPTCHAs or network-address safety gates.

Discovery results are candidates, not automatically reusable content. The user selects what to import. X2RED then normalizes it as a `SourceItem`, preserves sanitized raw evidence and defaults uncertain reuse rights to human review.

## 2. Classify and review sources

The source library groups entries by corpus batch, X, each supported Simplified-Chinese platform, and web/document inputs. Users can search, inspect provenance and metrics, add editorial notes, set rights status, archive or restore sources, add them to corpus pools, or send them directly to a workspace.

A failed media fetch does not discard source text. Editing a source note, deleting a source, or changing pool membership recompiles affected corpus pools.

## 3. Build a reusable corpus pool

A `CorpusPool` is a durable content asset, not a one-shot generation form. Compilation cleans duplicated/HTML/URL noise, summarizes each member, extracts keywords, aggregates themes and contradictions, and creates a context-budgeted full-pool memory without simply dropping later sources.

Previewing the next batch does not consume usage. A formal generation or workspace handoff freezes a `CorpusBatch` containing:

- pool ID and revision;
- batch ID, sequence and fingerprint;
- compressed full-pool memory;
- detailed selected source IDs;
- focus, selection rationale and provenance.

The hidden batch anchor can be selected by a workspace. The `corpus_batch` edge is one-way and one layer deep so an old batch cannot contaminate a later context through shared sources.

## 4. Choose a content workspace

### Xiaohongshu

Select a source or frozen batch, use the quick editorial flow or a multi-Agent writing project, save immutable `DraftRevision` versions, and render cards with the fast renderer or pinned Guizang Editorial/Swiss runtime. Review facts, quotations, media rights and the exact approved version before preparing a package. X2RED stops before the final publish click.

### WeChat long-form

Create an immutable WeChat `PlatformVariant`, edit Markdown/HTML and summary/cover data, validate HTML, and generate a preview and package from the same version. Publishing remains manual.

### WeChat light content

The v15 workspace has four stages:

1. **任务设置** — choose the source/batch, recipe, page count, audience, tone, visual style and quality mode.
2. **文案候选** — compare generated candidates and reports; adopting or editing content creates an immutable version.
3. **视觉分镜** — persist the current candidate/editor first, expand one page at a time, edit page text and visual controls, then freeze the complete 3–6 page contract as an immutable child `PlatformVariant`.
4. **成品交付** — render, inspect the complete page set, preview, manifest, ZIP and review state.

The storyboard endpoint freezes editorial intent; it does not generate copy or call the image model.

## 5. Render Minimal Zine safely

The text model reads the complete pinned upstream Skill and compiles a per-page recipe. The image prompt requires a sparse 3:5 composition, one visual cluster, reserved text space and no text, numbers, logos, signatures, UI, labels, watermarks or badges.

The image model produces only raw visual anchors. X2RED then:

1. validates and stores `anchor-XX.png` separately;
2. performs constrained high-risk edge cleanup while preserving the upstream plate and color signal;
3. composes phrase, note and page number with a cmap-verified local CJK font;
4. writes final `poster-XX.png` pages;
5. rebuilds Markdown, manifest, preview and ZIP from the same variant;
6. excludes raw anchors from the release ZIP through an explicit allowlist.

Rendering modes are:

- `render_missing`: reuse valid complete pages, locally recompose valid raw anchors, and generate only genuinely missing selected work;
- `recompose`: require stored raw anchors and call neither prompt compiler nor image model;
- `regenerate`: explicitly call the image model for selected pages.

The complete directory is staged, validated and atomically promoted. A failure retains the previous directory, package and database references. Negative prompting and edge cleanup reduce—but cannot absolutely eliminate—model watermark or badge risk, so human visual review remains required.

## 6. Review and publishing handoff

Every workspace requires review of:

- factual claims, numbers and causality against sources;
- quotation scope and provenance;
- source and media rights;
- image watermarks, abnormal characters and platform marks;
- agreement between the approved version, preview and package.

Rejection does not delete a version. Package or publishing-helper failure retains the frozen payload and hash for diagnosis and retry. X2RED may prepare or open a platform workflow, but the user performs the final publish action.
