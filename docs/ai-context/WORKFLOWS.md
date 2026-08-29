# X2RED 端到端流程

## 1. 发现层

### 1.1 X 信号发现

信号台负责：

- 监控 X profile、search、quote stream 或趋势；
- 保存 discovery candidate；
- 保存指标快照；
- 基于冻结的作者相对基线打分；
- 执行 L1 快速分析；
- 对有限候选执行 L2 深度拆解；
- 提取可复用 pattern。

候选有两种后续路径：

1. 直接加入语料素材库，成为标准 `SourceItem`；
2. 完成 L2 后创建写作项目。

新架构优先允许先进入素材库，再由用户决定是否建池或进入工作台。

### 1.2 简中平台发现

原料库通过本地 MediaCrawler 搜索：

- 小红书；
- 抖音；
- 快手；
- B站；
- 微博；
- 贴吧；
- 知乎。

运行前提：

- 本机 Chrome/Chromium 以 CDP 方式运行；
- 对应平台已有合法登录态；
- MediaCrawler 独立环境完成安装；
- 仅运行低频、人工触发的 search；
- 不抓评论、不批量下载媒体。

搜索结果先作为候选展示，用户选择后导入标准来源。导入时保留平台、作者、URL、正文、指标、图片 URL、发现查询和原始快照，但过滤敏感登录字段。

### 1.3 网页和人工来源

网页、文档、手工粘贴或其他合法输入也进入 `SourceItem`。公开可访问不等于可自由转载，默认仍需 limited quote 或人工版权复核。

## 2. 标准来源和平台分类

所有来源进入统一来源箱后，按平台组展示。用户可以：

- 搜索；
- 查看原文、作者、指标和关联来源；
- 添加编辑备注；
- 设置权利状态；
- 在语料素材库中归档、恢复或彻底删除标准来源；
- 在具体内容工作台中只归档或恢复该工作台的处理状态；
- 加入一个或多个语料池；
- 直接进入工作台。

来源备注变更、来源删除和池成员变化会触发相关语料池重编。

标准来源的 `SourceItem.workspace_state` 是素材库级状态；工作台的待处理/已归档状态存入独立的 `SourceWorkbenchState`。小红书工作台中的归档和“标记已发布”只能更新 `xhs` 工作台状态，不能让同一来源从公众号长文、公众号轻内容或深度写作中消失。只有素材库的明确全局归档或彻底删除动作可以改变标准来源本身。

## 3. 语料池

### 3.1 建池

用户从多个平台勾选来源并创建语料池。名称可以留空，由系统根据全池主题自动命名。

编译步骤：

1. 清理 HTML、裸 URL 和重复行；
2. 标准化标题、作者和正文；
3. 为每条来源生成摘要和关键词；
4. 聚合全池主题、共识、矛盾和选题空缺；
5. 为每条成员分配一个记忆位置；
6. 生成受上下文预算约束的全池压缩记忆。

池越大，每条来源的记忆越短，但不能简单截断后半部分来源。

### 3.2 预览下一批

预览使用当前池记忆和轮换算法选出候选来源，但不增加使用次数，也不创建最终生成记录。

选择优先级：

1. 与本批 focus 的相关性；
2. 历史使用次数更少；
3. 平台多样性；
4. 关键词和主题多样性；
5. 确定性序列扰动，避免每次顺序完全相同。

### 3.3 正式冻结批次

正式生成或“送到工作台”时创建 `CorpusBatch` 和隐藏 anchor `SourceItem`。

批次冻结：

- 全池记忆；
- 详细来源；
- pool revision；
- focus；
- sequence；
- fingerprint；
- provenance。

隐藏 anchor 可以被工作台选择，但不应该像普通平台来源那样反复出现在发现列表中。

## 4. 小红书工作台

### 4.1 文案

输入可以是单一来源或语料池批次。用户选择快速编辑流或多 Agent 写作项目。

每次保存产生不可变 `DraftRevision`。转换、精简、重写标题等操作也应产生新版本，而不是覆盖旧版本。

### 4.2 来源选择、归档与语义

