(() => {
  const state = {
    items: [],
    category: "mature_life",
    busy: false,
    providers: [],
  };

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
    if (document.getElementById("materials-v11-style")) return;
    const style = document.createElement("style");
    style.id = "materials-v11-style";
    style.textContent = `
.material-shell{display:grid;grid-template-columns:minmax(310px,390px) 1fr;gap:18px;align-items:start}.material-panel{border:1px solid #e1e5ee;border-radius:22px;background:#fff;box-shadow:0 18px 44px #1720330b;overflow:hidden}.material-panel-head{padding:20px;border-bottom:1px solid #edf0f5}.material-panel-head h3{margin:4px 0 0}.material-panel-body{padding:18px}.material-form{display:grid;gap:12px}.material-field{display:grid;gap:6px;color:#50596a;font-size:12px;font-weight:760}.material-field input,.material-field select,.material-field textarea{width:100%;border:1px solid #dce1eb;border-radius:11px;background:#fbfcff;padding:11px 12px;font:inherit}.material-actions{display:flex;gap:8px;flex-wrap:wrap}.material-actions button{min-height:42px;padding:0 14px;border:1px solid #dce1eb;border-radius:11px;background:#fff;color:#354055;font-weight:820;cursor:pointer}.material-actions button.primary{border-color:#4057eb;background:#4057eb;color:#fff}.material-actions button:disabled{opacity:.5}.material-policy{margin-top:14px;padding:12px;border-radius:12px;background:#f4f6fa;color:#677083;font-size:11px;line-height:1.65}.material-status{min-height:42px;margin-top:12px;padding:10px 12px;border-radius:11px;background:#f4f6fa;color:#616b7e;font-size:11px;line-height:1.55}.material-status.ok{background:#eaf8f0;color:#19724c}.material-status.error{background:#fff0f0;color:#b42318}.material-toolbar{display:flex;align-items:center;justify-content:space-between;gap:12px}.material-count{padding:5px 9px;border-radius:999px;background:#eef0ff;color:#4353d4;font-size:10px;font-weight:850}.material-list{display:grid;gap:12px}.material-empty{display:grid;place-items:center;min-height:430px;padding:40px;color:#7b8494;text-align:center}.material-card{display:grid;grid-template-columns:112px 1fr auto;gap:14px;padding:14px;border:1px solid #e3e6ed;border-radius:16px;background:#fafbfe}.material-thumb{width:112px;height:82px;border-radius:11px;object-fit:cover;background:linear-gradient(135deg,#dfe4ef,#f4f6fa)}.material-copy{min-width:0}.material-copy h4{margin:0 0 6px;font-size:14px;line-height:1.35}.material-copy p{margin:0;color:#6c7586;font-size:11px;line-height:1.55;display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;overflow:hidden}.material-meta{display:flex;gap:7px;flex-wrap:wrap;margin-top:8px;color:#8a91a0;font-size:9px}.material-fit{color:#2b6e50;font-weight:800}.material-provider{color:#4057eb;font-weight:820}.material-import{align-self:center;min-width:76px;height:36px;border:1px solid #d9deea;border-radius:10px;background:#fff;color:#394458;font-size:10px;font-weight:820;cursor:pointer}.material-import:disabled{opacity:.5}.provider-grid{display:grid;gap:7px;margin:4px 0 14px}.provider-row{display:flex;align-items:center;justify-content:space-between;gap:10px;padding:9px 10px;border:1px solid #e4e7ee;border-radius:10px;background:#fafbfe;font-size:10px}.provider-row strong{font-size:10px}.provider-state{padding:3px 7px;border-radius:999px;background:#f1f3f7;color:#7c8492;font-weight:800}.provider-state.on{background:#e8f7ef;color:#19724c}.material-supplement{margin-top:14px;border:1px solid #e6e9ef;border-radius:12px;padding:0 12px}.material-supplement summary{padding:12px 0;cursor:pointer;font-size:11px;font-weight:820;color:#596477}.material-supplement .material-form{padding:0 0 12px}.attempts{display:flex;gap:6px;flex-wrap:wrap;margin-top:8px}.attempt-chip{padding:3px 7px;border-radius:999px;background:#edf0f5;color:#687284}.attempt-chip.ok{background:#e7f7ef;color:#19724c}.attempt-chip.failed{background:#fff0f0;color:#b42318}@media(max-width:980px){.material-shell{grid-template-columns:1fr}.material-card{grid-template-columns:90px 1fr}.material-thumb{width:90px;height:72px}.material-import{grid-column:1/-1}}
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
        <span class="section-kicker">MARKET SEARCH + PUBLIC PAGE EXTRACTION</span>
        <h2>简中生活原料库</h2>
        <p>主入口改为百度与商业搜索 API；收录时先抓公开 HTML，无正文再启用无登录、无 Cookie 的浏览器渲染。</p>
      </section>
      <section class="material-shell">
        <aside class="material-panel">
          <div class="material-panel-head"><span class="section-kicker">SEARCH ROUTING</span><h3>搜索简中互联网</h3></div>
          <div class="material-panel-body">
            <div id="material-provider-grid" class="provider-grid"><div class="provider-row"><span>正在读取供应商配置</span><span class="provider-state">…</span></div></div>
            <form id="material-discover-form" class="material-form">
              <label class="material-field">内容用途
                <select id="material-category">
                  <option value="mature_life">中老年生活</option>
                  <option value="comfort">人生慰藉</option>
                  <option value="seasonal">节气时令</option>
                  <option value="photo_quote">照片叙事</option>
                  <option value="short_commentary">一句短评</option>
                </select>
              </label>
              <label class="material-field">搜索供应商
                <select id="material-provider">
                  <option value="auto">自动切换：百度优先</option>
                  <option value="serpapi_baidu">SerpApi · 百度</option>
                  <option value="dataforseo_baidu">DataForSEO · 百度</option>
                  <option value="tavily">Tavily · China</option>
                  <option value="brave">Brave · zh-CN</option>
                  <option value="gdelt">GDELT 中文新闻兜底</option>
                </select>
              </label>
              <label class="material-field">主题或关键词
                <input id="material-query" maxlength="300" placeholder="例如：退休后的社区生活、照顾父母后的疲惫" />
              </label>
              <label class="material-field">时间范围
                <select id="material-timespan"><option value="24h">24 小时</option><option value="7d" selected>7 天</option><option value="30d">30 天</option><option value="90d">90 天</option></select>
              </label>
              <div class="material-actions"><button id="material-discover" class="primary" type="submit">搜索简中互联网</button></div>
            </form>
            <hr style="border:0;border-top:1px solid #eceff4;margin:18px 0">
            <form id="material-direct-form" class="material-form">
              <label class="material-field">直接收录公开文章
                <input id="material-direct-url" type="url" maxlength="2000" placeholder="粘贴公开网页地址" />
              </label>
              <label class="material-field">我的用途说明
                <textarea id="material-note" rows="3" maxlength="6000" placeholder="为什么想写、准备提取哪类生活经验"></textarea>
              </label>
              <div class="material-actions"><button type="submit">浏览器检查并收录</button></div>
            </form>
            <details class="material-supplement">
              <summary>RSS / Atom / Sitemap（补充入口）</summary>
              <form id="material-feed-form" class="material-form">
                <label class="material-field">公开订阅或站点地图地址
                  <input id="material-feed-url" type="url" maxlength="2000" placeholder="https://example.com/feed.xml" />
                </label>
                <div class="material-actions"><button type="submit">读取补充源</button></div>
              </form>
            </details>
            <div class="material-policy">搜索 API 负责发现，浏览器只打开无需登录的公开页面。不会破解验证码、绕过付费墙或复用个人登录态。收录内容仍保留原 URL、站点、作者、采集方式和有限引用状态。</div>
            <div id="material-status" class="material-status">正在检查可用搜索供应商。</div>
          </div>
        </aside>
        <section class="material-panel">
          <div class="material-panel-head material-toolbar"><div><span class="section-kicker">CANDIDATES</span><h3>候选原料</h3></div><span id="material-count" class="material-count">0 条</span></div>
          <div class="material-panel-body"><div id="material-list" class="material-list"><div class="material-empty">还没有候选。<br>配置任一商业搜索 Key 后即可直接搜索；未配置时自动使用 GDELT 兜底。</div></div></div>
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

  function renderProviders() {
    const grid = document.getElementById("material-provider-grid");
    if (!grid) return;
    grid.innerHTML = state.providers.map((item) => `
      <div class="provider-row" title="${escapeHtml(item.description)}">
        <strong>${escapeHtml(item.label)}</strong>
        <span class="provider-state ${item.configured ? "on" : ""}">${item.configured ? "可用" : "未配置"}</span>
      </div>`).join("");
  }

  async function loadProviders() {
    try {
      const data = await api("/api/materials/providers");
      state.providers = data.providers || [];
      renderProviders();
      const usable = state.providers.filter((item) => item.configured).map((item) => item.label);
      setStatus(`可用供应商：${usable.join("、") || "无"}。动态公开页浏览器回退：${data.browser_fallback ? "已开启" : "已关闭"}。`, "ok");
    } catch (error) {
      setStatus(error.message, "error");
    }
  }

  function renderItems() {
    const list = document.getElementById("material-list");
    const count = document.getElementById("material-count");
    if (!list || !count) return;
    count.textContent = `${state.items.length} 条`;
    if (!state.items.length) {
      list.innerHTML = '<div class="material-empty">没有找到候选。换一个更具体的中文主题，或切换百度搜索供应商。</div>';
      return;
    }
    list.innerHTML = state.items.map((item, index) => `
      <article class="material-card">
        ${item.image_url ? `<img class="material-thumb" src="${escapeHtml(item.image_url)}" alt="" referrerpolicy="no-referrer">` : '<div class="material-thumb"></div>'}
        <div class="material-copy">
          <h4>${escapeHtml(item.title || item.site || "未命名材料")}</h4>
          <p>${escapeHtml(item.summary || "点击收录后，将打开公开页面并提取正文。")}</p>
          <div class="material-meta"><span>${escapeHtml(item.site)}</span><span>${escapeHtml(item.published_at)}</span><span class="material-provider">${escapeHtml(item.discovery_source)}</span><span class="material-fit">匹配 ${Math.round(Number(item.fit_score || 0) * 100)}%</span></div>
        </div>
        <button class="material-import" type="button" data-index="${index}">收录</button>
      </article>`).join("");
    list.querySelectorAll(".material-import").forEach((button) => button.addEventListener("click", () => importItem(Number(button.dataset.index), button)));
  }

  async function discover(event) {
    event.preventDefault();
    if (state.busy) return;
    state.busy = true;
    const button = document.getElementById("material-discover");
    if (button) button.disabled = true;
    state.category = document.getElementById("material-category")?.value || "mature_life";
    const provider = document.getElementById("material-provider")?.value || "auto";
    setStatus("正在调用搜索供应商，只读取搜索结果；点击收录后才打开正文。", "");
    try {
      const data = await api("/api/materials/discover", {
        method: "POST",
        body: JSON.stringify({
          category: state.category,
          provider,
          query: document.getElementById("material-query")?.value || "",
          timespan: document.getElementById("material-timespan")?.value || "7d",
          max_records: 40,
        }),
      });
      state.items = data.items || [];
      renderItems();
      setStatus(`由 ${data.provider || provider} 找到 ${state.items.length} 条候选。`, "ok", data.attempts || []);
    } catch (error) { setStatus(error.message, "error"); }
    finally { state.busy = false; if (button) button.disabled = false; }
  }

  async function discoverFeed(event) {
    event.preventDefault();
    const url = document.getElementById("material-feed-url")?.value.trim();
    if (!url || state.busy) return;
    state.busy = true;
    state.category = document.getElementById("material-category")?.value || "mature_life";
    setStatus("正在读取补充订阅源。", "");
    try {
      const data = await api("/api/materials/discover-feed", { method: "POST", body: JSON.stringify({ url, category: state.category, max_records: 60 }) });
      state.items = data.items || [];
      renderItems();
      setStatus(`补充源中发现 ${state.items.length} 条候选。`, "ok");
    } catch (error) { setStatus(error.message, "error"); }
    finally { state.busy = false; }
  }

  async function directImport(event) {
    event.preventDefault();
    const url = document.getElementById("material-direct-url")?.value.trim();
    if (!url || state.busy) return;
    state.busy = true;
    state.category = document.getElementById("material-category")?.value || "mature_life";
    setStatus("正在提取公开 HTML；正文不足时自动启用干净浏览器渲染。", "");
    try {
      const source = await api("/api/materials/import", { method: "POST", body: JSON.stringify({ url, category: state.category, editor_note: document.getElementById("material-note")?.value || "" }) });
      setStatus(`已收录到来源箱：${source.author_name || source.author_handle || source.canonical_url}`, "ok");
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
    setStatus(`正在打开公开页面：${item.title || item.url}`, "");
    try {
      const source = await api("/api/materials/import", { method: "POST", body: JSON.stringify({ url: item.url, category: state.category, editor_note: `原料库发现：${item.title || ""}；搜索源：${item.discovery_source || ""}` }) });
      button.textContent = "已收录";
      setStatus(`已进入来源箱：${source.canonical_url}`, "ok");
    } catch (error) { button.disabled = false; button.textContent = "重试"; setStatus(error.message, "error"); }
    finally { state.busy = false; }
  }

  function bind() {
    document.getElementById("material-discover-form")?.addEventListener("submit", discover);
    document.getElementById("material-feed-form")?.addEventListener("submit", discoverFeed);
    document.getElementById("material-direct-form")?.addEventListener("submit", directImport);
  }

  function boot() {
    injectStyles(); injectNav(); injectView(); bind(); loadProviders();
    const observer = new MutationObserver(() => { injectNav(); injectView(); });
    observer.observe(document.body, { childList: true, subtree: true });
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot, { once: true }); else boot();
})();
