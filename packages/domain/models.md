# Domain Models

## SourceItem
Normalized X content record.

Fields:
- provider
- external_id
- canonical_url
- text_original
- author
- captured_at

## SourceRelation
Graph edges:
- thread_next
- reply_to
- quote_of
- conversation_reply

## AssetVariant
Media choices:
- image
- video
- codec
- bitrate
- dimensions

## EditorialDraft
Contains AI and human revisions.

## ReviewDecision
Tracks approval before publishing.
