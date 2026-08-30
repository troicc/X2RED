# X2RED 项目记忆

更新时间：2026-08-30 +08:00

## 一、当前快照

仓库：`troicc/X2RED`

当前本地任务分支：`agent/replace-crawlers-with-api-adapters`

OPS1 分支来源：已合并 UI1 的 `agent/replace-crawlers-with-api-adapters`，准确基线 SHA `c9e4b74a133b9543040c3e02cb13356c80f1cbef`

OPS1 PR #29 已在 latest head `b3ed174a97ac292fc7db90e5d087d0b055ca9b81` 的 CI run `33295636707` 全部成功后 squash merge；当前功能基线为 `4f6ac5c21144bbed4905f4ebbcfdbfb9a38707d3`。

基线 PR：`#19 重构简中素材采集、语料池与三层创作工作区`

C0 PR：`#20 C0：冻结创作质量基线与可重放评测夹具`，已于 2026-08-09 squash merge 到功能基线分支。

V1 PR：`#21 V1：对齐 Minimal Zine v0.3 视觉 Prompt compiler`，head `291d6a13ca8606628d1c2c781f7f15e298e57bc2` 的 `test (3.12)` 成功后已于 2026-08-09 squash merge，功能基线前进到 `a7b00d0005d024ab16a770dd7513031f5e21d548`。

V2 PR：`#22 V2：Visual Bible 与逐页视觉简报`，head `833c0d422ab9a8e942e79f0340408e199b40c210` 的 CI run `817` 成功后已于 2026-08-09 squash merge，功能基线前进到 `9086b6226b68e367e10327a577eb625e4d251b5b`。

V3 PR：`#23 V3：图片多候选、Contact Sheet 与视觉审稿`，head `5ceeefcbe894cbc8e367f6fcdb314ae738e56d40` 的 CI run `819` 成功后已 squash merge，功能基线前进到 `bd77743808a3eb1ccb0bfa29efa959c0aee2b33a`。

V4 PR：`#24 V4：本地中文排版 Recipe v2`，修复 head `0b87097865dc6d57b1bb082cb12b37e938a4e9bb` 的 CI run `823` 成功后已 squash merge；功能基线前进到 `012299e2c77a02b076eb15aed33e17ad6196ce38`。

W1 PR：`#25 W1：证据编译与混合检索`，latest head `9085faf29b8b86d47cfcd4a1a2cd93c3cc9a7158` 的 CI run `826` 全部成功后已 squash merge；功能基线前进到 `88b995bfc75f25673e78777ee6f575fc2a5eb666`。

W2 PR：`#26 W2：结构化 Agent 输出与最终主张矩阵`，latest head `4027d0c26ef9b76f4c976231322bca18cac1bb69` 的 CI run `33249003306` / job `99091311679` 成功后已 squash merge；功能基线前进到 `f6dd3bbb747cdfd1758f0542f6977f6f58dd4103`。

W3 PR：`#27 W3：标题竞赛、授权风格范例与真实反馈`，latest head `1cee81507088f09eed6d2f17bf1efbd8c0810780` 的 CI 成功后已 squash merge；功能基线前进到 `519228354279fc1641bef2fe19a08991b9ed4731`。

UI1 PR #28 的 latest-head GitHub Actions run `33292506967` 成功后已 squash merge；功能基线前进到 `c9e4b74a133b9543040c3e02cb13356c80f1cbef`。OPS1 从这一准确远端 head 建立独立分支。

C0 首个提交：`08c0920f154d51a7cdfa5d35a604d48b3d393672`

PR #19 属于 C0 的基线功能分支，不是 C0 分支本身。

2026-08-04 收尾前的远端基线 head：`417adb4640ee7411362bc7a943b42c2c806a341b`

2026-08-05 本轮开始时的本地/远端 head：`e38c6f1353994e270dccef18684ba7e1f086f68a`。PR #19 重新检查为 open、draft、mergeable，最新 Python 3.12 CI 成功；这些仍是易变化事实。

2026-08-06 20:29 再次查询 GitHub：PR #19 仍为 open、draft、mergeable，head 仍为 `e38c6f1353994e270dccef18684ba7e1f086f68a`，该 head 的 `test (3.12)` 成功；这些仍是易变化事实。

2026-08-09 重新查询 GitHub：PR #19 仍为 open、draft、mergeable、未合并，head 已前进到 `9073a4bc8a71a76dbf6762d7fc64a425eb3c99fe`；该 head 的 PR CI run `811` 成功。C0 在该准确 head 上建立独立本地分支，未把质量基线继续堆入 PR #19。

2026-08-09 21:34：C0 首个提交 `08c0920f154d51a7cdfa5d35a604d48b3d393672` 已推送到远端 `codex/x2red-c0-quality-baseline`，并创建 Draft PR #20，目标为 `agent/replace-crawlers-with-api-adapters`。PR #20 的 CI、mergeability 和 head 属于易变化事实，合并前必须重新查询。

2026-08-09 随后重新查询并完成 C0：PR #20 head `dd10c9f959c2b518be6f9ef1b910e3e9b7a9b261` 的 CI run `813` 成功，PR 标记 ready 后 squash merge；功能基线分支的新 head 为 `02aa1db7f5eef45e438c8776bad0703c3e3ef441`。V1 从这个已合并 head 创建独立分支。

2026-08-29 16:45 再次查询 GitHub：PR #19 仍为 open、draft、mergeable，head 为 `bd77743808a3eb1ccb0bfa29efa959c0aee2b33a`。V3 PR #23 已在 head `5ceeefcbe894cbc8e367f6fcdb314ae738e56d40` 的 CI run `819` 成功后 squash merge，merge commit 即该功能基线 head。V4 从这个准确远端 head 创建；这些 PR/CI 事实在下一次合并前仍须重新查询。

2026-08-29 17:06 提交 V4 前再次查询 GitHub：PR #19 仍为 open、draft、mergeable，功能分支 head 仍为 `bd77743808a3eb1ccb0bfa29efa959c0aee2b33a`，与 V4 本地基线一致。

2026-08-29 17:08：V4 首个提交 `0f4a6773cbf9258c0ffc2da021830950ebc4cbfe` 已推送并创建 Draft PR #24；下一次合并判断必须以随后文档状态提交后的 latest head 和对应 CI 为准。

2026-08-29 17:14：PR #24 CI run `822` 在 Ubuntu 的 `test_wechat_workbench_api_end_to_end` 失败，其余迁移、静态门禁和 158 项测试均通过。根因不是生产排版降级，而是这个 V0.8 历史兼容流程未声明 legacy 模式，在无 CJK 字体的 runner 上触发 V4 production fail-closed 门禁。测试现显式设置 `X2RED_TYPOGRAPHY_RECIPE_MODE=legacy`；生产默认值与专门字体门禁测试保持不变，需以修复提交的新 head CI 再确认。

2026-08-29 17:23：V4 修复提交 `0b87097865dc6d57b1bb082cb12b37e938a4e9bb` 的 PR CI run `823` 全部成功；PR #24 转 Ready 后按该 expected head squash merge，合并提交为 `012299e2c77a02b076eb15aed33e17ad6196ce38`。PR #19 随即复核为 open、draft、mergeable，head 已同步到该提交。W1 从这一准确远端 head 建立独立分支。

2026-08-29 17:57：W1 实现提交 `0cfe4dd275d63c5b80d282c08b29a565bcc49489` 已推送并创建 Draft PR #25，base 为准确 V4 合并 head `012299e2c77a02b076eb15aed33e17ad6196ce38`。PR 创建前再次确认 PR #19 仍为 open、draft、mergeable，功能分支 head 未漂移。下一次合并必须使用状态文档提交后的 latest head 与对应 CI。

2026-08-29：W1 状态文档 head `9085faf29b8b86d47cfcd4a1a2cd93c3cc9a7158` 的 CI run `826`（GitHub run `33246837926`）全部成功；PR #25 转 Ready 后按该 expected head squash merge，功能基线 commit 为 `88b995bfc75f25673e78777ee6f575fc2a5eb666`。PR #19 随即复核为 open、draft、mergeable，head 已同步到该提交；W2 从这一准确 head 创建独立分支。

2026-08-29 18:54：W2 实现提交 `ba68082c46d3597fb1f92843a559bf9a048c24e8` 已推送并创建 Draft PR #26，base 为准确 W1 合并 head `88b995bfc75f25673e78777ee6f575fc2a5eb666`。PR 创建前再次确认 PR #19 仍为 open、draft、mergeable且功能分支 head 未漂移。初始 CI 已启动，但状态文档提交会产生新 head；下一次合并只认状态提交后的 latest-head CI。

2026-08-29：W2 状态 head `4027d0c26ef9b76f4c976231322bca18cac1bb69` 的 GitHub Actions run `33249003306` / job `99091311679` 在 2m54s 内成功；PR #26 转 Ready 后按该 expected head squash merge，功能基线 commit 为 `f6dd3bbb747cdfd1758f0542f6977f6f58dd4103`。W3 从这一准确 merge head 建立独立分支。

2026-08-29 19:46：W3 实现提交 `0750999eb305f203d417c1066e9fcdb2e1de9bdf` 已推送并创建 Draft PR #27，base 为准确 W2 合并 head `f6dd3bbb747cdfd1758f0542f6977f6f58dd4103`。PR 创建前再次确认 PR #19 仍为 open、draft、mergeable，功能分支 head 未漂移。状态文档提交会产生新 head，下一次合并只认该 head 对应的 CI。

2026-08-30：W3 latest head `1cee81507088f09eed6d2f17bf1efbd8c0810780` 的 CI 成功后，PR #27 已转 Ready 并按该 expected head squash merge；功能基线 commit 为 `519228354279fc1641bef2fe19a08991b9ed4731`。UI1 从这一准确远端 head 建立独立分支。

2026-08-30 12:24：UI1 提交前重新 fetch 并查询 GitHub；PR #19 仍为 open、draft、mergeable，head 与 UI1 base 均为 `519228354279fc1641bef2fe19a08991b9ed4731`，该 head 的 `test (3.12)` 成功。PR #27 状态为 merged，记录的 head/merge commit 分别为 `1cee81507088f09eed6d2f17bf1efbd8c0810780` / `519228354279fc1641bef2fe19a08991b9ed4731`。UI1 创建 PR 后仍须按其最新 head 重新判断 CI。

2026-08-30 12:25：UI1 实现提交 `039f85d1bf9c481d146a383eea906919fa586b02` 已推送并创建 Draft PR #28，base 为准确 W3 合并 head `519228354279fc1641bef2fe19a08991b9ed4731`；PR 创建后查询为 open、draft、mergeable，初始 `test (3.12)` 正在运行。状态文档提交会产生新 head，合并只认该 latest head 对应的 CI。

