import { useMemo, useState } from "react";
import { LayoutChangeEvent, StyleSheet, Text, View } from "react-native";

import { formatPlainNumber, formatTickerCurrency, formatTimestamp } from "@/lib/format";
import { Pill, theme } from "@/components/ui";

type ChartRow = {
  time?: string | number | null;
  timestamp?: string | number | null;
  open?: string | number | null;
  high?: string | number | null;
  low?: string | number | null;
  close?: string | number | null;
  volume?: string | number | null;
};

type MarkerRow = {
  time?: string | number | null;
  label?: string | null;
  event_type?: string | null;
  side?: string | null;
  price?: string | number | null;
  trigger?: string | null;
  invalidation?: string | null;
  invalidacao?: string | null;
  risk?: string | null;
};

type ZoneRow = {
  label?: string | null;
  price?: string | number | null;
};

function asNumber(value: unknown): number | null {
  const numeric = Number(value);
  return Number.isFinite(numeric) ? numeric : null;
}

function asTimeSeconds(value: unknown): number {
  if (typeof value === "number" && Number.isFinite(value)) {
    return value > 100000000000 ? Math.round(value / 1000) : value;
  }

  const text = String(value || "").trim();
  if (!text) {
    return 0;
  }

  const numeric = Number(text);
  if (Number.isFinite(numeric)) {
    return numeric > 100000000000 ? Math.round(numeric / 1000) : numeric;
  }

  const parsed = Date.parse(text);
  return Number.isFinite(parsed) ? Math.round(parsed / 1000) : 0;
}

function normalizeRows(rows: ChartRow[], fallbackSeries: ChartRow[]) {
  const source = rows.length ? rows : fallbackSeries;
  return source
    .map((row) => {
      const close = asNumber(row.close);
      if (close === null || close <= 0) {
        return null;
      }

      const open = asNumber(row.open) ?? close;
      const high = Math.max(asNumber(row.high) ?? close, open, close);
      const low = Math.min(asNumber(row.low) ?? close, open, close);
      return {
        time: row.time ?? row.timestamp ?? null,
        open,
        high,
        low,
        close,
        volume: asNumber(row.volume) ?? 0,
      };
    })
    .filter((row): row is NonNullable<typeof row> => Boolean(row));
}

function labelForMarker(marker: MarkerRow) {
  const label = String(marker.label || marker.event_type || "").trim();
  if (label) {
    return label;
  }
  return String(marker.side || "").toLowerCase() === "sell" ? "Sell" : "Buy";
}

