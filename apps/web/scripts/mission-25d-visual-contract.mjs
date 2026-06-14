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
assertIncludes(workspaceShell, "resolveLiquidityTarget(chartForOperationalLevels", "liquidity card uses canonical chart zones");
assertIncludes(workspaceShell, "chart: chartForOperationalLevels", "operational levels use canonical chart zones");
assertIncludes(workspaceShell, "supportLevel={chartSupportResistanceLevels.support}", "support level reaches chart");
assertIncludes(workspaceShell, "resistanceLevel={chartSupportResistanceLevels.resistance}", "resistance level reaches chart");
assertIncludes(workspaceShell, "Snapshot RSI", "RSI card source is explicit in English");
assertIncludes(workspaceShell, "RSI snapshot", "RSI card source is explicit in Portuguese");
assertIncludes(workspaceShell, "RSI do painel: indicador institucional do snapshot/ranking", "RSI card source is institutional");
assertIncludes(workspaceShell, "O TradingView não calcula RSI separado", "TradingView RSI divergence is explicitly disabled");
assertIncludes(workspaceShell, "institutionalRsiValue={panelRsiValue}", "panel RSI reaches chart as institutional value");
assertIncludes(workspaceShell, "label: isUsLocale ? \"Panel RSI\" : \"RSI painel\"", "chart RSI toggle is labeled as panel indicator");
assertIncludes(workspaceShell, "Volume snapshot", "volume card source is explicit");
assertIncludes(workspaceShell, "Card usa volume do quote/snapshot", "volume divergence explanation is present");
assertIncludes(workspaceShell, "assetRelativeVolumeForMeter", "volume meter uses relative volume when available");
assertIncludes(workspaceShell, "Abaixo da média", "volume meter can mirror below-average card state");

assertIncludes(tickerChart, "buildLevelOverlays", "chart overlay builder exists");
assertIncludes(tickerChart, "snbr-chart-level-overlay", "chart renders support/resistance overlays");
assertIncludes(tickerChart, "snbr-chart-level-lines", "chart renders visible support/resistance lines");
assertIncludes(tickerChart, "snbr-chart-level-line", "support/resistance lines are rendered on the chart");
assertIncludes(tickerChart, "supportLevel", "chart receives support level");
assertIncludes(tickerChart, "resistanceLevel", "chart receives resistance level");
assertIncludes(tickerChart, "institutionalRsiValue", "chart receives institutional RSI value");
assertIncludes(tickerChart, "snbr-chart-panel-rsi-badge", "chart renders institutional panel RSI badge");
assertIncludes(tickerChart, "snbr-institutional-rsi-panel", "chart renders the institutional RSI lower panel");
assertIncludes(tickerChart, "snbr-institutional-rsi-marker", "institutional RSI lower panel marks the same snapshot value");
assertIncludes(tickerChart, "--snbr-rsi-position", "institutional RSI marker uses the passed value");
assertIncludes(tickerChart, "O RSI do TradingView continua desativado", "empty RSI state keeps TradingView RSI disabled");
assertNotIncludes(tickerChart, "RSI@tv-basicstudies", "TradingView RSI study must not be injected");
assertNotIncludes(tickerChart, "style={{ top:", "support/resistance overlay must not be positioned from local OHLC");

assertIncludes(css, ".snbr-chart-level-overlays", "overlay container is styled");
assertIncludes(css, ".snbr-chart-level-lines", "visible support/resistance line container is styled");
assertIncludes(css, ".snbr-chart-level-line.support", "support line is styled");
assertIncludes(css, ".snbr-chart-level-line.resistance", "resistance line is styled");
assertIncludes(css, ".snbr-chart-level-overlay.support span", "support badge is styled");
assertIncludes(css, ".snbr-chart-level-overlay.resistance span", "resistance badge is styled");
assertIncludes(css, ".snbr-chart-panel-rsi-badge", "panel RSI badge is styled");
assertIncludes(css, ".snbr-institutional-rsi-panel", "institutional RSI lower panel is styled");
assertIncludes(css, ".snbr-institutional-rsi-track", "institutional RSI lower panel track is styled");
assertIncludes(css, ".snbr-institutional-rsi-marker", "institutional RSI lower panel marker is styled");

assertIncludes(types, "show_support?: boolean", "layout type persists support toggle");
assertIncludes(types, "show_resistance?: boolean", "layout type persists resistance toggle");

assertNotIncludes(allSources, "RSI@tv-basicstudies", "TradingView RSI study must stay removed");
assertNotIncludes(allSources, "RSI 14 close", "TradingView RSI legend must not be represented as a contract");
assertNotIncludes(allSources, "toggle do gráfico mostra RSI do TradingView", "old Portuguese RSI divergence text must stay removed");
assertNotIncludes(allSources, "chart toggle shows TradingView RSI", "old English RSI divergence text must stay removed");

console.log(JSON.stringify({ ok: true, mission: "25D.3", checks: 45 }, null, 2));
