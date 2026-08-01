(() => {
  const REQUEST_EVENT = "x2red:wechat-editor-request";
  const RESPONSE_EVENT = "x2red:wechat-editor-response";
  const INSTALLED_FLAG = "__X2RED_WECHAT_PAGE_BRIDGE_INSTALLED__";

  if (window[INSTALLED_FLAG]) return;
  window[INSTALLED_FLAG] = true;

  function respond(requestId, result) {
    document.dispatchEvent(new CustomEvent(RESPONSE_EVENT, {
      detail: JSON.stringify({ requestId, result }),
    }));
  }

  function invokeEditor(apiName, apiParam, timeoutMs = 5000) {
    return new Promise((resolve, reject) => {
      const api = window.__MP_Editor_JSAPI__;
      if (!api || typeof api.invoke !== "function") {
        reject(new Error("official_api_unavailable"));
        return;
      }
      let settled = false;
      const timer = window.setTimeout(() => {
        if (settled) return;
        settled = true;
        reject(new Error(`${apiName}_timeout`));
      }, timeoutMs);
      const finish = (callback) => (value) => {
        if (settled) return;
        settled = true;
        window.clearTimeout(timer);
        callback(value);
      };
      try {
        api.invoke({
          apiName,
          apiParam,
          sucCb: finish((result) => {
            const message = String(result?.err_msg || result?.errMsg || "");
            if (/fail|error/i.test(message)) reject(new Error(message));
            else resolve(result || {});
          }),
          errCb: finish((error) => reject(new Error(String(error?.err_msg || error?.errMsg || error || apiName)))),
        });
      } catch (error) {
        finish(reject)(error);
      }
    });
  }

  async function waitForReady(timeoutMs = 7000) {
    const startedAt = Date.now();
    let lastError = "";
    while (Date.now() - startedAt < timeoutMs) {
      try {
        const result = await invokeEditor("mp_editor_get_isready", {}, 1200);
        if (result?.isReady) return { ok: true, isNew: Boolean(result.isNew) };
      } catch (error) {
        lastError = error.message || String(error);
      }
      await new Promise((resolve) => window.setTimeout(resolve, 250));
    }
    return { ok: false, code: "editor_not_ready", error: lastError };
  }

  async function setContent(html) {
    if (!window.__MP_Editor_JSAPI__ || typeof window.__MP_Editor_JSAPI__.invoke !== "function") {
      return { ok: false, code: "official_api_unavailable" };
    }
    const ready = await waitForReady();
    if (!ready.ok) return ready;

    try {
      await invokeEditor("mp_editor_set_content", { content: html }, 6500);
      return { ok: true, method: "official_api_set_content", isNew: ready.isNew };
    } catch (setError) {
      try {
        await invokeEditor("mp_editor_insert_html", { html, isSelect: false }, 6500);
        return { ok: true, method: "official_api_insert_html", isNew: ready.isNew };
      } catch (insertError) {
        return {
          ok: false,
          code: "official_api_write_failed",
          error: `${setError.message || setError}; ${insertError.message || insertError}`,
        };
      }
    }
  }

  document.addEventListener(REQUEST_EVENT, (event) => {
    let request;
    try {
      request = JSON.parse(String(event.detail || "{}"));
    } catch {
      return;
    }
    const requestId = request?.requestId;
    if (!requestId) return;
    if (request.action !== "set_content") {
      respond(requestId, { ok: false, code: "unsupported_action" });
      return;
    }
    void setContent(String(request.payload?.html || ""))
      .then((result) => respond(requestId, result))
      .catch((error) => respond(requestId, {
        ok: false,
        code: "official_api_exception",
        error: error.message || String(error),
      }));
  });
})();
