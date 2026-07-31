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
    throw new Error(`Mission 25D inert check: "${label}" repeats an earlier assertion on the same source and can never fail independently`);
  }

  seen.add(key);
}

function assertIncludes(source, needle, label) {
  trackCheck(source, needle, label, "includes");

  if (!source.includes(needle)) {
    throw new Error(`Mission 25D contract missing: ${label}`);
  }
}

function assertNotIncludes(source, needle, label) {
  trackCheck(source, needle, label, "excludes");

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
// Two independent consumers of the same canonical zones: the operational decision
// builder (plain object prop) and the chart component (JSX prop). Asserting the
// same needle twice would leave the second check unable to fail on its own.
assertIncludes(workspaceShell, "chart: chartForOperationalLevels", "operational levels use canonical chart zones");
assertIncludes(workspaceShell, "chart={chartForOperationalLevels}", "chart component receives the same canonical zones");
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
assertIncludes(tickerChart, "rsiPanelStyle", "institutional RSI panel positions its marker from a computed style");
assertIncludes(tickerChart, "snbr-institutional-rsi-marker", "institutional RSI lower panel marks the same snapshot value");
assertIncludes(tickerChart, "--snbr-rsi-position", "institutional RSI marker uses the passed value");
assertIncludes(tickerChart, "O RSI do TradingView continua desativado", "empty RSI state states the TradingView RSI stays disabled");
assertIncludes(tickerChart, "rsiTitle", "institutional RSI labels are built from a single title source");
// show_rsi owns the institutional panel and nothing else: the panel's visibility
// must be bound to it directly, with no extra gate that can silently disable it.
assertIncludes(tickerChart, "aria-hidden={!showRsi}", "institutional RSI panel visibility is bound to show_rsi alone");
assertNotIncludes(tickerChart, "RSI_PANEL_VISIBLE", "no hard-coded flag may override the show_rsi toggle");
assertNotIncludes(tickerChart, "RSI@tv-basicstudies", "TradingView RSI study must not be injected");
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
assertIncludes(css, ".snbr-institutional-rsi-panel.hidden", "institutional RSI panel has an explicit off state");
assertIncludes(css, ".snbr-institutional-rsi-panel", "institutional RSI lower panel is styled");
assertIncludes(css, ".snbr-institutional-rsi-track", "institutional RSI lower panel track is styled");
assertIncludes(css, ".snbr-institutional-rsi-marker", "institutional RSI lower panel marker is styled");

assertIncludes(types, "show_support?: boolean", "layout type persists support toggle");
assertIncludes(types, "show_resistance?: boolean", "layout type persists resistance toggle");

assertNotIncludes(allSources, "RSI@tv-basicstudies", "TradingView RSI study must stay removed");
assertNotIncludes(allSources, "RSI 14 close", "TradingView RSI legend must not be represented as a contract");
assertNotIncludes(allSources, "toggle do gráfico mostra RSI do TradingView", "old Portuguese RSI divergence text must stay removed");
assertNotIncludes(allSources, "chart toggle shows TradingView RSI", "old English RSI divergence text must stay removed");

console.log(JSON.stringify({ ok: true, mission: "25D.3", checks: checkCount }, null, 2));
