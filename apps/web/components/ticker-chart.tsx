"use client";

import { useEffect, useMemo, useRef, useState, type CSSProperties } from "react";
import type { ChartPayload } from "@/lib/types";
import { canonicalSymbol, resolveTradingViewSymbolCandidates } from "@/lib/symbol-registry";

type Props = {
  chart: ChartPayload | null;
  ticker?: string;
  interval?: string;
  showMarkers?: boolean;
  showZones?: boolean;
  showPriceLine?: boolean;
  showVwap?: boolean;
  showMacd?: boolean;
  showRsi?: boolean;
  showSupertrend?: boolean;
  showVolume?: boolean;
  showSupport?: boolean;
  showResistance?: boolean;
  supportLevel?: number | null;
  resistanceLevel?: number | null;
  institutionalRsiValue?: number | null;
  // Timeframe tag for the chart chip + panel ("D1", "1m", "30m", "1h"): the panel
  // value follows the selected chart timeframe (per-timeframe RSI from the bundle).
  rsiTimeframeLabel?: string;
  rsiMetadata?: { status?: string | null; reason?: string | null; candle_count?: number | null; required_count?: number | null } | null;
  levelMetadata?: { symbol: string; timeframe: string; as_of?: string | null } | null;
  locale?: "pt-BR" | "en-US";
};

type ChartLevelOverlay = {
  key: "support" | "resistance";
  label: string;
  price: number;
};

const TIMEFRAME_TO_TRADING_VIEW: Record<string, { interval: string; range: string }> = {
  "1D": { interval: "5", range: "1D" },
  "1W": { interval: "30", range: "5D" },
  "1M": { interval: "60", range: "1M" },
  "3M": { interval: "D", range: "3M" },
  "6M": { interval: "D", range: "6M" },
  YTD: { interval: "D", range: "YTD" },
  "1Y": { interval: "D", range: "12M" },
  All: { interval: "W", range: "ALL" },
};

function cleanSymbol(value: string | undefined | null) {
  return canonicalSymbol(value);
}

function getTheme() {
  if (typeof document === "undefined") return "dark";
  const root = document.documentElement;
  const body = document.body;
  const dataTheme = root.getAttribute("data-theme") || body.getAttribute("data-theme");
  if (dataTheme?.toLowerCase().includes("light")) return "light";
  if (root.classList.contains("theme-light") || root.classList.contains("light") || body.classList.contains("theme-light") || body.classList.contains("light")) {
    return "light";
  }
  return "dark";
}

// No RSI study is injected here on purpose: `show_rsi` is labelled "RSI painel"/
// "Panel RSI" and owns the institutional RSI panel below the chart, which reads
// the snapshot value the backend computed. Pushing TradingView's own RSI study
// made a single toggle draw a second, differently-computed RSI inside the widget
// -- the exact divergence the mission-25d/28b contracts forbid.
function buildStudies(showVwap: boolean, showMacd: boolean, showSupertrend: boolean) {
  const studies: string[] = [];
  if (showVwap) studies.push("VWAP@tv-basicstudies");
  if (showMacd) studies.push("MACD@tv-basicstudies");
  // TradingView's built-in Supertrend (not the community "ATR WITH TSL" script,
  // which is a custom Pine indicator and cannot be injected via the embed widget).
  if (showSupertrend) studies.push("STD;Supertrend");
  return studies;
}

function firstFiniteNumber(...values: Array<unknown>) {
  for (const value of values) {
    if (value == null || value === "") continue;
    const numeric = Number(value);
    if (Number.isFinite(numeric)) return numeric;
  }
  return null;
}

function clampRsi(value: number) {
  return Math.min(100, Math.max(0, value));
}

function formatRsiValue(value: number, locale: "pt-BR" | "en-US") {
  return new Intl.NumberFormat(locale, {
    maximumFractionDigits: 1,
    minimumFractionDigits: 1,
  }).format(value);
}

// Same canonical thresholds as the top-card RSI copy in workspace-shell:
// <30 oversold, 30-45 bearish, 45-55 neutral, 55-70 bullish, >70 overbought.
function rsiToneClass(value: number) {
  if (value > 70) return "overbought";
  if (value < 30) return "oversold";
  if (value >= 55) return "bullish";
  if (value < 45) return "bearish";
  return "neutral";
}

