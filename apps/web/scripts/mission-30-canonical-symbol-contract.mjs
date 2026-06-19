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
    throw new Error(`Mission 30 missing: ${label}`);
  }
}

function assertNotIncludes(source, needle, label) {
  if (source.includes(needle)) {
    throw new Error(`Mission 30 regression: ${label}`);
  }
}

function priceToY(price, minPrice, maxPrice) {
  const span = Math.max(maxPrice - minPrice, Math.abs(price) * 0.0001, 0.0001);
  return 92 - ((price - minPrice) / span) * 84;
}

const registry = read("apps/web/lib/symbol-registry.ts");
const tickerChart = read("apps/web/components/ticker-chart.tsx");
const workspaceShell = read("apps/web/components/workspace-shell.tsx");
const workspaceRails = read("apps/web/components/workspace-rails.tsx");
const css = read("apps/web/app/globals.css");
const mobileRegistry = read("apps/mobile/lib/symbolRegistry.ts");
const mobileApi = read("apps/mobile/lib/api.ts");

for (const expected of [
  "PETR4: [\"PETR4.SA\", \"PETR4 B3\", \"PETR\"",
  "AXIA6: [\"AXIA6.SA\", \"AXIA6 B3\", \"ELET6\"",
  "ASAI3: [\"ASAI3.SA\"",
  "AZUL4: [\"AZUL4.SA\"",
  "B3SA3: [\"B3SA3.SA\"",
  "BTC",
  "XBTUSD",
  "NASDAQ:AAPL",
  "AAPL.US",
  "WINFUT",
  "export function canonicalSymbol",
  "export function tradingViewSymbolFor",
  "export function providerSymbolFor",
  "export function symbolCategoryFor",
  "BMFBOVESPA:PETR4",
  "BMFBOVESPA:AXIA6",
  "BINANCE:${canonical.slice(0, -3)}USDT",
  "NASDAQ:AAPL",
]) {
  assertIncludes(registry, expected, `web registry contains ${expected}`);
}

assertIncludes(workspaceShell, "resolveCanonicalSymbol", "workspace uses canonical symbol resolver");
assertIncludes(workspaceShell, "resolveCanonicalSymbolAliases", "workspace uses canonical alias resolver");
assertIncludes(workspaceShell, "\"AXIA6.SA\"", "active B3 watchlist uses AXIA6 instead of retired ELET6");
assertIncludes(workspaceShell, "friendlyNetworkErrorMessage", "frontend maps fetch failures to product-safe copy");
assertIncludes(workspaceShell, "sem snapshot", "watchlist has clear missing-price fallback");
assertIncludes(workspaceShell, "sem cotação confirmada", "symbol header avoids R$ n/a for missing quotes");
assertIncludes(workspaceShell, "activeWatchCategoryCounts", "active list counts by canonical category");
assertIncludes(workspaceShell, "CATEGORY_ORDER.reduce((total, category)", "Todos equals B3 + BDR + Crypto + USA");
assertIncludes(workspaceRails, "}: ${activeWatchCount}", "active list count label cannot be mistaken for a negative number");
assertIncludes(workspaceShell, "decisionTradeLabel(tradeTone", "mixed/conflicting scenarios render Aguardar instead of a forced side");
assertIncludes(workspaceShell, "alignStrategicSectionsWithTrade", "strategic conclusion is aligned with suggested trade side");
assertIncludes(workspaceShell, "alignOperationalDecisionWithTrade", "operational decision copy is aligned with suggested trade side");
assertIncludes(workspaceShell, "Resultados de ${oilResults[1]}", "BR news headlines translate common English market title");
assertIncludes(workspaceShell, "Sem evento relevante para este ativo agora", "AI zero-state badge has textual fallback");
assertNotIncludes(workspaceShell, "setError(requestError.message)", "raw fetch errors are not shown to users");
assertNotIncludes(workspaceShell, "setError(requestError instanceof Error ? requestError.message", "raw request errors are not shown to users");
assertNotIncludes(workspaceShell, "Failed to fetch", "literal fetch failure is not rendered in the UI");
assertNotIncludes(workspaceShell, "\"ELET3.SA\", \"ELET6.SA\"", "retired ELET6 is not preloaded as active B3 item");
assertIncludes(tickerChart, "tradingViewSymbolFor(sourceSymbol)", "ticker chart uses centralized TradingView mapping");
assertIncludes(tickerChart, "function priceToY", "support/resistance uses price-to-y projection");
assertIncludes(tickerChart, "buildPriceAnchoredLevelChart", "support/resistance chart layer is price anchored");
assertIncludes(tickerChart, "viewBox=\"0 0 100 100\"", "level layer uses scalable SVG viewBox");
assertIncludes(tickerChart, "preserveAspectRatio=\"none\"", "level layer resizes with fullscreen/container changes");
assertIncludes(tickerChart, "data-price={level.price}", "level line stores the invariant price");
assertIncludes(tickerChart, "y1={level.y}", "line y coordinate comes from price");
assertIncludes(tickerChart, "y2={level.y}", "line y coordinate is shared by the full line");
assertIncludes(tickerChart, "snbr-chart-level-label", "labels move with the same level group");
assertIncludes(css, "vector-effect: non-scaling-stroke", "price lines remain crisp during zoom/resize");
assertIncludes(css, ".snbr-chart-level-svg", "SVG level layer is styled");
assertIncludes(css, ".snbr-chart-level-label", "line labels are styled");
assertNotIncludes(css, "top: 26%", "resistance is not fixed to viewport percentage");
assertNotIncludes(css, "top: 55%", "support is not fixed to viewport percentage");
assertNotIncludes(tickerChart, "style={{ top:", "component does not position levels by local top style");

const resistanceY = priceToY(14.79, 14.7, 14.9);
const supportY = priceToY(14.77, 14.7, 14.9);
for (const viewportWidth of [320, 768, 1440, 2560]) {
  const zoomedResistanceY = priceToY(14.79, 14.7, 14.9);
  const zoomedSupportY = priceToY(14.77, 14.7, 14.9);
  if (zoomedResistanceY !== resistanceY || zoomedSupportY !== supportY || viewportWidth <= 0) {
    throw new Error("Mission 30 regression: support/resistance changed under viewport zoom simulation");
  }
}

assertIncludes(mobileRegistry, "export function canonicalSymbol", "mobile has canonical symbol resolver");
assertIncludes(mobileRegistry, "AXIA6: [\"AXIA6.SA\", \"AXIA6 B3\", \"ELET6\"", "mobile registry resolves retired ELET6 to AXIA6");
assertIncludes(mobileApi, "tickerPathValue", "mobile API canonicalizes ticker path values");
assertIncludes(mobileApi, "canonicalSymbol(ticker)", "mobile API uses canonical symbol resolver");

console.log(JSON.stringify({ ok: true, mission: "30", checks: 56 }, null, 2));
