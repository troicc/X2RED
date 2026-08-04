(() => {
  const studioState = { targets: [], feed: [], projects: [], selectedProject: null };

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
    const writingButton = createElement("button", "nav-item");
    writingButton.dataset.view = "writing-view";
    writingButton.innerHTML = '<span class="nav-icon">✎</span><span>写作项目</span>';
    nav.insertBefore(signalButton, publish);
    nav.insertBefore(writingButton, publish);
    [signalButton, writingButton].forEach((button) => {
      button.addEventListener("click", () => window.setView(button.dataset.view));
    });
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
        <span class="section-kicker">MULTI-AGENT WRITING ROOM</span><h2>写作项目</h2>
        <p>总编辑、证据研究、大纲、写手、读者审稿、事实审稿、风格审稿与资深主编通过阶段产物交接。</p>
      </section>
      <section class="studio-two-column writing-layout">
        <article class="surface studio-panel">
          <div class="panel-heading"><div><span class="section-kicker">NEW PROJECT</span><h3>建立写作任务</h3></div><button id="refresh-writing" class="secondary-action" type="button">刷新</button></div>
          <form id="writing-project-form" class="writing-project-form">
            <label>来源<select id="writing-source" required></select></label>
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
    const titles = { "signals-view": "信号台", "writing-view": "写作项目" };
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

  async function fillWritingSources() {
    const sources = await api("/api/sources?workspace_state=active");
    const select = document.getElementById("writing-source");
    const current = select.value;
    select.replaceChildren();
    sources.forEach((source) => {
      const option = document.createElement("option");
      option.value = source.id;
      option.textContent = `${source.author_handle ? `@${source.author_handle}` : source.author_name || "未知作者"} · ${(source.text_original || "").slice(0, 50)}`;
      select.append(option);
    });
    if (current && sources.some((source) => source.id === current)) select.value = current;
  }

  async function loadWriting(selectId = null) {
    await fillWritingSources();
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
      editorial_brief: "总编辑任务单", evidence_pack: "证据包", outline: "文章大纲",
      draft: "初稿", reader_review: "读者审稿", fact_review: "事实审稿",
      style_review: "风格审稿", revision_plan: "主编修改计划", final_draft: "终稿",
      author_decision: "作者决定",
    }[type] || type;
  }

  function renderProjectDetail(project) {
    document.getElementById("writing-empty").hidden = true;
    const box = document.getElementById("writing-detail");
    box.hidden = false;
    box.replaceChildren();
    const header = createElement("div", "project-detail-header");
    header.innerHTML = `<div><span class="section-kicker">${project.mode.toUpperCase()} MODE</span><h3>${project.promise || "写作项目"}</h3><p>${project.reader || "尚未明确读者"}</p></div><div class="project-state"><strong>${project.state}</strong><small>${project.current_stage}</small></div>`;
    const actions = createElement("div", "project-run-actions");
    const run = createElement("button", "primary-action", project.state.startsWith("awaiting_") ? "等待作者确认" : project.state === "completed" ? "已完成" : "运行下一阶段");
    run.disabled = project.state.startsWith("awaiting_") || ["completed", "failed", "canceled"].includes(project.state);
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

    const timeline = createElement("div", "artifact-timeline");
    project.artifacts.forEach((artifact) => {
      const item = createElement("article", "artifact-card");
      const itemHeader = createElement("div", "artifact-header");
      itemHeader.innerHTML = `<div><span>${artifactLabel(artifact.artifact_type)}</span><small>${artifact.created_by_role} · v${artifact.version}</small></div><strong>${artifact.approved ? "已确认" : "待确认"}</strong>`;
      const content = createElement("pre", "artifact-content");
      try { content.textContent = JSON.stringify(JSON.parse(artifact.content_json), null, 2); }
      catch { content.textContent = artifact.content_json; }
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
        const memoryButton = createElement("button", "secondary-action", "加入池子记忆");
        memoryButton.type = "button";
        memoryButton.dataset.memorySourceKind = "writing_artifact";
        memoryButton.dataset.memorySourceId = artifact.id;
        memoryAction.append(memoryButton);
        item.append(memoryAction);
      }
      timeline.append(item);
    });
    box.append(timeline);
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
      button.disabled = true;
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
      finally { button.disabled = false; }
    });
    document.getElementById("refresh-writing").addEventListener("click", () => loadWriting());
    document.getElementById("writing-project-form").addEventListener("submit", async (event) => {
      event.preventDefault();
      const button = event.submitter;
      button.disabled = true;
      try {
        const project = await api("/api/writing/projects", {
          method: "POST",
          body: JSON.stringify({
            source_id: document.getElementById("writing-source").value,
            mode: document.getElementById("writing-mode").value,
            reader: document.getElementById("writing-reader").value,
            promise: document.getElementById("writing-promise").value,
            main_thesis: document.getElementById("writing-thesis").value,
            budget_limit_cents: document.getElementById("writing-mode").value === "studio" ? 20 : 10,
          }),
        });
        const job = await api(`/api/writing/projects/${encodeURIComponent(project.id)}/run`, { method: "POST", body: JSON.stringify({ continuous: true }) });
        await waitJob(job.id, 300000);
        await loadWriting(project.id);
      } catch (error) { window.alert(error.message); }
      finally { button.disabled = false; }
    });
  }

  injectNavigation();
  injectViews();
  bindStudioEvents();
})();