function formatLevelPrice(value: number, locale: "pt-BR" | "en-US") {
  return new Intl.NumberFormat(locale, {
    maximumFractionDigits: value >= 100 ? 2 : 4,
    minimumFractionDigits: value >= 100 ? 2 : 0,
  }).format(value);
}

function buildLevelOverlays(
  input: {
    showSupport: boolean;
    showResistance: boolean;
    supportLevel?: number | null;
    resistanceLevel?: number | null;
    locale: "pt-BR" | "en-US";
  },
) {
  const support = firstFiniteNumber(input.supportLevel);
  const resistance = firstFiniteNumber(input.resistanceLevel);

  const labels = input.locale === "en-US"
    ? { support: "Support", resistance: "Resistance" }
    : { support: "Suporte", resistance: "Resistência" };

  const overlays: ChartLevelOverlay[] = [];
  if (input.showSupport && support != null && support > 0) {
    overlays.push({
      key: "support",
      label: labels.support,
      price: support,
    });
  }
  if (input.showResistance && resistance != null && resistance > 0) {
    overlays.push({
      key: "resistance",
      label: labels.resistance,
      price: resistance,
    });
  }
  return overlays;
}

const LEVEL_PANE_HEIGHT = 120;
const LEVEL_PANE_PAD = { top: 12, bottom: 12, left: 8, right: 10 };
const VWAP_COLOR = "#f59e0b";

function LevelLinesPane({
  closes,
  overlays,
  currencyPrefix,
  locale,
}: {
  closes: number[];
  overlays: ChartLevelOverlay[];
  currencyPrefix: string;
  locale: "pt-BR" | "en-US";
}) {
  const paneRef = useRef<HTMLElement | null>(null);
  const [paneWidth, setPaneWidth] = useState(640);

  useEffect(() => {
    const node = paneRef.current;
    if (!node || typeof ResizeObserver === "undefined") return undefined;
    const observer = new ResizeObserver((entries) => {
      const next = Math.round(entries[0]?.contentRect?.width || 0);
      if (next > 0) setPaneWidth(next);
    });
    observer.observe(node);
    return () => observer.disconnect();
  }, []);

  const values = [...closes, ...overlays.map((level) => level.price)];
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = (max - min) || Math.max(Math.abs(max) * 0.01, 1e-6);
  const plotWidth = Math.max(60, paneWidth - LEVEL_PANE_PAD.left - LEVEL_PANE_PAD.right);
  const plotHeight = LEVEL_PANE_HEIGHT - LEVEL_PANE_PAD.top - LEVEL_PANE_PAD.bottom;
  const yFor = (value: number) => LEVEL_PANE_PAD.top + (1 - (value - min) / span) * plotHeight;
  const xFor = (index: number) => LEVEL_PANE_PAD.left + (index / Math.max(1, closes.length - 1)) * plotWidth;
  const points = closes.map((value, index) => `${xFor(index).toFixed(1)},${yFor(value).toFixed(1)}`).join(" ");
  const clampLabelY = (value: number) => Math.min(LEVEL_PANE_HEIGHT - 3, Math.max(11, value));

  return (
    <section
      className="snbr-chart-level-lines"
      aria-label={locale === "en-US" ? "Support/Resistance (verified levels)" : "Suporte/Resistência (níveis verificados)"}
      ref={paneRef}
    >
      <header>{locale === "en-US" ? "Support/Resistance (verified levels)" : "Suporte/Resistência (níveis verificados)"}</header>
      <svg aria-hidden="true" height={LEVEL_PANE_HEIGHT} viewBox={`0 0 ${paneWidth} ${LEVEL_PANE_HEIGHT}`} width="100%">
        <polyline className="snbr-chart-level-closes" points={points} />
        {overlays.map((level) => {
          const lineY = yFor(level.price);
          return (
            <g key={level.key}>
              <line
                className={`snbr-chart-level-line ${level.key}`}
                data-chart-level-line={level.key}
                data-chart-level-price={String(level.price)}
                x1={LEVEL_PANE_PAD.left}
                x2={LEVEL_PANE_PAD.left + plotWidth}
                y1={lineY}
                y2={lineY}
              />
              <text
                className={`snbr-chart-level-label ${level.key}`}
                textAnchor="end"
                x={LEVEL_PANE_PAD.left + plotWidth - 4}
                y={clampLabelY(level.key === "resistance" ? lineY - 5 : lineY + 14)}
              >
                {level.label} {currencyPrefix}{formatLevelPrice(level.price, locale)}
              </text>
            </g>
          );
        })}
      </svg>
    </section>
  );
}