来源箱按来源组用一个选择器过滤，不把十个平台压成横向滚动标签。每条来源只显示一个平台/来源组徽标；语料池冻结批次必须标为“语料池批次/冻结批次”，不得沿用 X 图标、`X SOURCE` 或“在 X 查看原文”。摘要限制行数，名称可省略，单条归档/恢复是独立的 44px 操作，不与“打开来源”共享点击区域。

来源箱顶部提供“待处理/本台归档”，选中来源后的粘性工具栏也提供“归档此来源/恢复到本台”。两处都必须明确说明只影响小红书工作台；全局“彻底删除”与工作台归档视觉和文案分离。

### 4.3 阅读与判断布局

来源选中后，正文阅读是主任务。全局主导航在 861—1360px 默认收为 76px 图标栏，来源箱自动收为 64px；两处都必须保留可见、可键盘操作的恢复按钮。正文使用完整单列宽度，“我的判断”和“来源素材”通过按需侧抽屉查看和编辑，不再作为永久第三列挤压正文。抽屉必须支持遮罩、Escape、焦点圈定和焦点回返，关闭后编辑内容仍保留。

### 4.4 制图

可使用：

- 快速 HTML/CSS 卡片渲染；
- Guizang Editorial 原生完整链；
- Guizang Swiss 原生完整链。

Guizang 运行时使用固定上游 checkout、完整 seed、主题、布局 recipes、validator 和 Playwright 截图。

### 4.5 审核和发布

发布前：

- 明确批准当前不可变版本；
- 完成事实检查；
- 完成来源和素材版权检查；
- 创建冻结发布包；
- 预览标题、正文、标签和媒体顺序。

X2RED 可以打开发布准备页面，但不点击最终发布。

## 5. 公众号长文工作台

### 5.1 来源和证据

长文任务使用一个可叠加的混合输入区，以下材料可以同时提交，不是三选一：

1. 素材库中的 `SourceItem` 或冻结的 `CorpusBatch`；
2. 已经写好的 `DraftRevision` 或 `PlatformVariant`；
3. 直接粘贴的正文，以及可选标题、原作者和原文 URL。

粘贴正文不能只存在于临时表单或直接拼进 Prompt。系统先通过 `POST /api/sources/manual` 将它落为标准 `SourceItem`，按正文 hash 去重，标记为 `web/manual` 和 `needs_review`，再进入与库内来源相同的 evidence、provenance 和审核链路。

用户选择一个归档主来源，并可从按平台和材料类型分组的复选列表中选择原始来源、草稿版本和平台版本；连同粘贴形成的来源，一次最多冻结 32 个材料引用。列表提供搜索、清空和已选计数；点击复选框即可多选，不依赖 Command/Ctrl。重复引用会去重，已写版本关联的原始来源会自动加入事实 evidence pack。

原始来源决定“能写什么”。已写版本标记为 `written_version`，可以提供结构、段落组织、代码草稿和表达方式，但其中的具体事实仍须由关联的 `SourceItem` 支持。常规公众号版本冻结 `input_material_refs`、材料 provenance 和 `evidence_source_ids`；深度写作的不可变 `source_selection` artifact 冻结同一组材料引用、正文 hash 和来源快照。六张重复的风格说明卡片不再占据来源栏；排版主题只在主题选择器中配置一次。

W1 hybrid 模式不会再按材料数平均分配字符开头。每个来源和已写版本先按段落、标题与句子边界编译为带作者、时间、权利和原文位置的语义 chunk，再为任务单、事实研究或大纲中的每个章节单独执行 BM25 召回、可选 embedding 重排、来源/新鲜度/编辑备注/章节职责/权利重排和 MMR。写作 artifact 与公众号 metadata 冻结逐节 `source_id:chunk_id`；无 embedding 时本地 BM25 正常工作。legacy 仅用于回滚并明确标记 `DEGRADED_LEGACY_CHARACTER_SLICE`。池子记忆仍只决定怎么写，不能作为这些 evidence chunks 的替代。

### 5.2 生产阶段与深度写作

公众号长文只有一条主生产线，界面必须持续显示五个阶段：

