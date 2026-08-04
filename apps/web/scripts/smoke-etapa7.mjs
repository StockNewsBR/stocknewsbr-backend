import fs from "node:fs";
import path from "node:path";
import { chromium } from "playwright";
import {
  applyEphemeralAuth,
  countSessions,
  enableProMode,
  generateEphemeralSession,
  revokeEphemeralSession,
} from "./lib/ephemeral-auth.mjs";

const baseUrl = process.env.SNBR_WEB_URL || "http://127.0.0.1:3000";
const repoRoot = path.resolve(process.cwd(), "..", "..");
const runtimeDir = path.join(repoRoot, "runtime", "etapa7");
const tickers = ["F", "PETR4", "BTCUSD", "M1TA34"];
const aiTabs = [
  { id: "flow", name: /Fluxo IA|Flow AI/i },
  { id: "liquidity", name: /Liquidez IA|Liquidity AI/i },
  { id: "trend", name: /Tendência IA|Trend AI/i },
  { id: "momentum", name: /Momento IA|Momentum AI/i },
  { id: "smart-money", name: /Smart|Dinheiro/i },
];
const helpSections = [
  { label: "1️⃣ Sobre a Empresa", id: "sobre-a-empresa", title: "Sobre a Empresa" },
  { label: "2️⃣ Principais Módulos da Plataforma", id: "principais-modulos", title: "Principais Módulos da Plataforma" },
  { label: "3️⃣ Glossário: Painel de Análise Estratégica", id: "glossario-painel-estrategico", title: "Glossário: Painel de Análise Estratégica" },
  { label: "4️⃣ Glossário: Gráfico do Ativo", id: "glossario-grafico-ativo", title: "Glossário: Gráfico do Ativo" },
  { label: "5️⃣ Glossário: Modos de Uso da Plataforma", id: "glossario-modos-plataforma", title: "Glossário: Modos de Uso da Plataforma" },
  { label: "6️⃣ Guia Rápido StockNewsBR", id: "guia-rapido-stocknewsbr", title: "Guia Rápido StockNewsBR" },
  { label: "7️⃣ Plataforma Web Trader Desk", id: "plataforma-web-trader-desk", title: "Plataforma Web Trader Desk" },
  { label: "8️⃣ Aviso legal", id: "aviso-legal", title: "Aviso legal" },
  { label: "9️⃣ Por que escolher StockNewsBR?", id: "por-que-stocknewsbr", title: "Por que escolher StockNewsBR?" },
];

/**
 * Every non-terminal AI panel state, in both locales.
 *
 * workspace-shell emits exactly two transients -- "AI loading. / Waiting for the current
 * payload." and "Calculating analysis..." -- and the smoke previously knew about only the
 * first. Reading the panel during the second is what produced "precisa exibir horario
 * real" against a panel that was still computing.
 */
const TRANSIENT_AI_STATE = new RegExp(
  [
    "AI loading",
    "IA carregando",
    "Waiting for the current payload",
    "Aguardando o payload atual",
    "Calculating analysis",
    "Calculando an\\u00e1lise",
  ].join("|"),
  "i",
);

/**
 * The product's honest terminal "nothing to report" states.
 *
 * These are the strings workspace-shell emits when an attempt completed and had no valid
 * reading to publish. They are not placeholders and not fabricated data -- they are the
 * correct answer for a cold cache. The smoke previously enumerated only two of them, so a
 * panel sitting in one of the others read as a missing timestamp. Listing them in one
 * place keeps the real assertion below intact: when a reading *is* present it must still
 * carry a time, a Score, a Trigger and an invalidation.
 */
const HONEST_EMPTY_AI_STATE = new RegExp(
  [
    "No operational read with confirmed price and volume",
    "Sem leitura operacional com pre\\u00e7o e volume confirmados",
    "Insufficient current data",
    "Dados atuais insuficientes",
    "The pending hydration expired; no current reading was published",
    "A hidrata\\u00e7\\u00e3o pendente expirou; nenhuma leitura atual foi publicada",
    "No new read validated today",
    "Sem nova leitura validada hoje",
  ].join("|"),
  "i",
);

