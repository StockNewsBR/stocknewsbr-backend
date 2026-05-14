const API_BASE = (process.env.EXPO_PUBLIC_API_BASE || "http://127.0.0.1:8000").replace(/\/$/, "");
const DEFAULT_TIMEOUT_MS = 12000;

type QueryValue = string | number | boolean | null | undefined;

function normalizePath(path: string) {
  return path.startsWith("/") ? path : `/${path}`;
}

function buildUrl(path: string, query?: Record<string, QueryValue>) {
  const url = new URL(`${API_BASE}${normalizePath(path)}`);

  if (query) {
    Object.entries(query).forEach(([key, value]) => {
      if (value === null || value === undefined || value === "") {
        return;
      }
      url.searchParams.set(key, String(value));
    });
  }

  return url.toString();
}

async function readErrorDetail(response: Response) {
  const fallback = response.statusText || "request_failed";

  try {
    const payload = await response.json();
    if (typeof payload === "string") {
      return payload;
    }
    if (payload && typeof payload === "object") {
      if (typeof payload.detail === "string") {
        return payload.detail;
      }
      return JSON.stringify(payload);
    }
  } catch {}

  try {
    const text = await response.text();
    if (text) {
      return text;
    }
  } catch {}

  return fallback;
}

async function requestJson<T>(
  path: string,
  init: RequestInit = {},
  query?: Record<string, QueryValue>,
  timeoutMs: number = DEFAULT_TIMEOUT_MS,
): Promise<T> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), timeoutMs);

  try {
    const response = await fetch(buildUrl(path, query), {
      ...init,
      headers: {
        Accept: "application/json",
        ...(init.headers || {}),
      },
      signal: controller.signal,
    });

    if (!response.ok) {
      throw new Error(await readErrorDetail(response));
    }

    if (response.status === 204) {
      return undefined as T;
    }

    return (await response.json()) as T;
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") {
      throw new Error("request_timeout");
    }
    throw error;
  } finally {
    clearTimeout(timeout);
  }
}

export async function getPublicBootstrap() {
  return requestJson<Record<string, any>>("/public/bootstrap");
}

export async function getBillingPricing(market: "BR" | "USA" = "BR") {
  return requestJson<Record<string, any>>("/billing/pricing", {}, { market });
}

export async function loginJson(
  email: string,
  password: string,
  options?: { channel?: string; device_id?: string; device_label?: string },
) {
  return requestJson<Record<string, any>>(
    "/auth/login-json",
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password, ...(options || {}) }),
    },
  );
}

export async function verifyLoginOtp(login_token: string, code: string) {
  return requestJson<Record<string, any>>(
    "/auth/login/verify-otp",
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ login_token, code }),
    },
  );
}

export async function getAccess(token: string) {
  return requestJson<Record<string, any>>("/auth/access", {
    headers: { Authorization: `Bearer ${token}` },
  });
}

export async function updateProfile(
  token: string,
  payload: { email?: string | null; display_name?: string | null; avatar_url?: string | null },
) {
  return requestJson<Record<string, any>>(
    "/auth/profile",
    {
      method: "PATCH",
      headers: {
        Authorization: `Bearer ${token}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
    },
  );
}

export async function logoutAuth(token: string) {
  return requestJson<Record<string, any>>("/auth/logout", {
    method: "POST",
    headers: { Authorization: `Bearer ${token}` },
  });
}

export async function requestTelegramLink(token: string, origin_channel = "app") {
  return requestJson<Record<string, any>>(
    "/auth/telegram/link/request",
    {
      method: "POST",
      headers: {
        Authorization: `Bearer ${token}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ origin_channel }),
    },
  );
}

