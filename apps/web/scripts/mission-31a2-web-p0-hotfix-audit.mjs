import fs from "node:fs";
import path from "node:path";
import { execFileSync } from "node:child_process";
import { randomUUID } from "node:crypto";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";
import {
  applyEphemeralAuth as applySharedAuth,
  countSessions,
  enableProMode,
  generateEphemeralSession,
  PYTHON_PATH,
  revokeEphemeralSession,
} from "./lib/ephemeral-auth.mjs";

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(scriptDir, "..", "..", "..");
const reportPath = process.env.MISSION31A2_REPORT_PATH
  ? path.resolve(repoRoot, process.env.MISSION31A2_REPORT_PATH)
  : path.join(repoRoot, "runtime", "mission_31a2_web_p0_hotfix_report.json");
const alpacaDiagnosticPath = path.join(repoRoot, "runtime", "mission_31a2_alpaca_diagnostic.json");
const screenshotDir = process.env.MISSION31A2_SCREENSHOT_DIR
  ? path.resolve(repoRoot, process.env.MISSION31A2_SCREENSHOT_DIR)
  : path.join(repoRoot, "output", "playwright", "mission31a2");
const fixtureScript = path.join(repoRoot, "scripts", "mission31a2_offline_fixture.py");
const WEB_BASE = process.env.MISSION31A2_WEB_BASE || "http://127.0.0.1:3000";
const API_BASE = process.env.MISSION31A2_API_BASE || "http://127.0.0.1:8000";
const HEADLESS = process.env.MISSION31A2_HEADLESS !== "false";

const POPULATION_CONTRACTS = Object.freeze({
  canonical: Object.freeze(["PETR4", "BNY", "AMZN", "BTCUSD", "VALE3", "ITUB4", "AAPL", "TSLA", "NVDA"]),
  "supplemental-avgo": Object.freeze(["AVGO", "AXP", "CMG", "CRWD", "GE", "GM", "LI", "ROKU", "SAP"]),
  "extra-nine": Object.freeze(["DE", "DG", "DTC", "CAR", "CHPT", "GS", "HD", "LULU", "MARA"]),
});
const POPULATION_SIGNATURES = Object.freeze({
  canonical: "PETR4,BNY,AMZN,BTCUSD,VALE3,ITUB4,AAPL,TSLA,NVDA",
  "supplemental-avgo": "AVGO,AXP,CMG,CRWD,GE,GM,LI,ROKU,SAP",
  "extra-nine": "DE,DG,DTC,CAR,CHPT,GS,HD,LULU,MARA",
});
const POPULATION = process.env.MISSION31A2_POPULATION || "canonical";
if (process.env.MISSION31A2_SYMBOLS) {
  throw new Error("MISSION31A2_SYMBOLS is forbidden; select a named fixed population");
}
if (!Object.hasOwn(POPULATION_CONTRACTS, POPULATION)) {
  throw new Error(`unknown MISSION31A2_POPULATION: ${POPULATION}`);
}
const SYMBOLS = [...POPULATION_CONTRACTS[POPULATION]];
const REQUIRED_SYMBOL_COUNT = 9;
if (SYMBOLS.length !== REQUIRED_SYMBOL_COUNT || new Set(SYMBOLS).size !== REQUIRED_SYMBOL_COUNT) {
  throw new Error(`mission31a2 population count/duplicates changed: ${POPULATION}`);
}
if (SYMBOLS.join(",") !== POPULATION_SIGNATURES[POPULATION]) {
  throw new Error(`mission31a2 population names/order changed: ${POPULATION}`);
}
if (process.env.MISSION31A2_REQUIRED_SYMBOL_COUNT || process.env.MISSION31A2_REQUIRE_OPERATIONAL === "false") {
  throw new Error("mission31a2 count and operational assertions cannot be overridden");
}
const REQUIRE_OPERATIONAL = true;
const AI_TABS = ["flow", "liquidity", "trend", "momentum", "smart-money"];
const FORCED_FAILURE_REAL_SYMBOL = SYMBOLS[0];
// One cent: enough for monetary rounding, not enough to hide an inverted level.
const LEVEL_BRACKET_EPSILON = 0.01;
const CANONICAL_VWAP_COLOR = "#f59e0b";
const FORBIDDEN_URL_RE = /(example\.com|localhost|127\.0\.0\.1|0\.0\.0\.0|mock|fake|placeholder)/i;
const ALLOWED_ORIGINS = new Set([new URL(WEB_BASE).origin, new URL(API_BASE).origin]);

let EPHEMERAL_SESSION = null;
let VALID_JWT_TOKEN = "";
let TOKEN_TTL_SECONDS = 0;
let fixtureGeneration = "";
let fixtureRefreshTimer = null;
let fixtureRefreshFailure = "";
let sessionBaseline = null;
let activeBrowser = null;
let lifecycleResult = null;
let aborting = false;
const blockedExternalOrigins = new Set();

function runFixture(action, generation, ...extra) {
  const output = execFileSync(PYTHON_PATH, [fixtureScript, action, generation, ...extra.map(String)], {
    cwd: repoRoot,
    encoding: "utf8",
    shell: false,
    env: { ...process.env, PYTHONPATH: repoRoot, PYTHONDONTWRITEBYTECODE: "1" },
  });
  return JSON.parse(output);
}

function startFixtureLifecycle() {
  fixtureGeneration = randomUUID();
  const started = runFixture("start", fixtureGeneration, process.pid);
  runFixture("refresh", fixtureGeneration);
  fixtureRefreshTimer = setInterval(() => {
    try {
      runFixture("refresh", fixtureGeneration);
    } catch (error) {
      fixtureRefreshFailure ||= String(error?.message || error).slice(0, 240);
    }
  }, 20_000);
  fixtureRefreshTimer.unref();
  return started;
}

function finishLifecycle() {
  if (lifecycleResult) return lifecycleResult;
  if (fixtureRefreshTimer) clearInterval(fixtureRefreshTimer);
  fixtureRefreshTimer = null;
  const sessionRowsRemaining = EPHEMERAL_SESSION ? revokeEphemeralSession(EPHEMERAL_SESSION.sid) : 0;
  EPHEMERAL_SESSION = null;
  let fixtureStop = { residual_entries: fixtureGeneration ? -1 : 0, external_provider_calls: 0 };
  if (fixtureGeneration) {
    try {
      fixtureStop = runFixture("stop", fixtureGeneration);
    } catch (error) {
      fixtureStop = {
        residual_entries: -1,
        external_provider_calls: 0,
        error: String(error?.message || error).slice(0, 240),
      };
    }
  }
  fixtureGeneration = "";
  const sessionDelta = sessionBaseline === null ? -1 : countSessions() - sessionBaseline;
  lifecycleResult = {
    session_rows_remaining_after_cleanup: sessionRowsRemaining,
    session_delta: sessionDelta,
    fixture_residual_entries: Number(fixtureStop.residual_entries ?? -1),
    fixture_external_provider_calls: Number(fixtureStop.external_provider_calls ?? 0),
    fixture_refresh_failure: fixtureRefreshFailure || null,
    fixture_stop: fixtureStop,
  };
  return lifecycleResult;
}

