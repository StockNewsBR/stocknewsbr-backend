"use client";

import type { ChartPayload } from "@/lib/types";

type Props = {
  chart: ChartPayload | null;
  showMarkers?: boolean;
};

function clamp(value: number, min: number, max: number) {
  return Math.min(max, Math.max(min, value));
}

export function TickerChart({ chart, showMarkers = true }: Props) {
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

        <path
          d={`${closePath} L ${toX(series.length - 1)} ${height - padding} L ${toX(0)} ${height - padding} Z`}
          fill="url(#priceFill)"
        />
        <path d={closePath} stroke="#f4b942" strokeWidth="3" fill="none" strokeLinecap="round" />
        <path d={ema9Path} stroke="#1fd38a" strokeWidth="2" fill="none" strokeLinecap="round" />
        <path d={ema21Path} stroke="#69d6ff" strokeWidth="2" fill="none" strokeLinecap="round" />

        {showMarkers ? (chart?.markers || []).map((marker, index) => {
          const x = width - 30 - index * 22;
          const y = marker.side === "buy" ? 28 : marker.side === "sell" ? 54 : 80;
          const color = marker.side === "buy" ? "#1fd38a" : marker.side === "sell" ? "#ff6b6b" : "#f4b942";

          return <circle key={`${marker.time || "m"}-${index}`} cx={x} cy={y} r="5" fill={color} />;
        }) : null}
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
