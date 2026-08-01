(() => {
  async function apiCall(path) {
    const response = await fetch(path, { headers: { "Content-Type": "application/json" } });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    return response.json();
  }

  async function resolveCurrentVariant(preferredId = "") {
    const form = document.getElementById("wechat-editor");
    if (!form || form.hidden) return;
    const sourceId = document.getElementById("wechat-source")?.value || "";
    const title = document.getElementById("wechat-title")?.value || "";
    const stateText = document.getElementById("wechat-version-state")?.textContent || "";
    const version = Number(stateText.match(/v(\d+)/)?.[1] || 0);
    const variants = await apiCall(`/api/platforms/variants?platform=wechat&source_id=${encodeURIComponent(sourceId)}`);
    const variant = variants.find((item) => item.id === preferredId)
      || variants.find((item) => item.version === version && item.title === title)
      || variants.find((item) => item.title === title)
      || variants[0];
    if (!variant) return;
    form.dataset.variantId = variant.id;
    document.dispatchEvent(new CustomEvent("x2red:wechat-variant-selected", { detail: { variant } }));
  }

  document.addEventListener("click", (event) => {
    if (event.target.closest?.(".platform-variant-item")) {
      setTimeout(() => resolveCurrentVariant().catch(() => {}), 0);
    }
  });

  document.addEventListener("x2red:wechat-refresh-request", async (event) => {
    document.getElementById("wechat-refresh")?.click();
    const preferredId = event.detail?.variantId || "";
    for (let attempt = 0; attempt < 12; attempt += 1) {
      await new Promise((resolve) => setTimeout(resolve, 250));
      try {
        const variants = await apiCall("/api/platforms/variants?platform=wechat&limit=100");
        const preferred = variants.find((item) => item.id === preferredId);
        if (preferred) {
          const buttons = [...document.querySelectorAll(".platform-variant-item")];
          const target = buttons.find((button) => button.textContent.includes(`v${preferred.version}`) && button.textContent.includes(preferred.title));
          target?.click();
          await resolveCurrentVariant(preferredId);
          return;
        }
      } catch {}
    }
  });

  function boot() {
    const observer = new MutationObserver(() => {
      const state = document.getElementById("wechat-version-state");
      if (state && state.textContent && !state.dataset.reviewObserved) {
        state.dataset.reviewObserved = "1";
        resolveCurrentVariant().catch(() => {});
      }
    });
    observer.observe(document.body, { childList: true, subtree: true, characterData: true });
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot, { once: true });
  else boot();
})();
