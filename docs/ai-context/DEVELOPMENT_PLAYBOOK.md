# X2RED 开发与运行手册

## 1. 当前分支和 PR

2026-08-29 当前 V4 任务：

- 基线分支：`agent/replace-crawlers-with-api-adapters`
- 基线 SHA：`bd77743808a3eb1ccb0bfa29efa959c0aee2b33a`（V3 PR #23 squash merge）
- 当前本地任务分支：`codex/x2red-v4-local-chinese-typography-recipe-v2`
- PR #19 仍是基线功能 PR；V4 使用独立分支和独立 PR
- V3 PR #23 已在 head `5ceeefcbe894cbc8e367f6fcdb314ae738e56d40` 的 CI run `819` 成功后 squash merge
- V4 已实现严格 recipe schema、八种模式、冻结指纹、主体避让、四比例门禁、封面复用、UI 诊断和 legacy flag；安全区最后兜底回归补齐后定向 `30 passed`、完整套件 `159 passed, 8 warnings`，本地静态/迁移/wheel 门禁已通过，剩余 latest-head CI、PR 与合并
- V4 合并前不得创建 W1 分支

任务书后续阶段必须从最新已合并的前一阶段创建独立分支；C0 后依次为 V1、V2、V3、V4、W1、W2、W3、UI1、OPS1。

2026-08-04 检查时：

- 仓库：`troicc/X2RED`
- 分支：`agent/replace-crawlers-with-api-adapters`
- PR：`#19`
- 远端基线 head：`417adb4640ee7411362bc7a943b42c2c806a341b`
- 本轮实现提交：`f48fff4`
- Linux CI 字体测试隔离：`3063a9e`
- 远端 CI 已验证 head：`bc76e1b`（push/PR 两套 Python 3.12 和 3.13 全部通过）
- PR 仍为 open、draft、mergeable、clean，尚未合并到 `main`

每次工作前都应重新检查，不要假设上述状态仍成立。

## 2. 安全更新本地仓库

### 2.1 `git pull --ff-only` 的条件

只有在以下条件满足时才能安全快进：

- 当前分支正确；
- 工作区没有会阻止切换或更新的未提交修改；
- 本地 HEAD 与远端没有分叉；
- 本地分支是远端分支的祖先或与之相同。

推荐命令：

```bash
cd /path/to/X2RED
BRANCH=agent/replace-crawlers-with-api-adapters

if [ -n "$(git status --porcelain)" ]; then
  echo "工作区不干净，请先提交或 stash"
  git status --short
  exit 1
fi

git fetch --prune origin

if git show-ref --verify --quiet "refs/heads/$BRANCH"; then
  git switch "$BRANCH"
else
  git switch --track -c "$BRANCH" "origin/$BRANCH"
fi

git branch --set-upstream-to="origin/$BRANCH" "$BRANCH"

if ! git merge-base --is-ancestor HEAD "origin/$BRANCH"; then
  echo "本地分支与远端已经分叉，不能执行 --ff-only"
  exit 1
fi

git pull --ff-only
./scripts/start.sh
```

有本地修改时：

```bash
git stash push -u -m "before X2RED update"
```

更新和验证完成后再执行：

```bash
git stash pop
```

不要使用 `git reset --hard` 或强制覆盖用户工作，除非用户明确要求并已确认备份。

### 2.2 PR 合并后的 main 流程

只有确认 PR 已合并后才使用：

```bash
git switch main
git fetch --prune origin
git merge-base --is-ancestor HEAD origin/main || {
  echo "main 已分叉，停止更新"
  exit 1
}
git pull --ff-only origin main
./scripts/start.sh
```

## 3. `scripts/start.sh` 行为

启动脚本：

