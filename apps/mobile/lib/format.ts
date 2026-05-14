function currencyFormatter(currency: "BRL" | "USD") {
  return new Intl.NumberFormat(currency === "BRL" ? "pt-BR" : "en-US", {
    style: "currency",
    currency,
    maximumFractionDigits: 2,
  });
}

const compactFormatter = new Intl.NumberFormat("pt-BR", {
  notation: "compact",
  maximumFractionDigits: 1,
});

const numberFormatter = new Intl.NumberFormat("pt-BR", {
  maximumFractionDigits: 2,
});

export function currencyForTicker(ticker: unknown): "BRL" | "USD" {
  const symbol = String(ticker || "").toUpperCase().trim();
  if (!symbol || /[0-9]$/.test(symbol) || symbol.endsWith(".SA")) {
    return "BRL";
  }
  return "USD";
}

export function formatCurrency(value: unknown, currency: "BRL" | "USD" = "BRL") {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) {
    return "n/a";
  }
  return currencyFormatter(currency).format(numeric);
}

export function formatTickerCurrency(ticker: unknown, value: unknown) {
  return formatCurrency(value, currencyForTicker(ticker));
}

export function formatPercent(value: unknown) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) {
    return "n/a";
  }
  const prefix = numeric > 0 ? "+" : "";
  return `${prefix}${numberFormatter.format(numeric)}%`;
}

export function formatNumber(value: unknown) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) {
    return "n/a";
  }
  return compactFormatter.format(numeric);
}

export function formatPlainNumber(value: unknown) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) {
    return "n/a";
  }
  return numberFormatter.format(numeric);
}

export function formatTimestamp(value: unknown) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric) || numeric <= 0) {
    return "n/a";
  }

  const date = new Date(numeric * 1000);
  return new Intl.DateTimeFormat("pt-BR", {
    dateStyle: "short",
    timeStyle: "short",
  }).format(date);
}

export function formatRelativeSeconds(seconds: unknown) {
  const numeric = Number(seconds);
  if (!Number.isFinite(numeric) || numeric < 0) {
    return "n/a";
  }
  if (numeric < 60) {
    return `${Math.round(numeric)}s`;
  }
  if (numeric < 3600) {
    return `${Math.round(numeric / 60)}m`;
  }
  return `${Math.round(numeric / 3600)}h`;
}