1. 冻结材料：读取素材库、已写版本和粘贴内容，输出可追溯选择；
2. 深度研究与审稿：可选，输出任务单、证据包、大纲、完整初稿、三路结构化审稿、issue 裁决、深度终稿、final claims 和 claim-evidence matrix；
3. 公众号完整成稿：读取原始证据和可选深度终稿，创建独立 `PlatformVariant`；
4. 人工编辑与配图：基于不可变版本保存新版本和槽位图片，不覆盖历史；
5. 排版、审核与发布包：输出 HTML、封面、预览、manifest 和 ZIP，最终发布仍由用户完成。

选中已打包成品时，界面必须分别表达“已选成品 vN”与“正在查看阶段 N/5”：历史结果不得冒充系统当前阶段，点击阶段 2 后顶部必须显示阶段 2，而成品上下文仍保留。成品态首屏提供“开始新文章”；它仅退出当前项目/版本，保留历史版本、主来源和已选材料，遇到未保存 DOM 编辑时先询问，然后展开材料区并聚焦阶段 2 动作。新文章状态切换来源时不自动选中旧成品。

每个阶段必须显示当前状态、读取、输出或修改、Skill/实际模型路由和建议优化点，不能只展示一个模糊的“生成中”。深度写作详情进一步展开为八步：任务定义、证据研究、文章结构、完整初稿、三路审稿、修改裁决、终稿与证据闸门、公众号成稿。artifact 的原始 JSON 默认折叠，但阶段说明始终可见，方便按问题类型调整来源、Prompt、模型、推理强度或人工反馈。

深度写作不是第二个长文产品。writer 和 final_reviser 目标都是 1800—4500 个中文字符，模型输出至少 1200 个非空白字符、3—6 个完整 H2，并使用 12000 输出 token、360 秒窗口、停止原因捕获、完整度门禁和一次整篇重写；终稿少于完整初稿非空白字符的 70% 时按疑似过度压缩处理。最终 `DraftRevision` 最多保留 50000 字符，不能先经过小红书短稿的 4000 字清洗器。项目 API 暴露 `output_draft_id/version/chars`；公众号版本 metadata 记录 `writing_project_id` 和 `writing_final_artifact_id`，完成动作必须把准确终稿与冻结材料交回阶段 3，而不是跳到小红书卡片或仅按来源猜测草稿。

W2 production 模式要求每个 Agent 通过自己的严格 Pydantic Schema。JSON 或合同失败只允许一次结构修复；第二次仍失败则保留 failed AgentRun，但不保存普通成功 artifact。三路 reviewer 的 issue 必须可定位、分严重度、附证据和最小修复；Chief 只能逐一裁决既有 issue；Final 只能执行批准 issue。终稿随后由事实隔离角色重新提取 claims，本地 checker 对照 W1 evidence chunks、初稿 claims 和批准 issue 生成 matrix。critical/major 无证据、未经批准的主要主张扩张或找不到终稿原句时进入 `claims_blocked`，不创建 `DraftRevision`，也不能交接公众号。`legacy` 只恢复旧流程并显式标记 degraded，详细合同见 `STRUCTURED_WRITING_CLAIM_MATRIX_W2.md`。

### 5.3 生成和编辑

输入材料后，系统生成平台专用 `PlatformVariant`。模型长文使用 12000 输出 token 和最长 360 秒请求窗口，并记录 `finish_reason`。保存前必须同时通过以下完成度检查：正文不是短片段、至少三个完整 H2、Markdown 代码围栏闭合、没有连续代码行落在围栏外、正文不是半句话或半行代码、配图计划引用的章节真实存在。

第一次未通过时，系统携带全部输入材料、失败原因和上一候选重写整篇，而不是只续写尾部。第二次仍不合格则拒绝保存。模型若返回明确的裸语言标记或代码围栏外溢，X2RED 可以只调整 Markdown 围栏，不修改代码内容；调整后仍须重新通过全部完成度检查。模型创建的旧残缺文章可调用 `POST /api/platforms/variants/{variant_id}/repair-incomplete` 创建不可变修复版本，旧版本原样保留。

用户随后编辑 Markdown/HTML、封面 brief 和摘要，完成预览和发布包。写作偏好仍只决定怎么写；所有发布都需要人工事实、引用和版权复核。

### 5.4 半自动视觉交接

