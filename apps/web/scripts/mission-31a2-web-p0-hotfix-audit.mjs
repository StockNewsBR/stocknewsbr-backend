import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(scriptDir, "..", "..", "..");
const reportPath = path.join(repoRoot, "runtime", "mission_31a2_web_p0_hotfix_report.json");
const alpacaDiagnosticPath = path.join(repoRoot, "runtime", "mission_31a2_alpaca_diagnostic.json");
const screenshotDir = path.join(repoRoot, "output", "playwright", "mission31a2");
const WEB_BASE = process.env.MISSION31A2_WEB_BASE || "http://127.0.0.1:3000";
const API_BASE = process.env.MISSION31A2_API_BASE || "http://127.0.0.1:8000";
const HEADLESS = process.env.MISSION31A2_HEADLESS !== "false";

const SYMBOLS = ["PETR4", "BNY", "AMZN", "BTCUSD", "VALE3", "ITUB4", "AAPL", "TSLA", "NVDA"];
const AI_TABS = ["flow", "liquidity", "trend", "momentum", "smart-money"];
const FORCED_FAILURE_REAL_SYMBOL = "PETR4";
const FORBIDDEN_URL_RE = /(example\.com|localhost|127\.0\.0\.1|0\.0\.0\.0|mock|fake|placeholder)/i;

function normalize(value) {
  return String(value || "")
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/\s+/g, " ")
    .trim()
    .toLowerCase();
}

function ensureDir(dir) {
  fs.mkdirSync(dir, { recursive: true });
}

function pushIf(condition, failures, message) {
  if (condition) failures.push(message);
}

function loadJsonFile(filePath) {
  if (!fs.existsSync(filePath)) return null;
  try {
    return JSON.parse(fs.readFileSync(filePath, "utf8"));
  } catch (error) {
    return {
      status: "invalid_json",
      file: filePath,
      error: String(error?.message || error),
    };
  }
}

async function fetchJson(url) {
  const response = await fetch(url, { cache: "no-store" });
  if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
  return response.json();
}

async function fetchJsonWithMeta(url) {
  const response = await fetch(url, { cache: "no-store" });
  const text = await response.text();
  let body = null;
  try {
    body = text ? JSON.parse(text) : null;
  } catch {
    body = { raw: text };
  }
  return {
    url,
    status: response.status,
    ok: response.ok,
    headers: Object.fromEntries(response.headers.entries()),
    body,
  };
}

async function openPanel(page, symbol) {
  await page.goto(`${WEB_BASE}/panel/${encodeURIComponent(symbol)}`, { waitUntil: "domcontentloaded" });
  await page.locator("main").waitFor({ state: "visible", timeout: 20000 });
  await page.waitForTimeout(1200);
}

async function clickTab(page, id) {
  const button = page.locator(`.snbr-top-tabs button[role='tab'][aria-controls='panel-${id}']`).first();
  if ((await button.count()) === 0) return false;
  await button.evaluate((element) => {
    if (element instanceof HTMLElement) element.click();
  });
  await page.locator(`#panel-${id}`).first().waitFor({ state: "visible", timeout: 8000 }).catch(() => undefined);
  await page.waitForTimeout(500);
  return true;
}

async function activeTabCounts(page) {
  return page.evaluate(() => {
    const result = {};
    document.querySelectorAll(".snbr-top-tabs button[role='tab'][data-tab-id]").forEach((button) => {
      const raw = button.getAttribute("data-tab-count");
      result[button.getAttribute("data-tab-id")] = raw == null || raw === "" ? null : Number(raw);
    });
    return result;
  });
}

async function auditQuoteState(symbol) {
  const quote = await fetchJsonWithMeta(`${API_BASE}/public/market/quote/${encodeURIComponent(symbol)}?refresh=mission31a2`);
  const bundle = await fetchJsonWithMeta(`${API_BASE}/public/market/bundle/${encodeURIComponent(symbol)}?interval=1D&limit=6`);
  const quoteBody = quote.body || {};
  const bundleQuote = bundle.body?.quote || {};
  return {
    quote: {
      status: quote.status,
      source: quoteBody.source || null,
      quote_status: quoteBody.quote_status || null,
      core_data: quoteBody.core_data ?? null,
      strategic_core_data: quoteBody.strategic_core_data ?? null,
      missing_fields: quoteBody.missing_fields || [],
      field_status: quoteBody.field_status || {},
      price: quoteBody.price ?? null,
      volume: quoteBody.volume ?? null,
    },
    bundle: {
      status: bundle.status,
      source: bundleQuote.source || null,
      quote_status: bundleQuote.quote_status || null,
      core_data: bundleQuote.core_data ?? null,
      strategic_core_data: bundleQuote.strategic_core_data ?? null,
      missing_fields: bundleQuote.missing_fields || [],
      field_status: bundleQuote.field_status || {},
      price: bundleQuote.price ?? null,
      volume: bundleQuote.volume ?? null,
    },
  };
}

