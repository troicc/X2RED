# X2RED 创作质量基线 C0

更新时间：2026-08-09 +08:00

## 1. 基线范围

本文件冻结任务书 C0 阶段的可重复基线。它只回答“修改前是什么”，不修改写作、Prompt、图片生成、排版、采集或发布行为。

- 基线 commit：`9073a4bc8a71a76dbf6762d7fc64a425eb3c99fe`
- C0 分支：`codex/x2red-c0-quality-baseline`
- 基线完整测试：`94 passed, 8 warnings`
- C0 修改后完整测试：`99 passed, 8 warnings`（新增 5 个基线/导出测试）
- 写作案例：12 个
- 视觉页面：20 个
- 图片政策：仓库不提交真实用户图片；C0 只冻结无权利风险的合成输入、旧 Prompt、Skill pin 和可选的图片 hash/仓库相对引用
- 生产影响：无 API、数据库、迁移、前端或模型路由变化

所有提交内的案例都是人工编写的合成回归材料，不复制真实用户正文或第三方长引文。它们用于比较新旧行为，不代表当前输出已经达到目标质量，也不能替代真实题材的人工盲评。

## 2. 文件与 schema

- `apps/api/app/domain/creative_eval_schemas.py`：Pydantic 严格 schema、指纹函数和私有导出结构。
- `apps/api/tests/evals/writing_cases.json`：12 个写作案例。
- `apps/api/tests/evals/visual_cases.json`：20 个旧版 Minimal Zine Prompt 页面。
- `apps/api/tests/evals/rubrics/writing_rubric.json`：9 项写作评分。
- `apps/api/tests/evals/rubrics/visual_rubric.json`：10 项视觉评分。
- `apps/api/tests/test_creative_eval_fixtures.py`：数量、schema、指纹、旧 Prompt 重放和导出脱敏测试。
- `scripts/export-creative-baseline.py`：只读导出现有本地数据库中的写作、Prompt、版本和元数据。

JSON 使用 `extra="forbid"`，未知字段会使测试失败。写作输出和视觉 Prompt 都保存 SHA-256；任何无意改写都会立即暴露。

## 3. 写作 fixture 清单

| ID | 分类 | 核心问题 | 当前已知不足 |
|---|---|---|---|
| `writing-tech-01-tail-evidence` | 技术解释 | 长材料尾部证据 | 标题冲突弱，例子少 |
| `writing-tech-02-immutable-revisions` | 技术解释 | 不可变版本 | 开头概念化，失败细节少 |
| `writing-tech-03-local-cjk` | 技术解释 | 无字锚点与本地中文 | 标题直白，字体失败路径浅 |
| `writing-tech-04-raw-final-boundary` | 技术解释 | raw/final 工件边界 | 首段密度高，缺少视觉示例 |
| `writing-news-01-release-explainer` | 新闻解释 | 合成软件发布 | 新闻感与时间线较弱 |
| `writing-news-02-policy-change` | 新闻解释 | 合成规则变化 | 标题普通，行动优先级浅 |
| `writing-opinion-01-evidence-first` | 观点评论 | 证据优先于风格词 | 论证样本少，结尾模板化 |
| `writing-opinion-02-human-publish` | 观点评论 | 人工发布边界 | 反常识张力与成本讨论不足 |
| `writing-light-01-four-page-focus` | 轻内容 | 四个专注动作 | 像操作说明，生活细节少 |
| `writing-light-02-source-check` | 轻内容 | 四步来源核验 | 句型整齐且标题普通 |
| `writing-wechat-01-local-first-flow` | 公众号长文 | 本地优先完整链路 | 仍偏短，叙事张力弱 |
| `writing-wechat-02-memory-firewall` | 公众号长文 | 写作偏好事实防火墙 | 偏产品文档，缺少具体反例 |

分布严格冻结为：技术解释 4、新闻解释 2、观点评论 2、轻内容 2、公众号长文 2。每个案例包含受众、阅读承诺、主旨、当前证据、约束、旧版输出、claims、pipeline trace、已知问题和输出指纹。

## 4. 视觉 fixture 清单

20 页由五组四页系列组成：