启用“生成逐段生图 Prompt”后，长文版本为封面和每个正文二级标题建立独立视觉槽位。每个槽位必须包含放置位置、正文摘要、构图目标、主题色、比例与负面约束，明确禁止文字、Logo、水印、UI 和来源未支持的人物/产品/数据；封面还要为本地 21:9 与 1:1 裁切保留中央安全区。

视觉交接流程：

1. 用户在 X2RED 复制某个槽位的精确 Prompt；
2. 将 Prompt 粘贴到具备图片 Skill 的 Codex 中生成一张成品图；
3. 回到同一槽位上传或替换图片；
4. X2RED 校验格式、尺寸和像素数，校正方向并规范化文件，登记为 `needs_review` 的 `Asset`；
5. 上传使版本回到 draft 并清除旧输出引用，用户必须重新构建发布包；
6. 重建后，封面素材进入本地 21:9/1:1 封面，逐节图片插入对应 H2 后；Markdown、干净 HTML、预览、manifest、ZIP 和 `visual-handoff.md` 必须引用同一版本。

图片生成和回传成功不等于可以发布。人工仍须检查版权、事实暗示、水印、异常文字、平台标识、裁切和段落对应关系。

必须保持：

- 输入来源和证据可追溯；
- 版本不可变；
- HTML 经过验证；
- 发布包和预览引用同一版本；
- 最终发布由用户完成。

## 6. 公众号轻内容工作台

公众号工作台的“长文编辑”和“轻内容图组”是同一入口下互斥的两个工作模式，不是上下堆叠的两条生产线。进入轻内容后必须隐藏公众号长文五阶段生产线、长文编辑器和长文预览，只保留轻内容四阶段；切回长文时再恢复长文区域。模式切换必须同时更新标题说明、选中状态、键盘焦点和 `tabpanel` 可访问关系。

### 6.1 生成候选

用户选择来源、配方、页数、季节话题、受众、语气、视觉风格和质量模式。系统由策划、写作、审稿、视觉导演和总编等角色生成候选和评分。

### 6.2 采用候选和人工编辑

当前候选只是 UI 选择，必须通过接口创建新不可变版本。人工编辑标题、subtitle、summary、正文和标签后也要保存为新版本。

保存文章字段只创建新的文章版本，不得从正文重新切句覆盖已经冻结的逐页 `phrase` / `note`。已有分镜必须原样保留，并在 metadata 记录同步状态；只有完全没有分镜的 legacy 版本才允许使用本地应急初始化。

模型生成和候选采用必须检查同页及跨页文案：短句与说明不能相同或近似，也禁止“第 N 页说明 = 第 N+1 页短句”。每页要表达不同论点或生活场景，并随版本保存 `evidence_basis` 与 `source_refs`。语料池批次还要冻结并记录全池来源数、全池字符数、详细来源 ID 和实际提交模型的字符范围，页面证据不得由写作偏好替代。

### 6.3 生成图组

v15 工作台固定为四阶段：任务设置、文案候选、视觉分镜、成品交付。进入视觉阶段前必须先持久化当前候选和编辑框，不能只依赖旧版本 ID。

新建 production 版本先从文章与当前证据生成不含逐页物件的 `VisualBible`，再为每页生成恰好 3 个具体概念。全组通过主体、anchor、layout、cliché、复合抽象与 evidence ref 门禁后，主编选择才能冻结为 `PageVisualBrief`。四页至少使用三种 layout，具体主体不重复；不允许再把一个 `series_motif` 复制到全组。模型/结构失败时必须显示 `DEGRADED_VISUAL_BRIEF`，并进入可审计的确定性候选。

阶段 3 的分镜编辑：

1. 只展开当前选中的一页，其他页面显示紧凑摘要；
2. 新版编辑短句、说明、页面职责、具体主体、动作/关系和镜头字段；旧版本才继续显示自由“视觉隐喻”；UI 标记分镜为未保存，枚举控件使用中文标签；
3. 保存时向 `POST /api/platforms/wechat/light/variants/{variant_id}/storyboard` 提交完整、唯一且覆盖所有页码的合同；
4. 接口创建新的不可变子 `PlatformVariant`，保留 `parent_variant_id` 和模型输入/本地构图变更追踪，父版本不变；
5. 接口再次检查同页/跨页文案碰撞，并保留原 evidence refs 与 Visual Bible 不变量，重新冻结全组 brief 并运行 distinctness；
6. 任何 PageVisualBrief 语义修改使旧 Prompt、recipe、raw trace 与合成指纹过期；仅保存正文不自动改分镜；
7. 该接口只冻结视觉合同，不生成文案，也不在请求中调用图片模型。

