# macOS：为 X2RED 接入 GLM-5.2

X2RED 的 AI 编辑流程分为两步：

1. **编辑分析**：识别来源事实、原作者观点、待核查内容、读者价值、候选角度和文章结构。
2. **成稿写作**：选择一个明确角度，根据分析结果写成中文小红书草稿。

没有配置模型时，X2RED 只能使用规则化兜底稿，无法完成真正的语义分析、英文转中文编辑和选题判断。

## 1. 获取智谱 API Key

登录智谱开放平台，在 API Keys 页面创建一个通用 API Key。

内容编辑应使用智谱的**通用 API 端点**，而不是仅限编程工具使用的 Coding 端点。

## 2. 修改项目配置

在 Mac 终端运行：

```bash
cd /Users/EasyMaker/Documents/X2RED
cp -n .env.example .env
open -e .env
```

在打开的 `.env` 中找到最后三行，改成：

```env
X2RED_MODEL_BASE_URL=https://open.bigmodel.cn/api/paas/v4
X2RED_MODEL_API_KEY=replace-with-your-bigmodel-api-key
X2RED_MODEL_NAME=glm-5.2
```

把 `replace-with-your-bigmodel-api-key` 替换成你在智谱开放平台创建的真实密钥。不要把 `.env` 提交到 GitHub，也不要截图分享密钥。

## 3. 重启 X2RED

先在正在运行服务的终端按 `Control + C`，然后运行：

```bash
cd /Users/EasyMaker/Documents/X2RED
./scripts/start.sh
```

## 4. 确认是否真的调用了模型

重新生成一篇草稿。配置成功时，生成过程会连续调用模型两次：第一次分析，第二次写作。

生成后的草稿溯源数据中，`generator` 会记录为：

```text
model-two-pass
```

并保存 `editorial_analysis`，其中包括推荐角度、候选标题、事实与不确定项。

如果仍显示 `structured-fallback`，说明模型请求失败或配置未生效。优先检查：

- `.env` 是否位于 X2RED 项目根目录；
- Base URL 是否为 `https://open.bigmodel.cn/api/paas/v4`；
- 模型名是否为 `glm-5.2`；
- API Key 是否属于通用开放平台；
- 修改配置后是否重启了 X2RED。

## 5. 使用成本提醒

每次点击“生成草稿”会产生两次模型请求。第一阶段使用较高推理强度做编辑分析，第二阶段使用中等推理强度写稿。不要对同一来源无意义地反复点击生成；需要微调措辞时，优先在编辑器中人工修改并保存新版本。