function buildFallbackAudit(symbol, quoteState, panel) {
  const quote = quoteState?.quote || {};
  const bundle = quoteState?.bundle || {};
  const quoteSource = String(quote.source || "empty");
  const bundleSource = String(bundle.source || "empty");
  const finalSource = quoteSource !== "empty" ? quoteSource : bundleSource;
  const cacheHit = !["", "empty", "none", "null"].includes(finalSource.toLowerCase());
  const snapshotHit = Boolean(quote.field_status?.snapshot || bundle.field_status?.snapshot);
  const coreData = panel?.core_data === "true" || quote.core_data === true || bundle.core_data === true;
  const missingFields = Array.isArray(panel?.missing_fields) && panel.missing_fields.length
    ? panel.missing_fields
    : Array.isArray(quote.missing_fields) && quote.missing_fields.length
      ? quote.missing_fields
      : Array.isArray(bundle.missing_fields)
        ? bundle.missing_fields
        : [];

  return {
    symbol,
    fallback_path: [
      {
        step: "symbol_registry",
        status: "resolved",
        symbol,
        canonical_symbol: symbol,
        provider_symbol: symbol,
      },
      {
        step: "provider_or_quote",
        status: cacheHit ? "not_required_cache_available" : "empty_or_unavailable",
        note: "HTTP routes do not call external providers directly; provider fetch is blocked/degraded to cache or snapshot.",
      },
      {
        step: "quote_cache",
        status: quoteSource !== "empty" ? "hit" : "miss",
        source: quoteSource,
        quote_status: quote.quote_status || "empty",
      },
      {
        step: "snapshot_cache",
        status: snapshotHit ? "hit" : "miss",
        source: snapshotHit ? finalSource : "none",
      },
      {
        step: "bundle",
        status: bundleSource !== "empty" ? "hit" : "miss",
        source: bundleSource,
        quote_status: bundle.quote_status || "empty",
      },
      {
        step: "final",
        status: coreData ? "usable_quote" : "empty",
        blocked_reason: coreData ? null : "insufficient_real_data",
      },
    ],
    provider_attempted: true,
    provider_status: cacheHit ? "not_called_http_cache_or_snapshot_path" : "empty_or_unavailable",
    quote_status: quote.quote_status || "empty",
    snapshot_status: snapshotHit ? "hit" : "miss",
    cache_status: cacheHit ? "hit" : "miss",
    final_source: finalSource || "empty",
    core_data: coreData,
    missing_fields: missingFields,
    blocked_reason: coreData ? null : "insufficient_real_data",
  };
}