- 使用 `set -eu`；
- 自动定位仓库根目录；
- 优先使用 `X2RED_PYTHON`；
- 否则优先寻找 `python3.12`，再尝试 `python3`；
- 要求 Python 3.12+；
- 检查并必要时重建无效 `.venv`；
- 安装或升级 pip、setuptools、wheel；
- 安装 `-e '.[publisher]'`；
- 默认安装 Playwright Chromium，并使用 `.venv/.x2red-playwright-ready` 标记；
- 启动前自动执行数据库迁移；
- 默认绑定 `127.0.0.1:8787`。

跳过 Playwright 浏览器安装：

```bash
X2RED_SKIP_BROWSER_INSTALL=1 ./scripts/start.sh
```

这适合只验证后端或无需浏览器渲染的场景，但 Guizang 截图、部分预览和浏览器发布准备可能不可用。

指定 Python：

```bash
X2RED_PYTHON=/absolute/path/to/python3.12 ./scripts/start.sh
```

## 4. MediaCrawler 运行前提

启动脚本会调用 MediaCrawler 安装脚本。主要配置和约束：

- checkout 位于 `.vendor/MediaCrawler`；
- 使用固定上游 commit；
- 使用独立 uv 环境；
- 本机浏览器 CDP 默认需要可访问；
- 平台登录由用户在本机浏览器完成；
- 不把登录 Cookie 写入项目文档或提交到 Git。

排查时先检查：

1. Chrome/Chromium 是否以 CDP 模式启动；
2. CDP 地址是否与配置一致；
3. 对应平台是否仍保持登录；
4. `.vendor/MediaCrawler` 是否位于固定提交；
5. uv 环境是否与 lockfile 同步；
6. 平台是否出现验证码、访问限制或登录过期。

不要通过扩大抓取频率或绕过验证来“修复”平台限制。

## 5. 关键环境变量

### 文本模型

```env
X2RED_MODEL_BASE_URL=https://provider.example/v1
X2RED_MODEL_API_KEY=
X2RED_MODEL_NAME=
```

### 图片模型

```env
X2RED_IMAGE_BASE_URL=
X2RED_IMAGE_API_KEY=
X2RED_IMAGE_MODEL=glm-image
X2RED_IMAGE_SIZE=1024x1536
X2RED_MINIMAL_ZINE_PROMPT_MODE=production
X2RED_VISUAL_BRIEF_MODE=production
X2RED_IMAGE_CANDIDATE_MODE=production
X2RED_IMAGE_CANDIDATE_COUNT=3
X2RED_TYPOGRAPHY_RECIPE_MODE=production
X2RED_EVIDENCE_RETRIEVAL_MODE=hybrid
X2RED_EVIDENCE_EMBEDDING_BASE_URL=
X2RED_EVIDENCE_EMBEDDING_API_KEY=
X2RED_EVIDENCE_EMBEDDING_MODEL=
X2RED_WRITING_SCHEMA_MODE=production
```

图片 endpoint 未单独配置时可以继承文本模型 provider；`X2RED_IMAGE_MODEL` 为空时不得把本地占位图伪装成原版 Minimal Zine 生成结果。

Minimal Zine Prompt 模式支持 `production`（默认 v0.3 + text-safe）、`skill_v03`（忠实 v0.3）和 `legacy`（v0.1 回滚）。修改后需要重启服务。历史 raw anchor 没有 `visual_prompt_spec` 时自动按 legacy 读取，不能通过切换模式批量重写旧版本。

V2 `X2RED_VISUAL_BRIEF_MODE=production|legacy` 和 V3 `X2RED_IMAGE_CANDIDATE_MODE=production|legacy` 各自独立回滚。V3 production 默认请求 3 张 API 候选；`X2RED_IMAGE_CANDIDATE_COUNT` 只允许 1—4。网页人工回传允许每页 1—4 张，并与 API 使用同一候选、审稿和发布门禁模型。切换 legacy 不删除既有候选、Contact Sheet 或审计记录。

