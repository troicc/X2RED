(() => {
  function selectControl(id, label, values) {
    const wrapper = document.createElement("label");
    wrapper.className = "field-label rich-card-control";
    wrapper.textContent = label;
    const select = document.createElement("select");
    select.id = id;
    values.forEach(([value, text]) => select.add(new Option(text, value)));
    wrapper.appendChild(select);
    return wrapper;
  }

  function injectControls() {
    const actions = document.querySelector(".card-control-actions");
    if (!actions || document.getElementById("card-visual-style")) return;
    const template = document.getElementById("card-template")?.parentElement || document.getElementById("card-template");
    const controls = [
      selectControl("card-visual-style", "视觉", [
        ["auto", "自动风格"], ["editorial", "Editorial 编辑"], ["swiss", "Swiss 设计"],
        ["knowledge", "Knowledge 知识"], ["poster", "Poster 海报"], ["notebook", "Notebook 笔记"],
        ["bold", "Bold 强调"], ["minimal", "Minimal 极简"],
      ]),
      selectControl("card-layout", "布局", [
        ["auto", "自动布局"], ["sparse", "稀疏"], ["balanced", "均衡"], ["dense", "密集"],
        ["list", "清单"], ["comparison", "对比"], ["flow", "流程"], ["quadrant", "四象限"],
      ]),
      selectControl("card-palette", "配色", [
        ["auto", "自动配色"], ["neutral", "中性"], ["macaron", "马卡龙"], ["warm", "暖色"],
        ["neon", "霓虹"], ["monochrome", "黑白"],
      ]),
      selectControl("card-material", "素材", [
        ["auto", "自动"], ["source_first", "来源素材优先"], ["text_only", "纯文字"],
      ]),
    ];
    controls.reverse().forEach((control) => actions.insertBefore(control, template));
  }

  const previousFetch = window.fetch.bind(window);
  window.fetch = async (...args) => {
    try {
      const url = new URL(typeof args[0] === "string" ? args[0] : args[0]?.url || "", window.location.href);
      const method = (args[1]?.method || "GET").toUpperCase();
      if (method === "POST" && /^\/api\/drafts\/[^/]+\/cards$/.test(url.pathname) && args[1]?.body) {
        const body = JSON.parse(args[1].body);
        body.visual_style = document.getElementById("card-visual-style")?.value || "auto";
        body.layout = document.getElementById("card-layout")?.value || "auto";
        body.palette = document.getElementById("card-palette")?.value || "auto";
        body.material_strategy = document.getElementById("card-material")?.value || "auto";
        args[1] = { ...args[1], body: JSON.stringify(body) };
      }
    } catch {}
    return previousFetch(...args);
  };

  function boot() {
    injectControls();
    const observer = new MutationObserver(injectControls);
    observer.observe(document.body, { childList: true, subtree: true });
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot, { once: true });
  else boot();
})();