渲染阶段：

1. 读取当前显示版本；
2. 若 UI 当前候选与保存选择不同，先采用候选；
3. 比较编辑框和版本内容；
4. 有变化则创建新版本；
5. 保存有变化的分镜；
6. 根据视觉风格选择普通 renderer、Minimal Zine native 图片接口，或 ChatGPT Images 网页人工交接；
7. 生成后强制刷新并定位接口返回的准确版本；
8. 进入成品交付，检查整组图片、预览、清单、ZIP 和人工复核状态。

图片 Prompt 编译完成后进入 V3 候选生命周期：API 默认同一 Prompt 生成 3 张，provider 不支持或运行时拒绝 `n` 时按单张顺序调用并记录回退；网页人工路径每页可上传 1—4 张。每张候选保存 Prompt run、序号、provider/model、hash、尺寸、成本、延迟和状态，并生成只含缩略图与编号的 Contact Sheet。系统对 semantic match、主体、构图、缩略钩子、系列一致性、质感、色锚、伪影、无字安全和视觉俗套进行结构化预检；未通过者不得自动选中。

用户可以选中、保留、人工批准或带具体理由驳回候选。选择不会删除其他候选；每页最多允许一次定向修复，优先使用 provider edit，完整重复 Visual Bible、PageVisualBrief、Prompt invariants 和参考图要求，并且只修改一个主要缺陷。修复后仍未通过则停止自动重试。全部页面都存在通过审稿或人工批准的选中候选时才允许构建发布包；候选原图、Contact Sheet 和 raw anchor 永不进入 ZIP。

因此用户无需手动执行“采用 → 保存 → 刷新 → 生图”的四步临时流程。

### 6.4 ChatGPT Images 网页人工交接

当用户不希望使用图片 API 时，轻内容允许逐页使用 ChatGPT 网页生成视觉锚点：

1. 用户点击“生成并显示本页 Prompt”；X2RED 先保存当前候选、编辑稿和分镜，再冻结当前页 Prompt 及 fingerprint；
2. X2RED 通过 `POST /api/native-skills/minimal-zine/variants/{variant_id}/web-handoff` 本地编译 Prompt，不调用文本或图片 API，并把完整 Prompt 常驻显示在只读文本框中供人工检查；
3. 只有 Prompt 成功显示后，“复制完整 Prompt”、ChatGPT Images 外链和上传控件才解锁；用户复制 Prompt，在 `https://chatgpt.com/images` 的已登录网页中自行生成并下载图片。X2RED 不后台控制账号，也不把网页包装成隐藏 API；
4. 用户把 1—4 张下载图以重复 `file` 字段回传至 `POST /api/native-skills/minimal-zine/variants/{variant_id}/external-anchor?page={page}`；
5. X2RED 校验并统一为 PNG，建立与 API 相同的候选/审稿记录和 Contact Sheet；选中通过门禁的候选后再使用本地 compositor 排中文、页码和最终版式；
6. 分镜在 Prompt 生成后发生任何变化时，旧 Prompt 立即标为过期，复制、外链和上传同步锁定，必须重新生成并检查；
7. 可以逐页回传并预览，但只有全部页面齐全时才生成 manifest、HTML preview 和 ZIP 发布包。

如果前端已加载新静态资源、但正在运行的 Python 仍是未注册 `/web-handoff` 的旧进程，接口会返回 404。界面必须把这种版本错配解释为“重启 X2RED 后刷新”，不能把裸 `Not Found` 暴露给用户。

网页模型输出同样需要人工检查版权、水印、异常文字和视觉质量，不能因为换成 ChatGPT 就跳过审核。图片接口路径仍保留为显式备选，不再是轻内容唯一生图入口。

### 6.5 迭代和批准

