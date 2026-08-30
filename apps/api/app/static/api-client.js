/** Structured browser API failure with status and response payload. */
export class ApiError extends Error {
  constructor(message, { status = 0, payload = null, url = "" } = {}) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.payload = payload;
    this.url = url;
  }
}

async function responsePayload(response) {
  if (response.status === 204) return null;
  const text = await response.text();
  if (!text) return null;
  try {
    return JSON.parse(text);
  } catch {
    return text;
  }
}

/** Execute one JSON-aware API request with timeout and cancellation support. */
export async function request(url, options = {}) {
  const {
    timeoutMs = 45_000,
    signal: upstreamSignal,
    headers: requestedHeaders = {},
    ...fetchOptions
  } = options;
  const controller = new AbortController();
  const abortFromUpstream = () => controller.abort(upstreamSignal?.reason);
  if (upstreamSignal?.aborted) abortFromUpstream();
  else upstreamSignal?.addEventListener("abort", abortFromUpstream, { once: true });
  const timer = window.setTimeout(() => controller.abort("timeout"), timeoutMs);
  const headers = new Headers(requestedHeaders);
  if (fetchOptions.body && !(fetchOptions.body instanceof FormData) && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  try {
    const response = await fetch(url, { ...fetchOptions, headers, signal: controller.signal });
    const payload = await responsePayload(response);
    if (!response.ok) {
      const detail = payload && typeof payload === "object" ? payload.detail : payload;
      throw new ApiError(String(detail || `HTTP ${response.status}`), {
        status: response.status,
        payload,
        url,
      });
    }
    return payload;
  } catch (error) {
    if (error instanceof ApiError) throw error;
    if (controller.signal.aborted) {
      throw new ApiError(controller.signal.reason === "timeout" ? "请求超时，请稍后重试" : "请求已取消", { url });
    }
    throw new ApiError(error?.message || String(error), { url });
  } finally {
    window.clearTimeout(timer);
    upstreamSignal?.removeEventListener("abort", abortFromUpstream);
  }
}

export const apiClient = {
  get(url, options = {}) {
    return request(url, { ...options, method: "GET" });
  },
  post(url, body = {}, options = {}) {
    return request(url, { ...options, method: "POST", body: JSON.stringify(body) });
  },
  put(url, body = {}, options = {}) {
    return request(url, { ...options, method: "PUT", body: JSON.stringify(body) });
  },
  upload(url, files, { field = "file", fields = {}, ...options } = {}) {
    const form = new FormData();
    [...files].forEach((file) => form.append(field, file));
    Object.entries(fields).forEach(([key, value]) => form.append(key, String(value)));
    return request(url, { ...options, method: "POST", body: form });
  },
};
