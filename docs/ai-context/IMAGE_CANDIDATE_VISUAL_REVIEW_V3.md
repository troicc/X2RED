# V3 图片候选、Contact Sheet 与视觉审稿合同

更新时间：2026-08-09

## 1. 目标和边界

V3 把 Minimal Zine 的“一个 Prompt 直接得到一张 raw anchor”改为“同一冻结 Prompt 下的候选竞争、视觉审稿、人工选择和最多一次定向修复”。图片模型仍只生成无字视觉锚点；中文、页码和最终版式继续由 X2RED 本地合成。

V3 不改变 V1 的 Prompt compiler、V2 的 `VisualBible` / `PageVisualBrief` 权威，也不迁移或重写历史版本。旧版本和 `legacy` 模式仍可按原路径读取。

## 2. 统一候选模型

API 生图和 ChatGPT Images 网页回传都写入同一个 `ImageCandidateLifecycle`：

- 每页拥有独立 `ImageCandidatePageState`；
- 每次生成或上传建立 `ImagePromptRun`，冻结 Prompt、Prompt fingerprint、provider、model、请求候选数、实际调用次数、运行时回退、usage、成本和延迟；
- 每张候选保存 run ID、候选序号、provider/model、图片 SHA-256、尺寸、artifact key、成本、延迟、状态和审稿结果；
- 人工选择、保留、批准、驳回、修复和失效均追加审计事件，不物理覆盖其他候选；
- 只有审稿通过且仍有效的候选可以成为该页 `selected_candidate_id`。

手工网页路径允许一次上传 1—4 张；API 默认请求 3 张。两条路径只在 provider 和调用方式上不同，候选、审稿、选择、打包门禁与审计结构完全相同。

## 3. Provider 能力与调用回退

`ModelClient.image_capabilities()` 显式返回：

- `candidate_count`：是否支持单次 `n > 1`；
- `image_reference`：是否能携带参考图；
- `image_edit`：是否支持图片 edit；
- `multi_turn`：是否支持多轮图像修改；
- `usage`：是否返回 usage/cost 元数据。

已知 OpenAI `gpt-image` 路径声明完整能力；已知 GLM/Zhipu generation 路径声明实际可用能力；未知 provider 采用保守能力集。即使 provider 静态声明支持 `n`，若运行时拒绝多图请求，客户端也会记录失败尝试并按 `n=1` 顺序调用，不能静默伪装为一次多候选响应。

## 4. Contact Sheet

每页候选写入 `contact-sheet-XX.png`：

- 使用规范化后的原始候选缩略图；
- 只叠加 `#1`、`#2` 等候选编号；
- 不叠加 Prompt、审稿结论或长文字；
- Contact Sheet、候选原图和 raw anchor 可供审稿与追溯，但不进入发布 ZIP。

选择新候选只更新该页 raw anchor 并重新本地合成；原候选文件、记录和 Contact Sheet 继续保留。

## 5. 视觉审稿

每张候选保存十个结构化维度：

- `semantic_match`；
- `subject_clarity`；
- `composition`；
- `thumbnail_hook`；
- `series_consistency`；
- `texture`；
- `color_anchor`；
- `artifacts`；
- `text_safety`；
- `cliche_score`。

当前本地 critic 是确定性图片预检：它能检查尺寸、缩略图可读性、色彩/质感、边缘与潜在文字风险，并结合冻结简报给出可审计评分；它不伪称已经完成真实世界事实识别或完整语义视觉理解。最终视觉、版权、水印、异常文字和事实复核仍由人完成。

未通过自动门禁的候选不能自动选中。人工可以明确批准，批准动作及理由会留在审计记录中；驳回必须填写具体理由。

## 6. 一次定向修复

每页自动修复上限固定为 1：

1. critic 只选择一个主要缺陷；
2. 修复 Prompt 完整重复 V1/V2 已冻结的不变量和参考图约束；
3. provider 支持 edit 时优先调用 edit，否则重新 generation；
4. 修复结果作为新候选保存，不覆盖原候选；
5. 修复后仍不合格则交给人工，不进行第二次自动重试。

该上限同时由 domain schema、service 和 UI 控件执行，不能只依赖前端禁用按钮。

## 7. 发布门禁与产物

每页只有一个通过审稿且未被驳回/失效的选中候选，才允许生成该页 raw anchor 与 final poster。全部页面都满足该条件后，才允许重建完整 manifest、HTML preview 和 ZIP。

发布 ZIP 继续使用显式 allowlist，仅包含最终交付文件；以下内容不得进入 ZIP：

- 候选原图；
- Contact Sheet；
- raw anchor；
- critic 中间记录和修复参考图。

候选生命周期写入版本 metadata，文件路径写入 `output_paths_json`，最终 poster metadata 同时记录选中候选 ID、图片 hash、Prompt run 和审稿摘要，使每张最终图都能回溯到冻结 Prompt 与具体候选。

## 8. API 与 UI

候选操作接口：

- `POST /api/native-skills/minimal-zine/variants/{variant_id}/candidates/{page}/review`；
- `POST /api/native-skills/minimal-zine/variants/{variant_id}/candidates/{page}/select`；
- `POST /api/native-skills/minimal-zine/variants/{variant_id}/candidates/{page}/repair`。

外部网页回传接口继续使用 `external-anchor`，但 `file` 现在允许重复 1—4 次。轻内容页检查器显示 Contact Sheet、候选图片、十项评分、总分、provider/model、尺寸、成本、延迟、调用次数、自动修复次数，以及选中、保留、人工批准、驳回、定向修复、三候选再生、仅重排版和替换概念等动作。

## 9. Feature flag 与回滚

```env
X2RED_IMAGE_CANDIDATE_MODE=production
X2RED_IMAGE_CANDIDATE_COUNT=3
```

- `production`：启用统一候选生命周期、Contact Sheet、审稿、单次修复和发布门禁；
- `legacy`：回到单张 raw anchor 行为，用于紧急回滚；
- `X2RED_IMAGE_CANDIDATE_COUNT` 允许 1—4，默认 3，主要控制 API 请求；网页回传仍由实际上传数量决定。

回滚不会删除候选文件或 metadata，也不重写历史版本。重新切回 production 后仍可读取已有候选审计记录。

## 10. 验证

自动化覆盖 provider 能力、运行时 `n` 回退、API 三候选 trace、手工 1—4 张统一模型、候选保留、选择与驳回、一次 edit 修复、重复 invariants、失败打包门禁、allowlist 和 UI/API 静态合同。

临时隔离数据库上的真实浏览器验收覆盖 1280×800 与 375×812：3 张候选、Contact Sheet、十项分数、成本/次数、切换候选和驳回理由均可见且可操作，无页面级横向溢出，console 0 error。该探针使用合成候选图，不调用真实文本或图片模型，也不写用户主数据库。
