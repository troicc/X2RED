(() => {
  const state = { items: [], category: "mature_life", busy: false };

  async function api(url, options = {}) {
    const response = await fetch(url, {
      headers: { "Content-Type": "application/json", ...(options.headers || {}) },
      ...options,
    });
    if (!response.ok) {
      let message = `请求失败：${response.status}`;
      try { message = (await response.json()).detail || message; } catch {}
      throw new Error(message);
    }
    return response.status === 204 ? null : response.json();
  }

  function escapeHtml(value) {
    return String(value || "").replace(/[&<>'"]/g, (char) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;",
    })[char]);
  }

  function injectStyles() {
    if (document.getElementById("materials-v13-style")) return;
    const style = document.createElement("style");
    style.id = "materials-v13-style";
    style.textContent = `
.material-shell{display:grid;grid-template-columns:minmax(330px,410px) 1fr;gap:18px;align-items:start}.material-panel{border:1px solid #e1e5ee;border-radius:22px;background:#fff;box-shadow:0 18px 44px #1720330b;overflow:hidden}.material-panel-head{padding:20px;border-bottom:1px solid #edf0f5}.material-panel-head h3{margin:4px 0 0}.material-panel-body{padding:18px}.material-form{display:grid;gap:12px}.material-field{display:grid;gap:6px;color:#50596a;font-size:12px;font-weight:760}.material-field input,.material-field select,.material-field textarea{width:100%;border:1px solid #dce1eb;border-radius:11px;background:#fbfcff;padding:11px 12px;font:inherit}.material-actions{display:flex;gap:8px;flex-wrap:wrap}.material-actions button{min-height:42px;padding:0 14px;border:1px solid #dce1eb;border-radius:11px;background:#fff;color:#354055;font-weight:820;cursor:pointer}.material-actions button.primary{border-color:#4057eb;background:#4057eb;color:#fff}.material-actions button:disabled{opacity:.5}.material-policy{margin-top:14px;padding:12px;border-radius:12px;background:#fff8e7;color:#72551a;font-size:11px;line-height:1.65}.material-status{min-height:42px;margin-top:12px;padding:10px 12px;border-radius:11px;background:#f4f6fa;color:#616b7e;font-size:11px;line-height:1.55}.material-status.ok{background:#eaf8f0;color:#19724c}.material-status.error{background:#fff0f0;color:#b42318}.material-toolbar{display:flex;align-items:center;justify-content:space-between;gap:12px}.material-count{padding:5px 9px;border-radius:999px;background:#eef0ff;color:#4353d4;font-size:10px;font-weight:850}.material-list{display:grid;gap:12px}.material-empty{display:grid;place-items:center;min-height:430px;padding:40px;color:#7b8494;text-align:center}.material-card{display:grid;grid-template-columns:112px 1fr auto;gap:14px;padding:14px;border:1px solid #e3e6ed;border-radius:16px;background:#fafbfe}.material-thumb{width:112px;height:82px;border-radius:11px;object-fit:cover;background:linear-gradient(135deg,#dfe4ef,#f4f6fa)}.material-copy{min-width:0}.material-copy h4{margin:0 0 6px;font-size:14px;line-height:1.35}.material-copy p{margin:0;color:#6c7586;font-size:11px;line-height:1.55;display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;overflow:hidden}.material-meta{display:flex;gap:7px;flex-wrap:wrap;margin-top:8px;color:#8a91a0;font-size:9px}.material-provider{color:#4057eb;font-weight:820}.material-fit{color:#2b6e50;font-weight:800}.material-import{align-self:center;min-width:76px;height:36px;border:1px solid #d9deea;border-radius:10px;background:#fff;color:#394458;font-size:10px;font-weight:820;cursor:pointer}.platform-grid{display:grid;grid-template-columns:1fr 1fr;gap:7px;margin-bottom:14px}.platform-row{padding:9px 10px;border:1px solid #e4e7ee;border-radius:10px;background:#fafbfe;font-size:10px}.platform-row strong{display:block}.platform-state{font-size:9px;color:#8a91a0}.platform-state.on{color:#19724c}.attempts{display:flex;gap:6px;flex-wrap:wrap;margin-top:8px}.attempt-chip{padding:3px 7px;border-radius:999px;background:#edf0f5;color:#687284}.attempt-chip.ok{background:#e7f7ef;color:#19724c}.attempt-chip.failed{background:#fff0f0;color:#b42318}@media(max-width:980px){.material-shell{grid-template-columns:1fr}.material-card{grid-template-columns:90px 1fr}.material-thumb{width:90px;height:72px}.material-import{grid-column:1/-1}}
`;
    document.head.appendChild(style);
  }

  function setView() {
    document.querySelectorAll(".app-view").forEach((view) => view.classList.remove("active"));
    document.querySelectorAll(".nav-item").forEach((item) => item.classList.remove("active"));
    document.getElementById("materials-view")?.classList.add("active");
    document.getElementById("materials-nav")?.classList.add("active");
    const title = document.getElementById("page-title");
    if (title) title.textContent = "原料库";
  }

  function injectNav() {
    const nav = document.querySelector(".primary-nav");
    if (!nav || document.getElementById("materials-nav")) return;
    const button = document.createElement("button");
    button.id = "materials-nav";
    button.className = "nav-item";
    button.type = "button";
    button.innerHTML = '<span class="nav-icon">⌕</span><span>原料库</span>';
    button.addEventListener("click", setView);
    const settings = nav.querySelector('[data-view="settings-view"]');
    nav.insertBefore(button, settings || null);
  }

  function injectView() {
    const stack = document.querySelector(".view-stack");
    if (!stack || document.getElementById("materials-view")) return;
    const section = document.createElement("section");
    section.id = "materials-view";
    section.className = "app-view";
    section.innerHTML = `
      <section class="page-intro">
        <span class="section-kicker">MEDIACRAWLER · LOCAL CHROME CDP</span>
        <h2>简中平台原料库</h2>
        <p>直接运行 MediaCrawler，复用本机 Chrome 登录态，从小红书、抖音、快手、B站、微博、贴吧和知乎搜索公开内容。</p>
      </section>
      <section class="material-shell">
        <aside class="material-panel">
          <div class="material-panel-head"><span class="section-kicker">PLATFORM CRAWLER</span><h3>MediaCrawler 搜索</h3></div>
          <div class="material-panel-body">
            <div id="material-platform-grid" class="platform-grid"><div class="platform-row">正在检查 MediaCrawler</div></div>
            <form id="material-discover-form" class="material-form">
              <label class="material-field">内容用途
                <select id="material-category">
                  <option value="mature_life">中老年生活</option><option value="comfort">人生慰藉</option><option value="seasonal">节气时令</option><option value="photo_quote">照片叙事</option><option value="short_commentary">一句短评</option>
                </select>
              </label>
              <label class="material-field">平台
                <select id="material-platform"><option value="xhs">小红书</option><option value="dy">抖音</option><option value="ks">快手</option><option value="bili">哔哩哔哩</option><option value="wb">微博</option><option value="tieba">百度贴吧</option><option value="zhihu">知乎</option></select>
              </label>
              <label class="material-field">登录方式
                <select id="material-login-type"><option value="qrcode">二维码 / 已有浏览器登录态</option><option value="phone">手机号</option><option value="cookie">Cookie</option></select>
              </label>
              <label class="material-field">主题或关键词<input id="material-query" maxlength="300" placeholder="例如：退休后的社区生活" /></label>
              <div class="material-actions"><button id="material-discover" class="primary" type="submit">运行 MediaCrawler</button></div>
            </form>
            <div class="material-policy">先在 Chrome 打开 chrome://inspect/#remote-debugging 并启用远程调试。搜索会打开或复用真实平台页面，首次使用可能需要扫码或完成人机验证。仅限合法、低频、研究用途。</div>
            <hr style="border:0;border-top:1px solid #eceff4;margin:18px 0">
            <form id="material-direct-form" class="material-form">
              <label class="material-field">普通公开网页收录方式<select id="material-extractor"><option value="direct">HTTP + Trafilatura</option><option value="playwright">本地 Playwright</option></select></label>
              <label class="material-field">网页地址<input id="material-direct-url" type="url" maxlength="2000" placeholder="仅用于普通公开文章，不用于平台搜索" /></label>
              <label class="material-field">用途说明<textarea id="material-note" rows="3" maxlength="6000"></textarea></label>
              <div class="material-actions"><button type="submit">收录普通网页</button></div>
            </form>
            <div id="material-status" class="material-status">正在检查 MediaCrawler 和 Chrome CDP。</div>
          </div>
        </aside>
        <section class="material-panel">
          <div class="material-panel-head material-toolbar"><div><span class="section-kicker">CRAWLER RESULTS</span><h3>候选原料</h3></div><span id="material-count" class="material-count">0 条</span></div>
          <div class="material-panel-body"><div id="material-list" class="material-list"><div class="material-empty">选择平台并运行 MediaCrawler。</div></div></div>
        </section>
      </section>`;
    const settings = document.getElementById("settings-view");
    stack.insertBefore(section, settings || null);
  }

  function setStatus(message, type = "", attempts = []) {
    const node = document.getElementById("material-status");
    if (!node) return;
    node.className = `material-status ${type}`.trim();
    const chips = attempts.length ? `<div class="attempts">${attempts.map((item) => `<span class="attempt-chip ${escapeHtml(item.status)}">${escapeHtml(item.provider)} · ${escapeHtml(item.status)}</span>`).join("")}</div>` : "";
    node.innerHTML = `${escapeHtml(message)}${chips}`;
  }

  async function loadProviders() {
    try {
      const data = await api("/api/materials/providers");
      const grid = document.getElementById("material-platform-grid");
      if (grid) grid.innerHTML = (data.platforms || []).map((item) => `<div class="platform-row" title="${escapeHtml(item.description)}"><strong>${escapeHtml(item.label)}</strong><span class="platform-state ${item.ready ? "on" : ""}">${item.ready ? "CDP 可用" : item.configured ? "等待 Chrome CDP" : "未安装"}</span></div>`).join("");
      const platform = document.getElementById("material-platform");
      const login = document.getElementById("material-login-type");
      if (platform && data.default_platform) platform.value = data.default_platform;
      if (login && data.default_login_type) login.value = data.default_login_type;
      setStatus(data.installed ? (data.cdp_ready ? "MediaCrawler 与 Chrome CDP 已就绪。" : `MediaCrawler 已安装，但 127.0.0.1:${data.cdp_port} 尚未连接。`) : "MediaCrawler 尚未安装，请重新执行 ./scripts/start.sh。", data.installed && data.cdp_ready ? "ok" : "error");
    } catch (error) { setStatus(error.message, "error"); }
  }

  function renderItems() {
    const list = document.getElementById("material-list");
    const count = document.getElementById("material-count");
    if (!list || !count) return;
    count.textContent = `${state.items.length} 条`;
    if (!state.items.length) { list.innerHTML = '<div class="material-empty">MediaCrawler 没有返回候选。检查平台登录态、关键词和终端日志。</div>'; return; }
    list.innerHTML = state.items.map((item, index) => `<article class="material-card">${item.image_url ? `<img class="material-thumb" src="${escapeHtml(item.image_url)}" alt="" referrerpolicy="no-referrer">` : '<div class="material-thumb"></div>'}<div class="material-copy"><h4>${escapeHtml(item.title || "未命名内容")}</h4><p>${escapeHtml(item.summary)}</p><div class="material-meta"><span>${escapeHtml(item.site)}</span><span>${escapeHtml(item.published_at)}</span><span class="material-provider">${escapeHtml(item.discovery_source)}</span><span class="material-fit">匹配 ${Math.round(Number(item.fit_score || 0) * 100)}%</span></div></div><button class="material-import" type="button" data-index="${index}">收录</button></article>`).join("");
    list.querySelectorAll(".material-import").forEach((button) => button.addEventListener("click", () => importItem(Number(button.dataset.index), button)));
  }

  async function discover(event) {
    event.preventDefault();
    if (state.busy) return;
    state.busy = true;
    const button = document.getElementById("material-discover");
    if (button) button.disabled = true;
    state.category = document.getElementById("material-category")?.value || "mature_life";
    const platform = document.getElementById("material-platform")?.value || "xhs";
    setStatus(`正在运行 MediaCrawler：${platform}。请留意 Chrome 窗口。`);
    try {
      const data = await api("/api/materials/discover", { method: "POST", body: JSON.stringify({ category: state.category, platform, login_type: document.getElementById("material-login-type")?.value || "qrcode", query: document.getElementById("material-query")?.value || "", max_records: 30 }) });
      state.items = data.items || [];
      renderItems();
      setStatus(`MediaCrawler 返回 ${state.items.length} 条候选。`, "ok", data.attempts || []);
    } catch (error) { setStatus(error.message, "error"); }
    finally { state.busy = false; if (button) button.disabled = false; }
  }

  async function directImport(event) {
    event.preventDefault();
    const url = document.getElementById("material-direct-url")?.value.trim();
    if (!url || state.busy) return;
    state.busy = true;
    state.category = document.getElementById("material-category")?.value || "mature_life";
    try {
      const source = await api("/api/materials/import", { method: "POST", body: JSON.stringify({ url, category: state.category, extractor: document.getElementById("material-extractor")?.value || "direct", editor_note: document.getElementById("material-note")?.value || "" }) });
      setStatus(`已收录：${source.canonical_url}`, "ok");
      document.getElementById("material-direct-url").value = "";
    } catch (error) { setStatus(error.message, "error"); }
    finally { state.busy = false; }
  }

  async function importItem(index, button) {
    const item = state.items[index];
    if (!item || state.busy) return;
    state.busy = true;
    button.disabled = true;
    button.textContent = "收录中";
    try {
      const source = await api("/api/materials/import", { method: "POST", body: JSON.stringify({ category: state.category, candidate: item, editor_note: `MediaCrawler 发现：${item.title || ""}` }) });
      button.textContent = "已收录";
      setStatus(`已进入来源箱：${source.canonical_url}`, "ok");
    } catch (error) { button.disabled = false; button.textContent = "重试"; setStatus(error.message, "error"); }
    finally { state.busy = false; }
  }

  function boot() {
    injectStyles(); injectNav(); injectView();
    document.getElementById("material-discover-form")?.addEventListener("submit", discover);
    document.getElementById("material-direct-form")?.addEventListener("submit", directImport);
    loadProviders();
    new MutationObserver(() => { injectNav(); injectView(); }).observe(document.body, { childList: true, subtree: true });
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot, { once: true }); else boot();
})();