export async function linkTelegramAccount(
  token: string,
  payload: { telegram_id: string; telegram_username?: string | null },
) {
  return requestJson<Record<string, any>>(
    "/auth/telegram/link",
    {
      method: "POST",
      headers: {
        Authorization: `Bearer ${token}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
    },
  );
}

export async function getWorkspace(token: string) {
  return requestJson<Record<string, any>>("/app/workspace/data", {
    headers: { Authorization: `Bearer ${token}` },
  });
}

export async function getChart(token: string, ticker: string, interval = "1D") {
  return requestJson<Record<string, any>>(
    `/chart/${encodeURIComponent(ticker)}`,
    {
      headers: { Authorization: `Bearer ${token}` },
    },
    { interval },
  );
}

export async function getTickerSnapshot(token: string, ticker: string) {
  return requestJson<Record<string, any>>(`/ticker/${encodeURIComponent(ticker)}`, {
    headers: { Authorization: `Bearer ${token}` },
  });
}

export async function getNews(token: string, ticker: string, limit = 8) {
  return requestJson<Record<string, any>>(
    `/news/${encodeURIComponent(ticker)}`,
    {
      headers: { Authorization: `Bearer ${token}` },
    },
    { limit },
  );
}

export async function getTickerFeed(token: string, ticker: string, limit = 24) {
  return requestJson<Record<string, any>>(
    `/ticker/${encodeURIComponent(ticker)}/feed`,
    {
      headers: { Authorization: `Bearer ${token}` },
    },
    { limit },
  );
}

export async function createTickerPost(
  token: string,
  ticker: string,
  payload: { text: string; image_url?: string | null; sentiment?: string | null },
) {
  return requestJson<Record<string, any>>(
    `/ticker/${encodeURIComponent(ticker)}/post`,
    {
      method: "POST",
      headers: {
        Authorization: `Bearer ${token}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
    },
  );
}

export async function createTickerComment(
  token: string,
  postId: number,
  payload: { text: string; image_url?: string | null },
) {
  return requestJson<Record<string, any>>(
    `/post/${postId}/comment`,
    {
      method: "POST",
      headers: {
        Authorization: `Bearer ${token}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
    },
  );
}

export async function createTickerRepost(
  token: string,
  postId: number,
  payload?: { quote_text?: string | null },
) {
  return requestJson<Record<string, any>>(
    `/post/${postId}/repost`,
    {
      method: "POST",
      headers: {
        Authorization: `Bearer ${token}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload || {}),
    },
  );
}

export async function deleteTickerRepost(token: string, postId: number) {
  return requestJson<Record<string, any>>(`/post/${postId}/repost`, {
    method: "DELETE",
    headers: { Authorization: `Bearer ${token}` },
  });
}

export async function followUser(token: string, userId: number) {
  return requestJson<Record<string, any>>(
    `/social/users/${userId}/follow`,
    {
      method: "POST",
      headers: { Authorization: `Bearer ${token}` },
    },
  );
}

export async function unfollowUser(token: string, userId: number) {
  return requestJson<Record<string, any>>(
    `/social/users/${userId}/follow`,
    {
      method: "DELETE",
      headers: { Authorization: `Bearer ${token}` },
    },
  );
}

export async function getSocialPosts(token: string, limit = 50) {
  return requestJson<Record<string, any>>("/social/posts", {
    headers: { Authorization: `Bearer ${token}` },
  }, { limit });
}

export async function getMarketSnapshot(token: string) {
  return requestJson<Record<string, any>>("/market/snapshot", {
    headers: { Authorization: `Bearer ${token}` },
  });
}

export async function getMarketSnapshotInfo(token: string) {
  return requestJson<Record<string, any>>("/market/snapshot/info", {
    headers: { Authorization: `Bearer ${token}` },
  });
}

export async function getMarketHeatmap(token: string) {
  return requestJson<Record<string, any>>("/market/heatmap", {
    headers: { Authorization: `Bearer ${token}` },
  });
}

export async function getMarketNarrative(token: string) {
  return requestJson<Record<string, any>>("/market/narrative", {
    headers: { Authorization: `Bearer ${token}` },
  });
}

export async function getMarketRadar(token: string) {
  return requestJson<Record<string, any>>("/market/radar", {
    headers: { Authorization: `Bearer ${token}` },
  });
}

export async function getMarketOpportunity(token: string) {
  return requestJson<Record<string, any>>("/market/opportunity", {
    headers: { Authorization: `Bearer ${token}` },
  });
}

export async function getTopMovers(token: string) {
  return requestJson<Record<string, any>>("/market/top_movers", {
    headers: { Authorization: `Bearer ${token}` },
  });
}

export async function getPoll(ticker: string) {
  return requestJson<Record<string, any>>(`/poll/${encodeURIComponent(ticker)}`);
}

export async function getPollHistory(ticker: string, limit = 8) {
  return requestJson<Record<string, any>>(
    `/poll/${encodeURIComponent(ticker)}/history`,
    {},
    { limit },
  );
}

export async function votePoll(token: string, ticker: string, option: string) {
  return requestJson<Record<string, any>>(
    `/poll/${encodeURIComponent(ticker)}/vote`,
    {
      method: "POST",
      headers: { Authorization: `Bearer ${token}` },
    },
    { option },
  );
}
