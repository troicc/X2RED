# Third-party method and compatibility notices

X2RED remains licensed under the MIT License. The platform Skill Pack registry records external projects that informed capability design. Unless explicitly stated below, X2RED does not bundle or execute those projects.

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
- X2RED implementation does not embed Baoyu's scripts. Installed upstream skills are detected only to inform the user; they are never executed without an explicit future adapter and user action.

### doocs/md

- License: WTFPL 2.0
- Upstream: https://github.com/doocs/md
- Adapted concepts: browser preview expectations for WeChat-friendly Markdown and rich technical content.

## AGPL projects used only as public design research

### op7418/guizang-social-card-skill

- License: GNU Affero General Public License v3.0
- Upstream: https://github.com/op7418/guizang-social-card-skill
- Research concepts: material-first card planning, screenshot treatment, subject safe zones, and paired WeChat covers.
- No upstream code, templates, styles, scripts, assets, or prompt text are copied into X2RED. X2RED's implementation is an independent reimplementation using its existing MIT codebase.

### isjiamu/gzh-design-skill

- License: GNU Affero General Public License v3.0
- Upstream: https://github.com/isjiamu/gzh-design-skill
- Research concepts: WeChat inline-style constraints, chapter numbering, restrained keyword marking, preview/copy workflow, and deterministic HTML validation.
- No upstream code, templates, components, styles, scripts, assets, or prompt text are copied into X2RED. X2RED's themes and renderer are original implementations.

## External Skill Pack detection

X2RED may report whether a named skill directory exists under common local skill roots such as `~/.claude/skills`, `~/.codex/skills`, or `~/.openclaw/skills`. Detection is read-only. It does not import, run, modify, or redistribute the detected project.