V4 `X2RED_TYPOGRAPHY_RECIPE_MODE=production|legacy` 独立控制本地中文构图层。production 冻结八模式 recipe 与逐区域诊断；legacy 恢复单一安全区 compositor。切换不会删除 raw/final、候选或审计记录，也不会把旧成品静默重排。

W1 `X2RED_EVIDENCE_RETRIEVAL_MODE=hybrid|legacy` 独立控制写作证据输入。hybrid 默认使用本地 BM25、重排和 MMR；三个 embedding 配置全部留空时不会调用外部向量模型。配置单独的 OpenAI-compatible `/embeddings` endpoint 后只对召回候选重排。legacy 会在 artifact 中写入 `DEGRADED_LEGACY_CHARACTER_SLICE`，不改写历史版本。详细合同见 `EVIDENCE_COMPILER_HYBRID_RETRIEVAL_W1.md`。

W2 `X2RED_WRITING_SCHEMA_MODE=production|legacy` 独立控制多 Agent 输出合同。production 对每个角色执行严格 Schema、一次结构修复以及最终 claim-evidence gate；legacy 恢复旧链但 AgentRun/artifact 一律显示 degraded。production 下无模型 fallback 也不会伪称成功，critical/major 无证据会进入 `claims_blocked` 且不创建 output DraftRevision。切换不重写历史产物，详细合同见 `STRUCTURED_WRITING_CLAIM_MATRIX_W2.md`。

### 调度器

```env
X2RED_SCHEDULER_ENABLED=true
X2RED_SCHEDULER_TIMEZONE=Asia/Shanghai
X2RED_AUTO_L1_GRADES=T1,T2,T3
X2RED_AUTO_L2_GRADES=T2,T3
X2RED_AUTO_L2_DAILY_LIMIT=5
```

已有 `.env` 不会因为 `git pull` 自动加入新键。新增配置必须手动合并，不要覆盖用户现有密钥。

## 6. 数据库迁移

当前功能分支包含 Alembic revision `0012`。`0010` 新增语料池和批次表；`0011` 新增 `pool_memory_snapshots` 和 `pool_memory_usages`，正式记忆卡继续复用 append-only `review_artifacts`；`0012` 新增工作台隔离的 `source_workbench_states`。

`./scripts/start.sh` 和 `x2red serve` 默认自动迁移，因此正常启动不需要先单独运行迁移。

手动执行：

```bash
x2red migrate
```

迁移要求：

- 全新 SQLite 数据库可从头建表；
- 历史数据库可从旧 revision 增量升级；
- 迁移恢复测试必须验证旧 job 和核心数据不丢失。

不要在没有备份和迁移计划时直接修改生产数据库文件。

## 7. 测试和 CI

GitHub Actions 的额度优化策略是：PR 只跑 Python 3.12，`main` push 和手动 `workflow_dispatch` 跑 Python 3.12/3.13 完整矩阵；PR 分支不再额外触发 push workflow。同一 PR/分支的新运行会取消旧运行，每个任务最多 15 分钟。主要门禁：

```bash
python -m compileall -q apps/api/app
python -m py_compile scripts/run-mediacrawler.py
sh -n scripts/start.sh scripts/setup-mediacrawler.sh
x2red migrate
node --check <所有前端脚本>
node apps/api/extensions/wechat-publisher-assistant/content.test.mjs
pytest -q
ruff check apps/api --select E,F,I,B,UP --ignore E501,E701,E702,UP035,UP042,B008,I001
```

2026-08-04 23:03 本地 CI 等价验证为 71 passed、8 warnings。测试数量会变化，不能把固定数字当成永久门槛；真正门槛是当前分支全部测试通过。该次还通过了 compileall、Ruff、active Node 脚本检查、发布助手选择器、shell/py_compile、`git diff --check`、全新数据库 0001→0011 迁移和现有数据库 0010→0011 增量升级。`apps/api/tests/conftest.py` 会隔离开发机 `.env`、`X2RED_*` 和代理变量，避免真实模型/代理配置污染测试；这不改变生产运行时配置加载。运行时依赖使用 `httpx[socks]`，因此宿主机配置 SOCKS 代理时不会在模型客户端初始化阶段因缺少 `socksio` 退出。Minimal Zine 的产物/回滚测试会注入 font preflight，避免依赖 CI 宿主字体；专门的字体解析测试仍使用真实环境验证 CJK 可用与缺失路径。

