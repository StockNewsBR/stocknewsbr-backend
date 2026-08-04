import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(scriptDir, "..");
const repoRoot = path.resolve(root, "..", "..");

function read(relativePath) {
  return fs.readFileSync(path.join(repoRoot, relativePath), "utf8");
}

// Checks are counted, not hard-coded, so the reported total can never drift away
// from what actually ran. `trackCheck` also refuses a second assertion with the
// same (source, kind, needle) triple: such a check cannot fail on its own -- its
// twin always fails first -- so it inflates the count without adding coverage.
let checkCount = 0;
const seenChecks = new Map();

function trackCheck(source, needle, label, kind) {
  checkCount += 1;

  let seen = seenChecks.get(source);

  if (!seen) {
    seen = new Set();
    seenChecks.set(source, seen);
  }

  const key = `${kind}:${needle}`;

  if (seen.has(key)) {
    throw new Error(`Mission 28B inert check: "${label}" repeats an earlier assertion on the same source and can never fail independently`);
  }

  seen.add(key);
}

function assertIncludes(source, needle, label) {
  trackCheck(source, needle, label, "includes");

  if (!source.includes(needle)) {
    throw new Error(`Mission 28B missing: ${label}`);
  }
}

function assertNotIncludes(source, needle, label) {
  trackCheck(source, needle, label, "excludes");

  if (source.includes(needle)) {
    throw new Error(`Mission 28B regression: ${label}`);
  }
}

function countOccurrences(source, needle) {
  let total = 0;
  let index = source.indexOf(needle);
  while (index !== -1) {
    total += 1;
    index = source.indexOf(needle, index + needle.length);
  }
  return total;
}

// "Present" is a weaker claim than "present exactly once". Duplicate panes and duplicate
// colour authorities are precisely the regressions this mission has to catch, and
// includes() cannot see them.
function assertCountEquals(source, needle, expected, label) {
  trackCheck(source, needle, label, `count=${expected}`);

  const actual = countOccurrences(source, needle);
  if (actual !== expected) {
    throw new Error(`Mission 28B regression: ${label} (expected ${expected}, found ${actual})`);
  }
}

const workspaceShell = read("apps/web/components/workspace-shell.tsx");
const tickerChart = read("apps/web/components/ticker-chart.tsx");
const workspaceSections = read("apps/web/components/workspace-sections.tsx");
const workspaceRails = read("apps/web/components/workspace-rails.tsx");
const appLayout = read("apps/web/app/layout.tsx");
const css = read("apps/web/app/globals.css");
const types = read("apps/web/lib/types.ts");
const scoreDisplay = read("app/services/score_display.py");
const explainability = read("app/system/explainability.py");
const ranking = read("app/services/ranking.py");
const snapshotContract = read("app/services/snapshot_contract.py");
const allWebSources = [workspaceShell, tickerChart, workspaceSections, workspaceRails, appLayout, css, types].join("\n");

for (const label of ["Fluxo IA", "Liquidez IA", "Tendência IA", "Momento IA", "Risco IA", "Notícias IA"]) {
  assertIncludes(workspaceShell, label, `Portuguese label ${label}`);
}
for (const oldLabel of ["Flow IA", "Liquidity IA", "Trend IA", "Momentum IA", "Risk IA", "News IA"]) {
  assertNotIncludes(workspaceShell, oldLabel, `old mixed Portuguese/English label ${oldLabel}`);
}

assertIncludes(workspaceShell, "Disponível no Pro", "Basic Mode protects premium indicator values");
assertIncludes(workspaceShell, "displayStats", "Basic Mode uses protected display stats");
assertIncludes(workspaceShell, "snbr-basic-pro-lock", "Basic Mode keeps the asset identity header while locking premium metrics");
assertIncludes(workspaceShell, "<div className=\"snbr-price-line\">", "Basic Mode keeps public price/change visible in the symbol header");
assertIncludes(workspaceShell, "selectedTickerMarketLabel", "asset header keeps the market/category identity visible");
assertIncludes(workspaceShell, "activeWatchCount={activeWatchCountForFilter}", "active list counter uses the selected filter count");
assertIncludes(workspaceShell, "CATEGORY_ORDER.reduce((total, category)", "Todos counter aggregates B3 + BDR + Crypto + USA explicitly");
assertIncludes(workspaceRails, "activeCountLabel", "left rail shows the active filter name next to its count");