// A panel is terminal when it either published a reading (timestamped) or reported one of
// the honest empty states above. Kept as a source string so it can cross into the page.
const TERMINAL_AI_STATE_SOURCE = [
  "Found:",
  "Encontrado:",
  HONEST_EMPTY_AI_STATE.source,
  "0 current events",
  "0 eventos atuais",
].join("|");

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

async function pageText(page) {
  return (await page.locator("body").innerText()).replace(/\s+/g, " ").trim();
}

async function waitForPanel(page) {
  await page.waitForLoadState("domcontentloaded");
  await page.locator("main").waitFor({ timeout: 30_000 });
  await page.waitForTimeout(700);
}

/**
 * Wait for the AI panel to reach a terminal state.
 *
 * Asserting on a fixed sleep read the panel mid-flight, while it still said "AI loading.
 * Waiting for the current payload." -- a transient that is neither a reading nor an empty
 * state. This waits on the condition instead of on the clock: no timeout was raised, and
 * a panel that never settles still fails.
 */
async function waitForSettledAiPanel(page, tabId = "flow") {
  // Returns the panel text captured AT the moment it was terminal.
  //
  // Waiting and then re-reading is a race: the panel oscillates (hydration expires after
  // the backend's _WORKER_TIMEOUT_SECONDS, the panel republishes, and it re-enters
  // "Calculating analysis..."), so a separate innerText() call could land back in a
  // transient and report a settled panel as missing its timestamp. Capturing inside the
  // predicate removes the gap entirely.
  const handle = await page
    .waitForFunction(
      ({ id, terminal }) => {
        const panel = document.querySelector(`#panel-${id}`);
        const panelText = panel?.textContent || "";
        if (!panelText) return null;
        return new RegExp(terminal, "i").test(panelText) ? panelText : null;
      },
      { id: tabId, terminal: `${TERMINAL_AI_STATE_SOURCE}` },
      { timeout: 45_000, polling: 400 },
    )
    .catch(() => null);
  if (!handle) return "";
  const captured = await handle.jsonValue().catch(() => "");
  return String(captured || "").replace(/\s+/g, " ").trim();
}

fs.mkdirSync(runtimeDir, { recursive: true });

const VIEWPORT = { width: 1366, height: 768 };

// Phase 1 -- anonymous. This smoke used to open the panel with no session and click
// "Pro Mode" directly, which the product deliberately refuses: mission68 asserts that
// "anonymous and non-premium users cannot enter Pro mode". The script predated the
// access-control work and had simply never been re-run. Rather than drop the anonymous
// path, it now asserts the refusal, and premium work moves to a real session below.
const browser = await chromium.launch({ headless: true });
const anonymousContext = await browser.newContext({ viewport: VIEWPORT });
const anonymousPage = await anonymousContext.newPage();
const anonymousEvidence = {};
try {
  await anonymousPage.goto(`${baseUrl}/panel/F`, { waitUntil: "domcontentloaded", timeout: 45_000 });
  await anonymousPage.locator("main").waitFor({ timeout: 30_000 });
  const toggle = anonymousPage.locator(".snbr-mode-toggle").first();
  await toggle.waitFor({ timeout: 20_000 });
  anonymousEvidence.aria_disabled = await toggle.getAttribute("aria-disabled");
  anonymousEvidence.aria_pressed_before = await toggle.getAttribute("aria-pressed");
  assert(anonymousEvidence.aria_disabled === "true", "Pro Mode deve estar bloqueado para anonimo (aria-disabled)");
  assert(anonymousEvidence.aria_pressed_before !== "true", "Pro Mode nao pode estar ativo para anonimo");
  // A refused control must survive being clicked. force:true bypasses actionability so
  // this asserts the product's guard rather than Playwright's own precondition check.
  await toggle.click({ force: true, timeout: 5_000 }).catch(() => undefined);
  await anonymousPage.waitForTimeout(500);
  anonymousEvidence.aria_pressed_after = await toggle.getAttribute("aria-pressed");
  assert(anonymousEvidence.aria_pressed_after !== "true", "clique nao pode conceder Pro Mode a anonimo");
  const anonymousText = (await anonymousPage.locator("body").innerText()).replace(/\s+/g, " ").trim();
  assert(!/Leituras da IA|AI Reads/i.test(anonymousText), "anonimo nao pode ver conteudo premium de IA");
  anonymousEvidence.ok = true;
} finally {
  await anonymousContext.close();
}

