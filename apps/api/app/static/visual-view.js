import { renderCandidateView } from "./candidate-view.js?v=18";
import { renderPromptView } from "./prompt-view.js?v=18";

function element(tag, className = "", text = "") {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text) node.textContent = text;
  return node;
}

function parseObject(value) {
  try {
    const parsed = JSON.parse(value || "{}");
    return parsed && typeof parsed === "object" && !Array.isArray(parsed) ? parsed : {};
  } catch {
    return {};
  }
}

function variantMetadata(variant) {
  return parseObject(variant?.metadata_json);
}

function variantOutputs(variant) {
  return parseObject(variant?.output_paths_json);
}

function isLightVariant(variant) {
  return variant?.format === "light_series";
}

function visualUnits(variant) {
  const metadata = variantMetadata(variant);
  if (isLightVariant(variant)) {
    return (Array.isArray(metadata.poster_specs) ? metadata.poster_specs : []).map((item, index) => ({
      ...item,
      page: Number(item.page || index + 1),
      label: item.phrase || `第 ${index + 1} 页`,
    }));
  }
  return (Array.isArray(metadata.visual_prompts) ? metadata.visual_prompts : []).map((item, index) => ({
    ...item,
    page: index + 1,
    label: item.label || item.slot_id || `配图 ${index + 1}`,
  }));
}

function injectNavigation() {
  const nav = document.querySelector(".primary-nav");
  if (!nav || nav.querySelector('[data-view="visual-workflow-view"]')) return;
  const publish = nav.querySelector('[data-view="publish-view"]');
  const button = element("button", "nav-item");
  button.type = "button";
  button.dataset.view = "visual-workflow-view";
  button.innerHTML = '<span class="nav-icon" aria-hidden="true"></span><span>视觉任务</span>';
  button.addEventListener("click", () => window.setView?.("visual-workflow-view"));
  nav.insertBefore(button, publish);
}

function injectView() {
  const stack = document.querySelector(".view-stack");
  if (!stack || document.getElementById("visual-workflow-view")) return null;
  const view = element("section", "app-view visual-workflow-view");
  view.id = "visual-workflow-view";
  view.innerHTML = `
    <section class="page-intro studio-intro">
      <span class="section-kicker">VISUAL WORKFLOW</span>
      <h2 tabindex="-1">视觉任务</h2>
      <p>集中查看系列、Prompt 溯源、候选审核和回传状态；原工作台的编辑入口继续保留。</p>
    </section>
    <section class="visual-workflow-layout">
      <aside class="surface visual-series-rail" aria-labelledby="visual-series-title">
        <div class="creative-panel-head"><div><span class="section-kicker">SERIES</span><h3 id="visual-series-title">系列概览</h3></div><button id="visual-refresh" class="secondary-action" type="button">刷新</button></div>
        <div id="visual-series-list" class="visual-series-list"></div>
      </aside>
      <section class="visual-workspace">
        <div id="visual-workflow-status" class="inline-status" role="status" aria-live="polite"></div>
        <section id="visual-series-overview" class="surface visual-series-overview"></section>
        <section class="surface visual-page-workspace">
          <div class="creative-panel-head"><div><span class="section-kicker">PAGE / SLOT</span><h3>逐页视觉检查</h3></div><button id="visual-open-origin" class="secondary-action" type="button">回到公众号工作台</button></div>
          <div id="visual-page-tabs" class="visual-page-tabs" role="tablist" aria-label="视觉页面或配图槽位"></div>
          <section class="visual-upload-panel" aria-labelledby="visual-upload-title">
            <div><h4 id="visual-upload-title">批量上传</h4><p id="visual-upload-help">Minimal Zine 当前页可一次上传 1–4 张候选；公众号长文可按槽位顺序批量回传。</p></div>
            <form id="visual-upload-form" class="visual-upload-form">
              <label class="secondary-action visual-file-picker">选择图片<input id="visual-upload-files" type="file" accept="image/png,image/jpeg,image/webp" multiple /></label>
              <span id="visual-upload-selection">尚未选择文件</span>
              <button class="primary-action" type="submit">上传并刷新状态</button>
            </form>
          </section>
          <div id="visual-prompt-host"></div>
          <div id="visual-candidate-host"></div>
        </section>
      </section>
    </section>`;
  const publish = document.getElementById("publish-view");
  stack.insertBefore(view, publish || null);
  return view;
}

