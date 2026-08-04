const QUERY_RE = /[?&=]/;
const B3_RE = /^[A-Z][A-Z0-9]{3,4}(3|4|5|6|7|11|32|34)$/;
const B3_WITH_SUFFIX_RE = /^([A-Z][A-Z0-9]{3,4}(?:3|4|5|6|7|11|32|34))SA$/;
const B3_FUTURE_RE = /^(WIN|WDO)[FGHJKMNQUVXZ]\d{2}$/;
const CRYPTO_RE = /^([A-Z0-9]{2,8})(USD|USDT)$/;
const US_RE = /^[A-Z][A-Z0-9]{0,9}$/;

const CRYPTO_BASES = new Set(["BTC", "ETH", "BNB", "SOL", "XRP", "ADA", "DOGE", "MATIC", "AVAX", "LINK"]);
const US_MARKET_QUALIFIERS = new Set(["AMEX", "ARCA", "BATS", "CBOE", "NASDAQ", "NYSE", "NYSEARCA", "OTC"]);
const KNOWN_BDR_SYMBOLS = new Set([
  "A1MD34",
  "AAPL34",
  "AMZO34",
  "BABA34",
  "BERK34",
  "GOGL34",
  "ITLC34",
  "JBSS32",
  "M1TA34",
  "MELI34",
  "MSFT34",
  "NFLX34",
  "NVDC34",
  "PFIZ34",
  "PYPL34",
  "QCOM34",
  "TSLA34",
]);

const US_EXCHANGE_BY_SYMBOL: Record<string, string> = {
  AAL: "NASDAQ",
  AAPL: "NASDAQ",
  ADBE: "NASDAQ",
  AMD: "NASDAQ",
  AMZN: "NASDAQ",
  AVGO: "NASDAQ",
  BABA: "NYSE",
  BULL: "NASDAQ",
  BYDDY: "OTC",
  COIN: "NASDAQ",
  COST: "NASDAQ",
  CRM: "NYSE",
  GOOGL: "NASDAQ",
  INTC: "NASDAQ",
  META: "NASDAQ",
  MSFT: "NASDAQ",
  NFLX: "NASDAQ",
  NVDA: "NASDAQ",
  ORCL: "NYSE",
  PDD: "NASDAQ",
  PLTR: "NASDAQ",
  PYPL: "NASDAQ",
  QCOM: "NASDAQ",
  SHOP: "NYSE",
  QQQ: "NASDAQ",
  SPY: "NYSEARCA",
  SPCX: "NASDAQ",
  SNOW: "NYSE",
  TSLA: "NASDAQ",
  UBER: "NYSE",
  BA: "NYSE",
  BAC: "NYSE",
  BNY: "NYSE",
  CVX: "NYSE",
  DIA: "NYSEARCA",
  DIS: "NYSE",
  F: "NYSE",
  GE: "NYSE",
  GM: "NYSE",
  GS: "NYSE",
  IWM: "NYSEARCA",
  JPM: "NYSE",
  TSM: "NYSE",
  VOO: "NYSEARCA",
  WMT: "NYSE",
  XOM: "NYSE",
};

