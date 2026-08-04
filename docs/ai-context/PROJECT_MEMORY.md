# X2RED 项目记忆

更新时间：2026-08-04 16:16 +08:00

## 一、当前快照

仓库：`troicc/X2RED`

功能分支：`agent/replace-crawlers-with-api-adapters`

PR：`#19 重构简中素材采集、语料池与三层创作工作区`

2026-08-04 收尾前的远端基线 head：`417adb4640ee7411362bc7a943b42c2c806a341b`

本轮实现提交：`f48fff4`（v15 轻内容、Minimal Zine、本地测试隔离和根级架构文档）。

Linux CI 便携性修复提交：`3063a9e`（非字体主题的 Minimal Zine 生命周期测试不再依赖宿主机预装 CJK 字体）。

2026-08-04 检查时 PR 状态：open、draft、mergeable、clean、尚未合并到 `main`。修复后远端验证 head `bc76e1b9ce550556ad892c81315f9ea0af453e63` 的 push/PR 两套 Python 3.12 和 3.13 共四个 Actions 均通过。该状态和 head 都是易变化事实。

2026-08-04 的本地 CI 等价验证：完整测试 67 passed、8 warnings；compileall、Ruff、所有 active Node 脚本、发布助手选择器、shell/py_compile 和全新数据库 0001→0010 迁移均通过。真实浏览器在 1600、1440、1024 宽度检查无 console error 或横向溢出；轻内容第 3 阶段为 1 个展开页和 3 个紧凑页，第 4 阶段显示同一不可变版本的 manifest、预览、ZIP 和 4 张成品。来源切换能同步到该来源已有版本；写作项目深链用非首项 ID 验证后精确选中目标项目。

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
- 长文写作项目；
- 公众号长文；
- 公众号轻内容图组；
- 审核、预览、发布包和人工发布。

### 3. 模型与 Skill

负责可替换的模型与视觉/写作能力：

- OpenAI-compatible 文本模型；
- 图片模型；
- 风格配置；
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

来源箱增加平台标签和平台切换；小红书、公众号长文、公众号轻内容和写作项目的来源选择器使用 `optgroup`；语料池来源选择器可按平台过滤。

当前产品壳直接加载：

- `apps/api/app/static/product-shell-v15.js`
- `apps/api/app/static/product-shell-v15.css`

旧的 v10/v12/v14 和 information-architecture 控制器仍留在磁盘用于历史参考，但不再由运行时或 CI 加载。v15 导航实现仍必须保持幂等，MutationObserver 触发时不能反复重排已经完成的导航结构。

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
4. compositor v4 保留完整稀疏模型 plate 和颜色，只清理受约束的高风险外沿；
5. 图片模型颜色信号被保留，不再全局灰阶化、统一 colorize、重复厚框或添加巨大强调圆；真正颜色贫乏时才在安全区外添加不遮挡内容且不超过 0.3% 的小型 registration mark；
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

- 风格和模型设置；
- 原生 Skill。

这是当前信息架构的产品基线。后续新增功能应优先并入这三层，而不是继续增加平级主导航。

### I. v15 产品壳和轻内容不可变分镜

v15 产品壳的 canonical 导航层固定为：

- 语料素材库：信号、原料、语料池；
- 内容工作台：工作台、写作、公众号、发布；
- 模型与 Skill：模型、风格和设置。

公众号轻内容在同一工作台内使用四个阶段：任务设置 → 文案候选 → 视觉分镜 → 成品交付。它会在进入视觉阶段前持久化当前候选和编辑框；视觉分镜只展开选中的一页，其余页面保持紧凑摘要；版式、视觉锚点、质感、强调色、焦点和缩放等枚举/控件显示中文标签。

分镜编辑通过 `POST /api/platforms/wechat/light/variants/{variant_id}/storyboard` 提交完整、唯一且覆盖全部页码的页面合同，并创建不可变的子 `PlatformVariant`；父版本保持不变，子版本带 `parent_variant_id` 和变更追踪。渲染请求只消费已冻结合同，不负责创作文案。

