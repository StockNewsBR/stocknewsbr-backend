import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(scriptDir, "..", "..", "..");
const reportPath = process.env.MISSION30E_REPORT_PATH
  ? path.resolve(repoRoot, process.env.MISSION30E_REPORT_PATH)
  : path.join(repoRoot, "runtime", "mission_30e_news_report.json");

const API_BASE = process.env.MISSION30E_API_BASE || "http://127.0.0.1:8000";
const WEB_BASE = process.env.MISSION30E_WEB_BASE || "http://localhost:3000";
const HEADLESS = process.env.MISSION30E_HEADLESS !== "false";
const NEWS_SYMBOLS = (process.env.MISSION30E_SYMBOLS || "BULL,BYDDY,AAPL,NVDA,TSLA,MSFT,AMD,PETR4,VALE3,ITUB4,BTCUSD")
  .split(",")
  .map((item) => item.trim().toUpperCase())
  .filter(Boolean);

function normalizeText(value) {
  return String(value || "")
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/\s+/g, " ")
    .trim()
    .toLowerCase();
}

function newsCount(payload) {
  if (!payload || typeof payload !== "object") return 0;
  if (Array.isArray(payload.items)) return payload.items.length;
  if (Array.isArray(payload.news)) return payload.news.length;
  if (payload.news && typeof payload.news === "object") return newsCount(payload.news);
  if (Number.isFinite(Number(payload.count))) return Number(payload.count);
  return 0;
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
  while (newsCount(latest.body) === 0 && latest.body?.warmup_requested && Date.now() - startedAt < 28000) {
    await sleep(2500);
    latest = await fetchJson(`/public/market/news/${encodeURIComponent(symbol)}?limit=6&refresh=${Date.now()}`);
  }
  return latest;
}

async function openPanel(page, symbol) {
  await page.goto(`${WEB_BASE}/panel/${encodeURIComponent(symbol)}`, { waitUntil: "domcontentloaded" });
  await page.locator("main").waitFor({ state: "visible", timeout: 15000 });
  await page.waitForFunction((expectedSymbol) => {
    const text = document.body?.innerText || "";
    return text.includes(`Symbol / ${expectedSymbol}`) || text.includes(`Notícias de ${expectedSymbol}`) || window.location.pathname.toUpperCase().endsWith(`/PANEL/${expectedSymbol}`);
  }, symbol, { timeout: 18000 }).catch(() => undefined);
  await page.waitForTimeout(800);
}

async function clickNewsTab(page) {
  const tab = page.locator(".snbr-top-tabs button[role='tab'][aria-controls='panel-news']").first();
  if ((await tab.count()) === 0) return false;
  await tab.scrollIntoViewIfNeeded().catch(() => undefined);
  await tab.click({ force: true });
  await page.locator("#panel-news:visible").first().waitFor({ state: "visible", timeout: 12000 });
  return true;
}

async function waitForNewsDom(page, expectedCount) {
  const startedAt = Date.now();
  let currentCount = 0;
  let fallbackVisible = false;
  while (Date.now() - startedAt < 30000) {
    const panel = page.locator("#panel-news:visible").first();
    currentCount = await panel.locator("[data-news-card='true']").count().catch(() => 0);
    const text = await panel.innerText().catch(() => "");
    fallbackVisible = normalizeText(text).includes("sem noticias relevantes");
    if (expectedCount <= 0 || currentCount > 0) break;
    await sleep(1200);
  }
  return { currentCount, fallbackVisible };
}

async function collectDomNews(page, symbol, expectedCount) {
  await openPanel(page, symbol);
  const newsTabVisible = await clickNewsTab(page);
  const panel = page.locator("#panel-news:visible").first();
  const waited = await waitForNewsDom(page, expectedCount);
  const panelText = await panel.innerText().catch(() => "");
  const frontendStateCount = Number(await panel.getAttribute("data-news-state-count").catch(() => "0")) || 0;
  const cards = await panel.locator("[data-news-card='true']").evaluateAll((items) =>
    items.map((item) => {
      const get = (name) => item.getAttribute(name) || "";
      const strong = item.querySelector("strong")?.textContent?.trim() || "";
      return {
        headline: strong,
        text: item.textContent?.replace(/\s+/g, " ").trim() || "",
        source: get("data-news-source"),
        url: get("data-news-url"),
        published_at_source: get("data-news-published-source"),
        age_minutes: get("data-news-age-minutes"),
        matched_symbol: get("data-news-matched-symbol"),
        stale: get("data-news-stale"),
        incomplete: get("data-news-incomplete"),
      };
    }),
  ).catch(() => []);
  const decisionText = await page.locator(".snbr-decision-panel:visible").first().innerText().catch(() => "");
  return {
    news_tab_visible: newsTabVisible,
    frontend_state_count: frontendStateCount,
    dom_visible_count: cards.length,
    fallback_visible: waited.fallbackVisible || normalizeText(panelText).includes("sem noticias relevantes"),
    panel_text_sample: panelText.slice(0, 700),
    cards,
    decision_text_sample: decisionText.slice(0, 700),
  };
}