assertIncludes(workspaceShell, "RSI VISÃO", "RSI score is explicit in the top card");
assertIncludes(tickerChart, "aria-hidden={!showRsi}", "institutional RSI panel hides via show_rsi without unmounting chart overlays");
assertIncludes(css, ".snbr-institutional-rsi-panel.hidden", "RSI panel has a CSS off state instead of being unmounted");
assertIncludes(workspaceShell, "resolveCanonicalChartLevelZones", "support/resistance uses canonical chart zones");
assertIncludes(workspaceShell, "supportLevel={chartSupportResistanceLevels.support}", "support overlay consumes canonical support value");
assertIncludes(workspaceShell, "resistanceLevel={chartSupportResistanceLevels.resistance}", "resistance overlay consumes canonical resistance value");
assertNotIncludes(tickerChart, '<div className="snbr-chart-top-overlays"', "RSI/support/resistance badges are not rendered over chart");
// --- MISSION28B_CONTRACT_MIGRATION -------------------------------------------------
// Replaced: assertNotIncludes(tickerChart, "<LevelLinesPane", "verified support/resistance
// pane is not rendered").
//
// That assertion and the H2 overlay contract cannot both hold: H2 requires the verified
// level pane to render with real support/resistance, and the old check required it to be
// absent. The old one is the obsolete side -- note that the two assertions immediately
// above already require supportLevel/resistanceLevel to be wired into the chart, so this
// mission never objected to the levels existing, only to where they were drawn. The
// negative check is therefore replaced, not deleted, by a stronger positive contract that
// pins down identity, uniqueness, gating and provenance.
assertIncludes(tickerChart, "function LevelLinesPane({", "verified level pane component exists");
assertIncludes(tickerChart, "<LevelLinesPane", "verified level pane is actually rendered");
assertCountEquals(tickerChart, "<LevelLinesPane", 1, "verified level pane is mounted exactly once");
assertCountEquals(tickerChart, 'className="snbr-chart-level-lines"', 1, "exactly one level pane element exists (no duplicate pane)");
assertIncludes(tickerChart, "{showLevelPane ? (", "level pane render is gated, never unconditional");
assertIncludes(tickerChart, "const showLevelPane = hasPaneScale && levelOverlays.length > 0", "level pane stays hidden when there is no real price scale or no overlay");
assertIncludes(tickerChart, "closes={paneCloses}", "level pane plots real closes rather than literals");
assertIncludes(tickerChart, "overlays={levelOverlays}", "level pane consumes derived overlays rather than literals");
assertIncludes(tickerChart, 'data-level-symbol={levelMetadata?.symbol || ""}', "level pane publishes the symbol it belongs to");
assertIncludes(tickerChart, 'data-level-timeframe={levelMetadata?.timeframe || ""}', "level pane publishes its timeframe");
assertIncludes(tickerChart, "const support = firstFiniteNumber(input.supportLevel)", "support overlay requires a finite number");
assertIncludes(tickerChart, "const resistance = firstFiniteNumber(input.resistanceLevel)", "resistance overlay requires a finite number");
assertIncludes(tickerChart, 'const VWAP_COLOR = "#f59e0b"', "VWAP keeps the canonical colour");
assertCountEquals(tickerChart, '"#f59e0b"', 1, "VWAP colour has exactly one authority in the chart component");
assertIncludes(tickerChart, '"volume weighted average price.vwap.linewidth": 4', "VWAP keeps linewidth 4 on the long study id");
assertIncludes(tickerChart, '"vwap.vwap.linewidth": 4', "VWAP keeps linewidth 4 on the short study id");
assertNotIncludes(workspaceShell, '{ key: "show_support"', "support toggle is not rendered");
assertNotIncludes(workspaceShell, '{ key: "show_resistance"', "resistance toggle is not rendered");
assertNotIncludes(workspaceShell, '<div className="snbr-timeframes">', "duplicate timeframe row below RSI is not rendered");
assertNotIncludes(tickerChart, "RSI@tv-basicstudies", "TradingView RSI stays removed");
assertNotIncludes(tickerChart, "RSI 14 close", "TradingView RSI legend stays removed");
assertNotIncludes(tickerChart, "snbr-chart-level-line ${level.key}`}>\n                <span>", "support/resistance lines do not repeat labels");
assertNotIncludes(css, ".snbr-chart-level-line span", "support/resistance line label CSS removed");

