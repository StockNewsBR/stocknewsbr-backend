import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(scriptDir, "..", "..", "..");
const reportPath = process.env.MISSION30D_REPORT_PATH
  ? path.resolve(repoRoot, process.env.MISSION30D_REPORT_PATH)
  : path.join(repoRoot, "runtime", "mission_30d_playwright_report.json");

const API_BASE = process.env.MISSION30D_API_BASE || "http://127.0.0.1:8000";
const WEB_BASE = process.env.MISSION30D_WEB_BASE || "http://localhost:3000";
const HEADLESS = process.env.MISSION30D_HEADLESS !== "false";
const REQUESTED_SECTIONS = new Set(
  (process.env.MISSION30D_SECTIONS || "news,operational,freshness,data")
    .split(",")
    .map((item) => item.trim().toLowerCase())
    .filter(Boolean),
);

const NEWS_SYMBOLS = ["AAPL", "NVDA", "TSLA", "MSFT", "VALE3", "PETR4", "ITUB4", "BBAS3"];
const OPERATIONAL_SYMBOLS = ["AAPL", "NVDA", "TSLA", "MSFT", "VALE3", "PETR4"];
const DATA_AUDIT_SYMBOLS = ["ASAI3", "AZUL4", "PETR3", "RRRP3", "RENT3", "B3SA3", "TAEE11"];
const VISIBLE_AI_TABS = ["Fluxo IA", "Liquidez IA", "Tendência IA", "Momento IA", "Smart Money"];
const HIDDEN_AI_TABS = ["Risco IA", "Notícias IA", "Macro IA", "Regime IA"];
const TOP_TAB_IDS = new Map([
  ["Gráfico IA / Rede Social", "grafico"],
  ["Notícias", "news"],
  ["Fluxo IA", "flow"],
  ["Liquidez IA", "liquidity"],
  ["Tendência IA", "trend"],
  ["Momento IA", "momentum"],
  ["Smart Money", "smart-money"],
]);

function normalizeText(value) {
  return String(value || "")
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
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

function numberOrNull(value) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function quoteHasPrice(payload) {
  if (!payload || typeof payload !== "object") return false;
  const price = numberOrNull(payload.price ?? payload.last ?? payload.close);
  const source = normalizeText(payload.source);
  const status = normalizeText(payload.quote_status ?? payload.status);
  return Boolean(price && price > 0 && source !== "empty" && status !== "empty");
}

async function fetchJson(route) {
  const url = `${API_BASE}${route}`;
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 15000);
  try {
    const response = await fetch(url, { headers: { accept: "application/json" }, signal: controller.signal });
    const text = await response.text();
    let body = null;
    try {
      body = text ? JSON.parse(text) : null;
    } catch {
      body = { parse_error: text.slice(0, 300) };
    }
    return { ok: response.ok, status: response.status, url, body };
  } catch (error) {
    return { ok: false, status: 0, url, body: { error: error instanceof Error ? error.message : String(error) } };
  } finally {
    clearTimeout(timeout);
  }
}

async function openPanel(page, symbol) {
  await page.goto(`${WEB_BASE}/panel/${encodeURIComponent(symbol)}`, { waitUntil: "domcontentloaded" });
  await page.locator("main").waitFor({ state: "visible", timeout: 10000 });
  await page.waitForFunction((expectedSymbol) => {
    const text = document.body?.innerText || "";
    return text.includes(`Symbol / ${expectedSymbol}`) || text.includes(`Notícias de ${expectedSymbol}`) || window.location.pathname.toUpperCase().endsWith(`/PANEL/${expectedSymbol}`);
  }, symbol, { timeout: 15000 }).catch(() => undefined);
  await page.waitForTimeout(900);
}

async function clickTopTab(page, label) {
  const tabId = TOP_TAB_IDS.get(label);
  const tab = tabId
    ? page.locator(`.snbr-top-tabs button[role='tab'][aria-controls='panel-${tabId}']`).first()
    : page.locator(".snbr-top-tabs button[role='tab']").filter({ hasText: new RegExp(`^\\s*${label}\\s*$`, "i") }).first();
  if ((await tab.count()) === 0) return false;
  await tab.scrollIntoViewIfNeeded().catch(() => undefined);
  await tab.click({ force: true });
  await page.waitForTimeout(350);
  return true;
}

