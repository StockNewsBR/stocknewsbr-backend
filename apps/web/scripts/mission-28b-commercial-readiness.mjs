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
    throw new Error(`Mission 28B missing: ${label}`);
  }
}

function assertNotIncludes(source, needle, label) {
  if (source.includes(needle)) {
    throw new Error(`Mission 28B regression: ${label}`);
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

assertIncludes(workspaceShell, "Disponível no Plano Pro", "Basic Mode protects premium indicator values");
assertIncludes(workspaceShell, "displayStats", "Basic Mode uses protected display stats");
assertIncludes(workspaceShell, "snbr-basic-pro-lock", "Basic Mode keeps the asset identity header while locking premium metrics");
assertIncludes(workspaceShell, "<div className=\"snbr-price-line\">", "Basic Mode keeps public price/change visible in the symbol header");
assertIncludes(workspaceShell, "selectedTickerMarketLabel", "asset header keeps the market/category identity visible");
assertIncludes(workspaceShell, "activeWatchCount={activeWatchCountForFilter}", "active list counter uses the selected filter count");
assertIncludes(workspaceShell, "CATEGORY_ORDER.reduce((total, category)", "Todos counter aggregates B3 + BDR + Crypto + USA explicitly");
assertIncludes(workspaceRails, "activeCountLabel", "left rail shows the active filter name next to its count");

assertIncludes(workspaceShell, "RSI SCORE", "RSI score is explicit in the top card");
assertIncludes(tickerChart, "aria-hidden={!showRsi}", "institutional RSI panel can hide without unmounting chart overlays");
assertIncludes(css, ".snbr-institutional-rsi-panel.hidden", "RSI panel keeps reserved layout space when toggled off");
assertIncludes(workspaceShell, "resolveCanonicalChartLevelZones", "support/resistance uses canonical chart zones");
assertIncludes(workspaceShell, "supportLevel={chartSupportResistanceLevels.support}", "support overlay consumes canonical support value");
assertIncludes(workspaceShell, "resistanceLevel={chartSupportResistanceLevels.resistance}", "resistance overlay consumes canonical resistance value");
assertNotIncludes(tickerChart, '<div className="snbr-chart-top-overlays"', "RSI/support/resistance badges are not rendered over chart");
assertNotIncludes(tickerChart, "<LevelLinesPane", "verified support/resistance pane is not rendered");
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
assertIncludes(css, "grid-template-rows: auto auto minmax(0, 1fr);", "active list consumes remaining rail height");
assertIncludes(css, ".snbr-active-list-scroll {\n  min-height: 0;\n  height: 100%;\n  max-height: none;", "active list owns its internal scroll height");
assertIncludes(workspaceShell, 'return normalizeSymbol(label) === symbol', "watchlist suppresses a duplicated symbol label");
assertIncludes(workspaceShell, '{itemLabel ? <span>{itemLabel}</span> : null}', "watchlist second line only renders a canonical name");
assertIncludes(workspaceShell, '{symbolLabel ? <p>{symbolLabel}</p> : null}', "asset header second line only renders a canonical name");
assertNotIncludes(workspaceShell, 'label: isUsLocale ? "Price" : "Preço"', "separate current-price card is not rendered");
assertIncludes(css, "font-size: clamp(30px, 2.4vw, 38px);", "main price uses the reduced responsive size");
assertIncludes(workspaceShell, 'advancedMode\n                ? (isUsLocale ? "Basic Mode" : "Modo Básico")', "Pro mode button offers Basic mode");
assertIncludes(workspaceShell, 'const SIMPLE_TOP_TAB_IDS = new Set([\n  "grafico",\n  "referrals",\n  "education",\n]);', "Basic mode keeps only chart/social, referrals and trader help tabs");
assertIncludes(workspaceShell, 'setActiveTab("grafico")', "invalid Pro tab safely returns to chart in Basic mode");

assertNotIncludes(workspaceShell, "Card usa volume do quote/snapshot", "old volume snapshot explanation removed");
assertNotIncludes(workspaceShell, "RSI do painel: indicador institucional do snapshot/ranking", "old RSI snapshot explanation removed");

assertIncludes(workspaceShell, "resolveAiFindingTimestamp", "AI detection timestamp is resolved separately");
assertIncludes(workspaceShell, "isUsLocale ? \"Detected\" : \"Detectado\"", "AI detection time has bilingual label");
assertIncludes(workspaceShell, "Publicado às", "AI publication time can be shown separately");
assertIncludes(workspaceShell, "isUsLocale ? \"Viewed\" : \"Visualizado\"", "AI viewed time has bilingual label");
assertIncludes(workspaceSections, "Publicado às", "news publication time is explicit");
assertIncludes(workspaceSections, "Fonte", "news source is explicit");
assertIncludes(workspaceSections, "Sentimento", "news sentiment is explicit");
assertIncludes(workspaceSections, "Sem notícias relevantes para este ativo agora. Tente atualizar mais tarde.", "news area has explicit ticker-safe empty-state fallback");
assertIncludes(workspaceShell, "Nenhuma análise de notícia disponível para este ativo no momento.", "news AI area has explicit empty-state fallback");
assertIncludes(workspaceShell, "Sem leitura disponível para este ativo no momento.", "AI tool tabs have explicit empty-state fallback");
assertIncludes(workspaceShell, "Nenhum achado desta IA para este ativo agora.", "AI zero counter state explains no asset finding");
assertIncludes(workspaceShell, "IA temporariamente sem dados.", "AI empty payload state is explicit");
assertIncludes(workspaceSections, "Alta", "news bullish sentiment is localized in PT-BR");
assertIncludes(workspaceSections, "Neutra", "news neutral sentiment exists");
assertIncludes(workspaceSections, "Baixa", "news bearish sentiment is localized in PT-BR");
assertIncludes(types, "sentiment?: string | null", "news sentiment is typed");

assertIncludes(workspaceShell, "FILOSOFIA OFICIAL", "official philosophy section is available in Trader Help");
assertIncludes(workspaceShell, "filosofia-oficial", "official philosophy has a navigable section id");

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

console.log(JSON.stringify({ ok: true, mission: "28B.2", checks: 68 }, null, 2));
