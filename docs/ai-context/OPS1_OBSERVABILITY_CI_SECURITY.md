# OPS1：可观测性、可靠性、CI 与安全

更新时间：2026-08-30 +08:00

## 目标与边界

OPS1 只收紧运行可靠性、成本真值、数据库 authority、后台任务、CI 和本地服务安全，不扩展采集平台，不改变证据/记忆防火墙，也不把发布改成无人值守。最终发布按钮、事实核查、版权核查和真实创作质量判断仍由人完成。

## 模型 usage 与成本真值

文本和图片模型调用统一记录：provider、model、input/output tokens、image count、latency、attempts、retries、request ID 和 USD cost。成本状态不得混写：

- `provider_reported`：provider 返回明确实报成本；
- `provider_estimate`：provider 自己只返回 estimated cost；
- `catalog_estimate`：X2RED 按显式配置的文本 token 单价或图片单价估算；
- `partial` / `mixed_estimate`：多次调用只有部分成本或混合口径；
- `unavailable`：既无 provider 成本也无本地费率；
- `not_used`：没有证据表明模型被调用。

写作项目汇总 `AgentRun.usage_json`，并以 `WritingProject.spent_cost_usd` 保存已知实报或估算金额。旧的“每次尝试固定算 1 cent”已删除。结构化输出解析失败时，已经产生的 token 和成本仍随错误保存；确定性 fallback 不产生模型 usage，也不冒充成本已知。UI 明确显示 Provider 实报、Provider 估算、本地费率估算、部分已知、混合口径或不可用。

费率配置：

```env
X2RED_MODEL_INPUT_COST_PER_MILLION_USD=0
X2RED_MODEL_OUTPUT_COST_PER_MILLION_USD=0
X2RED_IMAGE_COST_PER_IMAGE_USD=0
```

费率为 `0` 表示未知，不表示免费。更新 provider/model 后必须同步核对费率，不能沿用另一个模型的价格。

## 请求可靠性

- timeout 和 transport error 使用稳定错误码；HTTP 408、409、425、429 和 5xx 可重试；认证、普通 4xx 和结构错误不盲重试。
- 退避使用可配置指数 backoff、上限、jitter，并尊重受上限约束的 `Retry-After`。
- 同一 HTTP payload 的重试复用同一个 `Idempotency-Key`；兼容性 fallback 改变 payload 时使用新的 idempotency scope，同时保留共同 `X-Request-ID`。
- 同步文本、异步文本和图片调用共享同一分类策略；错误只保存脱敏 detail、状态、provider/model、attempts 和 request ID。
- 图片 URL 只接受 HTTPS、受信 provider host、无凭证、非私网/保留/回环地址，关闭重定向并限制下载为 25 MB 或更低的全局媒体上限。

相关配置：

```env
X2RED_MODEL_MAX_RETRIES=2
X2RED_MODEL_RETRY_BASE_SECONDS=0.5
X2RED_MODEL_RETRY_MAX_SECONDS=8
X2RED_MODEL_RETRY_JITTER_SECONDS=0.25
```

## Schema authority 与 revision 0013

FastAPI 启动不再调用 `Base.metadata.create_all()`。Alembic 是唯一 schema authority：

1. `x2red serve` 默认先执行 `x2red migrate`；
2. application lifespan 在启动 job engine 前比较数据库 revision 与 repository head；
3. `--skip-migrate` 只跳过自动升级，不跳过 revision gate；
4. revision 不一致时启动失败，`/ready` 也返回不可用；
5. 测试需要数据库时显式升级临时数据库，不依赖隐式建表。

Revision `0013` 新增：

- `writing_projects.spent_cost_usd`；
- job lease、heartbeat、last worker、last error code 和 dead-letter 时间；
- active `dedupe_key` 的条件唯一索引；
- append-only `publish_audit_events`。

迁移会保留已有 job；若旧库已有同一 dedupe key 的多个 active job，会保留最早记录并把其余记录标记 canceled，而不是删除。回滚 revision 会删除 OPS1 新字段、索引和发布审计表，因此执行 downgrade 前必须备份；应用层回滚优先使用旧代码加数据库备份恢复，不应在含新审计数据的唯一副本上直接 downgrade。

## 后台任务

每个 worker 使用 hostname、PID 和随机片段组成 worker ID。claim 通过带 `state=pending` 条件的原子更新完成；同一 active dedupe key 在 SQLite/PostgreSQL 由数据库唯一索引兜底。运行中任务定期 heartbeat 并延长 lease；只有 lease 已过期的任务会被恢复。未耗尽 attempts 的过期任务重新排队，已经耗尽 attempts 的崩溃任务直接进入 `dead_letter`，避免进程级失败无限循环；普通失败同样使用带 jitter 的有界退避，人工 retry 会显式重置执行状态。

并发 worker 不会同时 claim 同一 job。崩溃后 lease 恢复属于 at-least-once 交付，handler 仍必须依靠业务幂等键防止“已产生外部副作用但来不及提交完成状态”时的重复副作用；OPS1 不声称分布式 exactly-once。