// Phase 2 -- authenticated premium through the canonical ephemeral session: a
// server-issued, TTL-bounded token delivered as the HTTP-only `snb_session` cookie. No
// password, no hardcoded JWT, and the row is revoked in the finally block below.
const sessionBaseline = countSessions();
const ephemeralSession = generateEphemeralSession();
const context = await browser.newContext({ viewport: VIEWPORT });
await applyEphemeralAuth(context, ephemeralSession.token);
const page = await context.newPage();
const consoleErrors = [];
const pageErrors = [];
page.on("console", (message) => {
  if (message.type() === "error") consoleErrors.push(message.text());
});
page.on("pageerror", (error) => pageErrors.push(error.stack || error.message));

const result = {
  baseUrl,
  tickers: [],
  aiTabs: [],
  screenshots: [],
  consoleErrors,
  pageErrors,
};

try {
  await page.goto(`${baseUrl}/panel/F`, { waitUntil: "domcontentloaded", timeout: 45_000 });
  await waitForPanel(page);

  const localeSwitch = page.locator(".snbr-locale-switch");
  await localeSwitch.getByRole("button", { name: /^BR$/i }).click();
  let text = await pageText(page);
  assert(/Gr[aá]fico IA\s*\/\s*Rede Social/i.test(text), "top tab BR deve mostrar Grafico IA / Rede Social");
  assert(!/\bWIN[FGHJKMNQUVXZ]?\d{0,2}\b/.test(text) && !/\bWDO[FGHJKMNQUVXZ]?\d{0,2}\b/.test(text), "lista B3 não deve exibir futuros WIN/WDO");
  assert(!/\b(NQ|MES|MYM)\b/.test(text), "lista USA não deve exibir futuros CME");

  const lightShot = path.join(runtimeDir, "panel-F-light.png");
  await page.screenshot({ path: lightShot, fullPage: true });
  result.screenshots.push(lightShot);

  await page.locator(".snbr-theme-toggle").click();
  await page.waitForTimeout(300);
  const darkShot = path.join(runtimeDir, "panel-F-dark.png");
  await page.screenshot({ path: darkShot, fullPage: true });
  result.screenshots.push(darkShot);
  await page.locator(".snbr-theme-toggle").click();

  await localeSwitch.getByRole("button", { name: /^USA$/i }).click();
  text = await pageText(page);
  assert(text.includes("AI Chart / Social"), "USA deve traduzir top tab IA Grafico");
  assert(!text.includes("International account: USA subscription"), "USA nao deve mostrar aviso de preco internacional no web");
  assert(!text.includes("$49/month") && !text.includes("$500 upfront"), "USA nao deve expor precos fixos no web");
  assert(text.includes("Asset Search") && text.includes("My Active List"), "USA deve traduzir rail e lista ativa");

  const forbiddenUsShellTerms = [
    "Painel do ativo",
    "ativo",
    "ativos",
    "Preço",
    "sem preço",
    "Leituras da IA",
    "Score IA",
    "Leitura principal",
    "Invalidação",
    "Métricas da lente",
    "Liberar Tela",
    "Sobre a empresa",
    "Descrição do produto",
    "Educação financeira",
    "Aviso legal",
    "Termos de uso",
    "Política de privacidade",
    "Contato / empresa",
    "Abrir",
    "Excluir",
    "Para trader:",
    "Ajuda",
    "Gráfico",
    "tendência semanal",
    "tendência",
    "Sem discussões",
    "LEITURA ATUAL",
    "DIRECAO OPERACIONAL",
    "CONFIRMACAO NECESSARIA",
    "INVALIDACAO",
    "RISCO",
    "buydor",
    "buydora",
    "posicao",
    "baixo",
    "médio",
    "medio",
    "alto:",
    "filtros principais",
    "Observar;",
    "sem ordem operacional",
    "Virada de",
    "confirmacao",
    "Ignorar se",
    "antes de virar",
  ];
  for (const term of forbiddenUsShellTerms) {
    assert(!text.includes(term), `USA nao deve mostrar texto PT no shell: ${term}`);
  }

  if ((await page.getByRole("tab", { name: /Fluxo IA|Flow AI/i }).count()) === 0) {
    // Entitlement-driven: the authority restores Pro from the stored preference, so this
    // never forces a control the product would refuse.
    await enableProMode(page);
  }
  await page.waitForTimeout(400);
  await page.getByRole("tab", { name: /Flow AI/i }).click();
  const settledFlowText = await waitForSettledAiPanel(page);
  text = `${await pageText(page)} ${settledFlowText}`;
  assert(
    (text.includes("Asset Panel") && text.includes("AI Reads"))
      || HONEST_EMPTY_AI_STATE.test(text)
      || (text.includes("0 current events for this asset") && text.includes("Waiting for a new read")),
    `USA deve traduzir painel de IA -- painel: "${(await page.locator("#panel-flow").innerText().catch(() => "<no #panel-flow>")).replace(/\s+/g, " ").trim().slice(0, 700)}"`,
  );
  assert(!text.includes("Painel do ativo") && !text.includes("Leituras da IA"), "USA nao deve manter labels PT na aba IA");

  await page.getByRole("tab", { name: /Help/i }).click();
  await page.waitForTimeout(700);
  text = await pageText(page);
  assert(text.includes("Trader Educational Help") && text.includes("About the Company"), "USA deve traduzir Ajuda institucional");
  assert(!text.includes("Sobre a empresa") && !text.includes("Descrição do produto"), "USA nao deve manter Ajuda institucional em PT");

  await page.getByRole("tab", { name: /AI Chart \/ Social/i }).click();
  await page.waitForTimeout(500);
  const usaShot = path.join(runtimeDir, "panel-F-usa.png");
  await page.screenshot({ path: usaShot, fullPage: true });
  result.screenshots.push(usaShot);

  await page.goto(`${baseUrl}/panel/PETR4`, { waitUntil: "domcontentloaded", timeout: 45_000 });
  await waitForPanel(page);
  await page.waitForTimeout(700);
  text = await pageText(page);
  assert(text.includes("AI Chart / Social") && text.includes("Asset Search"), "PETR4 em USA deve permanecer em ingles");
  for (const term of forbiddenUsShellTerms) {
    assert(!text.includes(term), `PETR4 USA nao deve mostrar texto PT no shell/news/poll/social: ${term}`);
  }

  await localeSwitch.getByRole("button", { name: /^BR$/i }).click();

  for (const ticker of tickers) {
    await page.goto(`${baseUrl}/panel/${encodeURIComponent(ticker)}`, { waitUntil: "domcontentloaded", timeout: 45_000 });
    await waitForPanel(page);
    text = await pageText(page);
    assert(text.includes(ticker), `painel deve carregar ticker ${ticker}`);
    result.tickers.push({ ticker, ok: true });
  }

  await page.goto(`${baseUrl}/panel/F`, { waitUntil: "domcontentloaded", timeout: 45_000 });
  await waitForPanel(page);
  const helpMenu = page.locator(".snbr-left-footer");
  assert(await helpMenu.getByText("Ajuda Educacional para o Trader", { exact: true }).count(), "rail must show the educational help title");
  assert(
    JSON.stringify(await helpMenu.locator("button").allTextContents()) === JSON.stringify(helpSections.map((section) => section.label)),
    "rail must show the nine help sections in order",
  );
  for (const section of helpSections) {
    await helpMenu.getByRole("button", { name: section.label, exact: true }).click();
    await page.locator(`#${section.id}`).waitFor({ state: "visible", timeout: 10_000 });
    assert(await page.locator(`#${section.id} h4`).getByText(section.title, { exact: false }).count(), `${section.label} must open its matching section`);
  }
  const petrButton = page.getByRole("button", { name: /PETR4/ }).first();
  await petrButton.click();
  await page.waitForTimeout(900);
  text = await pageText(page);
  assert(text.includes("PETR4"), "troca de ticker via UI deve carregar PETR4");
  if ((await page.getByRole("tab", { name: /Fluxo IA|Flow AI/i }).count()) === 0) {
    await enableProMode(page);
  }

  const tabTexts = new Map();
  for (const tab of aiTabs) {
    await page.getByRole("tab", { name: tab.name }).click();
    // Shares the settle helper rather than an inline 10 s wait. The panel's terminal state
    // is gated by the backend's own hydration deadline (_WORKER_TIMEOUT_SECONDS = 12 s), so
    // a 10 s budget could never observe it -- the same shape of defect as a client timing
    // out before the server's inner timeout. A panel that never settles still fails below.
    const settledText = await waitForSettledAiPanel(page, tab.id);
    const normalized = settledText
      || (await page.locator(`#panel-${tab.id}`).innerText({ timeout: 10_000 })).replace(/\s+/g, " ").trim();
    if (
      HONEST_EMPTY_AI_STATE.test(normalized)
      || (/0 (?:current events|eventos atuais)/i.test(normalized) && /Waiting for a new read|Aguardando nova leitura/i.test(normalized))
    ) {
      result.aiTabs.push({ id: tab.id, ok: true, status: "no_operational_findings" });
      continue;
    }
    assert(/Encontrado:|Found:/i.test(normalized), `${tab.id} precisa exibir horario real -- painel: "${normalized.slice(0, 1200)}"`);
    assert(/Score/i.test(normalized), `${tab.id} precisa exibir Score`);
    assert(/Trigger/i.test(normalized), `${tab.id} precisa exibir Trigger`);
    assert(/Invalid|Invalida/i.test(normalized), `${tab.id} precisa exibir invalidacao`);
    tabTexts.set(tab.id, normalized.slice(0, 1200));
    result.aiTabs.push({ id: tab.id, ok: true });
  }

  const uniqueTabBodies = new Set(tabTexts.values());
  if (tabTexts.size >= 4) {
    assert(uniqueTabBodies.size >= Math.max(3, tabTexts.size - 1), "abas IA parecem clonadas demais no smoke");
  }

  assert(
    !pageErrors.some((message) => message.includes('"[object Object]" is not valid JSON')),
    "TradingView nao deve gerar PAGEERROR de studies_overrides",
  );

  result.anonymousPhase = anonymousEvidence;
  const jsonPath = path.join(runtimeDir, "smoke-etapa7-result.json");
  fs.writeFileSync(jsonPath, JSON.stringify(result, null, 2), "utf-8");
  console.log(JSON.stringify({ ok: true, result: jsonPath, screenshots: result.screenshots }, null, 2));
} finally {
  await browser.close();
  const sessionRowsRemaining = revokeEphemeralSession(ephemeralSession.sid);
  const sessionDelta = countSessions() - sessionBaseline;
  if (sessionRowsRemaining !== 0 || sessionDelta !== 0) {
    throw new Error(
      `smoke deixou sessao residual: remaining=${sessionRowsRemaining} delta=${sessionDelta}`,
    );
  }
}
