function element(tag, className = "", text = "") {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text) node.textContent = text;
  return node;
}

const STATUS_LABELS = {
  pending_review: "待审核",
  eligible: "机器初审通过",
  kept: "保留比较",
  rejected: "已驳回",
  selected: "已选成品",
  repair_failed: "修复未通过",
};

function imageUrl(variantId, key) {
  if (!variantId || !key) return "";
  return `/api/platforms/variants/${encodeURIComponent(variantId)}/files/${encodeURIComponent(key)}?v=${Date.now()}`;
}

/** Return cross-page warnings for candidates that share an image hash. */
export function duplicateImageWarnings(lifecycle) {
  const hashes = new Map();
  const warnings = [];
  Object.values(lifecycle?.pages || {}).forEach((pageState) => {
    (pageState?.candidates || []).forEach((candidate) => {
      const previous = hashes.get(candidate.image_hash);
      if (candidate.image_hash && previous) {
        warnings.push(`第 ${candidate.page} 页候选 ${candidate.candidate_index} 与第 ${previous.page} 页候选 ${previous.index} 图片哈希重复`);
      } else if (candidate.image_hash) {
        hashes.set(candidate.image_hash, { page: candidate.page, index: candidate.candidate_index });
      }
    });
  });
  return warnings;
}

/** Render candidate review state and human selection controls. */
export function renderCandidateView(container, {
  variantId = "",
  pageState = null,
  lifecycle = {},
  onSelect = null,
  onReview = null,
  onRepair = null,
} = {}) {
  container.replaceChildren();
  const section = element("section", "creative-candidate-panel");
  const head = element("div", "creative-panel-head");
  const title = element("div");
  title.append(element("span", "section-kicker", "CANDIDATE REVIEW"), element("h3", "", "Contact Sheet 与候选状态"));
  const candidates = pageState?.candidates || [];
  head.append(title, element("span", "status-chip neutral", `${candidates.length} 个候选`));
  section.appendChild(head);

  const duplicates = duplicateImageWarnings(lifecycle);
  if (duplicates.length) {
    const warning = element("div", "creative-duplicate-warning is-warning", duplicates.join("；"));
    warning.setAttribute("role", "alert");
    section.appendChild(warning);
  }

  if (pageState?.contact_sheet_key) {
    const sheet = element("figure", "creative-contact-sheet");
    const image = document.createElement("img");
    image.src = imageUrl(variantId, pageState.contact_sheet_key);
    image.alt = `第 ${pageState.page} 页候选 Contact Sheet`;
    sheet.append(image, element("figcaption", "", "Contact Sheet · 编号与候选卡一致，最终仍需人工逐张查看。"));
    section.appendChild(sheet);
  }

  const gallery = element("div", "creative-candidate-grid");
  candidates.forEach((candidate) => {
    const card = element("article", `creative-candidate-card is-${candidate.status || "pending_review"}`);
    const image = document.createElement("img");
    image.src = imageUrl(variantId, candidate.artifact_key);
    image.alt = `第 ${candidate.page} 页候选 ${candidate.candidate_index}`;
    const top = element("div", "creative-candidate-top");
    top.append(
      element("strong", "", `候选 ${candidate.candidate_index}`),
      element("span", "creative-candidate-status", STATUS_LABELS[candidate.status] || candidate.status || "待审核"),
    );
    const score = Number(candidate.review?.overall_score || 0);
    const meter = element("div", "creative-quality-score");
    meter.setAttribute("role", "meter");
    meter.setAttribute("aria-label", `候选 ${candidate.candidate_index} 质量评分`);
    meter.setAttribute("aria-valuemin", "0");
    meter.setAttribute("aria-valuemax", "100");
    meter.setAttribute("aria-valuenow", String(score));
    meter.append(element("strong", "", score.toFixed(1)), element("span", "", "/ 100 质量分"));
    const issues = element("p", "creative-candidate-issues", (candidate.review?.issues || []).join("；") || "机器初审未记录明显问题。人工仍需检查事实、版权、文字残留与角标。" );
    const actions = element("div", "creative-candidate-actions");
    if (onReview && candidate.status !== "rejected") {
      const keep = element("button", "secondary-action", "保留比较");
      keep.type = "button";
      keep.addEventListener("click", () => onReview(candidate, "keep", keep));
      const reject = element("button", "ghost-danger", "驳回");
      reject.type = "button";
      reject.addEventListener("click", () => onReview(candidate, "reject", reject));
      actions.append(keep, reject);
      if (!candidate.review?.passed) {
        const approve = element("button", "secondary-action", "人工批准");
        approve.type = "button";
        approve.addEventListener("click", () => onReview(candidate, "approve", approve));
        actions.appendChild(approve);
      }
    }
    if (onRepair && !candidate.review?.passed && candidate.status !== "rejected") {
      const repair = element("button", "secondary-action", "定向修复 1 次");
      repair.type = "button";
      repair.disabled = Number(pageState.auto_repair_count || 0) >= 1;
      repair.addEventListener("click", () => onRepair(candidate, repair));
      actions.appendChild(repair);
    }
    if (onSelect && candidate.status !== "rejected") {
      const select = element("button", "primary-action", pageState.selected_candidate_id === candidate.candidate_id ? "当前已选" : "选为本页成品");
      select.type = "button";
      select.disabled = pageState.selected_candidate_id === candidate.candidate_id;
      select.addEventListener("click", () => onSelect(candidate, select));
      actions.appendChild(select);
    }
    card.append(image, top, meter, issues, actions);
    gallery.appendChild(card);
  });
  if (!candidates.length) gallery.appendChild(element("p", "creative-empty-copy", "本页还没有候选。可在上方批量上传 1–4 张无字视觉锚点。"));
  section.appendChild(gallery);
  container.appendChild(section);
}