涉及 Python 版本差异的高风险 PR，在合并前应从 Actions 页面手动触发完整矩阵。不要为了跳过文档提交而直接给必需 workflow 添加 `paths-ignore`，否则 required check 可能保持 Pending。

### 重要回归范围

- 历史数据库迁移恢复；
- 来源和语料池；
- 池子记忆候选、人工批准、严格 scope、角色隔离、事实防火墙、替代/撤销、快照和真实使用记录；
- MediaCrawler normalization 和跨平台 URL 校验；
- 启动脚本和安装脚本；
- 公众号发布助手选择器；
- Minimal Zine 本地中文合成；
- 模型图边缘角标区域裁切；
- exports 路径、preview 和 ZIP；
- 直接加载的 v15 产品壳和轻内容控制器语法；旧 v10/v12/v14 控制器只留在磁盘，不是 runtime/CI 入口。
- Minimal Zine v15 分镜不可变修订、raw/final 分离、render mode 校验和发布包 allowlist。
- V4 八种本地中文 recipe、3:5/3:4/21:9/1:1 无溢出、主体避让、缩略图差异、公众号双比例封面和 legacy 回滚。
- W2 全角色 Schema 重放、一次修复上限、review issue 定位/证据、Chief/Final issue 权限、final claims、critical/major 支持度与 `claims_blocked` 完成阻断。

## 8. 手工 smoke test

CI 不能替代真实浏览器交互。重要改动后至少验证：

2026-08-04 23:03 已在 1600、1440、1024、800 宽度执行池子记忆浏览器检查：独立导航、来源选项、手工规则、检索预览、空状态和响应式布局通过，无 console error 或横向溢出；此前轻内容第 3 阶段 1 个展开页 + 3 个紧凑页、第 4 阶段成品与交付链接、来源切换和非首项写作项目深链基线继续保留。后续改动仍需至少验证：

1. 来源箱按平台切换和搜索；
2. 来源下拉 `optgroup` 不会丢失当前选择；
3. MutationObserver 不产生循环重排；
4. 信号候选可加入素材库；
5. 简中平台搜索、选择和导入；
6. 语料池建池、预览、正式批次；
7. 三个“送到工作台”入口；
8. 轻内容四阶段状态、当前候选/编辑稿持久化和准确版本定位；
9. 视觉分镜只展开选中页，保存创建不可变子版本；
10. `render_missing`、`recompose`、`regenerate` 及 legacy 布尔冲突校验；
11. Minimal Zine raw anchor 与 final poster 分离、CJK cmap 字体检查、边缘角标人工审图；
12. preview 和 ZIP 内文件一致且 ZIP 不含 anchors；
13. 旧数据库启动并升级成功。
14. 池子记忆从内容生成候选后必须人工预览/编辑/批准，未授权来源需要明确确认；替代和撤销不物理覆盖旧卡。
15. 检索只命中任务 scope，事实角色不获得风格记忆；无模型回退不新增 usage，模型真实消费才标记 snapshot applied。
16. 草稿、AI 变换、多 Agent、公众号长文/轻内容和原生 Skill 的新版本都关联自己的冻结记忆快照。

## 9. 文档和上下文维护

完成重大任务后：

- 更新 `docs/ai-context/PROJECT_MEMORY.md`；
- 更新 `OPEN_ITEMS.md`；
- 更新 `context.json`；
- 必要时更新根目录 `AGENTS.md`；
- 把新的验证结果写入 PR；
- 删除或修正旧文档中的冲突描述。

上下文文件必须记录“为什么”，不能只记录改了哪些文件。