Minimal Zine 渲染接口 `POST /api/native-skills/minimal-zine/variants/{variant_id}/render` 支持 `mode: render_missing | recompose | regenerate`，以及可选的唯一一基页码 `pages`；旧客户端可用 `regenerate: true`，但显式 `mode` 与该 legacy 布尔值同时出现会被拒绝。`recompose` 必须找到存储的 raw anchor，只调用本地 compositor，不调用 Prompt compiler 或图片模型；`regenerate` 才会重新请求图片模型。渲染不会覆盖已有编辑文本。

### J. 2026-08-04 收尾审计修复

- 新增全局测试隔离 fixture：测试不再读取开发者真实 `.env`，并清除 `X2RED_*` 与代理变量；运行时加载 `.env` 的行为不变。
- 轻内容来源切换只选择同一 `source_id` 的已有版本，不再被此前来源的 `currentVariant` 劫持；从其他工作台带来源进入时同样优先匹配该来源。
- 写作项目深链恢复按 `data-project-id` 精确选择目标项目，不再无条件点击列表第一项。
- 自定义 storyboard `mood` 会进入冻结模型输入和 fingerprint，不再被静默降级为 `quiet`。
- README、根 `ARCHITECTURE.md` 和 `docs/WORKFLOW.md` 已统一到三层架构、MediaCrawler、语料池/批次与 Minimal Zine 本地合成合同。

### K. GitHub Actions 额度优化

由于仓库为 private，标准 GitHub-hosted runner 会消耗账户额度。旧工作流对 `agent/**` 同时监听 `push` 和 `pull_request`，每次 PR 推送再乘 Python 3.12/3.13，实际产生 4 个任务。

当前策略：

- `push` 只监听 `main`，PR 分支只由 `pull_request` 触发；
- PR 以受支持的最低版本 Python 3.12 作为日常门禁；
- `main` 和 `workflow_dispatch` 才运行 Python 3.12/3.13 完整矩阵；
- 同一 PR/分支启用 `cancel-in-progress`，新提交取消旧运行；
- 每个任务设置 15 分钟超时，防止异常挂起；
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

### DraftRevision

不可变编辑版本。任何人工修改应该产生新版本，旧版本保留。

### PlatformVariant

同一来源面向不同平台的不可变版本，例如微信长文、微信轻内容和平台专用制图结果。

### ReviewDecision / PublishTask

记录人工审核事件、冻结发布载荷、包哈希和发布状态。

## 六、模型与 Skill 边界

### 文本模型

使用 OpenAI-compatible chat endpoint，用于分析、写作、风格学习、平台适配和 Prompt 编译。无模型配置时，部分基础功能可以使用确定性回退，但高级工作室和原生视觉编译需要模型。

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

- 上游：`gc-minimal-zine-poster-v0-1`；
- 许可证：MIT；
- 独立固定版本 checkout；
- 当前采用上游视觉决策 + X2RED 本地中文合成。

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

截至 2026-08-04，README、根 `ARCHITECTURE.md`、`docs/WORKFLOW.md` 与本上下文包已经统一到当前三层架构。仍可能存在历史设计文档或已退役前端控制器中的旧术语；它们不得覆盖运行时入口和本上下文记录的产品合同。

## 九、未来 Agent 的工作方式

开始任务时：

1. 读取上下文包；
2. 查询当前 PR、head 和 CI；
3. 检查实际文件，确认文档没有过期；
4. 明确任务属于语料素材库、内容工作台还是模型与 Skill；
5. 修改后运行相关测试和完整 CI；
6. 更新上下文包。

禁止仅根据聊天记忆直接修改主分支，禁止在未确认工作区状态时建议强制 reset 或覆盖用户改动。
