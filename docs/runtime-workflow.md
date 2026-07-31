# X2RED Runtime Workflow

## Intake

1. User submits an X URL.
2. FxTwitter resolves the source graph.
3. Raw provider response is stored.
4. Media variants enter the asset pipeline.

## Editorial

Pipeline:

```
SourceGraph
 -> Claim extraction
 -> Context assembly
 -> Translation
 -> Xiaohongshu rewrite
 -> Card specification
 -> Review
```

## Publishing

Publishing is intentionally gated:

```
draft
 -> review_required
 -> approved
 -> publish_prepared
 -> user_confirmation
 -> published
```

Automatic silent publishing is not part of the default workflow.