| 系列 | 页面 ID | 页面职责 | 主要基线问题 |
|---|---|---|---|
| 章节证据检索 | `visual-retrieval-01-cover` | cover | 主旨、短句、说明和证据不进入旧 compiler |
| 章节证据检索 | `visual-retrieval-02-process` | process | 页面职责不进入 fingerprint，上游 recipe 未结构化保存 |
| 章节证据检索 | `visual-retrieval-03-comparison` | comparison | compiler 不知道这是比较页，语义只靠 metaphor |
| 章节证据检索 | `visual-retrieval-04-conclusion` | conclusion | 无相邻概念输入，结论职责丢失 |
| 本地优先工作流 | `visual-local-first-01-cover` | cover | 无项目级 Visual Bible |
| 本地优先工作流 | `visual-local-first-02-process` | process | 动作关系未结构化，可能退化为装饰拼贴 |
| 本地优先工作流 | `visual-local-first-03-limitation` | limitation | 限制条件不进入 Prompt 约束 |
| 本地优先工作流 | `visual-local-first-04-conclusion` | conclusion | 文章主旨和系列关系丢失 |
| Prompt 生命周期 | `visual-prompt-01-cover` | cover | web/API compiler 语义不等价 |
| Prompt 生命周期 | `visual-prompt-02-evidence` | evidence | phrase、note、evidence 和 role 不进入旧指纹 |
| Prompt 生命周期 | `visual-prompt-03-limitation` | limitation | recipe 被本地 `_recipe_for` 压平 |
| Prompt 生命周期 | `visual-prompt-04-conclusion` | conclusion | 没有 compiler mode、version 和 warnings |
| 写作偏好事实防火墙 | `visual-firewall-01-cover` | cover | 论证关系被压成单一 metaphor |
| 写作偏好事实防火墙 | `visual-firewall-02-evidence` | evidence | evidence ref 和证据页职责不进入 Prompt |
| 写作偏好事实防火墙 | `visual-firewall-03-comparison` | comparison | 与下一页发生旧指纹/Prompt 碰撞 |
| 写作偏好事实防火墙 | `visual-firewall-04-conclusion` | conclusion | 文字和职责变化仍复用上一页 Prompt |
| 四步专注 | `visual-focus-01-cover` | cover | typography 只落为通用 `local-cjk` |
| 四步专注 | `visual-focus-02-scene` | scene | 不检查相邻页面主体重复 |
| 四步专注 | `visual-focus-03-process` | process | process role 不进入 Prompt |
| 四步专注 | `visual-focus-04-conclusion` | conclusion | 无 Visual Bible 保证系列材质和色彩一致 |

每页保存文章摘要、文章主旨、章节名、页面职责、phrase、note、证据摘要、视觉隐喻、storyboard 控件、旧 raw/final Prompt、当前 compiler 路径、Skill commit、compositor version、model-input fingerprint、Prompt fingerprint 和已知问题。

### 已冻结的关键旧缺陷

`visual-firewall-03-comparison` 与 `visual-firewall-04-conclusion` 的 phrase、note、evidence summary 和页面职责都不同，但旧版只对 `visual_metaphor/layout/anchor/accent/texture/mood` 建指纹。因此两页当前拥有相同 `model_input_fingerprint` 和相同最终 Prompt。

这不是 fixture 错误，而是 V1 必须修复的对照：新路径应让任一语义字段变化使旧 Prompt 失效，同时保留 legacy feature flag 的可回滚能力。

## 5. 修改前 Minimal Zine Prompt 数据流

### ChatGPT 网页 handoff

```text
PlatformVariant.metadata.poster_specs
  -> _storyboard_controls(spec)
  -> 本地拼接 generic raw_prompt
  -> _four_paragraph_prompt(...)
  -> 网页复制 Prompt
```

该路径不调用图片 API，也不调用文本 Skill compiler。指纹只覆盖六个 storyboard 控件，不覆盖 phrase、note、evidence、visual role、article thesis、Skill SHA 或 compiler version。

### API render

```text
完整旧版 SKILL.md + storyboard controls
  -> 文本模型 chat_json
  -> result.final_prompt
  -> _recipe_for(spec) 重新生成 recipe
  -> _four_paragraph_prompt(...) 再次 text-safe 包装
  -> 图片 API
```