async function enableProMode(page) {
  const button = page.locator(".snbr-mode-toggle").first();
  if ((await button.count()) === 0) return false;
  const pressed = await button.getAttribute("aria-pressed");
  if (pressed !== "true") {
    await button.click();
    await page.waitForTimeout(350);
  }
  return true;
}

async function collectNewsDom(page, symbol) {
  await openPanel(page, symbol);
  const newsTabVisible = await clickTopTab(page, "Notícias");
  const panel = page.locator("#panel-news:visible").first();
  await panel.waitFor({ state: "visible", timeout: 10000 });
  const stateCount = Number(await panel.getAttribute("data-news-state-count")) || 0;
  const domVisibleCount = await panel.locator("article.snbr-news-row").count();
  const panelText = await panel.innerText().catch(() => "");
  const fallbackVisible = normalizeText(panelText).includes("sem noticias relevantes");
  const tabTexts = await page.locator(".snbr-top-tabs button[role='tab']").evaluateAll((items) =>
    items.map((item) => item.textContent?.replace(/\s+/g, " ").trim() || ""),
  );

  return {
    frontend_state_count: stateCount,
    dom_visible_count: domVisibleCount,
    news_tab_visible: newsTabVisible,
    fallback_visible: fallbackVisible,
    tab_texts: tabTexts,
  };
}

async function auditNews(page, symbol) {
  const refresh = Date.now();
  const route = await fetchJson(`/public/market/news/${encodeURIComponent(symbol)}?limit=6&refresh=${refresh}`);
  const bundle = await fetchJson(`/public/market/bundle/${encodeURIComponent(symbol)}?interval=1D&limit=6&refresh=${refresh}`);
  const routeCount = newsCount(route.body);
  const bundleCount = newsCount(bundle.body?.news);
  let dom;
  try {
    dom = await collectNewsDom(page, symbol);
  } catch {
    await page.reload({ waitUntil: "domcontentloaded" }).catch(() => undefined);
    await page.waitForTimeout(1200);
    dom = await collectNewsDom(page, symbol);
  }

  return {
    symbol,
    route_count: routeCount,
    bundle_count: bundleCount,
    ...dom,
    route_status: route.status,
    bundle_status: bundle.status,
  };
}

function extractCardValue(cards, label) {
  const normalizedLabel = normalizeText(label);
  const card = cards.find((item) => normalizeText(item).startsWith(normalizedLabel));
  if (!card) return "";
  return card
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean)
    .slice(1)
    .join(" ");
}

function containsAny(text, phrases) {
  const normalized = normalizeText(text);
  return phrases.some((phrase) => normalized.includes(normalizeText(phrase)));
}

function containsStandAside(text) {
  return containsAny(text, [
    "ficar de fora",
    "nenhum lado operacional",
    "nenhum lado tem",
    "sem nova operação",
    "preservar capital primeiro",
    "reduzir exposição",
    "aguardar decisão dominante",
    "aguardar a decisão dominante",
    "evitar entradas agressivas",
    "stand aside",
    "no operational side",
    "no new trade",
    "reduce exposure",
    "waiting is the dominant decision",
    "avoid aggressive entries",
  ]);
}

function operationalContradictions(snapshot) {
  const combinedDirection = normalizeText([
    snapshot.decisao_agora,
    snapshot.trade_sugerido,
    snapshot.bias,
    snapshot.direcao_provavel,
  ].join(" "));
  const body = [
    snapshot.conclusao,
    snapshot.interpretacao,
    snapshot.foco_agora,
  ].join("\n");
  const issues = [];

  const isProtection = containsAny(combinedDirection, ["encerrar", "proteger", "saída", "saida", "reduzir"]);
  const isBearish = containsAny(combinedDirection, ["baixa", "venda", "short", "vendedor"]);
  const tradeIsBuy = containsAny(snapshot.trade_sugerido, ["compra", "buy"]);
  const tradeIsSell = containsAny(snapshot.trade_sugerido, ["venda", "short", "sell"]);
  const isBullish = containsAny(combinedDirection, ["alta", "compra", "comprador"]);
  const isWait = containsAny(combinedDirection, ["aguardar", "monitorando", "neutro"]);

  if ((isProtection || isBearish) && containsAny(body, [
    "compra tem prioridade",
    "plano comprador controlado",
    "compra tem argumento mais forte",
    "comprar imediatamente",
    "fluxo comprador dominante",
    "força compradora dominante",
  ])) {
    issues.push("texto comprador em decisão de baixa/proteção");
  }

  if (isBullish && containsAny(body, [
    "venda tem prioridade",
    "plano vendedor controlado",
    "vender imediatamente",
    "fluxo vendedor dominante",
    "força vendedora dominante",
  ])) {
    issues.push("texto vendedor em decisão compradora");
  }

  if ((tradeIsBuy || tradeIsSell) && containsStandAside(body)) {
    issues.push("texto de ficar fora em decisão direcional");
  }

  if (isWait && containsAny(body, [
    "comprar imediatamente",
    "vender imediatamente",
    "executar imediatamente",
  ])) {
    issues.push("texto de execução imediata em decisão de aguardar");
  }

  return issues;
}

