(() => {
  const studioState = {
    targets: [],
    feed: [],
    projects: [],
    selectedProject: null,
    materials: [],
    selectedMaterialRefs: new Set(),
  };
  const WRITING_MATERIALS_KEY = "x2red.workspace.wechat.deep-writing.materials";
  const WRITING_MATERIAL_GROUPS = [
    ["pool", "语料池批次"],
    ["x", "X / 信号台来源"],
    ["xhs", "小红书来源"],
    ["dy", "抖音来源"],
    ["ks", "快手来源"],
    ["bili", "B站来源"],
    ["wb", "微博来源"],
    ["tieba", "贴吧来源"],
    ["zhihu", "知乎来源"],
    ["web", "网页、文档与粘贴来源"],
    ["draft_revision", "已写草稿版本"],
    ["platform_variant", "已写平台版本"],
  ];

  function createElement(tag, className = "", text = "") {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text) node.textContent = text;
    return node;
  }

  function injectNavigation() {
    const nav = document.querySelector(".primary-nav");
    if (!nav || document.querySelector('[data-view="signals-view"]')) return;
    const publish = nav.querySelector('[data-view="publish-view"]');
    const signalButton = createElement("button", "nav-item");
    signalButton.dataset.view = "signals-view";
    signalButton.innerHTML = '<span class="nav-icon">◉</span><span>信号台</span>';
    nav.insertBefore(signalButton, publish);
    signalButton.addEventListener("click", () => window.setView(signalButton.dataset.view));
  }

  function injectViews() {
    const stack = document.querySelector(".view-stack");
    if (!stack || document.getElementById("signals-view")) return;
    const publishView = document.getElementById("publish-view");

    const signals = createElement("section", "app-view");
    signals.id = "signals-view";
    signals.innerHTML = `
      <section class="page-intro studio-intro">
        <span class="section-kicker">SIGNAL INTELLIGENCE</span><h2>信号台</h2>
        <p>持续扫描对标作者与主题，用冻结基线判断异常表现；只有高价值候选才进入 AI 分析。</p>
      </section>
      <section id="signal-dashboard" class="signal-metrics"></section>
      <section class="studio-two-column">
        <article class="surface studio-panel">
          <div class="panel-heading"><div><span class="section-kicker">MONITOR TARGETS</span><h3>监控目标</h3></div><button id="refresh-signals" class="secondary-action" type="button">刷新</button></div>
          <form id="monitor-form" class="monitor-form">
            <select id="monitor-kind"><option value="profile">作者时间线</option><option value="search">关键词搜索</option><option value="quotes">引用帖子</option><option value="trends">趋势</option></select>
            <input id="monitor-target" required placeholder="作者 handle、搜索词或帖子 ID" />
            <input id="monitor-name" placeholder="显示名称（可选）" />
            <label>扫描间隔（分钟）<input id="monitor-interval" type="number" min="15" max="10080" value="360" /></label>
            <button class="primary-action" type="submit">添加并开始监控</button>
          </form>
          <div id="monitor-list" class="monitor-list"></div>
        </article>
        <article class="surface studio-panel signal-feed-panel">
          <div class="panel-heading"><div><span class="section-kicker">BOOM FEED</span><h3>高价值候选</h3></div><select id="signal-grade"><option value="">全部等级</option><option value="T3">T3 现象级</option><option value="T2">T2 爆款</option><option value="T1">T1 小爆</option><option value="low_quality">相对高但未破圈</option><option value="ordinary">普通</option></select></div>
          <div id="signal-feed" class="signal-feed"></div>
        </article>
      </section>`;

    const writing = createElement("section", "app-view");
    writing.id = "writing-view";
    writing.innerHTML = `
      <section class="page-intro studio-intro">
        <span class="section-kicker">WECHAT · DEEP WRITING</span><h2>公众号深度写作</h2>
        <p>这是公众号长文里的深度模式：先冻结多来源证据，再由总编辑、研究、写作和审稿分阶段交接。</p>
        <button id="writing-back-wechat" class="secondary-action" type="button">返回公众号工作台</button>
      </section>
      <section class="studio-two-column writing-layout">
        <article class="surface studio-panel">
          <div class="panel-heading"><div><span class="section-kicker">NEW PROJECT</span><h3>建立写作任务</h3></div><button id="refresh-writing" class="secondary-action" type="button">刷新</button></div>
          <form id="writing-project-form" class="writing-project-form">
            <section class="writing-material-picker" aria-labelledby="writing-material-title">
              <div class="writing-material-head"><strong id="writing-material-title">输入材料 · 来源与已写版本均可多选</strong><span id="writing-material-count">已选 0 个</span></div>
              <div class="writing-material-tools"><input id="writing-material-search" type="search" placeholder="搜索来源、版本标题或正文" /><button id="writing-material-clear" class="tool-button" type="button">清空库内选择</button></div>
              <div id="writing-material-list" class="writing-material-list" role="group" aria-label="深度写作可多选输入材料"></div>
              <small>直接勾选，不需要按住 ⌘ 或 Ctrl。来源、已写版本和下方粘贴内容会同时作为本项目输入。</small>
            </section>
            <section class="writing-paste-panel">
              <strong>同时补充粘贴材料（可留空）</strong>
              <label>材料标题<input id="writing-paste-title" maxlength="200" placeholder="可选；留空则取正文首句" /></label>
              <label>原作者<input id="writing-paste-author" maxlength="160" placeholder="可选" /></label>
              <label>原文链接<input id="writing-paste-url" maxlength="2000" inputmode="url" placeholder="可选；http(s)://…" /></label>
              <label>粘贴正文<textarea id="writing-paste-content" rows="7" maxlength="200000" placeholder="可以与上方所有已选材料一起提交；保存后进入标准素材库。"></textarea></label>
            </section>
            <label>模式<select id="writing-mode"><option value="studio">工作室模式 · 人工阶段确认</option><option value="fast">快速模式 · 自动走完</option></select></label>
            <label>目标读者<textarea id="writing-reader" rows="2" placeholder="例如：关注 AI 工程但不写 CUDA 的技术读者"></textarea></label>
            <label>文章承诺<textarea id="writing-promise" rows="2" placeholder="读完后读者具体能理解什么"></textarea></label>
            <label>我的核心判断<textarea id="writing-thesis" rows="3" placeholder="留空则由总编辑 Agent 提议"></textarea></label>
            <button class="primary-action" type="submit">创建写作项目</button>
          </form>
          <div id="writing-project-list" class="writing-project-list"></div>
        </article>
        <article class="surface studio-panel project-detail-panel">
          <div id="writing-empty" class="stage-empty"><div class="empty-orbit small">✎</div><h3>选择一个写作项目</h3><p>每个 Agent 的输入、输出、审批状态和错误都会保留下来。</p></div>
          <div id="writing-detail" hidden></div>
        </article>
      </section>`;

    stack.insertBefore(signals, publishView);
    stack.insertBefore(writing, publishView);
  }

  const baseSetView = window.setView;
  window.setView = function setStudioView(viewId) {
    baseSetView(viewId);
    const titles = { "signals-view": "信号台", "writing-view": "公众号深度写作" };
    if (titles[viewId]) document.getElementById("page-title").textContent = titles[viewId];
    if (viewId === "signals-view") loadSignals();
    if (viewId === "writing-view") loadWriting();
  };

  async function waitJob(jobId, timeoutMs = 180000) {
    const started = Date.now();
    while (Date.now() - started < timeoutMs) {
      const job = await api(`/api/jobs/${encodeURIComponent(jobId)}`);
      if (job.state === "succeeded") return job;
      if (job.state === "failed") throw new Error(job.error || "后台任务失败");
      await new Promise((resolve) => setTimeout(resolve, 700));
    }
    throw new Error("后台任务等待超时");
  }

  function metricCard(label, value, detail) {
    return `<article class="signal-metric"><span>${label}</span><strong>${value}</strong><small>${detail}</small></article>`;
  }

  async function loadSignals() {
    const [dashboard, targets, feed] = await Promise.all([
      api("/api/signals/dashboard"),
      api("/api/signals/targets"),
      api(`/api/signals/feed?grade=${encodeURIComponent(document.getElementById("signal-grade")?.value || "")}`),
    ]);
    studioState.targets = targets;
    studioState.feed = feed;
    document.getElementById("signal-dashboard").innerHTML = [
      metricCard("监控目标", dashboard.active_targets, `${dashboard.due_targets} 个等待扫描`),
      metricCard("候选内容", dashboard.candidates, "持续去重沉淀"),
      metricCard("T3 / T2", `${dashboard.grade_counts.T3 || 0} / ${dashboard.grade_counts.T2 || 0}`, "冻结作者基线"),
      metricCard("写作项目", dashboard.writing_projects, "正式进入生产的选题"),
    ].join("");
    renderTargets();
    renderSignalFeed();
  }

  function renderTargets() {
    const box = document.getElementById("monitor-list");
    box.replaceChildren();
    if (!studioState.targets.length) {
      box.append(createElement("div", "card-empty", "还没有监控目标。先从 5—10 个真正值得追踪的作者开始。"));
      return;
    }
    studioState.targets.forEach((target) => {
      const row = createElement("article", "monitor-row");
      const copy = createElement("div", "monitor-copy");
      const title = createElement("strong", "", target.name || target.target);
      const meta = createElement("small", "", `${target.kind} · 每 ${target.interval_minutes} 分钟 · ${target.last_run_at ? formatDate(target.last_run_at) : "尚未扫描"}`);
      if (target.last_error) meta.textContent += ` · ${target.last_error}`;
      copy.append(title, meta);
      const actions = createElement("div", "monitor-actions");
      const run = createElement("button", "secondary-action", "立即扫描");
      run.addEventListener("click", async () => {
        run.disabled = true;
        try {
          const job = await api(`/api/signals/targets/${encodeURIComponent(target.id)}/run`, { method: "POST" });
          await waitJob(job.id);
          await loadSignals();
        } catch (error) { window.alert(error.message); }
        finally { run.disabled = false; }
      });
      const remove = createElement("button", "ghost-danger", "删除");
      remove.addEventListener("click", async () => {
        if (!window.confirm(`删除监控目标“${target.name || target.target}”？已沉淀的数据不会被删除。`)) return;
        await api(`/api/signals/targets/${encodeURIComponent(target.id)}`, { method: "DELETE" });
        await loadSignals();
      });
      actions.append(run, remove);
      row.append(copy, actions);
      box.append(row);
    });
  }

  function scoreBadge(score) {
    if (!score) return '<span class="grade-badge unscored">未评分</span>';
    return `<span class="grade-badge ${score.grade.toLowerCase()}">${score.grade} · ${score.label}</span>`;
  }

  function renderSignalFeed() {
    const box = document.getElementById("signal-feed");
    box.replaceChildren();
    if (!studioState.feed.length) {
      box.append(createElement("div", "card-empty", "当前筛选下没有候选内容。"));
      return;
    }
    studioState.feed.forEach((item) => {
      const card = createElement("article", "signal-item");
      const top = createElement("div", "signal-item-top");
      const author = createElement("div");
      author.innerHTML = `<strong>${item.author_handle ? `@${item.author_handle}` : item.author_name || "未知作者"}</strong><small>${formatDate(item.discovered_at)}</small>`;
      top.innerHTML = scoreBadge(item.score);
      top.prepend(author);
      const text = createElement("p", "signal-text", item.text || "（无正文）");
      const stats = createElement("div", "signal-score-line");
      stats.textContent = item.score
        ? `R ${item.score.r_value.toFixed(2)} · M ${(item.score.m_value * 100).toFixed(2)}% · 速度 ${item.score.velocity.toFixed(1)}/h`
        : "等待指标快照";
      if (item.l1_analysis?.summary) {
        const summary = createElement("div", "signal-analysis-summary", item.l1_analysis.summary);
        card.append(top, text, stats, summary);
      } else card.append(top, text, stats);
      const actions = createElement("div", "signal-actions");
      ["l1", "l2"].forEach((level) => {
        const button = createElement("button", level === "l2" ? "primary-action" : "secondary-action", level === "l2" ? "深度拆解" : "快速分析");
        button.addEventListener("click", async () => {
          button.disabled = true;
          try {
            const job = await api(`/api/signals/candidates/${encodeURIComponent(item.candidate_id)}/analyze`, { method: "POST", body: JSON.stringify({ level }) });
            await waitJob(job.id);
            await loadSignals();
          } catch (error) { window.alert(error.message); }
          finally { button.disabled = false; }
        });
        actions.append(button);
      });
      const open = createElement("a", "tool-button", "在 X 查看 ↗");
      open.href = item.canonical_url;
      open.target = "_blank";
      open.rel = "noreferrer";
      actions.append(open);
      card.append(actions);
      box.append(card);
    });
  }

  function storedWritingMaterials() {
    try {
      const values = JSON.parse(window.localStorage.getItem(WRITING_MATERIALS_KEY) || "[]");
      return new Set(
        (Array.isArray(values) ? values : [])
          .map((value) => String(value).includes(":") ? String(value) : `source:${value}`),
      );
    } catch { return new Set(); }
  }

  function saveWritingMaterials() {
    try {
      window.localStorage.setItem(
        WRITING_MATERIALS_KEY,
        JSON.stringify([...studioState.selectedMaterialRefs]),
      );
    } catch {
      // Browser storage is optional.
    }
  }

  function writingMaterialGroup(material) {
    if (material.kind !== "source") return material.kind;
    if (material.platform === "pool") return "pool";
    if (["x", "xhs", "dy", "ks", "bili", "wb", "tieba", "zhihu"].includes(material.platform)) {
      return material.platform;
    }
    return "web";
  }

  function renderWritingMaterials() {
    const box = document.getElementById("writing-material-list");
    box.replaceChildren();
    const groups = new Map(WRITING_MATERIAL_GROUPS.map(([id, label]) => {
      const section = createElement("section", "writing-material-group");
      section.dataset.group = id;
      section.append(createElement("strong", "writing-material-group-title", label));
      section.append(createElement("div", "writing-material-group-items"));
      return [id, section];
    }));
    studioState.materials.forEach((material) => {
      const row = createElement("label", "writing-material-option");
      row.dataset.search = `${material.title} ${material.author} ${material.excerpt}`.toLowerCase();
      const input = document.createElement("input");
      input.type = "checkbox";
      input.value = material.ref;
      input.checked = studioState.selectedMaterialRefs.has(material.ref);
      input.addEventListener("change", () => {
        if (input.checked) studioState.selectedMaterialRefs.add(material.ref);
        else studioState.selectedMaterialRefs.delete(material.ref);
        saveWritingMaterials();
        updateWritingMaterialCount();
      });
      const copy = createElement("span", "writing-material-copy");
      const kind = material.kind === "source" ? "来源" : material.kind === "draft_revision" ? "草稿" : "平台稿";
      const version = material.version ? ` · v${material.version}` : "";
      copy.append(createElement("strong", "", `${kind}${version} · ${material.title || "未命名"}`));
      copy.append(createElement("small", "", material.excerpt || "无正文"));
      row.append(input, copy);
      groups.get(writingMaterialGroup(material))?.querySelector(".writing-material-group-items")?.append(row);
    });
    groups.forEach((group) => {
      if (group.querySelector(".writing-material-option")) box.append(group);
    });
    filterWritingMaterials();
    updateWritingMaterialCount();
  }

  function filterWritingMaterials() {
    const query = document.getElementById("writing-material-search")?.value.trim().toLowerCase() || "";
    document.querySelectorAll("#writing-material-list .writing-material-group").forEach((group) => {
      let visible = 0;
      group.querySelectorAll(".writing-material-option").forEach((row) => {
        const show = !query || row.dataset.search.includes(query);
        row.hidden = !show;
        if (show) visible += 1;
      });
      group.hidden = visible === 0;
    });
  }

  function updateWritingMaterialCount() {
    const target = document.getElementById("writing-material-count");
    if (target) target.textContent = `已选 ${studioState.selectedMaterialRefs.size} 个`;
  }

  function requiredWritingControl(form, id) {
    const control = form?.querySelector(`#${id}`);
    if (!control) throw new Error("深度写作表单未加载完整，请刷新页面后重试");
    return control;
  }

  function captureWritingProjectForm(form) {
    return {
      materialRefs: [...studioState.selectedMaterialRefs],
      pasteTitle: requiredWritingControl(form, "writing-paste-title").value,
      pasteAuthor: requiredWritingControl(form, "writing-paste-author").value,
      pasteUrl: requiredWritingControl(form, "writing-paste-url").value,
      pasteContent: requiredWritingControl(form, "writing-paste-content").value,
      mode: requiredWritingControl(form, "writing-mode").value,
      reader: requiredWritingControl(form, "writing-reader").value,
      promise: requiredWritingControl(form, "writing-promise").value,
      mainThesis: requiredWritingControl(form, "writing-thesis").value,
      styleProfileId: form?.querySelector("#writing-style-profile")?.value || null,
    };
  }

  async function fillWritingMaterials() {
    studioState.materials = await api("/api/writing/material-options?limit=500");
    if (!studioState.selectedMaterialRefs.size) {
      studioState.selectedMaterialRefs = storedWritingMaterials();
    }
    const valid = new Set(studioState.materials.map((item) => item.ref));
    studioState.selectedMaterialRefs = new Set(
      [...studioState.selectedMaterialRefs].filter((ref) => valid.has(ref)),
    );
    renderWritingMaterials();
  }

  async function materializeWritingPaste(formValues) {
    const text = formValues.pasteContent.trim();
    if (!text) return "";
    if (text.length < 20) throw new Error("粘贴材料请至少输入 20 个字符，或留空只使用库内材料");
    const source = await api("/api/sources/manual", {
      method: "POST",
      body: JSON.stringify({
        title: formValues.pasteTitle,
        author_name: formValues.pasteAuthor,
        canonical_url: formValues.pasteUrl,
        text_original: text,
      }),
    });
    return source.id;
  }

  async function loadWriting(selectId = null) {
    await fillWritingMaterials();
    studioState.projects = await api("/api/writing/projects");
    renderProjectList();
    const projectId = selectId || studioState.selectedProject?.id;
    if (projectId) await selectProject(projectId);
  }

  function renderProjectList() {
    const box = document.getElementById("writing-project-list");
    box.replaceChildren();
    if (!studioState.projects.length) {
      box.append(createElement("div", "card-empty", "还没有写作项目。普通来源可以继续用快速成稿；重要长文建议使用工作室模式。"));
      return;
    }
    studioState.projects.forEach((project) => {
      const button = createElement("button", `writing-project-item${studioState.selectedProject?.id === project.id ? " active" : ""}`);
      button.type = "button";
      button.dataset.projectId = project.id;
      button.innerHTML = `<strong>${project.promise || project.main_thesis || "未命名写作任务"}</strong><span>${project.mode === "studio" ? "工作室" : "快速"} · ${project.state}</span><small>${project.spent_estimate_cents}/${project.budget_limit_cents} 预算单位</small>`;
      button.addEventListener("click", () => selectProject(project.id));
      box.append(button);
    });
  }

  async function selectProject(projectId) {
    const project = await api(`/api/writing/projects/${encodeURIComponent(projectId)}`);
    studioState.selectedProject = project;
    renderProjectList();
    renderProjectDetail(project);
  }

  function artifactLabel(type) {
    return {
      source_selection: "冻结的输入材料与事实来源", editorial_brief: "总编辑任务单", evidence_pack: "证据包", outline: "文章大纲",
      style_exemplar_bundle: "冻结的授权风格短范例", title_candidates: "标题候选", title_tournament: "标题锦标赛",
      title_preference: "作者标题选择",
      draft: "初稿", reader_review: "读者审稿", fact_review: "事实审稿",
      style_review: "风格审稿", revision_plan: "主编修改计划", final_draft: "终稿",
      final_claims: "终稿 Claims", claim_evidence_matrix: "Claim-Evidence Matrix",
      author_decision: "作者决定",
    }[type] || type;
  }

  function artifactPayload(artifact) {
    try { return JSON.parse(artifact?.content_json || "{}"); }
    catch { return {}; }
  }

  function latestProjectArtifact(project, type) {
    return [...(project.artifacts || [])].reverse().find((item) => item.artifact_type === type) || null;
  }

  function renderTitleTournament(project, artifact, payload) {
    const panel = createElement("section", "title-tournament-panel");
    const head = createElement("div", "title-tournament-head");
    head.innerHTML = `<strong>读者第一眼 Top ${payload.top_five?.length || 0}</strong><span>${payload.quality_gate_passed ? "质量门通过" : "候选不足，当前为降级结果"}</span>`;
    panel.append(head);
    const preferenceArtifact = latestProjectArtifact(project, "title_preference");
    const preference = artifactPayload(preferenceArtifact);
    const list = createElement("ol", "title-tournament-list");
    (payload.top_five || []).forEach((item) => {
      const candidate = item.candidate || {};
      const row = createElement("li", "title-tournament-option");
      const copy = createElement("div");
      copy.append(
        createElement("strong", "", candidate.title || "未命名候选"),
        createElement("small", "", `${candidate.mechanism || "unknown"} · 第一眼 ${Number(item.reader_first_glance?.total_score || 0).toFixed(1)} · ${candidate.reader_promise || ""}`),
      );
      const selected = preference.tournament_artifact_id === artifact.id && preference.candidate_id === candidate.candidate_id;
      const qualityReady = Boolean(payload.quality_gate_passed);
      const button = createElement("button", selected ? "primary-action" : "secondary-action", selected ? "已选择" : qualityReady ? "选择这个标题" : "质量门未通过");
      button.type = "button";
      button.disabled = selected || !qualityReady;
      button.addEventListener("click", async () => {
        button.disabled = true;
        try {
          await api(`/api/writing/projects/${encodeURIComponent(project.id)}/titles/select`, {
            method: "POST",
            body: JSON.stringify({
              tournament_artifact_id: artifact.id,
              candidate_id: candidate.candidate_id,
              note: "作者在标题锦标赛 top 5 中明确选择",
            }),
          });
          await loadWriting(project.id);
        } catch (error) {
          window.alert(error.message);
          button.disabled = false;
        }
      });
      row.append(copy, button);
      list.append(row);
    });
    if (!list.children.length) {
      list.append(createElement("li", "card-empty", "当前没有通过证据与标题质量过滤的候选；写作仍可降级继续，但不会伪称标题锦标赛已通过。"));
    }
    panel.append(list);
    return panel;
  }

  function feedbackArticleType(project) {
    const brief = artifactPayload(latestProjectArtifact(project, "editorial_brief"));
    return brief.article_type || "technical_explainer";
  }

  async function hydrateWritingFeedback(project, panel) {
    if (!project.output_draft_id) return;
    try {
      const [drafts, feedbacks] = await Promise.all([
        api(`/api/sources/${encodeURIComponent(project.source_id)}/drafts`),
        api(`/api/writing/projects/${encodeURIComponent(project.id)}/feedback`),
      ]);
      const modelDraft = drafts.find((item) => item.id === project.output_draft_id);
      if (!modelDraft) throw new Error("没有找到当前项目冻结的模型终稿");
      panel.replaceChildren();
      const heading = createElement("div", "panel-heading");
      heading.innerHTML = '<div><span class="section-kicker">REAL REVISION FEEDBACK</span><h4>人工终稿与真实改稿反馈</h4><p>先保存人工版本，再由服务端计算不可伪造的 diff；之后可单独批准进入池子记忆。</p></div>';
      panel.append(heading);

      const form = createElement("form", "writing-feedback-form");
      const titleLabel = createElement("label", "", "人工终稿标题");
      const titleInput = document.createElement("input");
      titleInput.maxLength = 80;
      titleInput.required = true;
      titleInput.value = modelDraft.title || "";
      titleLabel.append(titleInput);
      const bodyLabel = createElement("label", "", "人工终稿正文");
      const bodyInput = document.createElement("textarea");
      bodyInput.rows = 16;
      bodyInput.maxLength = 50000;
      bodyInput.required = true;
      bodyInput.value = modelDraft.body || "";
      bodyLabel.append(bodyInput);
      const tagsLabel = createElement("label", "", "标签");
      const tagsInput = document.createElement("input");
      tagsInput.maxLength = 500;
      tagsInput.value = modelDraft.tags || "";
      tagsLabel.append(tagsInput);
      const reasonLabel = createElement("label", "", "为什么这样改");
      const reasonInput = document.createElement("textarea");
      reasonInput.rows = 4;
      reasonInput.maxLength = 4000;
      reasonInput.required = true;
      reasonInput.placeholder = "指出标题、开头、节奏、判断或禁用表达中哪些变化代表你的真实偏好。";
      reasonLabel.append(reasonInput);
      const articleTypeLabel = createElement("label", "", "文章类型");
      const articleTypeInput = document.createElement("input");
      articleTypeInput.maxLength = 80;
      articleTypeInput.required = true;
      articleTypeInput.value = feedbackArticleType(project);
      articleTypeLabel.append(articleTypeInput);
      const dimensions = [
        ["title", "标题"], ["opening", "开头"], ["tone", "语气"],
        ["sentence_rhythm", "句子节奏"], ["paragraph_rhythm", "段落节奏"],
        ["structure", "结构"], ["transition", "转场"], ["judgment", "判断方式"],
        ["ending", "结尾"], ["forbidden_expression", "禁用表达"],
        ["reader_relationship", "读者关系"], ["identity", "作者身份"],
        ["positive_phrase", "正向表达"],
      ];
      const dimensionField = createElement("fieldset", "writing-feedback-dimensions");
      dimensionField.append(createElement("legend", "", "受影响维度（至少一项）"));
      dimensions.forEach(([value, label], index) => {
        const option = createElement("label", "", label);
        const input = document.createElement("input");
        input.type = "checkbox";
        input.value = value;
        input.checked = index < 3;
        option.prepend(input);
        dimensionField.append(option);
      });
      const submit = createElement("button", "primary-action", "保存人工版本并记录反馈");
      submit.type = "submit";
      form.append(titleLabel, bodyLabel, tagsLabel, articleTypeLabel, reasonLabel, dimensionField, submit);
      form.addEventListener("submit", async (event) => {
        event.preventDefault();
        const selected = [...dimensionField.querySelectorAll('input[type="checkbox"]:checked')].map((item) => item.value);
        if (!selected.length) {
          window.alert("请至少选择一个受影响维度");
          return;
        }
        submit.disabled = true;
        try {
          const humanDraft = await api(`/api/drafts/${encodeURIComponent(modelDraft.id)}`, {
            method: "PUT",
            body: JSON.stringify({ title: titleInput.value, body: bodyInput.value, tags: tagsInput.value }),
          });
          await api(`/api/writing/projects/${encodeURIComponent(project.id)}/feedback`, {
            method: "POST",
            body: JSON.stringify({
              draft_before_id: modelDraft.id,
              draft_after_id: humanDraft.id,
              article_type: articleTypeInput.value,
              feedback_reason: reasonInput.value,
              affected_dimensions: selected,
            }),
          });
          await loadWriting(project.id);
        } catch (error) {
          window.alert(error.message);
          submit.disabled = false;
        }
      });
      panel.append(form);

      const history = createElement("div", "writing-feedback-history");
      if (!feedbacks.length) history.append(createElement("div", "card-empty", "尚未记录真实改稿反馈。"));
      feedbacks.forEach((feedback) => {
        const card = createElement("article", "writing-feedback-card");
        const delta = Number(feedback.diff?.changes?.body_character_delta || 0);
        card.append(
          createElement("strong", "", feedback.feedback_reason || "真实改稿反馈"),
          createElement("small", "", `${feedback.article_type || "未分类"} · ${feedback.affected_dimensions.join(" / ")} · 正文 ${delta >= 0 ? "+" : ""}${delta} 字符`),
        );
        const memory = createElement("button", feedback.approved_to_memory ? "primary-action" : "secondary-action", feedback.approved_to_memory ? "已批准进入记忆" : "预览并决定是否进入记忆");
        memory.type = "button";
        memory.disabled = feedback.approved_to_memory;
        memory.dataset.memorySourceKind = "writing_feedback";
        memory.dataset.memorySourceId = feedback.id;
        card.append(memory);
        history.append(card);
      });
      panel.append(history);
    } catch (error) {
      panel.replaceChildren(createElement("div", "card-empty", `真实反馈面板加载失败：${error.message}`));
    }
  }

  function renderProjectDetail(project) {
    document.getElementById("writing-empty").hidden = true;
    const box = document.getElementById("writing-detail");
    box.hidden = false;
    box.replaceChildren();
    const header = createElement("div", "project-detail-header");
    header.innerHTML = `<div><span class="section-kicker">${project.mode.toUpperCase()} MODE</span><h3>${project.promise || "写作项目"}</h3><p>${project.reader || "尚未明确读者"}</p></div><div class="project-state"><strong>${project.state}</strong><small>${project.current_stage}</small></div>`;
    const actions = createElement("div", "project-run-actions");
    const run = createElement("button", "primary-action", project.state.startsWith("awaiting_") ? "等待作者确认" : project.state === "claims_blocked" ? "证据闸门阻断" : project.state === "completed" ? "已完成" : "运行下一阶段");
    run.disabled = project.state.startsWith("awaiting_") || ["claims_blocked", "completed", "failed", "canceled"].includes(project.state);
    run.addEventListener("click", async () => {
      run.disabled = true;
      try {
        const job = await api(`/api/writing/projects/${encodeURIComponent(project.id)}/run`, { method: "POST", body: JSON.stringify({ continuous: true }) });
        await waitJob(job.id, 300000);
        await loadWriting(project.id);
      } catch (error) { window.alert(error.message); }
      finally { run.disabled = false; }
    });
    actions.append(run);
    header.append(actions);
    box.append(header);
    if (project.material_summaries?.length || project.source_summaries?.length) {
      const evidence = createElement("div", "platform-helper");
      const values = project.material_summaries?.length ? project.material_summaries : project.source_summaries;
      evidence.textContent = `冻结输入：${values
        .map((item) => `${item.kind === "draft_revision" ? "草稿" : item.kind === "platform_variant" ? "平台稿" : item.role === "primary" ? "主来源" : "来源"}·${item.title || item.author || item.id}`)
        .join(" ｜ ")}`;
      box.append(evidence);
    }

    const timeline = createElement("div", "artifact-timeline");
    project.artifacts.forEach((artifact) => {
      const item = createElement("article", "artifact-card");
      const itemHeader = createElement("div", "artifact-header");
      itemHeader.innerHTML = `<div><span>${artifactLabel(artifact.artifact_type)}</span><small>${artifact.created_by_role} · v${artifact.version}</small></div><strong>${artifact.approved ? "已确认" : "待确认"}</strong>`;
      const parsed = artifactPayload(artifact);
      const content = artifact.artifact_type === "title_tournament"
        ? renderTitleTournament(project, artifact, parsed)
        : createElement("pre", "artifact-content");
      if (artifact.artifact_type !== "title_tournament") content.textContent = JSON.stringify(parsed, null, 2);
      item.append(itemHeader, content);
      if (["editorial_brief", "outline", "revision_plan"].includes(artifact.artifact_type) && !artifact.approved) {
        const approval = createElement("div", "artifact-approval");
        const approve = createElement("button", "primary-action", "确认并继续");
        const reject = createElement("button", "ghost-danger", "退回");
        approve.addEventListener("click", () => approveArtifact(project.id, artifact.id, true));
        reject.addEventListener("click", () => approveArtifact(project.id, artifact.id, false));
        approval.append(reject, approve);
        item.append(approval);
      }
      if (artifact.artifact_type === "final_draft") {
        const memoryAction = createElement("div", "artifact-approval");
        const memoryButton = createElement("button", "secondary-action", "提炼为写作偏好");
        memoryButton.type = "button";
        memoryButton.dataset.memorySourceKind = "writing_artifact";
        memoryButton.dataset.memorySourceId = artifact.id;
        memoryAction.append(memoryButton);
        item.append(memoryAction);
      }
      timeline.append(item);
    });
    box.append(timeline);
    if (project.output_draft_id) {
      const feedbackPanel = createElement("section", "surface studio-panel writing-feedback-panel");
      feedbackPanel.append(createElement("div", "card-empty", "正在加载人工终稿与真实反馈…"));
      box.append(feedbackPanel);
      void hydrateWritingFeedback(project, feedbackPanel);
    }
  }

  async function approveArtifact(projectId, artifactId, approved) {
    const note = approved ? "作者确认阶段产物" : window.prompt("写下退回原因") || "作者退回";
    await api(`/api/writing/projects/${encodeURIComponent(projectId)}/artifacts/${encodeURIComponent(artifactId)}/approve`, { method: "POST", body: JSON.stringify({ approved, note }) });
    await loadWriting(projectId);
  }

  function bindStudioEvents() {
    document.getElementById("refresh-signals").addEventListener("click", loadSignals);
    document.getElementById("signal-grade").addEventListener("change", loadSignals);
    document.getElementById("monitor-form").addEventListener("submit", async (event) => {
      event.preventDefault();
      const button = event.submitter;
      if (button) button.disabled = true;
      try {
        const target = await api("/api/signals/targets", {
          method: "POST",
          body: JSON.stringify({
            name: document.getElementById("monitor-name").value,
            kind: document.getElementById("monitor-kind").value,
            target: document.getElementById("monitor-target").value,
            interval_minutes: Number(document.getElementById("monitor-interval").value || 360),
            enabled: true,
            config: { count: 30 },
          }),
        });
        event.target.reset();
        document.getElementById("monitor-interval").value = "360";
        const job = await api(`/api/signals/targets/${encodeURIComponent(target.id)}/run`, { method: "POST" });
        await waitJob(job.id);
        await loadSignals();
      } catch (error) { window.alert(error.message); }
      finally { if (button) button.disabled = false; }
    });
    document.getElementById("refresh-writing").addEventListener("click", () => loadWriting());
    document.getElementById("writing-back-wechat").addEventListener("click", () => window.setView?.("wechat-view"));
    document.getElementById("writing-material-search").addEventListener("input", filterWritingMaterials);
    document.getElementById("writing-material-clear").addEventListener("click", () => {
      studioState.selectedMaterialRefs.clear();
      saveWritingMaterials();
      renderWritingMaterials();
    });
    document.getElementById("writing-project-form").addEventListener("submit", async (event) => {
      event.preventDefault();
      const button = event.submitter;
      if (button) button.disabled = true;
      try {
        const formValues = captureWritingProjectForm(event.currentTarget);
        const pastedSourceId = await materializeWritingPaste(formValues);
        const materialRefs = [...formValues.materialRefs];
        if (pastedSourceId) materialRefs.push(`source:${pastedSourceId}`);
        const uniqueRefs = [...new Set(materialRefs)];
        if (!uniqueRefs.length) throw new Error("请至少选择一个库内材料或粘贴一段内容");
        const selectedOptions = uniqueRefs
          .map((ref) => studioState.materials.find((item) => item.ref === ref))
          .filter(Boolean);
        const sourceId = selectedOptions[0]?.source_id || pastedSourceId;
        if (!sourceId) throw new Error("输入材料没有可追溯的来源");
        const supportingSourceIds = [...new Set([
          ...selectedOptions
            .filter((item) => item.kind === "source" && item.source_id !== sourceId)
            .map((item) => item.source_id),
          ...(pastedSourceId && pastedSourceId !== sourceId ? [pastedSourceId] : []),
        ])];
        const project = await api("/api/writing/projects", {
          method: "POST",
          body: JSON.stringify({
            source_id: sourceId,
            supporting_source_ids: supportingSourceIds,
            material_refs: uniqueRefs,
            mode: formValues.mode,
            reader: formValues.reader,
            promise: formValues.promise,
            main_thesis: formValues.mainThesis,
            style_profile_id: formValues.styleProfileId,
            budget_limit_cents: formValues.mode === "studio" ? 20 : 10,
          }),
        });
        const job = await api(`/api/writing/projects/${encodeURIComponent(project.id)}/run`, { method: "POST", body: JSON.stringify({ continuous: true }) });
        await waitJob(job.id, 300000);
        await loadWriting(project.id);
      } catch (error) { window.alert(error.message); }
      finally { if (button) button.disabled = false; }
    });
  }

  injectNavigation();
  injectViews();
  bindStudioEvents();
  window.openX2redDeepWriting = async (sourceId = "", supportingIds = [], materialRefs = []) => {
    window.setView?.("writing-view");
    const selected = new Set(
      (Array.isArray(materialRefs) && materialRefs.length
        ? materialRefs
        : [sourceId, ...(Array.isArray(supportingIds) ? supportingIds : [])]
      )
        .filter(Boolean)
        .map((value) => String(value).includes(":") ? String(value) : `source:${value}`),
    );
    studioState.selectedMaterialRefs = selected;
    saveWritingMaterials();
    await loadWriting();
    renderWritingMaterials();
    document.getElementById("writing-project-form")?.scrollIntoView({ behavior: "smooth", block: "start" });
  };
  window.openX2redWritingProject = async (projectId) => {
    if (!projectId) return;
    window.setView?.("writing-view");
    await loadWriting(projectId);
    const detail = document.getElementById("writing-detail");
    const behavior = window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth";
    detail?.scrollIntoView({ behavior, block: "start" });
    detail?.querySelector("button:not(:disabled), [tabindex]")?.focus({ preventScroll: true });
  };
})();