2026-08-30 随后完成 UI1：PR #28 的 latest-head GitHub Actions run `33292506967` 成功后转 Ready 并 squash merge，功能基线准确前进到 `c9e4b74a133b9543040c3e02cb13356c80f1cbef`。OPS1 从该 merge head 创建独立分支 `codex/x2red-ops1-observability-ci-security`；提交、PR、CI 和 merge 状态仍须在推送前重新查询。

### 2026-08-30 OPS1 可观测性、可靠性、CI 与安全

- 文本和图片调用统一输出 provider/model、tokens 或 image count、latency、attempts、retries、request ID 与 USD cost。Provider 实报、Provider 估算、本地费率估算、部分/混合和 unavailable 分开显示；删除写作项目按尝试次数固定计 1 cent 的旧逻辑。结构化输出解析失败仍保留已发生 usage，确定性 fallback 不伪记模型调用或记忆应用。
- 同步文本、异步文本和图片请求统一 timeout/transport/HTTP 错误码；408/409/425/429/5xx 使用有界指数退避、jitter 和 `Retry-After`。同 payload 重试复用 idempotency key，兼容性 payload fallback 使用新 scope；provider detail、job error 和发布拒绝审计统一脱敏。
- FastAPI 启动移除 `create_all`，Alembic 成为唯一 schema authority。lifespan 和 `/ready` 都比较 revision；`--skip-migrate` 不能绕过门禁。Revision `0013` 新增 writing USD cost、job lease/heartbeat/worker/error/dead-letter、active dedupe 条件唯一索引和 append-only 发布审计。
- Job claim 改为原子条件更新；worker heartbeat 续 lease，仅过期 lease 可恢复；失败有界退避并最终进入 dead letter，人工 retry 显式重置。并发 worker 不会同时 claim 同一 pending job，但崩溃恢复仍是诚实的 at-least-once，不冒充分布式 exactly-once。
- CLI 默认 loopback，非 loopback 无 token 时拒绝启动；受保护 API 支持本地 token、Origin/CSRF、cross-site 拒绝和安全 header。持久化文件必须位于批准 root，图片上传/下载受类型、像素、host、HTTPS、重定向和大小约束。Web UI 与公众号发布助手均只在会话级保存 token；X2RED 仍不点击最终发布按钮。
- PR CI 显式清空所有付费模型配置，加入 70% coverage、Mypy、Bandit、pip/npm audit、ESLint/JSDoc、空库/旧快照迁移、离线 Prompt eval、Playwright E2E 与 visual contact sheet。独立 nightly canary 只有专用 secret 存在才调用模型，要求显式费率，并把全部最大重试尝试计入预检；默认 cap US$0.05、硬上限 US$0.10，artifact 不保存原始响应。
- 完整操作、迁移、回滚、配置和已知限制记录在 `docs/ai-context/OPS1_OBSERVABILITY_CI_SECURITY.md`。离线 Prompt eval 和自动测试不替代 W3 标题 ≥65% / 风格 ≥70% 的真实成对人工盲评。
- 2026-08-30 13:37 提交前重新 fetch：远端功能分支仍为准确基线 `c9e4b74a133b9543040c3e02cb13356c80f1cbef`；PR #19 为 open、draft、CLEAN、MERGEABLE，同 head 的 CI run `33292708661` 成功。13:45 当前精确本地 head 的最终套件 `220 passed, 55 warnings`，branch-aware coverage `72.05%`；三个 OPS1 测试文件 `23 passed`。Mypy、Bandit、Ruff、ESLint/JSDoc、Python/JavaScript/Shell/JSON、pip/npm audit、离线 Prompt eval、空库 CLI、`0013→0012→0013` 往返迁移和离线 wheel 均通过。桌面受管沙箱拒绝临时 loopback 端口，当前 OPS1 head 的 Playwright/contact sheet 由 GitHub latest-head CI 作为合并硬门禁；此前 UI1 基线 E2E 已通过，不能替代本次 CI 结果。
- 2026-08-30 13:51：OPS1 实现提交 `0629c5f87a73ef6c5e70087d2d24aeda8af7976d` 已推送，独立 Draft PR #29 指向功能基线。创建后查询为 open、draft、MERGEABLE；初始 CI run `33295579345` 正在执行。此状态文档更新会形成新 latest head，合并只认新 head 的完整 CI，不沿用初始 run。
- 2026-08-30 13:59：OPS1 PR #29 的 latest head `b3ed174a97ac292fc7db90e5d087d0b055ca9b81` 在 GitHub CI run `33295636707` 全部成功，包括迁移、Mypy、pip/npm audit、Bandit、ESLint/JSDoc、Prompt eval、220 项覆盖率门禁、Playwright、contact sheet artifact 和 Ruff。PR 转 Ready 后已 squash merge，merge commit 为 `4f6ac5c21144bbed4905f4ebbcfdbfb9a38707d3`。PR #19 当前为 open、draft、MERGEABLE；本状态提交会产生新 latest head，只有其完整 CI 可授权合入 `main`。

### 2026-08-30 UI1 统一创作任务与视觉工作流

- 全局导航收拢为 `收集 / 创作 / 视觉 / 发布 / 资产与偏好 / 设置` 六组，但信号台、原料库、语料池、小红书、公众号、发布、池子记忆、写作偏好和设置等旧入口全部保留。视图切换发出单一 `x2red:view-changed` 事件，返回时恢复原导航焦点。
- 新增可自动保存的六步创作任务：选择材料、文章类型、平台、读者与承诺、写作模式、视觉路线。向导只保存选择与意图，通过稳定 handoff 事件把数据填入现有小红书、公众号长文、公众号轻内容或深度写作控件；生成、保存和不可变版本合同仍由原工作台负责。
- 前端按职责拆成 `api-client`、`creative-store`、`writing-view`、`visual-view`、`candidate-view`、`prompt-view`、`publish-view` 和轻量入口；最大控制器 448 行，低于任务书 1000 行上限。旧 DOM ID 保持一个版本兼容，没有新建第二套生成链路。
- 视觉工作流统一展示系列总览、页/槽位导航、Prompt provenance、完整 Prompt、diff、重复警告、Contact Sheet、批量上传、质量分和候选状态；选择、保留、驳回与修复继续调用现有 V3 候选生命周期，不删除竞争候选或绕过本地排版与人工发布门禁。
- UI 只在现有暖白/炭黑/赤陶 token 上增加渐进模块，没有 CSS 全量重写、渐变或结构 emoji。设计覆盖见 `design-system/x2red/pages/unified-creative-workflow.md`。
- 新增独立 Playwright E2E：自建临时数据库和服务，迁移 `0001→0012`，验证六组导航与所有旧入口、六步向导交接、焦点恢复、方向键、视觉候选/Prompt/批量上传合同、860/1360/1800 响应式、减少动态效果，以及 console/page error 为零。最终布局与 44px 交互目标修复后，E2E、UI1 定向 `5 passed` 和完整 API 套件 `196 passed, 8 warnings` 均通过。Ruff、Python/JavaScript/Shell 编译、发布助手、全新迁移和离线 wheel 构建通过；验证只使用临时数据库和合成图片，没有调用真实模型或修改用户数据库。

### 2026-08-29 W3 标题、授权短范例与真实反馈

- 大纲后由严格 Schema 的 `title_strategist` 生成 12—20 个候选，覆盖结果、冲突、反常识、场景、问题、数字与判断；候选必须使用当前 W1 evidence refs。确定性 tournament 过滤空泛承诺、未知或不相干证据、无支持数字、过度悬念、套路词、无支持绝对承诺和近似同质标题。
- 本地读者第一眼模拟只做主题、价值、具体性、长度与自然度排序，不冒充真实读者。返回机制多样的 top 5；作者只能选择最新 tournament，选择冻结为 `title_preference`。writer/final 的 W2 合同要求逐字保留所选标题；未选择时使用显式 top-1 fallback，无合格 top 5 时不会伪称门禁通过。
- 风格训练现在要求显式确认原创或授权。作者真实反馈确定性保存为 `author_overrides`，优先于已批准反馈和模型推断。项目创建时从冻结 memory snapshot 建立 `style_exemplar_bundle`；最多四个短范例必须正式批准、created_by human、来源授权或明确确认权利、标注修辞职责并通过 URL/账号/日期/金额/数字结果等历史事实风险检查。
- 普通池子记忆 Prompt 不再注入原句；专用短范例只进入 title/writer/final 角色，事实研究、事实审稿和 claim extractor 继续只接收当前 evidence。原始风格样本与历史文章不整包注入。
- `EditorialService.revise()` 为人工 revision 保存直接父版本；反馈接口只接受当前项目的模型/多 Agent 原稿与其 direct human revision。模型全文、用户全文、版本、角色、hash、服务端 unified diff、原因、文章类型和受影响维度均被冻结；是否进入记忆由 append-only candidate/approval 状态动态反映。
- `X2RED_WRITING_QUALITY_MODE=production|legacy` 默认 production；legacy 跳过 W3 标题/范例层但保留全部历史 artifact、revision、feedback 和 memory。无数据库迁移，详细合同见 `TITLE_STYLE_FEEDBACK_W3.md`。
- 新增专项覆盖全部标题过滤类别、确定性 top 5、多样性补位、降级竞赛拒绝选择、过期选择、逐字标题合同、授权与人工批准、四例上限、修辞职责、事实风险、服务端 diff、版本血缘和记忆状态。完整 API 套件为 `191 passed, 8 warnings`；Ruff、Python/JavaScript/Shell 编译、发布助手回归、全新 SQLite `0001→0012` 迁移和 wheel 构建通过。latest head `1cee81507088f09eed6d2f17bf1efbd8c0810780` 的 CI 成功后已通过 PR #27 合并为 `519228354279fc1641bef2fe19a08991b9ed4731`。尚未调用真实模型或写用户数据库。任务书标题 ≥65% / 风格 ≥70% 只能由真实成对人工盲评确认，当前自动测试不作达标声明。

### 2026-08-29 W2 结构化写作 Agent 与 Claim-Evidence Matrix

