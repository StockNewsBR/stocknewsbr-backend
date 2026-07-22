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
expect("insufficient sentiment keeps the original colored gauge with a neutral needle and dash", /effectiveSentimentScore = firstFiniteNumber\(sentimentContract\?\.status === ["']READY["']/.test(shell) && /\(normalized \?\? 50\) \* 1\.8/.test(shell) && /className=["']snbr-meter-arc bearish["']/.test(shell) && /normalized == null \? ["']—["']/.test(shell));
expect("daily volume ratio is separate from intraday RVOL", /volume_vs_daily_average/.test(`${shell}\n${types}`) && /dailyVolumeRatio == null \? null : dailyVolumeRatio \* 100/.test(shell) && /formatLocalePrice\(dailyVolumeRatio, appLocale\)/.test(shell) && /Dado informativo/.test(shell));
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

const failed = checks.filter((check) => !check.ok);
for (const check of checks) {
  process.stdout.write(`${check.ok ? "PASS" : "FAIL"} ${check.label}\n`);
}

if (failed.length) {
  throw new Error(`Mission 68 frontend contract failed: ${failed.length}/${checks.length}`);
}

process.stdout.write(`Mission 68 frontend contract passed: ${checks.length}/${checks.length}\n`);