function validateApiItems(symbol, routeBody, failures) {
  const items = Array.isArray(routeBody?.items) ? routeBody.items : [];
  for (const [index, item] of items.entries()) {
    const prefix = `${symbol}: API item ${index + 1}`;
    if (!item.title && !item.headline) failures.push(`${prefix} sem titulo`);
    if (!item.source_name && !item.source) failures.push(`${prefix} sem fonte`);
    if (!item.source_url && !item.url) failures.push(`${prefix} sem URL original`);
    if (!item.published_at_source && !item.is_incomplete) failures.push(`${prefix} sem hora da fonte e sem marcar incompleta`);
    if (item.matched_symbol && String(item.matched_symbol).toUpperCase() !== symbol) {
      failures.push(`${prefix} matched_symbol=${item.matched_symbol} diferente de ${symbol}`);
    }
  }
}

function validateDomCards(symbol, dom, failures) {
  for (const [index, card] of dom.cards.entries()) {
    const prefix = `${symbol}: DOM card ${index + 1}`;
    const text = normalizeText(card.text);
    if (!card.headline) failures.push(`${prefix} sem titulo visivel`);
    if (!card.source || !text.includes("fonte")) failures.push(`${prefix} sem fonte visivel`);
    if (!card.url || !text.includes("url original")) failures.push(`${prefix} sem URL original visivel`);
    if (!card.age_minutes || !text.includes("idade")) failures.push(`${prefix} sem idade visivel`);
    if (!card.matched_symbol || card.matched_symbol.toUpperCase() !== symbol) failures.push(`${prefix} ticker relacionado invalido`);
    if (!text.includes("publicado em")) failures.push(`${prefix} sem data/hora da fonte visivel`);
    if (card.incomplete === "true" && !text.includes("noticia incompleta")) failures.push(`${prefix} incompleto sem aviso visual`);
    if (!card.published_at_source && card.incomplete !== "true") failures.push(`${prefix} sem hora da fonte e sem data-news-incomplete`);
    if (card.stale === "true" && !(text.includes("noticia anterior") || text.includes("ontem"))) {
      failures.push(`${prefix} noticia antiga sem marcador Noticia anterior/Ontem`);
    }
    if (card.incomplete === "true" && card.headline && normalizeText(dom.decision_text_sample).includes(normalizeText(card.headline))) {
      failures.push(`${prefix} noticia incompleta citada na conclusao estrategica`);
    }
  }
}

async function auditSymbol(page, symbol) {
  const failures = [];
  const route = await fetchNewsWithWarmup(symbol);
  const bundle = await fetchJson(`/public/market/bundle/${encodeURIComponent(symbol)}?interval=1D&limit=6&refresh=${Date.now()}`);
  const routeCount = newsCount(route.body);
  const bundleCount = newsCount(bundle.body?.news);
  const dom = await collectDomNews(page, symbol, Math.max(routeCount, bundleCount));

  validateApiItems(symbol, route.body, failures);
  validateDomCards(symbol, dom, failures);

  if (!dom.news_tab_visible) failures.push(`${symbol}: aba Noticias nao apareceu`);
  if ((routeCount > 0 || bundleCount > 0) && (dom.dom_visible_count <= 0 || dom.fallback_visible)) {
    failures.push(`${symbol}: API/bundle tem noticia, mas DOM mostrou fallback ou nenhum card`);
  }

  return {
    symbol,
    route_status: route.status,
    route_count: routeCount,
    route_warmup_requested: Boolean(route.body?.warmup_requested),
    bundle_status: bundle.status,
    bundle_count: bundleCount,
    frontend_state_count: dom.frontend_state_count,
    dom_visible_count: dom.dom_visible_count,
    fallback_visible: dom.fallback_visible,
    news_tab_visible: dom.news_tab_visible,
    cards: dom.cards,
    failures,
  };
}

function writeReport(report) {
  fs.mkdirSync(path.dirname(reportPath), { recursive: true });
  fs.writeFileSync(reportPath, JSON.stringify(report, null, 2), "utf8");
}

async function main() {
  const browser = await chromium.launch({ headless: HEADLESS });
  const context = await browser.newContext({ locale: "pt-BR", viewport: { width: 1600, height: 1000 } });
  const page = await context.newPage();
  page.setDefaultTimeout(12000);
  const report = {
    mission: "30E",
    scope: "P0.14-P0.17 news source-time DOM audit",
    generated_at: new Date().toISOString(),
    api_base: API_BASE,
    web_base: WEB_BASE,
    symbols: NEWS_SYMBOLS,
    assets: [],
    failures: [],
  };

  try {
    for (const symbol of NEWS_SYMBOLS) {
      console.error(`[30E] news ${symbol}`);
      const result = await auditSymbol(page, symbol);
      report.assets.push(result);
      report.failures.push(...result.failures);
      writeReport(report);
    }
  } finally {
    await browser.close();
  }

  writeReport(report);
  if (report.failures.length) {
    console.error(JSON.stringify({ ok: false, failures: report.failures, reportPath }, null, 2));
    process.exit(1);
  }
  console.log(JSON.stringify({ ok: true, mission: "30E", symbols: NEWS_SYMBOLS.length, reportPath }, null, 2));
}

main().catch((error) => {
  const message = error instanceof Error ? error.stack || error.message : String(error);
  fs.mkdirSync(path.dirname(reportPath), { recursive: true });
  fs.writeFileSync(reportPath, JSON.stringify({ ok: false, error: message }, null, 2), "utf8");
  console.error(message);
  process.exit(1);
});