- 新增全角色严格 Pydantic Schema，覆盖任务单、证据包、大纲、初稿、三路审稿、主编裁决、终稿和 final claims。业务字段禁止额外键；artifact 保存 mode、valid/repaired/degraded、Schema、修复记录和 payload hash，API 暴露可重放 trace。
- production runner 在 JSON/Schema/跨产物合同失败时只允许一次结构修复；第二次仍失败则 AgentRun 明确 failed，不保存普通成功 artifact。provider/网络失败不伪装成 Schema 问题。legacy 和无模型 fallback 始终 degraded；只有配置模型通过 Schema 且实际获得 memory IDs 后才登记记忆应用。
- reviewer 必须给出稳定前缀 issue ID、位置、严重度、证据和 minimal fix；事实 issue 必须有来源 evidence。Chief 只能逐一裁决既有 issue；Final 只能执行全部批准 issue，不能引用未批准项。
- 终稿后由事实隔离的 claim extractor 重提 critical/major 主张，冻结 exact quote、位置、W1 evidence refs、origin claim 和 approved issue。它不能发明初稿 claim 或批准 issue；数字、因果、比较和能力主张不能降为 minor。
- 本地 `ClaimChecker` 对照当前 W1 evidence chunks、初稿 claims 与批准 issue，验证引用、证据原文、statement 语义支持、主张范围和终稿原句；引用真实但无关的原文不能通过。Agent 自造 evidence ref、重复 claim/issue 也会被 Schema 拒绝。critical/major 无支持、未经批准的主要扩张或原句不存在均阻断完成。
- 阻断状态为 `claims_blocked / claim_evidence_gate`；保留候选终稿、final claims、matrix 和 AgentRun，但不创建 output DraftRevision、不显示公众号交接。UI 明示 Schema 通过/修复/降级和证据闸门结果。
- `X2RED_WRITING_SCHEMA_MODE=production|legacy` 默认 production；legacy 恢复旧完成路径但明确 degraded，不删除或重写历史。无数据库迁移。详细合同见 `docs/ai-context/STRUCTURED_WRITING_CLAIM_MATRIX_W2.md`。
- W2 专门回归覆盖 Schema 重放、一次修复、issue 权限、冻结 evidence ref、引文与主张语义一致性、critical/major 支持、范围扩张、完成阻断和 UI 状态。定向回归为 `24 passed, 1 warning`，完整套件为 `184 passed, 8 warnings`；latest head `4027d0c2` 的 CI run `33249003306` 成功后已合并为 `f6dd3bbb`。静态门禁、全新 SQLite `0001→0012` 迁移和 wheel 构建通过；验证未调用真实模型、未写用户数据库。

### 2026-08-29 W1 证据编译与混合检索

- 新增严格 `EvidenceDocument`、`EvidenceChunk`、`EvidenceSectionRequest`、`EvidenceScore`、`SectionEvidence` 与 `EvidenceBundle`。每个 chunk 冻结来源、材料引用、标题、作者、发布时间、抓取时间、权利、编辑备注、原文字符位置、内容 hash 和 `source_id:chunk_id`；持久化 trace 同时记录 compiler 版本、总 chunk/source 数、rank 与九项 score breakdown。
- `EvidenceCompiler` 按 Markdown 标题、段落和中英文句子边界分块；只对无自然边界的超长单元执行受控强制拆分。`structured_content_json` 仅取标题等元数据，不再作为序列化正文被截断。
- 本地 `BM25Index` 对全量 chunk 召回；可选 OpenAI-compatible embedding 只重排 BM25 候选和各来源最佳候选，并在同一编译中缓存 chunk vector。未配置或 provider 失败时明确使用 BM25，不调用外部服务或伪称 embedding 生效。
- 重排覆盖 semantic relevance、source authority、primary bonus、freshness、editor note、section role、rights、source diversity 和 redundancy penalty；MMR 拦截完全相同或高度相似文本占满预算。
- 深度写作根据任务阶段或已批准大纲逐节检索，并把 bundle 写入 immutable artifact 与终稿 provenance；公众号长文优先按已有 H2 检索，否则使用开头、机制、证据、比较和限制五类问题，bundle 冻结到版本 metadata。小红书编辑链、输入材料、语料池摘要和池子记忆主题匹配同步接入。
- 所有受影响 Prompt 的限长 JSON 改由 `bounded_json()` 生成仍可解析、带显式压缩标记的 JSON；直接截断已序列化 JSON 的扫描为零。语料池不再把预算除以来源数后从每份正文开头切片，而是保留全来源索引并追加语义摘要与 evidence refs。
- `X2RED_EVIDENCE_RETRIEVAL_MODE=hybrid|legacy` 默认 hybrid。legacy 冻结 `DEGRADED_LEGACY_CHARACTER_SLICE`，不删除来源、artifact 或历史版本。W1 无数据库迁移。详细合同见 `docs/ai-context/EVIDENCE_COMPILER_HYBRID_RETRIEVAL_W1.md`。
- 新增 W1 定向 `13 passed`；写作/公众号/语料池/池子记忆联合回归 `38 passed, 1 warning`；最终完整 API 套件 `172 passed, 8 warnings`。全 API Ruff、compileall、导出脚本、shell、18 个活动 JavaScript、发布助手、全仓 JSON、敏感信息、diff、全新 0001→0012 迁移和 wheel 内容门禁均通过。测试未配置 embedding，未调用真实文本、图片或向量模型，也未写用户数据库。

### 2026-08-29 V4 本地中文排版 Recipe v2

- 新增严格 `TypographyRecipe` / `TextRegion` / render diagnostic schema。recipe 冻结模式、归一化区域、字体职责、字重、字号比、行高、字距、旋转、对齐、透明度、blend 和碰撞策略；额外字段被拒绝，区域越界或 ID 重复明确失败。
- 本地 engine 实现 `type_led_large`、`edge_pressed_phrase`、`diagonal_fragments`、`ghost_text`、`archive_microtype`、`type_in_color_block`、`margin_scatter` 和 `safe_zone_caption` 八种模式。选择优先明确冻结模式，再结合页面职责/layout 和确定性轮换；安全区模式只在其他模式及四种镜像避让都失败后降级。
- source fingerprint 绑定比例、phrase/note、页码、layout、visual role、请求模式和关键主体矩形。相同输入复用已冻结 recipe；输入改变会重新选择。composition fingerprint 同时包含 recipe，旧版本不会被静默覆盖。
- 渲染按区域自身尺寸计算内边距，从目标字号向下拟合准确中文、说明、label 和页码；不以截断掩盖溢出。任一区域无法容纳、像素触边或可读文字覆盖主体时明确失败，并保存逐区域框、字号、换行、旋转、透明度、碰撞和裁切诊断。
- Minimal Zine compositor 升至 `minimal-zine-local-type-v7-typography-recipes`，仍完整 contain raw plate、只清理高风险外沿、不伪造强调色，并把 `typography_recipe_v2` 与诊断保存到 immutable page spec。ZIP allowlist 继续排除 raw anchor、候选和 Contact Sheet。
- 公众号 21:9 / 1:1 封面先生成无字视觉底图，再由同一 engine 本地叠加中文；Playwright 和 Pillow fallback 因此共用排版合同。轻内容页检查器显示中文模式名、比例、区域数、无溢出/主体状态、字体参数、避让变换、选择原因和降级提示。
- `X2RED_TYPOGRAPHY_RECIPE_MODE=production|legacy` 默认 production；legacy 恢复 V4 前单一安全区和羽化纸色 veil，不删除或改写历史工件。详细合同见 `docs/ai-context/LOCAL_CHINESE_TYPOGRAPHY_RECIPE_V4.md`。
- 自动化覆盖 3:5、3:4、21:9、1:1、八模式原生 1200×2000、主体镜像避让、冻结指纹、四模式缩略图差异、公众号四类封面双比例、`safe_zone_caption` 最后兜底顺序和 legacy 回滚；V4 定向 `30 passed`，完整 API 套件 `159 passed, 8 warnings`。人工 8 模式联系表已复核中文清晰和空间骨架差异。隔离浏览器在 1280×800 与手机断点请求 375×812（内置浏览器实际最小 450×812）验证诊断卡片、双栏到单栏响应、参数折行和局部阶段滚动；根页面无横向溢出、console 0 error/warning，未调用模型或写用户数据库。最终 Ruff、compileall、Python/shell/活动 JavaScript、发布助手、JSON、diff、全新 0001→0012 迁移和 wheel 内容门禁均通过。

### 2026-08-09 V3 图片多候选、Contact Sheet 与视觉审稿

- 新增统一 `ImageCandidateLifecycle`：API 生图和 ChatGPT Images 网页回传都按页保存 Prompt run、候选序号、provider/model、图片 hash、尺寸、成本、延迟、状态、审稿和 append-only audit event。手工 1—4 张与 API 默认 3 张只在调用来源上不同，不再维护两套状态模型。
- `ModelClient` 显式检测 candidate count、image reference、image edit、multi-turn 和 usage 能力；即使静态能力判断支持 `n`，运行时多图请求失败也会记录失败尝试并顺序回退为单张调用。候选成本、延迟、调用次数和 provider usage 保持可追溯。
- 每页生成只含原始缩略图与编号的 Contact Sheet，不叠加长文字。候选原图、Contact Sheet、raw anchor 和 final poster 分开记录；选择、驳回或修复不删除其他候选。
- 视觉预检结构化保存 semantic match、subject clarity、composition、thumbnail hook、series consistency、texture、color anchor、artifacts、text safety 和 cliché score。当前 deterministic critic 不伪称具备完整事实/语义视觉理解；最终人工视觉、版权、水印、异常文字和事实复核不变。
- 每页自动定向修复硬上限为 1，provider 支持时优先 image edit；修复完整重复 Visual Bible、PageVisualBrief、Prompt invariants 和参考图要求，只处理一个主要缺陷。仍不合格即停止自动重试并交给人工。
- 未通过审稿或未经人工明确批准的候选不得自动选中或进入发布包。全部页存在有效的选中候选后才可重建 ZIP；ZIP allowlist 排除候选、Contact Sheet 和 raw anchor。
- 轻内容 UI 已显示 Contact Sheet、候选图、十项评分、总分、provider/model、尺寸、成本/延迟/调用次数，以及选择、保留、人工批准、带理由驳回、单次修复、三候选再生、仅重排版和替换概念。真实浏览器在 1280×800 / 375×812 验证候选切换和驳回闭环，无横向溢出，console 0 error；使用隔离临时数据库与合成候选，未调用真实模型或写用户数据库。
- Feature flag `X2RED_IMAGE_CANDIDATE_MODE=production|legacy` 默认 production；`X2RED_IMAGE_CANDIDATE_COUNT=1..4` 默认 3。回滚不删除现有候选记录或文件。详细合同见 `docs/ai-context/IMAGE_CANDIDATE_VISUAL_REVIEW_V3.md`。
- 自动化最终为图片候选定向 `9 passed`、候选与 Minimal Zine 联合 `21 passed, 1 warning`、完整 API 套件 `128 passed, 8 warnings`；Ruff、compileall、全部 JavaScript、wheel 内容、JSON、敏感信息和 diff 门禁通过。

### 2026-08-09 V2 Visual Bible 与逐页视觉简报

