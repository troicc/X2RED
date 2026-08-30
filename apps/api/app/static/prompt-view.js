function element(tag, className = "", text = "") {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text) node.textContent = text;
  return node;
}

function valueAt(record, ...keys) {
  for (const key of keys) {
    const value = record?.[key];
    if (value !== undefined && value !== null && value !== "") return value;
  }
  return "";
}

function shortFingerprint(value) {
  const text = String(value || "");
  return text ? `${text.slice(0, 12)}${text.length > 12 ? "…" : ""}` : "—";
}

/** Return prompt duplication warnings relative to the active record. */
export function promptDuplicateWarnings(records, activeIndex) {
  const active = records[activeIndex] || {};
  const prompt = String(valueAt(active, "prompt", "final_prompt") || "").trim();
  const fingerprint = String(valueAt(active, "prompt_fingerprint", "source_fingerprint") || "");
  const warnings = [];
  records.forEach((record, index) => {
    if (index === activeIndex) return;
    const otherPrompt = String(valueAt(record, "prompt", "final_prompt") || "").trim();
    const otherFingerprint = String(valueAt(record, "prompt_fingerprint", "source_fingerprint") || "");
    if (prompt && otherPrompt && prompt === otherPrompt) warnings.push(`与第 ${index + 1} 项的完整 Prompt 重复`);
    else if (fingerprint && otherFingerprint && fingerprint === otherFingerprint) {
      warnings.push(`与第 ${index + 1} 项的 Prompt 指纹重复`);
    }
  });
  return [...new Set(warnings)];
}

/** Render prompt provenance, fingerprints, warnings, and the session diff. */
export function renderPromptView(container, {
  record = {},
  records = [],
  activeIndex = 0,
  onCompile = null,
} = {}) {
  container.replaceChildren();
  const visualSpec = record.visual_prompt_spec && typeof record.visual_prompt_spec === "object"
    ? record.visual_prompt_spec : {};
  const trace = element("section", "creative-prompt-trace");
  const head = element("div", "creative-panel-head");
  const copy = element("div");
  copy.append(element("span", "section-kicker", "PROMPT PROVENANCE"), element("h3", "", "Prompt 溯源与差异"));
  head.appendChild(copy);
  if (onCompile) {
    const compile = element("button", "secondary-action", "编译并比较当前 Prompt");
    compile.type = "button";
    compile.addEventListener("click", () => onCompile(compile));
    head.appendChild(compile);
  }
  trace.appendChild(head);

  const grid = element("dl", "creative-trace-grid");
  [
    ["编译模式", valueAt(record, "compiler_mode") || visualSpec.mode || "未记录"],
    ["Skill 版本", valueAt(record, "skill_version") || visualSpec.skill_version || "未记录"],
    ["来源指纹", shortFingerprint(valueAt(record, "source_fingerprint") || visualSpec.source_fingerprint)],
    ["Prompt 指纹", shortFingerprint(valueAt(record, "prompt_fingerprint") || visualSpec.prompt_fingerprint)],
  ].forEach(([label, value]) => grid.append(element("dt", "", label), element("dd", "", String(value))));
  trace.appendChild(grid);

  const warnings = [
    ...(Array.isArray(record.warnings) ? record.warnings.map(String) : []),
    ...promptDuplicateWarnings(records, activeIndex),
  ];
  const warningBox = element("div", `creative-duplicate-warning${warnings.length ? " is-warning" : ""}`);
  warningBox.setAttribute("role", warnings.length ? "alert" : "status");
  warningBox.textContent = warnings.length ? `重复或编译警告：${[...new Set(warnings)].join("；")}` : "未发现跨页 Prompt 重复。";
  trace.appendChild(warningBox);

  const prompt = String(valueAt(record, "prompt", "final_prompt") || "");
  const promptDetails = element("details", "creative-prompt-copy");
  promptDetails.appendChild(element("summary", "", "查看当前完整 Prompt"));
  promptDetails.appendChild(element("pre", "", prompt || "当前版本尚未冻结 Prompt。"));
  trace.appendChild(promptDetails);

  const diff = record.prompt_diff && typeof record.prompt_diff === "object" ? record.prompt_diff : {};
  const diffDetails = element("details", "creative-prompt-diff");
  const hasBaseline = Boolean(diff.before || diff.unified);
  diffDetails.appendChild(element(
    "summary",
    "",
    hasBaseline ? (diff.changed ? "Prompt diff · 已变化" : "Prompt diff · 无变化") : "Prompt diff · 尚无上一版基线",
  ));
  diffDetails.appendChild(element(
    "pre",
    "",
    hasBaseline ? String(diff.unified || "本次编译与上一版相同。") : "点击“编译并比较”后，当前会话会显示与上一版的逐行差异。",
  ));
  trace.appendChild(diffDetails);
  container.appendChild(trace);
}
