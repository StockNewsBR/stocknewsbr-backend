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
const css = read("apps/web/app/globals.css");
const types = read("apps/web/lib/types.ts");
const scoreDisplay = read("app/services/score_display.py");
const explainability = read("app/system/explainability.py");
const ranking = read("app/services/ranking.py");
const snapshotContract = read("app/services/snapshot_contract.py");
const allWebSources = [workspaceShell, tickerChart, workspaceSections, workspaceRails, css, types].join("\n");

for (const label of ["Fluxo IA", "Liquidez IA", "Tendência IA", "Momento IA", "Risco IA", "Notícias IA"]) {
  assertIncludes(workspaceShell, label, `Portuguese label ${label}`);
}
for (const oldLabel of ["Flow IA", "Liquidity IA", "Trend IA", "Momentum IA", "Risk IA", "News IA"]) {
  assertNotIncludes(workspaceShell, oldLabel, `old mixed Portuguese/English label ${oldLabel}`);
}

assertIncludes(workspaceShell, "Disponível no Plano Pro", "Basic Mode protects premium indicator values");
assertIncludes(workspaceShell, "displayStats", "Basic Mode uses protected display stats");
assertIncludes(workspaceShell, "activeWatchCount={activeWatchlist.length}", "active list counter uses all monitored categories");

assertIncludes(workspaceShell, "RSI SCORE", "RSI score is explicit in the top card");
assertIncludes(tickerChart, "RSI SCORE:", "RSI score is explicit in the chart badge and lower panel");
assertIncludes(tickerChart, "snbr-chart-top-overlays", "chart renders top row for RSI, support and resistance");
if (tickerChart.indexOf("snbr-chart-panel-rsi-badge") > tickerChart.indexOf("snbr-chart-level-overlays")) {
  throw new Error("Mission 28B regression: RSI SCORE must render before support/resistance chips");
}
assertNotIncludes(tickerChart, "RSI@tv-basicstudies", "TradingView RSI stays removed");
assertNotIncludes(tickerChart, "RSI 14 close", "TradingView RSI legend stays removed");
assertNotIncludes(tickerChart, "snbr-chart-level-line ${level.key}`}>\n                <span>", "support/resistance lines do not repeat labels");
assertNotIncludes(css, ".snbr-chart-level-line span", "support/resistance line label CSS removed");

assertNotIncludes(workspaceShell, "Card usa volume do quote/snapshot", "old volume snapshot explanation removed");
assertNotIncludes(workspaceShell, "RSI do painel: indicador institucional do snapshot/ranking", "old RSI snapshot explanation removed");

assertIncludes(workspaceShell, "Detectado às", "AI detection time is shown separately");
assertIncludes(workspaceShell, "Publicado às", "AI publication time can be shown separately");
assertIncludes(workspaceShell, "Visualizado às", "AI viewed time is explicit");
assertIncludes(workspaceSections, "Publicado às", "news publication time is explicit");
assertIncludes(workspaceSections, "Fonte", "news source is explicit");
assertIncludes(workspaceSections, "Sentimento", "news sentiment is explicit");
assertIncludes(workspaceSections, "Bullish", "news bullish sentiment exists");
assertIncludes(workspaceSections, "Neutra", "news neutral sentiment exists");
assertIncludes(workspaceSections, "Bearish", "news bearish sentiment exists");
assertIncludes(types, "sentiment?: string | null", "news sentiment is typed");

assertIncludes(workspaceShell, "FILOSOFIA OFICIAL", "official philosophy section is available in Trader Help");
assertIncludes(workspaceShell, "filosofia-oficial", "official philosophy has a navigable section id");

assertIncludes(scoreDisplay, "numeric > 10", "score display clamps values above 10");
assertIncludes(scoreDisplay, "numeric < 0", "score display clamps negative values");
assertIncludes(scoreDisplay, "logger.warning", "score display logs internal warning");
assertIncludes(workspaceShell, "normalizeMasterScoreForDisplay", "frontend normalizes score display");
assertIncludes(workspaceShell, "Score Mestre acima de 10 normalizado para display", "frontend logs display warning");
assertIncludes(explainability, "master_score_display", "explainability exposes display-safe score");
assertIncludes(ranking, "master_score_display", "ranking exposes display-safe score");
assertIncludes(snapshotContract, "master_score_display", "snapshot contract exposes display-safe score");

assertNotIncludes(allWebSources, "toggle do gráfico mostra RSI do TradingView", "old Portuguese TradingView RSI text absent");
assertNotIncludes(allWebSources, "chart toggle shows TradingView RSI", "old English TradingView RSI text absent");

console.log(JSON.stringify({ ok: true, mission: "28B", checks: 44 }, null, 2));