- 新增严格 `VisualBible` / `PageVisualBrief` / 每页三候选 / 冻结 bundle schema。生产路径先生成不含页面物件的文章级 Bible，再为每页生成恰好 3 个具体、可画、有 evidence ref 的概念；模型或 schema 失败时显式记录 `DEGRADED_VISUAL_BRIEF`，不伪称模型已生效。
- `VisualDistinctnessService` 在整组 3^N 候选上先选“通过阻断门禁”的组合，再比较质量分；拦截重复/仅换页码的主体、全组同 anchor、少于规定 layout、视觉陈词、复合抽象和缺证据页。4 页默认至少 3 种 layout，每页具体主体不重复。
- 轻内容生成管线升至 `light-lab-v14`，新版 `PlatformVariant` 冻结 `visual_brief_mode` / `visual_bible` / `visual_brief` / `visual_distinctness`；不再将 `series_motif` 复制到全页。旧版本无 V2 mode 时保持 legacy 读取，无迁移、无历史回填。
- 正文编辑继续字节级保留已有 storyboard。分镜编辑必须提交冻结 brief，后端保留原 evidence refs 和 Bible 不变量，重跑 distinctness 后生成新 fingerprint；任何 brief 语义变化会清除旧 Prompt/recipe/raw trace 和合成指纹。
- V1 Prompt compiler 在 PageVisualBrief 存在时只能使用该冻结简报的主体、动作、场景、职责、layout、palette 和情绪；`phrase` / `note` 仅供本地中文排版和缓存，不再推导第二套画面。
- 轻内容 UI 显示冻结 PageVisualBrief、三候选数、页面职责、具体主体、动作/场景/视点/裁切/光线、evidence refs 与 Visual Bible 不变量；历史版本仍显示旧“视觉隐喻”编辑器。
- Feature flag `X2RED_VISUAL_BRIEF_MODE=production|legacy` 默认 production。详细合同、升级和回滚见 `docs/ai-context/VISUAL_BIBLE_PAGE_BRIEF_V2.md`。C0 的 5 组 20 个视觉页已全部通过 V2 确定性主编验收；完整 API 套件 `118 passed, 8 warnings`，V2 定向 `9 passed`，V1/V2 联合 `18 passed`，轻内容端到端 `3 passed`。临时数据库的 1280×800 / 375×812 真实浏览器验收无横向溢出、console 0 error，四页主体/layout/职责差异在 UI 实际可见；未调用模型或写用户主数据库。

### 2026-08-09 V1 Minimal Zine Prompt compiler 对齐

- 固定并 vendor 上游 `gc-minimal-zine-poster` v0.3.0 commit `342b5c11d6fa9be261841ec722c12a683a9fa5e9`，完整保留 `SKILL.md`、`references/`、`evals/` 和 eval examples；v0.1 目录保持不变。运行时管理器可离线安装 v0.3，并校验 manifest、必需文件、commit 和 vendor 内容。
- 新增 `VisualPromptContext`、`VisualPromptRecipe`、`VisualPromptSpec` 与统一 `VisualPromptCompiler`。网页 handoff 和 API render 使用同一入口、同一结构化 recipe；网页可调用文本 compiler，但永不调用图片 API。
- 编译上下文覆盖 article thesis、section title、page visual role、phrase、note、evidence、audience、emotion、current concept、Visual Bible 和前后页概念。source fingerprint 同时冻结 Skill SHA、compiler version 与 feature mode；这些字段任一变化都会使旧 Prompt/raw anchor 失效。
- 上游 recipe 直接持久化；本地 compositor 只把新 schema 映射为旧六轴执行字段，不再在成功路径调用 `_recipe_for()` 覆盖。只有模型/Skill/JSON 校验失败时才使用页面控制 fallback，并显式写入 `DEGRADED_FALLBACK`。
- `_four_paragraph_prompt(VisualPromptSpec)` 在 production 只追加无模型文字/本地中文 invariant，不重新决定视觉主题、layout、anchor、texture、hue 或 mood。旧 C0 字节级 replay 接口保留，避免修改基线 fixture。
- Feature flag `X2RED_MINIMAL_ZINE_PROMPT_MODE=production|skill_v03|legacy` 默认 production；历史 raw anchor 若没有新结构化 trace，会自动按 legacy 读取，避免升级误作废已审阅成品。
- 轻内容 UI 显示 compiler mode、Skill version、recipe、warnings、source/Prompt fingerprint、重新编译和 Prompt diff；降级状态有文本警告和 `role=alert`，按钮保持至少 44px，窄屏溯源表改单列。
- 无数据库迁移；raw/final 分离、CJK 排版、原子 staging、预览/manifest/ZIP allowlist 和人工事实/版权/水印复核合同不变。详细升级与回滚见 `docs/ai-context/VISUAL_PROMPT_COMPILER_V1.md`。
- V1 完整测试为 `109 passed, 8 warnings`；编译器/native/UI 定向回归为 `48 passed, 2 warnings`。新增模块 Ruff 通过，完整 compileall、静态 JavaScript、context JSON 和 diff check 继续作为提交门禁。

### 2026-08-09 C0 创作质量基线

- 用户提供的执行任务书被拆为 `C0 -> V1 -> V2 -> V3 -> V4 -> W1 -> W2 -> W3 -> UI1 -> OPS1`。根据“独立分支、独立 PR、可回滚”和停止条件，本轮只实施 C0，不提前改 Prompt compiler、写作检索或 UI。
- 修改前完整套件在 Python 3.13.5 上为 `94 passed, 8 warnings`。C0 不改变 API、数据库、迁移、前端、模型或发布行为。
- `apps/api/tests/evals/writing_cases.json` 冻结 12 个合成、无用户隐私的写作案例：技术解释 4、新闻解释 2、观点评论 2、轻内容 2、公众号长文 2。每个案例保存输入证据、约束、旧版输出、claims、pipeline trace、已知问题和 SHA-256。
- `apps/api/tests/evals/visual_cases.json` 冻结 20 个 Minimal Zine 页面，保存文章摘要、页面职责、phrase、note、证据摘要、storyboard、完整旧 Prompt、Skill pin、compiler 路径和指纹。`visual-firewall-03/04` 有意证明现状缺陷：文字、证据和页面职责不同，但旧 Prompt 与 model fingerprint 相同。
- 写作 rubric 固定 evidence、clarity、specificity、structure、hook、title、style、AI clichés、usefulness；视觉 rubric 固定 semantic match、imageability、composition、thumbnail、distinctness、series consistency、texture、color anchor、typography、artifacts。每项有 1/3/5 分锚点和阻断项。
- `scripts/export-creative-baseline.py` 以 SQLite 只读模式导出 DraftRevision、PlatformVariant、WritingArtifact 和视觉 Prompt；不加载 `.env`、不调用模型、不修改数据库，并清理密钥、Bearer、Cookie、会话、敏感 URL 参数、结构化内部 ID 和本机绝对路径。真实数据库小样本 smoke 成功，临时私有导出随后删除。
- 完整设计、fixture 清单、旧 web/API Prompt 数据流、重放命令、隐私边界和当前已知问题记录在 `docs/ai-context/CREATIVE_QUALITY_BASELINE.md`。V1 必须从这个基线比较，不能通过改 fixture 掩盖行为差异。
- 修改后完整套件为 `99 passed, 8 warnings`；C0 定向测试 `5 passed`，全仓 CI 范围 Ruff、compileall、导出脚本 py_compile、JSON 校验、敏感信息扫描和 `git diff --check` 通过。C0 没有受影响的 JavaScript 或需要浏览器验证的生产行为。

2026-08-05 至 2026-08-09 严肃精简与证据修复：

