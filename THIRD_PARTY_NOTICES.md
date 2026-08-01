# Third-party method and compatibility notices

X2RED remains licensed under the MIT License. Some external projects inform capability design; two optional native Skills are installed as separate, pinned upstream checkouts and retain their own licenses.

## Separately licensed native Skill runtimes

### op7418/guizang-social-card-skill

- License: GNU Affero General Public License v3.0
- Upstream and source offer: https://github.com/op7418/guizang-social-card-skill
- Pinned commit: `cf4b810fac1c73fb65a2bb31d8c9278d82cbc4c5`
- Runtime location: `data/native-skills/guizang-social-card-skill`
- Integration: the exact upstream Git checkout remains separate from the MIT X2RED source tree. X2RED invokes its SKILL, references, 28 layout recipes, theme presets, seed templates, assets, Node dependencies, validator and Playwright-compatible HTML through file and subprocess boundaries.
- The installed checkout preserves the upstream LICENSE and Git metadata. X2RED displays the upstream source URL and local source path. Any modification to that component remains subject to the applicable AGPL-3.0 obligations.

### LiamGvchi/gc-minimal-zine-poster

- License: MIT
- Upstream: https://github.com/LiamGvchi/gc-minimal-zine-poster
- Pinned commit: `4cb0396ad4e834019f753b37e1c4f415f5e02026`
- Runtime location: `data/native-skills/gc-minimal-zine-poster-v0-1`
- Integration: X2RED reads the complete upstream `SKILL.md` Standard Mode Prompt Compiler, selects the six-axis visual recipe per page, calls the explicitly configured image-generation API, and stores the final prompt, recipe, interpretation, model and output.
- When no image model is configured, X2RED reports that requirement instead of presenting a reduced placeholder as an original Skill render.

See also `THIRD_PARTY_NATIVE_SKILLS.md`.

## Native adaptations under permissive licenses

### JuneYaooo/xhs-writer-skill

- License: Apache License 2.0
- Upstream: https://github.com/JuneYaooo/xhs-writer-skill
- Adapted concepts: material inventory, selling-point priority, multiple title directions, caption/hashtag separation, and publish-readiness checks.
- X2RED implementation: independently integrated with the existing evidence-bound editorial pipeline and rewritten for X2RED's data model and UI.

### JuneYaooo/social-account-doctor

- License: MIT
- Upstream: https://github.com/JuneYaooo/social-account-doctor
- Adapted concepts: benchmark-aware hook and structure diagnosis, cover/title diagnosis, and actionable prioritization.

### JimLiu/baoyu-skills

- License: MIT
- Upstream: https://github.com/JimLiu/baoyu-skills
- Adapted concepts: Style × Layout × Palette separation, long-form illustration planning, Markdown-to-WeChat workflow boundaries, cover metadata, and optional draft publishing adapters.
- X2RED implementation does not embed Baoyu's scripts. Installed upstream skills are detected only to inform the user; they are never executed without an explicit adapter and user action.

### doocs/md

- License: WTFPL 2.0
- Upstream: https://github.com/doocs/md
- Adapted concepts: browser preview expectations for WeChat-friendly Markdown and rich technical content.

## AGPL projects used only as public design research

### isjiamu/gzh-design-skill

- License: GNU Affero General Public License v3.0
- Upstream: https://github.com/isjiamu/gzh-design-skill
- Research concepts: WeChat inline-style constraints, chapter numbering, restrained keyword marking, preview/copy workflow, and deterministic HTML validation.
- No upstream code, templates, components, styles, scripts, assets, or prompt text are copied into X2RED. X2RED's themes and renderer are original implementations.

### pmlaowangba-lab/obsidian-wx-open-source

- License: GNU Affero General Public License v3.0 or later.
- Upstream: https://github.com/pmlaowangba-lab/obsidian-wx-open-source
- Research concepts: write both `text/html` and `text/plain` clipboard flavors for manual WeChat pasting, keep API draft publishing separate from browser DOM automation, and upload images through the WeChat publishing path rather than assuming browser HTML injection is stable.
- No upstream TypeScript, bundled JavaScript, proxy code, themes, or publishing implementation is copied into X2RED. X2RED's browser assistant is an independent implementation with field-collision guards, title/body verification, a page-world bridge for the editor's own API, and a manual rich-clipboard fallback.

## External Skill Pack detection

X2RED may report whether a named skill directory exists under common local skill roots such as `~/.claude/skills`, `~/.codex/skills`, or `~/.openclaw/skills`. Detection is read-only. It does not import, run, modify, or redistribute the detected project.
