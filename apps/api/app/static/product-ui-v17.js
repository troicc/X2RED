(() => {
  if (window.__x2redProductUIV17) return;

  const UI_VERSION = "17";
  const SIDEBAR_KEY = "x2red.ui.v17.sidebar.collapsed";
  const GROUP_KEY = "x2red.ui.v17.nav-groups";
  const compactMedia = window.matchMedia("(min-width: 861px) and (max-width: 1360px)");
  const mobileMedia = window.matchMedia("(max-width: 860px)");
  const regionMedia = window.matchMedia("(max-width: 1360px)");

  const ICONS = {
    radio: '<circle cx="12" cy="12" r="2"/><path d="M16.24 7.76a6 6 0 0 1 0 8.49M7.76 16.24a6 6 0 0 1 0-8.49"/><path d="M19.07 4.93a10 10 0 0 1 0 14.14M4.93 19.07a10 10 0 0 1 0-14.14"/>',
    search: '<circle cx="11" cy="11" r="7"/><path d="m20 20-3.6-3.6"/>',
    library: '<path d="m16 6 4 14"/><path d="M12 6v14"/><path d="M8 8v12"/><path d="M4 4v16"/>',
    penLine: '<path d="M12 20h9"/><path d="M16.5 3.5a2.12 2.12 0 0 1 3 3L8 18l-4 1 1-4Z"/><path d="m15 5 3 3"/>',
    newspaper: '<path d="M4 22h16a2 2 0 0 0 2-2V4H6v16a2 2 0 0 1-4 0V6h4"/><path d="M10 8h8M10 12h8M10 16h5"/>',
    send: '<path d="m22 2-7 20-4-9-9-4Z"/><path d="M22 2 11 13"/>',
    notebookPen: '<path d="M13.4 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-7.4"/><path d="M2 6h4M2 10h4M2 14h4M2 18h4"/><path d="M21.4 4.6a2 2 0 0 0-2.8-2.8l-5.2 5.2-.7 3.5 3.5-.7Z"/>',
    palette: '<circle cx="13.5" cy="6.5" r=".5" fill="currentColor"/><circle cx="17.5" cy="10.5" r=".5" fill="currentColor"/><circle cx="8.5" cy="7.5" r=".5" fill="currentColor"/><circle cx="6.5" cy="12.5" r=".5" fill="currentColor"/><path d="M12 2a10 10 0 0 0 0 20c1.1 0 2-.9 2-2 0-.5-.2-.9-.5-1.3-.3-.4-.5-.8-.5-1.2a2 2 0 0 1 2-2h1.8a5.2 5.2 0 0 0 5.2-5.2C22 5.7 17.5 2 12 2Z"/>',
    settings: '<path d="M12.2 2h-.4a2 2 0 0 0-2 2v.2a2 2 0 0 1-1 1.7l-.4.2a2 2 0 0 1-2 0L6.2 6a2 2 0 0 0-2.7.7l-.2.4a2 2 0 0 0 .7 2.7l.2.1a2 2 0 0 1 1 1.8v.5a2 2 0 0 1-1 1.8l-.2.1a2 2 0 0 0-.7 2.7l.2.4a2 2 0 0 0 2.7.7l.2-.1a2 2 0 0 1 2 0l.4.2a2 2 0 0 1 1 1.7v.2a2 2 0 0 0 2 2h.4a2 2 0 0 0 2-2v-.2a2 2 0 0 1 1-1.7l.4-.2a2 2 0 0 1 2 0l.2.1a2 2 0 0 0 2.7-.7l.2-.4a2 2 0 0 0-.7-2.7l-.2-.1a2 2 0 0 1-1-1.8v-.5a2 2 0 0 1 1-1.8l.2-.1a2 2 0 0 0 .7-2.7l-.2-.4a2 2 0 0 0-2.7-.7l-.2.1a2 2 0 0 1-2 0l-.4-.2a2 2 0 0 1-1-1.7V4a2 2 0 0 0-2-2Z"/><circle cx="12" cy="12" r="3"/>',
    menu: '<path d="M4 6h16M4 12h16M4 18h16"/>',
    panelClose: '<rect width="18" height="18" x="3" y="3" rx="2"/><path d="M9 3v18M16 9l-3 3 3 3"/>',
    panelOpen: '<rect width="18" height="18" x="3" y="3" rx="2"/><path d="M9 3v18M14 9l3 3-3 3"/>',
    chevronDown: '<path d="m6 9 6 6 6-6"/>',
    rotate: '<path d="M20 11a8.1 8.1 0 0 0-15.5-2M4 4v5h5"/><path d="M4 13a8.1 8.1 0 0 0 15.5 2M20 20v-5h-5"/>',
    link: '<path d="M10 13a5 5 0 0 0 7.1.1l2-2a5 5 0 0 0-7.1-7.1l-1.1 1.1"/><path d="M14 11a5 5 0 0 0-7.1-.1l-2 2A5 5 0 0 0 12 20l1.1-1.1"/>',
    sparkles: '<path d="m12 3-1.9 4.8a2 2 0 0 1-1.1 1.1L4.2 11 9 12.9a2 2 0 0 1 1.1 1.1l1.9 4.8 1.9-4.8a2 2 0 0 1 1.1-1.1l4.8-1.9L15 9.1a2 2 0 0 1-1.1-1.1Z"/><path d="M5 3v4M3 5h4M19 17v4M17 19h4"/>',
    check: '<path d="m5 12 4 4L19 6"/>',
    quote: '<path d="M3 21c3 0 7-1 7-8V5c0-1.3-.7-2-2-2H4c-1.3 0-2 .7-2 2v4c0 1.3.7 2 2 2h3c0 4-1 6-4 7ZM14 21c3 0 7-1 7-8V5c0-1.3-.7-2-2-2h-4c-1.3 0-2 .7-2 2v4c0 1.3.7 2 2 2h3c0 4-1 6-4 7Z"/>',
    alert: '<path d="m21.7 18-8-14a2 2 0 0 0-3.4 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.7-3Z"/><path d="M12 9v4M12 17h.01"/>',
    lightbulb: '<path d="M9 18h6M10 22h4"/><path d="M8.5 14.5A7 7 0 1 1 15.5 14.5c-.9.7-1.5 1.7-1.5 2.5h-4c0-.8-.6-1.8-1.5-2.5Z"/>',
    x: '<path d="M18 6 6 18M6 6l12 12"/>',
    fileText: '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8Z"/><path d="M14 2v6h6M8 13h8M8 17h8M8 9h2"/>',
  };

  const NAV_ICONS = {
    "signals-view": "radio",
    "materials-view": "search",
    "corpus-pools-view": "library",
    "creative-task-view": "sparkles",
    "workbench-view": "penLine",
    "writing-view": "penLine",
    "wechat-view": "newspaper",
    "visual-workflow-view": "palette",
    "publish-view": "send",
    "pool-memory-view": "notebookPen",
    "style-lab-view": "palette",
    "settings-view": "settings",
  };

  const REGION_CONFIGS = [
    { key: "source", root: "#workbench-view .source-rail", head: ":scope > .rail-header", label: "来源选择" },
    { key: "signals", root: "#signals-view .studio-two-column > .studio-panel:first-child", head: ":scope > .panel-heading", label: "监控配置" },
    { key: "materials", root: "#materials-view .material-shell > .material-panel:first-child", head: ":scope > .material-panel-head", label: "采集配置" },
    { key: "corpus", root: "#corpus-pools-view .corpus-shell > .corpus-panel:first-child", head: ":scope > .corpus-head", label: "来源选择" },
    { key: "writing", root: "#writing-view .writing-layout > .studio-panel:first-child", head: ":scope > .panel-heading", label: "项目输入" },
    { key: "wechat", root: "#wechat-view .platform-studio-layout > .platform-panel:first-child", head: ":scope > .panel-heading", label: "材料与版本" },
    { key: "memory", root: "#pool-memory-view .memory-grid > .memory-panel:first-child", head: ":scope > .memory-panel-head", label: "偏好输入" },
    { key: "style", root: "#style-lab-view .style-lab-grid > .studio-panel:first-child", head: ":scope > .panel-heading", label: "训练配置" },
  ];

  const uiState = {
    scheduled: false,
    mobileOpen: false,
    returnFocus: null,
    sourceInspectorReturnFocus: null,
    booted: false,
  };
  window.__x2redProductUIV17 = uiState;

  function icon(name) {
    return `<svg class="ui-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false">${ICONS[name] || ICONS.fileText}</svg>`;
  }

  function readJson(key, fallback) {
    try {
      const value = window.localStorage.getItem(key);
      return value ? JSON.parse(value) : fallback;
    } catch {
      return fallback;
    }
  }

  function writeJson(key, value) {
    try {
      window.localStorage.setItem(key, JSON.stringify(value));
    } catch {
      // Storage is optional for local-first operation.
    }
  }

  function appendFinalStylesheet() {
    const stylesheet = document.getElementById("product-ui-v17-styles");
    if (stylesheet && stylesheet.parentElement === document.head) {
      document.head.appendChild(stylesheet);
    }
  }

  function ensureShellControls() {
    const shell = document.querySelector(".app-shell");
    const sidebar = document.querySelector(".app-sidebar");
    const brand = document.querySelector(".brand-block");
    const topbar = document.querySelector(".topbar");
    const main = document.querySelector(".app-main");
    if (!shell || !sidebar || !brand || !topbar || !main) return;

    shell.dataset.uiVersion = UI_VERSION;
    sidebar.id ||= "app-sidebar";
    document.querySelector(".view-stack")?.setAttribute("id", "main-content");

    if (!document.querySelector(".skip-link")) {
      const skip = document.createElement("a");
      skip.className = "skip-link";
      skip.href = "#main-content";
      skip.textContent = "跳到主工作区";
      document.body.prepend(skip);
    }

    let desktopToggle = document.getElementById("sidebar-toggle");
    if (!desktopToggle) {
      desktopToggle = document.createElement("button");
      desktopToggle.id = "sidebar-toggle";
      desktopToggle.type = "button";
      desktopToggle.className = "sidebar-toggle ui-icon-button";
      brand.appendChild(desktopToggle);
    }
    if (!desktopToggle.dataset.uiBound) {
      desktopToggle.dataset.uiBound = "true";
      desktopToggle.addEventListener("click", () => {
        if (mobileMedia.matches) {
          setMobileDrawer(!uiState.mobileOpen, desktopToggle);
          return;
        }
        if (compactMedia.matches) {
          const opening = !shell.classList.contains("is-sidebar-pinned-open");
          shell.classList.toggle("is-sidebar-pinned-open", opening);
          if (opening) shell.classList.remove("is-sidebar-collapsed");
        } else {
          const collapsed = !shell.classList.contains("is-sidebar-collapsed");
          shell.classList.toggle("is-sidebar-collapsed", collapsed);
          writeJson(SIDEBAR_KEY, collapsed);
        }
        syncShellState();
      });
    }

    let mobileToggle = document.getElementById("mobile-nav-toggle");
    if (!mobileToggle) {
      mobileToggle = document.createElement("button");
      mobileToggle.id = "mobile-nav-toggle";
      mobileToggle.type = "button";
      mobileToggle.className = "mobile-nav-toggle ui-icon-button";
      mobileToggle.innerHTML = icon("menu");
      mobileToggle.setAttribute("aria-controls", sidebar.id);
      mobileToggle.setAttribute("aria-label", "打开主导航");
      mobileToggle.addEventListener("click", () => setMobileDrawer(!uiState.mobileOpen, mobileToggle));
      topbar.prepend(mobileToggle);
    }

    let backdrop = document.getElementById("sidebar-backdrop");
    if (!backdrop) {
      backdrop = document.createElement("button");
      backdrop.id = "sidebar-backdrop";
      backdrop.type = "button";
      backdrop.className = "sidebar-backdrop";
      backdrop.setAttribute("aria-label", "关闭主导航");
      backdrop.addEventListener("click", () => setMobileDrawer(false));
      document.body.appendChild(backdrop);
    }

    if (!shell.dataset.sidebarInitialised) {
      shell.dataset.sidebarInitialised = "true";
      shell.classList.toggle("is-sidebar-collapsed", Boolean(readJson(SIDEBAR_KEY, false)));
    }
    syncShellState();
  }

  function setMobileDrawer(open, trigger = null) {
    const shell = document.querySelector(".app-shell");
    const main = document.querySelector(".app-main");
    const sidebar = document.querySelector(".app-sidebar");
    if (!shell || !main || !sidebar) return;
    uiState.mobileOpen = Boolean(open && mobileMedia.matches);
    if (uiState.mobileOpen) {
      uiState.returnFocus = trigger || document.activeElement;
      shell.classList.add("is-sidebar-open");
      document.body.classList.add("ui-drawer-open");
      main.inert = true;
      window.setTimeout(() => sidebar.querySelector(".nav-item")?.focus(), 0);
    } else {
      shell.classList.remove("is-sidebar-open");
      document.body.classList.remove("ui-drawer-open");
      main.inert = false;
      if (open === false && uiState.returnFocus instanceof HTMLElement) uiState.returnFocus.focus();
      uiState.returnFocus = null;
    }
    syncShellState();
  }

  function syncShellState() {
    const shell = document.querySelector(".app-shell");
    const desktopToggle = document.getElementById("sidebar-toggle");
    const mobileToggle = document.getElementById("mobile-nav-toggle");
    if (!shell || !desktopToggle || !mobileToggle) return;
    const compact = compactMedia.matches;
    const pinnedOpen = shell.classList.contains("is-sidebar-pinned-open");
    const collapsed = compact ? !pinnedOpen : shell.classList.contains("is-sidebar-collapsed");
    const expanded = mobileMedia.matches ? uiState.mobileOpen : !collapsed;
    const iconState = expanded ? "panelClose" : "panelOpen";
    if (desktopToggle.dataset.uiIconState !== iconState) {
      desktopToggle.dataset.uiIconState = iconState;
      desktopToggle.innerHTML = icon(iconState);
    }
    desktopToggle.setAttribute("aria-controls", "app-sidebar");
    desktopToggle.setAttribute("aria-expanded", String(expanded));
    desktopToggle.setAttribute("aria-label", expanded ? "收起主导航" : "展开主导航");
    desktopToggle.title = expanded ? "收起主导航" : "展开主导航";
    mobileToggle.setAttribute("aria-expanded", String(uiState.mobileOpen));
    mobileToggle.setAttribute("aria-label", uiState.mobileOpen ? "关闭主导航" : "打开主导航");
  }

  function enhanceNavigation() {
    const groups = readJson(GROUP_KEY, {});
    document.querySelectorAll(".product-nav-section").forEach((section) => {
      const group = section.dataset.productNavGroup || "";
      let heading = section.querySelector(":scope > .product-nav-label");
      if (heading && heading.tagName !== "BUTTON") {
        const button = document.createElement("button");
        button.type = "button";
        button.className = "product-nav-label product-nav-toggle";
        button.innerHTML = `<span>${heading.textContent.trim()}</span>${icon("chevronDown")}`;
        heading.replaceWith(button);
        heading = button;
      }
      if (heading && !heading.dataset.uiBound) {
        heading.dataset.uiBound = "true";
        const collapsed = Boolean(groups[group]);
        section.classList.toggle("is-group-collapsed", collapsed);
        heading.setAttribute("aria-expanded", String(!collapsed));
        heading.addEventListener("click", () => {
          const next = !section.classList.contains("is-group-collapsed");
          section.classList.toggle("is-group-collapsed", next);
          heading.setAttribute("aria-expanded", String(!next));
          const value = readJson(GROUP_KEY, {});
          value[group] = next;
          writeJson(GROUP_KEY, value);
        });
      }
    });

    document.querySelectorAll(".primary-nav .nav-item").forEach((button) => {
      const view = button.dataset.view || (button.id === "materials-nav" ? "materials-view" : "");
      const holder = button.querySelector(".nav-icon");
      if (holder && holder.dataset.uiIcon !== NAV_ICONS[view]) {
        holder.innerHTML = icon(NAV_ICONS[view] || "fileText");
        holder.dataset.uiIcon = NAV_ICONS[view] || "fileText";
        holder.setAttribute("aria-hidden", "true");
      }
      const active = button.classList.contains("active");
      if (active) button.setAttribute("aria-current", "page");
      else button.removeAttribute("aria-current");
      if (!button.dataset.uiRouteBound) {
        button.dataset.uiRouteBound = "true";
        button.addEventListener("click", () => {
          setSourceInspectorOpen(false, null, false);
          const parent = button.closest(".product-nav-section");
          if (parent) {
            parent.classList.remove("is-group-collapsed");
            parent.querySelector(".product-nav-toggle")?.setAttribute("aria-expanded", "true");
          }
          if (mobileMedia.matches) setMobileDrawer(false);
          window.setTimeout(scheduleEnhance, 0);
        });
      }
    });
  }

  function setRegionCollapsed(root, collapsed, manual = false) {
    const toggle = root.querySelector(":scope > [data-ui-region-head] > .ui-region-toggle");
    root.classList.toggle("is-collapsed", collapsed);
    if (manual) root.dataset.uiRegionManual = "true";
    if (!toggle) return;
    const iconState = collapsed ? "panelOpen" : "panelClose";
    if (toggle.dataset.uiIconState !== iconState) {
      toggle.dataset.uiIconState = iconState;
      toggle.innerHTML = icon(iconState);
    }
    toggle.setAttribute("aria-expanded", String(!collapsed));
    toggle.setAttribute("aria-label", collapsed ? `展开${root.dataset.uiRegionLabel}` : `收起${root.dataset.uiRegionLabel}`);
    toggle.title = toggle.getAttribute("aria-label");
  }

  function shouldAutoCollapseRegion(root, key = root.dataset.uiRegion) {
    if (key === "source" && !document.getElementById("active-workbench")?.hidden) {
      return true;
    }
    if (!regionMedia.matches) return false;
    if (key === "wechat" && document.getElementById("wechat-view")?.classList.contains("is-wechat-preflight")) {
      return false;
    }
    return true;
  }

  function setSourceInspectorOpen(open, trigger = null, restoreFocus = true) {
    const inspector = document.getElementById("source-inspector");
    const backdrop = document.getElementById("source-inspector-backdrop");
    const toggle = document.getElementById("source-inspector-toggle");
    if (!inspector || !backdrop || !toggle) return;
    const next = Boolean(open);
    if (next) {
      uiState.sourceInspectorReturnFocus = trigger || document.activeElement;
      inspector.hidden = false;
      backdrop.hidden = false;
      document.body.classList.add("source-inspector-open");
      toggle.setAttribute("aria-expanded", "true");
      window.setTimeout(() => document.getElementById("source-inspector-close")?.focus(), 0);
      return;
    }
    inspector.hidden = true;
    backdrop.hidden = true;
    document.body.classList.remove("source-inspector-open");
    toggle.setAttribute("aria-expanded", "false");
    if (restoreFocus && uiState.sourceInspectorReturnFocus instanceof HTMLElement) {
      uiState.sourceInspectorReturnFocus.focus();
    }
    uiState.sourceInspectorReturnFocus = null;
  }

  function ensureSourceInspector() {
    const inspector = document.getElementById("source-inspector");
    const backdrop = document.getElementById("source-inspector-backdrop");
    const toggle = document.getElementById("source-inspector-toggle");
    const close = document.getElementById("source-inspector-close");
    if (!inspector || !backdrop || !toggle || !close) return;
    if (!toggle.dataset.uiBound) {
      toggle.dataset.uiBound = "true";
      toggle.addEventListener("click", () => setSourceInspectorOpen(inspector.hidden, toggle));
      close.addEventListener("click", () => setSourceInspectorOpen(false));
      backdrop.addEventListener("click", () => setSourceInspectorOpen(false));
      inspector.addEventListener("keydown", (event) => {
        if (event.key === "Escape") {
          event.preventDefault();
          setSourceInspectorOpen(false);
          return;
        }
        if (event.key !== "Tab") return;
        const focusable = [...inspector.querySelectorAll("button,textarea,input,select,a[href]")]
          .filter((control) => !control.disabled && control.getClientRects().length > 0);
        if (!focusable.length) return;
        const first = focusable[0];
        const last = focusable[focusable.length - 1];
        if (event.shiftKey && document.activeElement === first) {
          event.preventDefault();
          last.focus();
        } else if (!event.shiftKey && document.activeElement === last) {
          event.preventDefault();
          first.focus();
        }
      });
      document.querySelectorAll("#active-workbench .stage-tab").forEach((tab) => {
        tab.addEventListener("click", () => {
          if (tab.dataset.tab !== "source-pane") setSourceInspectorOpen(false, null, false);
        });
      });
    }
    if (document.getElementById("active-workbench")?.hidden && !inspector.hidden) {
      setSourceInspectorOpen(false, null, false);
    }
  }

  function setupRegions() {
    REGION_CONFIGS.forEach((config) => {
      const root = document.querySelector(config.root);
      if (!root) return;
      const head = root.querySelector(config.head);
      if (!head) return;
      if (!root.dataset.uiRegionReady) {
        root.dataset.uiRegionReady = "true";
        root.dataset.uiRegion = config.key;
        root.dataset.uiRegionLabel = config.label;
        root.classList.add("ui-region-collapsible");
        head.dataset.uiRegionHead = "true";
        const toggle = document.createElement("button");
        toggle.type = "button";
        toggle.className = "ui-region-toggle ui-icon-button";
        toggle.addEventListener("click", () => {
          setRegionCollapsed(root, !root.classList.contains("is-collapsed"), true);
        });
        head.appendChild(toggle);
      }
      if (!root.dataset.uiRegionManual) {
        setRegionCollapsed(root, shouldAutoCollapseRegion(root, config.key));
      } else {
        setRegionCollapsed(root, root.classList.contains("is-collapsed"));
      }
    });
  }

  function autoCollapseFromSelection(target) {
    const mappings = [
      [".source-item-select", "source"],
      [".writing-project-item", "writing"],
      [".platform-variant-item", "wechat"],
      [".corpus-pool-card", "corpus"],
      [".memory-card-open", "memory"],
    ];
    mappings.forEach(([selector, key]) => {
      if (!target.closest(selector)) return;
      const region = document.querySelector(`[data-ui-region="${key}"]`);
      if (region) window.setTimeout(() => setRegionCollapsed(region, true, true), 120);
    });
  }

  function enhanceIcons() {
    const iconControls = [
      ["refresh", "rotate", "刷新来源"],
      ["close-lightbox", "x", "关闭预览"],
    ];
    iconControls.forEach(([id, name, label]) => {
      const button = document.getElementById(id);
      if (!button || button.dataset.uiIconReady) return;
      button.dataset.uiIconReady = "true";
      button.innerHTML = icon(name);
      button.setAttribute("aria-label", label);
      button.title = label;
    });

    document.querySelectorAll(".review-close").forEach((button) => {
      if (button.dataset.uiIconReady) return;
      button.dataset.uiIconReady = "true";
      button.innerHTML = icon("x");
      button.setAttribute("aria-label", "关闭审核面板");
      button.title = "关闭审核面板";
    });

    document.querySelectorAll(".url-field > span").forEach((holder) => {
      if (holder.dataset.uiIconReady) return;
      holder.dataset.uiIconReady = "true";
      holder.innerHTML = icon("link");
      holder.setAttribute("aria-hidden", "true");
    });
    document.querySelectorAll(".source-filter > span").forEach((holder) => {
      if (holder.dataset.uiIconReady) return;
      holder.dataset.uiIconReady = "true";
      holder.innerHTML = icon("search");
      holder.setAttribute("aria-hidden", "true");
    });
    document.querySelectorAll(".empty-orbit").forEach((holder) => {
      if (holder.dataset.uiIconReady) return;
      holder.dataset.uiIconReady = "true";
      holder.innerHTML = icon(holder.closest("#analysis-pane") ? "lightbulb" : holder.closest("#writing-view") ? "penLine" : "sparkles");
    });
    [
      [".facts-card .analysis-card-title > span", "check"],
      [".claims-card .analysis-card-title > span", "quote"],
      [".caution-card .analysis-card-title > span", "alert"],
      [".value-card .analysis-card-title > span", "lightbulb"],
    ].forEach(([selector, name]) => {
      document.querySelectorAll(selector).forEach((holder) => {
        if (holder.dataset.uiIconReady) return;
        holder.dataset.uiIconReady = "true";
        holder.innerHTML = icon(name);
        holder.setAttribute("aria-hidden", "true");
      });
    });
  }

  function enhanceAccessibility() {
    document.querySelectorAll(".inline-status,.material-status,.corpus-status,.memory-status,.light-status").forEach((node) => {
      node.setAttribute("role", "status");
      node.setAttribute("aria-live", "polite");
    });
    document.querySelectorAll("button:not([type])").forEach((button) => {
      if (!button.closest("form")) button.type = "button";
    });
    document.querySelectorAll("img").forEach((image) => {
      if (!image.hasAttribute("alt")) image.alt = "";
    });
  }

  function scheduleEnhance() {
    if (uiState.scheduled) return;
    uiState.scheduled = true;
    window.requestAnimationFrame(() => {
      uiState.scheduled = false;
      ensureShellControls();
      ensureSourceInspector();
      enhanceNavigation();
      setupRegions();
      enhanceIcons();
      enhanceAccessibility();
    });
  }

  function syncResponsiveState() {
    const shell = document.querySelector(".app-shell");
    if (!shell) return;
    if (!compactMedia.matches) shell.classList.remove("is-sidebar-pinned-open");
    if (!mobileMedia.matches && uiState.mobileOpen) setMobileDrawer(false);
    document.querySelectorAll("[data-ui-region]").forEach((root) => {
      if (!root.dataset.uiRegionManual) setRegionCollapsed(root, shouldAutoCollapseRegion(root));
    });
    syncShellState();
  }

  function boot() {
    if (uiState.booted) return;
    uiState.booted = true;
    appendFinalStylesheet();
    scheduleEnhance();
    new MutationObserver(scheduleEnhance).observe(document.body, {
      childList: true,
      subtree: true,
      attributes: true,
      attributeFilter: ["hidden"],
    });
    document.addEventListener("click", (event) => autoCollapseFromSelection(event.target));
    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape" && !document.getElementById("source-inspector")?.hidden) {
        setSourceInspectorOpen(false);
      } else if (event.key === "Escape" && uiState.mobileOpen) {
        setMobileDrawer(false);
      }
    });
    compactMedia.addEventListener("change", syncResponsiveState);
    mobileMedia.addEventListener("change", syncResponsiveState);
    regionMedia.addEventListener("change", syncResponsiveState);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot, { once: true });
  } else {
    boot();
  }
})();