- 用户实际的 Kimi/Fable 项目只冻结了 Kimi evidence pack；Fable 卡片是仅适用于公众号文章的表达偏好，因此模型按事实防火墙拒绝比较。根因是产品把“写作偏好”和“事实来源”都叫作记忆，而不是模型不会查看材料。
- 公众号长文和深度写作现在共用统一的混合材料合同：一次最多提交 32 个库内来源、草稿版本、平台版本和直接粘贴形成的来源。深度写作用不可变 `source_selection` artifact 冻结 `material_refs`、材料快照和关联来源；公众号平台版本在 metadata 冻结 `input_material_refs`、材料 provenance、`evidence_source_ids` 和角色。已写版本可以提供结构与表达，但其事实仍必须回溯关联的原始 `SourceItem`。
- 侧栏删除独立“长文写作项目”；公众号成为单一主入口，常规长文直接生成，深度写作作为公众号长文子流程。原有项目和历史数据仍可深链访问，没有删除。
- 公众号长文主流程固定为五个阶段：冻结材料、可选深度研究与审稿、公众号完整成稿、人工编辑与配图、排版/审核/发布包。界面使用紧凑阶段导航和单一详情区，不再把五套长说明同时塞进五张大卡；系统当前阶段与用户正在查看的阶段独立表达。所选详情显示读取、输出、Skill/模型路由和可优化位置，明确动作再定位到材料、现有深度项目、编辑器或发布预览。
- 公众号成品上下文与阶段查看状态已完全拆分：打开 packaged vN 后显示“已选成品”，点击阶段 2 则顶部立即改为“正在查看阶段 2/5”，成品不再冒充当前步骤。首屏新增“开始新文章”：仅退出当前项目/版本，保留所有旧成品、主来源和已选材料，未保存编辑需先确认；随后自动展开材料区并聚焦阶段 2 创建动作。新文章状态切换来源不再自动选中该来源的旧成品。
- 深度写作详情展开为八个可定位阶段：任务定义、证据研究、文章结构、完整初稿、三路审稿、修改裁决、终稿修订、公众号成稿。每个 artifact 在原始 JSON 之外常驻显示“读取什么、产生或修改什么、实际模型与推理强度、建议优化哪里”，原始 JSON 默认折叠。完成后不再出现“小红书制图”动作，而是把准确的来源、冻结材料、`output_draft_id` 和已有 `wechat_variant_id` 交回公众号生产线。
- 深度写作的 writer/final_reviser 已与公众号质量合同对齐：目标 1800—4500 个中文字符、模型输出最低 1200 字符、3—6 个 H2、12000 输出 token、360 秒请求窗口、`finish_reason` 完整度检查和一次整篇重写；终稿少于初稿非空白字符的 70% 时也视为疑似过度压缩并重写。深度终稿绕过面向小红书短稿的 4000 字清洗上限，以最多 50000 字符保存为 `DraftRevision`；公众号阶段再从原始证据和该终稿创建独立 `PlatformVariant`，不会覆盖深度终稿。
- 写作项目 API 会返回最终 `DraftRevision` 的 ID/版本/字符数及关联公众号版本的 ID/版本/状态；公众号版本 metadata 反向记录 `writing_project_id` 和 `writing_final_artifact_id`。因此界面能区分“深度终稿已经完成”和“公众号平台稿已经生成”，并准确恢复既有版本。
- “池子记忆”在产品 UI 改名为“写作偏好”，并明确只决定怎么写，不能提供事实。后端 append-only snapshot/usage 合同不变。
- 公众号长文、公众号轻内容和深度写作各自保存独立来源选择。慢网络切换时先清空旧 draft/variant，并用 request token 丢弃过期响应。
- 轻内容新任务只暴露稳定的本地编辑卡片和显式标为实验的 Minimal Zine；视觉导演不能静默改掉作者选择的 renderer。五个未加载的旧控制器已从磁盘删除。
- Minimal Zine compositor 升至 v6：完整保留 raw plate 的宽高比和主体，用采样纸色的羽化外沿遮罩替代固定 8%/18%/14% 裁切，文字安全区只铺低透明 veil，不再出现硬边米色块。本地排版现在兼容旧中文 layout、动态平衡标题换行并避免单字/弱起始孤行；颜色贫乏时也不再伪造蓝色方块或 registration mark。未预期异常仍会原子回滚并转成可读 `NativeSkillError`。
- 轻内容保存标题、摘要或正文时不得重写已经冻结的逐页 `phrase` / `note`。此前 `_sync_light_storyboard()` 每次保存都会从正文连续切句，直接制造“第 N 页说明 = 第 N+1 页短句”的串页链；现在只保留原分镜并记录 `storyboard_copy_sync`，没有旧分镜的 legacy 版本才使用应急初始化。
- 轻内容文案采用三层质量门禁：生成/总编阶段检查同页及跨页的相同或近似短句，候选选择拒绝不合格结果，storyboard API 再次拒绝串页合同。四页必须分别表达不同论点或生活场景；模型产出的每页 `evidence_basis` 和 `source_refs` 随不可变版本保存并在页检查器中可见。
- 语料池批次生成轻内容时记录全池证据范围，而不是只显示一个模糊来源标题：本次真实批次包含 18 条全池记忆、40280 字全池语料和 6 条冻结详细来源；v13 Prompt 最多提交 18000 字，并要求不同页面使用不同来源线索。池子记忆仍只决定怎么写，不能替代该批次决定能写什么。
- 微信封面不再自动套用廉价网格/轨道“AI 风”；默认使用克制的 editorial split，并补齐无 Playwright 时 Pillow 回退的完整构图。
- 公众号长文的补充事实来源不再使用浏览器原生 `<select multiple>`。现在按平台分组显示复选框，并提供搜索、清空和“已选 N 个”反馈；点击即可多选，不再要求用户按住 Command/Ctrl。左栏重复展示的六张风格说明卡片已移除，正式排版主题仍通过单一主题选择器配置。
- 公众号长文和深度写作的库内材料与直接粘贴是“且”关系，不是二选一。库内复选列表同时包含 `SourceItem`、`DraftRevision` 和 `PlatformVariant`；粘贴内容会先写成标准 `web/manual` 来源，以正文 hash 去重并标记 `needs_review`，然后与所有已选材料同批进入 evidence pack、版本 metadata 和后续审核。
- 公众号模型长文不再以“JSON 可解析”代替“文章完整”。服务捕获 `finish_reason`，为长文设置 12000 输出 token 和 360 秒请求窗口，并检查正文长度、至少三个 H2、代码围栏、围栏外代码、结尾完整性及配图章节引用。第一次不合格会基于全部材料重写整篇；第二次仍不合格则拒绝保存。明确的裸语言标记和代码围栏外溢可以在不改代码内容的前提下本地规范化，规范化后仍须通过全部完成度检查。模型创建的历史残缺版本也会在重新排版前被拦截，人工版本不受该模型门禁误伤。
- 公众号长文启用配图规划后，会为封面和每个正文二级标题生成独立、可复制的精确生图 Prompt。用户可把 Prompt 粘贴到具备图片 Skill 的 Codex，生成后按槽位回传图片；X2RED 校验并规范化图片、登记为待版权复核的 `Asset`，再把它们插入预览、干净 HTML、Markdown、封面和 ZIP，同时输出 `visual-handoff.md`。上传后版本回到 draft，必须重建发布包并人工检查事实、版权、水印和异常文字。
- 公众号材料列表曾因长时间打开的页面继续复用旧控制器、同时加载新 DOM 而为空；随后异步提交路径还可能对已被替换的控件直接读取 `.value`，暴露 `Cannot read properties of null`。根页面现返回 `Cache-Control: no-store`，所有本地 CSS/JS 引用按文件内容附带 hash；公众号长文和深度写作在第一次 `await` 前冻结表单与材料选择，缺失控件时返回可读刷新提示，不再抛裸 `null.value`。
- 2026-08-05 13:02 再次收到公众号工作台裸 `Cannot read properties of null (reading 'value')`。复查发现上一轮只冻结了“直接生成”和“进入深度写作”的创建表单，仍漏掉两类路径：来源 `change` 处理器在等待草稿请求后重新读取 `#wechat-source.value`，保存/提炼编辑稿也直接读取实时 DOM。现在来源 ID 在异步开始前冻结并在返回后校验，编辑器字段同样先形成快照；所有关键控件通过 `requiredWechatControl` 校验仍连接在页面上，刷新请求也捕获并显示可读错误，不再把原生空引用暴露给用户。
- 2026-08-05 13:16 深度写作仍弹出同一裸错误的独立根因已确认：`style-v07.js` 还注册着一套捕获阶段的旧提交监听器，用 `stopImmediatePropagation()` 抢占当前多材料提交链，并读取已从 DOM 删除的 `#writing-source.value`。旧监听器已经移除；深度写作项目只由 `studio-v07.js` 提交，个人风格 ID 也合并进同一份冻结表单快照和 `style_profile_id` 请求字段，避免两套控制器再次漂移。
- 2026-08-06 全站网页 UI 已增加最终兼容层 `product-ui-v17.css/js` 和持久化设计规范 `design-system/x2red/MASTER.md`。视觉统一为 Claude 风格取向的暖白纸张、炭黑正文和赤陶主动作色，移除可见蓝紫色与装饰性渐变；所有导航和结构图标统一为同笔画 SVG，控件、圆角、边框、阴影、间距、焦点、状态和空页面使用同一套语义 token。v17 只重排和增强现有 DOM，不改变三层信息架构、后端合同或人工发布边界。
- 桌面侧栏为 256px，861—1360px 自动收为 76px 图标栏，860px 以下切换为带遮罩、焦点回返、Escape 关闭和主内容 `inert` 的抽屉。收起/恢复按钮直接存在于根 HTML，不再依赖运行时注入；来源、监控、采集、语料池、深度写作、公众号材料、写作偏好和风格训练区都可显式折叠。紧凑视口默认收起，选择来源、项目、版本、语料池或记忆卡后自动收起并扩展核心工作台。
- 小红书选中来源后，来源箱自动收为 64px，正文阅读区改为单主列；“我的判断”和“来源素材”进入按需 400px 侧抽屉，支持遮罩、Escape、焦点圈定和焦点回返。≤1600px 的作者标题栏改为两行，动作组保持 46/46/240/约120px 可用宽度。旧 8787 进程中缺少收起按钮的根因是 `product-ui-v17.js` 仅由 Python 启动时动态注入；现在脚本由根 HTML 直接、唯一加载，旧进程正常刷新也会获得交互增强。
- 最终浏览器回归覆盖 9 个主导航页面以及深度写作、公众号轻内容和真实选中来源状态；1440×900、1024×768、375×812、812×375 均无页面级横向溢出或 console error/warning。1024px 语料池保持 64/285/519px 同排等高，手机触控目标至少 44px，减少动态效果时过渡降为 0.01ms；扫描到的可见旧渐变和高饱和蓝紫色为 0。浏览器只读取既有数据和切换界面，没有触发模型、创建任务或写入业务数据。
- 2026-08-06 公众号长文页面重构修复了截图中的重叠根因：聚合 `/static/styles.css` 曾在进程启动时冻结，而缓存版本只散列基础 `styles.css`，导致新 DOM 配上缺失的 `platform-v08.css` 结构规则。服务现在按请求重建模块化聚合 CSS，并用完整聚合内容生成 hash、返回 `no-cache`。长文预生成态全宽展示材料且隐藏空编辑器/预览；生成后才让材料区退为可折叠辅助区。可选粘贴材料和紧凑视口技术细节按需展开，860px 以下阶段栏局部横向滚动；预生成态不会再被响应式逻辑错误地自动折叠。
- 已有深度项目和公众号版本不再回到新建起点：阶段动作打开准确项目，选择已存在 packaged 版本会直接进入对应编辑器、预览和发布状态。`design-system/x2red/pages/wechat-longform.md` 固化了这套页面级渐进披露和阶段感知规则。
- 公众号“长文编辑”和“轻内容图组”现在是互斥模式。轻内容激活时强制隐藏长文五阶段生产线、编辑器和预览，并使用独立的四阶段任务流；模式标签支持方向键、Home/End 和正确的 tab/tabpanel 关系。`design-system/x2red/pages/wechat-light.md` 固化了该边界。
- 全站壳层改为稳定视口：桌面侧栏固定在视口内，导航区自身滚动，主内容使用独立滚动容器；无论页面多长，侧栏底部状态和显式收起/恢复按钮都不会随正文滚走。切换主工作台时主内容回到顶部，轻内容阶段栏和当前页检查器在主内容滚动时保持可用。
- 轻内容新增 ChatGPT Images 网页人工交接，不调用 OpenAI API，也不尝试后台控制用户账号：系统先冻结当前编辑稿/分镜并本地编译逐页 Prompt，用户复制到 ChatGPT 网页生成、保存，再逐页上传回 X2RED。上传图会被校验和规范化为 raw anchor，中文与最终版式仍由本地 compositor 完成；未回传齐全时只生成逐页预览，全部页面齐全后才重建 manifest、HTML 和 ZIP。原图片接口仍是显式备选，GLM 随机性和异常文字/水印风险仍需人工审图。
- 2026-08-06 22:14 修复轻内容网页生图 Prompt 不可见：旧界面把“编译 Prompt”藏在“复制”按钮副作用里，未点击时只显示“尚未编译”，还错误要求“保存分镜并渲染”；分镜修改后旧 Prompt 仍显示可上传，且正在运行的旧 Python 进程会热读新静态 JS、却没有注册新增 `/web-handoff` 路由，点击只得到 `Not Found`。现在流程拆为“生成并显示 → 检查并复制 → 打开 ChatGPT Images → 上传”，完整 Prompt 常驻只读文本框；未生成时复制、外链、上传均禁用，任何分镜修改立即把旧 Prompt 标为过期并锁回后续动作。404 版本错配会明确要求重启 X2RED，本地服务已用当前代码重启并验证 Prompt 接口返回 200；生成过程不调用文本或图片模型。
- 小红书来源箱此前把所有非 X2PDF 来源的尾标签回退为 `X SOURCE`，阅读器又对所有来源硬编码 `𝕏`，产品壳层还追加第二个平台徽标；语料池批次因此被错误标为 X，约 300px 来源栏同时承载十个平台标签、长标题、长摘要和动作，形成重叠。现在平台筛选收拢为一个全宽选择器；来源行只保留一个来源组徽标、截断摘要、独立 44px 归档/恢复动作。语料池批次统一使用“语料池批次/冻结批次”和 `CORPUS BATCH READER`，不显示 X 图标、X 原文链接或 `X SOURCE`。
- 来源归档从全局 `SourceItem.workspace_state` 中拆出为 revision `0012` 的 `SourceWorkbenchState`。小红书来源箱与发布完成动作只写 `workbench=xhs`；素材库标准来源仍保持 active，公众号长文、公众号轻内容和深度写作不会被串联归档。来源行、选中来源粘性工具栏和“本台归档”都支持单条归档/恢复；全局“彻底删除”保持独立危险动作。

