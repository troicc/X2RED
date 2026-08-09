(() => {
  const uxState = {
    project: null,
    lastFocusKey: "",
    busy: false,
    scheduled: false,
  };

  const approvalTypes = new Set(["editorial_brief", "outline", "revision_plan"]);
  const artifactNames = {
    source_selection: "冻结的输入材料",
    editorial_brief: "总编辑任务单",
    evidence_pack: "证据包",
    outline: "文章大纲",
    draft: "公众号完整初稿",
    reader_review: "读者审稿",
    fact_review: "事实审稿",
    style_review: "风格审稿",
    revision_plan: "主编修改计划",
    final_draft: "深度写作终稿",
    author_decision: "作者决定",
  };
  const stageNames = {
    clarifying: "总编辑正在建立任务单",
    researching: "证据研究员正在整理材料",
    outlining: "结构 Agent 正在制作大纲",
    drafting: "写手正在生成公众号完整初稿",
    reviewing: "三路审稿与主编正在工作",
    revising: "终稿 Agent 正在执行修改",
    awaiting_brief_approval: "请确认总编辑任务单",
    awaiting_outline_approval: "请确认文章大纲",
    awaiting_revision_approval: "请确认主编修改计划",
    completed: "深度终稿完成，等待公众号成稿",
    failed: "项目执行失败",
    canceled: "项目已取消",
  };
  const artifactGuides = {
    source_selection: {
      verb: "冻结输入",
      reads: "素材库来源、已写版本和粘贴材料",
      writes: "本项目不可变的材料引用、事实来源和 provenance",
      optimize: "材料缺失或事实范围不对时，回到公众号阶段 01 调整来源。",
      skill: "人工选择",
    },
    editorial_brief: {
      verb: "产生任务单",
      reads: "输入材料、目标读者、文章承诺和核心判断",
      writes: "单一主线、必须使用、禁止主张和成功标准",
      optimize: "主线或读者定位不准时，调整这里；不要先改写手。",
      skill: "writing.editor",
    },
    evidence_pack: {
      verb: "产生证据",
      reads: "任务单和全部事实来源",
      writes: "事实、数字、来源引文、未知项和材料缺口",
      optimize: "事实遗漏、来源归属或比较维度有问题时，调整这里。",
      skill: "writing.research",
    },
    outline: {
      verb: "产生结构",
      reads: "任务单、证据包和写作偏好",
      writes: "开头、章节顺序、证据分配、目标篇幅和转场",
      optimize: "文章顺序、章节职责或认知负荷不顺时，调整这里。",
      skill: "writing.outline",
    },
    draft: {
      verb: "产生正文",
      reads: "原始材料、任务单、证据包、大纲和写作偏好",
      writes: "1800—4500 字、3—6 个 H2 的公众号完整初稿",
      optimize: "叙事、例子、节奏和表达质量有问题时，调整这里。",
      skill: "writing.writer",
    },
    reader_review: {
      verb: "检查理解",
      reads: "目标读者、文章大纲和完整初稿",
      writes: "退出点、术语阻力、数字解释和最小修改建议",
      optimize: "文章难懂、第一屏弱或阅读节奏差时，调整这里。",
      skill: "review.reader",
    },
    fact_review: {
      verb: "检查事实",
      reads: "完整初稿和证据包",
      writes: "无支持主张、范围扩大、数字错误和归属问题",
      optimize: "事实准确性或证据追溯有问题时，调整这里。",
      skill: "review.fact",
    },
    style_review: {
      verb: "检查风格",
      reads: "完整初稿和写作偏好",
      writes: "AI 腔、节奏、模板转场和身份偏差",
      optimize: "语言像报告、太均匀或不像你时，调整这里。",
      skill: "review.style",
    },
    revision_plan: {
      verb: "产生修改单",
      reads: "三份审稿报告和完整初稿",
      writes: "必须修、建议修、拒绝建议和最终修改指令",
      optimize: "审稿意见冲突或修改优先级不合理时，调整这里。",
      skill: "writing.chief_editor",
    },
    final_draft: {
      verb: "修改正文",
      reads: "完整初稿、修改单、证据包和原始材料",
      writes: "不缩短主线、通过完整度门禁的深度写作终稿",
      optimize: "修改执行不完整、文章被压短或引入新问题时，调整这里。",
      skill: "writing.final_revision",
    },
    author_decision: {
      verb: "记录决定",
      reads: "你的确认、退回原因和阶段反馈",
      writes: "后续 Agent 必须优先执行的作者决定",
      optimize: "反馈越具体，下一轮越容易只修目标问题。",
      skill: "人工反馈",
    },
  };
  const deepStages = [
    { key: "brief", number: "01", title: "任务定义", types: ["editorial_brief"], roles: ["editor_in_chief"] },
    { key: "evidence", number: "02", title: "证据研究", types: ["evidence_pack"], roles: ["evidence_researcher"] },
    { key: "outline", number: "03", title: "文章结构", types: ["outline"], roles: ["outline_architect"] },
    { key: "draft", number: "04", title: "完整初稿", types: ["draft"], roles: ["writer"] },
    { key: "reviews", number: "05", title: "三路审稿", types: ["reader_review", "fact_review", "style_review"], roles: ["reader_reviewer", "fact_reviewer", "style_reviewer"] },
    { key: "plan", number: "06", title: "修改裁决", types: ["revision_plan"], roles: ["chief_editor"] },
    { key: "final", number: "07", title: "终稿修订", types: ["final_draft"], roles: ["final_reviser"] },
    { key: "handoff", number: "08", title: "公众号成稿", types: [], roles: [] },
  ];

  function scheduleEnhance() {
    if (uxState.scheduled) return;
    uxState.scheduled = true;
    window.requestAnimationFrame(() => {
      uxState.scheduled = false;
      enhanceProjectDetail();
    });
  }

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
        scheduleEnhance();
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

  function latestRun(project, roles = [], artifactId = "") {
    const runs = [...(project.runs || [])].reverse();
    if (artifactId) {
      const exact = runs.find((run) => run.output_artifact_id === artifactId);
      if (exact) return exact;
    }
    return runs.find((run) => roles.includes(run.role)) || null;
  }

  function runDescription(run) {
    if (!run) return "模型：未执行或人工环节";
    const model = run.model_name || "确定性回退";
    const effort = run.reasoning_effort ? ` · 推理 ${run.reasoning_effort}` : "";
    const attempts = run.attempts > 1 ? ` · ${run.attempts} 次尝试` : "";
    return `模型：${model}${effort}${attempts}`;
  }

  function guideForStage(stage) {
    if (stage.key === "reviews") {
      return {
        verb: "并行检查",
        reads: "完整初稿、证据包、目标读者和写作偏好",
        writes: "读者理解、事实准确、语言风格三份独立审稿报告",
        optimize: "难懂看读者审稿，事实问题看事实审稿，AI 腔看风格审稿。",
        skill: "review.reader / review.fact / review.style",
      };
    }
    if (stage.key === "handoff") {
      return {
        verb: "产生平台稿",
        reads: "原始证据、深度写作终稿和公众号成稿设置",
        writes: "1800—4500 字公众号 PlatformVariant，不覆盖深度终稿",
        optimize: "整体叙事、公众号阅读节奏、标题和完整度在公众号工作台调整。",
        skill: "wechat.adapt_longform",
      };
    }
    return artifactGuides[stage.types[0]] || {
      verb: "处理内容",
      reads: "上一步产物",
      writes: "本阶段产物",
      optimize: "检查本阶段输入、Prompt、模型和人工反馈。",
      skill: "未记录",
    };
  }

  function activeDeepStageIndex(project) {
    if (project.wechat_variant_id) return 7;
    const stage = project.current_stage || "";
    const state = project.state || "";
    if (["completed"].includes(stage) || state === "completed") return 7;
    if (["final_revision"].includes(stage) || state === "revising") return 6;
    if (["approve_revision_plan"].includes(stage) || state === "awaiting_revision_approval") return 5;
    if (["parallel_reviews"].includes(stage) || state === "reviewing") return 4;
    if (["draft"].includes(stage) || state === "drafting") return 3;
    if (["outline", "approve_outline"].includes(stage) || ["outlining", "awaiting_outline_approval"].includes(state)) return 2;
    if (["evidence_pack"].includes(stage) || state === "researching") return 1;
    return 0;
  }

  function deepStageState(project, stage, index, activeIndex) {
    if (stage.key === "handoff") {
      if (project.wechat_variant_id) return { kind: "complete", label: `公众号 v${project.wechat_variant_version || ""}` };
      if (project.state === "completed") return { kind: "active", label: "下一步" };
      return { kind: "waiting", label: "待终稿" };
    }
    const artifacts = stage.types.map((type) => latestArtifact(project, (item) => item.artifact_type === type));
    const complete = artifacts.every(Boolean);
    const waitingApproval = artifacts.some((artifact) => artifact && approvalTypes.has(artifact.artifact_type) && !artifact.approved);
    if (project.state === "failed" && index === activeIndex) return { kind: "error", label: "失败" };
    if (waitingApproval && index === activeIndex) return { kind: "waiting", label: "等你确认" };
    if (complete && (index < activeIndex || project.state === "completed")) return { kind: "complete", label: "已产出" };
    if (index === activeIndex) return { kind: "active", label: complete ? "处理中" : "当前" };
    return { kind: complete ? "complete" : "waiting", label: complete ? "已产出" : "待开始" };
  }

  function stageRunDescription(project, stage) {
    if (stage.key === "handoff") return "模型路由：在公众号工作台查看 Skill 配置";
    const descriptions = stage.roles.map((role) => latestRun(project, [role])).filter(Boolean);
    if (!descriptions.length) return "模型：尚未执行";
    const labels = [...new Set(descriptions.map((run) => runDescription(run).replace(/^模型：/, "")))];
    return `模型：${labels.join(" ｜ ")}`;
  }

  function scrollToStageArtifact(project, stage) {
    if (stage.key === "handoff") {
      if (project.state === "completed" && typeof window.openX2redWechatForProject === "function") {
        window.openX2redWechatForProject(project).catch((error) => window.alert(error.message));
      }
      return;
    }
    const artifact = latestArtifact(project, (item) => stage.types.includes(item.artifact_type));
    const card = artifact && document.querySelector(`.artifact-card[data-artifact-id="${CSS.escape(artifact.id)}"]`);
    if (!card) return;
    card.classList.remove("collapsed");
    const toggle = card.querySelector(".artifact-toggle");
    if (toggle) toggle.textContent = "收起";
    card.scrollIntoView({ behavior: "smooth", block: "center" });
  }

  function buildStageMap(project) {
    const map = document.createElement("section");
    map.className = "writing-stage-map";
    map.setAttribute("aria-labelledby", "writing-stage-map-title");
    const activeIndex = activeDeepStageIndex(project);
    const head = document.createElement("header");
    const copy = document.createElement("div");
    copy.innerHTML = '<span class="section-kicker">DEEP WRITING TRACE</span><h4 id="writing-stage-map-title">深度写作内部流程</h4><p>点击已有阶段可定位产物；每一步都显示读取、输出、Skill 和实际模型。</p>';
    const progress = document.createElement("span");
    progress.className = "writing-stage-progress";
    progress.textContent = project.wechat_variant_id
      ? "8 / 8 · 已进入公众号"
      : `当前 ${Math.min(activeIndex + 1, 8)} / 8 · ${deepStages[activeIndex].title}`;
    head.append(copy, progress);

    const list = document.createElement("ol");
    list.className = "writing-stage-list";
    deepStages.forEach((stage, index) => {
      const state = deepStageState(project, stage, index, activeIndex);
      const guide = guideForStage(stage);
      const item = document.createElement("li");
      item.className = `writing-stage-item is-${state.kind}${index === activeIndex ? " is-current" : ""}`;
      const button = document.createElement("button");
      button.type = "button";
      button.className = "writing-stage-button";
      button.setAttribute("aria-label", `阶段 ${stage.number}：${stage.title}，${state.label}`);
      if (index === activeIndex) button.setAttribute("aria-current", "step");
      const top = document.createElement("span");
      top.className = "writing-stage-top";
      const number = document.createElement("span");
      number.className = "writing-stage-number";
      number.textContent = stage.number;
      const verb = document.createElement("span");
      verb.className = "writing-stage-verb";
      verb.textContent = guide.verb;
      const status = document.createElement("span");
      status.className = "writing-stage-state";
      status.textContent = state.label;
      top.append(number, verb, status);
      const title = document.createElement("strong");
      title.textContent = stage.title;
      const io = document.createElement("span");
      io.className = "writing-stage-io";
      const reads = document.createElement("small");
      reads.textContent = `读取：${guide.reads}`;
      const writes = document.createElement("small");
      writes.textContent = `输出：${guide.writes}`;
      io.append(reads, writes);
      const route = document.createElement("span");
      route.className = "writing-stage-route";
      route.textContent = `${guide.skill} · ${stageRunDescription(project, stage)}`;
      const optimize = document.createElement("small");
      optimize.className = "writing-stage-optimize";
      optimize.textContent = `优化：${guide.optimize}`;
      button.append(top, title, io, route, optimize);
      button.addEventListener("click", () => scrollToStageArtifact(project, stage));
      item.appendChild(button);
      list.appendChild(item);
    });
    map.append(head, list);
    return map;
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

  function resetDock() {
    uxState.busy = false;
    const detail = document.getElementById("writing-detail");
    if (detail) delete detail.dataset.uxFingerprint;
    scheduleEnhance();
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
      resetDock();
    }
  }

  async function rejectArtifact(project, artifact, dock) {
    if (uxState.busy) return;
    const note = window.prompt("写下需要修改的地方。Agent 会按这条反馈重新生成当前阶段。", "");
    if (note === null) return;
    setDockBusy(dock, "正在退回并重新生成当前阶段…");
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
      resetDock();
    }
  }

  async function continueProject(project, dock) {
    if (uxState.busy) return;
    setDockBusy(dock, "正在运行到下一个确认点…");
    try {
      const job = await api(`/api/writing/projects/${encodeURIComponent(project.id)}/run`, {
        method: "POST",
        body: JSON.stringify({ continuous: true }),
      });
      await waitJob(job.id);
      refreshSelectedProject();
    } catch (error) {
      window.alert(error.message);
      resetDock();
    }
  }

  async function handoffToWechat(project, dock) {
    if (!project.source_id || typeof window.openX2redWechatForProject !== "function") {
      window.alert("公众号工作台尚未就绪，请刷新页面后重试。");
      return;
    }
    if (dock) setDockBusy(dock, project.wechat_variant_id ? "正在打开对应公众号版本…" : "正在交接深度终稿与冻结材料…");
    try {
      await window.openX2redWechatForProject(project);
    } catch (error) {
      window.alert(error.message);
      resetDock();
    }
  }

  function showFinalPreview() {
    document.querySelector(".final-article-preview")?.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  function appendMarkdownPreview(container, markdown) {
    const lines = String(markdown || "").split(/\r?\n/);
    let paragraph = [];
    let list = null;
    let code = null;
    const flushParagraph = () => {
      if (!paragraph.length) return;
      const node = document.createElement("p");
      node.textContent = paragraph.join("\n").trim();
      container.appendChild(node);
      paragraph = [];
    };
    const flushList = () => {
      if (!list) return;
      container.appendChild(list);
      list = null;
    };
    lines.forEach((line) => {
      if (/^```/.test(line.trim())) {
        flushParagraph();
        flushList();
        if (code) {
          container.appendChild(code);
          code = null;
        } else {
          code = document.createElement("pre");
        }
        return;
      }
      if (code) {
        code.textContent += `${line}\n`;
        return;
      }
      const heading = line.match(/^(#{2,4})\s+(.+)$/);
      if (heading) {
        flushParagraph();
        flushList();
        const node = document.createElement(heading[1].length === 2 ? "h3" : "h4");
        node.textContent = heading[2];
        container.appendChild(node);
        return;
      }
      const bullet = line.match(/^[-*]\s+(.+)$/);
      if (bullet) {
        flushParagraph();
        if (!list || list.tagName !== "UL") {
          flushList();
          list = document.createElement("ul");
        }
        const node = document.createElement("li");
        node.textContent = bullet[1];
        list.appendChild(node);
        return;
      }
      const ordered = line.match(/^\d+[.)]\s+(.+)$/);
      if (ordered) {
        flushParagraph();
        if (!list || list.tagName !== "OL") {
          flushList();
          list = document.createElement("ol");
        }
        const node = document.createElement("li");
        node.textContent = ordered[1];
        list.appendChild(node);
        return;
      }
      if (!line.trim()) {
        flushParagraph();
        flushList();
        return;
      }
      flushList();
      paragraph.push(line);
    });
    flushParagraph();
    flushList();
    if (code) container.appendChild(code);
  }

  function buildFinalPreview(project) {
    const artifact = latestArtifact(project, (item) => item.artifact_type === "final_draft");
    if (!artifact) return null;
    const content = parseArtifact(artifact);
    const preview = document.createElement("article");
    preview.className = "final-article-preview";

    const heading = document.createElement("header");
    heading.innerHTML = '<span class="section-kicker">STAGE 07 OUTPUT</span><strong>深度写作终稿 · 尚未覆盖公众号版本</strong>';
    const title = document.createElement("h2");
    title.textContent = content.title || project.promise || "完成文章";
    const body = document.createElement("div");
    body.className = "final-article-body";
    appendMarkdownPreview(body, content.body || "");
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
      if (!header) return;
      card.querySelector(".artifact-explainer")?.remove();
      const guide = artifactGuides[artifact.artifact_type] || guideForStage({ key: "unknown", types: [artifact.artifact_type] });
      const run = latestRun(project, [artifact.created_by_role], artifact.id);
      const explainer = document.createElement("section");
      explainer.className = "artifact-explainer";
      const explainerHead = document.createElement("div");
      explainerHead.className = "artifact-explainer-head";
      const verb = document.createElement("span");
      verb.className = "artifact-verb";
      verb.textContent = guide.verb;
      const route = document.createElement("strong");
      route.textContent = `Skill：${guide.skill}`;
      explainerHead.append(verb, route);
      const io = document.createElement("div");
      io.className = "artifact-io-grid";
      [["读取", guide.reads], ["输出 / 修改", guide.writes]].forEach(([label, value]) => {
        const block = document.createElement("div");
        const key = document.createElement("span");
        key.textContent = label;
        const text = document.createElement("p");
        text.textContent = value;
        block.append(key, text);
        io.appendChild(block);
      });
      const meta = document.createElement("div");
      meta.className = "artifact-run-meta";
      const model = document.createElement("span");
      model.textContent = runDescription(run);
      const optimize = document.createElement("p");
      optimize.textContent = `建议优化：${guide.optimize}`;
      meta.append(model, optimize);
      explainer.append(explainerHead, io, meta);
      header.after(explainer);
      let toggle = header.querySelector(".artifact-toggle");
      if (!toggle) {
        toggle = document.createElement("button");
        toggle.type = "button";
        toggle.className = "artifact-toggle";
        header.appendChild(toggle);
        toggle.addEventListener("click", () => {
          card.classList.toggle("collapsed");
          toggle.textContent = card.classList.contains("collapsed") ? "展开" : "收起";
        });
      }
      const collapsed = artifact.id !== focusArtifact?.id;
      card.classList.toggle("collapsed", collapsed);
      toggle.textContent = collapsed ? "展开" : "收起";
    });
    return cards.find((card) => card.dataset.artifactId === focusArtifact?.id) || cards.at(-1);
  }

  function buildDock(project) {
    const dock = document.createElement("section");
    dock.className = "writing-action-dock";
    const copy = document.createElement("div");
    copy.className = "writing-dock-copy";
    const kicker = document.createElement("span");
    kicker.textContent = project.state === "completed"
      ? project.wechat_variant_id ? "WECHAT VERSION READY" : "NEXT: WECHAT ARTICLE"
      : "CURRENT ACTION";
    const title = document.createElement("strong");
    title.textContent = stageNames[project.state] || project.current_stage || "继续写作流程";
    const detail = document.createElement("small");
    const pending = pendingArtifact(project);
    detail.textContent = pending
      ? `${artifactName(pending.artifact_type)}确认后，系统会自动运行到下一个需要你决定的阶段。`
      : project.state === "completed"
        ? project.wechat_variant_id
          ? `深度终稿已关联公众号 v${project.wechat_variant_version || ""}；可打开继续编辑、配图与排版。`
          : `深度终稿已完整保存（${project.output_draft_chars || 0} 字符）；下一步以它和原始证据生成公众号版本。`
        : "系统会运行到下一个人工确认点。";
    copy.append(kicker, title, detail);

    const actions = document.createElement("div");
    actions.className = "writing-dock-actions";
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
      article.textContent = project.wechat_variant_id
        ? `打开公众号 v${project.wechat_variant_version || ""}`
        : "进入公众号成稿阶段";
      article.addEventListener("click", () => handoffToWechat(project, dock));
      const preview = document.createElement("button");
      preview.type = "button";
      preview.className = "secondary-action";
      preview.textContent = "查看本页终稿";
      preview.addEventListener("click", showFinalPreview);
      actions.append(article, preview);
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

  function projectFingerprint(project) {
    const tail = latestArtifact(project);
    const run = [...(project.runs || [])].at(-1);
    return [
      project.id,
      project.state,
      project.current_stage,
      project.artifacts.length,
      tail?.id || "",
      project.runs?.length || 0,
      run?.id || "",
      project.output_draft_id || "",
      project.wechat_variant_id || "",
      project.wechat_variant_version || "",
    ].join(":");
  }

  function enhanceProjectDetail() {
    const project = uxState.project;
    const detail = document.getElementById("writing-detail");
    if (!project || !detail || detail.hidden) return;
    const fingerprint = projectFingerprint(project);
    if (detail.dataset.uxFingerprint === fingerprint && detail.querySelector(".writing-action-dock")) {
      return;
    }

    uxState.busy = false;
    detail.dataset.uxFingerprint = fingerprint;
    detail.querySelector(".writing-action-dock")?.remove();
    detail.querySelector(".final-article-preview")?.remove();
    detail.querySelector(".writing-stage-map")?.remove();
    detail.querySelector(".project-run-actions")?.classList.add("legacy-project-actions");
    detail.querySelectorAll(".artifact-approval").forEach((node) => node.classList.add("legacy-artifact-actions"));

    const header = detail.querySelector(".project-detail-header");
    if (header) header.after(buildStageMap(project));
    const timeline = detail.querySelector(".artifact-timeline");
    if (project.state === "completed" && timeline) {
      const preview = buildFinalPreview(project);
      if (preview) timeline.before(preview);
    }
    const focusCard = prepareArtifacts(project, detail);
    detail.appendChild(buildDock(project));

    const focusKey = projectFingerprint(project);
    if (focusKey !== uxState.lastFocusKey) {
      uxState.lastFocusKey = focusKey;
      const panel = detail.closest(".project-detail-panel");
      if (window.matchMedia("(max-width: 1050px)").matches) {
        detail.scrollIntoView({ behavior: "smooth", block: "start" });
      } else if (project.state === "completed") {
        panel?.scrollTo({ top: 0, behavior: "smooth" });
      } else if (focusCard && panel) {
        panel.scrollTo({ top: Math.max(0, focusCard.offsetTop - 20), behavior: "smooth" });
      }
    }
  }

  function installObserver() {
    const root = document.getElementById("writing-view") || document.body;
    const observer = new MutationObserver(scheduleEnhance);
    observer.observe(root, { childList: true, subtree: true });
    scheduleEnhance();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", installObserver, { once: true });
  } else {
    installObserver();
  }
})();
