import type {
  AuthFlowResponse,
  ChartPayload,
  ChatHistoryPayload,
  FeedPayload,
  NewsPayload,
  PollPayload,
  PublicAiToolsPayload,
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
  const controller = options?.signal ? null : new AbortController();
  const timeout = controller
    ? setTimeout(() => controller.abort(), 15000)
    : undefined;

  try {
    const response = await fetch(buildUrl(path), {
      cache: "no-store",
      ...options,
      headers,
      signal: options?.signal || controller?.signal,
    });

    return parseJson<T>(response);
  } finally {
    if (timeout) clearTimeout(timeout);
  }
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

export function getChart(token: string, ticker: string, interval = "1D") {
  return request<ChartPayload>(`/web/chart/${encodeURIComponent(ticker)}?interval=${encodeURIComponent(interval)}`, { token });
}

export function getPublicChart(ticker: string, interval = "1D") {
  return request<ChartPayload>(`/public/market/chart/${encodeURIComponent(ticker)}?interval=${encodeURIComponent(interval)}`);
}

export function getFeed(token: string, ticker: string) {
  return request<FeedPayload>(`/ticker/${encodeURIComponent(ticker)}/feed?limit=500`, { token });
}

export function getNews(token: string | null | undefined, ticker: string) {
  const route = token ? `/news/${encodeURIComponent(ticker)}?limit=6` : `/public/market/news/${encodeURIComponent(ticker)}?limit=6`;
  return request<NewsPayload>(route, token ? { token } : undefined);
}

export function getPublicQuote(ticker: string) {
  return request<QuotePayload>(`/public/market/quote/${encodeURIComponent(ticker)}`);
}

export function getPublicQuotes(symbols: string[]) {
  const params = encodeURIComponent(symbols.join(","));
  return request<{ items: QuotePayload[]; count: number }>(`/public/market/quotes?symbols=${params}`);
}

export function getPublicAiTools() {
  return request<PublicAiToolsPayload>("/public/market/ai-tools");
}

export async function getPublicQuotesChunked(symbols: string[], chunkSize = 16) {
  const uniqueSymbols = Array.from(new Set(symbols.filter(Boolean)));
  const chunks = Array.from({ length: Math.ceil(uniqueSymbols.length / chunkSize) }, (_, index) =>
    uniqueSymbols.slice(index * chunkSize, (index + 1) * chunkSize),
  );
  const results = await Promise.allSettled(chunks.map((chunk) => getPublicQuotes(chunk)));
  const items = results.flatMap((result) => (result.status === "fulfilled" ? result.value.items || [] : []));

  return {
    items,
    count: items.length,
  };
}

function hasMarketQuoteValue(quote?: QuotePayload | null): quote is QuotePayload {
  if (!quote) return false;
  const source = String((quote as any).source || "").toLowerCase();
  const status = String((quote as any).quote_status || "").toLowerCase();
  if (source === "empty" || status === "empty" || status === "partial") return false;
  const price = Number(quote.price);
  return Number.isFinite(price) && price > 0;
}

function normalizeQuoteSymbol(symbol: string) {
  const raw = String(symbol || "").trim().toUpperCase();
  if (!raw) return "";
  const withoutBrazilSuffix = raw.replace(/\.SA$/, "");
  if (withoutBrazilSuffix.endsWith("-USD")) return withoutBrazilSuffix.replace(/-USD$/, "USD");
  if (withoutBrazilSuffix.endsWith("USDT")) return `${withoutBrazilSuffix.slice(0, -4)}USD`;
  return withoutBrazilSuffix;
}

function quoteSymbolAliases(symbol?: string | null) {
  const raw = String(symbol || "").trim().toUpperCase();
  const normalized = normalizeQuoteSymbol(raw);
  const aliases = new Set<string>();
  if (raw) aliases.add(raw);
  if (normalized) aliases.add(normalized);
  if (normalized.endsWith("USD")) {
    aliases.add(normalized.replace(/USD$/, "-USD"));
    aliases.add(normalized.replace(/USD$/, "USDT"));
  }
  if (/^[A-Z]{4}(3|4|5|6|11)$/.test(normalized) || /^[A-Z]{4,5}34$/.test(normalized)) {
    aliases.add(`${normalized}.SA`);
  }
  return Array.from(aliases);
}

function storeQuoteAliases(bySymbol: Map<string, QuotePayload>, item: QuotePayload, requestedSymbol?: string) {
  const normalized = normalizeQuoteSymbol(item.symbol || requestedSymbol || "");
  const normalizedItem = { ...item, symbol: normalized || item.symbol };
  const aliases = [...quoteSymbolAliases(item.symbol), ...quoteSymbolAliases(requestedSymbol)];
  for (const alias of aliases) {
    if (!alias) continue;
    const normalizedAlias = normalizeQuoteSymbol(alias);
    const current = bySymbol.get(alias) || bySymbol.get(normalizedAlias);
    if (hasMarketQuoteValue(normalizedItem) || !hasMarketQuoteValue(current)) {
      bySymbol.set(alias, normalizedItem);
      if (normalizedAlias) bySymbol.set(normalizedAlias, normalizedItem);
    }
  }
}

function getQuoteAlias(bySymbol: Map<string, QuotePayload>, symbol: string) {
  for (const alias of quoteSymbolAliases(symbol)) {
    const quote = bySymbol.get(alias) || bySymbol.get(normalizeQuoteSymbol(alias));
    if (quote) return quote;
  }
  return null;
}

async function getPublicQuotesIndividually(symbols: string[], concurrency = 4) {
  const uniqueSymbols = Array.from(new Set(symbols.map(normalizeQuoteSymbol).filter(Boolean)));
  const items: QuotePayload[] = [];
  let cursor = 0;

  async function worker() {
    while (cursor < uniqueSymbols.length) {
      const symbol = uniqueSymbols[cursor];
      cursor += 1;
      try {
        items.push(await getPublicQuote(symbol));
      } catch {
        // Partial market-provider failures should not block the whole board.
      }
    }
  }

  await Promise.all(Array.from({ length: Math.min(concurrency, uniqueSymbols.length) }, worker));
  return items;
}

export async function getPublicQuotesRobust(symbols: string[], chunkSize = 12, fallbackConcurrency = 0) {
  const uniqueSymbols = Array.from(new Set(symbols.map(normalizeQuoteSymbol).filter(Boolean)));
  const bulk = await getPublicQuotesChunked(uniqueSymbols, chunkSize);
  const bySymbol = new Map<string, QuotePayload>();

  for (const item of bulk.items || []) {
    if (!item?.symbol) continue;
    storeQuoteAliases(bySymbol, item, item.symbol);
  }

  const missingOrEmpty = uniqueSymbols.filter((symbol) => !hasMarketQuoteValue(getQuoteAlias(bySymbol, symbol)));

  if (missingOrEmpty.length && fallbackConcurrency > 0) {
    const fallbackItems = await getPublicQuotesIndividually(missingOrEmpty, fallbackConcurrency);
    for (const item of fallbackItems) {
      if (!item?.symbol) continue;
      storeQuoteAliases(bySymbol, item, item.symbol);
    }
  }

  const items = uniqueSymbols.map((symbol) => getQuoteAlias(bySymbol, symbol)).filter(hasMarketQuoteValue);
  return {
    items,
    count: items.length,
  };
}

export function getPublicInsight(ticker: string, interval = "1D") {
  return request<{
    symbol: string;
    score?: number | null;
    rsi?: number | null;
    trend_bias?: string | null;
    signal?: string | null;
    summary?: Record<string, unknown>;
  }>(`/public/market/insight/${encodeURIComponent(ticker)}?interval=${encodeURIComponent(interval)}`);
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

export function repostPost(
  token: string,
  postId: number,
  payload?: { quote_text?: string | null },
) {
  return request<{ status: string; post_id: number; repost: Record<string, unknown> }>(`/post/${postId}/repost`, {
    method: "POST",
    token,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload || {}),
  });
}

export function unrepostPost(token: string, postId: number) {
  return request<{ status: string; post_id: number }>(`/post/${postId}/repost`, {
    method: "DELETE",
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

export function followUser(token: string, targetUserId: number) {
  return request<{ status: string; is_following: boolean }>(`/social/users/${targetUserId}/follow`, {
    method: "POST",
    token,
  });
}

export function unfollowUser(token: string, targetUserId: number) {
  return request<{ status: string; is_following: boolean }>(`/social/users/${targetUserId}/follow`, {
    method: "DELETE",
    token,
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

export function getQuote(token: string | null | undefined, ticker: string) {
  const route = token ? `/ticker/${encodeURIComponent(ticker)}` : `/public/market/quote/${encodeURIComponent(ticker)}`;
  return request<QuotePayload>(route, token ? { token } : undefined);
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
