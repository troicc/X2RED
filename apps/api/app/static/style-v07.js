(() => {
  const styleState = { profiles: [] };

  function element(tag, className = "", text = "") {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text) node.textContent = text;
    return node;
  }

  function splitSamples(value) {
    return value
      .split(/\n\s*---+\s*\n/g)
      .map((item) => item.trim())
      .filter(Boolean);
  }

  async function waitForJob(jobId, timeoutMs = 300000) {
    const started = Date.now();
    while (Date.now() - started < timeoutMs) {
      const job = await api(`/api/jobs/${encodeURIComponent(jobId)}`);
      if (job.state === "succeeded") return job;
      if (job.state === "failed") throw new Error(job.error || "风格训练失败");
      await new Promise((resolve) => setTimeout(resolve, 700));
    }
    throw new Error("风格训练等待超时");
  }

  function injectNavigation() {
    const nav = document.querySelector(".primary-nav");
    if (!nav || document.querySelector('[data-view="style-lab-view"]')) return;
    const settings = nav.querySelector('[data-view="settings-view"]');
    const button = element("button", "nav-item");
    button.dataset.view = "style-lab-view";
    button.innerHTML = '<span class="nav-icon">Aa</span><span>风格实验室</span>';
    nav.insertBefore(button, settings);
    button.addEventListener("click", () => window.setView("style-lab-view"));
  }

  function injectView() {
    const stack = document.querySelector(".view-stack");
    if (!stack || document.getElementById("style-lab-view")) return;
    const settingsView = document.getElementById("settings-view");
    const view = element("section", "app-view");
    view.id = "style-lab-view";
    view.innerHTML = `
      <section class="page-intro studio-intro">
        <span class="section-kicker">PERSONAL STYLE LAB</span><h2>风格实验室</h2>
        <p>只使用你明确授权的原创样本。先提炼规则，再用留出样本和真实改稿反馈验证，不用一个“风格分数”代替作者判断。</p>
      </section>
      <section class="style-lab-grid">
        <article class="surface studio-panel">
          <div class="panel-heading"><div><span class="section-kicker">TRAIN PROFILE</span><h3>训练个人风格</h3></div></div>
          <form id="style-training-form" class="style-training-form">
            <label>档案名称<input id="style-name" required placeholder="例如：我的技术写作" /></label>
            <label>用途说明<input id="style-description" placeholder="例如：技术长文和产品观察" /></label>
            <label>原创样本（至少 3 篇，用单独一行 --- 分隔）<textarea id="style-originals" required rows="12" placeholder="第一篇原创全文\n\n---\n\n第二篇原创全文\n\n---\n\n第三篇原创全文"></textarea></label>
            <label>留出样本（可选，同样用 --- 分隔）<textarea id="style-held-out" rows="7" placeholder="这些样本不会参与初次规则提炼，只用于验证"></textarea></label>
            <label>真实改稿反馈（可选，每行一条）<textarea id="style-feedback" rows="5" placeholder="例如：删掉‘值得注意的是’，太像 AI"></textarea></label>
            <button class="primary-action" type="submit">训练并验证风格档案</button>
          </form>
        </article>
        <article class="surface studio-panel style-profile-panel">
          <div class="panel-heading"><div><span class="section-kicker">STYLE PROFILES</span><h3>可用风格档案</h3></div><button id="refresh-styles" class="secondary-action" type="button">刷新</button></div>
          <div id="style-profile-list" class="style-profile-list"></div>
        </article>
      </section>`;
    stack.insertBefore(view, settingsView);
  }

  function injectProjectStyleSelect() {
    const form = document.getElementById("writing-project-form");
    if (!form || document.getElementById("writing-style-profile")) return;
    const modeLabel = document.getElementById("writing-mode")?.closest("label");
    const label = element("label");
    label.innerHTML = '个人风格<select id="writing-style-profile"><option value="">默认通用风格</option></select>';
    if (modeLabel?.nextSibling) form.insertBefore(label, modeLabel.nextSibling);
    else form.append(label);
  }

  const previousSetView = window.setView;
  window.setView = function setStyleView(viewId) {
    previousSetView(viewId);
    if (viewId === "style-lab-view") {
      document.getElementById("page-title").textContent = "风格实验室";
      loadStyles();
    }
  };

  async function loadStyles() {
    styleState.profiles = await api("/api/writing/styles");
    renderStyles();
    const select = document.getElementById("writing-style-profile");
    if (select) {
      const current = select.value;
      select.replaceChildren(new Option("默认通用风格", ""));
      styleState.profiles.forEach((profile) => {
        select.append(new Option(`${profile.name} · v${profile.version}`, profile.id));
      });
      if (styleState.profiles.some((profile) => profile.id === current)) select.value = current;
    }
  }

  function renderStyles() {
    const box = document.getElementById("style-profile-list");
    if (!box) return;
    box.replaceChildren();
    if (!styleState.profiles.length) {
      box.append(element("div", "card-empty", "还没有个人风格档案。准备 5—10 篇同类型原创样本效果最好。"));
      return;
    }
    styleState.profiles.forEach((profile) => {
      const card = element("article", "style-profile-card");
      const header = element("div", "style-profile-header");
      header.innerHTML = `<div><strong>${profile.name}</strong><small>版本 ${profile.version} · ${profile.description || "未填写用途"}</small></div><span>${profile.active ? "启用" : "停用"}</span>`;
      const rules = element("pre", "style-rule-preview");
      try {
        const parsed = JSON.parse(profile.rules_json || "{}");
        rules.textContent = JSON.stringify({
          identity: parsed.identity,
          reader_relationship: parsed.reader_relationship,
          language_rhythm: parsed.language_rhythm,
          paragraph_habits: parsed.paragraph_habits,
          judgment_style: parsed.judgment_style,
          forbidden_expressions: parsed.forbidden_expressions,
        }, null, 2);
      } catch {
        rules.textContent = profile.rules_json;
      }
      card.append(header, rules);
      box.append(card);
    });
  }

  function bindEvents() {
    document.getElementById("refresh-styles")?.addEventListener("click", loadStyles);
    document.getElementById("style-training-form")?.addEventListener("submit", async (event) => {
      event.preventDefault();
      const button = event.submitter;
      button.disabled = true;
      try {
        const originals = splitSamples(document.getElementById("style-originals").value);
        if (originals.length < 3) throw new Error("至少需要 3 篇用 --- 分隔的原创样本");
        const feedback = document.getElementById("style-feedback").value
          .split("\n")
          .map((item) => item.trim())
          .filter(Boolean);
        const job = await api("/api/writing/styles/train", {
          method: "POST",
          body: JSON.stringify({
            name: document.getElementById("style-name").value,
            description: document.getElementById("style-description").value,
            original_samples: originals,
            held_out_samples: splitSamples(document.getElementById("style-held-out").value),
            author_feedback: feedback,
          }),
        });
        await waitForJob(job.id);
        await loadStyles();
        window.alert("风格档案已经训练并通过留出样本验证。再次使用同名档案会生成新版本。 ");
      } catch (error) {
        window.alert(error.message);
      } finally {
        button.disabled = false;
      }
    });
  }

  injectNavigation();
  injectView();
  injectProjectStyleSelect();
  bindEvents();
  loadStyles().catch(() => {});
})();
