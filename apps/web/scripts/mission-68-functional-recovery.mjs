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
const sections = read("components/workspace-sections.tsx");
const api = read("lib/api.ts");
const accessAuthority = read("lib/access-authority.ts");
const types = read("lib/types.ts");
const symbolContextSections = shell.slice(
  shell.indexOf("function symbolContextStrategicSections"),
  shell.indexOf("function symbolContextStrategicBasis"),
);
const symbolContextBasis = shell.slice(
  shell.indexOf("function symbolContextStrategicBasis"),
  shell.indexOf("function strategicDecisionBasis"),
);

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
expect("TradingView range presets do not override the canonical candle interval", /interval:\s*timeframe\.interval/.test(chart) && !/range:\s*timeframe\.range/.test(chart));
expect("GIF search is internal", /searchGifs\(/.test(api) && !/tenor\.com\/search/.test(shell));
expect("GIF provider errors remain errors", /payload\.status === ["']ERROR["'][\s\S]{0,120}["']error["']/.test(shell));
expect("selected GIF is sent as image_url", /let imageUrl: string \| null = selectedGif\?\.media_url[\s\S]{0,420}image_url: imageUrl/.test(shell));
expect("support and resistance receive symbol/timeframe metadata", /levelMetadata=\{/.test(shell));
expect("canonical analysis contract drives Bias", /canonicalAnalysis/.test(shell));
expect(
  "selected-symbol operational view drives cards and decision",
  /symbolContextDecisionCards\(symbolOperationalView, appLocale\)/.test(shell)
    && /operationalDecisionFromSymbolContext\(symbolOperationalView, appLocale\)/.test(shell),
);
expect(
  "selected-symbol page does not fall back to global snapshot insight",
  /return currentPublicInsight;/.test(shell) && !/if \(snapshotInsight\) return snapshotInsight;/.test(shell),
);
expect(
  "polling replaces hydrated fields instead of freezing the first partial payload",
  /return \{ \.\.\.current, \.\.\.nextInsight, market_metrics: bundle\?\.market_metrics \|\| null/.test(shell),
);
expect(
  "symbol metrics update independently from insight and keep operational polling alive",
  /const \[publicMarketMetrics, setPublicMarketMetrics\] = useState<PublicMarketMetrics \| null>\(null\)/.test(shell)
    && /const assetMetrics = publicMarketMetrics && sameSymbol\(publicMarketMetrics\.canonical_symbol, selectedTicker\)/.test(shell)
    && /publicMarketMetrics\?\.operational_view\?\.technical_context\?\.institutional_flow\?\.status/.test(shell),
);
expect("synthetic sentiment and RVOL calibrators are absent", !/calibrateSentimentMeterValue|calibrateVolumeMeterValue/.test(shell));
expect("null is not coerced into a real zero", /value == null \|\| value === ["']["']\) continue/.test(shell) && /value == null \|\| value === ["']["']\) continue/.test(chart));
expect("insufficient sentiment has no neutral needle and keeps the dash", /rawSentimentValue = sentimentContract\?\.status === ["']READY["']/.test(shell) && /\{normalized != null \? \(/.test(shell) && /normalized == null \? ["']—["']/.test(shell));
expect("classified neutral sentiment stays neutral and exposes sample size", /categoricalSentiment === ["']neutral["']/.test(shell) && /components\?\.classified_total/.test(shell) && /sentimentSampleSize/.test(shell));
expect("daily volume ratio is centered at 1x and clamps 4.42x high", /volume_vs_daily_average/.test(`${shell}\n${types}`) && /dailyVolumeRatio == null \? null : dailyVolumeRatio \* 50/.test(shell) && Math.min(100, 4.42 * 50) === 100 && /formatLocalePrice\(dailyVolumeRatio, appLocale\)/.test(shell) && /Dado informativo/.test(shell));
expect("non-operational daily volume never gets the green RVOL meter", !/assetRelativeVolumeForMeter/.test(shell) && !/Volume do ativo \(RVOL\)/.test(shell));
expect("insufficient level separation is terminal, not calculating", /operationalLevelsStatus === ["']INSUFFICIENT_SEPARATION["'][\s\S]{0,180}sem separação suficiente/.test(shell) && /Nenhum suporte, resistência ou entrada operacional validado/.test(shell));
expect("WAIT narrative preserves the technical bias", /AGUARDAR é um estado de autorização, não uma classificação de tendência neutra/.test(symbolContextSections) && !/leitura final é neutra|preço, volume e fluxo alinharem/i.test(symbolContextSections));
expect("partial Master Score exposes completeness", /Score técnico parcial/.test(shell) && /Calculado com \$\{usedScoreComponents\} de \$\{totalScoreComponents\} componentes/.test(shell) && /missing_components/.test(types));
expect("active liquidity requires validated geometry", /liquidityReady = liquidity\?\.status === ["']READY["'] && liquidity\.side/.test(shell) && /distance_from_price_pct/.test(types));
expect("unsolicited timeframe chips are absent", !/Dados carregados do gráfico/.test(shell) && !/Análise operacional/.test(shell) && !/aria-label=\{isUsLocale \? ["']Analysis timeframes["']/.test(shell));
expect("analysis basis contains only the six requested clean readings", /Viés técnico/.test(symbolContextBasis) && /Tendência D1/.test(symbolContextBasis) && /Direção 5m/.test(symbolContextBasis) && /Fluxo 5m/.test(symbolContextBasis) && /Score técnico parcial/.test(symbolContextBasis) && /Volume atual \/ média diária/.test(symbolContextBasis) && !/RSI D1:|RVOL intraday|Sentimento atual|Liquidez|Níveis operacionais|Dados de mercado até/.test(symbolContextBasis));
expect("stale D1 trend is presented as outdated without becoming a current neutral conclusion", /trendStatus === ["']STALE["'][\s\S]{0,100}["']Desatualizada["']/.test(shell) && /Última leitura/.test(shell) && /contexto intraday \$\{bias\}; tendência D1 aguardando atualização/.test(symbolContextSections));
expect("insufficient liquidity uses the compact visual copy", /["']Liquidez 5m["']/.test(shell) && /["']Indisponível["']/.test(shell) && /["']Dados insuficientes["']/.test(shell) && !/Liquidez indisponível — dados insuficientes/.test(shell));
expect(
  "top Bias prefers the selected-symbol technical bias over legacy insight",
  /const operationalTechnicalBias = currentTechnicalBias\(symbolOperationalView\?\.technical_context\.technical_bias\)/.test(shell)
    && /const rawBias = displayQuoteHasCoreData \? operationalBias \|\| derivedPublicInsight\?\.trend_bias/.test(shell)
    && /bear\|bearish/.test(shell)
    && /bull\|bullish/.test(shell),
);
expect(
  "partial top score keeps completeness instead of weakness copy",
  /masterScoreStatus === ["']PARTIAL["'][\s\S]{0,520}score técnico parcial, calculado com/.test(shell)
    && /masterScoreStatus === ["']PARTIAL["'] && effectiveAiScore != null \? `\$\{aiScoreValue\}\/10`/.test(shell)
    && /label\.includes\(["']parcial["']\) \|\| label\.includes\(["']partial["']\)\) return item/.test(shell),
);
expect(
  "READY or PARTIAL BULLISH plus WAIT keeps the selected-symbol bias everywhere",
  /status !== ["']READY["'] && status !== ["']PARTIAL["']/.test(shell)
    && /const technicalBias = currentTechnicalBias\(view\.technical_context\.technical_bias\)/.test(shell)
    && /const contextTechnicalBias = currentTechnicalBias\(input\.symbolContext\?\.technical_context\.technical_bias\)/.test(shell)
    && /bias,\n\s+risk: view\.risk/.test(shell),
);
expect(
  "daily trend and RSI expose their actual freshness session",
  /function dailyFreshnessMeta/.test(shell)
    && /component\.data_as_of \|\| component\.as_of/.test(shell)
    && /component\.session_date \|\| sessionDate/.test(shell)
    && /Última sessão disponível/.test(shell)
    && /trendFreshness/.test(shell)
    && /rsiFreshness/.test(shell)
    && /data_as_of\?: string \| null/.test(types)
    && /age_sessions\?: number \| null/.test(types),
);
expect(
  "Flow Liquidity Trend and Momentum badges are explicitly global",
  /GLOBAL_AI_ALERT_TAB_IDS = new Set\(\[["']flow["'], ["']liquidity["'], ["']trend["'], ["']momentum["']\]\)/.test(shell)
    && /data-tab-scope=\{isGlobalAiAlertTab \? ["']global["'] : ["']selected-symbol["']\}/.test(shell)
    && /alertas globais atuais do mercado/.test(shell)
    && /<span[\s\S]{0,260}className=["']snbr-tab-count-badge["'][\s\S]{0,500}>\s*\{tabCount\}\s*<\/span>/.test(shell),
);
expect(
  "terminal AI states never remain calculating",
  /normalizedAiRequestStatus === ["']PENDING_EXPIRED["']/.test(shell)
    && /normalizedAiRequestStatus === ["']UNSUPPORTED["']/.test(shell)
    && /normalizedAiRequestStatus === ["']ERROR["'] \|\| normalizedAiRequestStatus === ["']PROVIDER_ERROR["']/.test(shell)
    && /aiRequestTerminal[\s\S]{0,500}currentTabAlertSourceRows/.test(shell)
    && /A hidratação pendente expirou/.test(shell)
    && /Falha na análise da IA/.test(shell),
);
expect(
  "wait decision caps strong bias copy (coherence invariant)",
  /function reconcileStatsWithDecision/.test(shell)
    && /AGUARDAR\|WAIT/.test(shell)
    // The invariant is that a WAIT decision must DEMOTE "Alta/Baixa forte" to a
    // plain directional bias — not that it must carry a specific suffix. The
    // "(aguardando confirmação)" wording was dropped at the owner's request; the
    // capping itself still has to be there.
    && /Viés comprador/.test(shell)
    && /Viés vendedor/.test(shell)
    && !/Viés comprador forte/.test(shell)
    && !/Viés vendedor forte/.test(shell)
    && /Preço abaixo do VWAP — força limitada\./.test(shell)
    && /favorece compra APÓS confirmação\./.test(shell)
    && /stats=\{coherentDisplayStats\}/.test(shell)
    && !/stats=\{displayStats\}/.test(shell)
    && !/\{displayStats\.map/.test(shell),
);
expect(
  "top-card RSI stays D1 while chart chip + panel follow the selected timeframe",
  /firstValidRsiNumber\(symbolOperationalView\?\.technical_context\.rsi_d1/.test(shell)
    && /describeRsiValue\(panelRsiValue/.test(shell)
    && /RSI diário \(D1\)/.test(shell)
    && /institutionalRsiValue=\{chartTimeframeRsi\}/.test(shell)
    && /rsiTimeframeLabel=\{rsiTimeframeLabel\}/.test(shell)
    && /\$\{rsiTitle\}/.test(chart),
);
expect(
  "RSI timeframe label is driven by rsi_metadata, never by the chart range button",
  // The range button ("1D" = one day of 5m candles) is not a candle size. If the
  // label is ever derived from chartInterval again, an intraday RSI ships as "D1".
  /function rsiTimeframeTag\(/.test(shell)
    && /candle_interval\s*\|\|\s*metadata\?\.timeframe/.test(shell)
    && /rsiTimeframeLabel = rsiTimeframeTag\(chartRsiMetadata\)/.test(shell)
    && !/rsiTimeframeLabel = chartInterval/.test(shell)
    && /describeRsiValue\(panelRsiValue, appLocale, cardRsiTimeframeLabel[,)]/.test(shell),
);
expect(
  "premium public requests propagate the authenticated token",
  /getPublicAiTools\([\s\S]{0,220}token\?: string[\s\S]{0,420}\{ token, signal, cacheTtlMs: 15000 \}/.test(api)
    && /getPublicMarketBundle\([\s\S]{0,260}token\?: string[\s\S]{0,420}\{ token, signal, cacheTtlMs: force \? 0 : 10000 \}/.test(api)
    && /getPublicAiTools\(selectedTicker, currentAiKey, chartInterval, controller\.signal, token\)/.test(shell)
    && /getPublicMarketBundle\(deferredTicker, chartInterval, appLocale, controller\.signal, false, token\)/.test(shell),
);
expect(
  // The plan/status rule moved out of the shell into the canonical entitlement
  // authority (lib/access-authority.ts) when access got a single owner. The
  // property is unchanged and now stricter, so this asserts it at BOTH ends:
  // the authority still gates on the plan list, and the shell still derives
  // proModeAllowed only from that authority's ALLOWED state — never from
  // localStorage, which can express a preference but can never grant Pro.
  "anonymous and non-premium users cannot enter Pro mode",
  /export const PRO_PLANS = \["trial", "premium", "enterprise"\]/.test(accessAuthority)
    && /export function isProEntitled\(/.test(accessAuthority)
    && /PRO_PLANS as readonly string\[\]\)\.includes\(plan\)/.test(accessAuthority)
    && /DEAD_PLAN_STATUSES as readonly string\[\]\)\.includes\(status\)/.test(accessAuthority)
    && /return isProEntitled\(outcome\.payload\) \? "ALLOWED" : "DENIED"/.test(accessAuthority)
    && /case "DENIED":\s*\n\s*return \{ advancedMode: false/.test(accessAuthority)
    && /const proModeAllowed = accessState === "ALLOWED";/.test(shell)
    && /const proModeLocked = !proModeAllowed/.test(shell),
);
expect(
  "PREMIUM_LOCKED is terminal and clears AI findings",
  /const aiRequestLocked = normalizedAiRequestStatus === "PREMIUM_LOCKED"/.test(shell)
    && /const aiRequestTerminal = aiRequestLocked \|\|/.test(shell)
    && /const currentTabAlertSourceRows = aiAccessLocked\s*\?\s*\[\]/.test(shell)
    && /IA Pro bloqueada/.test(shell),
);
expect(
  "historical news is visible but never counted as current",
  /const freshNewsCount = useMemo/.test(shell)
    && /const newsIsHistorical = Boolean/.test(shell)
    && /Última notícia disponível \(histórico\)/.test(shell)
    && /newsStatus=\{newsStatusForPanel\}/.test(shell)
    && /tab\.id === "news"\s*\?\s*freshNewsCount/.test(shell)
    && /return historical \? "historical" as const : "ready" as const/.test(sections)
    && /data-news-historical="true"/.test(sections),
);
expect(
  "fallback conclusion uses real chart evidence without authorizing a trade",
  /conclusion: StrategicConclusion/.test(shell)
    && /strategicSectionsForRender\(input\.conclusion, input\.locale, input\.symbol\)/.test(shell)
    && /input\.conclusion\.basis\.length/.test(shell)
    && /executionMetricsReady = Boolean\(symbolOperationalView && operationalBlockComponents\.length === 0\)/.test(shell)
    && /AGUARDAR é um estado de autorização, não uma classificação de tendência neutra/.test(shell)
    && /Último evento do snapshot interno \(não é decisão operacional\)/.test(shell)
    && /data-chart-analysis-source-note="true"/.test(shell),
);
expect(
  "missing score is not converted into high risk and volume does not invent RVOL",
  /effectiveScore == null[\s\S]{0,180}Dados insuficientes/.test(shell)
    && !/estimateRelativeVolumeFromActivity/.test(shell)
    && /informativo, não é RVOL operacional/.test(shell),
);
expect(
  "RSI parsing ignores timeframe digits and reads the value after the label",
  /const basisNumber = \(line: string\) =>\s*Number\(line\.match\(\/:\\s\*\(-\?\\d\+/.test(shell)
    && /const rsiValue = basisNumber\(rsiLine\)/.test(shell)
    && /RSI do snapshot interno/.test(shell),
);
expect(
  "public D1 RSI and selected chart RSI remain available without premium operational context",
  /firstValidRsiNumber\(\s*symbolOperationalView\?\.technical_context\.rsi_d1\?\.value,\s*currentPublicInsight\?\.rsi/.test(shell)
    && /rsi: rsiNumber,[\s\S]{0,100}rsiTimeframe: rsiTimeframeLabel/.test(shell),
);

const failed = checks.filter((check) => !check.ok);
for (const check of checks) {
  process.stdout.write(`${check.ok ? "PASS" : "FAIL"} ${check.label}\n`);
}

if (failed.length) {
  throw new Error(`Mission 68 frontend contract failed: ${failed.length}/${checks.length}`);
}

process.stdout.write(`Mission 68 frontend contract passed: ${checks.length}/${checks.length}\n`);