export function MobilePriceChart({
  ticker,
  range,
  rows,
  series = [],
  markers = [],
  zones = [],
}: {
  ticker: string;
  range: string;
  rows: ChartRow[];
  series?: ChartRow[];
  markers?: MarkerRow[];
  zones?: ZoneRow[];
}) {
  const [width, setWidth] = useState(320);
  const candles = useMemo(() => normalizeRows(rows, series), [rows, series]);
  const visibleCandles = candles.slice(-90);
  const prices = visibleCandles.flatMap((row) => [row.high, row.low, row.open, row.close]);
  const minPrice = Math.min(...prices);
  const maxPrice = Math.max(...prices);
  const priceSpan = Math.max(maxPrice - minPrice, Math.max(maxPrice * 0.002, 0.01));
  const latest = visibleCandles[visibleCandles.length - 1];
  const previous = visibleCandles[visibleCandles.length - 2];
  const changePct = latest && previous ? ((latest.close - previous.close) / Math.max(previous.close, 0.01)) * 100 : 0;
  const chartHeight = 230;
  const contentWidth = Math.max(width - 8, 260);
  const spacing = visibleCandles.length > 1 ? contentWidth / (visibleCandles.length - 1) : contentWidth;
  const candleWidth = Math.max(3, Math.min(9, spacing * 0.48));
  const latestMarker = markers[markers.length - 1];

  function onLayout(event: LayoutChangeEvent) {
    const nextWidth = event.nativeEvent.layout.width;
    if (nextWidth > 0) {
      setWidth(nextWidth);
    }
  }

  function yForPrice(value: number) {
    return 14 + ((maxPrice - value) / priceSpan) * (chartHeight - 34);
  }

  function xForIndex(index: number) {
    if (visibleCandles.length <= 1) {
      return contentWidth / 2;
    }
    return index * spacing;
  }

  if (!visibleCandles.length || !Number.isFinite(minPrice) || !Number.isFinite(maxPrice)) {
    return (
      <View testID="mobile-price-chart-empty" style={styles.emptyChart}>
        <Text style={styles.emptyTitle}>Grafico indisponivel</Text>
        <Text style={styles.emptyText}>
          Faltam candles com preco real para {ticker}. Atualize quando o cache do worker entregar OHLC valido.
        </Text>
      </View>
    );
  }

  return (
    <View testID="mobile-price-chart" style={styles.wrapper} onLayout={onLayout}>
      <View style={styles.headerRow}>
        <View>
          <Text style={styles.ticker}>{ticker} - {range}</Text>
          <Text style={styles.price}>{formatTickerCurrency(ticker, latest?.close)}</Text>
        </View>
        <Pill label={`${changePct >= 0 ? "+" : ""}${formatPlainNumber(changePct)}%`} tone={changePct >= 0 ? "accent" : "danger"} />
      </View>

      <View style={[styles.chartCanvas, { height: chartHeight }]}>
        {[0, 1, 2, 3].map((row) => (
          <View key={`grid-${row}`} style={[styles.gridLine, { top: 18 + row * ((chartHeight - 36) / 3) }]} />
        ))}

        {zones
          .map((zone) => ({ ...zone, price: asNumber(zone.price) }))
          .filter((zone): zone is ZoneRow & { price: number } => zone.price !== null && zone.price >= minPrice && zone.price <= maxPrice)
          .slice(0, 4)
          .map((zone) => {
            const top = yForPrice(zone.price);
            return (
              <View key={`${zone.label || "zone"}-${zone.price}`} style={[styles.zoneLine, { top }]}>
                <Text style={styles.zoneLabel}>{zone.label || "zona"} {formatTickerCurrency(ticker, zone.price)}</Text>
              </View>
            );
          })}

        {visibleCandles.map((row, index) => {
          const x = xForIndex(index);
          const highTop = yForPrice(row.high);
          const lowTop = yForPrice(row.low);
          const openTop = yForPrice(row.open);
          const closeTop = yForPrice(row.close);
          const bullish = row.close >= row.open;
          const bodyTop = Math.min(openTop, closeTop);
          const bodyHeight = Math.max(Math.abs(closeTop - openTop), 3);
          const color = bullish ? theme.colors.accent : theme.colors.danger;

          return (
            <View key={`${row.time || index}-${row.close}`} style={[styles.candleSlot, { left: x - candleWidth / 2, width: candleWidth }]}>
              <View style={[styles.wick, { top: highTop, height: Math.max(lowTop - highTop, 2), backgroundColor: color }]} />
              <View style={[styles.body, { top: bodyTop, height: bodyHeight, backgroundColor: color }]} />
            </View>
          );
        })}

        {markers.slice(-6).map((marker, markerIndex) => {
          const markerTime = asTimeSeconds(marker.time);
          const candleIndex = markerTime
            ? visibleCandles.findIndex((row) => asTimeSeconds(row.time) === markerTime)
            : -1;
          const index = candleIndex >= 0 ? candleIndex : Math.max(0, visibleCandles.length - 1 - (markers.length - markerIndex));
          const price = asNumber(marker.price) ?? visibleCandles[index]?.close ?? latest.close;
          const x = Math.min(Math.max(xForIndex(index), 16), contentWidth - 58);
          const y = Math.min(Math.max(yForPrice(price) - 18, 6), chartHeight - 36);
          const bearish = String(marker.side || marker.event_type || "").toLowerCase().includes("sell");
          return (
            <View key={`${labelForMarker(marker)}-${marker.time || markerIndex}`} style={[styles.marker, { left: x, top: y, borderColor: bearish ? theme.colors.danger : theme.colors.accent }]}>
              <Text style={[styles.markerText, { color: bearish ? theme.colors.danger : theme.colors.accent }]}>{labelForMarker(marker)}</Text>
            </View>
          );
        })}
      </View>

      <View style={styles.footerRow}>
        <Text style={styles.axisText}>Min {formatTickerCurrency(ticker, minPrice)}</Text>
        <Text style={styles.axisText}>Max {formatTickerCurrency(ticker, maxPrice)}</Text>
        <Text style={styles.axisText}>{formatTimestamp(asTimeSeconds(latest?.time))}</Text>
      </View>

      {latestMarker ? (
        <View style={styles.markerDetail}>
          <Text style={styles.markerTitle}>Ultimo marcador: {labelForMarker(latestMarker)}</Text>
          <Text style={styles.markerLine}>Trigger: {latestMarker.trigger || "aguardar confirmacao de preco/volume"}</Text>
          <Text style={styles.markerLine}>Invalidacao: {latestMarker.invalidation || latestMarker.invalidacao || "perda do nivel/fluxo contrario"}</Text>
          <Text style={styles.markerLine}>Risco: {latestMarker.risk || "monitorar liquidez, spread e regime"}</Text>
        </View>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  wrapper: {
    gap: 12,
  },
  headerRow: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "flex-start",
    gap: 12,
  },
  ticker: {
    color: theme.colors.muted,
    fontSize: 12,
    fontWeight: "700",
  },
  price: {
    color: theme.colors.text,
    fontSize: 28,
    fontWeight: "800",
    marginTop: 2,
  },
  chartCanvas: {
    overflow: "hidden",
    borderRadius: 18,
    backgroundColor: "#071521",
    borderWidth: 1,
    borderColor: theme.colors.line,
  },
  gridLine: {
    position: "absolute",
    left: 0,
    right: 0,
    height: 1,
    backgroundColor: "rgba(255,255,255,0.08)",
  },
  candleSlot: {
    position: "absolute",
    top: 0,
    bottom: 0,
    alignItems: "center",
  },
  wick: {
    position: "absolute",
    width: 1,
    borderRadius: 1,
  },
  body: {
    position: "absolute",
    left: 0,
    right: 0,
    borderRadius: 2,
  },
  zoneLine: {
    position: "absolute",
    left: 0,
    right: 0,
    borderTopWidth: 1,
    borderStyle: "dashed",
    borderTopColor: theme.colors.info,
  },
  zoneLabel: {
    alignSelf: "flex-end",
    marginRight: 8,
    marginTop: 2,
    color: theme.colors.info,
    fontSize: 10,
    fontWeight: "700",
  },
  marker: {
    position: "absolute",
    minWidth: 42,
    borderRadius: 999,
    borderWidth: 1,
    backgroundColor: "rgba(6,16,24,0.92)",
    paddingHorizontal: 7,
    paddingVertical: 4,
  },
  markerText: {
    fontSize: 10,
    fontWeight: "800",
  },
  footerRow: {
    flexDirection: "row",
    justifyContent: "space-between",
    gap: 8,
  },
  axisText: {
    color: theme.colors.muted,
    fontSize: 11,
    flex: 1,
  },
  markerDetail: {
    gap: 5,
    borderRadius: 16,
    padding: 12,
    backgroundColor: theme.colors.surfaceSoft,
    borderWidth: 1,
    borderColor: theme.colors.line,
  },
  markerTitle: {
    color: theme.colors.text,
    fontWeight: "800",
  },
  markerLine: {
    color: theme.colors.muted,
    lineHeight: 18,
    fontSize: 12,
  },
  emptyChart: {
    minHeight: 170,
    borderRadius: 18,
    borderWidth: 1,
    borderColor: theme.colors.line,
    backgroundColor: theme.colors.surfaceSoft,
    justifyContent: "center",
    padding: 16,
    gap: 8,
  },
  emptyTitle: {
    color: theme.colors.text,
    fontWeight: "800",
    fontSize: 18,
  },
  emptyText: {
    color: theme.colors.muted,
    lineHeight: 20,
  },
});
