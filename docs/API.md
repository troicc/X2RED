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

## Publish

- `POST /api/publish/drafts/{draft_id}/prepare`
- `GET /api/publish`
- `POST /api/publish/{task_id}/open-xhs`
- `POST /api/publish/{task_id}/mark-published`

`mark-published` accepts the manually confirmed Xiaohongshu result URL and moves an
`awaiting_user_confirmation` task to `published`. The URL must use HTTPS and belong
to `xiaohongshu.com` or one of its subdomains.

Interactive OpenAPI documentation is available at `/docs` while the app is running.