assertIncludes(workspaceShell, '<div className="snbr-sticky-top">', "tabs and ticker tape share one sticky wrapper");
assertIncludes(css, ".snbr-sticky-top {", "sticky header class exists");
assertIncludes(css, "position: sticky;\n  top: 0;\n  z-index: 30;", "sticky header keeps the real top without spacer");
// The previous check here pinned `.snbr-symbol-page`'s grid-template-rows, which
// belongs to the main content area, not the left rail -- it could never catch a
// regression in the active list. The real container contract is the shell being a
// column flex box that can shrink (min-height: 0) and clip (overflow: hidden), so
// the scroll child below owns the overflow instead of pushing the rail open.
// Whether the inner list scrolls *independently* of the rail is a rendered
// behaviour and is verified by the browser suites, not by this static check.
assertIncludes(css, ".snbr-active-list-shell {\n  display: flex;\n  flex-direction: column;", "active list shell is a column flex container");
assertIncludes(css, "  min-height: 0;\n  height: 100%;\n  flex: 1 1 auto;\n  overflow: hidden;\n}", "active list shell can shrink and clips its own overflow");
assertIncludes(css, ".snbr-active-list-scroll {\n  flex: 1 1 auto;\n  min-height: 0;\n  height: 100%;\n  max-height: none;", "active list owns its internal scroll height");
assertIncludes(workspaceShell, 'return normalizeSymbol(label) === symbol', "watchlist suppresses a duplicated symbol label");
assertIncludes(workspaceShell, '{itemLabel ? <span>{itemLabel}</span> : null}', "watchlist second line only renders a canonical name");
assertIncludes(workspaceShell, '{symbolLabel ? <p>{symbolLabel}</p> : null}', "asset header second line only renders a canonical name");
assertNotIncludes(workspaceShell, 'label: isUsLocale ? "Price" : "Preço"', "separate current-price card is not rendered");
assertIncludes(css, "font-size: clamp(30px, 2.4vw, 38px);", "main price uses the reduced responsive size");
assertIncludes(workspaceShell, 'advancedMode\n                ? (isUsLocale ? "Basic Mode" : "Modo Básico")', "Pro mode button offers Basic mode");
assertIncludes(workspaceShell, 'const SIMPLE_TOP_TAB_IDS = new Set([\n  "grafico",\n  // "stockflow" is Pro/Trial-only: excluded from Modo Básico (shown only when advancedMode).\n  "news",\n  "referrals",\n  "education",\n]);', "Basic mode keeps only chart/social, news, referrals and trader help tabs");
assertIncludes(workspaceShell, 'setActiveTab("grafico")', "invalid Pro tab safely returns to chart in Basic mode");

assertNotIncludes(workspaceShell, "Card usa volume do quote/snapshot", "old volume snapshot explanation removed");
assertNotIncludes(workspaceShell, "RSI do painel: indicador institucional do snapshot/ranking", "old RSI snapshot explanation removed");

assertIncludes(workspaceShell, "resolveAiFindingTimestamp", "AI detection timestamp is resolved separately");
assertIncludes(workspaceShell, "isUsLocale ? \"Detected\" : \"Detectado\"", "AI detection time has bilingual label");
assertIncludes(workspaceShell, "Publicado às", "AI publication time can be shown separately");
assertIncludes(workspaceSections, "Publicado às", "news publication time is explicit");
assertIncludes(workspaceSections, "Fonte", "news source is explicit");
assertIncludes(workspaceSections, "Sentimento", "news sentiment is explicit");
assertIncludes(workspaceSections, "Sem notícia para", "news area has explicit ticker-safe empty-state fallback");
assertIncludes(workspaceShell, "Nenhuma análise de notícia disponível para este ativo no momento.", "news AI area has explicit empty-state fallback");
assertIncludes(workspaceShell, "Sem leitura disponível para este ativo no momento.", "AI tool tabs have explicit empty-state fallback");
assertIncludes(workspaceShell, "Nenhum achado desta IA para este ativo agora.", "AI zero counter state explains no asset finding");
assertIncludes(workspaceShell, "IA temporariamente sem dados.", "AI empty payload state is explicit");
assertIncludes(workspaceSections, "Alta", "news bullish sentiment is localized in PT-BR");
assertIncludes(workspaceSections, "Neutra", "news neutral sentiment exists");
assertIncludes(workspaceSections, "Baixa", "news bearish sentiment is localized in PT-BR");
assertIncludes(types, "sentiment?: string | null", "news sentiment is typed");

