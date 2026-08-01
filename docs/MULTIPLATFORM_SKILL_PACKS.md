# Multi-platform Skill Packs and WeChat Workbench

X2RED 0.8 introduces a platform-variant layer. Sources, evidence packs, personal style snapshots, and multi-Agent final drafts remain shared, but each publishing platform receives an independent immutable version.

```text
X source / X2PDF Article
        ↓
normalized source + evidence
        ↓
quick editorial or multi-Agent final draft
        ↓
┌──────────────────────┬────────────────────────┐
│ Xiaohongshu variant  │ WeChat article variant │
│ short editorial copy │ long-form restructuring│
│ 3:4 card storyboard  │ inline HTML + covers   │
└──────────────────────┴────────────────────────┘
```

A WeChat version never overwrites its base `DraftRevision`. Saving an edit creates a new `PlatformVariant` version.

## Curated Skill Pack registry

A Skill Pack is a user-facing group of real X2RED Skills. Enabling or disabling a pack changes the underlying Skill bindings rather than only changing UI labels.

Current packs:

| Pack | Platform | Main capabilities |
| --- | --- | --- |
| Xiaohongshu editorial growth | Xiaohongshu | selling-point ranking, title directions, caption/hashtags, benchmark-aware hooks |
| Style × Layout visual matrix | Xiaohongshu | independent style, layout and palette selection |
| Material-first social design | Multi-platform | source material inventory, screenshot treatment, safe zones, paired covers |
| Long-form illustration planner | Multi-platform | diagram/flow/comparison/scene placement briefs |
| WeChat editorial adapter | WeChat | long-form restructuring, title, summary, citations, illustration plan |
| WeChat inline design system | WeChat | six themes, chapter numbering, keyword marking, inline HTML and QA |
| WeChat draft publisher | WeChat | optional future API/CDP draft adapter; disabled by default |

The registry also checks common local skill roots for matching `SKILL.md` installations:

```text
~/.claude/skills
~/.codex/skills
~/.openclaw/skills
```

Detection is read-only. X2RED does not automatically execute detected third-party code.

## License handling

X2RED remains MIT licensed.

Permissively licensed sources are adapted with attribution. AGPL repositories are treated as public product/design research only: X2RED independently implements the capability boundaries using its existing architecture and does not copy upstream code, templates, components, styles, scripts, assets, or prompt text.

See `THIRD_PARTY_NOTICES.md` for the complete repository and license list.

## Xiaohongshu platform adaptation

After the existing reader-first drafting process, enabled Xiaohongshu Skills may run one optional final model pass:

```text
selling-point priority
→ title formula exploration
→ hook and reading-rhythm adjustment
→ separate caption and hashtags
→ evidence-bound sanitation
```

This pass is optional and failure-tolerant. If the model endpoint cannot serve another request, X2RED keeps the already completed reader-first draft instead of failing the entire generation.

## Rich social-card dimensions

The card workbench separates four concerns:

### Visual style

- Editorial
- Swiss
- Knowledge
- Poster
- Notebook
- Bold
- Minimal

### Layout

- Sparse
- Balanced
- Dense
- List
- Comparison
- Flow
- Quadrant

### Palette

- Neutral
- Macaron
- Warm
- Neon
- Monochrome

### Material strategy

- Auto
- Source material first
- Text only

The resolved selections are stored in `CardRender.spec_json` so the output remains reproducible.

## WeChat Official Account workbench

### Create a version

1. Open **公众号工作台**.
2. Select a source.
3. Select a base draft, or use the source directly.
4. Choose one mode:
   - **公众号重构**: return to the evidence and build a long-form narrative.
   - **保留现有终稿结构**: retain more of the selected draft's order and voice.
5. Select a theme or use automatic selection.
6. Optionally enable citations and illustration planning.
7. Generate the independent WeChat version.

A completed multi-Agent writing project also exposes **去公众号**, which preselects the project source.

### Edit and version

The editor stores:

- article title
- cover subtitle
- list/share summary
- Markdown body
- internal tags
- selected theme
- frozen Skill profile
- illustration plan and citations

Saving creates a new version instead of modifying the previous version.

### Render and package

The deterministic renderer produces:

```text
article.md       source Markdown with frontmatter
article.html     clean inline-style section fragment
preview.html     browser preview with rich-copy action
cover-21x9.png   main WeChat cover, 2100 × 900
cover-square.png share cover, 1080 × 1080
manifest.json    provenance, theme and validation results
wechat-*.zip     complete release package
```

## Inline HTML quality gate

The clean fragment is designed for copy/paste into the WeChat editor. It rejects or warns on:

- `style`, `script`, `div`, `iframe`, form or button tags
- `class` and `id` attributes
- CSS Grid, Flexbox, positioning and float layout
- CSS variables, media queries, animations and keyframes
- JavaScript URLs
- remaining Markdown heading or code-fence markers
- empty or excessively short content
- missing H2 structure in a long-form article
- exceptionally long single paragraphs
- excessive external links

Preview-only toolbar code is not included in `article.html`.

## Themes

All themes in X2RED are original implementations:

- Editorial Blue
- Vermillion
- Graphite
- Zen
- Receipt
- Olive

Automatic selection uses deterministic content signals and can be manually overridden.

## Paired covers

The cover Skill produces a coordinated pair:

- 21:9 main cover for the WeChat article list
- 1:1 share cover for compact sharing surfaces

Playwright is used when available. A deterministic Pillow fallback is retained for offline environments.

## Publishing boundary

X2RED 0.8 generates validated local output and a release package. It does not silently publish a WeChat article. The `wechat.publish_draft` Skill is disabled by default and reserves a clear interface for a future API or browser adapter with explicit credentials and human final confirmation.

## Data model

`platform_variants` stores:

- source and optional base-draft references
- platform and format
- monotonic platform-specific version
- title, subtitle, summary, Markdown and rendered HTML
- theme
- frozen Skill configuration
- structured metadata and illustration plan
- rendered output paths
- state and errors

Deleting a source cascades to its platform variants. Existing source, draft, writing-project, card, and publishing workflows remain compatible.