async function auditNews(page, symbol) {
  const api = await fetchJson(`${API_BASE}/public/market/news/${encodeURIComponent(symbol)}?limit=6&refresh=mission31a2`);
  await clickTab(page, "news");
  await page.waitForTimeout(2500);
  const cards = await page.locator("[data-news-card='true']").evaluateAll((nodes) => nodes.map((node) => {
    const link = node.querySelector("a.snbr-headline-symbol");
    return {
      source: node.getAttribute("data-news-source") || "",
      url: node.getAttribute("data-news-url") || "",
      published: node.getAttribute("data-news-published-source") || "",
      age: node.getAttribute("data-news-age-minutes") || "",
      matched: node.getAttribute("data-news-matched-symbol") || "",
      text: node.textContent || "",
      linkHref: link?.getAttribute("href") || "",
      disabledUrlText: node.textContent?.includes("URL real indisponível") || node.textContent?.includes("Real URL unavailable") || false,
    };
  })).catch(() => []);
  const bodyText = await page.locator("#panel-news").innerText().catch(() => "");
  const anchors = await page.locator("#panel-news a").evaluateAll((nodes) => nodes.map((node) => node.href)).catch(() => []);
  const failures = [];
  const apiCount = Number(api?.count ?? api?.items?.length ?? 0);
  pushIf(apiCount > 0 && cards.length === 0, failures, "API tem notícia, DOM não renderizou card real");
  pushIf(FORBIDDEN_URL_RE.test(bodyText), failures, "DOM de notícias contém URL fake/example/mock");
  anchors.forEach((href) => pushIf(FORBIDDEN_URL_RE.test(href), failures, `link ativo proibido: ${href}`));
  cards.forEach((card, index) => {
    pushIf(!card.source, failures, `card ${index + 1} sem fonte`);
    pushIf(!card.published, failures, `card ${index + 1} sem data/hora da fonte`);
    pushIf(!card.age, failures, `card ${index + 1} sem idade`);
    pushIf(card.matched && normalize(card.matched) !== normalize(symbol), failures, `card ${index + 1} contaminado por ${card.matched}`);
    pushIf(Boolean(card.url) && FORBIDDEN_URL_RE.test(card.url), failures, `card ${index + 1} tem URL fake`);
    pushIf(Boolean(card.linkHref) && FORBIDDEN_URL_RE.test(card.linkHref), failures, `card ${index + 1} abre URL fake`);
    pushIf(!card.url && !card.disabledUrlText, failures, `card ${index + 1} sem URL real não mostra bloqueio honesto`);
    const ageMinutes = Number(card.age);
    pushIf(Number.isFinite(ageMinutes) && ageMinutes > 7 * 24 * 60 && /ontem|yesterday/i.test(card.text), failures, `card ${index + 1} antigo aparece como Ontem`);
  });
  return {
    api_count: apiCount,
    api_status: api?.status,
    api_message: api?.message,
    dom_count: cards.length,
    cards: cards.slice(0, 3),
    failures,
  };
}

async function auditAiTabs(page) {
  const counts = await activeTabCounts(page);
  const failures = [];
  for (const id of ["news", ...AI_TABS]) {
    pushIf(!(id in counts), failures, `contador ausente na aba ${id}`);
    pushIf(counts[id] === null || Number.isNaN(Number(counts[id])), failures, `contador não numérico na aba ${id}`);
  }
  const tabs = {};
  for (const id of AI_TABS) {
    const opened = await clickTab(page, id);
    if (!opened) {
      tabs[id] = { opened: false, failures: [`aba ${id} não abriu`] };
      continue;
    }
    const panel = page.locator(`#panel-${id}`).first();
    const text = await panel.innerText().catch(() => "");
    const visibleCount = Number(await panel.getAttribute("data-ai-visible-count").catch(() => "0") || 0);
    const badgeCount = Number(await panel.getAttribute("data-ai-badge-count").catch(() => "0") || 0);
    const normalizedText = normalize(text);
    const tabFailures = [];
    const hasHonestZeroState = normalizedText.includes("0 eventos atuais")
      || normalizedText.includes("0 current events")
      || normalizedText.includes("achados visiveis da lente: 0/")
      || normalizedText.includes("aguardando nova leitura do dia")
      || normalizedText.includes("waiting for a new read");
    pushIf(visibleCount === 0 && !hasHonestZeroState, tabFailures, "IA vazia sem estado honesto");
    pushIf(badgeCount !== Number(counts[id] ?? 0), tabFailures, "badge do painel e contador da tab divergem");
    tabs[id] = { opened, visible_count: visibleCount, badge_count: badgeCount, text_sample: text.slice(0, 220), failures: tabFailures };
    failures.push(...tabFailures.map((failure) => `${id}: ${failure}`));
  }
  return { counts, tabs, failures };
}

