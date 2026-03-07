export class ApiError extends Error {
  status: number;
  payload: unknown;

  constructor(status: number, payload: unknown) {
    let message = `HTTP ${status}`;
    if (typeof payload === "string") {
      message = payload;
    } else if (typeof payload === "object" && payload && "error" in payload) {
      const err = (payload as { error?: unknown }).error;
      if (typeof err === "string") {
        message = err;
      } else if (typeof err === "object" && err && "message" in err) {
        message = String((err as { message?: unknown }).message || message);
      } else {
        message = JSON.stringify(err);
      }
    }
    super(message);
    this.status = status;
    this.payload = payload;
  }
}

const ACCESS_TOKEN_KEY = "ca_access_token";
let inMemoryToken = "";

export function getStoredToken(): string {
  if (inMemoryToken) {
    return inMemoryToken;
  }
  return localStorage.getItem(ACCESS_TOKEN_KEY) || "";
}

export function storeToken(token: string | null): void {
  inMemoryToken = token || "";
  if (!token) {
    localStorage.removeItem(ACCESS_TOKEN_KEY);
    return;
  }
  localStorage.setItem(ACCESS_TOKEN_KEY, token);
}

export function clearToken(): void {
  storeToken(null);
}

export function toQuery(params: Record<string, string | number | boolean | undefined | null>): string {
  const search = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value === undefined || value === null || value === "") {
      return;
    }
    search.set(key, String(value));
  });
  const out = search.toString();
  return out ? `?${out}` : "";
}

export async function apiFetch<T = unknown>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers || {});
  const token = getStoredToken();
  if (token && !headers.has("Authorization")) {
    headers.set("Authorization", `Bearer ${token}`);
  }

  const response = await fetch(path, {
    ...init,
    headers,
    credentials: "include",
  });

  const contentType = response.headers.get("content-type") || "";
  const body = contentType.includes("application/json") ? await response.json() : await response.text();

  if (!response.ok) {
    if (response.status === 401) {
      clearToken();
      if (typeof window !== "undefined" && !window.location.pathname.startsWith("/login")) {
        const next = encodeURIComponent(window.location.pathname + window.location.search);
        window.location.assign(`/login?next=${next}`);
      }
    }
    throw new ApiError(response.status, body);
  }
  return body as T;
}
