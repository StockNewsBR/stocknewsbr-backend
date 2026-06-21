import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(scriptDir, "..");
const repoRoot = path.resolve(root, "..", "..");

function read(relativePath) {
  return fs.readFileSync(path.join(repoRoot, relativePath), "utf8");
}

function assertIncludes(source, needle, label) {
  if (!source.includes(needle)) {
    throw new Error(`Mission 30 missing: ${label}`);
  }
}

function assertNotIncludes(source, needle, label) {
  if (source.includes(needle)) {
    throw new Error(`Mission 30 regression: ${label}`);
  }
}

const registry = read("apps/web/lib/symbol-registry.ts");
const tickerChart = read("apps/web/components/ticker-chart.tsx");
const workspaceShell = read("apps/web/components/workspace-shell.tsx");
const workspaceRails = read("apps/web/components/workspace-rails.tsx");
const workspaceSections = read("apps/web/components/workspace-sections.tsx");
const webApi = read("apps/web/lib/api.ts");
const publicNewsService = read("app/services/public_news_service.py");
const css = read("apps/web/app/globals.css");
const mobileRegistry = read("apps/mobile/lib/symbolRegistry.ts");
const mobileApi = read("apps/mobile/lib/api.ts");

for (const expected of [
  "PETR4: [\"PETR4.SA\", \"PETR4 B3\", \"PETR\"",
  "AXIA6: [\"AXIA6.SA\", \"AXIA6 B3\", \"ELET6\"",
  "ASAI3: [\"ASAI3.SA\"",
  "AZUL4: [\"AZUL4.SA\"",
  "B3SA3: [\"B3SA3.SA\"",
  "BTC",
  "XBTUSD",
  "NASDAQ:AAPL",
  "AAPL.US",
  "BULL: [\"NASDAQ:BULL\"",
  "BYDDY: [\"OTC:BYDDY\"",
  "CRM: [\"NYSE:CRM\"",
  "F: [\"NYSE:F\"",
  "WINFUT",
  "export function canonicalSymbol",
  "export function resolveTradingViewSymbolCandidates",
  "export function resolveTradingViewSymbol",
  "export function tradingViewSymbolFor",
  "export function providerSymbolFor",
  "export function symbolCategoryFor",
  "BMFBOVESPA:PETR4",
  "BMFBOVESPA:AXIA6",
  "BINANCE:${canonical.slice(0, -3)}USDT",
  "NASDAQ:AAPL",
  "NYSE:CRM",
  "NYSE:F",
  "OTC:BYDDY",
]) {
  assertIncludes(registry, expected, `web registry contains ${expected}`);
}

