# W2：结构化写作 Agent 与 Claim-Evidence Matrix

更新时间：2026-08-29 +08:00

## 目标

W2 把深度写作的多 Agent 链从“模型返回一个看起来像 JSON 的对象”升级为可校验、可修复、可重放并能阻断错误完成状态的执行合同：

`任务单 → 证据包 → 大纲 → 初稿 → 三路结构化审稿 → issue 裁决 → 终稿 → claims 重提取 → claim-evidence matrix → 完成或阻断`

W2 不替代 W1。W1 决定哪些冻结 evidence chunks 可被召回；W2 决定 Agent 是否遵守输出合同、终稿是否仍在批准范围内，以及主要事实是否真的引用这些 evidence chunks。

## Feature flag 与兼容路径

环境变量：

`X2RED_WRITING_SCHEMA_MODE=production|legacy`

- 默认 `production`：所有模型角色使用严格 Pydantic Schema；失败时只允许一次结构修复；终稿必须通过 claim-evidence gate。
- `legacy`：保留 W2 前的非结构化执行与完成路径，但所有 AgentRun 和 artifact 都显式标记 `degraded`，不得宣称 Schema 或记忆已经生效。
- 切换 flag 不删除、不回填、不重写旧 artifact、AgentRun、DraftRevision 或来源。
- 无数据库迁移；新增状态和结构继续使用现有字符串/JSON 列。

## Agent 输出 Schema

`apps/api/app/domain/writing_agent_schemas.py` 为每类 Agent 产物定义 `extra=forbid` 的合同：

- `EditorBriefOutput`
- `EvidencePackOutput`
- `OutlineOutput`
- `DraftOutput`
- `ReaderReviewOutput`
- `FactReviewOutput`
- `StyleReviewOutput`
- `RevisionPlanOutput`
- `FinalDraftOutput`
- `FinalClaimsOutput`

位置统一使用 `TextLocation(section, paragraph_index, quote)`；至少一个锚点必须存在。每条 review issue 必须包含稳定 `issue_id`、类别、位置、严重度、说明、来源/初稿证据和最小修复。事实审稿 issue 还必须携带来源 evidence ref 或 evidence quote，不能只引用初稿原句。Agent 提交的 evidence ref 必须属于本任务冻结的 W1 引用集合；自造 `source_id:chunk_id` 会进入同一“一次修复”合同。

成功 artifact 在业务字段之外保存 `_structured_output`：

- mode：`production|legacy`
- status：`valid|repaired|degraded`
- schema name
- 是否执行修复
- 首轮校验错误
- 经过规范化的业务 payload SHA-256
- 明确 warning

API 同时通过 `WritingArtifactOut.structured_output` 暴露该 trace；业务 payload hash 不包含 provider completion metadata 和 trace 本身。

## 一次修复上限

production runner 的执行顺序固定为：

1. 将目标 JSON Schema 和上下文约束附加到 Agent Prompt。
2. 解析 JSON 并执行 Pydantic 与跨产物上下文校验。
3. 仅在 JSON、Schema 或合同错误时发起一次零温度结构修复；HTTP、鉴权和 provider 故障不伪装成 Schema 问题。
4. 修复结果再次校验。
5. 第二次仍失败则 AgentRun=`failed`，不保存普通成功 artifact；attempts、两轮错误和成本估算保留在 AgentRun。

只有配置模型返回且通过 production Schema 后，才可能记录池子记忆已被使用；事实角色的 memory IDs 始终为空，因此 claim extractor 和 fact reviewer 不会接收或登记历史风格记忆。确定性 fallback 和 legacy 产物始终是 degraded。

## Review → Chief → Final 权限边界

三路 reviewer 使用互不冲突的 ID 前缀：`reader-`、`fact-`、`style-`。重复 ID、无位置、无证据或无最小修复均不能进入普通成功链。

Chief Editor 只能对三份报告中已经存在的每个 issue_id 恰好裁决一次：`approve|reject|defer`。它不能新建 issue，也不能直接改正文。

Final Reviser 只能提交 `applied_changes` 引用批准的 issue_id；所有批准项都必须执行，未批准项不得出现。即使 applied_changes 合法，最终正文仍需接受独立 claim gate，以拦截正文层面的主张扩大。

## Final claims 与证据矩阵

终稿生成后，事实隔离的 `claim_extractor` 会重新提取所有 critical/major 事实、数字、因果、比较和能力主张。每条记录冻结：

- 终稿 exact quote 与位置
- claim 类型和重要性
- W1 `source_id:chunk_id` 引用与 evidence quote
- 初稿 origin claim ID
- 允许该变化的 approved issue IDs

数字、因果、比较和能力主张不能降为 minor。extractor 不能发明初稿 claim ID 或 approved issue ID；错误会进入同一“一次修复”合同。

本地 `ClaimChecker` 构建严格 `ClaimEvidenceMatrix`：

- evidence ref 必须存在于当前冻结 W1 bundle；
- evidence quote 必须在对应 chunk 中；无论是否提供 quote，statement 与 chunk 还必须达到确定性语义阈值，避免“真实引文支持无关主张”；
- origin claim 必须存在、语义相近且没有异常长度扩张；
- approved revision 必须只引用当前批准 issue；
- final exact quote 必须真实存在于终稿正文。

以下任一情况会使 `completion_allowed=false`：

- critical claim 无完整支持；
- major claim 无完整支持；
- critical/major claim 属于未经批准的新扩张；
- 抽取的终稿 exact quote 不存在。

阻断时项目进入 `claims_blocked / claim_evidence_gate`，不创建 output DraftRevision，也不能交接公众号成稿。终稿候选、final claims、matrix 和全部历史 AgentRun 保留供审查。

## UI 与可观测性

深度写作 UI 显示 `Schema 通过`、`Schema 已修复`、`降级输出`、`证据闸门通过` 或 `证据闸门阻断`。Stage 07 现在同时包含终稿、final claims 与 claim-evidence matrix。

`claims_blocked` 状态只允许查看候选终稿和矩阵，不显示继续运行或公众号交接按钮。颜色之外始终有文本状态。

## 验证

专门回归覆盖：

- 全部 Agent Schema 的严格解析与序列化重放；
- reviewer 位置/证据/minimal fix；
- Chief 发明或遗漏 issue；
- Final 执行未批准 issue 或漏执行批准 issue；
- 首次失败后一次修复成功；
- 第二次失败不保存成功产物；
- critical/major 无证据阻断；
- 有证据但未经批准的新主张仍阻断；
- 引用真实 evidence quote 但主张与原文无语义关系时仍阻断；
- 合法 approved revision 可通过；
- `claims_blocked` 永不变成 completed；
- production 与 legacy/no-model 的显式状态；
- UI 的降级和证据阻断文本。

W2 提交前本地定向回归为 `24 passed, 1 warning`，完整套件为 `184 passed, 8 warnings`。CI 数字仍必须以当前 PR latest head 为准，不从本文的本地数字推断。

## 回滚

1. 设置 `X2RED_WRITING_SCHEMA_MODE=legacy` 并重启服务。
2. 新任务恢复 W2 前执行路径，但 artifact/AgentRun 保持 degraded 标记。
3. 不删除 production 生成的 final claims、matrix、失败 run 或 `claims_blocked` 项目。
4. 修复后重新切回 production，并为新版本创建新的不可变产物；不要物理覆盖历史。

回滚只用于兼容或应急，不得用来把已知 critical/major 无证据终稿伪装成经过 W2 审核的完成结果。最终发布仍要求人工事实、版权和平台复核。