迭代前先持久化当前编辑稿，再带 feedback 生成新轮次。批准前也先持久化，确保批准的是用户实际看到的稿件。

### 6.6 阶段状态和失败

- 从文案候选离开时自动保存当前候选和编辑稿；
- 视觉分镜有未保存修改时，阶段摘要明确显示“分镜有未保存修改”；
- 成品交付显示已生成的页数，未渲染时不能误标记为完成；
- 渲染失败保留文本、分镜和旧版发布包，允许人工重试。

## 7. 池子记忆闭环

池子记忆位于“模型与 Skill”层，与语料池的全池压缩记忆不是同一个对象。语料池/批次负责当前任务的来源和事实；池子记忆只保存长期可复用的表达、结构、判断和视觉经验。

候选来源包括草稿、平台版本、真实反馈、模式卡、写作产物、审核产物和人工规则。流程固定为：

1. 从内容选择学习维度和适用范围，或输入已授权手工规则；
2. 模型或确定性提炼只创建 `memory_candidate`；
3. 用户预览并编辑规则、偏好、禁用表达、短例、结构、视觉方向和 scope；
4. 来源权利未批准时额外确认授权；
5. 人工明确批准后创建 `memory_card`；
6. 后续变化通过 `memory_event` 追加替代或撤销，不覆盖旧卡。

生成前先按平台、格式、文章类型、风格、受众、配方和视觉路线硬过滤，再按主题相似度、来源优先级、时间和使用次数评分；同来源去重，默认检索 4—8 条。每个 Agent 只接收职责相关维度，事实/证据角色不接收风格记忆。

当前 evidence pack 是事实边界。历史记忆中的人名、数字、日期、结果和因果不能进入新文章，除非当前来源也提供相同事实。每个目标冻结不可变 `PoolMemorySnapshot`；AI 变换和轻内容迭代为新版本克隆选择，不回写旧快照。只有配置模型真实消费后才将 snapshot 标为 applied 并追加 `PoolMemoryUsage`，无模型回退不会伪记影响。

池子记忆入口存在于快速草稿、多 Agent 终稿、公众号长文和轻内容成品，也可以从独立“池子记忆”工作台统一管理、检索预览和查看使用链路。

## 8. Minimal Zine native

### 8.1 Prompt 编译

生产默认由统一 `VisualPromptCompiler` 读取固定的 v0.3.0 `SKILL.md`、`references/` 和 `evals/`。网页 handoff 与 API render 都调用这一入口；网页路径允许调用文本模型，但绝不调用图片 API。输入上下文必须包含文章主旨、章节标题、页面视觉职责、phrase、note、证据摘要、受众、情绪、当前页概念、Visual Bible、冻结 PageVisualBrief 和前后页概念。PageVisualBrief 存在时是唯一页面级视觉权威；compiler 不得再从 phrase/note 猜测第二个主体、动作、layout、palette 或 mood。

编译结果持久化为 `VisualPromptSpec`：compiler mode、Skill 名称/版本、四段正向 Prompt、invariants、compact exclusions、完整上游 recipe、source fingerprint、Prompt fingerprint 和 warnings。recipe 不得再被本地默认值覆盖；只有文本编译失败时才调用确定性页面合同，并写入 `DEGRADED_FALLBACK`。

`source_fingerprint` 覆盖 phrase、note、evidence、visual role、article thesis、Visual Bible、Skill SHA 和 compiler version；任一变化都会让旧 Prompt 与 raw anchor 失效。生产 `_four_paragraph_prompt(VisualPromptSpec)` 只追加“图片模型不写可读文字、本地合成中文”的 text-safe invariant，不重新选择主题、layout、anchor、texture 或 hue。

V2 还将 PageVisualBrief 及其 source fingerprint 纳入模型输入指纹。`X2RED_VISUAL_BRIEF_MODE=legacy` 可单独回滚视觉简报层，不改动 V1 Prompt compiler 模式或历史工件。

输出必须是结构化 JSON，其中图片 Prompt 明确要求：

- 竖版 3:5；
- 大面积旧纸留白；
- 单一视觉簇；
- 仅一个高饱和强调色；
- 禁止所有文字、数字、Logo、水印、签名、角标、UI 和标签；
- 按 layout 为本地中文保留一块约 28% 至 30% 的安全留白；它可以在上方或下方，不得用硬色块假造。