async function collectOperationalOnce(page, symbol) {
  await openPanel(page, symbol);
  await enableProMode(page);
  await clickTopTab(page, "Gráfico IA / Rede Social");
  await page.locator(".snbr-operational-decision:visible").first().waitFor({ state: "visible", timeout: 10000 }).catch(() => undefined);

  const operational = await page.locator(".snbr-operational-decision:visible").first().innerText().catch(() => "");
  const cards = await page.locator(".snbr-decision-card:visible").evaluateAll((items) => items.map((item) => item.innerText || item.textContent || ""));
  const conclusion = await page.locator(".snbr-decision-conclusion:visible").first().innerText().catch(() => "");
  const conclusionLines = conclusion.split(/\r?\n/).map((line) => line.trim()).filter(Boolean);
  const sections = {};
  let currentSection = "";
  for (const line of conclusionLines) {
    if (["Cenário Atual", "Direção da Estratégia", "Entre Venda e Compra", "Entre Proteção e Reentrada", "Interpretação", "Foco Agora"].includes(line)) {
      currentSection = line;
      sections[currentSection] = "";
    } else if (currentSection) {
      sections[currentSection] = `${sections[currentSection] ? `${sections[currentSection]} ` : ""}${line}`;
    }
  }

  const snapshot = {
    symbol,
    decisao_agora: operational.split(/\r?\n/).map((line) => line.trim()).filter(Boolean)[1] || "",
    trade_sugerido: extractCardValue(cards, "Trade Sugerido"),
    bias: (operational.match(/VI[ÉE]S\s+([^\n]+)/i)?.[1] || extractCardValue(cards, "Regime") || "").trim(),
    direcao_provavel: extractCardValue(cards, "Direção Provável"),
    conclusao: sections["Cenário Atual"] || "",
    interpretacao: sections["Interpretação"] || "",
    foco_agora: sections["Foco Agora"] || "",
    raw_operational: operational,
    raw_conclusion: conclusion,
  };
  return {
    ...snapshot,
    contradictions: operationalContradictions(snapshot),
  };
}

async function auditOperational(page, symbol) {
  let snapshot = await collectOperationalOnce(page, symbol);
  if (snapshot.raw_operational && snapshot.raw_conclusion) return snapshot;

  await page.reload({ waitUntil: "domcontentloaded" }).catch(() => undefined);
  await page.waitForTimeout(1200);
  snapshot = await collectOperationalOnce(page, symbol);
  return snapshot;
}

async function auditFreshness(page) {
  const samples = [];
  const failures = [];
  for (const symbol of ["PETR4", "AAPL", "NVDA", "VALE3"]) {
    await openPanel(page, symbol);
    await enableProMode(page);
    const tabTexts = await page.locator(".snbr-top-tabs button[role='tab']").evaluateAll((items) =>
      items.map((item) => item.textContent?.replace(/\s+/g, " ").trim() || ""),
    );
    const hiddenPresent = HIDDEN_AI_TABS.filter((label) => tabTexts.some((text) => text.includes(label)));
    if (hiddenPresent.length) {
      failures.push(`${symbol}: tabs internas visíveis: ${hiddenPresent.join(", ")}`);
    }

    for (const label of VISIBLE_AI_TABS) {
      if (!(await clickTopTab(page, label))) continue;
      const rows = await page.locator(".snbr-temporal-chip-row").evaluateAll((items) =>
        items.map((item) => item.textContent?.replace(/\s+/g, " ").trim() || ""),
      );
      for (const text of rows) {
        const hasDetected = /Detectado:\s*\d{2}\/\d{2}\/\d{4}/.test(text);
        const hasViewed = /Visualizado:\s*\d{2}\/\d{2}\/\d{4}/.test(text);
        const hasStatus = /Status:\s*/.test(text);
        samples.push({ symbol, tab: label, text, has_detected_date: hasDetected, has_viewed_date: hasViewed, has_status: hasStatus });
        if (!hasDetected || !hasViewed || !hasStatus) {
          failures.push(`${symbol}/${label}: freshness incompleto`);
        }
      }
    }
  }
  return { sample_count: samples.length, samples: samples.slice(0, 12), failures };
}

