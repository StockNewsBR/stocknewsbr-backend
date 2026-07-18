import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const webRoot = path.resolve(scriptDir, "..");

function read(relativePath) {
  return fs.readFileSync(path.join(webRoot, relativePath), "utf8");
}

const shell = read("components/workspace-shell.tsx");
const rails = read("components/workspace-rails.tsx");
const chart = read("components/ticker-chart.tsx");
const api = read("lib/api.ts");
const types = read("lib/types.ts");

const checks = [];

function expect(label, condition) {
  checks.push({ label, ok: Boolean(condition) });
}

expect("locale is sent by news requests", /getNews\([^)]*locale/.test(api));
expect("locale is sent by market bundle requests", /getPublicMarketBundle\([^)]*locale/.test(api));
expect("saved locale is restored only after hydration", /useState<AppLocale>\(["']pt-BR["']\)[\s\S]{0,180}appLocaleHydrated/.test(shell));
expect("AI requests carry symbol, tool, and timeframe", /getPublicAiTools\([^)]*symbol[^)]*tool[^)]*timeframe/.test(api));
expect("watchlist state has a versioned persistence key", /WATCHLIST_STATE_STORAGE_KEY\s*=\s*["'][^"']+\.v\d+["']/.test(shell));
expect("strategic panel has independent persisted state", /STRATEGIC_PANEL_STORAGE_KEY\s*=\s*["'][^"']+\.v\d+["']/.test(shell));
expect("strategic panel exposes aria-expanded", /aria-expanded=\{advancedMode && strategicPanelOpen\}/.test(shell));
expect("RSI metadata is represented in the web contract", /rsi_metadata\??:\s*\{/.test(types));
expect("quote-derived RSI fallback is not used", !/derivePublicRsi\(/.test(shell));
expect("synthetic chart fallback is removed", !/buildQuoteFallbackChart/.test(shell));
expect("fabricated poll fallback is removed", !/buildFallbackPoll/.test(shell));
expect(
  "right rail requires a verified poll question and options",
  /const hasVerifiedPoll = Boolean\(activePoll\.question\?\.trim\(\) && activePoll\.options\?\.length\)/.test(rails)
    && /hasVerifiedPoll \?[\s\S]{0,120}<strong>\{activePoll\.question\}<\/strong>/.test(rails)
    && !/Poll\/Vote for[^\n]*selectedTicker|Poll\/Votar de[^\n]*selectedTicker/.test(rails),
);
expect("fabricated AI rows are removed", !/expandedToolCandidates/.test(shell));
expect("Averages chart option is removed", !/show_averages|showAverages|MASimple@tv-basicstudies/.test(`${shell}\n${chart}`));
expect("TradingView study overrides are serialized before iframe parsing", /studies_overrides:\s*JSON\.stringify\(\{/.test(chart));
expect("TradingView uses a direct iframe without an async loader race", /www\.tradingview-widget\.com\/embed-widget\/advanced-chart/.test(chart) && !/external-embedding\/embed-widget-advanced-chart/.test(chart));
expect("GIF search is internal", /searchGifs\(/.test(api) && !/tenor\.com\/search/.test(shell));
expect("GIF provider errors remain errors", /payload\.status === ["']ERROR["'][\s\S]{0,120}["']error["']/.test(shell));
expect("selected GIF is sent as image_url", /let imageUrl: string \| null = selectedGif\?\.media_url[\s\S]{0,420}image_url: imageUrl/.test(shell));
expect("support and resistance receive symbol/timeframe metadata", /levelMetadata=\{/.test(shell));
expect("canonical analysis contract drives Bias", /canonicalAnalysis/.test(shell));
expect(
  "wait decision caps strong bias copy (coherence invariant)",
  /function reconcileStatsWithDecision/.test(shell)
    && /AGUARDAR\|WAIT/.test(shell)
    && /Viés comprador \(aguardando confirmação\)/.test(shell)
    && /Viés vendedor \(aguardando confirmação\)/.test(shell)
    && /Preço abaixo do VWAP — força limitada\./.test(shell)
    && /favorece compra APÓS confirmação\./.test(shell)
    && /stats=\{coherentDisplayStats\}/.test(shell)
    && !/stats=\{displayStats\}/.test(shell)
    && !/\{displayStats\.map/.test(shell),
);
expect(
  "top-card RSI stays D1 while chart chip + panel follow the selected timeframe",
  /firstValidRsiNumber\(currentPublicInsight\?\.rsi/.test(shell)
    && /describeRsiValue\(panelRsiValue/.test(shell)
    && /RSI diário \(D1\)/.test(shell)
    && /institutionalRsiValue=\{chartTimeframeRsi\}/.test(shell)
    && /rsiTimeframeLabel=\{rsiTimeframeLabel\}/.test(shell)
    && /RSI \$\{rsiTimeframeTag\}/.test(chart),
);

const failed = checks.filter((check) => !check.ok);
for (const check of checks) {
  process.stdout.write(`${check.ok ? "PASS" : "FAIL"} ${check.label}\n`);
}

if (failed.length) {
  throw new Error(`Mission 68 frontend contract failed: ${failed.length}/${checks.length}`);
}

process.stdout.write(`Mission 68 frontend contract passed: ${checks.length}/${checks.length}\n`);
