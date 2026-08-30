# V2 Visual Bible 与逐页视觉简报

更新时间：2026-08-09 23:06 +08:00

## 目标与边界

V2 解决同一 `series_motif` 被复制到全部页面、抽象隐喻换词复用、页面职责不清和 Prompt 从短句重新猜画面的缺陷。它不负责生成 contact sheet、多图视觉审稿、语义画像或成图评分；这些属于 V3/V4。

核心顺序固定为：

`文章与当前证据 -> Visual Bible -> 每页 3 个概念候选 -> 全组 distinctness -> 主编选择 -> 冻结 PageVisualBrief -> V1 Prompt compiler`

Visual Bible 只定义“怎么画”的项目不变量。PageVisualBrief 只定义当前页“画什么、承担什么职责、由什么证据支持”。两者都不能扩张事实范围。

## 数据合同

- `VisualBible` 冻结纸张、色板、强调色规则、印刷工艺、字体模式、摄影/插画处理、版式分布、重复母题政策、禁用陈词与项目不变量；不得包含页面级具体主体、人物、场景或动作。
- `PageVisualBrief` 冻结页码、章节、视觉职责、判断、读者情绪、具体主体、次要主体、动作/关系、场景、视点、裁切、光线、材料、版式、字体模式、局部色板、保留/禁止项和证据引用。
- `PageVisualConceptSet` 每页恰好保存 3 个候选及主编选中的 candidate ID；`FrozenVisualBriefBundle` 保存 Bible、全部候选、选中结果、distinctness 报告、compiler 版本、模式、警告和 SHA-256 source fingerprint。
- 当前存储继续使用 `PlatformVariant.metadata_json` 与 `poster_specs`，没有数据库迁移。生产新版本写入 `visual_brief_mode=production`、`visual_bible`、`visual_brief` 与 `visual_distinctness`；每个 poster 同步保存冻结 brief、三候选、选中 ID 和 source fingerprint。

## 生成与降级

Studio 模式且模型配置真实可用时，文章级模型必须先生成 Visual Bible，再一次生成全部页面的三候选。Bible 失败、候选 schema 失败或 distinctness 不通过时，系统显式记录 `DEGRADED_VISUAL_BRIEF`，改用可审计的确定性三候选；不得把确定性结果伪称为模型结果。

确定性编辑器也必须满足：

- 4 页至少 3 个 layout family；
- 每页 concrete subject 不重复，模板只换页码也视为重复；
- 不允许全部使用同一 anchor，尤其不能全是 `object-specimen`；
- 禁止希望灯塔、人生迷宫、通往未来的门等陈词；
- 禁止把多个抽象概念揉成一个不可画对象；
- 每页至少一个 evidence ref；
- 第一页是 cover、末页是 conclusion，中间页承担可解释的 scene/evidence/process 等职责。

## 编辑、缓存与 Prompt

- 正文标题、摘要或 body 的保存继续保留既有 storyboard，既不重写短句，也不自动重建 Visual Bible/PageVisualBrief。
- 分镜编辑必须提交已有 PageVisualBrief；后端保留原 evidence refs 和 Visual Bible 不变量，重新校验/冻结 brief，并对全组重新执行 distinctness。
- 重复主体、无证据、非法版式/色板或 Bible 泄漏会返回可读 400，不保存半成品。
- V1 compiler 在 production 只能从冻结 PageVisualBrief 取得页面主体、动作、场景、职责、版式、色板和情绪。`phrase`/`note` 仅用于本地中文排版和缓存，不得再推导第二套画面。
- PageVisualBrief 或其 fingerprint 变化属于模型语义变化，旧 Prompt、recipe、raw-anchor trace 和最终合成指纹全部过期；只改正文不会触发这一过程。
- 历史版本没有 `visual_brief_mode` 时按 legacy 读取，不追写、不静默改变已审阅 raw anchor。

## UI

视觉分镜展开页显示冻结 PageVisualBrief、页面职责、具体主体、动作/关系、场景、视点、裁切、光线、读者情绪、三候选数量和 evidence refs；检查器显示选中 brief 与 Visual Bible 不变量。旧版本继续显示“视觉隐喻”字段。

所有控件沿用 v17 暖白/炭黑/赤陶系统、44px 交互目标、可见焦点和窄屏单列布局。颜色不作为唯一状态信号。

## Feature Flag 与回滚

`X2RED_VISUAL_BRIEF_MODE=production|legacy`，默认 `production`。

紧急回滚时：

1. 设置 `X2RED_VISUAL_BRIEF_MODE=legacy` 并重启服务；
2. 新建/候选采用恢复 V1 之前的 `_apply_visual_direction` 路径；
3. 已有 V2 版本仍保留完整 metadata，可继续审计，不做数据删除或降级迁移；
4. V1 `X2RED_MINIMAL_ZINE_PROMPT_MODE` 是独立开关，不应为回滚 V2 而改动；
5. 恢复 production 前先对目标版本重新保存分镜，使 PageVisualBrief 和 Prompt 指纹一致。

## 验证

- `apps/api/tests/test_visual_brief_distinctness.py`：schema、Bible-first 调用顺序、三候选、distinctness、陈词/复合抽象、显式降级、人工重冻结、Prompt 单一权威与语义失效。
- C0 `visual_cases.json` 的 5 组、20 页全部进入确定性 V2 验收，每组均满足四页至少三版式、主体唯一、职责/证据完整、Bible 不含逐页对象。
- `test_light_content_lab_v12.py` 端到端覆盖新建、渲染、候选切换、正文编辑不改 storyboard、迭代与人工审批。
- 最终本地结果：完整 API 套件 `118 passed, 8 warnings`；V2 定向 `9 passed`；V1 compiler + V2 authority 联合回归 `18 passed`；轻内容端到端 `3 passed`。新模块 Ruff、compileall、JavaScript 语法、context JSON 和 diff check 通过。
- 真实浏览器使用临时数据库副本验收 1280×800 与 375×812：四页 UI 实际读取到 4 个不同主体、4 个不同 layout 和 cover/scene/evidence/conclusion 职责；冻结 brief、三候选状态、证据与 Bible 不变量可见，无页面横向溢出，console 0 error。未调用文本或图片模型，未写入用户主数据库。

测试通过不代表真实图片已达到上游示例质量。V2 不调用图片模型完成视觉验收；真实成图仍需后续 contact sheet、视觉审稿和人工事实/版权/水印复核。
