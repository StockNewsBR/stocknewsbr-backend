"use client";

import { useEffect, useMemo, useRef, useState, type CSSProperties } from "react";
import type { ChartPayload } from "@/lib/types";
import { canonicalSymbol, tradingViewSymbolFor } from "@/lib/symbol-registry";

type Props = {
  chart: ChartPayload | null;
  ticker?: string;
  interval?: string;
  showMarkers?: boolean;
  showZones?: boolean;
  showPriceLine?: boolean;
  showVwap?: boolean;
  showAverages?: boolean;
  showMacd?: boolean;
  showRsi?: boolean;
  showSupertrend?: boolean;
  showVolume?: boolean;
  showSupport?: boolean;
  showResistance?: boolean;
  supportLevel?: number | null;
  resistanceLevel?: number | null;
  institutionalRsiValue?: number | null;
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

function buildStudies(showVwap: boolean, showAverages: boolean, showMacd: boolean) {
  const studies: string[] = [];
  if (showVwap) studies.push("VWAP@tv-basicstudies");
  if (showAverages) {
    studies.push("MASimple@tv-basicstudies");
  }
  if (showMacd) studies.push("MACD@tv-basicstudies");
  return studies;
}

function firstFiniteNumber(...values: Array<unknown>) {
  for (const value of values) {
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

function rsiToneClass(value: number) {
  if (value >= 70) return "overbought";
  if (value <= 30) return "oversold";
  if (value >= 55) return "bullish";
  if (value <= 45) return "bearish";
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

function priceToY(price: number, minPrice: number, maxPrice: number) {
  const span = Math.max(maxPrice - minPrice, Math.abs(price) * 0.0001, 0.0001);
  return 92 - ((price - minPrice) / span) * 84;
}

function buildPriceAnchoredLevelChart(
  chart: ChartPayload | null,
  levels: ChartLevelOverlay[],
) {
  const rows = (chart?.series?.length ? chart.series : chart?.ohlc || [])
    .map((row) => ({
      time: String(row.time || ""),
      close: Number(row.close),
      high: Number(row.high ?? row.close),
      low: Number(row.low ?? row.close),
    }))
    .filter((row) => Number.isFinite(row.close) && row.close > 0)
    .slice(-160);

  if (!rows.length) return null;

  const levelPrices = levels.map((level) => level.price).filter((price) => Number.isFinite(price) && price > 0);
  const rawMin = Math.min(...rows.map((row) => Number.isFinite(row.low) && row.low > 0 ? row.low : row.close), ...levelPrices);
  const rawMax = Math.max(...rows.map((row) => Number.isFinite(row.high) && row.high > 0 ? row.high : row.close), ...levelPrices);
  const padding = Math.max((rawMax - rawMin) * 0.08, rawMax * 0.001, 0.0001);
  const minPrice = Math.max(0, rawMin - padding);
  const maxPrice = rawMax + padding;

  const points = rows.map((row, index) => {
    const x = rows.length === 1 ? 50 : (index / (rows.length - 1)) * 100;
    const y = priceToY(row.close, minPrice, maxPrice);
    return { x, y, close: row.close, time: row.time };
  });

  const path = points.map((point, index) => `${index === 0 ? "M" : "L"} ${point.x.toFixed(3)} ${point.y.toFixed(3)}`).join(" ");
  const areaPath = `${path} L 100 96 L 0 96 Z`;
  const levelRows = levels.map((level) => ({
    ...level,
    y: priceToY(level.price, minPrice, maxPrice),
  }));

  return {
    path,
    areaPath,
    levels: levelRows,
    minPrice,
    maxPrice,
    latest: points[points.length - 1],
  };
}

export function TickerChart({
  chart,
  ticker,
  interval = "1D",
  showVwap = true,
  showAverages = true,
  showMacd = false,
  showRsi = false,
  showVolume = true,
  showSupport = true,
  showResistance = true,
  supportLevel = null,
  resistanceLevel = null,
  institutionalRsiValue = null,
  locale = "pt-BR",
}: Props) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const [theme, setTheme] = useState<"dark" | "light">("dark");
  const [loadFailed, setLoadFailed] = useState(false);
  const sourceSymbol = cleanSymbol(ticker || chart?.ticker);
  const tradingViewSymbol = useMemo(() => tradingViewSymbolFor(sourceSymbol), [sourceSymbol]);
  const timeframe = TIMEFRAME_TO_TRADING_VIEW[interval] || TIMEFRAME_TO_TRADING_VIEW["1D"];
  const tradingViewUrl = `https://www.tradingview.com/chart/?symbol=${encodeURIComponent(tradingViewSymbol)}`;
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
  const priceAnchoredChart = useMemo(
    () => buildPriceAnchoredLevelChart(chart, levelOverlays),
    [chart, levelOverlays],
  );
  const institutionalRsi = useMemo(() => {
    const numeric = firstFiniteNumber(institutionalRsiValue);
    if (numeric == null || numeric <= 0 || numeric > 100) return null;
    return numeric;
  }, [institutionalRsiValue]);
  const rsiPanelLabel = useMemo(() => {
    if (institutionalRsi == null) return null;
    return `RSI SCORE: ${formatRsiValue(institutionalRsi, locale)}`;
  }, [institutionalRsi, locale]);
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

    const widget = document.createElement("div");
    widget.className = "tradingview-widget-container__widget";
    widget.style.width = "100%";
    widget.style.height = "100%";
    container.appendChild(widget);

    const script = document.createElement("script");
    script.src = "https://s3.tradingview.com/external-embedding/embed-widget-advanced-chart.js";
    script.async = true;
    script.type = "text/javascript";
    script.onerror = () => setLoadFailed(true);
    script.innerHTML = JSON.stringify({
      autosize: true,
      symbol: tradingViewSymbol,
      interval: timeframe.interval,
      range: timeframe.range,
      timezone: tradingViewSymbol.startsWith("BMFBOVESPA:") ? "America/Sao_Paulo" : "Etc/UTC",
      theme,
      style: "1",
      locale: locale === "en-US" ? "en" : "br",
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
      studies: buildStudies(showVwap, showAverages, showMacd),
      studies_overrides: JSON.stringify({
        "vwap.plot.color": "#f59e0b",
        "vwap.plot.linewidth": 3,
        "VWAP.plot.color": "#f59e0b",
        "VWAP.plot.linewidth": 3,
        "moving average.length": 9,
        "moving average.ma.color": "#38bdf8",
      }),
    });

    container.appendChild(script);

    return () => {
      container.innerHTML = "";
    };
  }, [tradingViewSymbol, timeframe.interval, timeframe.range, theme, locale, showVwap, showAverages, showMacd, showVolume]);

  return (
    <div className="snbr-chart-shell snbr-tv-widget-shell">
      <div className="snbr-tv-plot-area">
        <div className="tradingview-widget-container snbr-tv-widget" ref={containerRef} />
        {rsiPanelLabel || levelOverlays.length ? (
          <div className="snbr-chart-top-overlays" aria-hidden="true">
            <div className={`snbr-chart-panel-rsi-badge ${showRsi && rsiPanelLabel ? "" : "hidden"}`}>
              {rsiPanelLabel || "RSI SCORE: --"}
            </div>
            {levelOverlays.length ? (
              <div className="snbr-chart-level-overlays">
                {levelOverlays.map((level) => (
                  <div
                    key={level.key}
                    className={`snbr-chart-level-overlay ${level.key}`}
                  >
                    <span>
                      {level.label}: {formatLevelPrice(level.price, locale)}
                    </span>
                  </div>
                ))}
              </div>
            ) : null}
          </div>
        ) : null}
        {priceAnchoredChart ? (
          <div
            className="snbr-chart-level-lines"
            data-price-anchored="true"
            data-support-price={supportLevel ?? undefined}
            data-resistance-price={resistanceLevel ?? undefined}
            aria-hidden="true"
          >
            <svg className="snbr-chart-level-svg" viewBox="0 0 100 100" preserveAspectRatio="none">
              <path className="snbr-chart-level-area" d={priceAnchoredChart.areaPath} />
              <path className="snbr-chart-level-price-path" d={priceAnchoredChart.path} />
              {priceAnchoredChart.levels.map((level) => (
                <g key={level.key} className={`snbr-chart-level-group ${level.key}`}>
                  <line
                    className={`snbr-chart-level-line ${level.key}`}
                    x1="0"
                    x2="100"
                    y1={level.y}
                    y2={level.y}
                    data-price={level.price}
                  />
                  <text
                    className={`snbr-chart-level-label ${level.key}`}
                    x="98"
                    y={Math.max(7, level.y - 1)}
                    textAnchor="end"
                  >
                    {level.label}: {formatLevelPrice(level.price, locale)}
                  </text>
                </g>
              ))}
              <circle
                className="snbr-chart-level-latest-dot"
                cx={priceAnchoredChart.latest.x}
                cy={priceAnchoredChart.latest.y}
                r="0.9"
              />
            </svg>
          </div>
        ) : null}
        {loadFailed ? (
          <div className="snbr-tv-fallback">
            <strong>{locale === "en-US" ? "TradingView chart could not load here." : "O gráfico TradingView não carregou aqui."}</strong>
            <a href={tradingViewUrl} rel="noreferrer" target="_blank">
              {locale === "en-US" ? "Open on TradingView" : "Abrir no TradingView"}
            </a>
          </div>
        ) : null}
      </div>
      <section
        className={`snbr-institutional-rsi-panel ${rsiPanelTone} ${showRsi ? "" : "hidden"}`}
        aria-hidden={!showRsi}
        aria-label={locale === "en-US" ? "Institutional RSI panel" : "Painel RSI institucional"}
      >
          <div className="snbr-institutional-rsi-head">
            <div>
              <strong>RSI SCORE</strong>
              <span>
                {institutionalRsi == null
                  ? (locale === "en-US" ? "No institutional RSI in the current payload." : "Sem RSI institucional no payload atual.")
                  : (locale === "en-US"
                    ? "Same snapshot/ranking value used by the top card."
                    : "Mesmo valor do snapshot/ranking usado no card do topo.")}
              </span>
            </div>
            <strong className="snbr-institutional-rsi-value">
              {institutionalRsi == null ? "n/a" : `RSI SCORE: ${formatRsiValue(institutionalRsi, locale)}`}
            </strong>
          </div>
          {institutionalRsi == null ? (
            <div className="snbr-institutional-rsi-empty">
              {locale === "en-US"
                ? "The TradingView RSI remains disabled to avoid divergent reads."
                : "O RSI do TradingView continua desativado para evitar leituras divergentes."}
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
                <span>RSI SCORE: {formatRsiValue(institutionalRsi, locale)}</span>
              </span>
            </div>
          )}
      </section>
    </div>
  );
}

export default TickerChart;