Feature flag：

- `X2RED_MINIMAL_ZINE_PROMPT_MODE=production`：默认 v0.3 + text-safe；
- `skill_v03`：忠实 v0.3 Prompt；
- `legacy`：完整回滚到固定 v0.1 编译行为。

带历史 raw anchor 且没有 `visual_prompt_spec` 的旧版本自动按 legacy 读取，升级不会批量作废已审阅成品。

### 8.2 图片模型

图片模型只生成视觉锚点。它不负责最终中文、页码或正文。

### 8.3 本地合成

本地合成器：

1. 读取并校正模型图方向；
2. 按原始宽高比完整 contain 模型 plate，不再固定裁掉顶部、底部和两侧；
3. 从 raw anchor 取样纸色，只用羽化纸色遮罩清理高风险外沿，不用硬边米色矩形覆盖主体；
4. 保留模型的稀疏 plate 和颜色，颜色贫乏时也不自动伪造蓝色方块、短线或 registration mark；
5. 对旧版中文 layout 名称做兼容归一，并根据明确模式、页面职责和 layout 冻结一个 `TypographyRecipe`；
6. 在归一化文字区域上尝试水平/垂直镜像避让关键主体，其他模式都无法安全放置时才使用 `safe_zone_caption`；
7. 按 3:5、3:4、21:9 或 1:1 的实际区域动态缩放和换行 phrase、note、label 与页码，无法容纳或触边时明确失败，不做静默截断；
8. 使用 cmap 已验证的本地 CJK 字体；缺少可验证字体时明确失败；
9. 保存逐区域字号、换行、像素框、旋转、透明度、溢出和主体碰撞诊断；
10. 写入 exports，并将 raw `anchor_XX` 与 final `poster_XX` 分开记录。

V4 feature flag：

- `X2RED_TYPOGRAPHY_RECIPE_MODE=production`：默认八模式 recipe v2；
- `legacy`：恢复单一安全区和羽化纸色 veil。

详细 schema、模式、指纹、公众号封面集成和回滚合同见 `LOCAL_CHINESE_TYPOGRAPHY_RECIPE_V4.md`。

### 8.4 重建产物

每次 native render 后，必须确保下列产物来自同一 variant：

- 页面 PNG；
- Markdown；
- manifest；
- HTML preview；
- ZIP 发布包。

旧版本模型图可以在 compositor version 变化后被重新本地合成，避免不必要地再次调用图片 API。`recompose` 只接受已验证 raw anchor，永远不把 final poster 当作 raw fallback。

### 8.5 渲染 API 合同和发布包

`POST /api/native-skills/minimal-zine/variants/{variant_id}/render` 的 body 支持：

- `mode`: `render_missing`、`recompose` 或 `regenerate`；
- `pages`: 可选的一基、唯一页码数组；
- `regenerate`: 兼容旧客户端的布尔值。

显式 `mode` 和 `regenerate=true` 同时出现会被拒绝。`render_missing` 补齐缺失页，`recompose` 只重排已有 raw anchor，`regenerate` 才重新调用图片模型。每次完整 render 都在 `data/exports/wechat/{variant_id}/` staging 后原子 promotion；失败时保留先前目录和数据库引用。manifest 和 ZIP 使用显式 allowlist，仅包含 `poster_XX`、`article.md`、`manifest.json` 和 `preview.html`，不把 `anchor_XX` 打进发布包。

## 9. 审核和权利

任何工作台都不能因为模型输出成功而跳过人工审核。

最低检查：

- 事实、数字和因果是否有来源；
- 引用是否超出合理范围；
- 图片是否有权使用；
- 是否出现模型水印、异常字符或平台标识；
- 平台文案是否符合实际内容；
- 发布包是否对应批准版本。

## 10. 状态和失败原则

- 采集失败不删除已保存来源；
- 媒体失败不删除正文；
- 生图失败保留文本版本和错误；
- 审核拒绝不删除版本；
- 发布失败保留冻结包和哈希；
- 所有失败应在 UI 可见并允许人工重试；
- 不允许静默回退后错误标记为成功。