```env
X2RED_JOB_LEASE_SECONDS=90
X2RED_JOB_HEARTBEAT_SECONDS=20
X2RED_JOB_RETRY_BASE_SECONDS=2
```

## 本地服务安全

- CLI 默认绑定 `127.0.0.1`；非 loopback bind 没有 token 时拒绝启动，除非用户显式打开不安全 override。
- 配置 token 后，`/api` 和 `/ready` 都要求 Bearer 或 `X-X2RED-Token`。Web UI 只把 token 存在当前 tab 的 `sessionStorage`；公众号发布助手只存在扩展的 session storage。
- unsafe 请求拒绝 `Sec-Fetch-Site: cross-site`，并要求同源、显式允许 origin 或扩展 origin；不同端口的 loopback 页面不再自动视为同源。
- 持久化文件下载和发布包读取必须 resolve 到批准的 media/export root；上传限制大小、解码真实图片、限制像素并重新编码，不信任文件名或 MIME 声明。
- provider 错误、job 错误和发布拒绝审计执行 Bearer、文本/JSON assignment、URL credential、嵌套诊断字符串和敏感 query 脱敏。
- 发布 prepare、打开预览、失败/拒绝和人工确认写 append-only audit；审计不保存完整发布 URL、API key 或 Cookie。X2RED 仍不点击最终发布按钮。

```env
X2RED_LOCAL_API_TOKEN=
X2RED_ALLOWED_ORIGINS=
X2RED_ALLOW_INSECURE_NON_LOOPBACK=false
```

不安全 override 只用于用户明确理解网络边界的临时诊断，不能作为公网部署配置。X2RED 不是互联网多租户服务；若需要跨机器访问，应同时使用防火墙、受控反向代理/TLS、强 token 和显式 origin。

## CI 与 nightly canary

PR CI 清空所有文本/图片 provider 配置，不调用付费模型。Python 3.12 门禁包括：

- 空数据库和冻结 prior snapshot 迁移、Alembic metadata check；
- Mypy、Ruff、Bandit high-confidence/high-severity；
- pip-audit 与 npm audit；
- ESLint/JSDoc 和全部活动脚本语法；
- 确定性 Prompt fixture eval；
- 完整测试和不低于 70% 的 branch-aware coverage；
- 隔离 Playwright E2E、截图与 visual contact sheet artifact。

单独的 nightly workflow 只有在专用 secret 存在时才调用一次文本模型。它要求显式输入/输出费率，在调用前按 256 input tokens、最多 32 output tokens 和配置允许的全部最大尝试次数计算 worst-case；默认 cap 为 US$0.05，脚本硬上限为 US$0.10。观测成本缺失或超过 cap 都失败。artifact 只保存响应 hash、长度、usage、cap 和脱敏错误，不保存原始模型正文。

Nightly repository 配置：

- secret：`X2RED_CANARY_API_KEY`；
- variables：`X2RED_CANARY_MODEL_BASE_URL`、`X2RED_CANARY_MODEL_NAME`、`X2RED_CANARY_INPUT_COST_PER_MILLION_USD`、`X2RED_CANARY_OUTPUT_COST_PER_MILLION_USD`、可选 `X2RED_CANARY_COST_CAP_USD`。

## 提交前验证

- 完整 API 套件：`220 passed, 55 warnings`；branch-aware coverage `72.05%`，高于 70% 门禁。
- OPS1、job、迁移、发布与安全定向：`26 passed`；包括双 worker 原子 claim、租约耗尽死信、JSON 密钥脱敏、部分成本聚合、非回环 CLI 拒绝和 `0013→0012→0013` 往返。
- Mypy、Bandit high/high、Ruff、ESLint/JSDoc、Python/JavaScript/Shell/JSON、pip-audit、npm audit、离线 Prompt eval、空库 `x2red check` 和离线 wheel 通过；没有配置或调用付费模型。
- 本机受管沙箱禁止隔离测试服务绑定临时 loopback 端口，因此当前 OPS1 head 的 Playwright/contact sheet 不作本地通过声明。PR CI 必须在隔离 runner 上完成这两项后才允许合并；此前 UI1 基线 E2E 仅作历史回归证据。

## 创作质量与剩余人工验收

OPS1 的 Prompt eval 是离线 fixture/fingerprint 门禁，不代替模型输出质量或人类偏好。任务书要求的标题相对旧基线 ≥65%、风格相对旧基线 ≥70% 仍需真实成对输出、隐藏标签、随机顺序和人工记录；当前单元测试、确定性排序和模型自评都不能被报告为已达到该比例。最终事实、版权、水印、异常文字和发布复核继续保留。

## PR 状态

2026-08-30 13:51，初始实现提交 `0629c5f87a73ef6c5e70087d2d24aeda8af7976d` 已推送并创建 Draft PR #29，base 为 UI1 合并后的功能分支。创建后 PR 为 MERGEABLE，初始 CI run `33295579345` 正在执行；本状态提交将产生新 latest head，因此只有新 head 的完整 CI 可作为转 Ready 和合并依据。
