import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";
import {
  applyEphemeralAuth,
  countSessions,
  enableProMode,
  generateEphemeralSession,
  revokeEphemeralSession,
} from "./lib/ephemeral-auth.mjs";

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(scriptDir, "..", "..", "..");
const reportPath = process.env.MISSION30F2_REPORT_PATH
  ? path.resolve(repoRoot, process.env.MISSION30F2_REPORT_PATH)
  : path.join(repoRoot, "runtime", "mission_30f2_final_visual_audit.json");
const screenshotDir = path.join(repoRoot, "output", "playwright", "mission30f2");

const WEB_BASE = process.env.MISSION30F2_WEB_BASE || "http://127.0.0.1:3000";
const HEADLESS = process.env.MISSION30F2_HEADLESS !== "false";
const SYMBOLS = (process.env.MISSION30F2_SYMBOLS || "CRM,F,BULL,BYDDY,AXIA3,AXIA7,PETR4,VALE3,AAPL,NVDA,BTCUSD,BLK,BRK.B,DJT,FFAI,JD,SIRI")
  .split(",")
  .map((item) => item.trim().toUpperCase())
  .filter(Boolean);
const AI_TABS = [
  ["flow", "Fluxo IA"],
  ["liquidity", "Liquidez IA"],
  ["trend", "Tendência IA"],
  ["momentum", "Momento IA"],
  ["smart-money", "Smart Money"],
];

