# Security model

## Local boundary

Documented startup commands bind to `127.0.0.1`. Docker publishes only to the loopback interface. Do not expose the API to a LAN or the internet without adding authentication, TLS, CSRF protection, and an explicit reverse-proxy policy.

## X credentials

The default public FxTwitter provider does not need or store the user's X cookies. If a self-hosted FxEmbed provider is added later, its service credentials must be isolated from the user's daily account and stored outside the repository.

## Media SSRF controls

The media downloader accepts only HTTP(S) URLs on known X/FxTwitter media host suffixes and enforces a configurable maximum size. Provider responses are never allowed to choose arbitrary local paths.

## Model credentials

Model keys are loaded from environment variables. They are not returned through the API. A future desktop wrapper should move them to the operating-system keychain.

## Pool memory and source rights

Memory extraction creates a candidate only. Formal cards require explicit human approval, and sources without an approved rights state require an additional authorization confirmation. Pattern cards are stored as abstract patterns, not copied factual payloads. Memory cards retain source IDs and provenance while the full source remains in its original durable object; task prompts receive only the approved, scoped card fields.

Supersede and revoke actions preserve the audit trail instead of silently overwriting history. They are lifecycle controls, not a substitute for honoring deletion or retention obligations on the underlying source data.

## Publishing

Publish packages use local asset paths selected from the database. The browser adapter opens a persistent Xiaohongshu profile but does not store account passwords in SQLite and never clicks the final publish button.

## Data retention

Raw snapshots and drafts may contain personal data or deleted posts. The operator is responsible for deletion requests, copyright review, and retention policy. Do not use X2RED as a public mirror.
