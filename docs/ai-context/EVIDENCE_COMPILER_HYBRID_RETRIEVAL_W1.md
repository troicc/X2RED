# W1 证据编译与混合检索合同

更新时间：2026-08-29 +08:00

## 目标与旧问题

W1 将写作入口从“材料数决定预算、每份材料只取开头若干字符”切换为：

`原始正文 / 已写版本 → 语义 chunk → BM25 全文召回 → 可选 embedding 重排 → 权威/角色/权利重排 → MMR 去重与来源多样性 → 逐章节 evidence chunks`

旧路径会把长材料尾部的限制、反例或结论在写作前删除；多来源越多，每份材料保留的开头越短。公众号路径还会先把材料序列化为 JSON，再截断整个 JSON 字符串，既可能破坏结构，也无法解释丢失了哪一段。

## 严格 schema 与引用

`apps/api/app/domain/evidence_schemas.py` 定义严格、拒绝额外字段的：

- `EvidenceDocument`：来源、材料引用、标题、作者、发布时间、抓取时间、权利状态、编辑备注、平台和角色；
- `EvidenceChunk`：正文、原文字符位置、顺序、内容 hash 和完整 provenance；
- `EvidenceSectionRequest`：章节 ID、标题、问题、章节职责和预算；
- `EvidenceScore`：每个排序因素、重排分和 MMR 分；
- `EvidenceBundle`：compiler 版本、模式、后端、指纹、总 chunk/source 数、逐节 chunks、警告和完整 prompt payload。每个持久化 hit 同时冻结 rank、最终 MMR 分与九项 score breakdown，后续可重放排序判断。

所有 chunk 使用稳定的 `source_id:chunk_id`。原始来源使用 `c0001` 等顺序 ID；草稿或平台版本使用带材料 hash 的 chunk ID，仍保留其关联原始 `source_id`，不会与原始来源 chunk 冲突。已写版本只提供结构和表达，其事实必须回到原始来源。

`structured_content_json` 只读取标题等结构化元数据，不作为一整串正文切片。实际证据来自 `SourceItem.text_original` 或已明确选择的版本正文。

## 分块、召回与重排

分块优先使用 Markdown 段落、标题、中文/英文句末和分号边界；只有超长且没有自然边界的单元才在受控上限内强制拆分。每个 chunk 保存原文 `start_char` / `end_char`，尾段不会因处于材料末尾而自动消失。

默认召回后端是本地 BM25 全文索引，不依赖外部模型。若配置 OpenAI-compatible embedding endpoint，系统只对 BM25 候选与每个来源的最佳候选做向量重排，并在同一次编译中缓存 chunk vector，避免每个章节重复计费。embedding 未配置或调用失败时，后端明确记录 BM25 fallback，不影响本地检索。

重排显式覆盖：

1. semantic relevance；
2. source authority；
3. primary-source bonus；
4. freshness；
5. editor-note relevance；
6. section-role relevance；
7. rights status；
8. source diversity；
9. redundancy penalty。

MMR 会阻止完全相同或高度近似文本重复占满预算，同时奖励新的来源。权利状态参与排序，但检索命中不等于获得发布授权；最终事实、引用范围、版权和发布仍由人工复核。

## 生产集成

- `input_materials.py` 为来源和版本冻结作者、时间、权利和 evidence contract；
- `corpus_pools.py` 保留每条来源索引，再添加语义检索摘要与 evidence refs，不再按来源数平均截取每份材料开头；
- `writing_core.py` 根据任务单、研究职责或已批准大纲生成章节问题；
- `writing_agents.py` 将逐节 bundle 交给总编、研究员、写手和终稿角色，并把完整 trace 写入 immutable artifact；
- `editorial.py` / `reader_editorial.py` 的小红书编辑链路使用四类章节证据；
- `platform_studio.py` 优先按已有 H2 逐节检索，无 H2 时使用开头、机制、证据、比较和限制五类问题；公众号版本 metadata 冻结 bundle；
- `pool_memory.py` 只用整份材料的关键词 digest 匹配写作偏好，不再只看前 30,000 字符；事实防火墙保持不变。

Prompt 中需要限长的任意 JSON 现在通过 `bounded_json()` 生成仍可解析、带显式压缩标记的 JSON，不再截断已经序列化的 JSON 字符串。来源 evidence bundle 本身按章节预算生成，不再用字符串切片兜底。

## 配置与回滚

```env
X2RED_EVIDENCE_RETRIEVAL_MODE=hybrid

# 可选；留空时完全本地使用 BM25
X2RED_EVIDENCE_EMBEDDING_BASE_URL=
X2RED_EVIDENCE_EMBEDDING_API_KEY=
X2RED_EVIDENCE_EMBEDDING_MODEL=
```

- `hybrid` 是默认生产模式；没有 embedding 时仍运行本地 BM25、重排和 MMR。
- `legacy` 恢复按来源字符预算取开头的兼容路径；所有 bundle 和 hit 均显式标记 `DEGRADED_LEGACY_CHARACTER_SLICE`。
- 切换模式后重启服务。该切换不删除来源、语料池、写作 artifact、平台版本或历史 provenance。
- W1 无数据库迁移；新 trace 写入既有 JSON artifact / metadata。历史版本不回填、不静默重写。

## 验收基线

- 长材料尾部限制可被章节查询召回；
- 多来源按相关性、权威与多样性竞争，不再平均切成开头短片；
- 完全相同和高度近似文本不会占满章节预算；
- 深度写作 artifact 与公众号 metadata 都能逐节列出 evidence chunks；
- `source_id:chunk_id`、字符位置、作者、时间和权利状态可追溯；
- `hybrid` / `legacy` 可切换，legacy 明确 degraded；
- 未配置或故障的 embedding 均能回到 BM25；
- 直接截断序列化 JSON 的回归扫描为零。

最终本地验证：W1 定向 `13 passed`；写作、公众号、语料池与池子记忆联合回归 `38 passed, 1 warning`；完整 API 套件 `172 passed, 8 warnings`。全 API Ruff、compileall、导出脚本、shell、18 个活动 JavaScript、发布助手、全仓 JSON、敏感信息、diff、全新 0001→0012 SQLite 迁移与 x2red 0.12.0 wheel 内容检查全部通过。验证使用合成 fixture 和本地 BM25，未调用真实文本、图片或 embedding 模型，未写用户数据库。
