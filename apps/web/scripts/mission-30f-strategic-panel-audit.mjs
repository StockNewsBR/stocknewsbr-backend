import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(scriptDir, "..", "..", "..");
const reportPath = process.env.MISSION30F_REPORT_PATH
  ? path.resolve(repoRoot, process.env.MISSION30F_REPORT_PATH)
  : path.join(repoRoot, "runtime", "mission_30f_strategic_panel_report.json");

const API_BASE = process.env.MISSION30F_API_BASE || "http://127.0.0.1:8000";
const WEB_BASE = process.env.MISSION30F_WEB_BASE || "http://localhost:3000";
const HEADLESS = process.env.MISSION30F_HEADLESS !== "false";
const NEWS_WARMUP_MS = Number(process.env.MISSION30F_NEWS_WARMUP_MS || 6000);
const SYMBOLS = (process.env.MISSION30F_SYMBOLS || "CRM,F,BULL,BYDDY,AAPL,NVDA,TSLA,MSFT,AMD,PETR4,VALE3,BTCUSD")
  .split(",")
  .map((item) => item.trim().toUpperCase())
  .filter(Boolean);

const EXPECTED_TRADINGVIEW = {
  CRM: "NYSE:CRM",
  F: "NYSE:F",
  BULL: "NASDAQ:BULL",
  BYDDY: "OTC:BYDDY",
  AAPL: "NASDAQ:AAPL",
  NVDA: "NASDAQ:NVDA",
  TSLA: "NASDAQ:TSLA",
  MSFT: "NASDAQ:MSFT",
  AMD: "NASDAQ:AMD",
  PETR4: "BMFBOVESPA:PETR4",
  VALE3: "BMFBOVESPA:VALE3",
  BTCUSD: "BINANCE:BTCUSDT",
};

function normalizeText(value) {
  return String(value || "")
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/\s+/g, " ")
    .trim()
    .toLowerCase();
}

function containsAny(value, needles) {
  const normalized = normalizeText(value);
  return needles.some((needle) => normalized.includes(normalizeText(needle)));
}

function routeCount(payload) {
  if (!payload || typeof payload !== "object") return 0;
  if (Array.isArray(payload.items)) return payload.items.length;
  if (Array.isArray(payload.news)) return payload.news.length;
  if (payload.news && typeof payload.news === "object") return routeCount(payload.news);
  if (Number.isFinite(Number(payload.count))) return Number(payload.count);
  return 0;
}

function quoteHasPrice(payload) {
  if (!payload || typeof payload !== "object") return false;
  const price = Number(payload.price ?? payload.last_price ?? payload.close);
  return Number.isFinite(price) && price > 0;
}

async function sleep(ms) {
  await new Promise((resolve) => setTimeout(resolve, ms));
}

async function fetchJson(route) {
  const url = `${API_BASE}${route}`;
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 20000);
  try {
    const response = await fetch(url, { headers: { accept: "application/json" }, signal: controller.signal });
    const text = await response.text();
    let body = null;
    try {
      body = text ? JSON.parse(text) : null;
    } catch {
      body = { parse_error: text.slice(0, 500) };
    }
    return { ok: response.ok, status: response.status, url, body };
  } catch (error) {
    return { ok: false, status: 0, url, body: { error: error instanceof Error ? error.message : String(error) } };
  } finally {
    clearTimeout(timeout);
  }
}

async function fetchNewsWithWarmup(symbol) {
  let latest = await fetchJson(`/public/market/news/${encodeURIComponent(symbol)}?limit=6&refresh=${Date.now()}`);
  const startedAt = Date.now();
  while (routeCount(latest.body) === 0 && latest.body?.warmup_requested && Date.now() - startedAt < NEWS_WARMUP_MS) {
    await sleep(1000);
    latest = await fetchJson(`/public/market/news/${encodeURIComponent(symbol)}?limit=6&refresh=${Date.now()}`);
  }
  return latest;
}

async function openPanel(page, symbol) {
  await page.goto(`${WEB_BASE}/panel/${encodeURIComponent(symbol)}`, { waitUntil: "domcontentloaded" });
  await page.locator("main").waitFor({ state: "visible", timeout: 15000 });
  await page.waitForFunction((expectedSymbol) => {
    const panel = document.querySelector(".snbr-decision-panel");
    const selected = panel?.getAttribute("data-selected-symbol") || "";
    const text = document.body?.innerText || "";
    return selected === expectedSymbol || text.includes(`Symbol / ${expectedSymbol}`) || window.location.pathname.toUpperCase().endsWith(`/PANEL/${expectedSymbol}`);
  }, symbol, { timeout: 20000 }).catch(() => undefined);
  await page.waitForTimeout(900);
}

async function enableProMode(page) {
  const button = page.locator(".snbr-decision-mode-actions button").first();
  if ((await button.count()) > 0) {
    await button.click({ force: true }).catch(() => undefined);
    await page.waitForTimeout(300);
  }
}

