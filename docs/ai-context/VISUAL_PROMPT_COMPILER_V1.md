# V1 Minimal Zine Visual Prompt Compiler

更新时间：2026-08-09

## 目标与结果

V1 消除两条 Prompt 路径的语义漂移：ChatGPT 网页 handoff 不再使用弱化的本地模板，API render 也不再丢弃文本模型返回的 recipe 后用 `_recipe_for()` 二次覆盖。两条路径现在都调用 `VisualPromptCompiler`，持久化同一个 `VisualPromptSpec`，区别只在于网页 handoff 不调用图片 API，而 API render 可以在明确配置后生成 raw anchor。

## 固定上游

- Skill：`gc-minimal-zine-poster-v0-3`
- tag：`v0.3.0`
- commit：`342b5c11d6fa9be261841ec722c12a683a9fa5e9`
- license：MIT
- vendored snapshot：`apps/api/app/vendor/native-skills/gc-minimal-zine-poster-v0-3/`
- runtime install：`data/native-skills/gc-minimal-zine-poster-v0-3/`

快照保留未修改的 `SKILL.md`、`references/`、`evals/` 和 eval 引用的 examples。v0.1 checkout 保留在独立目录，不被覆盖。运行时管理器会校验 vendor manifest、必需路径、commit 与文件内容；v0.3 可以离线安装。

## 数据合同

`VisualPromptContext` 冻结：

- article thesis；
- section title；
- page visual role；
- phrase / note；
- evidence summary；
- audience / emotion；
- current page concept；
- Visual Bible；
- previous / next page concepts；
- 实际内容 recipe 与已有人工 layout/anchor/texture/hue/mood 提示。

`VisualPromptSpec` 冻结：

- schema、Skill 和 compiler version；
- `faithful_skill | production_text_safe | legacy` mode；
- 四段 positive prompt；
- invariants 与 compact exclusions；
- 上游 `VisualPromptRecipe`；
- source / Prompt fingerprint；
- warnings。

source fingerprint 包含完整上下文、Skill SHA、compiler version 和 feature mode。Prompt fingerprint 还包含实际 Prompt、recipe、invariants、exclusions 与 warnings。因此 phrase、note、evidence、页面职责、文章主旨、Visual Bible、Skill 或 compiler 任一变化后，旧 Prompt 不可继续冒充新输入的结果。

## 编译与回退

生产默认 `X2RED_MINIMAL_ZINE_PROMPT_MODE=production`：先执行完整 v0.3 compiler，再由 `_four_paragraph_prompt(VisualPromptSpec)` 只追加本地中文的 text-safe invariant。该转换不得重新选择主题、布局、锚点、质感、色彩或 mood。

文本模型不可用、上游文件损坏、JSON 不合法或 recipe 校验失败时，compiler 才延迟调用 `_recipe_for()` 对应的确定性页面合同，并在 warnings 中写入 `DEGRADED_FALLBACK`。界面会显示该警告；服务不得把降级输出记为 faithful Skill 成功。

## API 与 UI

- `POST /api/native-skills/minimal-zine/variants/{id}/web-handoff`
  - 可调用文本 compiler；
  - 永不调用图片 API；
  - `force_recompile=true` 强制重新编译并返回 Prompt diff；
  - 提交后保存结构化 spec。
- `POST /api/native-skills/minimal-zine/variants/{id}/render`
  - regenerate / 缺 raw 时使用同一 spec 后调用图片模型；
  - recompose 不调用文本或图片模型。

轻内容 UI 常驻显示 compiler mode、Skill version、完整 recipe、warnings、source/Prompt fingerprint、重新编译动作和逐行 Prompt diff。异步编译沿用全局 busy/disabled 状态；按钮至少 44px，warnings 使用 `role=alert`，长指纹和 diff 可换行/滚动，窄屏改为单列。

## 兼容与回滚

本阶段没有数据库迁移。

1. 将 `.env` 设置为 `X2RED_MINIMAL_ZINE_PROMPT_MODE=legacy` 并重启服务，即可让新请求回到固定 v0.1 行为。
2. 带 raw anchor 且没有 `visual_prompt_spec` 的历史版本自动按 legacy 读取；升级不会批量作废已审阅原图或重新调用模型。
3. raw anchors、final posters、preview、manifest 与 ZIP 仍在 `data/exports/wechat/{variant_id}/`；rollback 不移动或删除文件。
4. `skill_v03` 可用于核对忠实上游 Prompt；`production` 才追加本地排字安全 invariant。
5. 若需要代码级回滚，可回退 V1 独立提交/PR；C0 fixtures 和 v0.1 runtime 未被删除。

## 验证

核心测试：

```bash
pytest -q apps/api/tests/test_visual_prompt_compiler.py
pytest -q apps/api/tests/test_minimal_zine_v14.py apps/api/tests/test_minimal_zine_v15.py
pytest -q apps/api/tests/test_creative_eval_fixtures.py
node --check apps/api/app/static/light-content-v15.js
```

覆盖网页路径只调用文本 compiler、web/API recipe 等价、phrase/note/evidence 指纹失效、显式 degraded、上游 recipe 不被覆盖、text-safe 不改视觉决策、v0.3 eval 路由、legacy rollback，以及旧 raw/final/字体/包生命周期。
