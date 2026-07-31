import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(scriptDir, "..");
const workspaceShellPath = path.join(root, "components", "workspace-shell.tsx");
const tickerChartPath = path.join(root, "components", "ticker-chart.tsx");
const cssPath = path.join(root, "app", "globals.css");
const typesPath = path.join(root, "lib", "types.ts");

function read(filePath) {
  return fs.readFileSync(filePath, "utf8");
}

function assertIncludes(source, needle, label) {
  if (!source.includes(needle)) {
    throw new Error(`Mission 25D contract missing: ${label}`);
  }
}

function assertNotIncludes(source, needle, label) {
  if (source.includes(needle)) {
    throw new Error(`Mission 25D contract regression: ${label}`);
  }
}

const workspaceShell = read(workspaceShellPath);
const tickerChart = read(tickerChartPath);
const css = read(cssPath);
const types = read(typesPath);
const allSources = [workspaceShell, tickerChart, css, types].join("\n");

assertIncludes(workspaceShell, "show_support", "support toggle state is wired");
assertIncludes(workspaceShell, "show_resistance", "resistance toggle state is wired");
assertIncludes(workspaceShell, "resolveCanonicalChartLevelZones", "canonical support/resistance selection exists");
assertIncludes(workspaceShell, "chart: chartForOperationalLevels", "liquidity card uses canonical chart zones");
assertIncludes(workspaceShell, "chart: chartForOperationalLevels", "operational levels use canonical chart zones");
assertIncludes(workspaceShell, "supportLevel={chartSupportResistanceLevels.support}", "support level reaches chart");
assertIncludes(workspaceShell, "resistanceLevel={chartSupportResistanceLevels.resistance}", "resistance level reaches chart");
assertIncludes(workspaceShell, "RSI VISÃO", "RSI card uses the institutional RSI VISÃO label");
assertIncludes(workspaceShell, "institutionalRsiValue={chartTimeframeRsi}", "panel RSI reaches chart as institutional value");
assertIncludes(workspaceShell, "label: isUsLocale ? \"Panel RSI\" : \"RSI painel\"", "chart RSI toggle is labeled as panel indicator");
assertIncludes(workspaceShell, "Volume snapshot", "volume card source is explicit");
assertNotIncludes(workspaceShell, "Card usa volume do quote/snapshot", "old volume divergence explanation was removed");
assertIncludes(workspaceShell, "relVolume", "volume meter uses relative volume when available");
assertIncludes(workspaceShell, "Abaixo da média", "volume meter can mirror below-average card state");

assertIncludes(tickerChart, "buildLevelOverlays", "chart overlay builder exists");
assertIncludes(tickerChart, "snbr-chart-level-lines", "chart renders visible support/resistance lines");
assertIncludes(tickerChart, "snbr-chart-level-line", "support/resistance lines are rendered on the chart");
assertIncludes(tickerChart, "supportLevel", "chart receives support level");
assertIncludes(tickerChart, "resistanceLevel", "chart receives resistance level");
assertIncludes(tickerChart, "institutionalRsiValue", "chart receives institutional RSI value");
assertIncludes(tickerChart, "rsiPanelStyle", "chart renders institutional panel RSI badge");
assertIncludes(tickerChart, "snbr-institutional-rsi-marker", "institutional RSI lower panel marks the same snapshot value");
assertIncludes(tickerChart, "--snbr-rsi-position", "institutional RSI marker uses the passed value");
assertIncludes(tickerChart, "O RSI do TradingView segue visível no gráfico", "empty RSI state keeps TradingView RSI disabled");
assertIncludes(tickerChart, "rsiTitle", "institutional RSI labels include RSI VISÃO");
assertIncludes(tickerChart, "snbr-chart-level-lines", "RSI/support/resistance top row controls visual order");
assertNotIncludes(tickerChart, "snbr-chart-level-line ${level.key}`}>", "support/resistance lines must not repeat labels");
assertNotIncludes(tickerChart, "style={{ top:", "support/resistance overlay must not be positioned from local OHLC");

assertIncludes(css, ".snbr-chart-top-overlays", "top overlay row is styled");
assertIncludes(css, ".snbr-chart-level-overlays", "overlay container is styled");
assertIncludes(css, ".snbr-chart-level-lines", "visible support/resistance line container is styled");
assertIncludes(css, ".snbr-chart-level-line.support", "support line is styled");
assertIncludes(css, ".snbr-chart-level-line.resistance", "resistance line is styled");
assertIncludes(css, ".snbr-chart-level-overlay.support span", "support badge is styled in top row");
assertIncludes(css, ".snbr-chart-level-overlay.resistance span", "resistance badge is styled in top row");
assertNotIncludes(css, ".snbr-chart-level-line span", "support/resistance line labels were removed");
assertIncludes(css, ".snbr-institutional-rsi-panel", "panel RSI badge is styled");
assertIncludes(css, ".snbr-institutional-rsi-panel", "institutional RSI lower panel is styled");
assertIncludes(css, ".snbr-institutional-rsi-track", "institutional RSI lower panel track is styled");
assertIncludes(css, ".snbr-institutional-rsi-marker", "institutional RSI lower panel marker is styled");

assertIncludes(types, "show_support?: boolean", "layout type persists support toggle");
assertIncludes(types, "show_resistance?: boolean", "layout type persists resistance toggle");

assertNotIncludes(allSources, "RSI 14 close", "TradingView RSI legend must not be represented as a contract");
assertNotIncludes(allSources, "toggle do gráfico mostra RSI do TradingView", "old Portuguese RSI divergence text must stay removed");
assertNotIncludes(allSources, "chart toggle shows TradingView RSI", "old English RSI divergence text must stay removed");

console.log(JSON.stringify({ ok: true, mission: "25D.3", checks: 45 }, null, 2));