function variantTitle(variant) {
  const kind = isLightVariant(variant) ? "轻内容图组" : "公众号长文";
  return `${variant.title || "未命名"} · ${kind} v${variant.version}`;
}

function selectedCandidateScore(metadata) {
  const lifecycle = metadata.image_candidate_lifecycle || {};
  const values = Object.values(lifecycle.pages || {}).flatMap((page) => (
    (page.candidates || []).filter((candidate) => candidate.candidate_id === page.selected_candidate_id)
  ));
  if (!values.length) return null;
  return values.reduce((sum, item) => sum + Number(item.review?.overall_score || 0), 0) / values.length;
}

/** Initialize visual brief, prompt provenance, and candidate review controls. */
export async function initVisualView({ api, store }) {
  injectNavigation();
  const view = injectView() || document.getElementById("visual-workflow-view");
  if (!view || view.dataset.visualReady) return;
  view.dataset.visualReady = "true";
  const state = {
    variants: [],
    currentId: "",
    selectedPage: 1,
    handoffs: new Map(),
    busy: false,
  };

  const status = (message, kind = "") => {
    const target = view.querySelector("#visual-workflow-status");
    target.textContent = message;
    target.className = `inline-status${kind ? ` ${kind}` : ""}`;
  };

  function currentVariant() {
    return state.variants.find((item) => item.id === state.currentId) || null;
  }

  function currentRecord(variant, units, index) {
    const unit = units[index] || {};
    const handoff = state.handoffs.get(`${variant.id}:${unit.page}`) || {};
    return { ...unit, ...handoff, visual_prompt_spec: handoff.visual_prompt_spec || unit.visual_prompt_spec };
  }

  function renderSeriesList() {
    const root = view.querySelector("#visual-series-list");
    root.replaceChildren();
    state.variants.forEach((variant) => {
      const metadata = variantMetadata(variant);
      const units = visualUnits(variant);
      const lifecycle = metadata.image_candidate_lifecycle || {};
      const candidateCount = Object.values(lifecycle.pages || {}).reduce((sum, page) => sum + (page.candidates || []).length, 0);
      const button = element("button", `visual-series-item${variant.id === state.currentId ? " active" : ""}`);
      button.type = "button";
      button.dataset.variantId = variant.id;
      button.append(
        element("strong", "", variant.title || "未命名视觉任务"),
        element("span", "", `${isLightVariant(variant) ? "轻内容" : "长文"} · ${units.length} 项 · ${candidateCount} 候选`),
        element("small", "", `v${variant.version} · ${variant.status || "草稿"}`),
      );
      button.addEventListener("click", () => {
        state.currentId = variant.id;
        state.selectedPage = 1;
        render();
        view.querySelector("#visual-page-tabs button")?.focus();
      });
      root.appendChild(button);
    });
    if (!state.variants.length) root.appendChild(element("p", "creative-empty-copy", "还没有公众号视觉任务。先在创作工作台生成内容版本。"));
  }

  function renderOverview(variant) {
    const root = view.querySelector("#visual-series-overview");
    root.replaceChildren();
    if (!variant) {
      root.appendChild(element("p", "creative-empty-copy", "选择一个系列查看视觉状态。"));
      return;
    }
    const metadata = variantMetadata(variant);
    const outputs = variantOutputs(variant);
    const units = visualUnits(variant);
    const lifecycle = metadata.image_candidate_lifecycle || {};
    const pageStates = Object.values(lifecycle.pages || {});
    const selected = pageStates.filter((page) => page.selected_candidate_id).length;
    const score = selectedCandidateScore(metadata);
    const head = element("div", "creative-panel-head");
    const copy = element("div");
    copy.append(element("span", "section-kicker", "SERIES OVERVIEW"), element("h3", "", variantTitle(variant)));
    head.append(copy, element("span", "status-chip neutral", variant.status || "草稿"));
    const grid = element("dl", "visual-overview-grid");
    [
      ["页面 / 槽位", String(units.length)],
      ["已选候选", isLightVariant(variant) ? `${selected}/${units.length}` : "不适用"],
      ["候选均分", score === null ? "待人工选择" : `${score.toFixed(1)} / 100`],
      ["导出文件", String(Object.keys(outputs).length)],
      ["当前任务", store.summary().platformLabel],
      ["发布门禁", metadata.native_zine?.external_web_handoff?.complete ? "图片已齐，仍待人工复核" : "等待图片与人工复核"],
    ].forEach(([label, value]) => {
      const item = element("div", "visual-overview-item");
      item.append(element("dt", "", label), element("dd", "", value));
      grid.appendChild(item);
    });
    root.append(head, grid);
  }

  function renderPageTabs(variant, units) {
    const root = view.querySelector("#visual-page-tabs");
    root.replaceChildren();
    units.forEach((unit, index) => {
      const page = Number(unit.page || index + 1);
      const button = element("button", page === state.selectedPage ? "active" : "", `${String(page).padStart(2, "0")} · ${unit.label || `第 ${page} 页`}`);
      button.type = "button";
      button.setAttribute("role", "tab");
      button.setAttribute("aria-selected", String(page === state.selectedPage));
      button.tabIndex = page === state.selectedPage ? 0 : -1;
      button.addEventListener("click", () => {
        state.selectedPage = page;
        renderDetail(variant);
        root.querySelector('[role="tab"][aria-selected="true"]')?.focus();
      });
      root.appendChild(button);
    });
    if (!units.length) root.appendChild(element("p", "creative-empty-copy", "当前版本还没有视觉 Prompt 或分镜。"));
  }

  async function compilePrompt(variant, page, button) {
    if (!isLightVariant(variant) || state.busy) return;
    state.busy = true;
    button.disabled = true;
    status(`正在冻结第 ${page} 页分镜并比较 Prompt…`);
    try {
      const result = await api.post(`/api/native-skills/minimal-zine/variants/${encodeURIComponent(variant.id)}/web-handoff`, {
        pages: [page],
        force_recompile: true,
      });
      const handoff = result?.pages?.[0];
      if (handoff) state.handoffs.set(`${variant.id}:${page}`, handoff);
      await reloadVariant(variant.id, false);
      status(`第 ${page} 页 Prompt 已编译；请检查 diff、指纹和重复警告。`, "ok");
    } catch (error) {
      status(error.message, "error");
    } finally {
      state.busy = false;
      button.disabled = false;
      renderDetail(currentVariant());
    }
  }

  async function candidateAction(candidate, action, button) {
    const variant = currentVariant();
    if (!variant || state.busy) return;
    let reason = action === "approve" ? "人工复核后批准" : "";
    if (action === "reject") {
      reason = window.prompt("请写明主体、构图、伪影、文字残留或版权等具体问题：", "")?.trim() || "";
      if (!reason) {
        status("驳回候选必须填写具体理由。", "error");
        return;
      }
    }
    state.busy = true;
    button.disabled = true;
    try {
      await api.post(`/api/native-skills/minimal-zine/variants/${encodeURIComponent(variant.id)}/candidates/${encodeURIComponent(candidate.page)}/review`, {
        candidate_id: candidate.candidate_id,
        action,
        reason,
      });
      await reloadVariant(variant.id, false);
      status(`候选 ${candidate.candidate_index} 状态已更新。`, "ok");
    } catch (error) {
      status(error.message, "error");
    } finally {
      state.busy = false;
      renderDetail(currentVariant());
    }
  }

  async function selectCandidate(candidate, button) {
    const variant = currentVariant();
    if (!variant || state.busy) return;
    state.busy = true;
    button.disabled = true;
    try {
      await api.post(`/api/native-skills/minimal-zine/variants/${encodeURIComponent(variant.id)}/candidates/${encodeURIComponent(candidate.page)}/select`, {
        candidate_id: candidate.candidate_id,
      });
      await reloadVariant(variant.id, false);
      status(`候选 ${candidate.candidate_index} 已选为第 ${candidate.page} 页成品锚点；仍需本地重建和人工终审。`, "ok");
    } catch (error) {
      status(error.message, "error");
    } finally {
      state.busy = false;
      renderDetail(currentVariant());
    }
  }

  async function repairCandidate(candidate, button) {
    const variant = currentVariant();
    if (!variant || state.busy) return;
    state.busy = true;
    button.disabled = true;
    status(`正在定向修复候选 ${candidate.candidate_index}；本页最多自动修复一次…`);
    try {
      await api.post(`/api/native-skills/minimal-zine/variants/${encodeURIComponent(variant.id)}/candidates/${encodeURIComponent(candidate.page)}/repair`, {
        candidate_id: candidate.candidate_id,
      }, { timeoutMs: 180_000 });
      await reloadVariant(variant.id, false);
      status("定向修复完成，请重新人工检查候选。", "ok");
    } catch (error) {
      status(error.message, "error");
    } finally {
      state.busy = false;
      renderDetail(currentVariant());
    }
  }

  function renderDetail(variant) {
    const promptHost = view.querySelector("#visual-prompt-host");
    const candidateHost = view.querySelector("#visual-candidate-host");
    if (!variant) {
      promptHost.replaceChildren();
      candidateHost.replaceChildren();
      view.querySelector("#visual-page-tabs").replaceChildren();
      return;
    }
    const units = visualUnits(variant);
    if (!units.some((unit) => Number(unit.page) === state.selectedPage)) state.selectedPage = Number(units[0]?.page || 1);
    renderPageTabs(variant, units);
    const index = Math.max(0, units.findIndex((unit) => Number(unit.page) === state.selectedPage));
    const records = units.map((unit, itemIndex) => currentRecord(variant, units, itemIndex));
    renderPromptView(promptHost, {
      record: records[index] || {},
      records,
      activeIndex: index,
      onCompile: isLightVariant(variant) ? (button) => compilePrompt(variant, state.selectedPage, button) : null,
    });
    const metadata = variantMetadata(variant);
    const lifecycle = metadata.image_candidate_lifecycle || {};
    const pageState = lifecycle.pages?.[String(state.selectedPage)] || null;
    renderCandidateView(candidateHost, {
      variantId: variant.id,
      pageState,
      lifecycle,
      onSelect: isLightVariant(variant) ? selectCandidate : null,
      onReview: isLightVariant(variant) ? candidateAction : null,
      onRepair: isLightVariant(variant) ? repairCandidate : null,
    });
    if (!isLightVariant(variant)) {
      const note = element("p", "creative-empty-copy", "公众号长文配图按槽位上传，不使用 Minimal Zine 图片候选生命周期；事实与版权仍由人工终审。");
      candidateHost.prepend(note);
    }
  }

  function render() {
    renderSeriesList();
    const variant = currentVariant();
    renderOverview(variant);
    renderDetail(variant);
  }

  async function reloadVariant(variantId, rerender = true) {
    const variant = await api.get(`/api/platforms/variants/${encodeURIComponent(variantId)}`);
    const index = state.variants.findIndex((item) => item.id === variant.id);
    if (index >= 0) state.variants[index] = variant; else state.variants.unshift(variant);
    state.currentId = variant.id;
    if (rerender) render();
    return variant;
  }

  async function loadVariants(preferredId = state.currentId) {
    status("正在读取视觉任务…");
    try {
      const variants = await api.get("/api/platforms/variants?platform=wechat&limit=300");
      state.variants = (Array.isArray(variants) ? variants : []).filter((variant) => (
        isLightVariant(variant) || visualUnits(variant).length || Object.keys(variantOutputs(variant)).some((key) => /^(wide|square|visual_|poster_)/.test(key))
      ));
      state.currentId = state.variants.some((item) => item.id === preferredId) ? preferredId : state.variants[0]?.id || "";
      render();
      status(state.variants.length ? "视觉状态已刷新。" : "尚无视觉任务。", state.variants.length ? "ok" : "");
    } catch (error) {
      status(error.message, "error");
      render();
    }
  }

  view.querySelector("#visual-refresh").addEventListener("click", () => { void loadVariants(); });
  view.querySelector("#visual-open-origin").addEventListener("click", () => window.setView?.("wechat-view"));
  view.querySelector("#visual-page-tabs").addEventListener("keydown", (event) => {
    if (!["ArrowLeft", "ArrowRight"].includes(event.key)) return;
    const variant = currentVariant();
    const units = visualUnits(variant);
    const index = units.findIndex((unit) => Number(unit.page) === state.selectedPage);
    if (index < 0 || !units.length) return;
    event.preventDefault();
    const next = Math.min(units.length - 1, Math.max(0, index + (event.key === "ArrowRight" ? 1 : -1)));
    state.selectedPage = Number(units[next].page);
    renderDetail(variant);
    view.querySelector('#visual-page-tabs [role="tab"][aria-selected="true"]')?.focus();
  });
  const fileInput = view.querySelector("#visual-upload-files");
  fileInput.addEventListener("change", () => {
    const files = [...(fileInput.files || [])];
    view.querySelector("#visual-upload-selection").textContent = files.length ? files.map((file) => file.name).join("、") : "尚未选择文件";
  });
  view.querySelector("#visual-upload-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const variant = currentVariant();
    const files = [...(fileInput.files || [])];
    if (!variant || !files.length || state.busy) {
      status(!variant ? "请先选择视觉任务。" : "请先选择要上传的图片。", "error");
      return;
    }
    state.busy = true;
    const submitter = event.submitter || event.currentTarget.querySelector('button[type="submit"]');
    if (submitter) submitter.disabled = true;
    try {
      if (isLightVariant(variant)) {
        if (files.length > 4) throw new Error("Minimal Zine 当前页一次最多上传 4 张候选。");
        await api.upload(`/api/native-skills/minimal-zine/variants/${encodeURIComponent(variant.id)}/external-anchor?page=${encodeURIComponent(state.selectedPage)}`, files, {
          timeoutMs: 180_000,
        });
      } else {
        const units = visualUnits(variant);
        const start = Math.max(0, units.findIndex((unit) => Number(unit.page) === state.selectedPage));
        const targets = units.slice(start, start + files.length);
        if (targets.length < files.length) throw new Error("所选文件多于当前槽位之后的可用配图位置。");
        for (let index = 0; index < files.length; index += 1) {
          const slotId = targets[index].slot_id;
          if (!slotId) throw new Error("配图槽位缺少 slot_id，无法安全上传。");
          await api.upload(`/api/platforms/variants/${encodeURIComponent(variant.id)}/visuals/${encodeURIComponent(slotId)}`, [files[index]]);
        }
      }
      await reloadVariant(variant.id, false);
      fileInput.value = "";
      view.querySelector("#visual-upload-selection").textContent = "尚未选择文件";
      status("图片已回传并刷新候选状态；最终发布仍需人工事实与版权复核。", "ok");
    } catch (error) {
      status(error.message, "error");
    } finally {
      state.busy = false;
      if (submitter) submitter.disabled = false;
      render();
    }
  });

  document.addEventListener("x2red:view-changed", (event) => {
    if (event.detail?.viewId === "visual-workflow-view") void loadVariants();
  });
  await loadVariants();
}
