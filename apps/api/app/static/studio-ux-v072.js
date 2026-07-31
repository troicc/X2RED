(() => {
  const uxState = {
    project: null,
    lastFocusKey: "",
    busy: false,
  };

  const approvalTypes = new Set(["editorial_brief", "outline", "revision_plan"]);
  const artifactNames = {
    editorial_brief: "总编辑任务单",
    evidence_pack: "证据包",
    outline: "文章大纲",
    draft: "初稿",
    reader_review: "读者审稿",
    fact_review: "事实审稿",
    style_review: "风格审稿",
    revision_plan: "主编修改计划",
    final_draft: "完成文章",
    author_decision: "作者决定",
  };
  const stageNames = {
    clarifying: "总编辑正在建立任务单",
    researching: "证据研究员正在整理材料",
    outlining: "结构 Agent 正在制作大纲",
    drafting: "写手正在生成初稿",
    reviewing: "三路审稿与主编正在工作",
    revising: "终稿 Agent 正在执行修改",
    awaiting_brief_approval: "请确认总编辑任务单",
    awaiting_outline_approval: "请确认文章大纲",
    awaiting_revision_approval: "请确认主编修改计划",
    completed: "文章已经完成",
    failed: "项目执行失败",
    canceled: "项目已取消",
  };

  function projectEndpoint(urlValue, method) {
    if ((method || "GET").toUpperCase() !== "GET") return false;
    try {
      const url = new URL(typeof urlValue === "string" ? urlValue : urlValue?.url || "", window.location.href);
      return /^\/api\/writing\/projects\/[^/]+$/.test(url.pathname);
    } catch {
      return false;
    }
  }

  const nativeFetch = window.fetch.bind(window);
  window.fetch = async (...args) => {
    const response = await nativeFetch(...args);
    const method = args[1]?.method || (typeof args[0] === "object" ? args[0]?.method : "GET");
    if (response.ok && projectEndpoint(args[0], method)) {
      response.clone().json().then((project) => {
        if (!project?.id || !Array.isArray(project.artifacts)) return;
        uxState.project = project;
        window.requestAnimationFrame(enhanceProjectDetail);
      }).catch(() => {});
    }
    return response;
  };

  function artifactName(type) {
    return artifactNames[type] || type || "阶段产物";
  }

  function latestArtifact(project, predicate = () => true) {
    return [...(project.artifacts || [])].reverse().find(predicate) || null;
  }

  function pendingArtifact(project) {
    return latestArtifact(project, (artifact) => approvalTypes.has(artifact.artifact_type) && !artifact.approved);
  }

  function parseArtifact(artifact) {
    try {
      return JSON.parse(artifact?.content_json || "{}");
    } catch {
      return {};
    }
  }

  function wait(milliseconds) {
    return new Promise((resolve) => window.setTimeout(resolve, milliseconds));
  }

  async function waitJob(jobId, timeoutMs = 300000) {
    const started = Date.now();
    while (Date.now() - started < timeoutMs) {
      const job = await api(`/api/jobs/${encodeURIComponent(jobId)}`);
      if (job.state === "succeeded") return job;
      if (["failed", "canceled"].includes(job.state)) {
        throw new Error(job.error || "后台任务执行失败");
      }
      await wait(700);
    }
    throw new Error("后台任务等待超时");
  }

  function refreshSelectedProject() {
    document.getElementById("refresh-writing")?.click();
  }

  function setDockBusy(dock, text) {
    uxState.busy = true;
    dock.classList.add("busy");
    dock.querySelectorAll("button").forEach((button) => { button.disabled = true; });
    const status = dock.querySelector(".writing-dock-copy strong");
    if (status) status.textContent = text;
  }

  async function approveAndAdvance(project, artifact, dock) {
    if (uxState.busy) return;
    setDockBusy(dock, "已确认，正在自动运行下一阶段…");
    try {
      await api(
        `/api/writing/projects/${encodeURIComponent(project.id)}/artifacts/${encodeURIComponent(artifact.id)}/approve`,
        {
          method: "POST",
          body: JSON.stringify({ approved: true, note: "作者确认并自动继续下一阶段" }),
        },
      );
      const job = await api(`/api/writing/projects/${encodeURIComponent(project.id)}/run`, {
        method: "POST",
        body: JSON.stringify({ continuous: true }),
      });
      await waitJob(job.id);
      refreshSelectedProject();
    } catch (error) {
      window.alert(error.message);
      uxState.busy = false;
      refreshSelectedProject();
    }
  }

  async function rejectArtifact(project, artifact, dock) {
    if (uxState.busy) return;
    const note = window.prompt("写下需要修改的地方。Agent 会按这条反馈重新生成当前阶段。", "");
    if (note === null) return;
    setDockBusy(dock, "正在退回当前阶段…");
    try {
      await api(
        `/api/writing/projects/${encodeURIComponent(project.id)}/artifacts/${encodeURIComponent(artifact.id)}/approve`,
        {
          method: "POST",
          body: JSON.stringify({ approved: false, note: note.trim() || "作者要求重做当前阶段" }),
        },
      );
      const job = await api(`/api/writing/projects/${encodeURIComponent(project.id)}/run`, {
        method: "POST",
        body: JSON.stringify({ continuous: true }),
      });
      await waitJob(job.id);
      refreshSelectedProject();
    } catch (error) {
      window.alert(error.message);
      uxState.busy = false;
      refreshSelectedProject();
    }
  }

  async function continueProject(project, dock) {
    if (uxState.busy) return;
    setDockBusy(dock, "正在运行下一阶段…");
    try {
      const job = await api(`/api/writing/projects/${encodeURIComponent(project.id)}/run`, {
        method: "POST",
        body: JSON.stringify({ continuous: true }),
      });
      await waitJob(job.id);
      refreshSelectedProject();
    } catch (error) {
      window.alert(error.message);
      uxState.busy = false;
      refreshSelectedProject();
    }
  }

  async function openCompletedDraft(project, tabId) {
    if (!project.source_id) {
      window.alert("这个项目缺少来源关联，无法打开终稿。");
      return;
    }
    window.setView?.("workbench-view");
    if (typeof window.loadSources === "function") {
      await window.loadSources(project.source_id);
    } else if (typeof window.selectSource === "function") {
      await window.selectSource(project.source_id);
    }
    window.setTab?.(tabId);
    history.replaceState(null, "", `${window.location.pathname}?source=${encodeURIComponent(project.source_id)}`);
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  function buildFinalPreview(project) {
    const artifact = latestArtifact(project, (item) => item.artifact_type === "final_draft");
    if (!artifact) return null;
    const content = parseArtifact(artifact);
    const preview = document.createElement("article");
    preview.className = "final-article-preview";

    const heading = document.createElement("header");
    heading.innerHTML = '<span class="section-kicker">FINAL ARTICLE</span><strong>多 Agent 完成文章</strong>';
    const title = document.createElement("h2");
    title.textContent = content.title || project.promise || "完成文章";
    const body = document.createElement("div");
    body.className = "final-article-body";
    String(content.body || "").split(/\n{2,}/).filter(Boolean).forEach((paragraph) => {
      const node = document.createElement("p");
      node.textContent = paragraph.trim();
      body.appendChild(node);
    });
    const tags = document.createElement("div");
    tags.className = "final-article-tags";
    const values = Array.isArray(content.tags)
      ? content.tags
      : String(content.tags || "").split(/[，,\s]+/).filter(Boolean);
    values.slice(0, 10).forEach((value) => {
      const tag = document.createElement("span");
      tag.textContent = value.startsWith("#") ? value : `#${value}`;
      tags.appendChild(tag);
    });
    preview.append(heading, title, body, tags);
    return preview;
  }

  function prepareArtifacts(project, detail) {
    const cards = [...detail.querySelectorAll(".artifact-card")];
    if (!cards.length) return null;
    const pending = pendingArtifact(project);
    const focusArtifact = pending
      || latestArtifact(project, (item) => item.artifact_type === "final_draft")
      || latestArtifact(project);

    cards.forEach((card, index) => {
      const artifact = project.artifacts[index];
      if (!artifact) return;
      card.dataset.artifactId = artifact.id;
      card.dataset.artifactType = artifact.artifact_type;
      const header = card.querySelector(".artifact-header");
      if (!header || header.querySelector(".artifact-toggle")) return;
      const toggle = document.createElement("button");
      toggle.type = "button";
      toggle.className = "artifact-toggle";
      toggle.textContent = artifact.id === focusArtifact?.id ? "收起" : "展开";
      header.appendChild(toggle);
      const collapsed = artifact.id !== focusArtifact?.id;
      card.classList.toggle("collapsed", collapsed);
      toggle.addEventListener("click", () => {
        card.classList.toggle("collapsed");
        toggle.textContent = card.classList.contains("collapsed") ? "展开" : "收起";
      });
    });
    return cards.find((card) => card.dataset.artifactId === focusArtifact?.id) || cards.at(-1);
  }

  function buildDock(project) {
    const dock = document.createElement("section");
    dock.className = "writing-action-dock";
    const copy = document.createElement("div");
    copy.className = "writing-dock-copy";
    const kicker = document.createElement("span");
    kicker.textContent = project.state === "completed" ? "READY FOR EDITING" : "CURRENT ACTION";
    const title = document.createElement("strong");
    title.textContent = stageNames[project.state] || project.current_stage || "继续写作流程";
    const detail = document.createElement("small");
    detail.textContent = project.state.startsWith("awaiting_")
      ? "确认后系统会自动运行到下一个需要你决定的阶段。"
      : project.state === "completed"
        ? "终稿已经写入创作工作台，可直接编辑、制图和发布。"
        : "系统会运行到下一个人工确认点。";
    copy.append(kicker, title, detail);

    const actions = document.createElement("div");
    actions.className = "writing-dock-actions";
    const pending = pendingArtifact(project);
    if (pending) {
      const reject = document.createElement("button");
      reject.type = "button";
      reject.className = "ghost-danger";
      reject.textContent = "退回修改";
      reject.addEventListener("click", () => rejectArtifact(project, pending, dock));
      const approve = document.createElement("button");
      approve.type = "button";
      approve.className = "primary-action writing-primary-action";
      approve.textContent = "确认并自动继续";
      approve.addEventListener("click", () => approveAndAdvance(project, pending, dock));
      actions.append(reject, approve);
    } else if (project.state === "completed") {
      const article = document.createElement("button");
      article.type = "button";
      article.className = "primary-action writing-primary-action";
      article.textContent = "查看完成文章";
      article.addEventListener("click", () => openCompletedDraft(project, "draft-pane"));
      const cards = document.createElement("button");
      cards.type = "button";
      cards.className = "secondary-action";
      cards.textContent = "去制图";
      cards.addEventListener("click", () => openCompletedDraft(project, "cards-pane"));
      actions.append(article, cards);
    } else if (!["failed", "canceled"].includes(project.state)) {
      const run = document.createElement("button");
      run.type = "button";
      run.className = "primary-action writing-primary-action";
      run.textContent = "运行到下一个确认点";
      run.addEventListener("click", () => continueProject(project, dock));
      actions.append(run);
    }
    dock.append(copy, actions);
    return dock;
  }

  function enhanceProjectDetail() {
    const project = uxState.project;
    const detail = document.getElementById("writing-detail");
    if (!project || !detail || detail.hidden) return;
    uxState.busy = false;

    detail.querySelector(".writing-action-dock")?.remove();
    detail.querySelector(".final-article-preview")?.remove();
    detail.querySelector(".project-run-actions")?.classList.add("legacy-project-actions");
    detail.querySelectorAll(".artifact-approval").forEach((node) => node.classList.add("legacy-artifact-actions"));

    const timeline = detail.querySelector(".artifact-timeline");
    if (project.state === "completed" && timeline) {
      const preview = buildFinalPreview(project);
      if (preview) timeline.before(preview);
    }
    const focusCard = prepareArtifacts(project, detail);
    detail.appendChild(buildDock(project));

    const focusKey = `${project.id}:${project.state}:${project.current_stage}:${project.artifacts.length}`;
    if (focusKey !== uxState.lastFocusKey) {
      uxState.lastFocusKey = focusKey;
      const panel = detail.closest(".project-detail-panel");
      if (project.state === "completed") {
        panel?.scrollTo({ top: 0, behavior: "smooth" });
      } else if (focusCard && panel) {
        panel.scrollTo({ top: Math.max(0, focusCard.offsetTop - 20), behavior: "smooth" });
      }
    }
  }

  function installObserver() {
    const root = document.getElementById("writing-view") || document.body;
    const observer = new MutationObserver(() => window.requestAnimationFrame(enhanceProjectDetail));
    observer.observe(root, { childList: true, subtree: true });
    enhanceProjectDetail();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", installObserver, { once: true });
  } else {
    installObserver();
  }
})();