本轮本地验证：完整测试 `86 passed, 8 warnings`；compileall、CI Ruff、所有静态 JavaScript 语法检查、发布助手选择器回归、Playwright Chromium 环境检查和 `git diff --check` 通过。新增前端合同覆盖聚合样式真实内容 hash、五阶段渐进披露、现有项目精确打开、预生成态材料区和移动按需展开。真实浏览器在 1280×720、1024×768、768×800 和 375×812 检查预生成、已有 packaged 版本、阶段查看/当前状态分离、材料区响应式、局部阶段滚动、可选内容展开、抽屉 Escape/焦点回返；无页面级横向溢出或 console error/warning。浏览器只读取既有版本并验证界面，没有创建项目、生成文章或调用模型。

2026-08-06 21:14 轻内容、壳层与 ChatGPT 网页交接回归：完整测试 `89 passed, 8 warnings`，新增测试覆盖无模型调用的网页 Prompt 冻结、三页顺序回传、未完成图组不打包、完整图组发布包排除 raw anchors，以及前端模式隔离/侧栏合同。真实浏览器在 1280×720 验证轻内容完全隐藏长文生产线、正文独立滚动、侧栏收起/恢复后滚动位置保持、工作台切换回顶、阶段栏和页检查器 sticky、无横向溢出；只读取既有版本和切换界面，没有生成、上传或写入业务数据。

2026-08-06 21:35 小红书拥挤布局专项回归：完整测试 `90 passed, 8 warnings`；目标 Ruff、compileall、JavaScript 语法和 diff check 通过。真实浏览器在 1280×720 验证主导航 76↔256px 可恢复、选中来源栏 64px、正文阅读区约 1023px、判断/素材抽屉 400px、作者动作组不压缩、页面无横向溢出且 console 无 error/warning。回归只读取既有来源并切换界面，没有生成内容或写入业务数据。

2026-08-06 22:11 小红书来源语义与归档隔离回归：完整测试 `91 passed, 8 warnings`，目标 Ruff、compileall、变更 JavaScript 语法、context JSON 和 diff check 通过。真实浏览器在 1280×720 验证展开来源栏无横向溢出，27 条来源在 330px 高的独立滚动区内滚动且列表横向溢出为 0；语料池列表和阅读器均无 X 标识，来源卡片约 262×176px，独立恢复按钮 58×44px。临时数据库副本中的语料池批次从“待处理”归档后准确进入“本台归档”，公众号来源选择仍保留该来源；`SourceItem.workspace_state` 保持 active，只有 `SourceWorkbenchState(xhs)` 变化，随后已恢复原状态。主数据库已从 revision `0011` 自动升级到 `0012`，升级前后没有创建工作台状态行；8787 服务已重启并只读确认新来源栏、44px 归档按钮和语料池语义。验收没有调用模型、上传或生成内容。

2026-08-06 22:19 轻内容网页 Prompt 可见性回归：完整测试 `91 passed, 8 warnings`，轻内容/Minimal Zine 定向测试 `20 passed, 1 warning`；Ruff、compileall、全部静态 JavaScript 语法和 diff check 通过。真实浏览器在 1280×720 验证未生成态只开放“生成并显示”，接口 200 后完整 Prompt 常驻可见并解锁复制、ChatGPT Images 外链和上传；修改任一分镜字段后旧 Prompt 立即标为过期且三项后续动作全部锁定。测试修改通过刷新丢弃，没有保存分镜、调用模型或上传图片。

2026-08-08 23:18 公众号新文章入口与 Minimal Zine v6 回归：真实浏览器证明 packaged v5 的成品上下文不再锁死阶段标题，查看阶段 2 时顶部准确显示 2/5；“开始新文章”保留历史版本和两份已选材料，退出成品后展开材料区并聚焦创建动作。已用正式外部 anchor 导入路径重建用户的第 1 页海报；该图组只有第 1 页 raw，因此保持 rendered/未完整且不伪造 ZIP。完整测试 `92 passed, 8 warnings`，专项测试 `24 passed, 2 warnings`；CI Ruff、compileall、所有静态 JavaScript、发布助手选择器、shell/py_compile、context JSON 和 diff check 通过。

2026-08-09 00:43 轻内容串页文案与旧海报覆盖专项修复：确认坏图不是浏览器缓存，而是仍在运行的旧 Python 合成器把 v5 裁切结果写入磁盘；服务已经用当前代码重启。保留坏的 v10 不覆盖，创建不可变 v11 `variant_e7e5ff0d1e734c94a8364b3b2bcfc7f9`，四页文案全部互异并带逐页证据说明；已有 raw anchor 的第 1、3 页经 compositor v6 重合成，边缘裁切均为 0、本地伪造强调标记为 false。第 2、4 页没有真实 raw anchor，继续明确显示待回传且不伪造 ZIP。真实浏览器验证分镜、证据面板、1200×2000 成品和 console 0 error；完整测试 `94 passed, 8 warnings`，CI Ruff、compileall、静态 JavaScript、context JSON 和 diff check 通过。

2026-08-05 12:38 缓存/表单一致性回归：真实服务返回带内容 hash 的静态资源 URL 和 `Cache-Control: no-store` 首页；公众号页保留 Kimi 主来源并勾选 Fable 原始来源时显示“已选 1 个”，进入深度写作后两条来源均被勾选并显示“已选 2 个”，console 无错误，未触发真实模型生成。完整测试 `77 passed, 8 warnings`，目标 Ruff、compileall、JavaScript 语法检查和 `git diff --check` 通过。

2026-08-05 13:02 公众号异步控件回归：真实浏览器加载新的 `platform-v08.js` 内容哈希后，在刷新请求进行中连续切换三个来源再切回 Kimi；最终来源与预期一致、状态区无错误、console 无 error/warning，未触发模型或数据写入。完整测试 `77 passed, 8 warnings`，CI Ruff、compileall、active JavaScript 语法检查和 `git diff --check` 通过。

2026-08-05 13:16 深度写作提交回归：真实浏览器加载 `studio-v07.js?v=1c3f073ad1ba` 与 `style-v07.js?v=8a523196c80a`；清空库内材料并补齐必填项后点击“创建写作项目”，只出现正常业务校验 alert，不再出现 `Cannot read properties of null`，且没有创建项目或触发模型。返回公众号再进入深度写作后，Kimi + Fable 恢复为“已选 2 个”。完整测试 `77 passed, 8 warnings`，CI Ruff、compileall、变更 JavaScript 语法检查和 `git diff --check` 通过。

真实库中标题为《当AI不再只生成像素：Kimi K3与Claude如何接管Blender工程文件》的旧 v2 虽冻结了 Kimi 与 Claude 两个来源，却在 2940 字符处精确结束于 `building.name = f`。旧实现没有记录模型停止原因且仅检查正文是否超过 80 字，因此把语义残缺但 JSON 合法的结果打包。新的修复链路保留 v2/v3，并创建完整 draft v4：正文 5189 字符、8 个 H2、49 行 Python 示例通过 `ast.parse`，代码之后仍有 1615 字和 4 个实质章节；完成度检查为 0 个问题。v4 尚未发布，仍需人工事实、引用和版权复核后再构建发布包。

本轮实现提交：`f48fff4`（v15 轻内容、Minimal Zine、本地测试隔离和根级架构文档）。

Linux CI 便携性修复提交：`3063a9e`（非字体主题的 Minimal Zine 生命周期测试不再依赖宿主机预装 CJK 字体）。

2026-08-04 检查时 PR 状态：open、draft、mergeable、clean、尚未合并到 `main`。修复后远端验证 head `bc76e1b9ce550556ad892c81315f9ea0af453e63` 的 push/PR 两套 Python 3.12 和 3.13 共四个 Actions 均通过。该状态和 head 都是易变化事实。

2026-08-04 23:03 的最新本地 CI 等价验证：完整测试 71 passed、8 warnings；compileall、Ruff、所有 active Node 脚本、发布助手选择器、shell/py_compile、`git diff --check` 和全新数据库 0001→0011 迁移均通过。现有本地数据库完成 quick check、0010→0011 增量升级和升级后 quick check。真实服务在 `127.0.0.1:8787` 启动成功，`x2red check --publisher` 通过；真实浏览器在 1600、1440、1024、800 宽度检查池子记忆入口、来源选项、手工规则、检索预览和响应式布局，无 console error 或横向溢出。此前轻内容四阶段、来源切换和写作项目深链基线继续由完整回归套件覆盖。

首次推送后的 GitHub Ubuntu runner 暴露了 3 个测试的宿主字体耦合：产物集合、raw 拒绝和 staging 回滚测试在进入各自断言前，被真实 CJK 字体门禁提前拦截。生产合同没有放宽；`3063a9e` 只为这三个非字体主题测试注入已通过的 font preflight，专门的字体解析测试继续覆盖“有 CJK 字体成功、无 CJK 字体明确失败”。修复后本地完整套件仍为 67 passed、8 warnings，远端 `bc76e1b` 四个矩阵任务均通过。

以上 PR、head、CI 和浏览器结果均带有 2026-08-04 检查日期。新对话必须重新查询 GitHub 和实际代码，不能直接沿用。

## 二、用户的核心产品意图

用户不希望 X2RED 继续表现为堆叠功能的杂乱后台。产品必须形成三个清晰主层：

### 1. 语料素材库

负责发现、标准化、分类、筛选、组合和复用来源：

- X 信号发现；
- 简中平台发现；
- 统一来源箱；
- 按平台分类；
- 多来源语料池；
- 冻结批次与上下文记忆。

### 2. 内容工作台

负责将同一来源或语料池批次转为不同平台成品：

- 小红书工作台；
- 公众号工作台（常规长文、深度写作子流程、独立轻内容图组）；
- 审核、预览、发布包和人工发布。

### 3. 模型与 Skill

负责可替换的模型与视觉/写作能力：

- OpenAI-compatible 文本模型；
- 图片模型；
- 风格配置；
- 人工批准、任务相关的池子记忆；
- Guizang 原生卡片 Skill；
- Minimal Zine 原生视觉 Skill；
- 未来可插拔模型和 Skill。

用户关心的是完整、顺滑、可理解的产品路径，而不是仅修复一个按钮或增加一个接口。

## 三、核心数据链路

```text
X 信号台 ───────────────┐
                         ├→ SourceItem → 平台分类来源库 ─┐
简中原料发现 / 平台采集 ┘                               │
                                                         ├→ CorpusPool
网页、文档和人工导入 ────────────────────────────────────┘
                                                              │
                                                              v
                                              全池压缩记忆 + 轮换选批
                                                              │
                                                              v
                                                    CorpusBatch / anchor
                                                              │
                         ┌────────────────────────────────────┼───────────────────────────┐
                         v                                    v                           v
                  小红书工作台                        公众号长文                  公众号轻内容
                         │                                    │                           │
                         └──────────── 编辑 / 制图 / 审核 / 预览 / 发布包 ───────────────┘
```

