(() => {
  const apiCall = window.api || (async (url, options = {}) => {
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
  });

  const state = { currentVariant: null, busy: false };

  function el(tag, className = "", text = "") {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text) node.textContent = text;
    return node;
  }

  function injectStyles() {
    if (document.getElementById("light-content-v10-style")) return;
    const style = document.createElement("style");
    style.id = "light-content-v10-style";
    style.textContent = `
.light-content-builder{margin:18px 0 4px;padding:18px;border:1px solid #d7d1c6;border-radius:18px;background:linear-gradient(145deg,#f4efe5,#ebe4d8)}.light-content-head{display:flex;align-items:flex-start;justify-content:space-between;gap:16px;margin-bottom:14px}.light-content-head h4{margin:3px 0 5px;font-size:18px}.light-content-head p{max-width:560px;margin:0;color:#6f685e;font-size:13px;line-height:1.55}.light-content-badge{padding:7px 10px;border-radius:999px;background:#28231f;color:#f5eee3;font-size:11px;font-weight:800;letter-spacing:.06em}.light-content-grid{display:grid;grid-template-columns:1fr 1fr;gap:10px}.light-content-grid label,.light-content-full{display:grid;gap:6px;color:#514b43;font-size:12px;font-weight:760}.light-content-grid select,.light-content-grid input,.light-content-full input,.light-content-full textarea{width:100%;border:1px solid #d4cdc1;border-radius:10px;background:#fffdf9;padding:10px 11px;color:#27231f;font:inherit}.light-content-full{margin-top:10px}.light-content-actions{display:flex;align-items:center;justify-content:space-between;gap:12px;margin-top:14px}.light-content-status{min-height:20px;color:#6c655d;font-size:12px}.light-content-status.ok{color:#17734b}.light-content-status.error{color:#b42318}.light-content-gallery{margin-top:18px}.light-content-gallery[hidden]{display:none}.light-content-gallery-head{display:flex;align-items:flex-end;justify-content:space-between;gap:16px;margin-bottom:12px}.light-content-gallery-head h4{margin:0;font-size:18px}.light-content-gallery-head p{margin:4px 0 0;color:#6b7280;font-size:12px}.light-content-poster-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:14px}.light-content-poster{margin:0;padding:8px;border:1px solid #e0ddd6;border-radius:14px;background:#fff;box-shadow:0 12px 30px #2c241915}.light-content-poster img{display:block;width:100%;aspect-ratio:3/5;object-fit:cover;border-radius:9px;background:#e9e1d3}.light-content-poster figcaption{padding:9px 3px 2px;color:#5f594f;font-size:12px;line-height:1.5}.light-content-poster details{margin-top:7px}.light-content-poster summary{cursor:pointer;color:#596579;font-size:11px}.light-content-poster pre{max-height:180px;overflow:auto;white-space:pre-wrap;color:#5c554c;font:11px/1.55 ui-monospace,SFMono-Regular,monospace}.light-series-chip{display:inline-flex;margin-left:7px;padding:3px 7px;border-radius:999px;background:#eee3cf;color:#72502a;font-size:10px;font-weight:800}@media(max-width:760px){.light-content-grid{grid-template-columns:1fr}.light-content-actions{align-items:stretch;flex-direction:column}.light-content-actions button{width:100%}}
`;
    document.head.appendChild(style);
  }

  function injectBuilder() {
    const form = document.getElementById("wechat-create-form");
    if (!form || document.getElementById("wechat-light-builder")) return;
    const section = el("section", "light-content-builder");
    section.id = "wechat-light-builder";
    section.innerHTML = `
      <div class="light-content-head">
        <div><span class="section-kicker">PHOTO + FEW WORDS</span><h4>轻内容图组</h4><p>同一来源可生成 3–6 张“照片/单一物件 + 少字”3:5 图。适合人生慰藉、中老年生活、节气时令、照片短句和一句短评。</p></div>
        <span class="light-content-badge">MINIMAL ZINE</span>
      </div>
      <div class="light-content-grid">
        <label>内容配方<select id="light-recipe"><option value="comfort">人生慰藉</option><option value="mature_life">中老年生活共鸣</option><option value="seasonal">节气与时令</option><option value="photo_quote">照片 + 一句话</option><option value="short_commentary">一句短评</option></select></label>
        <label>图片数量<select id="light-count"><option value="3">3 张</option><option value="4" selected>4 张</option><option value="5">5 张</option><option value="6">6 张</option></select></label>
      </div>
      <label id="light-seasonal-wrap" class="light-content-full" hidden>节气或时令主题<input id="light-seasonal-topic" maxlength="120" placeholder="例如：处暑、入伏吃什么、秋分早晚温差" /></label>
      <label class="light-content-full">目标读者<input id="light-audience" maxlength="500" placeholder="例如：工作压力大的城市读者；50 岁以上关注日常生活的人" /></label>
      <label class="light-content-full">语气<input id="light-tone" maxlength="300" value="安静、克制、有生活感" /></label>
      <div class="light-content-actions"><span id="light-content-status" class="light-content-status">会保存每张图的最终 Prompt；时令和饮食内容发布前仍需人工核对。</span><button id="light-content-generate" type="button" class="primary-action">生成轻内容图组</button></div>`;
    form.insertAdjacentElement("afterend", section);
    const recipe = section.querySelector("#light-recipe");
    recipe.addEventListener("change", () => {
      section.querySelector("#light-seasonal-wrap").hidden = recipe.value !== "seasonal";
    });
    section.querySelector("#light-content-generate").addEventListener("click", generateLightSeries);
  }

  function injectGallery() {
    const preview = document.querySelector(".platform-preview-panel");
    if (!preview || document.getElementById("wechat-light-gallery")) return;
    const gallery = el("section", "light-content-gallery");
    gallery.id = "wechat-light-gallery";
    gallery.hidden = true;
    preview.appendChild(gallery);
  }

  function status(text, kind = "") {
    const target = document.getElementById("light-content-status");
    if (!target) return;
    target.textContent = text;
    target.className = `light-content-status${kind ? ` ${kind}` : ""}`;
  }

  async function generateLightSeries() {
    if (state.busy) return;
    const sourceId = document.getElementById("wechat-source")?.value || "";
    if (!sourceId) {
      status("请先选择来源。", "error");
      return;
    }
    const button = document.getElementById("light-content-generate");
    state.busy = true;
    button.disabled = true;
    status("正在生成短文、图组故事板与极简杂志 Prompt…");
    try {
      const variant = await apiCall("/api/platforms/wechat/light/variants", {
        method: "POST",
        body: JSON.stringify({
          source_id: sourceId,
          draft_id: document.getElementById("wechat-draft")?.value || null,
          recipe: document.getElementById("light-recipe")?.value || "comfort",
          image_count: Number(document.getElementById("light-count")?.value || 4),
          seasonal_topic: document.getElementById("light-seasonal-topic")?.value || "",
          audience: document.getElementById("light-audience")?.value || "",
          tone: document.getElementById("light-tone")?.value || "",
          theme: document.getElementById("wechat-theme")?.value || "zen",
          author: document.getElementById("wechat-author")?.value || "",
        }),
      });
      status("故事板已生成，正在渲染 3:5 图组…");
      const rendered = await apiCall(`/api/platforms/variants/${encodeURIComponent(variant.id)}/render`, {
        method: "POST",
        body: JSON.stringify({ package: true }),
      });
      state.currentVariant = rendered.variant;
      renderGallery(rendered.variant);
      status(`已生成 ${Object.keys(rendered.files).filter((key) => key.startsWith("poster_")).length} 张图和发布包。`, "ok");
      document.dispatchEvent(new CustomEvent("x2red:wechat-refresh-request", { detail: { variantId: variant.id } }));
    } catch (error) {
      status(error.message || String(error), "error");
    } finally {
      state.busy = false;
      button.disabled = false;
    }
  }

  function parse(value, fallback = {}) {
    try { return JSON.parse(value || ""); } catch { return fallback; }
  }

  function renderGallery(variant) {
    const gallery = document.getElementById("wechat-light-gallery");
    if (!gallery) return;
    if (!variant || variant.format !== "light_series") {
      gallery.hidden = true;
      gallery.replaceChildren();
      return;
    }
    const files = parse(variant.output_paths_json, {});
    const metadata = parse(variant.metadata_json, {});
    const specs = Array.isArray(metadata.poster_specs) ? metadata.poster_specs : [];
    const posterKeys = Object.keys(files).filter((key) => /^poster_\d+$/.test(key)).sort();
    gallery.hidden = false;
    gallery.replaceChildren();
    const head = el("div", "light-content-gallery-head");
    const copy = el("div");
    copy.innerHTML = `<span class="section-kicker">LIGHT SERIES</span><h4>${escapeHtml(variant.title)}<span class="light-series-chip">${escapeHtml(metadata.recipe_label || "轻内容")}</span></h4><p>${escapeHtml(variant.summary || "")}</p>`;
    const download = el("a", "tool-button", "下载图组发布包");
    download.href = `/api/platforms/variants/${encodeURIComponent(variant.id)}/files/package`;
    download.target = "_blank";
    download.rel = "noreferrer";
    if (!files.package) download.hidden = true;
    head.append(copy, download);
    const grid = el("div", "light-content-poster-grid");
    posterKeys.forEach((key, index) => {
      const spec = specs[index] || {};
      const figure = el("figure", "light-content-poster");
      const image = document.createElement("img");
      image.src = `/api/platforms/variants/${encodeURIComponent(variant.id)}/files/${key}?v=${Date.now()}`;
      image.alt = spec.phrase || `轻内容海报 ${index + 1}`;
      const caption = el("figcaption", "", spec.phrase || `第 ${index + 1} 张`);
      const details = document.createElement("details");
      const summary = document.createElement("summary");
      summary.textContent = "查看生图 Prompt";
      const prompt = document.createElement("pre");
      prompt.textContent = spec.final_prompt || "Prompt 会在渲染后写入。";
      details.append(summary, prompt);
      figure.append(image, caption, details);
      grid.appendChild(figure);
    });
    gallery.append(head, grid);
  }

  function escapeHtml(value) {
    return String(value || "").replace(/[&<>'"]/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;" })[char]);
  }

  document.addEventListener("x2red:wechat-variant-selected", (event) => {
    state.currentVariant = event.detail?.variant || null;
    renderGallery(state.currentVariant);
  });

  function boot() {
    injectStyles();
    injectBuilder();
    injectGallery();
    const observer = new MutationObserver(() => {
      injectBuilder();
      injectGallery();
    });
    observer.observe(document.body, { childList: true, subtree: true });
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot, { once: true });
  else boot();
})();
