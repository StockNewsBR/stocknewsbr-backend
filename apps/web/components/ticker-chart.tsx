"use client";

import type { ChartPayload } from "@/lib/types";

type Props = {
  chart: ChartPayload | null;
  showMarkers?: boolean;
  showZones?: boolean;
};

function clamp(value: number, min: number, max: number) {
  return Math.min(max, Math.max(min, value));
}

function normalizeNumber(value: unknown): number | null {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

export function TickerChart({ chart, showMarkers = true, showZones = true }: Props) {
  const series = chart?.series || [];

  if (!series.length) {
    return <div className="snbr-empty">Sem serie historica suficiente para desenhar o grafico ainda.</div>;
  }

  const width = 960;
  const height = 360;
  const padding = 22;
  const closes = series.map((item) => Number(item.close || 0));
  const ema9 = series.map((item) => Number(item.ema9 || item.close || 0));
  const ema21 = series.map((item) => Number(item.ema21 || item.close || 0));
  const allValues = [...closes, ...ema9, ...ema21];
  const minValue = Math.min(...allValues);
  const maxValue = Math.max(...allValues);
  const valueRange = Math.max(maxValue - minValue, 0.0001);

  function toY(value: number) {
    return clamp(
      height - padding - ((value - minValue) / valueRange) * (height - padding * 2),
      padding,
      height - padding,
    );
  }

  function toX(index: number) {
    return padding + (index * (width - padding * 2)) / Math.max(series.length - 1, 1);
  }

  function buildPath(values: number[]) {
    return values
      .map((value, index) => `${index === 0 ? "M" : "L"} ${toX(index)} ${toY(value)}`)
      .join(" ");
  }

  const closePath = buildPath(closes);
  const ema9Path = buildPath(ema9);
  const ema21Path = buildPath(ema21);
  const timeToIndex = new Map(series.map((item, index) => [String(item.time || ""), index]));

  const markerAnchors = showMarkers
    ? (chart?.markers || []).map((marker, markerIndex) => {
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
        const stemEndY = clamp(y + direction * 20, padding + 8, height - padding - 8);
        const label = side === "buy" ? "BUY" : side === "sell" ? "SELL" : String(marker.type || "EVENT");
        const fill = side === "buy" ? "#1fd38a" : side === "sell" ? "#ff6b6b" : "#f4b942";
        const stroke = side === "buy" ? "#0b6a45" : side === "sell" ? "#8f2838" : "#8a651d";

        return {
          key: `${normalizedTime || "marker"}-${markerIndex}`,
          x,
          y,
          stemEndY,
          label,
          fill,
          stroke,
          side,
        };
      })
    : [];

  return (
    <div className="snbr-chart-shell">
      <svg viewBox={`0 0 ${width} ${height}`} className="snbr-svg" role="img" aria-label="Grafico do ticker">
        <defs>
          <linearGradient id="priceFill" x1="0" x2="0" y1="0" y2="1">
            <stop offset="0%" stopColor="rgba(31, 211, 138, 0.22)" />
            <stop offset="100%" stopColor="rgba(31, 211, 138, 0.02)" />
          </linearGradient>
        </defs>

        {[0, 1, 2, 3].map((step) => {
          const y = padding + (step * (height - padding * 2)) / 3;
          return <line key={step} x1={padding} x2={width - padding} y1={y} y2={y} stroke="rgba(255,255,255,0.06)" />;
        })}

        {showZones
          ? (chart?.zones || []).map((zone, index) => {
              const zonePrice = normalizeNumber(zone.price);
              if (zonePrice == null) return null;
              const y = toY(zonePrice);
              return (
                <g key={`${zone.label}-${zone.price}-${index}`}>
                  <line
                    x1={padding}
                    x2={width - padding}
                    y1={y}
                    y2={y}
                    stroke="rgba(105,214,255,0.35)"
                    strokeDasharray="6 6"
                  />
                  <text
                    x={width - padding - 8}
                    y={Math.max(y - 6, padding + 12)}
                    textAnchor="end"
                    fill="#9fd8ff"
                    fontSize="11"
                  >
                    {String(zone.label).toUpperCase()}
                  </text>
                </g>
              );
            })
          : null}

        <path
          d={`${closePath} L ${toX(series.length - 1)} ${height - padding} L ${toX(0)} ${height - padding} Z`}
          fill="url(#priceFill)"
        />
        <path d={closePath} stroke="#f4b942" strokeWidth="3" fill="none" strokeLinecap="round" />
        <path d={ema9Path} stroke="#1fd38a" strokeWidth="2" fill="none" strokeLinecap="round" />
        <path d={ema21Path} stroke="#69d6ff" strokeWidth="2" fill="none" strokeLinecap="round" />

        {markerAnchors.map((marker) => (
          <g key={marker.key}>
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
              x={clamp(marker.x - 19, padding, width - padding - 38)}
              y={marker.side === "sell" ? marker.stemEndY + 8 : marker.stemEndY - 28}
              rx="10"
              ry="10"
              width="38"
              height="18"
              fill={marker.fill}
              opacity="0.95"
            />
            <text
              x={marker.x}
              y={marker.side === "sell" ? marker.stemEndY + 20 : marker.stemEndY - 16}
              textAnchor="middle"
              fill="#08131b"
              fontSize="10"
              fontWeight="700"
            >
              {marker.label}
            </text>
          </g>
        ))}
      </svg>

      <div className="snbr-chart-meta">
        <span className="snbr-chip">Ticker: {chart?.summary?.ticker || chart?.ticker}</span>
        <span className="snbr-chip">Fechamento: {chart?.summary?.latest_close ?? "n/a"}</span>
        <span className="snbr-chip">Bias: {chart?.summary?.trend_bias || "n/a"}</span>
        <span className="snbr-chip">Marcadores: {chart?.markers?.length || 0}</span>
      </div>
    </div>
  );
}
