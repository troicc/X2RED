# V4 本地中文排版 Recipe v2

更新时间：2026-08-29 +08:00

## 目标与边界

V4 在不把最终中文交给图片模型的前提下，让字体重新参与 Minimal Zine 和公众号封面的构图。图片模型仍只生成无字 raw anchor；中文字、说明、页码、区域底板、避让和最终合成都在本地完成。

本阶段不改变 raw/final/package 边界，不新增数据库迁移，也不降低人工事实、版权、水印和异常文字复核要求。

## 严格 Schema

`TypographyRecipe` 冻结以下核心字段：

- `mode`；
- `text_regions`；
- `font_role`、`weight`；
- `size_ratio`、`line_height`、`tracking`；
- `rotation`、`alignment`；
- `opacity`、`blend_mode`；
- `collision_policy`。

每个 `TextRegion` 使用 0—1 归一化坐标，并声明文字职责、来源、字号倍率、最大行数、局部旋转、对齐、透明度、底板和内边距。Pydantic 使用 `extra=forbid`，区域必须完整位于画布内，ID 在同一 recipe 中必须唯一。

冻结 recipe 还保存 schema version、source fingerprint、选择理由、降级来源和避让变换。只有文章文字、页面、比例、layout、visual role、请求模式和关键主体区域完全相同时，才复用已有 recipe；输入变化会生成新指纹和新选择，不回写旧版本。

## 八种模式

| 模式 | 主要构图职责 |
|---|---|
| `type_led_large` | 大字成为主视觉，说明和页码退居次级 |
| `edge_pressed_phrase` | 标题压近一侧边缘，另一侧留给主体 |
| `diagonal_fragments` | 将短句拆成两个斜向片段 |
| `ghost_text` | 低透明大字作为底层节奏，正文另设可读区 |
| `archive_microtype` | 档案标签、微排说明、大比例标题和页码共同组织页面 |
| `type_in_color_block` | 在本地深色块中承载准确中文，不要求图片模型排字 |
| `margin_scatter` | 两侧边注与底部说明形成散排结构 |
| `safe_zone_caption` | 其他模式无法避开主体时的最后安全兜底 |

`safe_zone_caption` 不再是全页默认。选择器优先读取明确冻结模式，再结合页面职责和 layout，最后使用确定性页面轮换；只有其他模式及其避让变换全部碰撞时才降级。

## 主体避让与无溢出门禁

Minimal Zine compositor 根据冻结 layout 提供保守的关键主体矩形；公众号封面根据实际 cover style 和比例提供视觉区矩形。选择器依次尝试 `identity`、`mirror_x`、`mirror_y` 和 `mirror_xy`，文字职责区域不得与关键主体相交。低透明 ghost 底字可以软叠，但可读标题和说明仍须避让。

渲染器按区域自身尺寸计算内边距，从 recipe 字号向下寻找能同时满足宽度、高度、旋转和最大行数的字体。它不以省略或截断掩盖溢出；任一区域无法容纳、像素触边或可读文字覆盖主体时，渲染明确失败。诊断记录每个区域的逻辑框、实际像素框、字号、换行、旋转、透明度、碰撞和裁切状态。

CJK 字体继续通过 `cmap` 验证，优先使用配置字体、PingFang、Songti 或 Noto CJK。无法验证中文覆盖时，Minimal Zine native render 明确失败，不把 `.notdef` 方框当作成品。

## 集成位置

- Minimal Zine 在每页 spec 保存 `typography_recipe_v2`，在 `composition_diagnostics.typography` 保存逐区域结果；composition fingerprint 包含冻结 recipe。
- 公众号 21:9 与 1:1 封面先渲染无文字视觉底图，再由同一 recipe engine 叠加本地中文，使 Playwright 与 Pillow fallback 使用一致的文字合同。
- 轻内容页检查器显示模式中文名、比例、可见区域数、无溢出/主体避让状态、字体角色、字重、字号比、行高、字距、避让变换、选择原因和降级提示。
- manifest 与预览继续同步读取同一 composition diagnostics；ZIP 仍使用显式 allowlist，只含 final poster、正文、manifest 和 preview。

## 比例与视觉验收

自动化覆盖 3:5、3:4、21:9 和 1:1，逐项验证中文内容未被修改、无溢出、主体未遮挡。八种模式均在 Minimal Zine 原生 1200×2000 画布渲染；其中大字主导、对角碎句、档案微排和色块承字还执行缩略图像素差异门禁。

人工联系表复核确认八种模式均可辨认，至少上述四种在缩略图尺度具有明确不同的空间骨架。该检查是本地合成器质量证据，不替代真实图片主体和最终发布人工审图。

隔离浏览器验收使用专用临时数据库和合成的只读诊断数据，不读取或写入用户数据库，也不调用文本/图片模型。1280×800 桌面端保持分镜与页检查器双栏，排版模式、比例、区域数、无溢出、主体避让和字体参数均可见；手机断点请求为 375×812（内置浏览器实际最小画布 450×812），界面改为单栏，诊断卡片、中文与参数 chips 正常折行。根页面无横向溢出，四阶段导航保留有意的局部横向滚动，console 无 error/warning。

最终本地门禁为 typography 定向 `30 passed`、完整 API 套件 `159 passed, 8 warnings`；回归明确保证非显式选择时 `safe_zone_caption` 始终位于所有其他模式之后。CI 范围 Ruff、compileall、Python/shell/全部活动 JavaScript 语法、发布助手选择器、context JSON 和 diff check 全部通过。全新 SQLite 数据库可从 0001 升级到 0012；wheel 构建成功，并包含 typography schema、engine、Minimal Zine/封面集成、UI 与测试。

## Feature flag、升级与回滚

```env
X2RED_TYPOGRAPHY_RECIPE_MODE=production
```

- `production`：使用 recipe v2、冻结指纹、主体避让和逐区域诊断；
- `legacy`：恢复 V4 前的单一安全区、羽化纸色 veil 和本地标题/说明/页码排法。

切换 flag 需要重启服务。它不会删除历史 raw anchor、final poster、候选或审计记录。旧版本没有 `typography_recipe_v2` 时会在下一次明确重合成时生成 recipe；不会静默改写已审阅成品。回滚也不允许把 final poster 当作 raw anchor，发布包排除 raw 的合同不变。