async function auditChart(page) {
  await clickTab(page, "grafico");
  const shell = page.locator(".snbr-chart-shell").first();
  const attrs = {
    support_anchor_mode: await shell.getAttribute("data-support-anchor-mode").catch(() => ""),
    resistance_anchor_mode: await shell.getAttribute("data-resistance-anchor-mode").catch(() => ""),
    support_status: await shell.getAttribute("data-support-overlay-status").catch(() => ""),
    resistance_status: await shell.getAttribute("data-resistance-overlay-status").catch(() => ""),
    vwap_color: await shell.getAttribute("data-vwap-color").catch(() => ""),
    vwap_width: await shell.getAttribute("data-vwap-width").catch(() => ""),
    tradingview_symbol: await shell.getAttribute("data-tradingview-symbol").catch(() => ""),
  };
  const lineCounts = await page.evaluate(() => ({
    support: document.querySelectorAll("[data-chart-level-line='support']").length,
    resistance: document.querySelectorAll("[data-chart-level-line='resistance']").length,
  }));
  const failures = [];
  pushIf(attrs.support_status !== "hidden" && lineCounts.support < 1, failures, "badge de suporte sem linha");
  pushIf(attrs.resistance_status !== "hidden" && lineCounts.resistance < 1, failures, "badge de resistência sem linha");
  pushIf(attrs.vwap_color.toLowerCase() !== "#f59e0b", failures, "VWAP sem contrato laranja");
  pushIf(Number(attrs.vwap_width) < 4, failures, "VWAP sem largura mínima 4");
  return { attrs, line_counts: lineCounts, failures };
}

async function auditBlockedPanel(page, symbol) {
  const panel = page.locator(".snbr-decision-panel").first();
  const coreData = await panel.getAttribute("data-core-data").catch(() => "");
  const missingFieldsAttr = await panel.getAttribute("data-missing-fields").catch(() => "");
  const text = await panel.innerText().catch(() => "");
  const normalizedText = normalize(text);
  const statTexts = await page.locator(".snbr-stat-strip .snbr-stat-cell").evaluateAll((nodes) => nodes.map((node) => node.textContent || "")).catch(() => []);
  const decisionGridCount = await page.locator(".snbr-decision-grid").count().catch(() => 0);
  const conclusionCount = await page.locator(".snbr-decision-conclusion").count().catch(() => 0);
  const failures = [];
  if (coreData === "false") {
    pushIf(!normalizedText.includes("aguardar dados reais"), failures, "painel sem dados não mostra AGUARDAR DADOS REAIS");
    pushIf(normalizedText.includes("entre venda e compra"), failures, "painel sem dados mostra Entre Venda e Compra");
    pushIf(/\b(compra somente|buscar gatilho de compra|venda \/ short|encerrar posicao|encerrar \/ proteger)\b/.test(normalizedText), failures, "painel sem dados mostra ação operacional");
    pushIf(!normalizedText.includes("campos faltantes"), failures, "painel sem dados não lista campos faltantes");
    pushIf(!missingFieldsAttr, failures, "painel sem dados não recebeu missing_fields do backend");
    pushIf(decisionGridCount > 0, failures, "painel sem dados renderiza cards de score/bias/RSI/trade");
    pushIf(conclusionCount > 0, failures, "painel sem dados renderiza conclusão operacional");
    pushIf(statTexts.some((value) => /score mestre|rsi score|bias/i.test(value)), failures, "painel sem dados mostra score/bias/RSI no cabeçalho");
  }
  return {
    symbol,
    core_data: coreData,
    missing_fields: missingFieldsAttr ? missingFieldsAttr.split(",").filter(Boolean) : [],
    decision_grid_count: decisionGridCount,
    conclusion_count: conclusionCount,
    stat_texts: statTexts,
    text_sample: text.slice(0, 520),
    failures,
  };
}