const CURATED_ALIASES: Record<string, string[]> = {
  ASAI3: ["ASAI3.SA", "ASAI3 B3", "BVMF:ASAI3", "BMFBOVESPA:ASAI3"],
  // Corporate-action remaps (old B3 tickers -> live successors), mirrors backend registry:
  BRAV3: ["BRAV3.SA", "BRAV3 B3", "RRRP3", "RRRP3.SA", "BVMF:BRAV3", "BMFBOVESPA:BRAV3", "BVMF:RRRP3", "BMFBOVESPA:RRRP3"],
  MBRF3: ["MBRF3.SA", "MBRF3 B3", "MRFG3", "MRFG3.SA", "BRFS3", "BRFS3.SA", "BVMF:MBRF3", "BMFBOVESPA:MBRF3", "BVMF:MRFG3", "BMFBOVESPA:MRFG3", "BVMF:BRFS3", "BMFBOVESPA:BRFS3"],
  EMBJ3: ["EMBJ3.SA", "EMBJ3 B3", "EMBR3", "EMBR3.SA", "BVMF:EMBJ3", "BMFBOVESPA:EMBJ3", "BVMF:EMBR3", "BMFBOVESPA:EMBR3"],
  // B3 renamed AZUL ON from AZUL4 to AZUL54 (Dec/2025); Yahoo serves AZUL54.SA.
  AZUL54: ["AZUL54.SA", "AZUL54 B3", "AZUL4", "AZUL4.SA", "BVMF:AZUL54", "BMFBOVESPA:AZUL54", "BVMF:AZUL4", "BMFBOVESPA:AZUL4"],
  // CPLE6 still trades on B3 as its own line — do NOT fold it into CPLE3.
  CPLE3: ["CPLE3.SA", "CPLE3 B3", "CPLE5", "CPLE5.SA", "BVMF:CPLE3", "BMFBOVESPA:CPLE3"],
  JBSS32: ["JBSS32.SA", "JBSS32 B3", "JBSS3", "JBSS3.SA", "BVMF:JBSS32", "BMFBOVESPA:JBSS32", "BVMF:JBSS3", "BMFBOVESPA:JBSS3"],
  B3SA3: ["B3SA3.SA", "B3SA3 B3", "BVMF:B3SA3", "BMFBOVESPA:B3SA3"],
  AXIA3: ["AXIA3.SA", "AXIA3 B3", "AXIA6", "AXIA6.SA", "ELET3", "ELET3.SA", "ELET6", "ELET6.SA", "BVMF:ELET3", "BVMF:ELET6", "BMFBOVESPA:ELET3", "BMFBOVESPA:ELET6", "BMFBOVESPA:AXIA6"],
  AXIA7: ["AXIA7.SA", "AXIA7 B3"],
  PETR4: ["PETR4.SA", "PETR4 B3", "PETR", "BVMF:PETR4", "BMFBOVESPA:PETR4"],
  VALE3: ["VALE3.SA", "VALE3 B3", "VALE", "BVMF:VALE3", "BMFBOVESPA:VALE3"],
  ITUB4: ["ITUB4.SA", "ITUB4 B3", "ITUB", "BVMF:ITUB4", "BMFBOVESPA:ITUB4"],
  BBAS3: ["BBAS3.SA", "BBAS3 B3", "BBAS", "BVMF:BBAS3", "BMFBOVESPA:BBAS3"],
  WIN: ["WIN$", "WINFUT", "WIN1!", "BMFBOVESPA:WIN1!"],
  AAPL: ["NASDAQ:AAPL", "AAPL.US"],
  BNY: ["NYSE:BNY", "BNY.US"],
  BULL: ["NASDAQ:BULL", "BULL.US"],
  BYDDY: ["OTC:BYDDY", "BYDDY.US"],
  CRM: ["NYSE:CRM", "CRM.US"],
  DIA: ["NYSEARCA:DIA", "DIA.US"],
  F: ["NYSE:F", "F.US"],
  IWM: ["NYSEARCA:IWM", "IWM.US"],
  MSFT: ["NASDAQ:MSFT", "MSFT.US"],
  NVDA: ["NASDAQ:NVDA", "NVDA.US"],
  TSLA: ["NASDAQ:TSLA", "TSLA.US"],
  VOO: ["NYSEARCA:VOO", "VOO.US"],
  SPY: ["NYSEARCA:SPY", "SPY.US"],
  QQQ: ["NASDAQ:QQQ", "QQQ.US"],
  A1MD34: ["AMD34", "AMD34.SA", "A1MD34.SA"],
  AMZO34: ["AMZN34", "AMZN34.SA", "AMZO34.SA"],
  ITLC34: ["INTC34", "INTC34.SA", "I1NC34", "I1NC34.SA", "ITLC34.SA"],
  M1TA34: ["META34", "META34.SA", "M1TA34.SA"],
};

const TRADING_VIEW_SYMBOL_FALLBACKS: Record<string, string[]> = {
  AXIA3: ["BMFBOVESPA:AXIA3", "BMFBOVESPA:AXIA6", "BMFBOVESPA:ELET6", "BMFBOVESPA:ELET3"],
  AXIA7: ["BMFBOVESPA:AXIA7"],
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
  if (cryptoMatch && CRYPTO_BASES.has(cryptoMatch[1])) {
    compact = `${cryptoMatch[1]}USD`;
  }

  return compact;
}

function hasMarketQualifier(value: unknown) {
  const raw = String(value || "").trim().toUpperCase();
  if (raw.endsWith(".US")) return true;
  if (!raw.includes(":")) return false;
  return US_MARKET_QUALIFIERS.has(raw.split(":")[0]?.trim() || "");
}

function buildAliasMap() {
  const map = new Map<string, string>();

  for (const [canonical, aliases] of Object.entries(CURATED_ALIASES)) {
    for (const alias of [canonical, ...aliases]) {
      const key = aliasKey(alias);
      if (key) map.set(key, canonical);
    }
  }

  for (const base of CRYPTO_BASES) {
    const canonical = `${base}USD`;
    const aliases = [
      canonical,
      `${base}USDT`,
      `${base}/USD`,
      `${base}/USDT`,
      `${base}-USD`,
      `${base}-USDT`,
      `BINANCE:${base}USDT`,
    ];
    if (base === "BTC") aliases.push("XBTUSD", "XBTUSDT", "XBT/USD");
    for (const alias of aliases) {
      const key = aliasKey(alias);
      if (key) map.set(key, canonical);
    }
  }

  for (const [symbol, exchange] of Object.entries(US_EXCHANGE_BY_SYMBOL)) {
    for (const alias of [symbol, `${exchange}:${symbol}`, `${symbol}.US`]) {
      const key = aliasKey(alias);
      if (key) map.set(key, symbol);
    }
  }

  return map;
}