export function TickerChart({
  chart,
  ticker,
  interval = "1D",
  showVwap = true,
  showMacd = false,
  showRsi = false,
  showSupertrend = false,
  showVolume = true,
  showSupport = true,
  showResistance = true,
  supportLevel = null,
  resistanceLevel = null,
  institutionalRsiValue = null,
  rsiMetadata = null,
  rsiTimeframeLabel = "D1",
  levelMetadata = null,
  locale = "pt-BR",
}: Props) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const [theme, setTheme] = useState<"dark" | "light">("dark");
  const [loadFailed, setLoadFailed] = useState(false);
  const sourceSymbol = cleanSymbol(ticker || chart?.ticker);
  const tradingViewCandidates = useMemo(() => resolveTradingViewSymbolCandidates(sourceSymbol), [sourceSymbol]);
  const tradingViewSymbol = tradingViewCandidates[0] || "BMFBOVESPA:PETR4";
  const timeframe = TIMEFRAME_TO_TRADING_VIEW[interval] || TIMEFRAME_TO_TRADING_VIEW["1D"];
  const tradingViewUrl = `https://www.tradingview.com/chart/?symbol=${encodeURIComponent(tradingViewSymbol)}`;
  const currencyPrefix = tradingViewSymbol.startsWith("BMFBOVESPA:") ? "R$" : "$";
  const levelOverlays = useMemo(
    () =>
      buildLevelOverlays({
        showSupport,
        showResistance,
        supportLevel,
        resistanceLevel,
        locale,
      }),
    [showSupport, showResistance, supportLevel, resistanceLevel, locale],
  );
  // The free tv.js embed iframe has no drawing API, so S/R lines are drawn on our own mini price
  // pane below the iframe: real backend closes + real levels sharing one price scale
  // (price_scaled_overlay). Nothing is painted over the third-party chart; chips stay as summary.
  const paneCloses = useMemo(() => {
    const bars = (chart?.series?.length ? chart.series : chart?.ohlc) || [];
    const closes: number[] = [];
    for (const bar of bars) {
      const value = Number(bar?.close);
      if (Number.isFinite(value) && value > 0) closes.push(value);
    }
    return closes.slice(-90);
  }, [chart]);
  const hasPaneScale = paneCloses.length >= 2;
  // mission-30f2 audit only accepts price_scaled_overlay|pending_chart_scale|hidden for anchor mode.
  const supportOverlayStatus = levelOverlays.some((level) => level.key === "support")
    ? (hasPaneScale ? "price_scaled_overlay" : "pending_chart_scale")
    : "hidden";
  const resistanceOverlayStatus = levelOverlays.some((level) => level.key === "resistance")
    ? (hasPaneScale ? "price_scaled_overlay" : "pending_chart_scale")
    : "hidden";
  const showLevelPane = hasPaneScale && levelOverlays.length > 0;
  const institutionalRsi = useMemo(() => {
    const numeric = firstFiniteNumber(institutionalRsiValue);
    if (numeric == null || numeric < 0 || numeric > 100) return null;
    return numeric;
  }, [institutionalRsiValue]);
  // Comes from rsi_metadata (the candles the backend really used). When the backend
  // does not say, show a bare "RSI" rather than inventing a timeframe.
  const rsiTimeframeTag = (rsiTimeframeLabel || "").trim();
  const rsiTitle = rsiTimeframeTag ? `RSI ${rsiTimeframeTag}` : "RSI";
  const rsiPanelLabel = useMemo(() => {
    if (institutionalRsi == null) return null;
    return `${rsiTitle}: ${formatRsiValue(institutionalRsi, locale)}`;
  }, [institutionalRsi, locale, rsiTitle]);
  const rsiPanelStyle = useMemo(() => {
    if (institutionalRsi == null) return undefined;
    return { "--snbr-rsi-position": `${clampRsi(institutionalRsi)}%` } as CSSProperties;
  }, [institutionalRsi]);
  const rsiPanelTone = institutionalRsi == null ? "missing" : rsiToneClass(institutionalRsi);

  useEffect(() => {
    const syncTheme = () => {
      const nextTheme = getTheme();
      setTheme(nextTheme === "light" ? "light" : "dark");
    };
    syncTheme();

    if (typeof MutationObserver === "undefined") return undefined;
    const observer = new MutationObserver(syncTheme);
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ["class", "data-theme"] });
    observer.observe(document.body, { attributes: true, attributeFilter: ["class", "data-theme"] });
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return undefined;

    setLoadFailed(false);
    container.innerHTML = "";

    const widgetLocale = locale === "en-US" ? "en" : "br";
    const iframeSettings = {
      autosize: true,
      symbol: tradingViewSymbol,
      interval: timeframe.interval,
      // TradingView range presets also change the candle resolution (for
      // example, 1D selects 1m). Omitting range preserves the backend's
      // canonical candle interval, so chart indicators and AI start aligned.
      timezone: tradingViewSymbol.startsWith("BMFBOVESPA:") ? "America/Sao_Paulo" : "Etc/UTC",
      theme,
      style: "1",
      backgroundColor: theme === "dark" ? "rgba(7, 16, 26, 1)" : "rgba(255, 255, 255, 1)",
      gridColor: theme === "dark" ? "rgba(226, 232, 240, 0.16)" : "rgba(100, 116, 139, 0.18)",
      withdateranges: true,
      hide_side_toolbar: false,
      allow_symbol_change: true,
      save_image: false,
      calendar: false,
      details: false,
      hotlist: false,
      hide_volume: !showVolume,
      support_host: "https://www.tradingview.com",
      studies: buildStudies(showVwap, showMacd, showSupertrend),
      studies_overrides: JSON.stringify({
        // tv.js embed override keys use the lowercase study title + plot id.
        "volume weighted average price.vwap.color": VWAP_COLOR,
        "volume weighted average price.vwap.linewidth": 4,
        "vwap.vwap.color": VWAP_COLOR,
        "vwap.vwap.linewidth": 4,
      }),
      // No width/height here on purpose: autosize (set above) is what makes the
      // widget track its container. Passing both made TradingView keep the size
      // it had at load time and leave a gap when the layout widened.
      utm_source: window.location.hostname,
      utm_medium: "widget",
      utm_campaign: "advanced-chart",
      "page-uri": `${window.location.host}${window.location.pathname}`,
    };
    const iframeUrl = new URL("https://www.tradingview-widget.com/embed-widget/advanced-chart/");
    iframeUrl.searchParams.set("locale", widgetLocale);
    iframeUrl.hash = encodeURIComponent(JSON.stringify(iframeSettings));

    const iframe = document.createElement("iframe");
    iframe.className = "tradingview-widget-container__widget";
    iframe.src = iframeUrl.toString();
    iframe.title = locale === "en-US" ? `TradingView chart for ${sourceSymbol}` : `Gráfico TradingView de ${sourceSymbol}`;
    iframe.lang = widgetLocale;
    iframe.setAttribute("allowtransparency", "true");
    iframe.setAttribute("frameborder", "0");
    iframe.setAttribute("scrolling", "no");
    iframe.style.width = "100%";
    iframe.style.height = "100%";
    iframe.style.display = "block";
    iframe.style.border = "0";
    iframe.addEventListener("load", () => setLoadFailed(false));
    iframe.addEventListener("error", () => setLoadFailed(true));
    container.appendChild(iframe);

    return () => {
      container.innerHTML = "";
    };
  // `showRsi` is intentionally absent: it no longer feeds the widget, so toggling
  // the panel must not tear down and rebuild the TradingView iframe.
  }, [tradingViewSymbol, sourceSymbol, timeframe.interval, theme, locale, showVwap, showMacd, showSupertrend, showVolume]);

  return (
    <div
      className="snbr-chart-shell snbr-tv-widget-shell"
      data-chart-status={loadFailed ? "load_failed" : "requested"}
      data-source-symbol={sourceSymbol}
      data-tradingview-symbol={tradingViewSymbol}
      data-tradingview-candidates={tradingViewCandidates.join(",")}
      data-anchor-mode={showLevelPane ? "price_scaled_overlay" : "card_only"}
      data-support-anchor-mode={supportOverlayStatus}
      data-resistance-anchor-mode={resistanceOverlayStatus}
      data-support-overlay-status={supportOverlayStatus}
      data-resistance-overlay-status={resistanceOverlayStatus}
      data-vwap-color={VWAP_COLOR}
      data-vwap-width="4"
      data-level-symbol={levelMetadata?.symbol || ""}
      data-level-timeframe={levelMetadata?.timeframe || ""}
      data-level-as-of={levelMetadata?.as_of || ""}
    >
      <div className="snbr-tv-plot-area">
        <div className="tradingview-widget-container snbr-tv-widget" ref={containerRef} />
        {loadFailed ? (
          <div className="snbr-tv-fallback">
            <strong>{locale === "en-US" ? "TradingView chart could not load here." : "O gráfico TradingView não carregou aqui."}</strong>
            <a href={tradingViewUrl} rel="noreferrer" target="_blank">
              {locale === "en-US" ? "Open on TradingView" : "Abrir no TradingView"}
            </a>
          </div>
        ) : null}
      </div>
      {showLevelPane ? (
        <LevelLinesPane
          closes={paneCloses}
          overlays={levelOverlays}
          currencyPrefix={currencyPrefix}
          locale={locale}
        />
      ) : null}
      {/* `show_rsi` owns this panel and nothing else. Toggling a class instead of
          unmounting keeps the node in the tree, so switching the panel off never
          remounts the chart above it. The `.hidden` rule collapses the panel with
          display:none -- it does not reserve the space. */}
      <section
        className={`snbr-institutional-rsi-panel ${rsiPanelTone} ${showRsi ? "" : "hidden"}`}
        aria-hidden={!showRsi}
        aria-label={locale === "en-US" ? "Institutional RSI panel" : "Painel RSI institucional"}
      >
          <div className="snbr-institutional-rsi-head">
            <div>
              <strong>{rsiTitle}</strong>
              <span>
                {institutionalRsi == null
                  ? (rsiMetadata?.reason === "insufficient_candles"
                    ? (locale === "en-US" ? `Insufficient data: ${rsiMetadata.candle_count || 0} of ${rsiMetadata.required_count || 14} required candles.` : `Dados insuficientes: ${rsiMetadata.candle_count || 0} de ${rsiMetadata.required_count || 14} candles necessários.`)
                    : (locale === "en-US" ? "Institutional RSI temporarily unavailable." : "RSI institucional temporariamente indisponível."))
                  : (locale === "en-US"
                    ? `${rsiTitle} — computed on the ${rsiTimeframeTag || "chart"} candles shown. The top card always shows daily RSI (D1).`
                    : `${rsiTitle} — calculado nos candles ${rsiTimeframeTag || "do gráfico"} exibidos. O card do topo sempre mostra o RSI diário (D1).`)}
              </span>
            </div>
            <strong className="snbr-institutional-rsi-value">
              {institutionalRsi == null ? "n/a" : `${rsiTitle}: ${formatRsiValue(institutionalRsi, locale)}`}
            </strong>
          </div>
          {institutionalRsi == null ? (
            <div className="snbr-institutional-rsi-empty">
              {locale === "en-US"
                ? "The TradingView RSI study stays disabled; this panel is the only RSI on the chart and is waiting for data."
                : "O RSI do TradingView continua desativado; este painel é o único RSI do gráfico e aguarda dados."}
            </div>
          ) : (
            <div className="snbr-institutional-rsi-track" style={rsiPanelStyle}>
              <span className="snbr-rsi-zone oversold">{locale === "en-US" ? "Oversold" : "Sobrevenda"}</span>
              <span className="snbr-rsi-zone neutral">50</span>
              <span className="snbr-rsi-zone overbought">{locale === "en-US" ? "Overbought" : "Sobrecompra"}</span>
              <span className="snbr-rsi-threshold threshold-25">25</span>
              <span className="snbr-rsi-threshold threshold-50">50</span>
              <span className="snbr-rsi-threshold threshold-75">75</span>
              <span className="snbr-institutional-rsi-marker">
                <span>{rsiTitle}: {formatRsiValue(institutionalRsi, locale)}</span>
              </span>
            </div>
          )}
      </section>
    </div>
  );
}

export default TickerChart;
