# HTTP API

All endpoints are local by default.

## Intake

`POST /api/intake/x`

```json
{
  "url": "https://x.com/user/status/123",
  "mode": "thread",
  "download_media": true
}
```

## Sources

- `GET /api/sources`
- `GET /api/sources/{source_id}`
- `GET /api/assets/{asset_id}/file`

## Drafts

- `POST /api/sources/{source_id}/drafts`
- `GET /api/sources/{source_id}/drafts`
- `PUT /api/drafts/{draft_id}`
- `POST /api/drafts/{draft_id}/review`

## Pool memory

- `GET /api/pool-memory/source-options`
- `GET /api/pool-memory/candidates`
- `POST /api/pool-memory/candidates`
- `PUT /api/pool-memory/candidates/{candidate_id}`
- `POST /api/pool-memory/candidates/{candidate_id}/approve`
- `GET /api/pool-memory/items`
- `POST /api/pool-memory/items`
- `POST /api/pool-memory/items/{memory_id}/supersede`
- `POST /api/pool-memory/items/{memory_id}/revoke`
- `POST /api/pool-memory/retrieve-preview`
- `GET /api/pool-memory/snapshots`
- `GET /api/pool-memory/usages`

Candidate extraction never creates a formal card automatically. Approval and manual creation require explicit human confirmation, and uncertain source rights require an additional authorization confirmation. Supersede/revoke operations append lifecycle records rather than deleting history. Retrieval is task-scoped and fact-firewalled; snapshots and usages distinguish selection from actual configured-model consumption.

## Publish

- `POST /api/publish/drafts/{draft_id}/prepare`
- `GET /api/publish`
- `POST /api/publish/{task_id}/open-xhs`
- `POST /api/publish/{task_id}/mark-published`

`mark-published` accepts the manually confirmed Xiaohongshu result URL and moves an
`awaiting_user_confirmation` task to `published`. The URL must use HTTPS and belong
to `xiaohongshu.com` or one of its subdomains.

Interactive OpenAPI documentation is available at `/docs` while the app is running.
