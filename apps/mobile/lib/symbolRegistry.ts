const QUERY_RE = /[?&=]/;
const B3_RE = /^[A-Z][A-Z0-9]{3,4}(3|4|5|6|11|34)$/;
const B3_WITH_SUFFIX_RE = /^([A-Z][A-Z0-9]{3,4}(?:3|4|5|6|11|34))SA$/;
const CRYPTO_RE = /^([A-Z0-9]{2,8})(USD|USDT)$/;
const US_RE = /^[A-Z][A-Z0-9]{0,9}$/;

const CRYPTO_BASES = new Set(["BTC", "ETH", "BNB", "SOL", "XRP", "ADA", "DOGE", "MATIC", "AVAX", "LINK"]);

const CURATED_ALIASES: Record<string, string[]> = {
  ASAI3: ["ASAI3.SA", "ASAI3 B3", "BVMF:ASAI3", "BMFBOVESPA:ASAI3"],
  AZUL4: ["AZUL4.SA", "AZUL4 B3", "BVMF:AZUL4", "BMFBOVESPA:AZUL4"],
  B3SA3: ["B3SA3.SA", "B3SA3 B3", "BVMF:B3SA3", "BMFBOVESPA:B3SA3"],
  AXIA6: ["AXIA6.SA", "AXIA6 B3", "ELET6", "ELET6.SA", "BVMF:ELET6", "BMFBOVESPA:ELET6", "BMFBOVESPA:AXIA6"],
  PETR4: ["PETR4.SA", "PETR4 B3", "PETR", "BVMF:PETR4", "BMFBOVESPA:PETR4"],
  VALE3: ["VALE3.SA", "VALE3 B3", "VALE", "BVMF:VALE3", "BMFBOVESPA:VALE3"],
  ITUB4: ["ITUB4.SA", "ITUB4 B3", "ITUB", "BVMF:ITUB4", "BMFBOVESPA:ITUB4"],
  BBAS3: ["BBAS3.SA", "BBAS3 B3", "BBAS", "BVMF:BBAS3", "BMFBOVESPA:BBAS3"],
  WIN: ["WIN$", "WINFUT", "WIN1!", "BMFBOVESPA:WIN1!"],
  AAPL: ["NASDAQ:AAPL", "AAPL.US"],
  MSFT: ["NASDAQ:MSFT", "MSFT.US"],
  NVDA: ["NASDAQ:NVDA", "NVDA.US"],
  TSLA: ["NASDAQ:TSLA", "TSLA.US"],
};

function aliasKey(value: unknown) {
  let raw = String(value || "").trim().toUpperCase();
  if (!raw || QUERY_RE.test(raw)) return "";
  raw = raw.replace(/\s+/g, " ");
  if (raw.includes(":")) raw = raw.split(":").pop()?.trim() || "";
  raw = raw.replace(/\s+(B3|BVMF|BMFBOVESPA)$/u, "").trim();
  raw = raw.replace(/^\$/u, "");
  for (const suffix of [".SA", ".US"]) {
    if (raw.endsWith(suffix)) raw = raw.slice(0, -suffix.length);
  }
  let compact = raw.replace(/[\s/_\-.]/gu, "");
  if (compact.endsWith("SA")) {
    const match = compact.match(B3_WITH_SUFFIX_RE);
    if (match) compact = match[1];
  }
  if (compact.startsWith("XBT")) compact = `BTC${compact.slice(3)}`;
  const cryptoMatch = compact.match(CRYPTO_RE);
  if (cryptoMatch && CRYPTO_BASES.has(cryptoMatch[1])) compact = `${cryptoMatch[1]}USD`;
  return compact;
}

const ALIASES = new Map<string, string>();
for (const [canonical, aliases] of Object.entries(CURATED_ALIASES)) {
  for (const alias of [canonical, ...aliases]) {
    const key = aliasKey(alias);
    if (key) ALIASES.set(key, canonical);
  }
}
for (const base of CRYPTO_BASES) {
  const canonical = `${base}USD`;
  for (const alias of [base, canonical, `${base}USDT`, `${base}/USD`, `${base}-USD`, `BINANCE:${base}USDT`]) {
    const key = aliasKey(alias);
    if (key) ALIASES.set(key, canonical);
  }
}

export function canonicalSymbol(value: unknown) {
  const key = aliasKey(value);
  if (!key) return "";
  const mapped = ALIASES.get(key);
  if (mapped) return mapped;
  const cryptoMatch = key.match(CRYPTO_RE);
  if (cryptoMatch && CRYPTO_BASES.has(cryptoMatch[1])) return `${cryptoMatch[1]}USD`;
  if (CRYPTO_BASES.has(key)) return `${key}USD`;
  if (B3_RE.test(key) || US_RE.test(key)) return key;
  return "";
}
