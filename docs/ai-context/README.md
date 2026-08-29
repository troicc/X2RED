# X2RED 多对话上下文包

这套文件用于在不同 ChatGPT 对话、编码 Agent、IDE Agent 和人工协作之间恢复 X2RED 的完整上下文。它不是聊天摘要，而是仓库内长期维护的项目记忆。

## 快速读取顺序

### 需要在 2 分钟内理解项目

1. 根目录 `AGENTS.md`
2. 本目录 `context.json`
3. `PROJECT_MEMORY.md` 的“当前快照”“产品主架构”“已完成工作”
4. `OPEN_ITEMS.md`

### 准备修改代码

继续读取：

- `WORKFLOWS.md`：端到端业务流程和数据流。
- `DEVELOPMENT_PLAYBOOK.md`：分支、本地更新、启动、迁移、测试和 CI。
- 实际代码和当前 GitHub PR；文档不能代替实时验证。

## 文件说明

- `PROJECT_MEMORY.md`：产品意图、当前进展、关键实现、历史决策和长期约束。
- `WORKFLOWS.md`：发现、来源、语料池、工作台、池子记忆、制图、审核和发布的完整流程。
- `DEVELOPMENT_PLAYBOOK.md`：开发和运维操作手册。
- `OPEN_ITEMS.md`：未完成事项、风险、验证边界和建议顺序。
- `CREATIVE_QUALITY_BASELINE.md`：任务书 C0 的写作/视觉 fixture、rubric、旧 Prompt 数据流、重放与隐私边界。
- `VISUAL_PROMPT_COMPILER_V1.md`：任务书 V1 的统一 Minimal Zine compiler、v0.3 pin、指纹、降级、升级与回滚合同。
- `VISUAL_BIBLE_PAGE_BRIEF_V2.md`：任务书 V2 的 Visual Bible、逐页三候选、distinctness、冻结编辑、Prompt 失效与回滚合同。
- `IMAGE_CANDIDATE_VISUAL_REVIEW_V3.md`：任务书 V3 的图片多候选、Contact Sheet、十维视觉审稿、单次定向修复、发布门禁与回滚合同。
- `LOCAL_CHINESE_TYPOGRAPHY_RECIPE_V4.md`：任务书 V4 的八种本地中文构图模式、严格 schema、主体避让、比例验收、诊断与回滚合同。
- `context.json`：供模型或脚本快速解析的结构化摘要。
- 根目录 `AGENTS.md`：Agent 入口和不可违反的约束。

## 新对话推荐提示词

在新对话中可以直接说：

> 请先读取仓库根目录 AGENTS.md，以及 docs/ai-context/ 下的全部上下文文件；然后重新检查当前 PR、分支 head 和 CI。不要根据旧聊天猜测仓库状态。完成任务后同步更新项目上下文包。

## 信息可信度

文档分三类事实：

1. **长期产品原则**：例如三层架构、人工发布、来源分类，除非用户明确改变，视为稳定约束。
2. **实现快照**：例如某文件、接口或数据库 revision，需要与当前代码核对。
3. **易变化状态**：PR、commit、CI、是否合并，必须实时查询 GitHub。

## 维护协议

每次重大修改后：

1. 更新日期和状态；
2. 记录根因而不仅是结果；
3. 记录被放弃方案及原因；
4. 更新关键文件和测试；
5. 移除已过期事实，避免多个互相冲突的“真相”；
6. 不写密钥、Cookie、本机私有数据或未确认的推测。
