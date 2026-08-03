// Focused contract: a real news item served by the API must survive
// normalization and reach the DOM as a real card for the requested symbol.
//
// Guards the API -> DOM ordering defect found in mission31a2 (PETR4):
// the panel issues its own news request during page load, so seeding the
// server AFTER the page loaded mutates state behind a request that already
// left, and the audit then measures a panel still resolving its own fetch.
//
// Modes:
//   default            seed BEFORE load, wait for the panel's terminal phase (GREEN)
//   NEWS_CONTRACT_LEGACY_ORDER=1  seed AFTER load, assert straight after the tab
//                      click without waiting for the panel to resolve (RED)
//
// The legacy mode exists to prove this test can fail: it reproduces the exact
// ordering that produced "API tem notícia, DOM não renderizou card real".
import pw from "playwright";

const { chromium } = pw;

const WEB_BASE = process.env.NEWS_CONTRACT_WEB_BASE || "http://127.0.0.1:3000";
const API_BASE = process.env.NEWS_CONTRACT_API_BASE || "http://127.0.0.1:8000";
const SYMBOL = process.env.NEWS_CONTRACT_SYMBOL || "PETR4";
const LEGACY_ORDER = process.env.NEWS_CONTRACT_LEGACY_ORDER === "1";
const TERMINAL_PHASES = ["ready", "historical", "empty", "error"];
const MIN_HEADLINE_CHARS = 24;

const failures = [];
const pushIf = (condition, message) => {
  if (condition) failures.push(message);
};

async function seedNews() {
  const response = await fetch(`${API_BASE}/public/market/news/${encodeURIComponent(SYMBOL)}?limit=6&refresh=mission31a2`);
  const payload = await response.json();
  return {
    http: response.status,
    count: Number(payload?.count ?? (payload?.items || []).length ?? 0),
    status: payload?.status ?? null,
    symbol: payload?.symbol ?? null,
    items: payload?.items || [],
  };
}

async function openPanel(page) {
  await page.goto(`${WEB_BASE}/panel/${encodeURIComponent(SYMBOL)}`, { waitUntil: "domcontentloaded" });
  await page.locator("main").waitFor({ state: "visible", timeout: 20000 });
}

async function openNewsTab(page) {
  const button = page.locator(".snbr-top-tabs button[role='tab'][aria-controls='panel-news']").first();
  if ((await button.count()) === 0) return false;
  await button.evaluate((element) => {
    if (element instanceof HTMLElement) element.click();
  });
  await page.locator("#panel-news").first().waitFor({ state: "visible", timeout: 8000 }).catch(() => undefined);
  return true;
}

async function readPanel(page) {
  return page.evaluate(() => {
    const panel = document.querySelector("#panel-news");
    const cards = [...document.querySelectorAll("[data-news-card='true']")].map((node) => ({
      matched: node.getAttribute("data-news-matched-symbol") || "",
      source: node.getAttribute("data-news-source") || "",
      published: node.getAttribute("data-news-published-source") || "",
      url: node.getAttribute("data-news-url") || "",
      text: (node.textContent || "").trim(),
    }));
    return {
      phase: panel?.getAttribute("data-news-phase") ?? null,
      stateCount: Number(panel?.getAttribute("data-news-state-count") ?? -1),
      symbol: panel?.getAttribute("data-news-symbol") ?? null,
      cards,
    };
  });
}

async function main() {
  const browser = await chromium.launch({ args: ["--no-sandbox"] });
  const page = await browser.newPage();

  // The payload the UI fetched for itself -- what the DOM must actually reflect.
  let uiPayload = null;
  page.on("response", async (response) => {
    if (!/\/news\//.test(response.url())) return;
    const body = await response.json().catch(() => null);
    if (!body) return;
    uiPayload = { count: Number(body?.count ?? (body?.items || []).length ?? 0), symbol: body?.symbol ?? null };
  });

  let seed;
  if (LEGACY_ORDER) {
    await openPanel(page);
    seed = await seedNews();
  } else {
    seed = await seedNews();
    await openPanel(page);
  }

  // The API must actually be serving real news; otherwise this run proves nothing.
  pushIf(seed.http !== 200, `API respondeu HTTP ${seed.http}`);
  pushIf(seed.count <= 0, `API não devolveu notícia real para ${SYMBOL} (count=${seed.count})`);
  pushIf(String(seed.symbol || "").toUpperCase() !== SYMBOL, `API devolveu símbolo ${seed.symbol}, esperado ${SYMBOL}`);

  const tabOpened = await openNewsTab(page);
  pushIf(!tabOpened, "aba Notícias não abriu");

  if (!LEGACY_ORDER) {
    const reachedTerminal = await page
      .waitForFunction(
        (terminal) => {
          const panel = document.querySelector("#panel-news");
          if (!panel) return false;
          return terminal.includes(panel.getAttribute("data-news-phase") || "");
        },
        TERMINAL_PHASES,
        { timeout: 8000 },
      )
      .then(() => true)
      .catch(() => false);
    pushIf(!reachedTerminal, "painel de notícias não alcançou fase terminal");
  }

  const panel = await readPanel(page);

  pushIf(seed.count > 0 && panel.cards.length === 0, "API tem notícia, DOM não renderizou card real");
  pushIf(
    uiPayload && uiPayload.count > 0 && panel.cards.length === 0,
    `UI recebeu ${uiPayload?.count} notícia(s) e não renderizou card`,
  );
  pushIf(
    panel.stateCount >= 0 && panel.stateCount !== panel.cards.length,
    `estado do painel (${panel.stateCount}) diverge dos cards (${panel.cards.length})`,
  );
  pushIf(
    String(panel.symbol || "").toUpperCase() !== SYMBOL,
    `painel renderizou símbolo ${panel.symbol}, esperado ${SYMBOL}`,
  );

  panel.cards.forEach((card, index) => {
    pushIf(card.text.length < MIN_HEADLINE_CHARS, `card ${index + 1} é placeholder sem manchete real`);
    pushIf(!card.source, `card ${index + 1} sem fonte`);
    pushIf(!card.published, `card ${index + 1} sem data/hora da fonte`);
    pushIf(
      card.matched && card.matched.toUpperCase() !== SYMBOL,
      `card ${index + 1} contaminado por ${card.matched}`,
    );
  });

  const keys = panel.cards.map((card) => `${card.url}|${card.text.slice(0, 120)}`);
  pushIf(new Set(keys).size !== keys.length, "cards de notícia duplicados no DOM");

  const report = {
    mode: LEGACY_ORDER ? "legacy-order (expected RED)" : "seeded-before-load (expected GREEN)",
    symbol: SYMBOL,
    api_count: seed.count,
    api_status: seed.status,
    ui_payload_count: uiPayload?.count ?? null,
    panel_phase: panel.phase,
    panel_state_count: panel.stateCount,
    dom_cards: panel.cards.length,
    failureCount: failures.length,
    failures,
  };
  console.log(JSON.stringify(report, null, 2));

  await browser.close();
  process.exit(failures.length === 0 ? 0 : 1);
}

main().catch((error) => {
  console.error("NEWS_CONTRACT_ERROR", error);
  process.exit(1);
});
