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

    // Keep the project id available for diagnostics even though the list is sorted
    // newest-first and the newly created project is therefore the first item.
    list.dataset.restoreProjectId = expectedId;
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", restoreWritingProject, { once: true });
  } else {
    restoreWritingProject();
  }
})();
