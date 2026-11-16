/**
 * Thin typed client over the backend REST API.
 *
 * - Every request is same-origin (`/api/v1/...`) and goes through the Next.js
 *   rewrite, so the backend's httpOnly cookies are sent automatically.
 * - Auth failures surface as `ApiError` with `status: 401`; the auth provider
 *   reacts to them once, in one place.
 * - Errors from the backend always have the shape `{error: {code, message}}`.
 */

export class ApiError extends Error {
  status: number;
  code: string;
  details: unknown;
  requestId?: string;

  constructor(message: string, status: number, code = "unknown", details?: unknown, requestId?: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.details = details;
    this.requestId = requestId;
  }
}

const BASE = "/api/v1";

type Query = Record<string, string | number | boolean | null | undefined>;

export function qs(query?: Query): string {
  if (!query) return "";
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query)) {
    if (value === undefined || value === null || value === "") continue;
    params.set(key, String(value));
  }
  const s = params.toString();
  return s ? `?${s}` : "";
}

async function toError(res: Response): Promise<ApiError> {
  let code = `http_${res.status}`;
  let message = res.statusText || "Request failed";
  let details: unknown;
  let requestId: string | undefined;
  try {
    const body = (await res.json()) as { error?: { code?: string; message?: string; details?: unknown; request_id?: string }; detail?: unknown };
    if (body?.error) {
      code = body.error.code ?? code;
      message = body.error.message ?? message;
      details = body.error.details;
      requestId = body.error.request_id;
    } else if (typeof body?.detail === "string") {
      message = body.detail;
    }
  } catch {
    /* non-JSON (e.g. proxy error) — keep the status text */
  }
  return new ApiError(message, res.status, code, details, requestId);
}

interface RequestOptions {
  method?: string;
  body?: unknown;
  form?: FormData;
  signal?: AbortSignal;
  /** Skip the global unauthorized handler (used by the session probe itself). */
  quiet?: boolean;
}

export async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = "GET", body, form, signal } = options;
  const init: RequestInit = { method, signal, credentials: "same-origin", cache: "no-store" };
  if (form) {
    init.body = form;
  } else if (body !== undefined) {
    init.headers = { "content-type": "application/json" };
    init.body = JSON.stringify(body);
  }

  let res: Response;
  try {
    res = await fetch(`${BASE}${path}`, init);
  } catch (err) {
    if ((err as Error).name === "AbortError") throw err;
    throw new ApiError("Tarmoqqa ulanib bo'lmadi", 0, "network_error");
  }

  if (res.status === 204) return undefined as T;
  if (!res.ok) throw await toError(res);
  const type = res.headers.get("content-type") ?? "";
  if (!type.includes("application/json")) return (await res.text()) as unknown as T;
  return (await res.json()) as T;
}

export const api = {
  get: <T>(path: string, query?: Query, signal?: AbortSignal) => request<T>(`${path}${qs(query)}`, { signal }),
  post: <T>(path: string, body?: unknown) => request<T>(path, { method: "POST", body }),
  postQuery: <T>(path: string, query?: Query) => request<T>(`${path}${qs(query)}`, { method: "POST" }),
  postForm: <T>(path: string, form: FormData) => request<T>(path, { method: "POST", form }),
  patch: <T>(path: string, body?: unknown) => request<T>(path, { method: "PATCH", body }),
  del: <T>(path: string) => request<T>(path, { method: "DELETE" }),
};

/** Fetch a file (PDF/XLSX/CSV) through the authenticated proxy and save it. */
export async function downloadFile(path: string, fallbackName = "nextgen-export"): Promise<string> {
  const res = await fetch(`${BASE}${path}`, { credentials: "same-origin", cache: "no-store" });
  if (!res.ok) throw await toError(res);
  const blob = await res.blob();
  const disposition = res.headers.get("content-disposition") ?? "";
  const match = /filename\*?=(?:UTF-8'')?"?([^";]+)"?/i.exec(disposition);
  const filename = match ? decodeURIComponent(match[1]) : fallbackName;
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  setTimeout(() => URL.revokeObjectURL(url), 4000);
  return filename;
}
