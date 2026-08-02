(() => {
  function restoreWritingProject() {
    const raw = window.location.hash || "";
    const match = raw.match(/^#writing-project=([^&]+)$/);
    if (!match) return;

    window.setView?.("writing-view");
    const expectedId = decodeURIComponent(match[1]);
    const list = document.getElementById("writing-project-list");
    if (!list) return;

    const selectNewestProject = () => {
      const first = list.querySelector("button.writing-project-item");
      if (!first) return false;
      first.click();
      history.replaceState(null, "", `${window.location.pathname}${window.location.search}`);
      document.getElementById("writing-detail")?.scrollIntoView({ behavior: "smooth", block: "start" });
      return true;
    };

    if (selectNewestProject()) return;
    const observer = new MutationObserver(() => {
      if (!selectNewestProject()) return;
      observer.disconnect();
    });
    observer.observe(list, { childList: true });
    window.setTimeout(() => observer.disconnect(), 15000);

    list.dataset.restoreProjectId = expectedId;
  }

  function loadScript(src) {
    if (document.querySelector(`script[src='${src}']`)) return Promise.resolve();
    return new Promise((resolve, reject) => {
      const script = document.createElement("script");
      script.src = src;
      script.async = false;
      script.addEventListener("load", resolve, { once: true });
      script.addEventListener("error", () => reject(new Error(`无法加载 ${src}`)), { once: true });
      document.body.appendChild(script);
    });
  }

  async function loadV14Enhancements() {
    await loadScript("/static/light-content-fixes-v14.js");
    await loadScript("/static/information-architecture-v14.js");
  }

  function boot() {
    restoreWritingProject();
    const start = () => loadV14Enhancements().catch((error) => console.error(error));
    if (document.readyState === "complete") start();
    else window.addEventListener("load", start, { once: true });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot, { once: true });
  } else {
    boot();
  }
})();
