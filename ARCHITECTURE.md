# X2RED Architecture

## Goal
Local-first X content intelligence and Xiaohongshu editorial workflow.

## Principles
- FxTwitter is a replaceable read-only source adapter.
- No user X cookies are stored.
- Raw source payloads are immutable.
- Publishing requires human approval.

## Monorepo

```
apps/
  api/ FastAPI backend
  web/ React editorial studio
  extension/ browser capture helper
packages/
  domain/ shared models
  providers/ external source adapters
  media/ download and processing
  ai/ editorial pipelines
infra/
  docker
  migrations
```

## Core pipeline

X URL -> Intake Job -> FxTwitter Provider -> Source Graph -> Media Assets -> AI Editorial -> Review -> XHS Publisher

## Domains

### Source
SourceItem, SourceRevision, SourceRelation, AuthorProfile

### Media
Asset, AssetVariant, DownloadJob, MediaFingerprint

### Editorial
Draft, Claim, Translation, CardLayout, ReviewDecision

### Publishing
PublishAccount, PublishTask, PublishResult

## Provider chain

1. Local cache
2. FxTwitter public API
3. Self-hosted FxEmbed
4. Manual import

## First milestone

- Paste X URL
- Fetch thread
- Store normalized data
- Download media variants
- Generate editorial workspace
