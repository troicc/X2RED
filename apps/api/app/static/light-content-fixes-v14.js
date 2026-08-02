(() => {
  const call = window.api || (async (url, options = {}) => {
    const response = await fetch(url, {
      headers: { "Content-Type": "application/json", ...(options.headers || {}) },
      ...options,
    });
    if (!response.ok) {
      const payload = await response.json().catch(() => ({}));
      throw new Error(payload.detail || `HTTP ${response.status}`);
    }
    if (response.status === 204) return null;
    return response.json();
  });

  let busy = false;

  const node = (id) => document.getElementById(id);
  const parse = (value, fallback = {}) => {
    try { return JSON.parse(value || ""); } catch { return fallback; }
  };
  const selected = (name, fallback = "") => (
    document.querySelector(`input[name='${name}']:checked`)?.value || fallback
  );

  function show(text, kind = "") {
    const target = node("light-status");
    if (!target) return;
    target.textContent = text;
    target.className = `light-status${kind ? ` ${kind}` : ""}`;
  }

  function setButtonsDisabled(value) {
    [
      "light-generate",
      "light-use-candidate",
      "light-save-edit",
      "light-render",
      "light-approve",
      "light-iterate",
      "light-corpus-add",
    ].forEach((id) => {
      const button = node(id);
      if (button) button.disabled = value;
    });
  }

  async function run(message, task) {
    if (busy) return;
    busy = true;
    setButtonsDisabled(true);
    if (message) show(message);
    try {
      return await task();
    } catch (error) {
      show(error.message || String(error), "error");
      throw error;
    } finally {
      busy = false;
      setButtonsDisabled(false);
    }
  }

  function briefPayload() {
    return {
      source_id: node("light-source")?.value || "",
      draft_id: node("light-draft")?.value || null,
      recipe: selected("light-recipe", "comfort"),
      image_count: Number(node("light-count")?.value || 4),
      seasonal_topic: node("light-seasonal-topic")?.value || "",
      audience: node("light-audience")?.value || "",
      tone: node("light-tone")?.value || "自然、具体、克制",
      visual_style: selected("light-style", "auto"),
      quality_mode: node("light-quality")?.value || "studio",
      feedback: node("light-initial-feedback")?.value || "",
      theme: "zen",
      author: "",
    };
  }

  function editorPayload() {
    return {
      title: node("light-edit-title")?.value || "",
      subtitle: node("light-edit-subtitle")?.value || "",
      summary: node("light-edit-summary")?.value || "",
      body_markdown: node("light-edit-body")?.value || "",
      tags: node("light-edit-tags")?.value || "",
      theme: "zen",
    };
  }

  function versionNumber() {
    const value = node("light-current-state")?.textContent || "";
    return Number(value.match(/v(\d+)/)?.[1] || 0);
  }

  function activeCandidateIndex() {
    const tabs = [...document.querySelectorAll("#light-candidate-tabs .light-candidate-tab")];
    return Math.max(0, tabs.findIndex((button) => button.classList.contains("active")));
  }

  async function currentVariant() {
    const sourceId = node("light-source")?.value || "";
    if (!sourceId) throw new Error("请先选择来源。 ");
    const variants = await call(
      `/api/platforms/variants?platform=wechat&source_id=${encodeURIComponent(sourceId)}&limit=200`,
    );
    const light = variants.filter((item) => item.format === "light_series");
    const version = versionNumber();
    const variant = light.find((item) => Number(item.version) === version) || light[0];
    if (!variant) throw new Error("当前来源还没有轻内容版本。 ");
    return variant;
  }

  function differs(variant, payload) {
    return ["title", "subtitle", "summary", "body_markdown", "tags", "theme"]
      .some((key) => String(variant[key] || "") !== String(payload[key] || ""));
  }

  async function persistEditor(variant, { adoptCandidate = true } = {}) {
    let current = variant;
    const metadata = parse(current.metadata_json, {});
    const candidates = Array.isArray(metadata.candidates) ? metadata.candidates : [];
    const candidateIndex = activeCandidateIndex();
    if (
      adoptCandidate
      && candidates.length
      && Number(metadata.selected_candidate_index || 0) !== candidateIndex
    ) {
      current = await call(
        `/api/platforms/wechat/light/variants/${encodeURIComponent(current.id)}/select-candidate`,
        {
          method: "POST",
          body: JSON.stringify({ candidate_index: candidateIndex }),
        },
      );
    }
    const payload = { ...editorPayload(), theme: current.theme || "zen" };
    if (differs(current, payload)) {
      current = await call(`/api/platforms/variants/${encodeURIComponent(current.id)}`, {
        method: "PUT",
        body: JSON.stringify(payload),
      });
    }
    return current;
  }

  const wait = (milliseconds) => new Promise((resolve) => setTimeout(resolve, milliseconds));

  async function refreshToVariant(variant) {
    node("light-refresh")?.click();
    const expected = Number(variant.version || 0);
    for (let attempt = 0; attempt < 40; attempt += 1) {
      await wait(150);
      const chips = [...document.querySelectorAll("#light-version-rail .light-version-chip")];
      const chip = chips.find((item) => item.textContent.trim().startsWith(`v${expected} ·`));
      if (chip) {
        chip.click();
        return;
      }
    }
    node("light-refresh")?.click();
  }

  async function generate() {
    const payload = briefPayload();
    if (!payload.source_id) return show("请先选择来源。", "error");
    await run("选题、写作、审稿、视觉导演和总编正在协作……", async () => {
      const variant = await call("/api/platforms/wechat/light/variants", {
        method: "POST",
        body: JSON.stringify(payload),
      });
      await refreshToVariant(variant);
      show("已生成并自动加载三个候选，不需要再手动刷新。", "ok");
    });
  }

  async function useCandidate() {
    await run("正在采用当前候选并保存不可变版本……", async () => {
      const variant = await currentVariant();
      const revised = await call(
        `/api/platforms/wechat/light/variants/${encodeURIComponent(variant.id)}/select-candidate`,
        {
          method: "POST",
          body: JSON.stringify({ candidate_index: activeCandidateIndex() }),
        },
      );
      await refreshToVariant(revised);
      show(`当前候选已保存为 v${revised.version}。`, "ok");
    });
  }

  async function saveEdit() {
    await run("正在保存编辑框里的当前文字……", async () => {
      const variant = await currentVariant();
      const revised = await persistEditor(variant, { adoptCandidate: true });
      await refreshToVariant(revised);
      show(`当前候选与人工修改已保存为 v${revised.version}。`, "ok");
    });
  }

  async function nativeImageConfigured() {
    try {
      const value = await call("/api/native-skills");
      return Boolean(value.image_generation?.configured);
    } catch {
      return false;
    }
  }

  async function renderCurrent() {
    await run("正在冻结当前候选和编辑框，再生成图组……", async () => {
      let variant = await currentVariant();
      variant = await persistEditor(variant, { adoptCandidate: true });
      const metadata = parse(variant.metadata_json, {});
      const useNative = ["minimal_zine", "minimal_zine_native"].includes(
        String(metadata.visual_style || ""),
      ) && await nativeImageConfigured();
      if (useNative) {
        await call(
          `/api/native-skills/minimal-zine/variants/${encodeURIComponent(variant.id)}/render`,
          { method: "POST", body: JSON.stringify({ regenerate: false }) },
        );
        variant = await call(`/api/platforms/variants/${encodeURIComponent(variant.id)}`);
        show("原版 Minimal Zine 已完成：模型只画无字视觉锚点，中文与版式由本地合成。", "ok");
      } else {
        const result = await call(`/api/platforms/variants/${encodeURIComponent(variant.id)}/render`, {
          method: "POST",
          body: JSON.stringify({ package: true }),
        });
        variant = result.variant;
        show(
          useNative
            ? "图组已生成。"
            : "图组已按当前编辑稿生成并重建预览与发布包。",
          "ok",
        );
      }
      await refreshToVariant(variant);
    });
  }

  async function iterate() {
    const feedback = node("light-feedback")?.value.trim() || "";
    if (!feedback) return show("请先写清楚要修改的角度、文字或画面。", "error");
    await run("正在带着反馈重新策划和审稿……", async () => {
      let variant = await currentVariant();
      variant = await persistEditor(variant, { adoptCandidate: true });
      const revised = await call(
        `/api/platforms/wechat/light/variants/${encodeURIComponent(variant.id)}/iterate`,
        {
          method: "POST",
          body: JSON.stringify({
            feedback,
            quality_mode: node("light-quality")?.value || "studio",
          }),
        },
      );
      node("light-feedback").value = "";
      await refreshToVariant(revised);
      show("新一轮候选和审稿已经加载。", "ok");
    });
  }

  async function approve() {
    await run("正在批准当前编辑稿并加入私有优质语料……", async () => {
      let variant = await currentVariant();
      variant = await persistEditor(variant, { adoptCandidate: true });
      const note = node("light-feedback")?.value.trim()
        || "人工确认可作为未来同配方的正向样本";
      await call(`/api/platforms/wechat/light/variants/${encodeURIComponent(variant.id)}/approve`, {
        method: "POST",
        body: JSON.stringify({ note }),
      });
      await refreshToVariant(variant);
      show("当前实际编辑稿已批准并进入私有优质语料。", "ok");
    });
  }

  async function addCorpus() {
    const title = node("light-corpus-title")?.value.trim() || "";
    const body = node("light-corpus-body")?.value.trim() || "";
    if (!title && !body) return show("请粘贴你原创或有权使用的样本。", "error");
    await run("正在加入授权样本……", async () => {
      await call("/api/platforms/wechat/light/corpus", {
        method: "POST",
        body: JSON.stringify({
          recipe: selected("light-recipe", "comfort"),
          title,
          body_markdown: body,
          visual_style: selected("light-style", "auto"),
          note: node("light-corpus-note")?.value || "",
        }),
      });
      ["light-corpus-title", "light-corpus-body", "light-corpus-note"].forEach((id) => {
        if (node(id)) node(id).value = "";
      });
      node("light-refresh")?.click();
      show("授权样本已加入。", "ok");
    });
  }

  function replaceButton(id, label, handler) {
    const old = node(id);
    if (!old || old.dataset.v14 === "true") return;
    const button = old.cloneNode(true);
    button.dataset.v14 = "true";
    if (label) button.textContent = label;
    old.replaceWith(button);
    button.addEventListener("click", (event) => {
      event.preventDefault();
      handler().catch(() => {});
    });
  }

  function patch() {
    replaceButton("light-generate", "多 Agent 生成 3 个候选", generate);
    replaceButton("light-use-candidate", "采用当前候选", useCandidate);
    replaceButton("light-save-edit", "保存当前编辑稿", saveEdit);
    replaceButton("light-render", "按当前编辑稿生成图组", renderCurrent);
    replaceButton("light-iterate", "按反馈重新迭代", iterate);
    replaceButton("light-approve", "批准当前编辑稿", approve);
    replaceButton("light-corpus-add", "加入授权样本", addCorpus);
    const helper = node("light-render")?.parentElement;
    if (helper && !helper.querySelector("[data-light-v14-note]")) {
      const note = document.createElement("small");
      note.dataset.lightV14Note = "true";
      note.style.cssText = "display:block;width:100%;color:#737b8a;line-height:1.5";
      note.textContent = "生成前会自动采用当前候选并保存编辑框；Minimal Zine 的模型图只作无字视觉素材，中文由本地排版。";
      helper.appendChild(note);
    }
  }

  const observer = new MutationObserver(patch);
  observer.observe(document.documentElement, { childList: true, subtree: true });
  patch();
})();