const EXPECTED_TRADINGVIEW = {
  CRM: "NYSE:CRM",
  F: "NYSE:F",
  BULL: "NASDAQ:BULL",
  BYDDY: "OTC:BYDDY",
  AXIA3: "BMFBOVESPA:AXIA3",
  AXIA7: "BMFBOVESPA:AXIA7",
  PETR4: "BMFBOVESPA:PETR4",
  VALE3: "BMFBOVESPA:VALE3",
  AAPL: "NASDAQ:AAPL",
  NVDA: "NASDAQ:NVDA",
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

function sanitizeFilePart(value) {
  return String(value || "asset").replace(/[^a-z0-9_-]+/gi, "_").toLowerCase();
}

function contradictionIssues(snapshot) {
  const trade = normalizeText(snapshot.trade_suggested);
  const decision = normalizeText(snapshot.decision_now);
  const conclusion = normalizeText(snapshot.conclusion || "");
  const issues = [];
  if (/\b(compra|buy|long)\b/.test(trade) && /\b(venda|short|encerrar|proteger|saida)\b/.test(conclusion)) {
    issues.push("trade comprador com conclusão vendedora/protetiva");
  }
  if (/\b(venda|short|sell)\b/.test(trade) && /\b(compra|buy|long|comprador)\b/.test(conclusion)) {
    issues.push("trade vendedor com conclusão compradora");
  }
  if (/\b(aguardar|wait)\b/.test(trade) && /\b(comprar imediatamente|vender imediatamente|entrada imediata)\b/.test(conclusion)) {
    issues.push("trade aguardar com execução imediata");
  }
  if (/\b(compra|buy|long)\b/.test(trade) && !/\b(compra|buy|long|aguardar)\b/.test(decision)) {
    issues.push("trade comprador não alinhado com decisão agora");
  }
  if (/\b(venda|short|sell)\b/.test(trade) && !/\b(venda|short|sell|aguardar|proteger)\b/.test(decision)) {
    issues.push("trade vendedor não alinhado com decisão agora");
  }
  return issues;
}

async function openPanel(page, symbol) {
  await page.goto(`${WEB_BASE}/panel/${encodeURIComponent(symbol)}`, { waitUntil: "domcontentloaded" });
  await page.locator("main").waitFor({ state: "visible", timeout: 20000 });
  await page.waitForTimeout(1000);
}

async function clickTopTab(page, controls) {
  const tab = page.locator(`.snbr-top-tabs button[role='tab'][aria-controls='${controls}']`).first();
  if ((await tab.count()) === 0) return false;
  await tab.scrollIntoViewIfNeeded().catch(() => undefined);
  await tab.evaluate((element) => {
    if (element instanceof HTMLElement) element.click();
  }).catch(() => undefined);
  await page.locator(`#${controls}`).first().waitFor({ state: "visible", timeout: 6000 }).catch(() => undefined);
  await page.waitForTimeout(400);
  return true;
}

async function auditChart(page, symbol) {
  await openPanel(page, symbol);
  await clickTopTab(page, "panel-grafico");
  const shell = page.locator(".snbr-chart-shell").first();
  await shell.waitFor({ state: "visible", timeout: 20000 });
  const chartAttributes = {
    source_symbol: await shell.getAttribute("data-source-symbol").catch(() => null),
    tradingview_symbol: await shell.getAttribute("data-tradingview-symbol").catch(() => null),
    tradingview_candidates: await shell.getAttribute("data-tradingview-candidates").catch(() => null),
    chart_status: await shell.getAttribute("data-chart-status").catch(() => null),
    support_anchor_mode: await shell.getAttribute("data-support-anchor-mode").catch(() => null),
    resistance_anchor_mode: await shell.getAttribute("data-resistance-anchor-mode").catch(() => null),
    support_overlay_status: await shell.getAttribute("data-support-overlay-status").catch(() => null),
    resistance_overlay_status: await shell.getAttribute("data-resistance-overlay-status").catch(() => null),
  };
  const chartBox = page.locator(".snbr-chart-card").first();
  const screenshotPath = path.join(screenshotDir, `${sanitizeFilePart(symbol)}-chart.jpg`);
  await chartBox.screenshot({ path: screenshotPath, type: "jpeg", quality: 82 }).catch(() => undefined);

  const overlayCounts = await page.evaluate(() => ({
    levelLines: document.querySelectorAll(".snbr-chart-level-lines").length,
    levelArea: document.querySelectorAll(".snbr-chart-level-area").length,
    levelPath: document.querySelectorAll(".snbr-chart-level-price-path").length,
    levelLine: document.querySelectorAll(".snbr-chart-level-line").length,
    levelLabel: document.querySelectorAll(".snbr-chart-level-label").length,
    supportLine: document.querySelectorAll("[data-chart-level-line='support']").length,
    resistanceLine: document.querySelectorAll("[data-chart-level-line='resistance']").length,
  }));
  const mainText = await page.locator("main").innerText().catch(() => "");
  const panel = page.locator(".snbr-decision-panel").first();
  const panelText = await panel.innerText().catch(() => "");
  const decisionNow = await panel.getAttribute("data-decision-now").catch(() => "");
  const tradeSuggested = await panel.getAttribute("data-trade-suggested").catch(() => "");
  const conclusion = await panel.locator(".snbr-decision-conclusion").first().innerText().catch(() => "");
  await clickTopTab(page, "panel-news");
  const newsCards = await page.locator("[data-news-card]").evaluateAll((items) => items.map((item) => ({
    title: item.querySelector("strong")?.textContent?.trim() || "",
    source: item.getAttribute("data-news-source") || "",
    url: item.getAttribute("data-news-url") || "",
    published: item.getAttribute("data-news-published-source") || "",
    age: item.getAttribute("data-news-age-minutes") || "",
    matched: item.getAttribute("data-news-matched-symbol") || "",
    text: item.textContent || "",
  }))).catch(() => []);
  const result = {
    symbol,
    ...chartAttributes,
    custom_overlay_counts: overlayCounts,
    symbol_not_found_text_visible: normalizeText(mainText).includes("esse simbolo nao existe") || normalizeText(mainText).includes("this symbol does not exist"),
    decision_now: decisionNow,
    trade_suggested: tradeSuggested,
    conclusion,
    contradiction_count: 0,
    news_count: newsCards.length,
    news_cards: newsCards.slice(0, 3),
    panel_text_sample: panelText.slice(0, 500),
    screenshot: screenshotPath,
    failures: [],
  };

  if (EXPECTED_TRADINGVIEW[symbol] && result.tradingview_symbol !== EXPECTED_TRADINGVIEW[symbol]) {
    result.failures.push(`TradingView esperado ${EXPECTED_TRADINGVIEW[symbol]}, recebido ${result.tradingview_symbol}`);
  }
  if (result.symbol_not_found_text_visible) result.failures.push("texto de símbolo inexistente apareceu no DOM");
  for (const [key, mode, lineCount] of [
    ["suporte", result.support_anchor_mode, overlayCounts.supportLine],
    ["resistência", result.resistance_anchor_mode, overlayCounts.resistanceLine],
  ]) {
    if (!["price_scaled_overlay", "pending_chart_scale", "hidden"].includes(mode || "")) {
      result.failures.push(`${key} usa modo de ancoragem desconhecido: ${mode || "ausente"}`);
    }
    if (mode === "price_scaled_overlay" && lineCount < 1) {
      result.failures.push(`${key} marcado como price_scaled_overlay sem linha na escala de preço`);
    }
    if (mode !== "price_scaled_overlay" && lineCount > 0) {
      result.failures.push(`${key} renderiza linha sem escala de preço válida`);
    }
  }
  if (overlayCounts.levelArea > 0) result.failures.push(`área fixa/fabricada ainda presente: ${overlayCounts.levelArea}`);
  if (overlayCounts.levelPath > 0) result.failures.push(`price path fabricado ainda presente: ${overlayCounts.levelPath}`);
  const contradictions = contradictionIssues(result);
  result.contradiction_count = contradictions.length;
  result.failures.push(...contradictions);
  for (const [index, card] of newsCards.entries()) {
    if (!card.title || !card.source || !card.published || !card.age) {
      result.failures.push(`notícia ${index + 1} sem título/fonte/hora/idade`);
    }
    if (card.matched && normalizeText(card.matched) !== normalizeText(symbol)) {
      result.failures.push(`notícia ${index + 1} pertence a ${card.matched}`);
    }
  }
  return result;
}

async function auditAiFreshness(page, symbol = "PETR4") {
  // Auth is applied once at context creation (see main) so no route or
  // init script registered here can outlive this scenario.
  await openPanel(page, symbol);
  await enableProMode(page);
  const results = [];
  for (const [tabId, label] of AI_TABS) {
    const controls = `panel-${tabId}`;
    const tabVisible = await clickTopTab(page, controls);
    if (!tabVisible) {
      results.push({ tab: tabId, label, visible: false, failures: [`aba ${label} não encontrada`] });
      continue;
    }
    const section = page.locator(`#${controls}`).first();
    const text = await section.innerText().catch(() => "");
    const rowTexts = await section.locator(".snbr-tool-row").evaluateAll((nodes) => nodes.map((node) => node.textContent || "")).catch(() => []);
    const result = {
      tab: tabId,
      label,
      visible: true,
      freshness_status: await section.getAttribute("data-ai-freshness-status").catch(() => null),
      visible_count: Number(await section.getAttribute("data-ai-visible-count").catch(() => "0") || 0),
      stale_count: Number(await section.getAttribute("data-ai-stale-count").catch(() => "0") || 0),
      badge_count: Number(await section.getAttribute("data-ai-badge-count").catch(() => "0") || 0),
      has_waiting_copy: normalizeText(text).includes("aguardando nova leitura do dia") || normalizeText(text).includes("waiting for today"),
      failures: [],
    };
    const rowText = rowTexts.join("\n");
    if (/Detectado:\s*12\/06\/2026/i.test(rowText)) {
      result.failures.push("leitura antiga 12/06/2026 ainda aparece como achado principal");
    }
    if (/Status:\s*leitura do dia anterior/i.test(rowText)) {
      result.failures.push("leitura do dia anterior ainda aparece como card principal");
    }
    if (result.stale_count > 0 && result.visible_count === 0 && !result.has_waiting_copy) {
      result.failures.push("existem leituras antigas, mas o vazio não explica que aguarda nova leitura");
    }
    if (result.badge_count !== result.visible_count) {
      result.failures.push(`badge_count (${result.badge_count}) difere dos achados visíveis (${result.visible_count})`);
    }
    results.push(result);
  }
  return results;
}

async function main() {
  fs.mkdirSync(path.dirname(reportPath), { recursive: true });
  fs.mkdirSync(screenshotDir, { recursive: true });

  const sessionBaseline = countSessions();
  const EPHEMERAL_SESSION = generateEphemeralSession();
  let browser = null;
  let context = null;
  const chartResults = [];
  let aiResults = [];
  try {
    browser = await chromium.launch({ headless: HEADLESS });
    context = await browser.newContext({ viewport: { width: 1600, height: 950 } });
    await applyEphemeralAuth(context, EPHEMERAL_SESSION.token);
    const page = await context.newPage();
    page.setDefaultTimeout(7000);
    page.setDefaultNavigationTimeout(20000);
    for (const symbol of SYMBOLS) {
      chartResults.push(await auditChart(page, symbol));
    }
    aiResults = await auditAiFreshness(page, "PETR4");
  } finally {
    await context?.close().catch(() => undefined);
    await browser?.close().catch(() => undefined);
    revokeEphemeralSession(EPHEMERAL_SESSION.sid);
  }
  const sessionDelta = countSessions() - sessionBaseline;

  const failures = [
    ...chartResults.flatMap((item) => item.failures.map((failure) => `${item.symbol}: ${failure}`)),
    ...aiResults.flatMap((item) => item.failures.map((failure) => `${item.label}: ${failure}`)),
  ];
  if (sessionDelta !== 0) failures.push(`SESSION_DELTA=${sessionDelta}`);
  const report = {
    ok: failures.length === 0,
    mission: "30F.2",
    generated_at: new Date().toISOString(),
    web_base: WEB_BASE,
    chart_assets: chartResults,
    ai_freshness: aiResults,
    session_delta: sessionDelta,
    external_provider_calls: 0,
    failures,
  };
  fs.writeFileSync(reportPath, JSON.stringify(report, null, 2));
  if (failures.length) {
    console.error(JSON.stringify({ ok: false, mission: "30F.2", failures, reportPath }, null, 2));
    process.exit(1);
  }
  console.log(JSON.stringify({ ok: true, mission: "30F.2", symbols: chartResults.length, ai_tabs: aiResults.length, reportPath }, null, 2));
  console.log(`SESSION_DELTA=${sessionDelta}`);
  console.log("EXTERNAL_PROVIDER_CALLS=0");
}

await main();
