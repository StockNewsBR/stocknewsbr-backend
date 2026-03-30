import type {
  AuthFlowResponse,
  ChartPayload,
  ChatHistoryPayload,
  FeedPayload,
  PollPayload,
  PublicBootstrap,
  QuotePayload,
  TelegramLinkSessionResponse,
  UploadResponse,
  UserAccess,
  WorkspaceData,
  WorkspaceLayout,
} from "./types";

export function resolveApiBase() {
  return (process.env.NEXT_PUBLIC_API_BASE || "http://127.0.0.1:8000").replace(/\/$/, "");
}

function buildUrl(path: string) {
  return `${resolveApiBase()}${path.startsWith("/") ? path : `/${path}`}`;
}

function buildHeaders(token?: string, base?: HeadersInit) {
  return {
    ...(base || {}),
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  };
}

async function parseJson<T>(response: Response): Promise<T> {
  if (!response.ok) {
    let detail = response.statusText;

    try {
      const payload = await response.json();
      detail = payload.detail || JSON.stringify(payload);
    } catch {
      detail = response.statusText;
    }

    throw new Error(detail || "request_failed");
  }

  return response.json() as Promise<T>;
}

async function request<T>(path: string, options?: RequestInit & { token?: string }) {
  const headers = buildHeaders(options?.token, options?.headers);
  const response = await fetch(buildUrl(path), {
    ...options,
    headers,
  });

  return parseJson<T>(response);
}

export function buildWebSocketUrl(path: string) {
  const base = resolveApiBase();
  const websocketBase = base.replace(/^http/, "ws");
  return `${websocketBase}${path.startsWith("/") ? path : `/${path}`}`;
}

export function getBootstrap() {
  return request<PublicBootstrap>("/public/bootstrap");
}

export function loginJson(
  email: string,
  password: string,
  options?: { channel?: string; device_id?: string; device_label?: string },
) {
  return request<AuthFlowResponse>("/auth/login-json", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password, ...(options || {}) }),
  });
}

export function verifyLoginOtp(login_token: string, code: string) {
  return request<AuthFlowResponse>("/auth/login/verify-otp", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ login_token, code }),
  });
}

export function logoutAuth(token: string) {
  return request<{ ok: boolean }>("/auth/logout", {
    method: "POST",
    token,
  });
}

export function getAccess(token: string) {
  return request<UserAccess>("/auth/access", { token });
}

export function updateProfile(
  token: string,
  payload: { display_name?: string | null; email?: string | null; avatar_url?: string | null },
) {
  return request<UserAccess>("/auth/profile", {
    method: "PATCH",
    token,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export function requestTelegramLink(token: string, origin_channel = "web") {
  return request<TelegramLinkSessionResponse>("/auth/telegram/link/request", {
    method: "POST",
    token,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ origin_channel }),
  });
}

export function getWorkspace(token: string) {
  return request<WorkspaceData>("/web/workspace/data", { token });
}

export function searchAssets(token: string, query: string) {
  return request<string[]>(`/web/search/${encodeURIComponent(query)}`, { token });
}

export function saveWorkspaceLayout(token: string, payload: WorkspaceLayout) {
  return request<WorkspaceLayout>("/web/workspace/layout", {
    method: "PUT",
    token,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export function getChart(token: string, ticker: string) {
  return request<ChartPayload>(`/web/chart/${encodeURIComponent(ticker)}?interval=1D`, { token });
}

export function getFeed(token: string, ticker: string) {
  return request<FeedPayload>(`/ticker/${encodeURIComponent(ticker)}/feed?limit=500`, { token });
}

export function createPost(
  token: string,
  ticker: string,
  payload: { text: string; image_url?: string | null; sentiment?: string | null },
) {
  return request(`/ticker/${encodeURIComponent(ticker)}/post`, {
    method: "POST",
    token,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export function commentOnPost(
  token: string,
  postId: number,
  payload: { text: string; image_url?: string | null },
) {
  return request(`/post/${postId}/comment`, {
    method: "POST",
    token,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export function likePost(token: string, postId: number) {
  return request<{ likes: number }>(`/post/${postId}/like`, {
    method: "POST",
    token,
  });
}

export function unlikePost(token: string, postId: number) {
  return request<{ likes: number }>(`/post/${postId}/unlike`, {
    method: "POST",
    token,
  });
}

export function blockUser(token: string, target: number) {
  return request<{ status: string }>("/block", {
    method: "POST",
    token,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ target }),
  });
}

export function muteUser(token: string, target: number) {
  return request<{ status: string }>("/mute", {
    method: "POST",
    token,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ target }),
  });
}

export function reportPost(token: string, post_id: number, reason = "community") {
  return request<{ status: string }>("/report", {
    method: "POST",
    token,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ post_id, reason }),
  });
}

export function deletePost(token: string, postId: number) {
  return request<{ status: string; post_id: number }>(`/post/${postId}`, {
    method: "DELETE",
    token,
  });
}

export function getPoll(ticker: string) {
  return request<PollPayload>(`/poll/${encodeURIComponent(ticker)}`);
}

export function votePoll(token: string, ticker: string, option: string) {
  return request<PollPayload>(`/poll/${encodeURIComponent(ticker)}/vote?option=${encodeURIComponent(option)}`, {
    method: "POST",
    token,
  });
}

export function getChatHistory(token: string, ticker: string) {
  return request<ChatHistoryPayload>(`/chat/${encodeURIComponent(ticker)}/history?limit=60`, { token });
}

export function postChatMessage(
  token: string,
  ticker: string,
  payload: { text: string; image_url?: string | null },
) {
  return request(`/chat/${encodeURIComponent(ticker)}/message`, {
    method: "POST",
    token,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export function getQuote(token: string, ticker: string) {
  return request<QuotePayload>(`/ticker/${encodeURIComponent(ticker)}`, { token });
}

export function getPushStatus(token: string) {
  return request("/push/status", { token });
}

export function getMediaStatus(token: string) {
  return request("/api/media/status", { token });
}

export async function uploadMedia(token: string, file: File) {
  const body = new FormData();
  body.append("file", file);

  const response = await fetch(buildUrl("/api/media/upload"), {
    method: "POST",
    headers: buildHeaders(token),
    body,
  });

  return parseJson<UploadResponse>(response);
}