async function clickTopTab(page, controls) {
  const tab = page.locator(`.snbr-top-tabs button[role='tab'][aria-controls='${controls}']`).first();
  if ((await tab.count()) === 0) return false;
  await tab.scrollIntoViewIfNeeded().catch(() => undefined);
  await tab.click({ force: true });
  await page.locator(`#${controls}:visible`).first().waitFor({ state: "visible", timeout: 12000 }).catch(() => undefined);
  await page.waitForTimeout(300);
  return true;
}

function extractCardValue(cards, labelPattern) {
  const pattern = new RegExp(labelPattern, "i");
  for (const raw of cards) {
    const lines = String(raw || "").split(/\r?\n/).map((line) => line.trim()).filter(Boolean);
    if (!lines.length || !pattern.test(lines[0])) continue;
    return lines[1] || "";
  }
  return "";
}

function contradictionIssues(snapshot) {
  const issues = [];
  const trade = normalizeText(snapshot.trade_suggested);
  const decision = normalizeText(snapshot.decision_now);
  const body = `${snapshot.decision_now} ${snapshot.bias} ${snapshot.direction_probable} ${snapshot.conclusion_text}`;
  const text = normalizeText(body);
  const isBuy = /\b(compra|buy|long)\b/.test(trade);
  const isSell = /\b(venda|short|sell)\b/.test(trade);
  const isExit = /\b(encerrar|close position|exit)\b/.test(trade);
  const isWait = /\b(aguardar|wait)\b/.test(trade);

  if (isBuy && !/\b(compra|buy|long)\b/.test(decision)) issues.push("Trade Compra sem Decisão Agora compradora");
  if (isSell && !/\b(venda|short|sell)\b/.test(decision)) issues.push("Trade Venda/Short sem Decisão Agora vendedora");
  if (isExit && !/\b(encerrar|protect|proteger|close)\b/.test(decision)) issues.push("Trade Encerrar sem decisão de proteção");
  if (isWait && /\b(comprar agora|vender agora|short agora|entrada prioritaria|operacao recomendada)\b/.test(text)) issues.push("Aguardar com texto de execução imediata");

  if (isBuy && /\b(venda|short|encerrar posicao|proteger posicao|nenhum lado|ficar de fora|reduzir exposicao)\b/.test(text)) {
    issues.push("texto vendedor/proteção em Trade Compra");
  }
  if (isSell && /\b(compra|comprador|compra tem prioridade|plano comprador|nenhum lado|ficar de fora)\b/.test(text)) {
    issues.push("texto comprador/neutro em Trade Venda/Short");
  }
  if (isExit && /\b(compra|venda|short|nova operacao|lado comprador|lado vendedor)\b/.test(text)) {
    issues.push("texto direcional em Trade Encerrar posição");
  }
  return issues;
}