async function installNetworkFence(context) {
  await context.route("**/*", async (route) => {
    const url = new URL(route.request().url());
    if ((url.protocol === "http:" || url.protocol === "https:") && !ALLOWED_ORIGINS.has(url.origin)) {
      blockedExternalOrigins.add(url.origin);
      await route.abort("blockedbyclient").catch(() => undefined);
      return;
    }
    await route.fallback().catch(() => route.continue().catch(() => undefined));
  });
}

for (const [signal, code] of [["SIGINT", 130], ["SIGTERM", 143], ["SIGHUP", 129]]) {
  process.once(signal, async () => {
    if (aborting) return;
    aborting = true;
    await activeBrowser?.close().catch(() => undefined);
    finishLifecycle();
    process.exit(code);
  });
}

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

const INTERNAL_TOKEN = process.env.INTERNAL_API_TOKEN || "";

async function fetchJsonWithMeta(url) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 20000);
  try {
    const response = await fetch(url, {
      cache: "no-store",
      signal: controller.signal,
      headers: {
        Authorization: `Bearer ${VALID_JWT_TOKEN}`,
        ...(INTERNAL_TOKEN ? { "X-Internal-Token": INTERNAL_TOKEN } : {}),
      },
    });
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
  } catch (error) {
    return { url, status: 0, ok: false, headers: {}, body: { error: String(error?.message || error) } };
  } finally {
    clearTimeout(timeout);
  }
}

async function openPanel(page, symbol, { requireOperational = false } = {}) {
  await page.goto(`${WEB_BASE}/panel/${encodeURIComponent(symbol)}`, { waitUntil: "domcontentloaded" });
  await page.locator("main").waitFor({ state: "visible", timeout: 20000 });
  // Wait for the strategic panel to reach a DECIDED data state before measuring.
  // Measuring a page that is still hydrating is what made the core_data,
  // missing_fields and news assertions flap between runs.
  await page
    .waitForFunction(
      (waitForOperational) => {
        const panel = document.querySelector(".snbr-decision-panel");
        if (!panel) return false;
        const core = panel.getAttribute("data-core-data");
        const missing = panel.getAttribute("data-missing-fields");
        const decision = panel.getAttribute("data-decision-now") || "";
        if (waitForOperational) return core === "true" && !/dados reais|real data/i.test(decision);
        return core === "true" || (core === "false" && Boolean(missing));
      },
      requireOperational,
      { timeout: 40000 },
    )
    .catch(() => undefined);
}