所有发现渠道最终都应该进入统一的标准来源，而不是让每个平台维护孤立的数据孤岛。

池子记忆位于模型与 Skill 层，是与 `CorpusBatch` 证据链分离的“怎么写”经验层。生成前按平台、格式、文章类型、风格、受众、配方和视觉路线检索少量已批准记忆；证据包仍独立决定“能写什么”，历史记忆中的人名、数字、日期、结果和因果不得进入新文章事实。

## 四、已完成的主要重构

### A. 简中平台发现改为 MediaCrawler 主链路

当前分支中，原料库的平台发现不再以 SerpApi、DataForSEO、Firecrawl Search、Brave、Jina Search、Tavily 或 GDELT 自动兜底作为主要路径，而是直接运行固定版本的 `NanmiCoder/MediaCrawler`。

关键约束：

- 固定上游提交：`1779dde9725f6b7ef42e29022c0054b3e678f1af`；
- 本地安装在被忽略的 `.vendor/MediaCrawler`；
- 使用上游 `uv.lock` 和 `--no-install-project`；
- 通过本机 Chrome/Chromium CDP 复用用户已存在的登录态；
- 支持小红书、抖音、快手、B站、微博、贴吧和知乎关键词搜索；
- 使用低并发 search 模式；
- 关闭评论抓取和媒体下载；
- 不向前端返回 Cookie、`xsec_token`、`sec_uid` 等敏感运行字段；
- 不绕过登录、验证码、付费墙或平台访问控制；
- 遵守上游非商业学习许可证。

分支名称仍包含 `api-adapters`，这是历史遗留名称，不代表当前产品方向。

### B. 来源按平台分类

来源展示和选择器已经按以下组别组织：

1. 语料池批次；
2. X / 信号台；
3. 小红书；
4. 抖音；
5. 快手；
6. B站；
7. 微博；
8. 贴吧；
9. 知乎；
10. 网页与文档。

来源箱增加平台标签和平台切换；各工作台都必须保留平台分组。小红书和公众号轻内容沿用分组来源选择；公众号长文与深度写作使用可搜索、可清空、带计数的分组复选框，并把原始来源、草稿版本和平台版本分组展示，避免浏览器原生多选必须配合 Command/Ctrl 的隐藏交互；语料池来源选择器可按平台过滤。

当前产品壳直接加载：

- `apps/api/app/static/product-shell-v15.js`
- `apps/api/app/static/product-shell-v15.css`
- `apps/api/app/static/product-ui-v17.js`
- `apps/api/app/static/product-ui-v17.css`

`product-shell-v15` 继续负责三层导航和工作台路由；`product-ui-v17` 是最后加载的视觉与交互兼容层，负责统一设计 token、SVG 图标、响应式侧栏、无障碍增强和辅助区折叠。两层职责不能倒置，也不要把 v17 的最终样式并回旧模块的各自蓝紫色局部规则中。设计决策的可复用来源是 `design-system/x2red/MASTER.md`。

旧的 v10/v12/v14 和 information-architecture 控制器已经从磁盘删除。v15 导航实现仍必须保持幂等，MutationObserver 触发时不能反复重排已经完成的导航结构。

### C. X 信号合并进素材库

信号台继续作为 X 的发现和分析入口。X 候选可以直接“加入语料素材库”，将以下字段合并为标准 `SourceItem`：

- X URL；
- external ID；
- 作者 handle 和名称；
- 正文；
- 指标与发现元数据；
- 默认需要人工复核的权利状态。

这一步不要求先创建写作项目。进入素材库后，它可以加入语料池，也可以送往任意工作台。

相关后端：

- `apps/api/app/api/sources.py`
- `apps/api/app/api/signals.py`

### D. 可复用语料池和冻结批次

新增数据库 revision `0010`：

- `corpus_pools`
- `corpus_pool_sources`
- `corpus_batches`

语料池能力包括：

- 多来源建池；
- HTML、URL 和重复行清洗；
- 标题和正文标准化；
- 每条来源摘要和关键词；
- 全池主题关键词聚合；
- 名称留空时自动命名；
- 全池压缩记忆；
- 来源编辑备注、删除、成员增删时重编；
- 预览下一批而不消耗使用次数；
- 按聚焦相关性、历史使用次数、平台多样性、关键词多样性和确定性扰动轮换批次。

每次正式生成或送往工作台时，批次必须冻结：

- pool ID；
- pool revision；
- batch ID 和 sequence；
- 全池压缩记忆；
- 详细来源 ID；
- 聚焦条件；
- memory mode；
- provenance。

`corpus_batch` 是单向、单层隔离边。旧批次不能通过共享来源把整段旧上下文串入新批次。

相关实现：

- `apps/api/app/api/corpus_pools.py`
- `apps/api/app/services/corpus_pools.py`
- `apps/api/app/domain/models.py`
- `apps/api/app/static/corpus-pools-v13.js`

### E. 语料池直接分发到工作台

语料池界面增加三个出口：

- 送到小红书工作台；
- 送到公众号长文；
- 送到公众号轻内容。

操作时创建冻结 batch anchor，并把该来源选入对应工作台。这样工作台读取的是可追溯批次，而不是重新从整个池临时拼接一份不可复现的上下文。

### F. 公众号轻内容“没有反应”修复

根因：旧控制器在操作开始时设置 `busy=true`，接口成功后立即调用 `loadLab()`，而 `loadLab()` 发现仍处于 busy 状态后直接退出；直到 `finally` 才解除 busy。因此后端已经生成，但右侧图库没有加载。

同时存在语义错误：旧“按当前稿生成图组”只提交已保存版本 ID，不提交当前候选和编辑框内容。

当前修复：

- 使用直接加载的 v15 产品壳和轻内容控制器接管关键按钮；
- 操作成功后强制刷新；
- 根据接口返回版本定位准确版本；
- 生成图组前自动采用当前候选；
- 自动保存标题、subtitle、摘要、正文、标签和主题；
- 用新保存版本生成图组；
- 迭代和批准也先持久化当前编辑稿。

相关文件：

- `apps/api/app/static/light-content-v15.js`
- `apps/api/app/static/light-content-v15.css`
- `apps/api/app/static/product-shell-v15.js`
- `apps/api/app/static/product-shell-v15.css`

旧的 `light-content-fixes-v14.js`、`light-content-lab-v12.js` 和其他旧控制器仍在磁盘，但不再是运行时或 CI 入口。

正确用户流程已经简化为：修改候选或编辑框后，直接点击“按当前编辑稿生成图组”。

### G. Minimal Zine 视觉链路重构

旧问题：

- GLM-image 同时承担视觉、中文和最终排版；
- 中文容易变形、错字或呈现廉价模板感；
- 供应商可能在图片边缘生成“AI生成”等角标；
- 原生 Skill 输出曾写到 `data/assets`，与图片接口允许读取的 exports 根目录不一致；
- 生成后预览和发布包可能没有同步重建。

当前设计：

1. 文本模型读取完整上游 `SKILL.md`，为每页编译视觉配方；
2. 图片模型只生成无字视觉锚点；
3. Prompt 明确禁止中文、英文、数字、Logo、水印、签名、角标、UI 和标签；
4. compositor v6 保留完整稀疏模型 plate 的宽高比、主体和颜色，只用羽化纸色遮罩清理受约束的高风险外沿；
5. 文字安全区使用低透明纸色 veil，不再全局灰阶化、统一 colorize、重复厚框、硬边米色板或任何自动伪造的 registration mark；
6. 在 X2RED 的干净画布上用 cmap 已验证的本地 CJK 字体排中文和页码；缺少可验证字体时明确失败，不静默使用 tofu/错误 fallback；
7. raw `anchor_XX` 和最终 `poster_XX` 是两类独立、各自校验的产物；发布包使用显式 allowlist 排除 anchors；
8. 所有完整产物写入该 variant 的 `data/exports/wechat/{variant_id}/`，并同步重建 Markdown、manifest、preview 和 ZIP；
9. 先在 staging 目录完成完整性校验，再原子 promotion；服务失败时恢复此前目录和数据库引用。

最终目录：

`data/exports/wechat/{variant_id}/`

产物包括：

- `poster-01.png` 等页面图；
- `article.md`；
- `manifest.json`；
- `preview.html`；
- 微信轻内容发布 ZIP。

相关文件：

- `apps/api/app/services/minimal_zine_native.py`
- `apps/api/app/services/light_visual_renderer.py`
- `apps/api/app/static/light-content-v15.js`
- `apps/api/tests/test_minimal_zine_v15.py`

2026-08-02 的真实配置 GLM 探针显示：GLM 能生成目标稀疏旧纸视觉，但即使严格负面 Prompt 仍在右下角生成了“AI生成”角标；该样本经过受约束外沿清理后未进入最终画布。这个样本证明缓解有效，不证明模型永不生成水印或角标。历史质量损伤的主因判断为 compositor 合同、raw 可观测性和错误 CJK fallback，而不是 Prompt 已经失真；GLM 的随机性和水印行为仍是残余模型风险。最终仍需人工视觉、版权和事实复核。

### H. 三层前端导航

侧栏被重新组织为：

#### 01 · 语料素材库

- X 信号发现；
- 简中原料发现；
- 语料素材库。

#### 02 · 内容工作台

- 小红书工作台；
- 长文写作项目；
- 公众号工作台；
- 发布任务。

#### 03 · 模型与 Skill

- 池子记忆；
- 风格配置；
- 模型设置；
- 原生 Skill。

这是当前信息架构的产品基线。后续新增功能应优先并入这三层，而不是继续增加平级主导航。

### I. v15 产品壳和轻内容不可变分镜

v15 产品壳的 canonical 导航层固定为：

- 语料素材库：信号、原料、语料池；
- 内容工作台：工作台、写作、公众号、发布；
- 模型与 Skill：池子记忆、风格、模型和原生 Skill。

公众号轻内容在同一工作台内使用四个阶段：任务设置 → 文案候选 → 视觉分镜 → 成品交付。它会在进入视觉阶段前持久化当前候选和编辑框；视觉分镜只展开选中的一页，其余页面保持紧凑摘要；版式、视觉锚点、质感、强调色、焦点和缩放等枚举/控件显示中文标签。

分镜编辑通过 `POST /api/platforms/wechat/light/variants/{variant_id}/storyboard` 提交完整、唯一且覆盖全部页码的页面合同，并创建不可变的子 `PlatformVariant`；父版本保持不变，子版本带 `parent_variant_id` 和变更追踪。渲染请求只消费已冻结合同，不负责创作文案。

Minimal Zine 渲染接口 `POST /api/native-skills/minimal-zine/variants/{variant_id}/render` 支持 `mode: render_missing | recompose | regenerate`，以及可选的唯一一基页码 `pages`；旧客户端可用 `regenerate: true`，但显式 `mode` 与该 legacy 布尔值同时出现会被拒绝。`recompose` 必须找到存储的 raw anchor，只调用本地 compositor，不调用 Prompt compiler 或图片模型；`regenerate` 才会重新请求图片模型。渲染不会覆盖已有编辑文本。