async function auditSymbol(page, symbol) {
  const quote = await fetchJson(`/public/market/quote/${encodeURIComponent(symbol)}?refresh=${Date.now()}`);
  const bundle = await fetchJson(`/public/market/bundle/${encodeURIComponent(symbol)}?interval=1D&limit=6&refresh=${Date.now()}`);
  const news = await fetchNewsWithWarmup(symbol);

  await openPanel(page, symbol);
  await enableProMode(page);
  await clickTopTab(page, "panel-grafico");

  const mainText = await page.locator("main").innerText().catch(() => "");
  const panel = page.locator(`.snbr-decision-panel[data-selected-symbol="${symbol}"]`).first();
  await panel.waitFor({ state: "visible", timeout: 15000 });
  const panelText = await panel.innerText().catch(() => "");
  const cards = await panel.locator(".snbr-decision-card:visible").evaluateAll((items) => items.map((item) => item.innerText || item.textContent || ""));
  const chartShell = page.locator(".snbr-chart-shell[data-tradingview-symbol]").first();
  const tradingviewSymbol = await chartShell.getAttribute("data-tradingview-symbol").catch(() => null);
  const chartStatus = await chartShell.getAttribute("data-chart-status").catch(() => null);
  const coreData = await panel.getAttribute("data-core-data").catch(() => "false");
  const displayedSymbol = await panel.getAttribute("data-selected-symbol").catch(() => "");
  const decisionNow = await panel.getAttribute("data-decision-now").catch(() => null);
  const tradeSuggested = await panel.getAttribute("data-trade-suggested").catch(() => null);
  const conclusionText = await page.locator(".snbr-decision-conclusion:visible").first().innerText().catch(() => "");
  const symbolNotFoundVisible = containsAny(mainText, ["Esse símbolo não existe", "This symbol does not exist"]);
  const failedFetchVisible = containsAny(mainText, ["Failed to fetch"]);

  await clickTopTab(page, "panel-news");
  const domNewsCount = await page.locator("[data-news-card]").count().catch(() => 0);
  const newsCards = await page.locator("[data-news-card]").evaluateAll((items) => items.map((item) => ({
    title: item.querySelector("strong")?.textContent?.trim() || "",
    source: item.getAttribute("data-news-source") || "",
    url: item.getAttribute("data-news-url") || "",
    published: item.getAttribute("data-news-published-source") || "",
    age: item.getAttribute("data-news-age-minutes") || "",
    matched: item.getAttribute("data-news-matched-symbol") || "",
    text: item.textContent || "",
  }))).catch(() => []);
  const routeNewsCount = routeCount(news.body);

  const snapshot = {
    requested_symbol: symbol,
    displayed_symbol: displayedSymbol,
    tradingview_symbol: tradingviewSymbol,
    chart_status: chartStatus || "unknown",
    chart_error_text: symbolNotFoundVisible ? "symbol_not_found" : "",
    price: quote.body?.price ?? bundle.body?.quote?.price ?? null,
    variation: quote.body?.change_pct ?? bundle.body?.quote?.change_pct ?? null,
    volume: quote.body?.volume ?? bundle.body?.quote?.volume ?? null,
    score_mestre: extractCardValue(cards, "Score Mestre|Master Score"),
    rsi_score: extractCardValue(cards, "RSI"),
    bias: (panelText.match(/VI[ÉE]S\s+([^\n]+)/i)?.[1] || extractCardValue(cards, "Regime") || "").trim(),
    decision_now: decisionNow || "",
    trade_suggested: tradeSuggested || extractCardValue(cards, "Trade Sugerido|Suggested Trade"),
    direction_probable: extractCardValue(cards, "Direção provável|Likely Direction"),
    regime: extractCardValue(cards, "Regime"),
    risk: (panelText.match(/RISCO\s+([^\n]+)/i)?.[1] || extractCardValue(cards, "Risco|Risk") || "").trim(),
    conclusion_text: conclusionText,
    news_count: domNewsCount,
    api_news_count: routeNewsCount,
    core_data: coreData === "true",
    quote_available: quoteHasPrice(quote.body) || quoteHasPrice(bundle.body?.quote),
    failed_fetch_visible: failedFetchVisible,
    symbol_not_found_visible: symbolNotFoundVisible,
    news_cards: newsCards.slice(0, 3),
    failures: [],
  };

  if (snapshot.displayed_symbol !== symbol) snapshot.failures.push(`displayed_symbol diferente: ${snapshot.displayed_symbol}`);
  if (EXPECTED_TRADINGVIEW[symbol] && snapshot.tradingview_symbol !== EXPECTED_TRADINGVIEW[symbol]) {
    snapshot.failures.push(`TradingView esperado ${EXPECTED_TRADINGVIEW[symbol]}, recebido ${snapshot.tradingview_symbol}`);
  }
  if (symbolNotFoundVisible) snapshot.failures.push("TradingView exibiu símbolo inexistente");
  if (failedFetchVisible) snapshot.failures.push("DOM exibiu Failed to fetch");
  if (!snapshot.core_data && containsAny(snapshot.trade_suggested, ["Compra", "Venda / Short", "Buy", "Sell/Short"])) {
    snapshot.failures.push("ativo sem dados reais gerou trade direcional");
  }
  if (routeNewsCount > 0 && domNewsCount === 0) snapshot.failures.push("API possui notícia, mas DOM não renderizou card");
  for (const [index, card] of newsCards.entries()) {
    if (!card.title || !card.source || !card.url || !card.published || !card.age) {
      snapshot.failures.push(`notícia ${index + 1} sem título/fonte/url/data/idade`);
    }
    if (card.matched && normalizeText(card.matched) !== normalizeText(symbol)) {
      snapshot.failures.push(`notícia ${index + 1} pertence a ${card.matched}`);
    }
  }
  snapshot.contradictions = contradictionIssues(snapshot);
  snapshot.contradiction_count = snapshot.contradictions.length;
  snapshot.failures.push(...snapshot.contradictions);
  return snapshot;
}

async function main() {
  fs.mkdirSync(path.dirname(reportPath), { recursive: true });
  const browser = await chromium.launch({ headless: HEADLESS });
  const context = await browser.newContext({ viewport: { width: 1600, height: 950 } });
  const page = await context.newPage();
  const results = [];
  try {
    for (const symbol of SYMBOLS) {
      results.push(await auditSymbol(page, symbol));
    }
  } finally {
    await context.close().catch(() => undefined);
    await browser.close().catch(() => undefined);
  }
  const failures = results.flatMap((item) => item.failures.map((failure) => `${item.requested_symbol}: ${failure}`));
  const report = {
    ok: failures.length === 0,
    mission: "30F",
    generated_at: new Date().toISOString(),
    api_base: API_BASE,
    web_base: WEB_BASE,
    assets: results,
    failures,
  };
  fs.writeFileSync(reportPath, JSON.stringify(report, null, 2));
  if (failures.length) {
    console.error(JSON.stringify({ ok: false, mission: "30F", failures, reportPath }, null, 2));
    process.exit(1);
  }
  console.log(JSON.stringify({ ok: true, mission: "30F", symbols: results.length, reportPath }, null, 2));
}

await main();