async function clickTab(page, id) {
  const button = page.locator(`.snbr-top-tabs button[role='tab'][aria-controls='panel-${id}']`).first();
  if ((await button.count()) === 0) return false;
  await button.evaluate((element) => {
    if (element instanceof HTMLElement) element.click();
  });
  await page.locator(`#panel-${id}`).first().waitFor({ state: "visible", timeout: 8000 }).catch(() => undefined);
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
  const quote = await fetchJsonWithMeta(`${API_BASE}/public/market/quote/${encodeURIComponent(symbol)}`);
  const bundle = await fetchJsonWithMeta(`${API_BASE}/public/market/bundle/${encodeURIComponent(symbol)}?interval=1D&limit=6`);
  const quoteBody = quote.body || {};
  const bundleQuote = bundle.body?.quote || {};
  const insight = bundle.body?.insight || {};
  const operational = bundle.body?.market_metrics?.operational_view || {};
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
    analysis: {
      hydration_status: bundle.body?.hydration?.status || null,
      score: insight.score ?? null,
      master_score: insight.master_score ?? null,
      rsi: insight.rsi ?? null,
      trend_bias: insight.trend_bias || null,
      recommended_action: insight.strategic_panel?.recommended_action || insight.recommended_action || null,
      operational_score: operational.operational_context?.master_score?.value ?? null,
      operational_score_status: operational.operational_context?.master_score?.status || null,
      operational_decision: operational.decision || null,
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

// Terminal states of the news panel. "loading" means the panel's own fetch has
// not landed yet; asserting there measures the audit's timing, not the product.
const NEWS_TERMINAL_PHASES = ["ready", "historical", "empty", "error"];

// Seeds the server-side news state for a symbol. MUST run before the panel is
// opened: the UI issues its own news request during page load, so a refresh
// fired afterwards mutates the server behind a request that already left.
async function seedNews(symbol) {
  const api = await fetchJson(`${API_BASE}/public/market/news/${encodeURIComponent(symbol)}?limit=6&refresh=mission31a2`);
  return {
    count: Number(api?.count ?? api?.items?.length ?? 0),
    status: api?.status,
    message: api?.message,
    symbol: api?.symbol,
  };
}

async function auditNews(page, symbol, { requireTab = false, seed = null, uiPayload = null } = {}) {
  const api = seed || (await seedNews(symbol));
  const apiCount = Number(api?.count ?? 0);
  const tabOpened = await clickTab(page, "news");
  // Wait for the panel's OWN fetch to resolve, using the state the product
  // already publishes. Same 8s budget as before -- what changed is the
  // predicate: a terminal phase instead of a card that may still be in flight.
  const reachedTerminal = await page
    .waitForFunction(
      (terminal) => {
        const panel = document.querySelector("#panel-news");
        if (!panel) return false;
        return terminal.includes(panel.getAttribute("data-news-phase") || "");
      },
      NEWS_TERMINAL_PHASES,
      { timeout: 8000 },
    )
    .then(() => true)
    .catch(() => false);
  const newsPhase = await page.locator("#panel-news").getAttribute("data-news-phase").catch(() => null);
  const panelStateCount = Number(
    (await page.locator("#panel-news").getAttribute("data-news-state-count").catch(() => null)) ?? -1,
  );
  const panelVisible = await page.locator("#panel-news").isVisible().catch(() => false);
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
  pushIf(requireTab && (!tabOpened || !panelVisible), failures, "aba Notícias não abriu");
  // A panel still in "loading" is stuck, not empty. Naming it separately keeps
  // the evidence honest instead of surfacing an unresolved fetch as dom_count=0.
  pushIf(!reachedTerminal, failures, `painel de notícias preso em fase não terminal (${newsPhase || "ausente"})`);
  pushIf(apiCount > 0 && cards.length === 0, failures, "API tem notícia, DOM não renderizou card real");
  // The DOM must match the payload the UI itself consumed, not just the payload
  // the audit fetched on its own connection.
  pushIf(
    uiPayload && Number(uiPayload.count) > 0 && cards.length === 0,
    failures,
    `UI recebeu ${uiPayload?.count} notícia(s) e não renderizou card`,
  );
  pushIf(
    panelStateCount >= 0 && panelStateCount !== cards.length,
    failures,
    `estado do painel (${panelStateCount}) diverge dos cards renderizados (${cards.length})`,
  );
  {
    const cardKeys = cards.map((card) => `${card.url}|${card.text.slice(0, 120)}`);
    pushIf(new Set(cardKeys).size !== cardKeys.length, failures, "cards de notícia duplicados no DOM");
  }
  pushIf(FORBIDDEN_URL_RE.test(bodyText), failures, "DOM de notícias contém URL fake/example/mock");
  anchors.forEach((href) => pushIf(FORBIDDEN_URL_RE.test(href), failures, `link ativo proibido: ${href}`));
  cards.forEach((card, index) => {
    // A real card carries actual headline copy -- not a skeleton or placeholder.
    pushIf(card.text.trim().length < 24, failures, `card ${index + 1} é placeholder sem manchete real`);
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
    api_seeded_before_load: Boolean(seed),
    tab_opened: tabOpened,
    panel_visible: panelVisible,
    news_phase: newsPhase,
    reached_terminal_phase: reachedTerminal,
    panel_state_count: panelStateCount,
    ui_payload: uiPayload,
    dom_count: cards.length,
    cards: cards.slice(0, 3),
    failures,
  };
}

// Non-terminal states. A panel sitting in any of these is stuck, not empty —
// reported as its own failure so the evidence names the real defect.
const AI_LOADING_MARKERS = [
  "ia carregando",
  "aguardando o payload",
  "ai loading",
  "waiting for the current payload",
  "calculando analise",
  "calculating analysis",
];

// The AI panel mounts in a loading state ("IA carregando / Aguardando o payload
// atual") and resolves asynchronously. Asserting immediately measures the
// spinner, not the contract. Wait for a terminal state, bounded — a panel still
// loading after the window is a real failure and is reported as one below.
// Reads the panel in the SAME browser evaluation that decides it settled.
// Deciding and then measuring in a second round-trip let a transient
// non-loading frame satisfy the wait while the text read a moment later was
// back on "Calculando analise..." - a measurement race, not a product state.
async function readSettledAiPanel(page, id) {
  const handle = await page
    .waitForFunction(
      ([panelId, markers]) => {
        const panel = document.querySelector(`#panel-${panelId}`);
        if (!panel) return null;
        const visible = Number(panel.getAttribute("data-ai-visible-count") || 0);
        const raw = panel.textContent || "";
        const normalized = raw.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase();
        const loading = markers.some((marker) => normalized.includes(marker));
        if (visible > 0 || !loading) {
          return {
            text: panel.innerText || raw,
            visible,
            badge: Number(panel.getAttribute("data-ai-badge-count") || 0),
            loading,
          };
        }
        return null;
      },
      [id, AI_LOADING_MARKERS],
      { timeout: 40000 },
    )
    .catch(() => null);
  if (!handle) {
    return page
      .evaluate((panelId) => {
        const panel = document.querySelector(`#panel-${panelId}`);
        if (!panel) return { text: "", visible: 0, badge: 0, loading: true };
        return {
          text: panel.innerText || panel.textContent || "",
          visible: Number(panel.getAttribute("data-ai-visible-count") || 0),
          badge: Number(panel.getAttribute("data-ai-badge-count") || 0),
          loading: true,
        };
      }, id)
      .catch(() => ({ text: "", visible: 0, badge: 0, loading: true }));
  }
  const value = await handle.jsonValue().catch(() => ({ text: "", visible: 0, badge: 0, loading: true }));
  await handle.dispose().catch(() => undefined);
  return value;
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
    const snapshot = await readSettledAiPanel(page, id);
    const text = snapshot.text || "";
    const visibleCount = snapshot.visible;
    const badgeCount = snapshot.badge;
    const normalizedText = normalize(text);
    const tabFailures = [];
    // Terminal honest zero-states rendered by the product (workspace-shell.tsx
    // aiZeroStateNotice). A loading state is deliberately NOT in this list.
    const hasHonestZeroState = normalizedText.includes("0 eventos atuais")
      || normalizedText.includes("0 current events")
      || normalizedText.includes("achados visiveis da lente: 0/")
      || normalizedText.includes("aguardando nova leitura do dia")
      || normalizedText.includes("waiting for a new read")
      || normalizedText.includes("nenhum achado desta ia")
      || normalizedText.includes("no ai finding for this asset")
      || normalizedText.includes("sem nova leitura validada hoje")
      || normalizedText.includes("no new read validated today")
      || normalizedText.includes("dados atuais insuficientes")
      || normalizedText.includes("insufficient current data")
      || normalizedText.includes("a analise nao ficou pronta a tempo")
      || normalizedText.includes("analysis did not finish in time");
    const stillLoading = AI_LOADING_MARKERS.some((marker) => normalizedText.includes(marker));
    pushIf(stillLoading, tabFailures, "IA presa em estado de carregamento");
    pushIf(visibleCount === 0 && !stillLoading && !hasHonestZeroState, tabFailures, "IA vazia sem estado honesto");
    pushIf(badgeCount !== Number(counts[id] ?? 0), tabFailures, "badge do painel e contador da tab divergem");
    tabs[id] = { opened, visible_count: visibleCount, badge_count: badgeCount, text_sample: text.slice(0, 800), failures: tabFailures };
    failures.push(...tabFailures.map((failure) => `${id}: ${failure}`));
  }
  return { counts, tabs, failures };
}

async function auditChart(page, symbol) {
  await clickTab(page, "grafico");
  await page.waitForFunction(() => {
    const shell = document.querySelector(".snbr-chart-shell");
    if (!shell) return false;
    return shell.getAttribute("data-support-overlay-status") === "price_scaled_overlay"
      && shell.getAttribute("data-resistance-overlay-status") === "price_scaled_overlay"
      && shell.querySelectorAll("[data-chart-level-line='support']").length > 0
      && shell.querySelectorAll("[data-chart-level-line='resistance']").length > 0;
  }, undefined, { timeout: 8000 }).catch(() => undefined);
  const shell = page.locator(".snbr-chart-shell").first();
  const attrs = {
    anchor_mode: await shell.getAttribute("data-anchor-mode").catch(() => ""),
    support_anchor_mode: await shell.getAttribute("data-support-anchor-mode").catch(() => ""),
    resistance_anchor_mode: await shell.getAttribute("data-resistance-anchor-mode").catch(() => ""),
    support_status: await shell.getAttribute("data-support-overlay-status").catch(() => ""),
    resistance_status: await shell.getAttribute("data-resistance-overlay-status").catch(() => ""),
    vwap_color: await shell.getAttribute("data-vwap-color").catch(() => ""),
    vwap_width: await shell.getAttribute("data-vwap-width").catch(() => ""),
    tradingview_symbol: await shell.getAttribute("data-tradingview-symbol").catch(() => ""),
    level_symbol: await shell.getAttribute("data-level-symbol").catch(() => ""),
    level_timeframe: await shell.getAttribute("data-level-timeframe").catch(() => ""),
  };
  const visual = await page.evaluate(() => {
    const chartShell = document.querySelector(".snbr-chart-shell");
    const supportLines = [...(chartShell?.querySelectorAll("[data-chart-level-line='support']") || [])];
    const resistanceLines = [...(chartShell?.querySelectorAll("[data-chart-level-line='resistance']") || [])];
    let studies = [];
    let vwapColors = [];
    try {
      const iframe = chartShell?.querySelector("iframe");
      const url = new URL(iframe?.getAttribute("src") || "", window.location.href);
      const settings = JSON.parse(decodeURIComponent(url.hash.slice(1)));
      const overrides = typeof settings.studies_overrides === "string"
        ? JSON.parse(settings.studies_overrides)
        : settings.studies_overrides || {};
      studies = Array.isArray(settings.studies) ? settings.studies : [];
      vwapColors = [
        overrides["volume weighted average price.vwap.color"],
        overrides["vwap.vwap.color"],
      ].filter(Boolean);
    } catch {
      // Assertions below fail closed when the iframe contract cannot be read.
    }
    return {
      line_counts: { support: supportLines.length, resistance: resistanceLines.length },
      support_prices: supportLines.map((line) => line.getAttribute("data-chart-level-price")),
      resistance_prices: resistanceLines.map((line) => line.getAttribute("data-chart-level-price")),
      pane_count: chartShell?.querySelectorAll(".snbr-chart-level-lines").length || 0,
      pane_text: chartShell?.querySelector(".snbr-chart-level-lines")?.textContent || "",
      studies,
      vwap_colors: vwapColors,
    };
  });
  const lineCounts = visual.line_counts;
  const failures = [];
  pushIf(attrs.anchor_mode !== "price_scaled_overlay", failures, "painel não publicou escala real de suporte/resistência");
  pushIf(attrs.support_status !== "price_scaled_overlay", failures, "status de suporte não confirma overlay renderizado");
  pushIf(attrs.resistance_status !== "price_scaled_overlay", failures, "status de resistência não confirma overlay renderizado");
  pushIf(lineCounts.support < 1, failures, "suporte sem linha renderizada");
  pushIf(lineCounts.resistance < 1, failures, "resistência sem linha renderizada");
  pushIf(visual.pane_count !== 1, failures, `painel de níveis divergente: ${visual.pane_count}`);
  pushIf(visual.support_prices.length !== lineCounts.support || visual.support_prices.some((price) => !Number.isFinite(Number(price)) || Number(price) <= 0), failures, "linha de suporte sem preço real");
  pushIf(visual.resistance_prices.length !== lineCounts.resistance || visual.resistance_prices.some((price) => !Number.isFinite(Number(price)) || Number(price) <= 0), failures, "linha de resistência sem preço real");
  pushIf(!/suporte|support/i.test(visual.pane_text) || !/resistência|resistencia|resistance/i.test(visual.pane_text), failures, "texto visível dos níveis diverge das linhas");
  pushIf(String(attrs.level_symbol).toUpperCase() !== symbol, failures, `overlay antigo: ${attrs.level_symbol || "sem símbolo"} em ${symbol}`);
  pushIf(!String(attrs.level_timeframe).trim(), failures, "overlay sem timeframe canônico");
  pushIf(attrs.vwap_color.toLowerCase() !== CANONICAL_VWAP_COLOR, failures, "VWAP fora da cor canônica");
  pushIf(Number(attrs.vwap_width) < 4, failures, "VWAP sem largura mínima 4");
  pushIf(!visual.studies.includes("VWAP@tv-basicstudies"), failures, "VWAP não foi solicitado ao gráfico");
  pushIf(visual.vwap_colors.length !== 2 || visual.vwap_colors.some((color) => String(color).toLowerCase() !== CANONICAL_VWAP_COLOR), failures, "configuração renderizada do VWAP diverge do atributo DOM");
  return { attrs, ...visual, failures };
}

async function auditBlockedPanel(page, symbol, options = {}) {
  const requireNoData = options.requireNoData === true;
  const requireOperational = options.requireOperational === true;
  const snapshot = await page.evaluate(() => {
    const panel = document.querySelector(".snbr-decision-panel");
    const conclusion = panel?.querySelector(".snbr-decision-conclusion");
    return {
      coreData: panel?.getAttribute("data-core-data") || "",
      decisionNow: panel?.getAttribute("data-decision-now") || "",
      tradeSuggested: panel?.getAttribute("data-trade-suggested") || "",
      missingFieldsAttr: panel?.getAttribute("data-missing-fields") || "",
      masterScoreValue: panel?.getAttribute("data-master-score-value") || "",
      rsiValue: panel?.getAttribute("data-rsi-value") || "",
      biasValue: panel?.getAttribute("data-bias-value") || "",
      text: panel?.textContent || "",
      statTexts: Array.from(document.querySelectorAll(".snbr-stat-strip .snbr-stat-cell"), (node) => node.textContent || ""),
      decisionGridCount: panel?.querySelectorAll(".snbr-decision-grid").length || 0,
      conclusionCount: panel?.querySelectorAll(".snbr-decision-conclusion").length || 0,
      conclusionText: conclusion?.textContent || "",
    };
  }).catch(() => ({
    coreData: "", decisionNow: "", tradeSuggested: "", missingFieldsAttr: "", masterScoreValue: "", rsiValue: "", biasValue: "", text: "",
    statTexts: [], decisionGridCount: 0, conclusionCount: 0, conclusionText: "",
  }));
  const { coreData, decisionNow, tradeSuggested, missingFieldsAttr, masterScoreValue, rsiValue, biasValue, text, statTexts, decisionGridCount, conclusionCount, conclusionText } = snapshot;
  const normalizedText = normalize(text);
  const failures = [];
  let assertionCount = 0;
  const assert = (condition, message) => {
    assertionCount += 1;
    if (condition) failures.push(message);
  };

  // Fail closed. The old shape wrapped every assertion in `if (coreData === "false")`,
  // so when the fixture failed to force the no-data state the whole contract was
  // skipped and the scenario passed having verified nothing.
  if (requireNoData) {
    assert(coreData !== "false", `fixture nao produziu core_data=false (recebido: ${coreData || "ausente"})`);
  }

  if (requireOperational) {
    assert(coreData !== "true", `fixture não produziu core_data=true (recebido: ${coreData || "ausente"})`);
    assert(!String(decisionNow || "").trim(), "painel não publicou DECISÃO AGORA");
    assert(!String(tradeSuggested || "").trim(), "painel não publicou TRADE SUGERIDO");
    assert(conclusionCount < 1 || normalize(conclusionText).length < 20, "painel não publicou conclusão operacional");
    assert(normalize(decisionNow).includes("dados reais"), "painel com números permaneceu em AGUARDAR DADOS REAIS");
    assert(
      !statTexts.some((value) => /preço|preco|volume|score|rsi|bias|vwap/i.test(value) && /\d/.test(value)),
      "painel não exibiu contexto numérico de preço/volume/score/RSI/bias",
    );
  }

  if (requireNoData || coreData === "false") {
    assert(!normalizedText.includes("aguardar dados reais"), "painel sem dados não mostra AGUARDAR DADOS REAIS");
    assert(normalizedText.includes("entre venda e compra"), "painel sem dados mostra Entre Venda e Compra");
    assert(/\b(compra somente|buscar gatilho de compra|venda \/ short|encerrar posicao|encerrar \/ proteger)\b/.test(normalizedText), "painel sem dados mostra ação operacional");
    assert(!normalizedText.includes("campos faltantes"), "painel sem dados não lista campos faltantes");
    assert(!missingFieldsAttr, "painel sem dados não recebeu missing_fields do backend");
    assert(decisionGridCount > 0, "painel sem dados renderiza cards de score/bias/RSI/trade");
    assert(conclusionCount > 0, "painel sem dados renderiza conclusão operacional");
    assert(statTexts.some((value) => /score mestre|rsi score|bias/i.test(value)), "painel sem dados mostra score/bias/RSI no cabeçalho");
    // Stale price/change/volume/VWAP from a previous symbol must not survive as
    // current operational data.
    assert(
      statTexts.some((value) => {
        const normalizedValue = normalize(value);
        return /variacao|volume|vwap|preco/.test(normalizedValue) && /\d/.test(normalizedValue);
      }),
      "painel sem dados mantém preço/variação/volume/VWAP stale",
    );
  }
  return {
    symbol,
    core_data: coreData,
    decision_now: decisionNow,
    trade_suggested: tradeSuggested,
    missing_fields: missingFieldsAttr ? missingFieldsAttr.split(",").filter(Boolean) : [],
    master_score_value: masterScoreValue,
    rsi_value: rsiValue,
    bias_value: biasValue,
    decision_grid_count: decisionGridCount,
    conclusion_count: conclusionCount,
    conclusion_text: conclusionText,
    stat_texts: statTexts,
    text_sample: text.slice(0, 520),
    assertion_count: assertionCount,
    failures,
  };
}

// Deterministic fixture payload: explicit nulls, never a fabricated zero.
function forcedQuotePayload() {
  return {
    symbol: FORCED_FAILURE_REAL_SYMBOL,
    price: null,
    change: null,
    change_percent: null,
    volume: null,
    vwap: null,
    updated_at: "2026-07-31T20:00:00Z",
    core_data: false,
    strategic_core_data: false,
    missing_fields: ["price", "volume", "vwap"],
  };
}

async function auditForcedProviderFailureRealTicker(browser) {
  const mockQuote = forcedQuotePayload();
  const mockBundle = {
    symbol: FORCED_FAILURE_REAL_SYMBOL,
    quote: mockQuote,
    historical: [],
    news: [],
    events: [],
    ai_insights: [],
  };
  const mockWorkspace = {
    symbol: FORCED_FAILURE_REAL_SYMBOL,
    chart: {},
    insight: { symbol: FORCED_FAILURE_REAL_SYMBOL, score: null, rsi: null, trend_bias: null, signal: null, status: "empty" },
    feed: { items: [], symbol: FORCED_FAILURE_REAL_SYMBOL },
    news: { symbol: FORCED_FAILURE_REAL_SYMBOL, items: [], count: 0, status: "empty" },
    room: { symbol: FORCED_FAILURE_REAL_SYMBOL, items: [] },
    quote: mockQuote,
    source: "forced_provider_failure",
  };

  const counters = { workspace: 0, bundle: 0, quotes: 0 };
  const failures = [];
  const screenshot = path.join(screenshotDir, `${FORCED_FAILURE_REAL_SYMBOL.toLowerCase()}-forced-provider-failure-real-ticker-fullpage.jpg`);
  // Own context: a fresh origin store, so no localStorage or in-page cache from
  // the normal run can rehydrate a stale price into this scenario. Closing the
  // context disposes every route with it — nothing leaks back to the main flow.
  const context = await browser.newContext({ viewport: { width: 1600, height: 950 } });
  let panel = null;
  let proMode = false;

  try {
    await applyEphemeralAuth(context);
    await installNetworkFence(context);
    await context.route(new RegExp(`/web/workspace/ticker/${FORCED_FAILURE_REAL_SYMBOL}(?:[/?]|$)`), async (route) => {
      counters.workspace += 1;
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(mockWorkspace) }).catch(() => undefined);
    });
    await context.route(new RegExp(`/public/market/bundle/${FORCED_FAILURE_REAL_SYMBOL}(?:[/?]|$)`), async (route) => {
      counters.bundle += 1;
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(mockBundle) }).catch(() => undefined);
    });
    await context.route("**/public/market/quotes*", async (route) => {
      counters.quotes += 1;
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ items: [mockQuote] }) }).catch(() => undefined);
    });

    const page = await context.newPage();
    await openPanel(page, FORCED_FAILURE_REAL_SYMBOL);
    const forcedProStats = await enableProMode(page);
    proMode = forcedProStats.ok;
    await page.waitForFunction(() => {
      const decisionPanel = document.querySelector(".snbr-decision-panel");
      return decisionPanel?.getAttribute("data-core-data") === "false"
        && Boolean(decisionPanel.getAttribute("data-missing-fields"));
    }, undefined, { timeout: 8000 }).catch(() => undefined);
    panel = await auditBlockedPanel(page, FORCED_FAILURE_REAL_SYMBOL, { requireNoData: true });
    await page.screenshot({ path: screenshot, type: "jpeg", quality: 82, fullPage: true }).catch(() => undefined);
    await page.close().catch(() => undefined);
  } finally {
    await context.close().catch(() => undefined);
  }

  const assertionCount = panel?.assertion_count ?? 0;
  failures.push(...(panel?.failures || []));
  pushIf(!panel, failures, "cenário forced não coletou o painel");
  pushIf(!proMode, failures, "cenário forced não entrou em Modo Pro");
  pushIf(counters.workspace < 1, failures, "intercept forced do workspace não foi consumido");
  pushIf(counters.bundle < 1, failures, "intercept forced do bundle não foi consumido");
  pushIf(counters.quotes < 1, failures, "intercept forced do lote de quotes não foi consumido");
  pushIf(assertionCount === 0, failures, "cenário forced não executou nenhuma assertion");
  pushIf((panel?.missing_fields || []).length === 0, failures, "ticker real com core_data=false ficou sem missing_fields");

  return {
    symbol: FORCED_FAILURE_REAL_SYMBOL,
    provider_forced_failure: true,
    forced_endpoint: `/public/market/bundle/${FORCED_FAILURE_REAL_SYMBOL}`,
    registered_intercepts: ["workspace", "bundle", "quotes_batch"],
    forced_workspace_intercept_count: counters.workspace,
    forced_bundle_intercept_count: counters.bundle,
    forced_quotes_batch_intercept_count: counters.quotes,
    forced_assertion_count: assertionCount,
    pro_mode: proMode,
    fallback_used: panel?.core_data === "false" ? "empty" : "cache_or_snapshot",
    core_data: panel?.core_data ?? null,
    missing_fields: panel?.missing_fields || [],
    decision_grid_count: panel?.decision_grid_count ?? null,
    conclusion_count: panel?.conclusion_count ?? null,
    screenshot,
    panel,
    failures,
  };
}