当前实现会丢弃模型返回的上游 recipe，并让本地 `_recipe_for` 重新决定最终持久化 recipe。compiler 失败会报错，但不存在任务书要求的结构化 `DEGRADED_FALLBACK` 规格。

## 6. Rubric

写作采用 1–5 分：

1. evidence；
2. clarity；
3. specificity；
4. structure；
5. hook；
6. title；
7. style；
8. AI clichés；
9. usefulness。

视觉采用 1–5 分：

1. semantic match；
2. imageability；
3. composition；
4. thumbnail；
5. distinctness；
6. series consistency；
7. texture；
8. color anchor；
9. typography；
10. artifacts。

每项都有 1、3、5 分锚点和阻断项。含 critical unsupported claim、乱码/溢出、可读模型文字或水印、发布包包含 raw anchor 等情况不能被平均分掩盖。

未来阶段进行盲评时，应随机隐藏 legacy/new 标签，至少记录评审者、case ID、各维度分数、胜负和理由。任务书 W3 的 65%/70% 胜率只能由真实成对盲评得出，不能用模型自评或测试通过替代。

## 7. 重放与导出

重放提交内 fixture：

```bash
pytest -q apps/api/tests/test_creative_eval_fixtures.py
```

测试会重新调用当前 `_storyboard_controls`、`_safe_zone`、`_four_paragraph_prompt` 和 `_model_input_fingerprint`，证明同一输入可以逐字重建冻结的旧 Prompt。

从本地数据库创建私有重放包：

```bash
python scripts/export-creative-baseline.py \
  --database data/x2red.db \
  --output /path/outside/repository/creative-baseline-private.json
```

可用 `--limit-writing` 和 `--limit-visual` 做小样本检查。导出器：

- 以 SQLite `mode=ro` 和 `query_only` 打开数据库；
- 不加载 `.env`，不调用文本或图片模型；
- 导出 `DraftRevision`、`PlatformVariant`、`WritingArtifact` 及嵌套视觉 Prompt；
- 用稳定 hash 替换结构化 ID 字段；
- 清理 API Key、Bearer、Cookie、会话字段、敏感 URL 参数和绝对本机路径；
- 只在用户显式指定的路径写原子 JSON；
- 不修改源数据库。

真实导出仍可能包含用户正文、公开来源 URL 和待审元数据，所以默认是私有本地工件。即使脚本已脱敏，分享或提交前仍必须人工复核隐私和来源权利。

## 8. 当前已知系统问题

C0 只冻结、没有解决以下问题：

1. web handoff 没有执行完整 Skill compiler；
2. API 路径覆盖上游 recipe，并进行第二次 Prompt 压平；
3. Prompt 指纹遗漏 phrase、note、evidence、visual role、article thesis、Visual Bible、Skill SHA 和 compiler version；
4. 正向可成像信息相对负面禁令不足；
5. 没有文章级 Visual Bible 与冻结的逐页视觉简报；
6. 没有多候选、contact sheet、视觉审稿和一次定向修复；
7. 本地排字仍主要依赖安全区 caption，没有 recipe v2 的多种构图模式；
8. W1 已补齐语义 chunk、章节级 BM25/可选 embedding、重排和 MMR；C0 的尾部证据案例继续作为后续 W2/W3 成稿质量对照，不把结构门禁等同于模型盲评已完成；
9. 多 Agent 还没有 W2 的统一 Pydantic 输出与最终主张矩阵；
10. 标题竞赛、授权短范例和真实修改反馈学习仍未实现。

这些事项必须继续按 `C0 -> V1 -> V2 -> V3 -> V4 -> W1 -> W2 -> W3 -> UI1 -> OPS1` 的顺序在独立分支处理，不能为了界面观感先跳过底层质量路径。

## 9. 基线限制

- 合成写作案例适合防回归，不代表真实选题的内容质量分布。
- Prompt 可重放只证明编译文本稳定，不证明图片质量达到上游示例水平。
- 未提交真实图片，因此 composition、thumbnail、texture、color anchor、typography 和 artifacts 的最终分数需要后续本地受权图片或 contact sheet 才能完成。
- 当前测试不调用付费模型；真实模型 canary 必须在 OPS1 中设置显式成本上限并与 PR CI 隔离。