assertIncludes(workspaceShell, "resolveCanonicalSymbol", "workspace uses canonical symbol resolver");
assertIncludes(workspaceShell, "resolveCanonicalSymbolAliases", "workspace uses canonical alias resolver");
assertIncludes(workspaceShell, "\"AXIA6.SA\"", "active B3 watchlist uses AXIA6 instead of retired ELET6");
assertIncludes(workspaceShell, "friendlyNetworkErrorMessage", "frontend maps fetch failures to product-safe copy");
assertIncludes(workspaceShell, "sem snapshot", "watchlist has clear missing-price fallback");
assertIncludes(workspaceShell, "sem cotação confirmada", "symbol header avoids R$ n/a for missing quotes");
assertIncludes(workspaceShell, "activeWatchCategoryCounts", "active list counts by canonical category");
assertIncludes(workspaceShell, "CATEGORY_ORDER.reduce((total, category)", "Todos equals B3 + BDR + Crypto + USA");
assertIncludes(workspaceRails, "}: ${activeWatchCount}", "active list count label cannot be mistaken for a negative number");
assertIncludes(workspaceShell, "INTERNAL_AI_TAB_IDS", "internal AI tools remain hidden from top tabs");
assertIncludes(workspaceShell, "shouldShowTopBarTabId", "top bar has explicit visibility rules");
assertIncludes(workspaceShell, "if (INTERNAL_AI_TAB_IDS.has(id)) return false", "Risk, News AI, Macro and Regime tabs are hidden visually");
assertIncludes(workspaceShell, "tabCount != null", "top bar renders explicit ticker-scoped counters for news and visible AI tabs");
assertIncludes(workspaceShell, "aiToolFindingCounts[tab.id] ?? 0", "AI tabs expose zero-count badges instead of looking broken");
assertNotIncludes(workspaceShell, "no data\" : \"sem dados", "top bar does not render no-data AI badges");
assertIncludes(workspaceShell, "news: { label: \"📰 Notícias\"", "common news tab remains available");
assertIncludes(workspaceSections, "Sem notícias relevantes para este ativo agora. Tente atualizar mais tarde.", "empty common news tab explains absence inside the panel");
assertIncludes(workspaceShell, "hasWatchlistSnapshotData", "active list separates assets by valid snapshot");
assertIncludes(workspaceShell, "unavailableGroupedActiveWatchlist", "assets without snapshot are grouped separately");
assertIncludes(workspaceShell, "Ativos temporariamente sem dados", "UI labels the temporary no-data asset section");
assertIncludes(css, ".snbr-watch-unavailable-section", "temporary no-data assets have separated styling");
assertIncludes(css, "clamp(360px, 24vw, 420px)", "left rail is wide enough for full ticker symbols");
assertIncludes(workspaceShell, "decisionTradeLabel(tradeTone", "mixed/conflicting scenarios render Aguardar instead of a forced side");
assertIncludes(workspaceShell, "alignStrategicSectionsWithTrade", "strategic conclusion is aligned with suggested trade side");
assertIncludes(workspaceShell, "alignOperationalDecisionWithTrade", "operational decision copy is aligned with suggested trade side");
assertIncludes(workspaceShell, "StrategicDecisionContract", "strategic panel uses a single visual decision contract");
assertIncludes(workspaceShell, "buildStrategicDecisionContract", "strategic panel contract is built once for all visual fields");
assertIncludes(workspaceShell, "operationalDecisionFromStrategicContract", "operational decision renders from the same final contract");
assertIncludes(workspaceShell, "alignDecisionCardsWithStrategicContract", "decision cards render from the same final contract");
assertIncludes(workspaceShell, "AGUARDAR VENDA / SHORT COM CONFIRMAÇÃO", "bearish trade decision no longer renders generic protection copy");
assertIncludes(workspaceShell, "data-decision-side", "strategic panel exposes final decision side for Playwright");
assertIncludes(workspaceShell, "data-trade-suggested", "strategic panel exposes final suggested trade for Playwright");
assertIncludes(workspaceShell, "directionalBuyBlocked", "buy-side conclusion cannot override bearish/exit final decision");
assertIncludes(workspaceShell, "positionProtectionSections", "exit/close-position decisions render dedicated protection copy");
assertIncludes(workspaceShell, "textHasStandAsideSide", "buy/sell conclusions cannot fall back to stand-aside language");
assertIncludes(workspaceShell, "Zona de proteção", "exit decisions use protection zone instead of buy/sell zone");
assertIncludes(workspaceShell, "Fluxo de entrada não está confirmado", "exit decisions avoid buyer/seller wording in primary reasons");
assertIncludes(workspaceShell, "Resultados de ${oilResults[1]}", "BR news headlines translate common English market title");
assertIncludes(workspaceShell, "0 eventos atuais para este ativo.", "AI empty-state remains available inside the panel");
assertIncludes(workspaceShell, "function formatAiUpdatedAt", "AI freshness uses a centralized timestamp formatter");
assertIncludes(workspaceShell, "day: \"2-digit\"", "AI timestamps show the full day");
assertIncludes(workspaceShell, "year: \"numeric\"", "AI timestamps show the full year");
assertIncludes(workspaceShell, "function aiFreshnessStatus", "AI freshness status is computed explicitly");
assertIncludes(workspaceShell, "Status: atualizado hoje", "current AI reads are labeled as updated today");
assertIncludes(workspaceShell, "Status: leitura do dia anterior · aguardando nova leitura do dia", "previous-day AI reads after reset are labeled clearly");
assertIncludes(workspaceShell, "Detectado", "AI findings show detection timestamp");
assertIncludes(workspaceShell, "Visualizado", "AI findings show viewer timestamp");
assertIncludes(workspaceSections, "data-news-state-count={newsRows.length}", "news panel exposes frontend state count for DOM audit");
assertIncludes(css, ".snbr-chip.fresh", "fresh AI status has visual styling");
assertIncludes(css, ".snbr-chip.stale", "stale AI status has visual styling");
assertIncludes(workspaceShell, "getNews(token, deferredTicker, Date.now())", "common news tab fetches the ticker-specific public news route when bundle is empty");
assertIncludes(webApi, "/public/market/news/${encodeURIComponent(ticker)}?limit=6", "frontend uses the public ticker-specific news endpoint");
assertIncludes(publicNewsService, "_item_belongs_to_symbol(item, ticker)", "public news payload filters items by requested ticker");
assertIncludes(publicNewsService, "\"mixed_ticker_allowed\": False", "public news payload forbids cross-ticker reuse");
assertIncludes(publicNewsService, "schedule_warmup", "public news can request background cache warmup without direct HTTP provider calls");
assertIncludes(publicNewsService, "published_at_source", "public news exposes source publication time");
assertIncludes(publicNewsService, "source_name", "public news exposes source name");
assertIncludes(publicNewsService, "source_url", "public news exposes original source URL");
assertIncludes(publicNewsService, "matched_symbol", "public news exposes matched symbol");
assertIncludes(workspaceShell, "formatNewsAge", "frontend renders news age from source time");
assertIncludes(workspaceShell, "sourceDateIsToday", "frontend classifies source date freshness");
assertIncludes(workspaceSections, "data-news-published-source", "news DOM exposes source publication time for Playwright");
assertIncludes(workspaceSections, "data-news-matched-symbol", "news DOM exposes matched symbol for Playwright");
assertIncludes(workspaceSections, "Notícia incompleta: sem hora da fonte", "news DOM marks incomplete source-time cards");
assertNotIncludes(workspaceShell, "setError(requestError.message)", "raw fetch errors are not shown to users");
assertNotIncludes(workspaceShell, "setError(requestError instanceof Error ? requestError.message", "raw request errors are not shown to users");
assertNotIncludes(workspaceShell, "Failed to fetch", "literal fetch failure is not rendered in the UI");
assertNotIncludes(workspaceShell, "\"ELET3.SA\", \"ELET6.SA\"", "retired ELET6 is not preloaded as active B3 item");
assertIncludes(tickerChart, "resolveTradingViewSymbolCandidates(sourceSymbol)", "ticker chart uses centralized TradingView resolver candidates");
assertIncludes(tickerChart, "data-tradingview-symbol={tradingViewSymbol}", "ticker chart exposes TradingView symbol for DOM audit");
assertIncludes(tickerChart, "data-tradingview-candidates={tradingViewCandidates.join", "ticker chart exposes TradingView fallback candidates for DOM audit");
assertIncludes(tickerChart, "data-chart-status", "ticker chart exposes chart status for DOM audit");
assertIncludes(tickerChart, "data-support-anchor-mode={supportOverlayStatus}", "support level exposes price-scale overlay anchor status");
assertIncludes(tickerChart, "data-resistance-anchor-mode={resistanceOverlayStatus}", "resistance level exposes price-scale overlay anchor status");
assertIncludes(tickerChart, "data-support-overlay-status={supportOverlayStatus}", "support overlay state is explicit for Playwright");
assertIncludes(tickerChart, "data-resistance-overlay-status={resistanceOverlayStatus}", "resistance overlay state is explicit for Playwright");
assertIncludes(tickerChart, "snbr-chart-level-lines", "support/resistance lines render when badges are visible");
assertIncludes(css, ".snbr-chart-level-lines", "support/resistance level CSS is present");
assertNotIncludes(tickerChart, "snbr-chart-level-area", "blue mist fill is removed");
assertNotIncludes(tickerChart, "snbr-chart-level-price-path", "fake price path overlay is removed");
assertNotIncludes(css, ".snbr-chart-level-area", "blue mist CSS fill is removed");
assertNotIncludes(css, "top: 26%", "resistance is not fixed to viewport percentage");
assertNotIncludes(css, "top: 55%", "support is not fixed to viewport percentage");
assertNotIncludes(tickerChart, "style={{ top:", "component does not position levels by local top style");

assertIncludes(mobileRegistry, "export function canonicalSymbol", "mobile has canonical symbol resolver");
assertIncludes(mobileRegistry, "AXIA6: [\"AXIA6.SA\", \"AXIA6 B3\", \"ELET6\"", "mobile registry resolves retired ELET6 to AXIA6");
assertIncludes(mobileApi, "tickerPathValue", "mobile API canonicalizes ticker path values");
assertIncludes(mobileApi, "canonicalSymbol(ticker)", "mobile API uses canonical symbol resolver");

console.log(JSON.stringify({ ok: true, mission: "30", checks: 101 }, null, 2));