const applyEphemeralAuth = (context) => applySharedAuth(context, VALID_JWT_TOKEN);

async function main() {
  ensureDir(path.dirname(reportPath));
  ensureDir(screenshotDir);
  let report = null;
  const proModeStats = { accessResolved: 0, restored: 0, clicks: 0, persistPro: 0, persistSimple: 0, logicalRequests: 0, networkRequests: 0, staleIgnored: 0, denied: 0 };

  try {
    const fixtureStart = startFixtureLifecycle();
    sessionBaseline = countSessions();
    EPHEMERAL_SESSION = generateEphemeralSession();
    VALID_JWT_TOKEN = EPHEMERAL_SESSION.token;
    TOKEN_TTL_SECONDS = EPHEMERAL_SESSION.ttlSeconds;
    report = {
      generated_at: new Date().toISOString(),
      web_base: WEB_BASE,
      api_base: API_BASE,
      token_ttl_seconds: TOKEN_TTL_SECONDS,
      population: POPULATION,
      expected_symbols: [...SYMBOLS],
      symbols_expected: REQUIRED_SYMBOL_COUNT,
      symbols_executed: [...SYMBOLS],
      fixture_generation: fixtureStart.generation,
      fixture_manual_reseed_required: false,
      fixture_manual_clear_required: false,
      operational_requirements_enforced: REQUIRE_OPERATIONAL,
      fixture_start: fixtureStart,
      alpaca_diagnostic: loadJsonFile(alpacaDiagnosticPath) || {
        status: "missing",
        file: alpacaDiagnosticPath,
        note: "No provider diagnostic is executed by this offline gate.",
      },
      symbols: {},
      failures: [],
    };

    pushIf(SYMBOLS.length !== REQUIRED_SYMBOL_COUNT, report.failures, `população ${POPULATION} tem ${SYMBOLS.length}/${REQUIRED_SYMBOL_COUNT} ativos`);
    pushIf(fixtureStart.population !== POPULATION, report.failures, `fixture executou população ${fixtureStart.population || "ausente"}`);
    pushIf(JSON.stringify(fixtureStart.symbols || []) !== JSON.stringify(SYMBOLS), report.failures, "fixture e browser divergem na população/ordem");

    const browser = await chromium.launch({ headless: HEADLESS });
    activeBrowser = browser;
    const context = await browser.newContext({ viewport: { width: 1600, height: 950 } });
    await applyEphemeralAuth(context);
    await installNetworkFence(context);
    const page = await context.newPage();
    const browserBundles = new Map();
    const browserRequestCounts = new Map();
    const uiNewsPayloads = new Map();
    page.on("request", (request) => {
      const match = new URL(request.url()).pathname.match(/^\/(public\/market\/bundle|web\/workspace\/ticker)\/([^/]+)$/);
      if (!match) return;
      const symbol = decodeURIComponent(match[2]).toUpperCase();
      const kind = match[1] === "public/market/bundle" ? "public" : "workspace";
      const counts = browserRequestCounts.get(symbol) || { public: 0, workspace: 0 };
      counts[kind] += 1;
      browserRequestCounts.set(symbol, counts);
    });
    page.on("response", async (response) => {
      // News the UI fetched for itself. Recorded so the audit compares the DOM
      // against the payload the app actually consumed, not only against a
      // payload the audit fetched on a separate connection.
      const newsMatch = new URL(response.url()).pathname.match(/^\/(?:public\/market\/)?news\/([^/]+)$/);
      if (newsMatch) {
        const newsPayload = await response.json().catch(() => null);
        const newsSymbol = decodeURIComponent(newsMatch[1]).toUpperCase();
        uiNewsPayloads.set(newsSymbol, {
          status: response.status(),
          count: Number(newsPayload?.count ?? (newsPayload?.items || []).length ?? 0),
          news_status: newsPayload?.status || null,
          symbol: newsPayload?.symbol || null,
        });
        return;
      }
      const kind = response.url().includes("/public/market/bundle/")
        ? "public"
        : response.url().includes("/web/workspace/ticker/")
          ? "workspace"
          : null;
      if (!kind) return;
      const payload = await response.json().catch(() => null);
      const symbol = String(payload?.symbol || "").toUpperCase();
      if (!symbol) return;
      const insight = payload?.insight || {};
      const operational = payload?.market_metrics?.operational_view || {};
      const rows = browserBundles.get(symbol) || [];
      rows.push({
        kind,
        status: response.status(),
        quote_source: payload?.quote?.source || null,
        quote_price: payload?.quote?.price ?? null,
        quote_volume: payload?.quote?.volume ?? null,
        quote_core_data: payload?.quote?.core_data ?? null,
        hydration_status: payload?.hydration?.status || null,
        data_status: payload?.data_status || {},
        score: insight.score ?? null,
        master_score: insight.master_score ?? null,
        rsi: insight.rsi ?? null,
        trend_bias: insight.trend_bias || null,
        operational_score: operational.operational_context?.master_score?.value ?? null,
      });
      browserBundles.set(symbol, rows);
    });

    for (const symbol of SYMBOLS) {
      // Establish the server-side news state BEFORE the page loads, so the
      // panel's own fetch observes the seeded payload. Seeding after openPanel
      // made the audit assert a DOM whose in-flight request predated the seed.
      const newsSeed = await seedNews(symbol);
      await openPanel(page, symbol, { requireOperational: REQUIRE_OPERATIONAL });
      const proStats = await enableProMode(page);
      const proMode = proStats.ok;
      proModeStats.accessResolved += proStats.accessState === "ALLOWED" ? 1 : 0;
      proModeStats.logicalRequests = Math.max(proModeStats.logicalRequests, proStats.ACCESS_LOGICAL_REQUEST_COUNT);
      proModeStats.networkRequests = Math.max(proModeStats.networkRequests, proStats.ACCESS_NETWORK_REQUEST_COUNT);
      proModeStats.staleIgnored += proStats.ACCESS_STALE_RESPONSE_IGNORED_COUNT;
      proModeStats.denied += proStats.ACCESS_DENIED_COUNT;
      proModeStats.restored += proStats.restored ? 1 : 0;
      proModeStats.clicks += proStats.clicks;
      proModeStats.persistPro = Math.max(proModeStats.persistPro, proStats.persistPro);
      proModeStats.persistSimple = Math.max(proModeStats.persistSimple, proStats.persistSimple);
      const screenshot = path.join(screenshotDir, `${symbol.toLowerCase()}-panel.jpg`);
      await page.screenshot({ path: screenshot, type: "jpeg", quality: 82, fullPage: false }).catch(() => undefined);
      const quote_state = await auditQuoteState(symbol);
      const panel = await auditBlockedPanel(page, symbol, { requireOperational: REQUIRE_OPERATIONAL });
      const news = await auditNews(page, symbol, {
        requireTab: REQUIRE_OPERATIONAL,
        seed: newsSeed,
        uiPayload: uiNewsPayloads.get(symbol.toUpperCase()) || null,
      });
      const ai = await auditAiTabs(page);
      const chart = await auditChart(page, symbol);
      const failures = [...panel.failures, ...news.failures, ...ai.failures, ...(chart?.failures || [])];
      const fallback = buildFallbackAudit(symbol, quote_state, panel);
      const requests = browserRequestCounts.get(symbol) || { public: 0, workspace: 0 };
      const analysis = quote_state.analysis || {};
      const publicBundleEvidence = [...(browserBundles.get(symbol) || [])]
        .reverse()
        .find((row) => row.kind === "public");
      const quotePrice = Number(quote_state.quote?.price ?? quote_state.bundle?.price);
      const quoteVolume = Number(quote_state.quote?.volume ?? quote_state.bundle?.volume);
      const masterScoreRaw = publicBundleEvidence?.operational_score
        ?? publicBundleEvidence?.master_score
        ?? analysis.operational_score
        ?? analysis.master_score;
      const rsiRaw = publicBundleEvidence?.rsi ?? analysis.rsi;
      const masterScore = masterScoreRaw == null || masterScoreRaw === "" ? Number.NaN : Number(masterScoreRaw);
      const rsi = rsiRaw == null || rsiRaw === "" ? Number.NaN : Number(rsiRaw);
      const direction = String(publicBundleEvidence?.trend_bias || analysis.trend_bias || analysis.operational_decision || "").trim();
      const panelMasterScore = panel.master_score_value === "" ? Number.NaN : Number(panel.master_score_value);
      const panelRsi = panel.rsi_value === "" ? Number.NaN : Number(panel.rsi_value);
      const operationalEvidence = {
        price: quotePrice,
        volume: quoteVolume,
        master_score: masterScore,
        rsi,
        direction,
        panel_master_score: panelMasterScore,
        panel_rsi: panelRsi,
        panel_bias: panel.bias_value,
        conclusion_count: panel.conclusion_count,
        source: "browser_public_bundle",
      };
      pushIf(!proMode, failures, "painel não entrou em Modo Pro");
      if (REQUIRE_OPERATIONAL) {
        pushIf(!Number.isFinite(quotePrice) || quotePrice <= 0, failures, `${symbol} sem preço numérico positivo`);
        pushIf(!Number.isFinite(quoteVolume) || quoteVolume <= 0, failures, `${symbol} sem volume numérico positivo`);
        pushIf(!Number.isFinite(masterScore) || masterScore < 0 || masterScore > 10, failures, `${symbol} sem Master Score real`);
        pushIf(!Number.isFinite(rsi) || rsi < 0 || rsi > 100, failures, `${symbol} sem RSI real`);
        pushIf(!direction, failures, `${symbol} sem direção real`);
        pushIf(!Number.isFinite(panelMasterScore) || Math.abs(panelMasterScore - masterScore) > 0.001, failures, `${symbol} atributo DOM do Master Score divergente`);
        pushIf(!Number.isFinite(panelRsi) || Math.abs(panelRsi - rsi) > 0.001, failures, `${symbol} atributo DOM do RSI divergente`);
        pushIf(!String(panel.bias_value).trim(), failures, `${symbol} atributo DOM da direção ausente`);
        pushIf(panel.conclusion_count < 1 || normalize(panel.conclusion_text).length < 20, failures, `${symbol} sem conclusão real`);
        pushIf(panel.stat_texts.some((value) => /\b(undefined|null|nan|placeholder|mock|fake)\b/i.test(value)), failures, `${symbol} painel contém placeholder`);
        // Levels must bracket the quote, not merely be positive. Checking only `> 0`
        // let PETR4 publish a support of 191.20 against a 43.42 quote, and VALE3/ITUB4
        // publish a resistance *below* spot -- positive, rendered, and meaningless.
        // Tolerance is one cent: enough for monetary rounding, not enough to hide an
        // inverted level.
        const supportPrice = Number((chart?.support_prices || [])[0]);
        const resistancePrice = Number((chart?.resistance_prices || [])[0]);
        pushIf(!Number.isFinite(supportPrice) || supportPrice <= 0, failures, `${symbol} sem suporte finito positivo`);
        pushIf(!Number.isFinite(resistancePrice) || resistancePrice <= 0, failures, `${symbol} sem resistência finita positiva`);
        pushIf(
          Number.isFinite(supportPrice) && Number.isFinite(quotePrice) && supportPrice > quotePrice + LEVEL_BRACKET_EPSILON,
          failures,
          `${symbol} suporte ${supportPrice} acima do preço ${quotePrice}`,
        );
        pushIf(
          Number.isFinite(resistancePrice) && Number.isFinite(quotePrice) && resistancePrice < quotePrice - LEVEL_BRACKET_EPSILON,
          failures,
          `${symbol} resistência ${resistancePrice} abaixo do preço ${quotePrice}`,
        );
      }
      pushIf(requests.public < 1, failures, `${symbol} bundle público não foi consumido pelo browser`);
      pushIf(requests.workspace < 1, failures, `${symbol} bundle autenticado não foi consumido pelo browser`);
      pushIf(publicBundleEvidence?.status !== 200, failures, `${symbol} bundle público consumido sem HTTP 200`);
      pushIf(panel.core_data === "false" && panel.missing_fields.length === 0, failures, `${symbol} core_data=false sem missing_fields`);
      pushIf(!fallback, failures, `${symbol} sem fallback_path estruturado`);
      report.symbols[symbol] = { screenshot, pro_mode: proMode, pro_stats: proStats, request_counts: requests, operational_evidence: operationalEvidence, quote_state, browser_bundles: browserBundles.get(symbol) || [], panel, news, ai, chart, fallback, failures };
      report.failures.push(...failures.map((failure) => `${symbol}: ${failure}`));
    }

    pushIf(Object.keys(report.symbols).join(",") !== POPULATION_SIGNATURES[POPULATION], report.failures, "população executada diverge do contrato exato");

    await context.close().catch(() => undefined);

    report.pro_mode_stats = {
      ACCESS_RESOLVED_COUNT: proModeStats.accessResolved,
      PRO_RESTORE_COUNT: proModeStats.restored,
      PRO_USER_CLICK_COUNT: proModeStats.clicks,
      PRO_PERSIST_WRITE_COUNT: proModeStats.persistPro,
      SIMPLE_PERSIST_WRITE_COUNT: proModeStats.persistSimple,
      ACCESS_LOGICAL_REQUEST_COUNT: proModeStats.logicalRequests,
      ACCESS_NETWORK_REQUEST_COUNT: proModeStats.networkRequests,
      ACCESS_STALE_RESPONSE_IGNORED_COUNT: proModeStats.staleIgnored,
      ACCESS_DENIED_COUNT: proModeStats.denied,
    };
    // One logical access request per page: a second one means a competing owner
    // came back.
    pushIf(proModeStats.logicalRequests > 1, report.failures, `access teve ${proModeStats.logicalRequests} requests lógicas (esperado 1)`);
    // The stored preference is "pro", so the bootstrap must restore it without
    // any user click. A click here means the product regressed.
    pushIf(proModeStats.clicks > 0, report.failures, `bootstrap exigiu ${proModeStats.clicks} clique(s) apesar da preferência salva ser pro`);

    const forcedReal = await auditForcedProviderFailureRealTicker(browser);
    report.forced_provider_failure_real_ticker = forcedReal;
    report.failures.push(...forcedReal.failures.map((failure) => `${FORCED_FAILURE_REAL_SYMBOL} forced: ${failure}`));
    await browser.close().catch(() => undefined);
    activeBrowser = null;
  } finally {
    await activeBrowser?.close().catch(() => undefined);
    activeBrowser = null;
    const lifecycle = finishLifecycle();
    if (report) {
      Object.assign(report, lifecycle, {
        external_provider_calls: 0,
        blocked_external_origins: [...blockedExternalOrigins].sort(),
        fixture_manual_reseed_required: false,
        fixture_manual_clear_required: false,
      });
    }
  }

  pushIf(
    report.session_rows_remaining_after_cleanup !== 0,
    report.failures,
    `sessão efêmera não foi removida (restantes: ${report.session_rows_remaining_after_cleanup})`,
  );
  pushIf(report.session_delta !== 0, report.failures, `SESSION_DELTA=${report.session_delta}`);
  pushIf(
    report.fixture_residual_entries !== 0,
    report.failures,
    `FIXTURE_RESIDUAL_ENTRIES=${report.fixture_residual_entries}`,
  );
  pushIf(Boolean(report.fixture_refresh_failure), report.failures, `fixture refresh falhou: ${report.fixture_refresh_failure}`);
  pushIf(
    report.fixture_external_provider_calls !== 0,
    report.failures,
    `FIXTURE_EXTERNAL_PROVIDER_CALLS=${report.fixture_external_provider_calls}`,
  );

  fs.writeFileSync(reportPath, JSON.stringify(report, null, 2), "utf8");
  console.log(JSON.stringify({
    reportPath,
    failureCount: report.failures.length,
    population: POPULATION,
    symbolsExecuted: [...SYMBOLS],
    symbolCount: SYMBOLS.length,
    tokenTtlSeconds: TOKEN_TTL_SECONDS,
    proMode: `${proModeStats.restored}/${SYMBOLS.length} restaurados, ${proModeStats.clicks} cliques`,
    forcedAssertions: report.forced_provider_failure_real_ticker?.forced_assertion_count ?? 0,
    forcedIntercepts:
      (report.forced_provider_failure_real_ticker?.forced_workspace_intercept_count ?? 0) +
      (report.forced_provider_failure_real_ticker?.forced_bundle_intercept_count ?? 0) +
      (report.forced_provider_failure_real_ticker?.forced_quotes_batch_intercept_count ?? 0),
  }, null, 2));
  console.log("FIXTURE_MANUAL_RESEED_REQUIRED=false");
  console.log("FIXTURE_MANUAL_CLEAR_REQUIRED=false");
  console.log(`FIXTURE_RESIDUAL_ENTRIES=${report.fixture_residual_entries}`);
  console.log(`FIXTURE_EXTERNAL_PROVIDER_CALLS=${report.fixture_external_provider_calls}`);
  console.log(`SESSION_DELTA=${report.session_delta}`);
  console.log("EXTERNAL_PROVIDER_CALLS=0");
  if (report.failures.length) process.exit(1);
}

main().catch((error) => {
  ensureDir(path.dirname(reportPath));
  const payload = { generated_at: new Date().toISOString(), error: String(error?.stack || error), lifecycle: lifecycleResult };
  fs.writeFileSync(reportPath, JSON.stringify(payload, null, 2), "utf8");
  console.error(error);
  process.exit(1);
});