const helpMenuLabels = [
  "1️⃣ Sobre a Empresa",
  "2️⃣ Principais Módulos da Plataforma",
  "3️⃣ Glossário: Painel de Análise Estratégica",
  "4️⃣ Glossário: Gráfico do Ativo",
  "5️⃣ Glossário: Modos de Uso da Plataforma",
  "6️⃣ Guia Rápido StockNewsBR",
  "7️⃣ Plataforma Web Trader Desk",
  "8️⃣ Aviso legal",
  "9️⃣ Por que escolher StockNewsBR?",
];
const helpSectionIds = [
  "sobre-a-empresa",
  "principais-modulos",
  "glossario-painel-estrategico",
  "glossario-grafico-ativo",
  "glossario-modos-plataforma",
  "guia-rapido-stocknewsbr",
  "plataforma-web-trader-desk",
  "aviso-legal",
  "por-que-stocknewsbr",
];
let previousHelpLabelIndex = -1;
for (const label of helpMenuLabels) {
  const index = workspaceShell.indexOf(label);
  if (index <= previousHelpLabelIndex) throw new Error(`Mission 28B help menu order regression: ${label}`);
  previousHelpLabelIndex = index;
}
for (const id of helpSectionIds) assertIncludes(workspaceShell, `id: "${id}"`, `help section id ${id}`);
assertIncludes(workspaceShell, "Ajuda Educacional para o Trader", "help panel uses its educational title");
assertIncludes(workspaceRails, "institutionalSections.map", "left rail shows every help menu item");
assertNotIncludes(workspaceRails, "slice(0, 8)", "left rail is no longer limited to eight help items");
assertIncludes(workspaceSections, "<article id={section.id}", "selected help section keeps its anchor");
assertIncludes(workspaceShell, "openInstitutionalSection(sectionId: string)", "help buttons retain their shared open handler");
for (const obsolete of ["filosofia-oficial", "institucional-produto", "institucional-educacao", "FILOSOFIA OFICIAL", "Descrição do produto", "Educação financeira", "Ajuda ao Trader"]) {
  assertNotIncludes(workspaceShell, obsolete, `obsolete help reference ${obsolete}`);
}

assertIncludes(scoreDisplay, "numeric > 10", "score display normalizes raw values above 10");
assertIncludes(scoreDisplay, "master_score_raw", "score display preserves raw score separately");
assertIncludes(scoreDisplay, "numeric < 0", "score display clamps negative values");
assertIncludes(scoreDisplay, "logger.warning", "score display logs internal warning");
assertIncludes(workspaceShell, "normalizeMasterScoreForDisplay", "frontend normalizes score display");
assertIncludes(workspaceShell, "Score Mestre bruto normalizado para escala 0..10", "frontend logs raw score normalization warning");
assertIncludes(explainability, "master_score_display", "explainability exposes display-safe score");
assertIncludes(ranking, "master_score_display", "ranking exposes display-safe score");
assertIncludes(snapshotContract, "master_score_display", "snapshot contract exposes display-safe score");

for (const forbidden of ["Bullish\" : \"Bullish", "Bearish\" : \"Bearish", "News IA", "Flow IA", "Risk IA", "Inteligencia", "Notificacao", "Preferencias", "versoes", "ambigua"]) {
  assertNotIncludes(allWebSources, forbidden, `forbidden PT-BR visible string ${forbidden}`);
}

assertNotIncludes(allWebSources, "toggle do gráfico mostra RSI do TradingView", "old Portuguese TradingView RSI text absent");
assertNotIncludes(allWebSources, "chart toggle shows TradingView RSI", "old English TradingView RSI text absent");

console.log(JSON.stringify({ ok: true, mission: "28B.2", checks: checkCount }, null, 2));