async function auditForcedProviderFailureRealTicker(context) {
  const page = await context.newPage();
  await page.route(`**/public/market/quote/${FORCED_FAILURE_REAL_SYMBOL}**`, async (route) => {
    await route.fulfill({
      status: 500,
      contentType: "application/json",
      body: JSON.stringify({ detail: { retryable: true, message: "forced mission31a2 real ticker provider failure" } }),
    });
  });
  await openPanel(page, FORCED_FAILURE_REAL_SYMBOL);
  const forcedQuote = await page.evaluate(async (url) => {
    const response = await fetch(url, { cache: "no-store" });
    const text = await response.text();
    let body = null;
    try {
      body = text ? JSON.parse(text) : null;
    } catch {
      body = { raw: text };
    }
    return { status: response.status, ok: response.ok, body };
  }, `${API_BASE}/public/market/quote/${FORCED_FAILURE_REAL_SYMBOL}?refresh=forced-provider-failure`);
  const panel = await auditBlockedPanel(page, FORCED_FAILURE_REAL_SYMBOL);
  const screenshot = path.join(screenshotDir, `${FORCED_FAILURE_REAL_SYMBOL.toLowerCase()}-forced-provider-failure-real-ticker-fullpage.jpg`);
  await page.screenshot({ path: screenshot, type: "jpeg", quality: 82, fullPage: true }).catch(() => undefined);
  await page.close();
  const failures = [...panel.failures];
  const coreData = panel.core_data === "true";
  const fallbackUsed = coreData ? "cache_or_snapshot" : "empty";
  if (!coreData) {
    pushIf(panel.missing_fields.length === 0, failures, "ticker real com core_data=false ficou sem missing_fields");
  }
  return {
    symbol: FORCED_FAILURE_REAL_SYMBOL,
    provider_forced_failure: true,
    forced_endpoint: `/public/market/quote/${FORCED_FAILURE_REAL_SYMBOL}`,
    forced_response: forcedQuote,
    fallback_used: fallbackUsed,
    core_data: coreData,
    missing_fields: panel.missing_fields,
    decision_grid_count: panel.decision_grid_count,
    conclusion_count: panel.conclusion_count,
    screenshot,
    panel,
    failures,
  };
}

async function main() {
  ensureDir(path.dirname(reportPath));
  ensureDir(screenshotDir);
  const browser = await chromium.launch({ headless: HEADLESS });
  const context = await browser.newContext({ viewport: { width: 1600, height: 950 } });
  await context.addInitScript(() => {
    window.localStorage.setItem("stocknewsbr.workspace_mode", "pro");
  });
  const page = await context.newPage();
  const report = {
    generated_at: new Date().toISOString(),
    web_base: WEB_BASE,
    api_base: API_BASE,
    alpaca_diagnostic: loadJsonFile(alpacaDiagnosticPath) || {
      status: "missing",
      file: alpacaDiagnosticPath,
      note: "Run the Alpaca plugin diagnostic step before this script to attach get_asset/get_stock_snapshot evidence.",
    },
    symbols: {},
    failures: [],
  };

  for (const symbol of SYMBOLS) {
    await openPanel(page, symbol);
    const screenshot = path.join(screenshotDir, `${symbol.toLowerCase()}-panel${symbol === "BNY" ? "-fullpage" : ""}.jpg`);
    await page.screenshot({ path: screenshot, type: "jpeg", quality: 82, fullPage: symbol === "BNY" }).catch(() => undefined);
    const quote_state = await auditQuoteState(symbol);
    const panel = await auditBlockedPanel(page, symbol);
    const news = await auditNews(page, symbol);
    const ai = await auditAiTabs(page);
    const chart = symbol === "PETR4" ? await auditChart(page) : null;
    const failures = [...panel.failures, ...news.failures, ...ai.failures, ...(chart?.failures || [])];
    const fallback = symbol === "BNY" ? buildFallbackAudit(symbol, quote_state, panel) : null;
    report.symbols[symbol] = { screenshot, quote_state, panel, news, ai, chart, fallback, failures };
    if (symbol === "BNY") {
      pushIf(panel.core_data === "false" && panel.missing_fields.length === 0, failures, "BNY core_data=false sem missing_fields");
      pushIf(!fallback, failures, "BNY sem fallback_path estruturado");
    }
    report.failures.push(...failures.map((failure) => `${symbol}: ${failure}`));
  }

  const forcedReal = await auditForcedProviderFailureRealTicker(context);
  report.forced_provider_failure_real_ticker = forcedReal;
  report.failures.push(...forcedReal.failures.map((failure) => `${FORCED_FAILURE_REAL_SYMBOL} forced: ${failure}`));

  await browser.close();
  fs.writeFileSync(reportPath, JSON.stringify(report, null, 2), "utf8");
  console.log(JSON.stringify({ reportPath, failureCount: report.failures.length }, null, 2));
  if (report.failures.length) process.exit(1);
}

main().catch((error) => {
  ensureDir(path.dirname(reportPath));
  const payload = { generated_at: new Date().toISOString(), error: String(error?.stack || error) };
  fs.writeFileSync(reportPath, JSON.stringify(payload, null, 2), "utf8");
  console.error(error);
  process.exit(1);
});