function classifyDataAsset({ quote, bundle, chart, frontend }) {
  const quoteOk = quoteHasPrice(quote.body);
  const bundleQuoteOk = quoteHasPrice(bundle.body?.quote);
  const chartRows = Array.isArray(chart.body?.ohlc) ? chart.body.ohlc.length : 0;

  if (frontend.has_failed_fetch || frontend.has_raw_na) return "Frontend inconsistente";
  if (!quoteOk && !bundleQuoteOk && frontend.has_directional_trade) return "Frontend inconsistente";
  if (quoteOk && !bundleQuoteOk) return "Bundle inconsistente";
  if (quoteOk && bundleQuoteOk && frontend.has_clear_price) return "Resolvido";
  if (!quoteOk && chartRows === 0) return "Snapshot ausente";
  if (!quoteOk && chartRows > 0) return "Snapshot ausente";
  return "Provider sem dados";
}

async function auditDataAsset(page, symbol) {
  const quote = await fetchJson(`/public/market/quote/${encodeURIComponent(symbol)}`);
  const bundle = await fetchJson(`/public/market/bundle/${encodeURIComponent(symbol)}?interval=1D&limit=6`);
  const chart = await fetchJson(`/public/market/chart/${encodeURIComponent(symbol)}?interval=1D`);
  await openPanel(page, symbol);
  await enableProMode(page);
  await clickTopTab(page, "Gráfico IA / Rede Social");
  const decisionPanel = page.locator(`.snbr-decision-panel[data-selected-symbol="${symbol}"]`).first();
  await decisionPanel.waitFor({ state: "visible", timeout: 15000 });
  const mainText = await page.locator("main").innerText().catch(() => "");
  const panelText = await decisionPanel.innerText().catch(() => "");
  const cards = await decisionPanel.locator(".snbr-decision-card:visible").evaluateAll((items) => items.map((item) => item.innerText || item.textContent || "")).catch(() => []);
  const tradeText = extractCardValue(cards, "Trade Sugerido");
  const quotePayload = quote.body || {};
  const bundleQuote = bundle.body?.quote || {};
  const chartRows = Array.isArray(chart.body?.ohlc) ? chart.body.ohlc.length : 0;
  const hasClearPrice = quoteHasPrice(quotePayload) || quoteHasPrice(bundleQuote);
  const frontend = {
    has_failed_fetch: normalizeText(mainText).includes("failed to fetch"),
    has_raw_na: mainText.includes("R$ n/a") || mainText.includes("US$ n/a"),
    has_clear_price: hasClearPrice && !mainText.includes("R$ n/a") && !mainText.includes("US$ n/a"),
    has_no_trade_copy: containsAny(panelText || mainText, ["AGUARDAR DADOS REAIS", "sem cotação confirmada", "sem preço confirmado"]),
    trade_sugerido: tradeText || null,
    has_directional_trade: containsAny(tradeText, ["compra", "venda", "short", "buy", "sell"]),
  };

  return {
    symbol,
    provider: quotePayload.provider || quotePayload.source || bundleQuote.provider || bundleQuote.source || chart.body?.summary?.provider_status || "cache/snapshot",
    cache: quotePayload.source || bundleQuote.source || bundle.body?.source || "sem payload",
    snapshot: quoteHasPrice(quotePayload) || quoteHasPrice(bundleQuote) ? "quote presente" : "ausente",
    quote: {
      status: quote.status,
      price: quotePayload.price ?? null,
      source: quotePayload.source ?? null,
      quote_status: quotePayload.quote_status ?? quotePayload.status ?? null,
    },
    bundle: {
      status: bundle.status,
      price: bundleQuote.price ?? null,
      source: bundleQuote.source ?? null,
      quote_status: bundleQuote.quote_status ?? bundleQuote.status ?? null,
    },
    chart: {
      status: chart.status,
      rows: chartRows,
      source: chart.body?.summary?.source ?? chart.body?.source ?? null,
      provider_status: chart.body?.provider_status ?? chart.body?.summary?.provider_status ?? null,
    },
    frontend,
    status_final: classifyDataAsset({ quote, bundle, chart, frontend }),
  };
}

