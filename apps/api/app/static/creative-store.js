const STORAGE_KEY = "x2red.creative-task.v18";

const DEFAULT_TASK = Object.freeze({
  version: 18,
  materialRefs: [],
  articleType: "deep_explainer",
  platform: "wechat_long",
  reader: "",
  promise: "",
  writingMode: "studio",
  visualRoute: "wechat_inline",
  step: 0,
  handoffState: "draft",
  updatedAt: "",
});

function uniqueStrings(values, limit = 32) {
  return [...new Set((Array.isArray(values) ? values : []).map(String).filter(Boolean))].slice(0, limit);
}

function normalize(value = {}) {
  const next = { ...DEFAULT_TASK, ...(value && typeof value === "object" ? value : {}) };
  next.materialRefs = uniqueStrings(next.materialRefs);
  next.articleType = ["deep_explainer", "news_digest", "editorial_view", "light_series"].includes(next.articleType)
    ? next.articleType : DEFAULT_TASK.articleType;
  next.platform = ["xiaohongshu", "wechat_long", "wechat_light"].includes(next.platform)
    ? next.platform : DEFAULT_TASK.platform;
  next.writingMode = ["studio", "fast"].includes(next.writingMode) ? next.writingMode : DEFAULT_TASK.writingMode;
  next.visualRoute = ["html_cards", "wechat_inline", "minimal_zine", "none"].includes(next.visualRoute)
    ? next.visualRoute : DEFAULT_TASK.visualRoute;
  next.reader = String(next.reader || "").slice(0, 2000);
  next.promise = String(next.promise || "").slice(0, 2000);
  next.step = Math.min(5, Math.max(0, Number(next.step) || 0));
  next.handoffState = ["draft", "ready", "handed_off"].includes(next.handoffState)
    ? next.handoffState : "draft";
  return next;
}

function readStored() {
  try {
    return normalize(JSON.parse(window.localStorage.getItem(STORAGE_KEY) || "{}"));
  } catch {
    return normalize();
  }
}

/** Create the current-tab creative brief store and persistence bridge. */
export function createCreativeStore() {
  let task = readStored();
  const listeners = new Set();

  function notify(reason = "update") {
    const snapshot = get();
    listeners.forEach((listener) => listener(snapshot, reason));
    document.dispatchEvent(new CustomEvent("x2red:creative-task-changed", {
      detail: { task: snapshot, reason },
    }));
  }

  function persist(reason) {
    task.updatedAt = new Date().toISOString();
    try {
      window.localStorage.setItem(STORAGE_KEY, JSON.stringify(task));
    } catch {
      // Local storage is an optional convenience; the handoff still works in-memory.
    }
    notify(reason);
  }

  function get() {
    return { ...task, materialRefs: [...task.materialRefs] };
  }

  return {
    get,
    update(patch, reason = "update") {
      const value = typeof patch === "function" ? patch(get()) : patch;
      task = normalize({ ...task, ...(value || {}) });
      persist(reason);
      return get();
    },
    reset() {
      task = normalize();
      persist("reset");
      return get();
    },
    subscribe(listener) {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
    summary() {
      const labels = {
        xiaohongshu: "小红书",
        wechat_long: "公众号长文",
        wechat_light: "公众号轻内容",
      };
      return {
        materialCount: task.materialRefs.length,
        platformLabel: labels[task.platform] || task.platform,
        ready: Boolean(task.materialRefs.length && task.reader.trim() && task.promise.trim()),
      };
    },
  };
}

export { STORAGE_KEY as CREATIVE_TASK_STORAGE_KEY };
