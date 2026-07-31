# Security model

## Local boundary

Documented startup commands bind to `127.0.0.1`. Docker publishes only to the loopback interface. Do not expose the API to a LAN or the internet without adding authentication, TLS, CSRF protection, and an explicit reverse-proxy policy.

## X credentials

The default public FxTwitter provider does not need or store the user's X cookies. If a self-hosted FxEmbed provider is added later, its service credentials must be isolated from the user's daily account and stored outside the repository.

## Media SSRF controls

The media downloader accepts only HTTP(S) URLs on known X/FxTwitter media host suffixes and enforces a configurable maximum size. Provider responses are never allowed to choose arbitrary local paths.

## Model credentials

Model keys are loaded from environment variables. They are not returned through the API. A future desktop wrapper should move them to the operating-system keychain.

## Publishing

Publish packages use local asset paths selected from the database. The browser adapter opens a persistent Xiaohongshu profile but does not store account passwords in SQLite and never clicks the final publish button.

## Data retention

Raw snapshots and drafts may contain personal data or deleted posts. The operator is responsible for deletion requests, copyright review, and retention policy. Do not use X2RED as a public mirror.
