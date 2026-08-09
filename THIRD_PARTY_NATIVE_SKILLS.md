# X2RED Native Skill Runtime

X2RED can install and invoke the following upstream Skills as separate, pinned Git checkouts under `data/native-skills/`.

## Guizang Social Card Skill

- Upstream: https://github.com/op7418/guizang-social-card-skill
- Pinned commit: `cf4b810fac1c73fb65a2bb31d8c9278d82cbc4c5`
- License: GNU Affero General Public License v3.0 (`AGPL-3.0`)
- Integration: separate checkout, unmodified upstream templates/references/assets, file and subprocess adapter
- Source access: the application displays the upstream repository and installed source path

X2RED does not relabel the Guizang code as MIT and does not copy a reduced subset into X2RED. Generated tasks use the upstream seed templates, layout recipes, theme tokens, validator, and Playwright-compatible HTML output. Any local modifications to the upstream component must remain under its applicable license and should be recorded prominently.

## GC Minimal Zine Poster

- Upstream: https://github.com/LiamGvchi/gc-minimal-zine-poster
- Pinned commit: `4cb0396ad4e834019f753b37e1c4f415f5e02026`
- License: MIT
- Integration: separate checkout; the full `SKILL.md` Standard Mode Prompt Compiler is used to compile prompts before calling the configured image-generation API

The v0.1 checkout remains available for explicit legacy rollback. The production compiler uses the parallel, unmodified v0.3.0 snapshot:

- Tag: `v0.3.0`
- Pinned commit: `342b5c11d6fa9be261841ec722c12a683a9fa5e9`
- License: MIT
- Vendored source: `apps/api/app/vendor/native-skills/gc-minimal-zine-poster-v0-3`
- Included upstream material: `SKILL.md`, `references/`, `evals/`, and referenced examples
- Runtime integration: offline install into `data/native-skills/gc-minimal-zine-poster-v0-3`; web handoff and API image generation consume the same structured `VisualPromptSpec`

## Public-web material research

The material harvester is X2RED code, not part of either upstream Skill. It is limited to public HTTP/HTTPS resources and:

- checks `robots.txt`;
- rate-limits by host;
- rejects local, private, link-local, reserved, and internal addresses;
- does not bypass authentication, paywalls, CAPTCHAs, or access controls;
- stores canonical URLs and provenance;
- marks imported web pages as `limited_quote` by default;
- requires human rights review before publication or image reuse.
