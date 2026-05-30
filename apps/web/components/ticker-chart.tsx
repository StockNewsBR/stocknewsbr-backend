"use client";

import { useEffect, useState } from "react";
import type { ChartMarker, ChartPayload, ChartZone } from "@/lib/types";

type CandleRow = {
  time: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  sessionBoundary?: boolean;
};

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
  locale?: "pt-BR" | "en-US";
};

function clamp(value: number, min: number, max: number) {
  return Math.min(max, Math.max(min, value));
}

function normalizeNumber(value: unknown): number | null {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function formatAxisTime(value: unknown, interval = "1D", locale: "pt-BR" | "en-US" = "pt-BR") {
  const date = new Date(String(value || ""));
  if (Number.isNaN(date.getTime())) return "";

  const normalizedInterval = String(interval || "1D").toUpperCase();
  const dateLocale = locale === "en-US" ? "en-US" : "pt-BR";
  if (normalizedInterval === "1D") {
    return date.toLocaleTimeString(dateLocale, { hour: "2-digit", minute: "2-digit" });
  }
  if (["1W", "1M", "3M", "6M", "YTD"].includes(normalizedInterval)) {
    return date.toLocaleDateString(dateLocale, { day: "2-digit", month: "2-digit" });
  }
  return date.toLocaleDateString(dateLocale, { month: "short", year: "2-digit" }).replace(".", "");
}

function formatTooltipTime(value: unknown, interval = "1D", locale: "pt-BR" | "en-US" = "pt-BR") {
  const date = new Date(String(value || ""));
  if (Number.isNaN(date.getTime())) return locale === "en-US" ? "Date unavailable" : "Data indisponivel";

  const normalizedInterval = String(interval || "1D").toUpperCase();
  const datePart = date.toLocaleDateString(locale === "en-US" ? "en-US" : "pt-BR", { day: "2-digit", month: "2-digit", year: "numeric" });
  if (normalizedInterval === "1D") {
    return `${datePart} ${date.toLocaleTimeString(locale === "en-US" ? "en-US" : "pt-BR", { hour: "2-digit", minute: "2-digit" })}`;
  }
  return datePart;
}

function formatPrice(value: unknown, locale: "pt-BR" | "en-US" = "pt-BR") {
  const parsed = normalizeNumber(value);
  return parsed == null
    ? "n/a"
    : parsed.toLocaleString(locale === "en-US" ? "en-US" : "pt-BR", { maximumFractionDigits: 2 });
}

function formatCompact(value: unknown, locale: "pt-BR" | "en-US" = "pt-BR") {
  const parsed = normalizeNumber(value);
  return parsed == null
    ? "n/a"
    : new Intl.NumberFormat(locale === "en-US" ? "en-US" : "pt-BR", { notation: "compact", maximumFractionDigits: 1 }).format(parsed);
}

function truncateText(value: unknown, maxLength = 74) {
  const text = String(value || "").trim();
  if (!text) return "Nao informado pelo provider";
  return text.length > maxLength ? `${text.slice(0, maxLength - 1)}...` : text;
}

function markerActionLabel(marker: ChartMarker, locale: "pt-BR" | "en-US" = "pt-BR") {
  const explicit = String(marker.action_label || marker.label || "").trim();
  if (explicit) {
    const normalized = explicit.toUpperCase();
    if (normalized === "BUY") return "Buy Long";
    if (normalized === "SELL" || normalized === "CLOSE LONG") return locale === "en-US" ? "Close Long" : "Encerrar long";
    if (normalized === "SHORT") return "Sell Short";
    if (normalized === "COVER" || normalized === "CLOSE SHORT") return locale === "en-US" ? "Close Short" : "Encerrar short";
    return explicit;
  }

  const type = String(marker.type || "").toUpperCase();
  if (type === "BUY") return "Buy Long";
  if (type === "SELL") return locale === "en-US" ? "Close Long" : "Encerrar long";
  if (type === "SHORT") return "Sell Short";
  if (type === "COVER") return locale === "en-US" ? "Close Short" : "Encerrar short";
  return "Watch";
}

function localizeChartText(value: unknown, locale: "pt-BR" | "en-US") {
  const text = String(value || "").trim();
  if (locale !== "en-US" || !text) return text;
  return text
    .replace(/Entrada long/gi, "Long entry")
    .replace(/Saida long|Saída long/gi, "Long exit")
    .replace(/Entrada short/gi, "Short entry")
    .replace(/Saida short|Saída short/gi, "Short exit")
    .replace(/Aguardar confirmacao/gi, "Wait for confirmation")
    .replace(/Aguardar/g, "Wait")
    .replace(/Observar/g, "Watch")
    .replace(/Pivo tecnico derivado; nao e entrada operacional sem confirmacao\./gi, "Derived technical pivot; not an operational entry without confirmation.")
    .replace(/Confirmar com volume, VWAP\/EMA21 e fluxo institucional no mesmo lado\./gi, "Confirm with volume, VWAP/EMA21 and institutional flow on the same side.")
    .replace(/Ignorar se romper o pivo sem defesa ou se o regime\/fluxo apontar contra\./gi, "Ignore if the pivot breaks without defense or regime/flow points against it.")
    .replace(/Risco medio: pivo derivado pode virar falso sinal em mercado lateral\./gi, "Medium risk: derived pivot can become a false signal in a range.")
    .replace(/Aguardar preco, volume e regime confirmarem antes de operar\./gi, "Wait for price, volume and regime to confirm before trading.")
    .replace(/Nao usar como trade se faltar preco real, volume ou leitura de fluxo\./gi, "Do not use as a trade if real price, volume or flow read is missing.")
    .replace(/Risco medio: fallback visual existe para orientar observacao, nao para executar ordem\./gi, "Medium risk: visual fallback guides observation, not order execution.")
    .replace(/Invalidar se a tese perder preco, VWAP\/EMA21, volume ou regime\./gi, "Invalidate if the thesis loses price, VWAP/EMA21, volume or regime.")
    .replace(/Risco ([^:]+): confirmar liquidez antes de operar\./gi, "Risk $1: confirm liquidity before trading.")
    .replace(/Aguardar confirmacao de preco, volume e fluxo\./gi, "Wait for price, volume and flow confirmation.")
    .replace(/medio/gi, "medium")
    .replace(/baixo/gi, "low")
    .replace(/alto/gi, "high")
    .replace(/alta/gi, "uptrend")
    .replace(/baixa/gi, "downtrend")
    .replace(/lateral/gi, "range")
    .replace(/resistencia/gi, "resistance")
    .replace(/suporte/gi, "support")
    .replace(/RESISTENCIA/g, "RESISTANCE")
    .replace(/SUPORTE/g, "SUPPORT");
}

function localizeInvalidation(value: unknown, locale: "pt-BR" | "en-US") {
  const text = localizeChartText(value, locale);
  if (/^(se|if)\s*:/i.test(text)) return text;
  return `${locale === "en-US" ? "IF:" : "Se:"} ${text}`;
}

function markerOperationalNote(marker: ChartMarker, locale: "pt-BR" | "en-US" = "pt-BR") {
  const explicit = String(marker.operational_note || "").trim();
  if (explicit) return localizeChartText(explicit, locale);

  const type = String(marker.type || "").toUpperCase();
  if (type === "BUY") return locale === "en-US" ? "Long entry" : "Entrada long";
  if (type === "SELL") return locale === "en-US" ? "Long exit" : "Saida long";
  if (type === "SHORT") return locale === "en-US" ? "Short entry" : "Entrada short";
  if (type === "COVER") return locale === "en-US" ? "Short exit" : "Saida short";
  return marker.derived ? (locale === "en-US" ? "Wait for confirmation" : "Aguardar confirmacao") : (locale === "en-US" ? "Watch" : "Observar");
}

function markerReason(marker: ChartMarker, locale: "pt-BR" | "en-US" = "pt-BR") {
  const reason = String(marker.reason_text || marker.reason || "").trim();
  if (reason) return localizeChartText(reason, locale);
  return marker.derived
    ? (locale === "en-US" ? "Derived technical read" : "Leitura tecnica derivada")
    : (locale === "en-US" ? "Operational chart signal" : "Sinal operacional do grafico");
}

function markerLabelLines(label: string) {
  const parts = label.trim().split(/\s+/).filter(Boolean);
  if (parts.length <= 1) return [label];
  return [parts.slice(0, -1).join(" "), parts.at(-1) || ""];
}

function isOneDayInterval(interval: string) {
  return String(interval || "1D").toUpperCase() === "1D";
}

function displayIntervalLabel(interval: string, locale: "pt-BR" | "en-US" = "pt-BR") {
  return isOneDayInterval(interval)
    ? (locale === "en-US" ? "5 min" : "5 min")
    : String(interval || "1D").toUpperCase();
}

function usesB3Session(symbol?: string | null) {
  return /^[A-Z]{4}\d{1,2}/i.test(String(symbol || ""));
}

function isB3MiniFutureTicker(symbol?: string | null) {
  const compact = String(symbol || "").toUpperCase().replace(/\.SA$/, "");
  return /^(WIN|WDO)[FGHJKMNQUVXZ]\d{2}$/.test(compact);
}

function isCryptoTicker(symbol?: string | null) {
  return /^(BTC|ETH|XRP|DOGE|SOL|ADA|BNB|LTC|BCH|DOT|AVAX|MATIC)(USD|USDT)?$/i.test(String(symbol || ""));
}

type SessionProfile = {
  timezone: string;
  regularStart: number;
  regularEnd: number;
  supportsExtended: boolean;
  note: string;
};

type SessionSegment = {
  start: number;
  end: number;
};

const timeFormatterCache = new Map<string, Intl.DateTimeFormat>();

function getTimeFormatter(timezone: string) {
  const cached = timeFormatterCache.get(timezone);
  if (cached) return cached;
  const formatter = new Intl.DateTimeFormat("en-US", {
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
    timeZone: timezone,
  });
  timeFormatterCache.set(timezone, formatter);
  return formatter;
}

function minutesInTimeZone(value: unknown, timezone: string) {
  const date = new Date(String(value || ""));
  if (Number.isNaN(date.getTime())) return null;
  const parts = getTimeFormatter(timezone).formatToParts(date);
  const hour = Number(parts.find((part) => part.type === "hour")?.value);
  const minute = Number(parts.find((part) => part.type === "minute")?.value);
  if (!Number.isFinite(hour) || !Number.isFinite(minute)) return null;
  return (hour % 24) * 60 + minute;
}

function getSessionProfile(symbol?: string | null): SessionProfile | null {
  if (isCryptoTicker(symbol)) return null;
  if (usesB3Session(symbol)) {
    return {
      timezone: "America/Sao_Paulo",
      regularStart: 10 * 60,
      regularEnd: 18 * 60,
      supportsExtended: false,
      note: "Sessão: B3 regular; provider público inicia perto de 10:00",
    };
  }
  return {
    timezone: "America/New_York",
    regularStart: 9 * 60 + 30,
    regularEnd: 16 * 60,
    supportsExtended: true,
    note: "Sessão: EUA com pré/after-hours quando o provider entrega",
  };
}

function isExtendedSessionPoint(item: any, symbol?: string | null) {
  const profile = getSessionProfile(symbol);
  if (!profile?.supportsExtended || item?.sessionBoundary) return false;
  const minutes = minutesInTimeZone(item?.time, profile.timezone);
  if (minutes == null) return false;
  return minutes < profile.regularStart || minutes >= profile.regularEnd;
}

function buildExtendedSessionSegments(series: any[], symbol?: string | null): SessionSegment[] {
  const segments: SessionSegment[] = [];
  let current: SessionSegment | null = null;

  series.forEach((item, index) => {
    if (isExtendedSessionPoint(item, symbol)) {
      if (!current) current = { start: index, end: index };
      current.end = index;
      return;
    }

    if (current) {
      segments.push(current);
      current = null;
    }
  });

  if (current) segments.push(current);
  return segments;
}

function atSessionTime(source: Date, hour: number, minute: number) {
  const date = new Date(source);
  date.setHours(hour, minute, 0, 0);
  return date;
}

function buildSessionBoundary(
  time: Date,
  reference: any,
  referenceOhlc: any,
) {
  const close = normalizeNumber(referenceOhlc?.close) ?? normalizeNumber(reference?.close) ?? 0;
  return {
    series: {
      ...reference,
      time: time.toISOString(),
      close,
      ema9: normalizeNumber(reference?.ema9) ?? close,
      ema21: normalizeNumber(reference?.ema21) ?? close,
      supertrend: normalizeNumber(reference?.supertrend) ?? close,
      sessionBoundary: true,
    },
    ohlc: {
      time: time.toISOString(),
      open: close,
      high: close,
      low: close,
      close,
      volume: 0,
      sessionBoundary: true,
    },
  };
}

function padOneDaySession(series: any[], ohlc: any[], ticker?: string | null) {
  if (!series.length) return { series, ohlc };
  const firstTime = new Date(String(series[0]?.time || ohlc[0]?.time || ""));
  const lastTime = new Date(String(series[series.length - 1]?.time || ohlc[ohlc.length - 1]?.time || ""));
  if (Number.isNaN(firstTime.getTime()) || Number.isNaN(lastTime.getTime())) return { series, ohlc };

  const isB3 = usesB3Session(ticker);
  const sessionStart = atSessionTime(firstTime, isB3 ? 10 : 4, isB3 ? 0 : 0);
  const sessionEnd = atSessionTime(firstTime, isB3 ? 18 : 20, 0);
  const paddedSeries = [...series];
  const paddedOhlc = ohlc.length ? [...ohlc] : series.map((item) => ({
    time: item.time,
    open: item.close,
    high: item.close,
    low: item.close,
    close: item.close,
    volume: 0,
  }));

  if (firstTime.getTime() > sessionStart.getTime() + 60_000) {
    const boundary = buildSessionBoundary(sessionStart, paddedSeries[0], paddedOhlc[0]);
    paddedSeries.unshift(boundary.series);
    paddedOhlc.unshift(boundary.ohlc);
  }

  if (lastTime.getTime() < sessionEnd.getTime() - 60_000) {
    const boundary = buildSessionBoundary(sessionEnd, paddedSeries[paddedSeries.length - 1], paddedOhlc[paddedOhlc.length - 1]);
    paddedSeries.push(boundary.series);
    paddedOhlc.push(boundary.ohlc);
  }

  return { series: paddedSeries, ohlc: paddedOhlc };
}

function pickTickIndexes(length: number, maxTicks = 7) {
  if (length <= 0) return [];
  if (length <= maxTicks) return Array.from({ length }, (_, index) => index);

  const indexes = new Set<number>();
  const last = length - 1;
  for (let step = 0; step < maxTicks; step += 1) {
    indexes.add(Math.round((step * last) / (maxTicks - 1)));
  }
  return Array.from(indexes).sort((a, b) => a - b);
}

function average(values: number[]) {
  const finite = values.filter((value) => Number.isFinite(value));
  if (!finite.length) return 0;
  return finite.reduce((total, value) => total + value, 0) / finite.length;
}

function buildVwap(candles: CandleRow[]) {
  let cumulativePriceVolume = 0;
  let cumulativeVolume = 0;
  return candles.map((bar) => {
    const typicalPrice = (bar.high + bar.low + bar.close) / 3;
    const volume = Number.isFinite(bar.volume) && bar.volume > 0 ? bar.volume : 1;
    cumulativePriceVolume += typicalPrice * volume;
    cumulativeVolume += volume;
    return cumulativePriceVolume / Math.max(cumulativeVolume, 1);
  });
}

function buildEma(values: number[], period: number) {
  if (!values.length) return [];
  const multiplier = 2 / (period + 1);
  return values.reduce<number[]>((rows, value, index) => {
    rows.push(index === 0 ? value : (value - rows[index - 1]) * multiplier + rows[index - 1]);
    return rows;
  }, []);
}

function buildMacdHistogram(closes: number[]) {
  const ema12 = buildEma(closes, 12);
  const ema26 = buildEma(closes, 26);
  const macd = closes.map((_, index) => (ema12[index] || 0) - (ema26[index] || 0));
  const signal = buildEma(macd, 9);
  return macd.map((value, index) => value - (signal[index] || 0));
}

function buildRsi(closes: number[], period = 14) {
  return closes.map((_, index) => {
    if (index === 0) return 50;
    const start = Math.max(1, index - period + 1);
    let gains = 0;
    let losses = 0;
    for (let cursor = start; cursor <= index; cursor += 1) {
      const change = closes[cursor] - closes[cursor - 1];
      if (change >= 0) gains += change;
      else losses += Math.abs(change);
    }
    if (losses === 0) return gains > 0 ? 100 : 50;
    const rs = gains / losses;
    return 100 - 100 / (1 + rs);
  });
}

function buildDerivedZones(candles: CandleRow[]): ChartZone[] {
  if (candles.length < 2) return [];
  const highs = candles.map((item) => item.high).filter((value) => Number.isFinite(value));
  const lows = candles.map((item) => item.low).filter((value) => Number.isFinite(value));
  if (!highs.length || !lows.length) return [];

  return [
    { label: "RESISTENCIA", price: Math.max(...highs) },
    { label: "SUPORTE", price: Math.min(...lows) },
  ];
}

function buildDerivedMarkers(candles: CandleRow[]): ChartMarker[] {
  if (candles.length < 6) return [];

  const avgVolume = Math.max(average(candles.map((item) => item.volume)), 1);
  const markers: ChartMarker[] = [];

  for (let index = 2; index < candles.length - 2; index += 1) {
    const bar = candles[index];
    const previous = candles[index - 1];
    const next = candles[index + 1];
    const prevTwo = candles[index - 2];
    const nextTwo = candles[index + 2];
    const range = Math.max(bar.high - bar.low, Math.abs(bar.close) * 0.001, 0.0001);
    const body = bar.close - bar.open;
    const relativeVolume = bar.volume / avgVolume;
    const swingLow = bar.low <= previous.low && bar.low <= next.low && bar.low <= prevTwo.low && bar.low <= nextTwo.low;
    const swingHigh = bar.high >= previous.high && bar.high >= next.high && bar.high >= prevTwo.high && bar.high >= nextTwo.high;
    const bullishReversal = swingLow && body > 0 && next.close >= bar.close;
    const bearishReversal = swingHigh && body < 0 && next.close <= bar.close;

    if (!bullishReversal && !bearishReversal) continue;

    const side: "buy" | "sell" = bullishReversal ? "buy" : "sell";
    markers.push({
      time: String(bar.time || ""),
      price: side === "buy" ? bar.low + range * 0.18 : bar.high - range * 0.18,
      side: "neutral",
      type: "WATCH",
      label: "Watch",
      action_label: "Watch",
      operational_note: "Aguardar confirmacao",
      score: clamp(Math.round((Math.abs(body) / range) * 8 + relativeVolume * 2), 1, 14),
      reason: side === "buy" ? "swing_low_watch" : "swing_high_watch",
      reason_text: "Pivo tecnico derivado; nao e entrada operacional sem confirmacao.",
      trigger: "Confirmar com volume, VWAP/EMA21 e fluxo institucional no mesmo lado.",
      invalidation: "Ignorar se romper o pivo sem defesa ou se o regime/fluxo apontar contra.",
      risk: "Risco medio: pivo derivado pode virar falso sinal em mercado lateral.",
      risk_level: "medio",
      coherence_status: "derived_watch",
      derived: true,
    });

    if (markers.length >= 16) break;
  }

  if (markers.length >= 3) return markers;

  const fallbackIndexes = [0.18, 0.36, 0.56, 0.74, 0.9]
    .map((ratio) => Math.min(candles.length - 2, Math.max(1, Math.round((candles.length - 1) * ratio))))
    .filter((index, position, indexes) => indexes.indexOf(index) === position);

  return fallbackIndexes.map((index, markerIndex) => {
    const bar = candles[index];
    const side: "buy" | "sell" = markerIndex % 2 === 0 ? "buy" : "sell";
    return {
      time: String(bar.time || ""),
      price: side === "buy" ? bar.low : bar.high,
      side: "neutral",
      type: "WATCH",
      label: "Watch",
      action_label: "Watch",
      operational_note: "Aguardar confirmacao",
      score: markerIndex + 5,
      reason: "fallback_watch",
      reason_text: "Marcador tecnico de cobertura visual; faltou sinal institucional confirmado.",
      trigger: "Aguardar preco, volume e regime confirmarem antes de operar.",
      invalidation: "Nao usar como trade se faltar preco real, volume ou leitura de fluxo.",
      risk: "Risco medio: fallback visual existe para orientar observacao, nao para executar ordem.",
      risk_level: "medio",
      coherence_status: "derived_watch",
      derived: true,
    };
  });
}

export function TickerChart({
  chart,
  ticker,
  interval = "1D",
  showMarkers = true,
  showZones = true,
  showPriceLine = true,
  showVwap = true,
  showAverages = true,
  showMacd = false,
  showRsi = false,
  showSupertrend = true,
  showVolume = true,
  locale = "pt-BR",
}: Props) {
  const isEnglish = locale === "en-US";
  const [hoverPoint, setHoverPoint] = useState<{
    x: number;
    y: number;
    time: string;
    close: number;
    open: number;
    high: number;
    low: number;
    volume: number;
  } | null>(null);
  const [hoverMarker, setHoverMarker] = useState<{
    x: number;
    y: number;
    rows: Array<{ label: string; value: string }>;
    title: string;
    side: string;
  } | null>(null);
  const [windowStart, setWindowStart] = useState(0);
  const [windowSize, setWindowSize] = useState<number | null>(null);
  const rawSeries = chart?.series || [];
  const rawOhlc = chart?.ohlc || [];
  const baseSeries = rawSeries.length
    ? rawSeries
    : rawOhlc.map((item: any) => ({
        time: item.time,
        close: item.close,
        ema9: item.close,
        ema21: item.close,
        supertrend: item.close,
        supertrend_side: "neutral",
      }));
  const sessionPadded = isOneDayInterval(interval)
    ? padOneDaySession(baseSeries, rawOhlc, chart?.summary?.ticker || chart?.ticker)
    : { series: baseSeries, ohlc: rawOhlc };
  const displaySeries = sessionPadded.series;
  const ohlc = sessionPadded.ohlc;

  useEffect(() => {
    setWindowStart(0);
    setWindowSize(null);
    setHoverPoint(null);
    setHoverMarker(null);
  }, [chart?.ticker, chart?.interval, interval, displaySeries.length]);

  if (!displaySeries.length) {
    const chartSummary = (chart?.summary || {}) as Record<string, unknown>;
    const chartTicker = String(chartSummary.ticker || chart?.ticker || ticker || "");
    const providerStatus = String(chartSummary.provider_status || (chart as any)?.provider_status || chartSummary.source || "").toLowerCase();
    const isUnavailableB3Future = isB3MiniFutureTicker(chartTicker) && (!providerStatus || providerStatus === "empty_chart" || providerStatus === "b3_future_exact_chart_unavailable");
    const message = isUnavailableB3Future
      ? (isEnglish
          ? "No reliable real B3 futures chart from the public provider. Synthetic/proxy candles were blocked to avoid a wrong chart."
          : "Sem gráfico real confiável para este futuro B3 no provider público. Candles sintéticos/proxy foram bloqueados para evitar gráfico errado.")
      : (isEnglish ? "Not enough historical series to draw the chart yet." : "Sem série histórica suficiente para desenhar o gráfico ainda.");
    return <div className="snbr-empty">{message}</div>;
  }

  const minWindowSize = Math.min(displaySeries.length, 12);
  const effectiveWindowSize = clamp(Math.round(windowSize ?? displaySeries.length), minWindowSize, displaySeries.length);
  const maxWindowStart = Math.max(0, displaySeries.length - effectiveWindowSize);
  const effectiveWindowStart = clamp(windowStart, 0, maxWindowStart);
  const effectiveWindowEnd = effectiveWindowStart + effectiveWindowSize;
  const series = displaySeries.slice(effectiveWindowStart, effectiveWindowEnd);
  const visibleOhlc = ohlc.slice(effectiveWindowStart, effectiveWindowEnd);
  const panStep = Math.max(1, Math.floor(effectiveWindowSize * 0.35));
  const canPanLeft = effectiveWindowStart > 0;
  const canPanRight = effectiveWindowStart < maxWindowStart;
  const canZoomIn = effectiveWindowSize > minWindowSize;
  const canZoomOut = effectiveWindowSize < displaySeries.length;

  const width = 960;
  const height = 430;
  const paddingX = 42;
  const paddingTop = 34;
  const paddingBottom = 72;
  const plotBottom = height - paddingBottom;
  const plotWidth = width - paddingX * 2;
  const plotHeight = plotBottom - paddingTop;
  const closes = series.map((item) => Number(item.close || 0));
  const ema9 = series.map((item) => Number(item.ema9 || item.close || 0));
  const ema21 = series.map((item) => Number(item.ema21 || item.close || 0));
  const supertrend = series.map((item) => normalizeNumber(item.supertrend));
  const candleRows = series.map((item, index) => {
    const raw = visibleOhlc[index] || {};
    const close = normalizeNumber(raw.close) ?? normalizeNumber(item.close) ?? 0;
    return {
      time: raw.time || item.time,
      open: normalizeNumber(raw.open) ?? close,
      high: normalizeNumber(raw.high) ?? close,
      low: normalizeNumber(raw.low) ?? close,
      close,
      volume: normalizeNumber(raw.volume) ?? 0,
      sessionBoundary: Boolean(raw.sessionBoundary || (item as any).sessionBoundary),
    };
  });
  const vwap = buildVwap(candleRows);
  const macdHistogram = buildMacdHistogram(closes);
  const rsiSeries = buildRsi(closes);
  const allValues = [
    ...closes,
    ...ema9,
    ...ema21,
    ...vwap,
    ...supertrend.filter((value): value is number => value != null),
    ...candleRows.flatMap((item) => [item.open, item.high, item.low, item.close]),
  ].filter((value) => Number.isFinite(value));
  const minValue = Math.min(...allValues);
  const maxValue = Math.max(...allValues);
  const valueRange = Math.max(maxValue - minValue, 0.0001);

  function toY(value: number) {
    return clamp(
      plotBottom - ((value - minValue) / valueRange) * plotHeight,
      paddingTop,
      plotBottom,
    );
  }

  function toX(index: number) {
    return paddingX + (index * plotWidth) / Math.max(series.length - 1, 1);
  }

  function buildPath(values: number[]) {
    return values
      .map((value, index) => `${index === 0 ? "M" : "L"} ${toX(index)} ${toY(value)}`)
      .join(" ");
  }

  const closePath = buildPath(closes);
  const ema9Path = buildPath(ema9);
  const ema21Path = buildPath(ema21);
  const vwapPath = buildPath(vwap);
  const indicatorTop = plotBottom - 58;
  const indicatorHeight = 42;
  const macdMax = Math.max(...macdHistogram.map((value) => Math.abs(value)).filter((value) => Number.isFinite(value)), 0.0001);
  const macdZeroY = indicatorTop + indicatorHeight / 2;
  const rsiPath = rsiSeries
    .map((value, index) => {
      const y = indicatorTop + ((100 - clamp(value, 0, 100)) / 100) * indicatorHeight;
      return `${index === 0 ? "M" : "L"} ${toX(index)} ${y}`;
    })
    .join(" ");
  const supertrendSegments = supertrend.reduce<Array<{ side: string; path: string }>>((segments, value, index) => {
    if (value == null) return segments;
    const side = String(series[index]?.supertrend_side || "neutral");
    const command = segments.length && segments[segments.length - 1].side === side ? "L" : "M";
    const point = `${command} ${toX(index)} ${toY(value)}`;
    const current = segments[segments.length - 1];
    if (current && current.side === side) {
      current.path = `${current.path} ${point}`;
    } else {
      segments.push({ side, path: point });
    }
    return segments;
  }, []);
  const timeToIndex = new Map(series.map((item, index) => [String(item.time || ""), index]));
  const candleWidth = clamp((plotWidth / Math.max(series.length, 1)) * 0.58, 3, 9);
  const xTicks = pickTickIndexes(series.length, 8);
  const verticalGridTicks = pickTickIndexes(series.length, 13);
  const latestClose = closes[closes.length - 1] ?? 0;
  const latestOpen = candleRows[candleRows.length - 1]?.open ?? latestClose;
  const latestIsUp = latestClose >= latestOpen;
  const latestY = toY(latestClose);
  const derivedTrendBias = chart?.summary?.trend_bias || (latestClose > latestOpen ? "alta" : latestClose < latestOpen ? "baixa" : "lateral");
  const derivedClose = normalizeNumber(chart?.summary?.latest_close) ?? latestClose;
  const volumeValues = candleRows.map((item) => item.volume).filter((value) => Number.isFinite(value));
  const maxVolume = Math.max(...volumeValues, 1);
  const volumeTop = plotBottom + 18;
  const volumeHeight = 28;
  const volumeBarWidth = clamp((plotWidth / Math.max(candleRows.length, 1)) * 0.54, 2, 6);
  const yTicks = pickTickIndexes(5, 5);
  const tradableCandleRows = candleRows.filter((item) => !item.sessionBoundary);
  const isSyntheticFallbackChart = Boolean(chart?.fallback || chart?.synthetic || chart?.summary?.fallback || chart?.summary?.synthetic || chart?.summary?.source === "quote_visual_fallback");
  const zoneRows = showZones ? (chart?.zones?.length ? chart.zones : buildDerivedZones(tradableCandleRows)) : [];
  const rawMarkerRows = showMarkers ? (chart?.markers?.length ? chart.markers : (isSyntheticFallbackChart ? [] : buildDerivedMarkers(tradableCandleRows))) : [];
  const markerRows = rawMarkerRows.filter((marker) => !marker.time || timeToIndex.has(String(marker.time || "")));
  const activeToolCount = [
    showMarkers,
    showZones,
    showPriceLine,
    showVwap,
    showAverages,
    showMacd,
    showRsi,
    showSupertrend,
    showVolume,
  ].filter(Boolean).length;
  const currentTicker = chart?.summary?.ticker || chart?.ticker;
  const chartIntervalLabel = displayIntervalLabel(interval, locale);
  const sessionProfile = isOneDayInterval(interval) ? getSessionProfile(currentTicker) : null;
  const extendedSessionSegments = isOneDayInterval(interval)
    ? buildExtendedSessionSegments(series, currentTicker)
    : [];

  const markerAnchors = markerRows.map((marker, markerIndex) => {
        const normalizedTime = String(marker.time || "");
        let index = timeToIndex.get(normalizedTime);

        if (index == null) {
          index = Math.max(series.length - 1 - markerIndex, 0);
        }

        const anchorValue = normalizeNumber(marker.price) ?? closes[index] ?? closes[closes.length - 1] ?? 0;
        const x = toX(index);
        const y = toY(anchorValue);
        const side = marker.side === "buy" || marker.side === "sell" ? marker.side : "neutral";
        const direction = side === "buy" ? -1 : side === "sell" ? 1 : -1;
        const stemEndY = clamp(y + direction * 28, paddingTop + 10, plotBottom - 10);
        const label = markerActionLabel(marker, locale);
        const labelLines = markerLabelLines(label);
        const operationalNote = markerOperationalNote(marker, locale);
        const fill = side === "buy" ? "#22c55e" : side === "sell" ? "#ff4d57" : "#f59e0b";
        const stroke = side === "buy" ? "#0b6a45" : side === "sell" ? "#8f2838" : "#92400e";
        const lineEndX = markerIndex < markerRows.length - 1
          ? toX(timeToIndex.get(String(markerRows[markerIndex + 1]?.time || "")) ?? Math.min(index + 18, series.length - 1))
          : width - paddingX;
        const tooltipRows = [
          { label: isEnglish ? "Time" : "Horario", value: formatTooltipTime(marker.time || series[index]?.time, interval, locale) },
          { label: isEnglish ? "Reason" : "Motivo", value: markerReason(marker, locale) },
          { label: "Trigger", value: localizeChartText(marker.trigger || marker.confirmation || "Aguardar confirmacao de preco, volume e fluxo.", locale) },
          { label: isEnglish ? "Invalidation" : "Invalidacao", value: localizeInvalidation(marker.invalidation || "Invalidar se a tese perder preco, VWAP/EMA21, volume ou regime.", locale) },
          { label: isEnglish ? "Risk" : "Risco", value: localizeChartText(marker.risk || `Risco ${marker.risk_level || "medio"}: confirmar liquidez antes de operar.`, locale) },
        ];
        const tooltipTitle = tooltipRows.map((row) => `${row.label}: ${row.value}`).join("\n");

        return {
          key: `${normalizedTime || "marker"}-${markerIndex}`,
          index,
          x,
          y,
          lineEndX,
          stemEndY,
          label,
          fill,
          stroke,
          side,
          price: anchorValue,
          score: normalizeNumber(marker.score),
          labelLines,
          operationalNote,
          tooltipRows,
          tooltipTitle,
          derived: Boolean(marker.derived || marker.coherence_status === "derived_watch"),
        };
      });
  const markerTooltipBox = hoverMarker
    ? {
        x: clamp(hoverMarker.x + 16, paddingX + 4, width - paddingX - 286),
        y: clamp(hoverMarker.y - 74, paddingTop + 8, plotBottom - 136),
      }
    : null;

  return (
    <div className="snbr-chart-shell">
      <svg
        viewBox={`0 0 ${width} ${height}`}
        className="snbr-svg snbr-trading-chart"
        role="img"
        aria-label={isEnglish ? "Ticker chart" : "Grafico do ticker"}
        onMouseLeave={() => {
          setHoverPoint(null);
          setHoverMarker(null);
        }}
        onMouseMove={(event) => {
          const rect = event.currentTarget.getBoundingClientRect();
          const x = ((event.clientX - rect.left) / Math.max(rect.width, 1)) * width;
          const y = ((event.clientY - rect.top) / Math.max(rect.height, 1)) * height;
          const clampedX = clamp(x, paddingX, width - paddingX);
          const index = Math.max(0, Math.min(series.length - 1, Math.round(((clampedX - paddingX) / plotWidth) * Math.max(series.length - 1, 1))));
          const source = candleRows[index];
          if (!source) return;
          const candleX = toX(index);
          setHoverPoint({
            x: candleX,
            y: clamp(y, paddingTop, plotBottom),
            time: String(source.time || series[index]?.time || ""),
            close: source.close,
            open: source.open,
            high: source.high,
            low: source.low,
            volume: source.volume,
          });
        }}
      >
        <defs>
          <linearGradient id="priceFill" x1="0" x2="0" y1="0" y2="1">
            <stop offset="0%" stopColor="rgba(34, 197, 94, 0.14)" />
            <stop offset="100%" stopColor="rgba(34, 197, 94, 0.015)" />
          </linearGradient>
        </defs>

        <rect x="0" y="0" width={width} height={height} rx="18" fill="var(--snbr-chart-panel-bg, #ffffff)" />
        {extendedSessionSegments.map((segment, index) => {
          const x1 = segment.start <= 0
            ? paddingX
            : (toX(segment.start - 1) + toX(segment.start)) / 2;
          const x2 = segment.end >= series.length - 1
            ? width - paddingX
            : (toX(segment.end) + toX(segment.end + 1)) / 2;
          return (
            <rect
              key={`session-extended-${index}`}
              x={x1}
              y={paddingTop}
              width={Math.max(0, x2 - x1)}
              height={plotHeight}
              fill="var(--snbr-chart-session-bg, #fff2cc)"
              opacity="0.65"
            />
          );
        })}

        {verticalGridTicks.map((index) => {
          const x = toX(index);
          return <line key={`v-grid-${index}`} x1={x} x2={x} y1={paddingTop} y2={plotBottom} stroke="var(--snbr-chart-grid, #e6edf5)" strokeWidth="1" />;
        })}

        {[0, 1, 2, 3, 4].map((step) => {
          const y = paddingTop + (step * plotHeight) / 4;
          const value = maxValue - (step * valueRange) / 4;
          return (
            <g key={step}>
              <line x1={paddingX} x2={width - paddingX} y1={y} y2={y} stroke="var(--snbr-chart-grid, #dfe8f2)" strokeWidth="1" />
              <text x={width - paddingX + 10} y={y + 4} fill="var(--snbr-chart-axis, #5f6b7c)" fontSize="11">
                {formatPrice(value, locale)}
              </text>
            </g>
          );
        })}

        <text x={paddingX} y={22} fill="var(--snbr-chart-title, #4b5563)" fontSize="12" fontWeight="700">
          {chart?.summary?.ticker || chart?.ticker || "Ticker"} · {chartIntervalLabel}
        </text>
        <text x={paddingX + 96} y={22} fill={latestIsUp ? "#059669" : "#dc2626"} fontSize="12" fontWeight="700">
          O {formatPrice(candleRows.at(-1)?.open, locale)} H {formatPrice(candleRows.at(-1)?.high, locale)} L {formatPrice(candleRows.at(-1)?.low, locale)} C {formatPrice(latestClose, locale)}
        </text>

        {zoneRows.map((zone, index) => {
              const zonePrice = normalizeNumber(zone.price);
              if (zonePrice == null) return null;
              const y = toY(zonePrice);
              return (
                <g key={`${zone.label}-${zone.price}-${index}`}>
                  <rect
                    x={paddingX}
                    y={clamp(y - 8, paddingTop, plotBottom - 16)}
                    width={plotWidth}
                    height="16"
                    fill="rgba(105,214,255,0.10)"
                    rx="8"
                  />
                  <line
                    x1={paddingX}
                    x2={width - paddingX}
                    y1={y}
                    y2={y}
                    stroke="rgba(34,148,255,0.68)"
                    strokeDasharray="7 6"
                    strokeWidth="2"
                  />
                  <text
                    x={width - paddingX - 8}
                    y={Math.max(y - 10, paddingTop + 12)}
                    textAnchor="end"
                    fill="#4aa4ff"
                    fontSize="11"
                    fontWeight="700"
                  >
                    {localizeChartText(String(zone.label), locale).toUpperCase()}
                  </text>
                </g>
              );
            })}

        <path
          d={`${closePath} L ${toX(series.length - 1)} ${plotBottom} L ${toX(0)} ${plotBottom} Z`}
          fill="url(#priceFill)"
        />
        {candleRows.map((bar, index) => {
          if (bar.sessionBoundary) return null;
          const x = toX(index);
          const openY = toY(bar.open);
          const closeY = toY(bar.close);
          const highY = toY(bar.high);
          const lowY = toY(bar.low);
          const bullish = bar.close >= bar.open;
          const bodyY = Math.min(openY, closeY);
          const bodyHeight = Math.max(Math.abs(closeY - openY), 2);
          return (
            <g key={`${bar.time || "bar"}-${index}`} className={bullish ? "snbr-candle bullish" : "snbr-candle bearish"}>
              <title>{`${formatTooltipTime(bar.time, interval, locale)}
${isEnglish ? "Open" : "Abertura"}: ${formatPrice(bar.open, locale)}
${isEnglish ? "High" : "Maxima"}: ${formatPrice(bar.high, locale)}
${isEnglish ? "Low" : "Minima"}: ${formatPrice(bar.low, locale)}
${isEnglish ? "Close" : "Fechamento"}: ${formatPrice(bar.close, locale)}
Volume: ${formatPrice(bar.volume, locale)}`}</title>
              <line x1={x} x2={x} y1={highY} y2={lowY} />
              <rect x={x - candleWidth / 2} y={bodyY} width={candleWidth} height={bodyHeight} rx="1.5" />
            </g>
          );
        })}
        {showPriceLine ? <path d={closePath} stroke="#f2b233" strokeWidth="2.4" fill="none" strokeLinecap="round" /> : null}
        {showVwap ? <path d={vwapPath} stroke="#a855f7" strokeWidth="1.8" fill="none" strokeDasharray="6 5" strokeLinecap="round" /> : null}
        {showAverages ? <path d={ema9Path} stroke="#22c55e" strokeWidth="2" fill="none" strokeLinecap="round" /> : null}
        {showAverages ? <path d={ema21Path} stroke="#38bdf8" strokeWidth="2" fill="none" strokeLinecap="round" /> : null}
        {(showMacd || showRsi) ? (
          <g pointerEvents="none">
            <rect x={paddingX} y={indicatorTop} width={plotWidth} height={indicatorHeight} rx="8" fill="rgba(15,23,42,0.22)" />
            {showMacd
              ? macdHistogram.map((value, index) => {
                  const x = toX(index);
                  const barHeight = Math.max(1, (Math.abs(value) / macdMax) * (indicatorHeight / 2 - 3));
                  const isPositive = value >= 0;
                  return (
                    <rect
                      key={`macd-${series[index]?.time || index}`}
                      x={x - volumeBarWidth / 2}
                      y={isPositive ? macdZeroY - barHeight : macdZeroY}
                      width={volumeBarWidth}
                      height={barHeight}
                      fill={isPositive ? "rgba(16,185,129,0.55)" : "rgba(239,68,68,0.55)"}
                      rx="1"
                    />
                  );
                })
              : null}
            {showRsi ? (
              <>
                <line x1={paddingX} x2={width - paddingX} y1={indicatorTop + indicatorHeight * 0.3} y2={indicatorTop + indicatorHeight * 0.3} stroke="rgba(250,204,21,0.35)" strokeDasharray="3 4" />
                <line x1={paddingX} x2={width - paddingX} y1={indicatorTop + indicatorHeight * 0.7} y2={indicatorTop + indicatorHeight * 0.7} stroke="rgba(250,204,21,0.35)" strokeDasharray="3 4" />
                <path d={rsiPath} stroke="#f97316" strokeWidth="1.7" fill="none" strokeLinecap="round" />
              </>
            ) : null}
            <text x={paddingX + 6} y={indicatorTop + 12} fill="#cbd5e1" fontSize="9" fontWeight="800">
              {[showMacd ? "MACD" : "", showRsi ? "RSI" : ""].filter(Boolean).join(" / ")}
            </text>
          </g>
        ) : null}
        {showSupertrend ? supertrendSegments.map((segment, index) => (
          <path
            key={`supertrend-${segment.side}-${index}`}
            d={segment.path}
            className={segment.side === "sell" ? "snbr-supertrend sell" : "snbr-supertrend buy"}
            fill="none"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        )) : null}

        <line
          x1={paddingX}
          x2={width - paddingX}
          y1={latestY}
          y2={latestY}
          stroke={latestIsUp ? "#10b981" : "#ef4444"}
          strokeDasharray="2 3"
          strokeWidth="1.4"
        />
        <rect
          x={width - paddingX + 5}
          y={clamp(latestY - 10, paddingTop + 2, plotBottom - 22)}
          width="54"
          height="22"
          rx="4"
          fill={latestIsUp ? "#10b981" : "#ef4444"}
        />
        <text
          x={width - paddingX + 32}
          y={clamp(latestY + 4, paddingTop + 16, plotBottom - 6)}
          textAnchor="middle"
          fill="#ffffff"
          fontSize="10"
          fontWeight="800"
        >
          {formatPrice(latestClose, locale)}
        </text>

        {markerAnchors.map((marker) => {
          const badgeWidth = marker.labelLines.some((line) => line.length > 5) ? 64 : 50;
          const badgeHeight = marker.labelLines.length > 1 ? 41 : 31;
          const badgeX = clamp(marker.x - badgeWidth / 2, paddingX, width - paddingX - badgeWidth);
          const badgeY = marker.side === "sell" ? marker.stemEndY + 8 : marker.stemEndY - badgeHeight - 8;
          const scoreText = marker.score != null && Math.round(marker.score) > 0 ? `+${Math.round(marker.score)}` : "";
          return (
          <g
            key={marker.key}
            tabIndex={0}
            onBlur={() => setHoverMarker(null)}
            onFocus={() => setHoverMarker({
              x: marker.x,
              y: marker.y,
              rows: marker.tooltipRows,
              title: marker.tooltipTitle,
              side: marker.side,
            })}
            onMouseEnter={() => setHoverMarker({
              x: marker.x,
              y: marker.y,
              rows: marker.tooltipRows,
              title: marker.tooltipTitle,
              side: marker.side,
            })}
            onMouseLeave={() => setHoverMarker(null)}
          >
            <title>{marker.tooltipTitle}</title>
            <line
              x1={marker.x}
              x2={marker.lineEndX}
              y1={marker.y}
              y2={marker.y}
              className={marker.side === "sell" ? "snbr-trade-level sell" : marker.side === "buy" ? "snbr-trade-level buy" : "snbr-trade-level neutral"}
            />
            <text
              x={clamp(marker.x + 36, paddingX + 30, width - paddingX - 106)}
              y={clamp(marker.y - 8, paddingTop + 12, plotBottom - 28)}
              className={marker.derived ? "snbr-trade-note neutral" : "snbr-trade-note"}
            >
              {marker.operationalNote}
            </text>
            <line
              x1={marker.x}
              x2={marker.x}
              y1={marker.y}
              y2={marker.stemEndY}
              stroke={marker.fill}
              strokeWidth="2"
            />
            <circle cx={marker.x} cy={marker.y} r="5" fill={marker.fill} stroke={marker.stroke} strokeWidth="2" />
            <path
              d={
                marker.side === "sell"
                  ? `M ${marker.x - 5} ${marker.stemEndY - 4} L ${marker.x + 5} ${marker.stemEndY - 4} L ${marker.x} ${marker.stemEndY + 4} Z`
                  : `M ${marker.x - 5} ${marker.stemEndY + 4} L ${marker.x + 5} ${marker.stemEndY + 4} L ${marker.x} ${marker.stemEndY - 4} Z`
              }
              fill={marker.fill}
              stroke={marker.stroke}
              strokeWidth="1"
            />
            <rect
              x={badgeX}
              y={badgeY}
              rx="5"
              ry="5"
              width={badgeWidth}
              height={badgeHeight}
              fill={marker.fill}
              opacity="0.95"
            />
            <text x={badgeX + badgeWidth / 2} y={badgeY + 14} textAnchor="middle" fill="#ffffff" fontSize="9" fontWeight="800">
              {marker.labelLines.map((line, lineIndex) => (
                <tspan key={`${marker.key}-label-${lineIndex}`} x={badgeX + badgeWidth / 2} dy={lineIndex === 0 ? 0 : 10}>
                  {line}
                </tspan>
              ))}
            </text>
            {scoreText ? (
              <text
                x={badgeX + badgeWidth / 2}
                y={badgeY + badgeHeight - 7}
                textAnchor="middle"
                fill="#ffffff"
                fontSize="8"
                fontWeight="800"
              >
                {scoreText}
              </text>
            ) : null}
          </g>
          );
        })}

        {showVolume ? candleRows.map((bar, index) => {
          if (bar.sessionBoundary) return null;
          const x = toX(index);
          const barHeight = Math.max(1, (bar.volume / maxVolume) * volumeHeight);
          const bullish = bar.close >= bar.open;
          return (
            <rect
              key={`volume-${bar.time || index}`}
              x={x - volumeBarWidth / 2}
              y={volumeTop + volumeHeight - barHeight}
              width={volumeBarWidth}
              height={barHeight}
              fill={bullish ? "rgba(16, 185, 129, 0.35)" : "rgba(239, 68, 68, 0.35)"}
              rx="1"
            />
          );
        }) : null}

        {xTicks.map((index) => {
          const x = toX(index);
          return (
            <g key={`x-tick-${index}`}>
              <line x1={x} x2={x} y1={plotBottom + 5} y2={plotBottom + 10} stroke="var(--snbr-chart-grid, rgba(98,120,151,0.28))" />
              <text x={x} y={height - 16} textAnchor="middle" fill="var(--snbr-chart-axis, #6b7a90)" fontSize="10">
                {formatAxisTime(series[index]?.time, interval, locale)}
              </text>
            </g>
          );
        })}

        {hoverMarker && markerTooltipBox ? (
          <g pointerEvents="none">
            <rect
              x={markerTooltipBox.x}
              y={markerTooltipBox.y}
              width="286"
              height="128"
              rx="12"
              fill="rgba(15, 23, 42, 0.94)"
              stroke={hoverMarker.side === "sell" ? "rgba(248, 113, 113, 0.7)" : hoverMarker.side === "buy" ? "rgba(34, 197, 94, 0.7)" : "rgba(245, 158, 11, 0.72)"}
            />
            <text x={markerTooltipBox.x + 12} y={markerTooltipBox.y + 20} fill="#ffffff" fontSize="11" fontWeight="800">
              {hoverMarker.title.split("\n")[0] || (isEnglish ? "Chart signal" : "Sinal no grafico")}
            </text>
            {hoverMarker.rows.slice(1).map((row, index) => (
              <g key={`${row.label}-${index}`}>
                <text x={markerTooltipBox.x + 12} y={markerTooltipBox.y + 40 + index * 20} fill="#93c5fd" fontSize="9" fontWeight="800">
                  {row.label}
                </text>
                <text x={markerTooltipBox.x + 82} y={markerTooltipBox.y + 40 + index * 20} fill="#e5edf7" fontSize="9">
                  {truncateText(row.value, 48)}
                </text>
              </g>
            ))}
          </g>
        ) : null}

        {hoverPoint && !hoverMarker ? (
          <g pointerEvents="none">
            <line x1={hoverPoint.x} x2={hoverPoint.x} y1={paddingTop} y2={plotBottom} stroke="rgba(59,130,246,0.22)" strokeDasharray="4 4" />
            <circle cx={hoverPoint.x} cy={toY(hoverPoint.close)} r="4" fill="#2563eb" stroke="#ffffff" strokeWidth="2" />
            <rect
              x={clamp(hoverPoint.x + 14, paddingX, width - paddingX - 170)}
              y={clamp(hoverPoint.y - 78, paddingTop + 8, plotBottom - 118)}
              width="170"
              height="108"
              rx="12"
              fill="rgba(15, 23, 42, 0.92)"
            />
            <text x={clamp(hoverPoint.x + 24, paddingX + 10, width - paddingX - 150)} y={clamp(hoverPoint.y - 56, paddingTop + 28, plotBottom - 90)} fill="#ffffff" fontSize="11" fontWeight="700">
              {formatTooltipTime(hoverPoint.time, interval, locale) || (isEnglish ? "Date unavailable" : "Data indisponivel")}
            </text>
            <text x={clamp(hoverPoint.x + 24, paddingX + 10, width - paddingX - 150)} y={clamp(hoverPoint.y - 38, paddingTop + 46, plotBottom - 72)} fill="#dbeafe" fontSize="10">
              {isEnglish ? "Open" : "Abertura"}: {formatPrice(hoverPoint.open, locale)}
            </text>
            <text x={clamp(hoverPoint.x + 24, paddingX + 10, width - paddingX - 150)} y={clamp(hoverPoint.y - 22, paddingTop + 62, plotBottom - 56)} fill="#dbeafe" fontSize="10">
              {isEnglish ? "High" : "Máxima"}: {formatPrice(hoverPoint.high, locale)}
            </text>
            <text x={clamp(hoverPoint.x + 24, paddingX + 10, width - paddingX - 150)} y={clamp(hoverPoint.y - 6, paddingTop + 78, plotBottom - 40)} fill="#dbeafe" fontSize="10">
              {isEnglish ? "Low" : "Mínima"}: {formatPrice(hoverPoint.low, locale)}
            </text>
            <text x={clamp(hoverPoint.x + 24, paddingX + 10, width - paddingX - 150)} y={clamp(hoverPoint.y + 10, paddingTop + 94, plotBottom - 24)} fill="#dbeafe" fontSize="10">
              {isEnglish ? "Close" : "Fechamento"}: {formatPrice(hoverPoint.close, locale)} • Volume: {formatCompact(hoverPoint.volume, locale)}
            </text>
          </g>
        ) : null}
      </svg>

      <div className="snbr-chart-nav" aria-label={isEnglish ? "Chart navigation" : "Navegacao do grafico"}>
        <button
          disabled={!canPanLeft}
          onClick={() => setWindowStart((value) => clamp(value - panStep, 0, maxWindowStart))}
          type="button"
        >
          ← {isEnglish ? "Left" : "Esquerda"}
        </button>
        <button
          disabled={!canZoomIn}
          onClick={() => {
            const nextSize = Math.max(minWindowSize, Math.floor(effectiveWindowSize * 0.68));
            setWindowSize(nextSize);
            setWindowStart((value) => clamp(value + Math.floor((effectiveWindowSize - nextSize) / 2), 0, Math.max(0, displaySeries.length - nextSize)));
          }}
          type="button"
        >
          Zoom +
        </button>
        <button
          disabled={!canZoomOut}
          onClick={() => {
            const nextSize = Math.min(displaySeries.length, Math.ceil(effectiveWindowSize * 1.45));
            setWindowSize(nextSize);
            setWindowStart((value) => clamp(value - Math.floor((nextSize - effectiveWindowSize) / 2), 0, Math.max(0, displaySeries.length - nextSize)));
          }}
          type="button"
        >
          Zoom -
        </button>
        <button
          disabled={!canPanRight}
          onClick={() => setWindowStart((value) => clamp(value + panStep, 0, maxWindowStart))}
          type="button"
        >
          {isEnglish ? "Right" : "Direita"} →
        </button>
        <button
          disabled={effectiveWindowSize === displaySeries.length && effectiveWindowStart === 0}
          onClick={() => {
            setWindowStart(0);
            setWindowSize(null);
          }}
          type="button"
        >
          Reset
        </button>
      </div>

      <div className="snbr-chart-meta">
        <span className="snbr-chip">Ticker: {currentTicker}</span>
        <span className="snbr-chip">{isEnglish ? "Current close" : "Fechamento atual"}: {formatPrice(derivedClose, locale)}</span>
        <span className="snbr-chip">{isEnglish ? "Chart bias" : "Bias do gráfico"}: {localizeChartText(derivedTrendBias || "n/a", locale)}</span>
        <span className="snbr-chip">{isEnglish ? "Active chart items" : "Itens ativos no gráfico"}: {activeToolCount}</span>
        {sessionProfile?.note ? <span className="snbr-chip">{isEnglish ? sessionProfile.note.replace("Sessão: EUA com pré/after-hours quando o provider entrega", "Session: US pre/after-hours when provider delivers").replace("Sessão: B3 regular; provider público inicia perto de 10:00", "Session: regular B3; public provider starts near 10:00") : sessionProfile.note}</span> : null}
      </div>
    </div>
  );
}