function assertNews(report, failures) {
  for (const item of report.news) {
    if ((item.route_count > 0 || item.bundle_count > 0) && (item.dom_visible_count <= 0 || item.fallback_visible)) {
      failures.push(`${item.symbol}: noticia existe na API/bundle, mas DOM nao renderizou card real`);
    }
    if (!item.news_tab_visible) {
      failures.push(`${item.symbol}: aba Noticias nao esta visivel`);
    }
  }
}

function assertOperational(report, failures) {
  for (const item of report.operational) {
    if (!item.decisao_agora || !item.raw_operational || !item.raw_conclusion) {
      failures.push(`${item.symbol}: painel operacional/conclusao nao renderizou no DOM`);
    }
    for (const issue of item.contradictions) {
      failures.push(`${item.symbol}: ${issue}`);
    }
  }
}

function assertDataAssets(report, failures) {
  for (const item of report.data_assets) {
    if (["Bundle inconsistente", "Frontend inconsistente", "Registry inconsistente"].includes(item.status_final)) {
      failures.push(`${item.symbol}: ${item.status_final}`);
    }
  }
}

function writeReport(report) {
  fs.mkdirSync(path.dirname(reportPath), { recursive: true });
  fs.writeFileSync(reportPath, JSON.stringify(report, null, 2));
}

async function main() {
  const browser = await chromium.launch({ headless: HEADLESS });
  const context = await browser.newContext({ locale: "pt-BR", viewport: { width: 1600, height: 1000 } });
  const page = await context.newPage();
  page.setDefaultTimeout(10000);
  const report = {
    generated_at: new Date().toISOString(),
    api_base: API_BASE,
    web_base: WEB_BASE,
    news: [],
    operational: [],
    freshness: null,
    data_assets: [],
    failures: [],
  };

  try {
    if (REQUESTED_SECTIONS.has("news")) {
      for (const symbol of NEWS_SYMBOLS) {
        console.error(`[30D] news ${symbol}`);
        report.news.push(await auditNews(page, symbol));
        writeReport(report);
      }
    }
    if (REQUESTED_SECTIONS.has("operational")) {
      for (const symbol of OPERATIONAL_SYMBOLS) {
        console.error(`[30D] operational ${symbol}`);
        report.operational.push(await auditOperational(page, symbol));
        writeReport(report);
      }
    }
    if (REQUESTED_SECTIONS.has("freshness")) {
      console.error("[30D] freshness");
      report.freshness = await auditFreshness(page);
      writeReport(report);
    }
    if (REQUESTED_SECTIONS.has("data")) {
      for (const symbol of DATA_AUDIT_SYMBOLS) {
        console.error(`[30D] data ${symbol}`);
        report.data_assets.push(await auditDataAsset(page, symbol));
        writeReport(report);
      }
    }
  } finally {
    await browser.close();
  }

  if (REQUESTED_SECTIONS.has("news")) assertNews(report, report.failures);
  if (REQUESTED_SECTIONS.has("operational")) assertOperational(report, report.failures);
  if (REQUESTED_SECTIONS.has("data")) assertDataAssets(report, report.failures);
  if (REQUESTED_SECTIONS.has("freshness") && report.freshness?.failures?.length) {
    report.failures.push(...report.freshness.failures);
  }
  if (REQUESTED_SECTIONS.has("freshness") && (!report.freshness || report.freshness.sample_count === 0)) {
    report.freshness = {
      ...(report.freshness || {}),
      sample_count: 0,
      samples: [],
      failures: report.freshness?.failures || [],
      status: "sem achados IA visiveis no payload atual",
    };
  }

  writeReport(report);
  console.log(JSON.stringify(report, null, 2));
  if (report.failures.length) {
    process.exitCode = 1;
  }
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