const ALIAS_TO_CANONICAL = buildAliasMap();

export function canonicalSymbol(value: unknown) {
  const key = aliasKey(value);
  if (!key) return "";
  const marketQualified = hasMarketQualifier(value);
  const cryptoMatch = key.match(CRYPTO_RE);
  if (CRYPTO_BASES.has(key)) return marketQualified && US_EXCHANGE_BY_SYMBOL[key] ? key : "";
  if (marketQualified && cryptoMatch && CRYPTO_BASES.has(cryptoMatch[1])) return "";
  if (marketQualified && (B3_RE.test(key) || B3_FUTURE_RE.test(key))) {
    return US_EXCHANGE_BY_SYMBOL[key] ? key : "";
  }

  const mapped = ALIAS_TO_CANONICAL.get(key);
  if (mapped) return mapped;
  if ((key.endsWith("34") || key.endsWith("32")) && !KNOWN_BDR_SYMBOLS.has(key)) return "";
  if (B3_RE.test(key) || B3_FUTURE_RE.test(key)) return key;

  if (cryptoMatch && CRYPTO_BASES.has(cryptoMatch[1])) return `${cryptoMatch[1]}USD`;
  if (US_RE.test(key)) return key;
  return "";
}

export function isAmbiguousCryptoSymbol(value: unknown) {
  return CRYPTO_BASES.has(aliasKey(value)) && !hasMarketQualifier(value);
}

export function isBdrSymbol(value: unknown) {
  return KNOWN_BDR_SYMBOLS.has(canonicalSymbol(value));
}

export function canonicalSymbolAliases(value: unknown) {
  const canonical = canonicalSymbol(value);
  if (!canonical) return [];

  const aliases = new Set<string>([canonical]);
  for (const [alias, mapped] of ALIAS_TO_CANONICAL.entries()) {
    if (mapped === canonical) aliases.add(alias);
  }
  if (B3_RE.test(canonical)) {
    aliases.add(`${canonical}.SA`);
    aliases.add(`BMFBOVESPA:${canonical}`);
  }
  if (canonical.endsWith("USD")) {
    const base = canonical.slice(0, -3);
    aliases.add(`${base}USDT`);
    aliases.add(`${base}-USD`);
    aliases.add(`${base}-USDT`);
    aliases.add(`${base}/USD`);
    aliases.add(`${base}/USDT`);
    if (base === "BTC") {
      aliases.add("XBTUSD");
      aliases.add("XBTUSDT");
    }
  }
  if (US_EXCHANGE_BY_SYMBOL[canonical]) {
    aliases.add(`${US_EXCHANGE_BY_SYMBOL[canonical]}:${canonical}`);
    aliases.add(`${canonical}.US`);
  }
  if (canonical === "WIN") {
    aliases.add("WIN$");
    aliases.add("WINFUT");
    aliases.add("WIN1!");
    aliases.add("BMFBOVESPA:WIN1!");
  }
  return Array.from(aliases);
}

export function resolveTradingViewSymbolCandidates(value: unknown) {
  const canonical = canonicalSymbol(value);
  if (!canonical) return ["BMFBOVESPA:PETR4"];
  const curatedFallbacks = TRADING_VIEW_SYMBOL_FALLBACKS[canonical];
  if (curatedFallbacks?.length) return curatedFallbacks;
  if (canonical === "WIN") return ["BMFBOVESPA:WIN1!"];
  if (canonical.endsWith("USD") && CRYPTO_BASES.has(canonical.slice(0, -3))) {
    return [`BINANCE:${canonical.slice(0, -3)}USDT`];
  }
  if (B3_RE.test(canonical)) return [`BMFBOVESPA:${canonical}`];
  return [`${US_EXCHANGE_BY_SYMBOL[canonical] || "NASDAQ"}:${canonical}`];
}

export function resolveTradingViewSymbol(value: unknown) {
  return resolveTradingViewSymbolCandidates(value)[0] || "BMFBOVESPA:PETR4";
}

export function tradingViewSymbolFor(value: unknown) {
  return resolveTradingViewSymbol(value);
}

export function providerSymbolFor(value: unknown) {
  const canonical = canonicalSymbol(value);
  if (!canonical) return "";
  if (canonical === "WIN") return "WIN1!";
  if (canonical.endsWith("USD") && CRYPTO_BASES.has(canonical.slice(0, -3))) {
    return `${canonical.slice(0, -3)}-USD`;
  }
  if (B3_RE.test(canonical)) return `${canonical}.SA`;
  return canonical;
}

export function symbolCategoryFor(value: unknown) {
  const canonical = canonicalSymbol(value);
  if (!canonical) return "";
  if (canonical.endsWith("USD") && CRYPTO_BASES.has(canonical.slice(0, -3))) return "Crypto";
  if (KNOWN_BDR_SYMBOLS.has(canonical)) return "BDR";
  if (B3_RE.test(canonical) || B3_FUTURE_RE.test(canonical) || canonical === "WIN") return "B3";
  return "USA";
}