### J. 2026-08-04 收尾审计修复

- 新增全局测试隔离 fixture：测试不再读取开发者真实 `.env`，并清除 `X2RED_*` 与代理变量；运行时加载 `.env` 的行为不变。
- 轻内容来源切换只选择同一 `source_id` 的已有版本，不再被此前来源的 `currentVariant` 劫持；从其他工作台带来源进入时同样优先匹配该来源。
- 写作项目深链恢复按 `data-project-id` 精确选择目标项目，不再无条件点击列表第一项。
- 自定义 storyboard `mood` 会进入冻结模型输入和 fingerprint，不再被静默降级为 `quiet`。
- README、根 `ARCHITECTURE.md` 和 `docs/WORKFLOW.md` 已统一到三层架构、MediaCrawler、语料池/批次与 Minimal Zine 本地合成合同。

### K. 池子记忆与个人风格闭环（v0.12）

池子记忆不再等同于一个不断膨胀的全局 Prompt。当前实现使用现有 `ReviewArtifact` 保存三类 append-only 记录：

- `memory_candidate`：由文章、平台版本、反馈、模式卡或写作产物提炼的待批准候选；
- `memory_card`：人工确认并批准的正式记忆卡；
- `memory_event`：替代和撤销事件，旧卡保留且不物理覆盖。

候选生成、候选编辑和正式批准相互分离。来源权利未明确时必须额外确认授权；模式卡只能保存抽象模式；手工规则必须确认原创、系统生成且已批准，或已获授权。卡片保存来源引用、版本、学习维度、适用范围、规则/偏好/禁用表达/短例/结构/视觉方向及 provenance，完整原文仍由来源对象持有，不复制进每次模型上下文。

检索使用两阶段策略：先按平台、格式、文章类型、风格配置、受众、配方和视觉路线做硬过滤，再按主题相似度、来源优先级、时间和历史使用次数评分；同一来源去重，默认只取 4—8 条。Prompt 按角色分区，事实/证据角色不接收风格记忆；其他角色只得到与职责相关的维度。每个生成目标冻结不可变 `PoolMemorySnapshot`，只有配置的模型真实消费后才标记 `applied=true` 并追加 `PoolMemoryUsage`。无模型的确定性回退会保留选择 provenance，但不会伪称记忆已经影响输出，也不会增加使用记录。

该链路已经接入快速小红书草稿、多 Agent 写作终稿、公众号长文、公众号轻内容及其迭代、XHS 原生 Skill 文案/视觉提示。AI 变换和轻内容迭代会克隆原版本的冻结选择，不回写旧快照。风格训练快照只保留授权样本包的 hash 和说明，不再把完整历史样本正文注入所有任务。

前端在“03 · 模型与 Skill”下提供独立“池子记忆”工作台，包括内容提炼、手工规则、候选预览/编辑/批准、替代、撤销、任务检索预览、有效记忆和最近使用链路；草稿、多 Agent 终稿、公众号长文和轻内容成品均提供就地入口。1440px 及更窄桌面宽度会把追溯面板换行，避免检索控件在窄右栏内被压缩。

数据库 revision `0011` 新增：

- `pool_memory_snapshots`
- `pool_memory_usages`

revision `0011` 相关实现：

- `apps/api/app/api/pool_memory.py`
- `apps/api/app/services/pool_memory.py`
- `apps/api/app/domain/pool_memory.py`
- `apps/api/app/static/pool-memory-v16.js`
- `apps/api/app/static/pool-memory-v16.css`
- `apps/api/tests/test_pool_memory_v16.py`

数据库 revision `0012` 新增 `source_workbench_states`，以 `(source_id, workbench)` 唯一约束保存内容工作台自己的 active/archived 状态。该表不替代 `SourceItem.workspace_state`：前者是工作台处理队列，后者仍是语料素材库的标准来源生命周期。相关实现位于 `apps/api/app/services/source_workbenches.py`、`apps/api/app/api/sources.py` 和 `migrations/versions/0012_source_workbench_states.py`。

数据库 revision `0013` 新增 `writing_projects.spent_cost_usd`、job lease/heartbeat/worker/error/dead-letter 字段、active dedupe 条件唯一索引与 `publish_audit_events`。标准启动不再隐式 `create_all`；Alembic head 是唯一 schema authority。旧库 active dedupe 冲突只会把额外记录标为 canceled，不物理删除；完整迁移和回滚边界见 `OPS1_OBSERVABILITY_CI_SECURITY.md`。

### L. GitHub Actions 额度优化

由于仓库为 private，标准 GitHub-hosted runner 会消耗账户额度。旧工作流对 `agent/**` 同时监听 `push` 和 `pull_request`，每次 PR 推送再乘 Python 3.12/3.13，实际产生 4 个任务。

当前策略：

- `push` 只监听 `main`，PR 分支只由 `pull_request` 触发；
- PR 以受支持的最低版本 Python 3.12 作为日常门禁；
- `main` 和 `workflow_dispatch` 才运行 Python 3.12/3.13 完整矩阵；
- 同一 PR/分支启用 `cancel-in-progress`，新提交取消旧运行；
- 每个任务设置 35 分钟超时，为完整 coverage 和 Chromium E2E 留出冷启动余量；
- PR 明确清空文本/图片 provider 配置，并加入 Mypy、Bandit、pip/npm audit、ESLint/JSDoc、70% coverage、Prompt eval、迁移快照、Playwright 和 visual artifact；
- 付费模型只允许在独立 nightly canary 使用专用 secret、显式费率和硬成本 cap；
- 不用 `paths-ignore` 跳过必需检查，避免 required check 长期 Pending。

常规 PR 推送因此从 4 个任务降为 1 个；Python 3.13 的兼容性反馈延后到主分支或人工完整检查，这是额度紧张时的明确取舍。

## 五、关键领域对象

### SourceItem

统一来源实体。X、简中平台、网页、文档和批次 anchor 最终都围绕它工作。

重要字段包括 provider、platform、external ID、canonical URL、作者、原文、structured content、metrics、editor note、rights 状态和生命周期状态。

### RawSnapshot

保存原始提供方响应或采集结果，用于可追溯、调试和证据留存。

### Asset / AssetVariant

保存来源媒体以及可用编码或派生版本。来源正文和媒体失败必须解耦，媒体失败不能导致正文丢失。

### CorpusPool / CorpusPoolSource / CorpusBatch

分别代表长期语料池、池成员关系和冻结生成批次。

### ReviewArtifact / PoolMemorySnapshot / PoolMemoryUsage

`ReviewArtifact` 的 memory candidate/card/event 保存人工门禁的 append-only 写作偏好；`PoolMemorySnapshot` 冻结一次生成选择、角色 Prompt 和 hash；`PoolMemoryUsage` 只记录模型真实消费的偏好、角色、阶段、分数和选择原因。写作偏好决定表达方式，不是当前文章的事实来源。任务事实由混合输入中显式选择的原始来源及已写版本所追溯的关联来源决定，并冻结在 evidence pack；已写版本本身只能贡献结构和表达。

### DraftRevision

不可变编辑版本。任何人工修改应该产生新版本，旧版本保留。

### PlatformVariant

同一来源面向不同平台的不可变版本，例如微信长文、微信轻内容和平台专用制图结果。

### ReviewDecision / PublishTask

记录人工审核事件、冻结发布载荷、包哈希和发布状态。

## 六、模型与 Skill 边界

### 文本模型

使用 OpenAI-compatible chat endpoint，用于分析、写作、风格学习、平台适配和 Prompt 编译。无模型配置时，部分基础功能可以使用确定性回退，但高级工作室和原生视觉编译需要模型。

池子记忆只在模型配置且实际调用成功时标记为已应用。检索结果按角色最小化注入，证据角色不读取风格记忆；历史样本和记忆中的具体事实不能越过当前 evidence pack。

### 图片模型

使用 OpenAI-compatible `/images/generations`。Minimal Zine 中只承担 raw 视觉锚点，不承担中文、页码或最终排版；raw 和 final 的 provenance 必须可追踪，重排不能把 final 当作 raw。

### 本地 CJK 排版

Minimal Zine native render 需要通过字体 `cmap` 探针验证中文 glyph；优先使用配置的卡片字体，或 PingFang / Songti / Noto CJK 候选。无法验证覆盖时 native render 明确失败，避免把通用字体的 `.notdef` 假装成可发布中文。

### Guizang

- 上游：Guizang social card skill；
- 许可证：AGPL-3.0；
- 独立固定版本 checkout；
- X2RED 使用上游主题、布局、seed、validator 和运行时；
- 不得把它重新标注为 MIT。

### Minimal Zine

- 上游：生产为 `gc-minimal-zine-poster-v0-3`（v0.3.0 / `342b5c11d6fa9be261841ec722c12a683a9fa5e9`），v0.1 保留为 legacy rollback；
- 许可证：MIT；
- v0.3 的 Skill、references、evals/examples 以未修改固定快照 vendor，并离线安装到独立 runtime 目录；
- web handoff 与 API render 共用结构化 `VisualPromptSpec`；生产采用上游视觉决策 + 仅 text-safe 转换 + X2RED 本地中文合成；
- 编译失败必须标记 `DEGRADED_FALLBACK`，不得声称 faithful Skill 已生效。

## 七、安全、权利和许可原则

- 服务默认绑定 `127.0.0.1`；
- 不在项目文档中存储 Cookie、密钥或个人登录信息；
- 不绕过认证、验证码、付费墙或访问限制；
- 简中平台采集保持低频、人工触发和研究用途；
- 导入公开页面不等于取得转载权；
- 来源和素材默认需要人工复核；
- 发布前必须确认事实、引用范围、图片和媒体版权；
- 小红书和微信均由用户完成最终发布动作；
- Review Agent 只提供报告，不应静默覆盖人工稿件。

## 八、当前文档状态

截至 2026-08-05 00:43，README、根 `ARCHITECTURE.md`、`docs/WORKFLOW.md`、`docs/API.md` 与本上下文包统一到三层架构、写作偏好闭环和 revision `0011`。v10/v12/v14 轻内容、旧导航和 information-architecture 五套退役控制器已经删除；历史设计文档中的旧术语不得覆盖运行时入口和本上下文记录的产品合同。

## 九、未来 Agent 的工作方式

开始任务时：

1. 读取上下文包；
2. 查询当前 PR、head 和 CI；
3. 检查实际文件，确认文档没有过期；
4. 明确任务属于语料素材库、内容工作台还是模型与 Skill；
5. 修改后运行相关测试和完整 CI；
6. 更新上下文包。

禁止仅根据聊天记忆直接修改主分支，禁止在未确认工作区状态时建议强制 reset 或覆盖用户改动。
