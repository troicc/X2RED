# W3 标题竞赛、授权风格范例与真实反馈

更新时间：2026-08-29 +08:00

## 1. 目标与边界

W3 只改变公众号深度写作中“怎么写”的质量路径，不扩大“能写什么”的事实范围。标题、风格范例和历史反馈都必须服从当前项目冻结的 W1 evidence pack；事实研究、事实审稿和 final claim extractor 不接收历史风格范例。

生产默认由 `X2RED_WRITING_QUALITY_MODE=production` 控制。切换为 `legacy` 会跳过 W3 标题竞赛、标题冻结和短范例注入，但不删除或重写任何 `WritingArtifact`、`DraftRevision`、风格档案、记忆卡或反馈。W2 `X2RED_WRITING_SCHEMA_MODE` 与 W3 开关相互独立。

旧路径：

```text
任务单 + 证据包 + 大纲 + 整体风格规则 -> Writer 自拟单个标题与正文 -> Final 可再次改标题
模型稿/人工稿 -> 可选客户端 diff -> 反馈记录
```

新路径：

```text
当前 evidence pack -> 12—20 标题候选 -> 本地过滤 -> 读者第一眼排序 -> top 5
                                                               |
                                                               v
作者选择 -> immutable title_preference -> Writer / Final 逐字标题合同

approved memory snapshot -> rights/fact guard -> 2—4 个职责短范例 -> Writer / Final
模型 output DraftRevision -> direct human revision -> server diff -> human-gated memory candidate
```

## 2. 标题竞赛

大纲生成后，`title_strategist` 一次返回 12—20 个严格结构化候选，候选至少覆盖五种并尽量覆盖全部七种机制：结果、冲突、反常识、场景、问题、数字和判断。每个候选冻结标题、读者承诺、机制与当前 `source_id:chunk_id` 引用。

本地 `TitleTournamentService` 不扩写事实，只执行可重放过滤：

- 空泛承诺与模板标题；
- 未知、缺失或语义不相干的 evidence ref；
- 当前证据没有出现的阿拉伯数字或中文数量词；
- 震惊体和过度悬念；
- 常见套路词；
- 当前证据没有支持的绝对承诺；
- 高相似候选同质化。

`ReaderSimulationService` 对剩余候选做确定性的第一眼主题、价值、具体性、长度和自然度评分，并优先返回机制互异的 top 5。该分数只是排序器，不冒充真实读者或人工盲评。

作者只能在最新且质量门通过的 `title_tournament` top 5 中选择。选择保存为新的、已批准的 `title_preference` artifact；旧锦标赛或不足五个合格候选时的选择都会被拒绝。writer 和 final reviser 的 W2 Schema 合同要求标题与冻结选择逐字一致。质量门通过但作者未选择时可使用当前 top 1 的显式可回滚默认值；没有五个合格候选时 artifact 标记质量门未通过，并回到未冻结标题的降级写作，不伪称竞赛成功。

## 3. 授权风格短范例

风格训练请求必须明确提交 `confirm_original_or_authorized=true`，否则在请求校验阶段拒绝。训练仍先从原创/授权样本提炼规则，再用留出样本和作者真实反馈验证。作者反馈会被保存为确定性的 `author_overrides`，优先级固定为：

1. 作者明确覆盖规则；
2. 已批准真实反馈；
3. 模型推断。

创建写作项目时，系统从当时冻结的池子记忆快照建立一个不可变 `style_exemplar_bundle`。普通池子记忆 Prompt 不再携带正向原句；只有专用检索器可以选择最多四个短范例，并要求：

- 正式记忆卡为 approved，且批准者为 human；
- 来源为原创、授权、用户真实改稿或明确确认权利的来源；
- 使用策略为 `style_and_structure_only`；
- 每个范例标记 opening、title、transition、judgment、ending 或节奏等修辞职责；
- 优先职责多样，文本不超过 120 字；
- URL、账号、日期、金额、比例、具体数字结果等历史事实风险会被拒绝；
- Prompt 明示范例不是事实来源，只能学习标注职责。

模型原始样本和历史文章不会整包进入写作 Prompt。找不到安全范例时使用空 bundle 并给出原因，不从历史正文临时抓句子。

## 4. 模型原稿到人工终稿的反馈

深度写作完成后，作者从准确的 output `DraftRevision` 保存一个新的 human revision。`EditorialService.revise()` 冻结直接父版本 ID；反馈接口只接受：

- 修改前版本属于当前项目并由 model、model-polish 或 multi-agent 生成；
- 修改后版本由 human 保存、版本号更高，且直接以所选模型稿为父版本；
- 非空文章类型、修改原因和至少一个受影响维度。

客户端不能提交自己的 diff。服务端保存模型原稿和人工终稿的完整标题、正文、标签、版本、创建角色和 SHA-256，并用 `difflib` 生成 unified diff、标题/标签变化和正文字数差。反馈通过既有 append-only 池子记忆流程生成候选；列表动态展示 none、candidate、approved 或 inactive 状态。只有人工预览、编辑并批准后，反馈才会进入正式记忆。

## 5. 验证与盲评边界

自动化覆盖候选数量与机制、全部过滤类别、确定性排序、多样性补位、降级竞赛拒绝选择、top 5 选择、过期选择、标题逐字合同、授权/人工批准、四例上限、修辞职责、历史事实风险、服务端 diff、版本血缘和记忆批准状态。W3 实现时完整 API 套件为 `191 passed, 8 warnings`；Ruff、Python/JavaScript/Shell 编译、发布助手回归、全新 SQLite `0001→0012` 迁移和 wheel 构建通过。

C0 案例与自动测试只证明结构、权限和防火墙回归，不是质量胜率。任务书中的标题相对旧基线 ≥65% 和风格输出相对旧基线 ≥70% 必须用隐藏 legacy/new 标签的真实成对人工盲评得出；在完成真实模型样本、权利复核和人工记录前，文档、UI、测试和 PR 都不得声称这两个阈值已经达到。

## 6. 回滚

```env
X2RED_WRITING_QUALITY_MODE=legacy
```

重启服务后，新运行跳过 W3 质量层，继续使用既有 W2 写作链。回滚不变更数据库结构，也不物理删除已保存的标题候选、竞赛结果、标题偏好、风格 bundle、人工 revision、反馈或池子记忆状态。
