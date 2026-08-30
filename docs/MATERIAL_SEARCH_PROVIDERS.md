# 原料库：MediaCrawler 接入

原料库的简中平台发现只使用 [NanmiCoder/MediaCrawler](https://github.com/NanmiCoder/MediaCrawler) 的实际运行方式，不再把搜索 API 聚合器作为自动发现链。

## 固定上游版本

X2RED 固定使用 MediaCrawler 提交：

`1779dde9725f6b7ef42e29022c0054b3e678f1af`

`./scripts/start.sh` 会调用 `scripts/setup-mediacrawler.sh`，把该版本克隆到被 Git 忽略的 `.vendor/MediaCrawler`，并在独立虚拟环境中安装依赖。X2RED 不复制或修改 MediaCrawler 源码。

MediaCrawler 使用 NON-COMMERCIAL LEARNING LICENSE 1.1。该能力仅限学习、研究、低频采集和人工有限引用，不得用于商业用途、大规模抓取或干扰平台运行。

## 工作方式

1. X2RED 检查 `.vendor/MediaCrawler` 和其独立 Python 环境。
2. 用户在本机 Chrome 开启远程调试。
3. X2RED 通过独立运行器设置 MediaCrawler 的 CDP 模式。
4. MediaCrawler 复用真实 Chrome 的 Cookie、扩展和登录状态。
5. MediaCrawler 按平台执行 `search`，保存 JSONL。
6. X2RED 读取 JSONL、统一字段并展示候选。
7. 用户点击“收录”后，候选正文、指标、图片地址、来源和原始快照进入来源箱。

支持平台：

- 小红书 `xhs`
- 抖音 `dy`
- 快手 `ks`
- 哔哩哔哩 `bili`
- 微博 `wb`
- 百度贴吧 `tieba`
- 知乎 `zhihu`

## Chrome CDP

MediaCrawler 默认连接用户已经打开的 Chrome：

1. 打开 `chrome://inspect/#remote-debugging`。
2. 启用 **Allow remote debugging for this browser instance**。
3. 确认页面显示 `127.0.0.1:9222`。
4. 保持 Chrome 运行，再从 X2RED 原料库执行搜索。

首次访问某个平台时，MediaCrawler 可能要求扫码登录、手机号验证或完成滑块。X2RED 不破解验证码，也不绕过平台验证。

## 配置

```env
X2RED_MATERIAL_SEARCH_PROVIDER=mediacrawler
X2RED_MEDIACRAWLER_ROOT=./.vendor/MediaCrawler
X2RED_MEDIACRAWLER_REVISION=1779dde9725f6b7ef42e29022c0054b3e678f1af
X2RED_MEDIACRAWLER_PLATFORM=xhs
X2RED_MEDIACRAWLER_LOGIN_TYPE=qrcode
X2RED_MEDIACRAWLER_CONNECT_EXISTING=true
X2RED_MEDIACRAWLER_CDP_PORT=9222
X2RED_MEDIACRAWLER_TIMEOUT_SECONDS=600
X2RED_MEDIACRAWLER_MAX_RESULTS=30
```

跳过自动安装：

```bash
X2RED_SKIP_MEDIACRAWLER_INSTALL=1 ./scripts/start.sh
```

手工安装或修复：

```bash
sh scripts/setup-mediacrawler.sh .venv/bin/python
```

## 数据边界

- 搜索默认关闭评论、二级评论、媒体下载和高并发。
- 默认并发为 1，抓取间隔至少 2 秒。
- Cookie、`xsec_token`、`sec_uid` 等敏感运行字段不会进入浏览器候选数据。
- 收录项标记为 `limited_quote`，发布前必须人工复核版权、隐私和平台条款。
- 普通公开网页的手工收录仍可选择本地 HTTP + Trafilatura 或本地 Playwright；它不参与平台搜索。
