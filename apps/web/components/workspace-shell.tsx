"use client";

import { startTransition, useDeferredValue, useEffect, useMemo, useRef, useState } from "react";
import type { ReactNode } from "react";
import { useSearchParams } from "next/navigation";

import { TickerChart } from "@/components/ticker-chart";
import {
  WorkspaceEducationPanel,
  WorkspaceNewsPanel,
  WorkspaceSearchPanel,
} from "@/components/workspace-sections";
import {
  WorkspaceLeftRail,
  WorkspaceRightRail,
} from "@/components/workspace-rails";
import {
  blockUser,
  buildWebSocketUrl,
  commentOnPost,
  createPost,
  deletePost,
  getAccess,
  getBootstrap,
  getChart,
  getChatHistory,
  getFeed,
  getPublicInsight,
  getPublicChart,
  getPublicQuote,
  getPublicQuotesRobust,
  getNews,
  getMediaStatus,
  getPoll,
  getPushStatus,
  getQuote,
  searchAssets,
  getWorkspace,
  followUser,
  likePost,
  loginJson,
  logoutAuth,
  muteUser,
  postChatMessage,
  repostPost,
  reportPost,
  requestTelegramLink,
  resolveApiBase,
  saveWorkspaceLayout,
  unrepostPost,
  unfollowUser,
  unlikePost,
  updateProfile,
  uploadMedia,
  verifyLoginOtp,
  votePoll,
} from "@/lib/api";
import type {
  AiToolRow,
  AiToolMetrics,
  AuthFlowResponse,
  ChartPayload,
  ChatHistoryPayload,
  FeedPayload,
  FeedPost,
  NewsItem,
  NewsPayload,
  PollPayload,
  PollOption,
  PublicBootstrap,
  PublicInsightPayload,
  QuotePayload,
  RankingRow,
  SignalRow,
  TelegramLinkSessionResponse,
  UserAccess,
  WorkspaceData,
  WorkspaceTab,
} from "@/lib/types";

type Props = {
  focusedTab?: string;
  initialTicker?: string;
};

type ChartSettings = {
  show_markers: boolean;
  show_zones: boolean;
};

type WatchlistItem = {
  symbol: string;
  label: string;
  category: string;
  price?: number | null;
  changePct?: number | null;
  change?: number | null;
  volume?: number | null;
  score?: number | null;
  trend?: string | null;
  rsi?: number | null;
  bias?: string | null;
};

type ToolCopyItem = {
  title: string;
  description: string;
  explanation: string;
};

type WorkspacePersona = "guiado" | "trader" | "pro";
type AppLocale = "pt-BR" | "en-US";
type SettingsTab = "preferencias" | "bloqueados" | "silenciados";
type AccountPanel = "perfil" | "editar" | "upgrade";
type UserListEntry = {
  id: number;
  nome: string;
  identificador: string;
  avatarUrl?: string | null;
};

type ReferralLeaderboardItem = {
  position: number;
  name: string;
  badge?: string | null;
  total_validated: number;
  total_active: number;
  paid_referrals: string[];
};

type ReferralLeaderboardPayload = {
  items: ReferralLeaderboardItem[];
  rules: {
    valid_after_days: number;
    reward: string;
    vip_badge_at: number;
    leaderboard_badge_at: number;
  };
};

const AI_TOOL_TAB_MAP = {
  "heat-map": "heat_map",
  radar: "radar",
  "breakout-probability": "breakout_probability",
  "volatility-squeeze": "volatility_squeeze",
  "institutional-flow": "institutional_flow",
  "smart-money": "smart_money",
  accumulation: "accumulation",
  "liquidity-sweep": "liquidity_sweep",
  "liquidity-map": "liquidity_map",
  "market-regime": "market_regime",
  "master-score": "master_score",
} as const;

const TAB_META: Record<string, { label: string; short: string }> = {
  grafico: { label: "📈 IA Gráfico / Rede Social", short: "Gráfico/Rede Social" },
  news: { label: "📰 Notícias", short: "Notícias" },
  busca: { label: "🔎 Busca", short: "Busca" },
  "heat-map": { label: "🗺 IA Mapa de Calor", short: "Mapa" },
  radar: { label: "⚡ IA Radar", short: "Radar" },
  "breakout-probability": { label: "🎯 IA Probabilidade de Breakout", short: "Breakout" },
  "volatility-squeeze": { label: "🟣 IA Compressão de Volatilidade", short: "Squeeze" },
  "institutional-flow": { label: "🏦 IA Fluxo Institucional", short: "Fluxo" },
  "smart-money": { label: "💼 IA Dinheiro Inteligente", short: "Smart" },
  accumulation: { label: "📦 IA Acumulação", short: "Acumulação" },
  "liquidity-sweep": { label: "🧲 IA Varredura de Liquidez", short: "Varredura" },
  "liquidity-map": { label: "🧭 IA Liquidity Map", short: "IA Liquidity Map" },
  "market-regime": { label: "📊 IA Regime de Mercado", short: "Regime" },
  "master-score": { label: "⭐ IA Score Mestre", short: "Score" },
  referrals: { label: "🤝 Indicações", short: "Indicações" },
  education: { label: "🎓 Ajuda Educacional para o Trader", short: "Ajuda" },
};

const TAB_META_EN: Record<string, { label: string; short: string }> = {
  grafico: { label: "📈 AI Chart / Social Network", short: "Chart/Social" },
  news: { label: "📰 News", short: "News" },
  busca: { label: "🔎 Search", short: "Search" },
  "heat-map": { label: "🗺 AI Heat Map", short: "Heat Map" },
  radar: { label: "⚡ AI Radar", short: "Radar" },
  "breakout-probability": { label: "🎯 AI Breakout Probability", short: "Breakout" },
  "volatility-squeeze": { label: "🟣 AI Volatility Squeeze", short: "Squeeze" },
  "institutional-flow": { label: "🏦 AI Institutional Flow", short: "Flow" },
  "smart-money": { label: "💼 AI Smart Money", short: "Smart" },
  accumulation: { label: "📦 AI Accumulation", short: "Accumulation" },
  "liquidity-sweep": { label: "🧲 AI Liquidity Sweep", short: "Sweep" },
  "liquidity-map": { label: "🧭 AI Liquidity Map", short: "Liquidity Map" },
  "market-regime": { label: "📊 AI Market Regime", short: "Regime" },
  "master-score": { label: "⭐ AI Master Score", short: "Master Score" },
  referrals: { label: "🤝 Referrals", short: "Referrals" },
  education: { label: "🎓 Trader Help", short: "Help" },
};

const WORKSPACE_PERSONAS: Record<
  WorkspacePersona,
  {
    label: string;
    subtitle: string;
    emphasis: string;
    feedHint: string;
  }
> = {
  guiado: {
    label: "Guiado",
    subtitle: "Explica melhor o que importa primeiro.",
    emphasis: "Comece por preço, notícia útil e leitura final da IA.",
    feedHint: "Use o feed para contexto; confirme tudo no gráfico.",
  },
  trader: {
    label: "Trader",
    subtitle: "Equilíbrio entre contexto, fluxo e execução.",
    emphasis: "Preço, IA, notícias e comunidade em leitura rápida.",
    feedHint: "Feed e notícias funcionam como confirmação tática.",
  },
  pro: {
    label: "Pro",
    subtitle: "Menos explicação, mais densidade operacional.",
    emphasis: "Priorize score, regime, fluxo, liquidez e evento de preço.",
    feedHint: "Ignore ruído e trate notícia como gatilho só com preço confirmando.",
  },
};

const WORKSPACE_PERSONAS_EN: Record<WorkspacePersona, (typeof WORKSPACE_PERSONAS)[WorkspacePersona]> = {
  guiado: {
    label: "Guided",
    subtitle: "Explains what matters first.",
    emphasis: "Start with price, useful news and the final AI read.",
    feedHint: "Use the feed for context; confirm everything on the chart.",
  },
  trader: {
    label: "Trader",
    subtitle: "Balanced context, flow and execution.",
    emphasis: "Price, AI, news and community in a quick read.",
    feedHint: "Feed and news work as tactical confirmation.",
  },
  pro: {
    label: "Pro",
    subtitle: "Less explanation, more operating density.",
    emphasis: "Prioritize score, regime, flow, liquidity and price events.",
    feedHint: "Ignore noise and treat news as a trigger only with price confirmation.",
  },
};

const TOP_TAB_TEXT: Record<string, string> = {
  grafico: "IA Gráfico/ Rede Social",
  news: "Notícias",
  "heat-map": "IA Mapa de Calor",
  radar: "IA Radar",
  "breakout-probability": "IA Breakout",
  "volatility-squeeze": "IA Squeeze",
  "institutional-flow": "IA Fluxo",
  "smart-money": "IA Smart",
  accumulation: "IA Acumulação",
  "liquidity-sweep": "IA Varredura",
  "liquidity-map": "IA Liquidity Map",
  "market-regime": "IA Regime",
  "master-score": "Score Mestre",
  referrals: "Indicações",
  education: "Ajuda",
};

const TOP_TAB_TEXT_EN: Record<string, string> = {
  grafico: "AI Chart / Social",
  news: "News",
  "heat-map": "AI Heat Map",
  radar: "AI Radar",
  "breakout-probability": "AI Breakout",
  "volatility-squeeze": "AI Squeeze",
  "institutional-flow": "AI Flow",
  "smart-money": "AI Smart",
  accumulation: "AI Accumulation",
  "liquidity-sweep": "AI Sweep",
  "liquidity-map": "AI Liquidity Map",
  "market-regime": "AI Regime",
  "master-score": "Master Score",
  referrals: "Referrals",
  education: "Help",
};

const TAB_ORDER = [
  "grafico",
  "news",
  "heat-map",
  "radar",
  "breakout-probability",
  "volatility-squeeze",
  "institutional-flow",
  "smart-money",
  "accumulation",
  "liquidity-sweep",
  "liquidity-map",
  "market-regime",
  "master-score",
  "referrals",
  "education",
];

const TOP_BAR_TAB_IDS = TAB_ORDER.filter((id) => id !== "busca");
const DETACHABLE_IA_TABS = new Set([
  "grafico",
  "heat-map",
  "radar",
  "breakout-probability",
  "volatility-squeeze",
  "institutional-flow",
  "smart-money",
  "accumulation",
  "liquidity-sweep",
  "liquidity-map",
  "market-regime",
  "master-score",
]);

const FALLBACK_TABS: WorkspaceTab[] = [
  { id: "grafico", title: "IA Gráfico / Rede Social" },
  { id: "news", title: "Notícias" },
  { id: "busca", title: "Busca" },
  { id: "heat-map", title: "IA Mapa de Calor" },
  { id: "radar", title: "IA Radar" },
  { id: "breakout-probability", title: "IA Probabilidade de Breakout" },
  { id: "volatility-squeeze", title: "IA Compressão de Volatilidade" },
  { id: "institutional-flow", title: "IA Fluxo Institucional" },
  { id: "smart-money", title: "IA Dinheiro Inteligente" },
  { id: "accumulation", title: "IA Acumulação" },
  { id: "liquidity-sweep", title: "IA Varredura de Liquidez" },
  { id: "liquidity-map", title: "IA Liquidity Map" },
  { id: "market-regime", title: "IA Regime de Mercado" },
  { id: "master-score", title: "IA Score Mestre" },
  { id: "referrals", title: "Indicações" },
  { id: "education", title: "Ajuda Educacional para o Trader" },
];

const CATEGORY_ORDER = ["B3", "BDR", "Crypto", "USA"] as const;
const DEFAULT_CHART_SETTINGS: ChartSettings = {
  show_markers: true,
  show_zones: true,
};
const APP_LOCALE_STORAGE_KEY = "snbr-app-locale";
const AI_ALERT_HISTORY_STORAGE_KEY = "snbr-ai-alert-history-v5";
const MAINTENANCE_NOTICES = [
  {
    id: "maintenance-window",
    titulo: "Manutenção programada",
    corpo: "O site entrará em manutenção em 30/04/2026 às 23:00. Website, app e Telegram podem oscilar por alguns minutos.",
  },
];
const B3_SYMBOL_PATTERN = /^[A-Z]{4}(?:3|4|5|6|11)$/;
const BDR_SYMBOL_PATTERN = /^[A-Z]{4,5}34$/;
const USA_SYMBOL_PATTERN = /^[A-Z]{1,5}$/;
const FUTURES_MONTH_CODES = ["F", "G", "H", "J", "K", "M", "N", "Q", "U", "V", "X", "Z"] as const;
const FUTURES_MONTH_NAMES: Record<string, string> = {
  F: "Jan",
  G: "Fev",
  H: "Mar",
  J: "Abr",
  K: "Mai",
  M: "Jun",
  N: "Jul",
  Q: "Ago",
  U: "Set",
  V: "Out",
  X: "Nov",
  Z: "Dez",
};
const FUTURES_MONTH_NAMES_EN: Record<string, string> = {
  F: "Jan",
  G: "Feb",
  H: "Mar",
  J: "Apr",
  K: "May",
  M: "Jun",
  N: "Jul",
  Q: "Aug",
  U: "Sep",
  V: "Oct",
  X: "Nov",
  Z: "Dec",
};
const DERIVATIVE_HINTS: Record<string, string> = {
  CME: "CME Group",
  NQ: "E-mini Nasdaq",
  MNQ: "Micro E-mini Nasdaq",
  MNO: "Micro E-mini Nasdaq",
  ES: "E-mini S&P 500",
  MES: "Micro E-mini S&P 500",
  MYM: "Micro E-mini Dow",
};

function buildRollingB3Futures(date = new Date()) {
  const monthKeys = [0, 1].map((offset) => {
    const monthIndex = date.getMonth() + offset;
    const contractDate = new Date(date.getFullYear(), monthIndex, 1);
    const code = FUTURES_MONTH_CODES[contractDate.getMonth()] || "F";
    const year = String(contractDate.getFullYear()).slice(-2);
    return { code, year };
  });

  return monthKeys.flatMap(({ code, year }) => [`WIN${code}${year}`, `WDO${code}${year}`]);
}

function b3FutureLabel(symbol: string, locale: AppLocale = "pt-BR") {
  const match = /^(WIN|WDO)([FGHJKMNQUVXZ])(\d{2})$/.exec(symbol);
  if (!match) return "";

  const [, root, monthCode, year] = match;
  const contractName =
    locale === "en-US"
      ? root === "WIN"
        ? "Mini Bovespa Index Futures"
        : "Mini Commercial Dollar Futures"
      : root === "WIN"
        ? "Mini Indice Futuro Bovespa"
        : "Mini Dolar Futuro";
  const monthName =
    locale === "en-US" ? FUTURES_MONTH_NAMES_EN[monthCode] || monthCode : FUTURES_MONTH_NAMES[monthCode] || monthCode;
  return `${contractName} ${monthName}/20${year}`;
}

const WATCHLIST_B3 = [
  ...buildRollingB3Futures(),
  "ITUB4.SA", "BBDC4.SA", "BBAS3.SA", "SANB11.SA", "BPAC11.SA",
  "VALE3.SA", "PETR4.SA", "PETR3.SA", "SUZB3.SA", "KLBN11.SA",
  "ELET3.SA", "ELET6.SA", "CPFE3.SA", "EQTL3.SA",
  "MGLU3.SA", "LREN3.SA", "AMER3.SA", "VIIA3.SA", "ASAI3.SA",
  "WEGE3.SA", "GGBR4.SA", "CSNA3.SA", "USIM5.SA",
  "TOTS3.SA", "POSI3.SA",
  "RAIL3.SA", "CCRO3.SA", "NTCO3.SA",
  "ABEV3.SA", "B3SA3.SA", "BBSE3.SA", "BRAP4.SA", "BRFS3.SA",
  "CMIG4.SA", "COGN3.SA", "CPLE6.SA", "CRFB3.SA", "CSAN3.SA",
  "CYRE3.SA", "DXCO3.SA", "EMBR3.SA", "ENEV3.SA", "ENGI11.SA",
  "EZTC3.SA", "HAPV3.SA", "HYPE3.SA", "IRBR3.SA", "JBSS3.SA",
  "MRFG3.SA", "MRVE3.SA", "MULT3.SA", "PCAR3.SA", "PRIO3.SA",
  "RADL3.SA", "RAIZ4.SA", "RDOR3.SA", "RENT3.SA", "RRRP3.SA",
  "SBSP3.SA", "SLCE3.SA", "SMTO3.SA", "TAEE11.SA", "TIMS3.SA",
  "UGPA3.SA", "VBBR3.SA", "VIVT3.SA", "YDUQ3.SA", "AZUL4.SA",
];

const WATCHLIST_BDR = [
  "AAPL34.SA", "MSFT34.SA", "GOGL34.SA", "AMZN34.SA",
  "NVDC34.SA", "TSLA34.SA", "META34.SA", "NFLX34.SA",
  "INTC34.SA", "AMD34.SA", "QCOM34.SA", "IVVB11.SA",
];
const BDR_UNDERLYING: Record<string, string> = {
  AAPL34: "AAPL",
  MSFT34: "MSFT",
  GOGL34: "GOOGL",
  AMZN34: "AMZN",
  NVDC34: "NVDA",
  TSLA34: "TSLA",
  META34: "META",
  NFLX34: "NFLX",
  INTC34: "INTC",
  AMD34: "AMD",
  QCOM34: "QCOM",
};

const WATCHLIST_US = [
  "CME", "NQ", "MNQ", "MNO", "ES", "MES", "MYM",
  "AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "TSLA",
  "AMD", "INTC", "AVGO", "TSM",
  "JPM", "BAC", "GS",
  "XOM", "CVX",
  "COST", "WMT", "DIS",
  "CRM", "SNOW", "PLTR",
];

const WATCHLIST_CRYPTO = [
  "BTC-USD",
  "ETH-USD",
  "BNB-USD",
  "SOL-USD",
  "XRP-USD",
  "ADA-USD",
  "DOGE-USD",
];

const FIXED_TAPE_SYMBOLS = [
  "PETR4",
  "VALE3",
  "ITUB4",
  "BBDC4",
  "BPAC11",
  "AAPL",
  "NVDA",
  "TSLA",
  "BTCUSD",
  "ETHUSD",
  "MSFT",
  "IVVB11",
];

const HELP_MANUAL_ITEMS = [
  "🧠 Heat Map → mostra ativos fortes (🟢 compra) e fracos (🔴 venda).",
  "⚡ Radar → detecta ativos que começaram a se mover rápido.",
  "🎯 Probabilidade de Breakout → indica rompimento de resistência importante.",
  "🟣 Compressão de Volatilidade → alerta quando o mercado está “quieto” e pode explodir.",
  "🏦 Fluxo Institucional → identifica entrada de grandes investidores.",
  "💰 Dinheiro Inteligente → mostra sinais dos grandes players antes de movimentos fortes.",
  "🏛 Acumulação → detecta compras discretas de instituições.",
  "🧲 Varredura de Liquidez → mostra rompimentos falsos para buscar liquidez.",
  "🧭 IA Liquidity Map → indica onde há concentração de stops e liquidez.",
  "📊 Regime de Mercado → classifica o mercado: 📈 alta, 📉 baixa ou ➡ lateral.",
  "⭐ Score Mestre → pontuação geral da oportunidade (90 = forte, 70 = moderada, <50 = fraca).",
  "📈 Gráfico IA → exibe sinais no gráfico: COMPRA, VENDA A DESCOBERTO ou ⚠ encerrar posição.",
];

const HELP_MANUAL_ITEMS_EN = [
  "🧠 Heat Map → shows strong assets (🟢 buy) and weak assets (🔴 sell).",
  "⚡ Radar → detects assets that started moving fast.",
  "🎯 Breakout Probability → highlights important resistance breakouts.",
  "🟣 Volatility Squeeze → warns when the market is quiet and may expand.",
  "🏦 Institutional Flow → identifies large investor participation.",
  "💰 Smart Money → surfaces signals from large players before stronger moves.",
  "🏛 Accumulation → detects discreet institutional buying.",
  "🧲 Liquidity Sweep → flags false breakouts used to seek liquidity.",
  "🧭 AI Liquidity Map → shows where stops and liquidity are concentrated.",
  "📊 Market Regime → classifies the market: 📈 uptrend, 📉 downtrend or ➡ range.",
  "⭐ Master Score → consolidated opportunity score (90 = strong, 70 = moderate, <50 = weak).",
  "📈 AI Chart / Social Network → displays BUY LONG, CLOSE LONG, SELL SHORT or CLOSE SHORT markers.",
];

const EDUCATIONAL_HELP_SECTIONS = [
  {
    title: "📚 Ajuda Educacional para o Trader",
    body: [
      "Bem-vindo ao StockNewsBR 🚀",
      "Aqui você encontra ferramentas de Inteligência Artificial que analisam o mercado em tempo real e transformam dados complexos em informações simples para qualquer trader. 📊",
      "Nosso objetivo é: te ajudar a enxergar oportunidades de forma clara e prática.",
    ],
  },
  {
    title: "🧠 IA Heat Map",
    body: [
      "Mostra quais ativos estão mais fortes ou mais fracos.",
      "• 🟢 Verde = força compradora",
      "• 🔴 Vermelho = pressão vendedora",
      "👉 Exemplo: Se PETR4 aparece verde, significa que está ganhando força no momento. 📈",
    ],
  },
  {
    title: "⚡ IA Radar",
    body: [
      "Detecta ativos que começaram a se mover rápido.",
      "👉 Exemplo: Uma ação dispara com aumento de volume. O Radar te avisa na hora. ⚡",
    ],
  },
  {
    title: "🎯 IA Probabilidade de Rompimento",
    body: [
      "Indica quando um ativo está prestes a romper uma resistência.",
      "👉 Exemplo: Um papel ficou entre 10 e 10.20. Se romper 10.20 com volume, pode iniciar uma alta forte. 🚀",
    ],
  },
  {
    title: "🟣 IA Compressão de Volatilidade",
    body: [
      "Mostra quando o mercado está “quieto demais” e pode explodir em movimento.",
      "👉 Exemplo: Preço andando de lado por dias → depois vem uma expansão forte. 💥",
    ],
  },
  {
    title: "🏦 IA Fluxo Institucional",
    body: [
      "Detecta entrada de investidores grandes (institucionais).",
      "👉 Exemplo: Um ativo sobe com volume muito acima da média → sinal de possível compra institucional. 🏦",
    ],
  },
  {
    title: "💰 IA Dinheiro Inteligente",
    body: [
      "Mostra sinais de movimentação dos grandes players.",
      "👉 Exemplo: Volume crescente antes de uma alta ou queda forte. 📊",
    ],
  },
  {
    title: "🏛 IA Acumulação",
    body: [
      "Identifica quando grandes investidores estão comprando aos poucos.",
      "👉 Exemplo: Preço estável, mas volume aumentando devagar. 📈",
    ],
  },
  {
    title: "🧲 IA Varredura de Liquidez",
    body: [
      "Mostra quando o mercado busca liquidez antes de mudar de direção.",
      "👉 Exemplo: Preço rompe o topo, ativa stops e depois volta para baixo. 🧲",
    ],
  },
  {
    title: "🗺 IA Liquidity Map",
    body: [
      "Mostra onde há maior concentração de liquidez.",
      "👉 Exemplo: Muitos stops acima de um nível → preço tende a buscar esse ponto. 🗺",
    ],
  },
  {
    title: "📊 IA Market Regime",
    body: [
      "Mostra o tipo de mercado atual:",
      "• 📈 Tendência de alta",
      "• 📉 Tendência de baixa",
      "• ➡ Mercado lateral",
      "👉 Isso ajuda a escolher a estratégia certa.",
    ],
  },
  {
    title: "⭐ IA Master Score",
    body: [
      "Pontuação geral da IA sobre oportunidades.",
      "👉 Exemplo:",
      "• Score 90 → oportunidade forte",
      "• Score 70 → moderada",
      "• Score < 50 → baixa probabilidade",
    ],
  },
  {
    title: "📈 IA Gráfico",
    body: [
      "Mostra o gráfico com sinais da IA:",
      "• 📈 BUY",
      "• 📉 SHORT",
      "• ⚠ Encerrar posição",
      "👉 Ajuda a identificar pontos de entrada e saída.",
    ],
  },
  {
    title: "🖥️ Versão Web Trader Desk",
    body: [
      "Plataforma inspirada nos terminais de Hedge Funds dos EUA.",
      "• Suporte a múltiplos monitores 🖥️",
      "• Velocidade e análise avançada 🤖📊",
      "👉 Exemplo de uso:",
      "• Monitor 1 → 🧠 Heat Map",
      "• Monitor 2 → ⚡ Radar",
      "• Monitor 3 → 🎯 Breakout",
      "... e assim por diante.",
      "Se tiver apenas um monitor, basta abrir cada IA em abas diferentes do navegador. 📊",
    ],
  },
  {
    title: "⚠ Importante",
    body: [
      "• As análises são apoio inteligente, não garantias.",
      "• Sempre use gestão de risco.",
      "• O mercado é dinâmico, e disciplina é essencial.",
      "• 👉 Agora você tem um guia rápido para consultar em segundos e não perder nenhuma oportunidade! 🚀📊",
      "👉 Boas trades e muito sucesso! 🚀📈",
    ],
  },
];

const EDUCATIONAL_HELP_SECTIONS_EN = [
  {
    title: "📚 Trader Educational Help",
    body: [
      "Welcome to StockNewsBR.",
      "Here you find AI tools that analyze the market in real time and turn complex data into a simple trader screen.",
      "The goal is to help you see opportunities clearly and act only after price, volume and risk confirm the thesis.",
    ],
  },
  {
    title: "🧠 AI Heat Map",
    body: [
      "Shows which assets are stronger or weaker.",
      "• 🟢 Green = buying strength",
      "• 🔴 Red = selling pressure",
      "Example: if PETR4 appears green, the asset is gaining relative strength now.",
    ],
  },
  {
    title: "⚡ AI Radar",
    body: [
      "Detects assets that started moving quickly.",
      "Example: a stock accelerates with higher volume and Radar alerts it immediately.",
    ],
  },
  {
    title: "🎯 AI Breakout Probability",
    body: [
      "Indicates when an asset is close to breaking an important resistance.",
      "Example: price stayed between 10 and 10.20. If it breaks 10.20 with volume, a stronger trend may start.",
    ],
  },
  {
    title: "🟣 AI Volatility Squeeze",
    body: [
      "Shows when volatility is too compressed and the next expansion may matter.",
      "Example: price moves sideways for days, then a strong expansion starts.",
    ],
  },
  {
    title: "🏦 AI Institutional Flow",
    body: [
      "Detects participation from larger investors.",
      "Example: an asset rises with volume far above average, suggesting possible institutional buying.",
    ],
  },
  {
    title: "💰 AI Smart Money",
    body: [
      "Shows signs of large-player positioning.",
      "Example: rising volume before a strong move up or down.",
    ],
  },
  {
    title: "🏛 AI Accumulation",
    body: [
      "Identifies when large investors may be building a position gradually.",
      "Example: stable price with volume slowly rising.",
    ],
  },
  {
    title: "🧲 AI Liquidity Sweep",
    body: [
      "Shows when the market seeks liquidity before changing direction.",
      "Example: price breaks a high, triggers stops and then rejects back down.",
    ],
  },
  {
    title: "🗺 AI Liquidity Map",
    body: [
      "Shows where liquidity is concentrated.",
      "Example: many stops above a level can attract price before a reaction.",
    ],
  },
  {
    title: "📊 AI Market Regime",
    body: [
      "Shows the current market type:",
      "• 📈 Uptrend",
      "• 📉 Downtrend",
      "• ➡ Range",
      "This helps choose the right strategy for the current environment.",
    ],
  },
  {
    title: "⭐ AI Master Score",
    body: [
      "The consolidated AI opportunity score.",
      "Example:",
      "• Score 90 = strong opportunity",
      "• Score 70 = moderate",
      "• Score < 50 = low probability",
    ],
  },
  {
    title: "📈 AI Chart",
    body: [
      "Shows chart signals with operational labels:",
      "• Buy Long",
      "• Close Long",
      "• Sell Short",
      "• Close Short",
      "It helps identify entries, exits and invalidation points.",
    ],
  },
  {
    title: "🖥️ Web Trader Desk",
    body: [
      "A web desk inspired by institutional trading terminals.",
      "• Multi-monitor workflow",
      "• Fast AI and market analysis",
      "Example:",
      "• Monitor 1 → Heat Map",
      "• Monitor 2 → Radar",
      "• Monitor 3 → Breakout",
      "With one monitor, open each AI in a different browser tab.",
    ],
  },
  {
    title: "⚠ Important",
    body: [
      "• AI analysis is decision support, not a guarantee.",
      "• Always use risk management.",
      "• Markets are dynamic and discipline matters.",
      "• Use this guide as a quick reference before acting on any setup.",
    ],
  },
];

const INSTITUTIONAL_SECTIONS = [
  {
    id: "institucional-sobre",
    label: "1️⃣ Sobre a empresa",
    title: "🏛 Sobre a empresa",
    body: [
      "StockNewsBR é uma plataforma brasileira de Inteligência de Mercado com IA para traders de B3, BDR, ações dos EUA e cripto.",
      "A proposta do produto é transformar leitura institucional, fluxo, estrutura e contexto do mercado em uma tela simples, rápida e prática para operação diária.",
    ],
  },
  {
    id: "institucional-produto",
    label: "2️⃣ Descrição do produto",
    title: "📦 Descrição do produto",
    body: [
      "O produto principal nasce no app Google Play e libera experiência integrada entre app, website e Telegram conforme o plano do usuário.",
      "As superfícies atuais incluem gráfico com IA, heat map, radar, breakout probability, institutional flow, smart money, accumulation, liquidity sweep, liquidity map, market regime, master score, comunidade e ajuda educacional.",
    ],
  },
  {
    id: "institucional-educacao",
    label: "3️⃣ Educação financeira",
    title: "🎓 Educação financeira",
    body: [
      "A aba Ajuda foi criada para explicar cada IA em português claro, com exemplos simples para qualquer trader entender como usar a leitura no dia a dia.",
      "O objetivo educacional é orientar, não prometer resultado. Toda decisão continua exigindo disciplina e gestão de risco.",
    ],
  },
  {
    id: "institucional-aviso-legal",
    label: "4️⃣ Aviso legal",
    title: "⚠️ Aviso legal",
    body: [
      "As ferramentas do StockNewsBR são apoio analítico e educacional. Elas não constituem recomendação individual de compra, venda ou manutenção de ativos.",
      "Mercado financeiro envolve risco. O usuário deve tomar decisões por conta própria e usar gestão de risco em todas as operações.",
    ],
  },
  {
    id: "institucional-termos",
    label: "5️⃣ Termos de uso",
    title: "📄 Termos de uso",
    body: [
      "O acesso ao produto depende do plano contratado e do respeito às regras da comunidade, incluindo uso responsável do feed social, polls e ferramentas de IA.",
      "Contas Premium usam OTP por email e política de sessão mais rígida para evitar compartilhamento indevido.",
    ],
  },
  {
    id: "institucional-privacidade",
    label: "6️⃣ Política de privacidade",
    title: "🔐 Política de privacidade",
    body: [
      "Dados básicos de conta, autenticação, perfil e preferências são usados para operar o acesso ao app, website, Telegram e recursos da comunidade.",
      "Quando o trader publica no feed, o nome, a foto e o email configurados no profile são usados para identificar o post dentro do ticker.",
    ],
  },
  {
    id: "institucional-cookies",
    label: "7️⃣ Política de cookies",
    title: "🍪 Política de cookies",
    body: [
      "A versão web utiliza cookies e armazenamento local para manter sessão, preferências de layout, ticker selecionado e continuidade da experiência do trader.",
      "Esses recursos ajudam a salvar workspace, autenticação e contexto entre visitas.",
    ],
  },
  {
    id: "institucional-contato",
    label: "8️⃣ Contato / empresa",
    title: "📬 Contato / empresa",
    body: [
      "Canal institucional principal: https://www.stocknewsbr.com",
      "As comunicações oficiais da empresa devem ser publicadas nos canais institucionais da própria StockNewsBR.",
    ],
  },
  {
    id: "institucional-redes",
    label: "9️⃣ Redes sociais",
    title: "🌐 Redes sociais",
    body: [
      "As redes sociais oficiais e o Telegram da StockNewsBR servem para distribuição de alertas, novidades do produto e comunicação institucional.",
      "Sempre confirme se o canal está vinculado aos endereços oficiais da empresa antes de confiar em qualquer mensagem.",
    ],
  },
  {
    id: "institucional-ajuda-trader",
    label: "🔟 Ajuda Educacional para o Trader",
    title: "🎓 Ajuda Educacional para o Trader",
    body: [
      "Esta seção reúne o manual rápido, explicações de cada IA e a forma correta de ler os sinais no app, web e Trader Desk.",
      "Sempre que clicar neste item, a plataforma abre a aba Ajuda e leva o trader direto para o conteúdo educacional oficial do StockNewsBR.",
    ],
  },
];

const INSTITUTIONAL_SECTIONS_EN = [
  {
    id: "institucional-sobre",
    label: "1️⃣ About the company",
    title: "🏛 About the company",
    body: [
      "StockNewsBR is a market-intelligence platform using AI for B3, BDR, US equities, futures and crypto traders.",
      "The product turns institutional reading, flow, structure and market context into a fast daily trading workspace.",
    ],
  },
  {
    id: "institucional-produto",
    label: "2️⃣ Product description",
    title: "📦 Product description",
    body: [
      "The main product starts with the Google Play app and unlocks an integrated experience across app, website and Telegram according to the user's plan.",
      "Current surfaces include AI chart, heat map, radar, breakout probability, institutional flow, smart money, accumulation, liquidity sweep, liquidity map, market regime, master score, community and educational help.",
    ],
  },
  {
    id: "institucional-educacao",
    label: "3️⃣ Financial education",
    title: "🎓 Financial education",
    body: [
      "The Help tab explains each AI module in plain English, with simple examples for daily trading use.",
      "The educational goal is guidance, not promised results. Every decision still requires discipline and risk management.",
    ],
  },
  {
    id: "institucional-aviso-legal",
    label: "4️⃣ Legal notice",
    title: "⚠️ Legal notice",
    body: [
      "StockNewsBR tools are analytical and educational support. They are not individualized recommendations to buy, sell, hold or short any asset.",
      "Financial markets involve risk. Users make their own decisions and must manage risk on every trade.",
    ],
  },
  {
    id: "institucional-termos",
    label: "5️⃣ Terms of use",
    title: "📄 Terms of use",
    body: [
      "Product access depends on the contracted plan and compliance with community rules, including responsible use of social feed, polls and AI tools.",
      "Premium accounts use email OTP and stricter session policy to reduce account sharing.",
    ],
  },
  {
    id: "institucional-privacidade",
    label: "6️⃣ Privacy policy",
    title: "🔐 Privacy policy",
    body: [
      "Basic account, authentication, profile and preference data are used to operate app, website, Telegram and community access.",
      "When a trader posts in the feed, the configured display name, image and email identify the post inside that ticker room.",
    ],
  },
  {
    id: "institucional-cookies",
    label: "7️⃣ Cookie policy",
    title: "🍪 Cookie policy",
    body: [
      "The web version uses cookies and local storage to keep session, layout preferences, selected ticker and workspace continuity.",
      "These resources preserve authentication, workspace state and context between visits.",
    ],
  },
  {
    id: "institucional-contato",
    label: "8️⃣ Contact / company",
    title: "📬 Contact / company",
    body: [
      "Main institutional channel: https://www.stocknewsbr.com",
      "Official company communications should be published through StockNewsBR institutional channels.",
    ],
  },
  {
    id: "institucional-redes",
    label: "9️⃣ Social channels",
    title: "🌐 Social channels",
    body: [
      "Official social channels and Telegram distribute alerts, product news and institutional communication.",
      "Always confirm that a channel is linked to the company's official addresses before trusting any message.",
    ],
  },
  {
    id: "institucional-ajuda-trader",
    label: "🔟 Trader Educational Help",
    title: "🎓 Trader Educational Help",
    body: [
      "This section gathers the quick manual, explanations for each AI and the right way to read signals across app, web and Trader Desk.",
      "When this item is clicked, the platform opens Help and takes the trader to the official StockNewsBR educational content.",
    ],
  },
];

const COMPANY_HINTS: Record<string, string> = {
  PETR4: "Petrobras PN",
  PETR3: "Petrobras ON",
  VALE3: "Vale ON",
  ITUB4: "Itau Unibanco PN",
  BBDC4: "Bradesco PN",
  BBAS3: "Banco do Brasil",
  SANB11: "Santander Units",
  BPAC11: "BTG Pactual Units",
  SUZB3: "Suzano",
  KLBN11: "Klabin Units",
  ELET3: "Eletrobras ON",
  ELET6: "Eletrobras PNB",
  CPFE3: "CPFL Energia",
  EQTL3: "Equatorial",
  ENBR3: "EDP Brasil",
  MGLU3: "Magazine Luiza",
  LREN3: "Lojas Renner",
  AMER3: "Americanas",
  VIIA3: "Via",
  ASAI3: "Assai",
  WEGE3: "WEG",
  GGBR4: "Gerdau PN",
  CSNA3: "CSN",
  USIM5: "Usiminas PNA",
  TOTS3: "Totvs",
  POSI3: "Positivo",
  RAIL3: "Rumo",
  CCRO3: "CCR",
  NTCO3: "Natura",
  BRFS3: "BRF",
  JBSS3: "JBS",
  AAPL34: "Apple BDR",
  MSFT34: "Microsoft BDR",
  GOGL34: "Alphabet BDR",
  AMZN34: "Amazon BDR",
  NVDC34: "NVIDIA BDR",
  TSLA34: "Tesla BDR",
  META34: "Meta BDR",
  NFLX34: "Netflix BDR",
  INTC34: "Intel BDR",
  AMD34: "AMD BDR",
  QCOM34: "Qualcomm BDR",
  IVVB11: "ETF IVVB11",
  AAPL: "Apple Inc",
  MSFT: "Microsoft",
  GOOGL: "Alphabet",
  AMZN: "Amazon",
  F: "Ford Motor",
  META: "Meta",
  NVDA: "NVIDIA",
  AMD: "Advanced Micro Devices",
  TSLA: "Tesla",
  INTC: "Intel",
  AVGO: "Broadcom",
  TSM: "TSMC",
  JPM: "JPMorgan",
  BAC: "Bank of America",
  GS: "Goldman Sachs",
  XOM: "Exxon Mobil",
  CVX: "Chevron",
  COST: "Costco",
  WMT: "Walmart",
  DIS: "Disney",
  CRM: "Salesforce",
  SNOW: "Snowflake",
  PLTR: "Palantir",
  BTCUSD: "Bitcoin",
  ETHUSD: "Ethereum",
  BNBUSD: "BNB",
  SOLUSD: "Solana",
  XRPUSD: "XRP",
  ADAUSD: "Cardano",
  DOGEUSD: "Dogecoin",
  MATICUSD: "Polygon",
};

const TOOL_COPY: Record<string, { title: string; description: string; explanation: string }> = {
  "heat-map": {
    title: "🗺 IA Mapa de Calor",
    description: "Mostra quais ativos estão mais fortes ou mais fracos no mercado.",
    explanation: "🟢 Verde = força compradora. 🔴 Vermelho = pressão vendedora. Exemplo: se PETR4 aparece bem verde, o ativo está ganhando força agora.",
  },
  radar: {
    title: "⚡ IA Radar",
    description: "Detecta ativos que começaram a se movimentar rapidamente no mercado.",
    explanation: "Funciona como um radar para encontrar oportunidades antes da maioria dos traders perceber.",
  },
  "breakout-probability": {
    title: "🎯 IA Probabilidade de Breakout",
    description: "Identifica quando um ativo está próximo de romper uma resistência importante.",
    explanation: "Breakout significa que o preço pode iniciar uma tendência forte. Exemplo: se romper uma faixa lateral com volume, a probabilidade sobe.",
  },
  "volatility-squeeze": {
    title: "🟣 IA Compressão de Volatilidade",
    description: "Detecta momentos em que a volatilidade do mercado está muito comprimida.",
    explanation: "Depois de muita compressão costuma vir expansão forte. A IA busca exatamente esse ponto.",
  },
  "institutional-flow": {
    title: "🏦 IA Fluxo Institucional",
    description: "Identifica quando investidores institucionais estão entrando no mercado.",
    explanation: "Instituições movem muito volume e muitas vezes iniciam movimentos importantes antes do varejo perceber.",
  },
  "smart-money": {
    title: "💼 IA Dinheiro Inteligente",
    description: "Busca sinais de movimentação de grandes players antes de movimentos importantes no mercado.",
    explanation: "É a leitura do dinheiro inteligente: absorção, deslocamento e volume anormal.",
  },
  accumulation: {
    title: "📦 IA Acumulação",
    description: "Detecta quando um ativo está sendo acumulado lentamente por grandes investidores.",
    explanation: "A acumulação costuma acontecer com preço estável e volume subindo aos poucos, sem chamar tanta atenção do mercado.",
  },
  "liquidity-sweep": {
    title: "🧲 IA Varredura de Liquidez",
    description: "Detecta quando o mercado busca liquidez antes de mudar de direção.",
    explanation: "É quando o preço varre stops, busca liquidez e depois reage na direção contrária.",
  },
  "liquidity-map": {
    title: "🧭 IA Liquidity Map",
    description: "Mostra onde existe maior concentração de liquidez no mercado.",
    explanation: "Esses pontos costumam atrair o preço e ajudam o trader a entender onde a reação pode acontecer.",
  },
  "market-regime": {
    title: "📊 IA Regime de Mercado",
    description: "Mostra qual é o tipo de mercado atual.",
    explanation: "A IA identifica se o mercado está em tendência de alta, tendência de baixa ou lateral, para o trader usar a ferramenta certa no cenário certo.",
  },
  "master-score": {
    title: "⭐ IA Score Mestre",
    description: "É a pontuação geral do sistema.",
    explanation: "Combina diversas análises da IA para classificar oportunidades. Score alto = oportunidade mais forte.",
  },
};

const TOOL_COPY_EN: Record<string, { title: string; description: string; explanation: string }> = {
  "heat-map": {
    title: "🗺 AI Heat Map",
    description: "Shows which assets are stronger or weaker in the market.",
    explanation: "🟢 Green = buying strength. 🔴 Red = selling pressure. If PETR4 appears strongly green, the asset is gaining strength now.",
  },
  radar: {
    title: "⚡ AI Radar",
    description: "Detects assets that started moving quickly.",
    explanation: "Works as a radar for opportunities before most traders notice the move.",
  },
  "breakout-probability": {
    title: "🎯 AI Breakout Probability",
    description: "Identifies when an asset is close to breaking important resistance.",
    explanation: "Breakout means price may start a stronger trend. If range breaks with volume, probability improves.",
  },
  "volatility-squeeze": {
    title: "🟣 AI Volatility Squeeze",
    description: "Detects moments when market volatility is highly compressed.",
    explanation: "After strong compression, expansion often follows. This AI looks for that point.",
  },
  "institutional-flow": {
    title: "🏦 AI Institutional Flow",
    description: "Identifies when institutional investors may be entering the market.",
    explanation: "Institutions move large volume and often start important moves before retail notices.",
  },
  "smart-money": {
    title: "💼 AI Smart Money",
    description: "Looks for large-player movement before important market moves.",
    explanation: "It reads smart money through absorption, displacement and abnormal volume.",
  },
  accumulation: {
    title: "📦 AI Accumulation",
    description: "Detects when an asset may be slowly accumulated by large investors.",
    explanation: "Accumulation often appears as stable price with gradually rising volume.",
  },
  "liquidity-sweep": {
    title: "🧲 AI Liquidity Sweep",
    description: "Detects when the market seeks liquidity before changing direction.",
    explanation: "Price sweeps stops, takes liquidity and then reacts in the opposite direction.",
  },
  "liquidity-map": {
    title: "🧭 AI Liquidity Map",
    description: "Shows where liquidity is more concentrated in the market.",
    explanation: "These zones often attract price and help the trader understand where reaction can happen.",
  },
  "market-regime": {
    title: "📊 AI Market Regime",
    description: "Shows the current market environment.",
    explanation: "The AI identifies uptrend, downtrend or range so the trader uses the right tool for the right scenario.",
  },
  "master-score": {
    title: "⭐ AI Master Score",
    description: "The system's consolidated score.",
    explanation: "Combines several AI reads to classify opportunities. Higher score means stronger opportunity.",
  },
};

const HELP_GUIDES = [
  {
    title: "Ajuda Educacional para o Trader",
    description:
      "Nossa plataforma usa modelos quantitativos avançados, IA e ferramentas de mesa institucional para transformar leitura complexa em uma tela simples para o trader.",
  },
  ...Object.values(TOOL_COPY).map((item) => ({
    title: item.title,
    description: `${item.description} ${item.explanation}`,
  })),
];

const TIMEFRAME_OPTIONS = ["1D", "1W", "1M", "3M", "6M", "YTD", "1Y", "All"];
const COMPOSER_EMOJIS = ["🔥", "📈", "🚀", "💰", "⚠️", "👀", "🐂", "🐻"];
const QUICK_GIF_TERMS = ["bull market", "bear market", "stocks rally", "market crash"];

function cx(...values: Array<string | false | null | undefined>) {
  return values.filter(Boolean).join(" ");
}

function titleFromKey(key: string) {
  return key.replace(/_/g, " ").replace(/\b\w/g, (match) => match.toUpperCase());
}

function normalizeSymbol(raw: string) {
  const value = String(raw || "").trim().toUpperCase().replace(/\.SA$/, "");
  if (value.endsWith("-USD")) return value.replace(/-USD$/, "USD");
  if (value.endsWith("USDT")) return `${value.slice(0, -4)}USD`;
  return value;
}

function symbolAliases(raw?: string | null) {
  const source = String(raw || "").trim().toUpperCase();
  const normalized = normalizeSymbol(source);
  const aliases = new Set<string>();
  if (source) aliases.add(source);
  if (normalized) aliases.add(normalized);
  if (normalized.endsWith("USD")) {
    aliases.add(normalized.replace(/USD$/, "-USD"));
    aliases.add(normalized.replace(/USD$/, "USDT"));
  }
  if (/^[A-Z]{4}(3|4|5|6|11)$/.test(normalized) || /^[A-Z]{4,5}34$/.test(normalized)) {
    aliases.add(`${normalized}.SA`);
  }
  return Array.from(aliases);
}

function sameSymbol(left?: string | null, right?: string | null) {
  const normalizedLeft = normalizeSymbol(String(left || ""));
  const normalizedRight = normalizeSymbol(String(right || ""));
  return Boolean(normalizedLeft && normalizedRight && normalizedLeft === normalizedRight);
}

function sameChartRequest(chart: any, ticker: string, interval: string) {
  if (!sameSymbol(chart?.ticker || chart?.summary?.ticker, ticker)) return false;
  return String(chart?.interval || chart?.summary?.interval || "1D").toUpperCase() === String(interval || "1D").toUpperCase();
}

function topTabText(tabId: string, fallback: string, locale: AppLocale = "pt-BR") {
  const copy = locale === "en-US" ? TOP_TAB_TEXT_EN : TOP_TAB_TEXT;
  return copy[tabId] || fallback;
}

function guessCategory(symbol: string) {
  if (symbol.endsWith("USD")) return "Crypto";
  if (symbol.endsWith("34") || symbol === "IVVB11") return "BDR";
  if (/\d/.test(symbol)) return "B3";
  return "USA";
}

function symbolName(symbol: string, locale: AppLocale = "pt-BR") {
  return b3FutureLabel(symbol, locale) || DERIVATIVE_HINTS[symbol] || COMPANY_HINTS[symbol] || symbol;
}

function displayWatchlistLabel(item: { symbol: string; label?: string | null }, locale: AppLocale = "pt-BR") {
  if (locale !== "en-US") return item.label || symbolName(item.symbol, locale);
  return b3FutureLabel(item.symbol, locale) || DERIVATIVE_HINTS[item.symbol] || COMPANY_HINTS[item.symbol] || item.label || item.symbol;
}

function resolveTypedSymbol(raw: string) {
  const trimmed = String(raw || "").trim();
  const normalized = normalizeSymbol(trimmed);
  if (!trimmed) return "";

  const lower = trimmed.toLowerCase();
  const companyMatch = Object.entries(COMPANY_HINTS).find(([symbol, name]) => {
    const nameLower = name.toLowerCase();
    return lower === nameLower || lower === symbol.toLowerCase() || nameLower.includes(lower);
  });

  return companyMatch?.[0] || normalized;
}

function initialsFromName(value?: string | null) {
  const source = String(value || "").trim();
  if (!source) return "SN";

  const parts = source.split(/\s+/).filter(Boolean);
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return `${parts[0][0] || ""}${parts[parts.length - 1][0] || ""}`.toUpperCase();
}

function formatRelativeTime(timestamp?: number | null, locale: AppLocale = "pt-BR") {
  const nowText = locale === "en-US" ? "now" : "agora";
  if (!timestamp) return nowText;

  const diffSeconds = Math.max(0, Math.floor(Date.now() / 1000) - Number(timestamp));
  if (diffSeconds < 60) return nowText;
  if (diffSeconds < 3600) return `${Math.floor(diffSeconds / 60)} min`;
  if (diffSeconds < 86400) return `${Math.floor(diffSeconds / 3600)} h`;
  return `${Math.floor(diffSeconds / 86400)} d`;
}

function getSaoPauloParts(date = new Date()) {
  const formatter = new Intl.DateTimeFormat("en-GB", {
    timeZone: "America/Sao_Paulo",
    weekday: "short",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
  const parts = formatter.formatToParts(date);
  const pick = (type: string) => parts.find((part) => part.type === type)?.value || "";
  return {
    weekday: pick("weekday").toLowerCase(),
    hour: Number(pick("hour") || 0),
    minute: Number(pick("minute") || 0),
  };
}

function isB3Symbol(symbol: string) {
  return guessCategory(symbol) === "B3";
}

function isB3MarketOpen(date = new Date()) {
  const { weekday, hour, minute } = getSaoPauloParts(date);
  const openDays = ["mon", "tue", "wed", "thu", "fri"];
  if (!openDays.includes(weekday)) return false;
  const minutes = hour * 60 + minute;
  return minutes >= 10 * 60 && minutes <= 17 * 60;
}

function normalizeAlertTimestamp(value?: unknown) {
  if (value == null || value === "") return null;
  const numeric = typeof value === "number" ? value : Number(value);
  const date = Number.isFinite(numeric)
    ? new Date(numeric < 10_000_000_000 ? numeric * 1000 : numeric)
    : new Date(String(value));

  if (Number.isNaN(date.getTime())) return null;
  return date.toISOString();
}

function normalizeAlertEpoch(value?: unknown) {
  const iso = normalizeAlertTimestamp(value);
  return iso ? Date.parse(iso) : null;
}

function resolveAiAlertTimestamp(row: AiToolRow, fallbackIso?: unknown) {
  return (
    normalizeAlertTimestamp(row.detected_at) ||
    normalizeAlertTimestamp(row.updated_at) ||
    normalizeAlertTimestamp(row.last_seen_at) ||
    normalizeAlertTimestamp((row as any).timestamp) ||
    normalizeAlertTimestamp((row as any).created_at) ||
    normalizeAlertTimestamp(fallbackIso)
  );
}

function formatAlertTime(symbol: string, rawTimestamp?: number | null) {
  const date = rawTimestamp ? new Date(rawTimestamp) : null;
  if (!date || Number.isNaN(date.getTime())) return "sem horário";
  const { hour, minute } = getSaoPauloParts(date);
  const timeText = `${String(hour).padStart(2, "0")}:${String(minute).padStart(2, "0")}`;
  return isB3Symbol(symbol) && !isB3MarketOpen(date) ? `${timeText} fora pregão` : timeText;
}

function aiAlertSignalKey(row: AiToolRow) {
  return [
    row.tool || "tool",
    normalizeSymbol(row.ticker),
    humanizeMachineLabel(row.state || row.signal || "alerta").toLowerCase(),
  ].join("|");
}

function aiAlertComparableSignature(row: AiToolRow) {
  return [
    aiAlertSignalKey(row),
    row.score ?? "",
    row.signal ?? "",
    row.state ?? "",
    row.price ?? "",
    row.change_pct ?? "",
    row.volume ?? "",
    row.rsi ?? "",
    row.rel_volume ?? (row as any).rvol ?? "",
    row.adx ?? "",
    row.atr_pct ?? "",
    row.ai_comment ?? "",
    row.trigger ?? "",
    row.invalidation ?? "",
  ].join("|");
}

function withAlertTimestamp(row: AiToolRow, fallbackIso: string): AiToolRow {
  const detectedAt = resolveAiAlertTimestamp(row, fallbackIso) || fallbackIso;
  const lastSeenAt =
    normalizeAlertTimestamp(row.last_seen_at) ||
    normalizeAlertTimestamp(row.updated_at) ||
    detectedAt;

  return {
    ...row,
    updated_at: detectedAt,
    detected_at: detectedAt,
    last_seen_at: lastSeenAt,
  };
}

function getAlertResetKey(date = new Date()) {
  const saoPaulo = new Date(date.toLocaleString("en-US", { timeZone: "America/Sao_Paulo" }));
  if (saoPaulo.getHours() < 7) saoPaulo.setDate(saoPaulo.getDate() - 1);
  return saoPaulo.toISOString().slice(0, 10);
}

function symbolFamilyKey(symbol?: string | null) {
  const normalized = normalizeSymbol(String(symbol || ""));
  if (!normalized) return "unknown";
  const category = guessCategory(normalized);
  if (BDR_UNDERLYING[normalized]) return `US:${BDR_UNDERLYING[normalized]}`;
  if (category === "USA") return `US:${normalized}`;
  return `${category}:${normalized}`;
}

function categoryQuotaForTab(tabId: string): Record<string, number> {
  switch (tabId) {
    case "radar":
      return { B3: 9, BDR: 4, USA: 5, Crypto: 2 };
    case "breakout-probability":
      return { B3: 13, BDR: 4, USA: 3, Crypto: 1 };
    case "volatility-squeeze":
      return { B3: 15, BDR: 3, USA: 2, Crypto: 1 };
    case "institutional-flow":
      return { B3: 15, BDR: 3, USA: 2, Crypto: 0 };
    case "smart-money":
      return { B3: 10, BDR: 5, USA: 5, Crypto: 1 };
    case "accumulation":
      return { B3: 16, BDR: 2, USA: 2, Crypto: 0 };
    case "liquidity-sweep":
      return { B3: 11, BDR: 4, USA: 4, Crypto: 1 };
    case "liquidity-map":
      return { B3: 12, BDR: 4, USA: 4, Crypto: 0 };
    case "market-regime":
      return { B3: 13, BDR: 3, USA: 4, Crypto: 1 };
    case "master-score":
      return { B3: 11, BDR: 4, USA: 4, Crypto: 1 };
    default:
      return { B3: 12, BDR: 4, USA: 4, Crypto: 2 };
  }
}

function selectDiverseByLens<T>(
  rows: T[],
  tabId: string,
  limit: number,
  getSymbol: (row: T) => string | null | undefined,
) {
  const quotas = categoryQuotaForTab(tabId);
  const selected: T[] = [];
  const selectedRows = new Set<T>();
  const familyCount = new Map<string, number>();
  const categoryCount = new Map<string, number>();

  const tryPush = (row: T, enforceFamily: boolean, enforceCategory: boolean) => {
    if (selected.length >= limit || selectedRows.has(row)) return;
    const symbol = normalizeSymbol(String(getSymbol(row) || ""));
    if (!symbol) return;
    const family = symbolFamilyKey(symbol);
    const category = guessCategory(symbol);
    if (enforceFamily && familyCount.has(family)) return;
    if (enforceCategory && (categoryCount.get(category) || 0) >= (quotas[category] ?? limit)) return;

    selected.push(row);
    selectedRows.add(row);
    familyCount.set(family, (familyCount.get(family) || 0) + 1);
    categoryCount.set(category, (categoryCount.get(category) || 0) + 1);
  };

  for (const row of rows) tryPush(row, true, true);
  for (const row of rows) tryPush(row, true, false);
  return selected.slice(0, limit);
}

function clampNumber(value: number, min: number, max: number) {
  return Math.max(min, Math.min(max, value));
}

function calibrateSentimentMeterValue(value: number | null, label: string) {
  if (value == null) return null;
  const normalized = clampNumber(value, 0, 100);
  if (label === "Urso") return clampNumber(normalized <= 5 ? 32 : normalized, 18, 45);
  if (label === "Touro") return clampNumber(normalized < 55 ? 64 : normalized, 55, 92);
  if (label === "Neutro") return clampNumber(normalized, 46, 54);
  return normalized;
}

function calibrateVolumeMeterValue(value: number | null, label: string) {
  if (value == null) return null;
  const normalized = clampNumber(value, 0, 100);
  if (label === "Baixo") return clampNumber(normalized <= 5 ? 22 : normalized, 12, 34);
  if (label === "Normal") return clampNumber(normalized, 35, 64);
  if (label === "Alto") return clampNumber(normalized < 65 ? 72 : normalized, 65, 100);
  return normalized;
}

function buildCategoryUniverse(symbols: string[], category: string) {
  return symbols.map((rawSymbol) => {
    const symbol = normalizeSymbol(rawSymbol);
    return {
      symbol,
      label: symbolName(symbol),
      category,
    } satisfies WatchlistItem;
  });
}

const PRELOADED_UNIVERSE: WatchlistItem[] = [
  ...buildCategoryUniverse(WATCHLIST_B3, "B3"),
  ...buildCategoryUniverse(WATCHLIST_BDR, "BDR"),
  ...buildCategoryUniverse(WATCHLIST_CRYPTO, "Crypto"),
  ...buildCategoryUniverse(WATCHLIST_US, "USA"),
];

function formatPrice(value?: number | null) {
  if (value == null || Number.isNaN(Number(value))) return "n/a";
  return Number(value).toLocaleString("pt-BR", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

function isBrazilianMarketSymbol(symbol?: string | null) {
  const normalized = normalizeSymbol(String(symbol || ""));
  return /^[A-Z]{4}\d{1,2}$/.test(normalized) || normalized.startsWith("WIN") || normalized.startsWith("WDO");
}

function parsePriceNumber(value: unknown) {
  if (value == null) return null;
  if (typeof value === "number") return Number.isFinite(value) ? value : null;
  const text = String(value).trim();
  if (!text) return null;
  const normalized = text.includes(",") ? text.replace(/\./g, "").replace(",", ".") : text;
  const parsed = Number(normalized);
  return Number.isFinite(parsed) ? parsed : null;
}

function formatLocalePrice(value?: unknown, locale: AppLocale = "pt-BR") {
  const numeric = parsePriceNumber(value);
  if (numeric == null) return "n/a";
  return numeric.toLocaleString(locale === "en-US" ? "en-US" : "pt-BR", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

function formatAssetMoney(value: unknown, symbol: string, locale: AppLocale) {
  const prefix = isBrazilianMarketSymbol(symbol) ? "R$" : locale === "en-US" ? "$" : "US$";
  return `${prefix} ${formatLocalePrice(value, locale)}`;
}

function formatSignedPercent(value?: number | null) {
  if (value == null || Number.isNaN(Number(value))) return "n/a";
  const numeric = Number(value);
  const decimals = Math.abs(numeric) > 0 && Math.abs(numeric) < 0.01 ? 4 : 2;
  return `${numeric > 0 ? "+" : ""}${numeric.toFixed(decimals)}%`;
}

function formatCompact(value?: number | null) {
  if (value == null || Number.isNaN(Number(value))) return "n/a";
  return Intl.NumberFormat("pt-BR", {
    notation: "compact",
    maximumFractionDigits: 1,
  }).format(Number(value));
}

function formatWatchlistPrimaryValue(
  item: { price?: number | null; changePct?: number | null; score?: number | null },
  locale: AppLocale = "pt-BR",
) {
  if (item.price != null && Number.isFinite(Number(item.price))) {
    return formatLocalePrice(item.price, locale);
  }
  if (item.changePct != null && Number.isFinite(Number(item.changePct))) {
    return formatSignedPercent(item.changePct);
  }
  if (item.score != null && Number.isFinite(Number(item.score))) {
    return `Score ${Number(item.score).toFixed(1)}`;
  }
  return locale === "en-US" ? "no price" : "sem preço";
}

function formatMarketMovementText(item: {
  price?: number | null;
  changePct?: number | null;
  score?: number | null;
  trend?: string | null;
}, locale: AppLocale = "pt-BR") {
  if (item.changePct != null && Number.isFinite(Number(item.changePct))) {
    return formatSignedPercent(item.changePct);
  }
  if (item.price != null && Number.isFinite(Number(item.price))) {
    return locale === "en-US" ? "active price" : "preço ativo";
  }
  if (item.score != null && Number.isFinite(Number(item.score))) {
    return `Score ${Number(item.score).toFixed(1)}`;
  }
  const trend = String(item.trend || "").trim();
  return trend ? localizeUiText(trend, locale) : locale === "en-US" ? "no price" : "sem preço";
}

function deriveChangePercent(change?: number | null, price?: number | null) {
  const numericChange = Number(change);
  const numericPrice = Number(price);
  if (!Number.isFinite(numericChange) || !Number.isFinite(numericPrice) || numericPrice <= 0) return null;

  const priorClose = numericPrice - numericChange;
  if (!Number.isFinite(priorClose) || priorClose <= 0) return null;

  return Number(((numericChange / priorClose) * 100).toFixed(2));
}

function quoteHasMarketValue(quote?: QuotePayload | null) {
  if (!quote) return false;
  const source = String((quote as any).source || "").toLowerCase();
  const status = String((quote as any).quote_status || "").toLowerCase();
  if (source === "empty" || status === "empty" || status === "partial") return false;
  const price = Number(quote.price);
  return Number.isFinite(price) && price > 0;
}

function mergeQuoteState(current: Record<string, QuotePayload>, incoming: Record<string, QuotePayload>) {
  const next = { ...current };

  for (const [symbol, quote] of Object.entries(incoming)) {
    if (!symbol) continue;
    const normalized = normalizeSymbol(symbol);
    const normalizedQuote = { ...quote, symbol: normalized || quote.symbol || symbol };
    for (const alias of symbolAliases(symbol)) {
      const normalizedAlias = normalizeSymbol(alias);
      const existing = next[alias] || next[normalizedAlias];
      if (quoteHasMarketValue(normalizedQuote) || !quoteHasMarketValue(existing)) {
        next[alias] = normalizedQuote;
        if (normalizedAlias) next[normalizedAlias] = normalizedQuote;
      }
    }
  }

  return next;
}

function usableScore(...scores: Array<number | null | undefined>) {
  for (const score of scores) {
    const numeric = Number(score);
    if (Number.isFinite(numeric) && numeric > 0) return numeric;
  }
  return null;
}

function derivePublicScore(input: {
  changePct?: number | null;
  rsi?: number | null;
  trend?: string | null;
  volume?: number | null;
}) {
  const changePct = Number(input.changePct);
  const rsi = Number(input.rsi);
  const trend = String(input.trend || "").toLowerCase();
  let score = 5;

  if (Number.isFinite(changePct)) {
    score += clampNumber(changePct * 3, -2, 2);
  }
  if (Number.isFinite(rsi)) {
    if (rsi >= 55 && rsi <= 70) score += 1;
    if (rsi > 75 || rsi < 30) score -= 0.75;
  }
  if (trend.includes("alta") || trend.includes("bull") || trend.includes("buy")) score += 1;
  if (trend.includes("baixa") || trend.includes("bear") || trend.includes("sell")) score -= 1;
  if (input.volume != null && Number(input.volume) > 0) score += 0.25;

  return clampNumber(Number(score.toFixed(1)), 1, 10);
}

function derivePublicRsi(changePct?: number | null, trend?: string | null) {
  const change = Number(changePct);
  const trendText = String(trend || "").toLowerCase();
  let value = 50;

  if (Number.isFinite(change)) value += clampNumber(change * 7, -18, 18);
  if (trendText.includes("alta") || trendText.includes("bull") || trendText.includes("buy")) value += 4;
  if (trendText.includes("baixa") || trendText.includes("bear") || trendText.includes("sell")) value -= 4;

  return clampNumber(Number(value.toFixed(1)), 20, 80);
}

function deriveRelativeVolume(volume?: number | null) {
  const numeric = Number(volume);
  if (!Number.isFinite(numeric) || numeric <= 0) return 1;
  return clampNumber(Number((numeric / 1_000_000).toFixed(2)), 0.1, 9.9);
}

function deriveAdx(changePct?: number | null, rsi?: number | null, trend?: string | null) {
  const change = Math.abs(Number(changePct || 0));
  const rsiValue = Number(rsi);
  const trendText = String(trend || "").toLowerCase();
  let value = 18;

  if (Number.isFinite(change)) value += clampNumber(change * 280, 0, 24);
  if (Number.isFinite(rsiValue)) value += clampNumber(Math.abs(rsiValue - 50) * 0.35, 0, 10);
  if (trendText.includes("alta") || trendText.includes("baixa") || trendText.includes("bull") || trendText.includes("bear")) value += 6;
  if (trendText.includes("lateral") || trendText.includes("monitor")) value -= 4;

  return clampNumber(Number(value.toFixed(1)), 8, 60);
}

function deriveAtrPct(changePct?: number | null, rsi?: number | null, volume?: number | null) {
  const change = Math.abs(Number(changePct || 0));
  const rsiValue = Number(rsi);
  const volumeValue = Number(volume || 0);
  let value = 0.8;

  if (Number.isFinite(change)) value += clampNumber(change * 4.2, 0, 1.8);
  if (Number.isFinite(rsiValue)) value += clampNumber(Math.abs(rsiValue - 50) / 120, 0, 0.7);
  if (Number.isFinite(volumeValue) && volumeValue > 0) value += clampNumber(Math.log10(volumeValue + 1) / 30, 0, 0.8);

  return clampNumber(Number(value.toFixed(2)), 0.2, 12);
}

function firstFiniteNumber(...values: Array<unknown>) {
  for (const value of values) {
    const numeric = Number(value);
    if (Number.isFinite(numeric)) return numeric;
  }
  return null;
}

function firstNonZeroFiniteNumber(...values: Array<unknown>) {
  for (const value of values) {
    const numeric = Number(value);
    if (Number.isFinite(numeric) && Math.abs(numeric) > 0.000001) return numeric;
  }
  return null;
}

function chartLatestAlertEpoch(chart?: ChartPayload | null) {
  const rows = chart?.ohlc?.length ? chart.ohlc : chart?.series || [];
  const last = rows[rows.length - 1] as any;
  return normalizeAlertEpoch(last?.time || last?.timestamp || null);
}

function deriveChartMovement(chart?: ChartPayload | null) {
  const rows = chart?.ohlc?.length ? chart.ohlc : chart?.series || [];
  if (rows.length < 2) return null;

  const firstClose = firstFiniteNumber((rows[0] as any).close, (rows[0] as any).price);
  const lastClose = firstFiniteNumber((rows[rows.length - 1] as any).close, (rows[rows.length - 1] as any).price);
  if (firstClose == null || firstClose <= 0 || lastClose == null) return null;

  const change = lastClose - firstClose;
  const changePct = (change / firstClose) * 100;
  if (!Number.isFinite(change) || !Number.isFinite(changePct)) return null;
  return {
    change,
    changePct,
  };
}

function formatLiquidityVolume(volume?: number | null, rvol?: number | null) {
  const numericVolume = firstFiniteNumber(volume);
  if (numericVolume != null && numericVolume > 0) return formatCompact(numericVolume);
  const numericRvol = firstFiniteNumber(rvol);
  if (numericRvol != null) return `RVOL ${numericRvol.toFixed(2)}`;
  return "sem leitura";
}

function looksPortuguese(text?: string | null) {
  const value = String(text || "").trim();
  if (!value) return false;
  return /[ãõçáéíóúàêô]|preço|mercado|ação|acao|notícia|noticia|volume|alta|baixa|trimestre|resultado|ativo|risco|fluxo/i.test(value);
}

function normalizeUiText(value?: string | null) {
  return String(value || "")
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/\s+/g, " ")
    .trim()
    .toLowerCase();
}

function sameUiText(left?: string | null, right?: string | null) {
  const a = normalizeUiText(left);
  const b = normalizeUiText(right);
  return Boolean(a && b && (a === b || a.includes(b) || b.includes(a)));
}

function translatePtToEn(value?: string | null, symbol?: string | null) {
  const original = String(value || "").trim();
  if (!original) return "";
  const ticker = normalizeSymbol(String(symbol || "")) || "this ticker";
  const normalized = normalizeUiText(original);

  if (normalized.includes("para trader") && normalized.includes("reacao de preco") && normalized.includes("volume")) {
    return `Trader note: monitor price and volume reaction in ${ticker} because the read may turn into an intraday trend.`;
  }
  if (normalized.includes("para trader") && normalized.includes("priorize continuacao")) {
    return `Trader note: prioritize continuation only if ${ticker} sustains flow and does not give back the breakout.`;
  }
  if (normalized.includes("para trader") && normalized.includes("use a manchete")) {
    return `Trader note: use the headline as complementary context and wait for market confirmation in ${ticker}.`;
  }
  if (normalized.includes("para trader") && normalized.includes("monitore")) {
    return `Trader note: monitor ${ticker} price, volume and flow before acting.`;
  }
  if (normalized === "serie ohlc do provider") return "provider OHLC series";
  if (normalized === "preco real confirmado") return "confirmed real price";
  if (normalized === "marcador operacional confirmado") return "confirmed operational marker";
  if (normalized.includes("sem enquete institucional carregada")) {
    return `${ticker}: no institutional poll is loaded; which confirmation is still missing to validate this week's thesis?`;
  }
  if (normalized.includes("preco romper nivel com volume real")) return "Price breaks a level with real volume";
  if (normalized.includes("fluxo ou noticia confirmar contexto")) return "Flow or news confirms the context";
  if (normalized.includes("continuidade com buying flow")) return "Continuation with buying flow";
  if (normalized.includes("exaustao e retorno a media")) return "Exhaustion and mean reversion";
  if (normalized.includes("tendencia semanal ainda tem perna")) {
    return `${ticker}: does the weekly trend still have room or is it already showing exhaustion?`;
  }
  if (normalized.includes("resultado") && normalized.includes("regulacao")) {
    return `Earnings, regulation and sector context affect ${ticker}; confirm whether the impact is ticker-specific or only sector-wide.`;
  }
  if (normalized.includes("noticia macro tende a afetar")) {
    return `Macro news may affect the sector first and only then ${ticker}; watch price confirmation before acting.`;
  }
  if (normalized.includes("pode mover") && normalized.includes("expectativa")) {
    return `${ticker} may move if profit expectations or sector pricing change.`;
  }
  if (normalized.includes("nenhum perfil bloqueado")) return "No blocked profile.";
  if (normalized.includes("quando voce bloquear alguem")) return "When you block someone in the feed, that profile appears here.";
  if (normalized.includes("nenhum perfil silenciado")) return "No muted profile.";
  if (normalized.includes("quando voce silenciar alguem")) return "When you mute someone in the feed, that profile appears here.";
  if (normalized === "bloqueado") return "Blocked";
  if (normalized === "silenciado") return "Muted";
  if (normalized.includes("manter short apenas se perder suporte")) {
    return "Keep the short only if support is lost again with selling volume and without institutional defense.";
  }
  if (normalized.includes("close posicao long") || (normalized.includes("posicao long") && normalized.includes("conflito de regime"))) {
    return `Close the long in ${ticker} if there is trend loss, weak buying flow or a regime/liquidity conflict against the buy.`;
  }
  if (normalized.includes("cancelar") && normalized.includes("vwap")) {
    return "Cancel the sell/exit if price recovers VWAP, buying volume returns and the regime stays in an uptrend.";
  }
  if (normalized.includes("perde a leitura se score cair")) {
    return "The read fails if Score drops, relative strength turns neutral or the opposite side dominates the tape.";
  }
  if (normalized.includes("mapa so autoriza") || normalized.includes("mapa só autoriza")) {
    return `Heat Map only authorizes action if ${ticker} keeps relative strength, RVOL confirms and price breaks the tactical level.`;
  }
  if (normalized.includes("close sell descoberta") || normalized.includes("vwap") && normalized.includes("short")) {
    return "Close short if VWAP/EMA21 recovers or institutional buying appears.";
  }
  if (normalized.includes("risco baixo") && normalized.includes("filtros principais alinhados")) {
    return "Low risk: main filters are aligned.";
  }
  if (normalized.includes("low risk")) return original;

  return original
    .replace(/Preço/g, "Price")
    .replace(/preço/g, "price")
    .replace(/Variação/g, "Change")
    .replace(/variação/g, "change")
    .replace(/Confiança/g, "Confidence")
    .replace(/confiança/g, "confidence")
    .replace(/Estado/g, "State")
    .replace(/estado/g, "state")
    .replace(/Leitura principal/g, "Main read")
    .replace(/leitura principal/g, "main read")
    .replace(/Invalidação/g, "Invalidation")
    .replace(/Invalidacao/g, "Invalidation")
    .replace(/invalidação/g, "invalidation")
    .replace(/Métricas da lente/g, "Lens metrics")
    .replace(/metricas da lente/g, "lens metrics")
    .replace(/no mapa de força/g, "on the strength map")
    .replace(/no mapa de forca/g, "on the strength map")
    .replace(/Direção tática/g, "Tactical direction")
    .replace(/direção tática/g, "tactical direction")
    .replace(/Direcao tatica/g, "Tactical direction")
    .replace(/direcao tatica/g, "tactical direction")
    .replace(/leitura favorece/g, "read favors")
    .replace(/Leitura favorece/g, "Read favors")
    .replace(/confirmar/g, "confirm")
    .replace(/Confirmar/g, "Confirm")
    .replace(/mantiver/g, "keeps")
    .replace(/romper/g, "break")
    .replace(/surgir/g, "appears")
    .replace(/dominante/g, "dominant")
    .replace(/perder/g, "lose")
    .replace(/Direção operacional/g, "Operational direction")
    .replace(/direção operacional/g, "operational direction")
    .replace(/gatilho/g, "trigger")
    .replace(/Gatilho/g, "Trigger")
    .replace(/contexto/g, "context")
    .replace(/Contexto/g, "Context")
    .replace(/força compradora/g, "buying strength")
    .replace(/Força compradora/g, "Buying strength")
    .replace(/pressão vendedora/g, "selling pressure")
    .replace(/Pressão vendedora/g, "Selling pressure")
    .replace(/comprador/g, "buying")
    .replace(/Comprador/g, "Buying")
    .replace(/compradora/g, "buying")
    .replace(/Compradora/g, "Buying")
    .replace(/vendedor/g, "selling")
    .replace(/Vendedor/g, "Selling")
    .replace(/vendedora/g, "selling")
    .replace(/Vendedora/g, "Selling")
    .replace(/último sinal/g, "latest signal")
    .replace(/ultimo sinal/g, "latest signal")
    .replace(/posição/g, "position")
    .replace(/posicao/g, "position")
    .replace(/quando houver/g, "when there is")
    .replace(/voltar/g, "return")
    .replace(/seguir de/g, "remain")
    .replace(/contra a/g, "against the")
    .replace(/compra discreta/g, "discreet buying")
    .replace(/acumulacao nao confirmada/g, "accumulation not confirmed")
    .replace(/acumulação não confirmada/g, "accumulation not confirmed")
    .replace(/regime de alta/g, "uptrend regime")
    .replace(/regime de baixa\/lateral/g, "downtrend/range regime")
    .replace(/tendencia de alta/g, "uptrend")
    .replace(/tendência de alta/g, "uptrend")
    .replace(/tendencia de baixa/g, "downtrend")
    .replace(/tendência de baixa/g, "downtrend")
    .replace(/alta convicção/g, "high conviction")
    .replace(/convicção moderada/g, "moderate conviction")
    .replace(/observação tática/g, "tactical watch")
    .replace(/baixa convicção/g, "low conviction")
    .replace(/médio/g, "medium")
    .replace(/Médio/g, "Medium")
    .replace(/medio/g, "medium")
    .replace(/Medio/g, "Medium")
    .replace(/baixo/g, "low")
    .replace(/Baixo/g, "Low")
    .replace(/alto/g, "high")
    .replace(/Alto/g, "High")
    .replace(/compra/g, "buy")
    .replace(/Compra/g, "Buy")
    .replace(/venda/g, "sell")
    .replace(/Venda/g, "Sell")
    .replace(/alta/g, "uptrend")
    .replace(/Alta/g, "Uptrend")
    .replace(/baixa/g, "downtrend")
    .replace(/Baixa/g, "Downtrend")
    .replace(/neutro/g, "neutral")
    .replace(/Neutro/g, "Neutral")
    .replace(/lateral/g, "range")
    .replace(/Lateral/g, "Range")
    .replace(/risco/g, "risk")
    .replace(/Risco/g, "Risk")
    .replace(/fluxo/g, "flow")
    .replace(/Fluxo/g, "Flow")
    .replace(/notícia/g, "news")
    .replace(/Notícia/g, "News")
    .replace(/ativo/g, "asset")
    .replace(/Ativo/g, "Asset")
    .replace(/mercado/g, "market")
    .replace(/Mercado/g, "Market")
    .replace(/romper/g, "break")
    .replace(/resistência/g, "resistance")
    .replace(/Resistência/g, "Resistance")
    .replace(/resistencia/g, "resistance")
    .replace(/Resistencia/g, "Resistance")
    .replace(/suporte/g, "support")
    .replace(/Suporte/g, "Support")
    .replace(/sem leitura/g, "no read")
    .replace(/Sem leitura/g, "No read")
    .replace(/filtros principais alinhados/g, "main filters are aligned")
    .replace(/Filtros principais alinhados/g, "Main filters are aligned")
    .replace(/aguardar/g, "wait")
    .replace(/Aguardar/g, "Wait")
    .replace(/monitorando/g, "watching")
    .replace(/Monitorando/g, "Watching");
}

function localizeUiText(value?: string | null, locale: AppLocale = "pt-BR", symbol?: string | null) {
  const text = String(value || "").trim();
  if (locale !== "en-US" || !text) return text;
  return translatePtToEn(text, symbol);
}

function portugueseNewsInsight(text: string | null | undefined, symbol: string) {
  const value = String(text || "").trim();
  if (looksPortuguese(value)) return value;
  return `Notícia relevante detectada em ${symbol}; confirme impacto em preço, volume e leitura da IA antes de agir.`;
}

function companyAliasesForSymbol(symbol: string) {
  const normalized = normalizeSymbol(symbol);
  const aliases = new Set<string>([normalized]);
  const companyName = COMPANY_HINTS[normalized];
  if (companyName) aliases.add(companyName);

  if (/^[A-Z]{4}\d{1,2}$/.test(normalized)) aliases.add(normalized.slice(0, 4));
  if (normalized === "F") {
    aliases.add("Ford");
    aliases.add("Ford Motor");
  }
  if (normalized.startsWith("PETR")) {
    aliases.add("Petrobras");
    aliases.add("Petrobras PN");
    aliases.add("PETR");
    aliases.add("PBR");
  }
  if (normalized.startsWith("BBDC")) {
    aliases.add("Bradesco");
    aliases.add("BBDC");
  }
  if (normalized.startsWith("ITUB")) {
    aliases.add("Itau");
    aliases.add("Itaú");
    aliases.add("ITUB");
  }
  if (normalized.startsWith("VALE")) {
    aliases.add("Vale");
    aliases.add("VALE");
  }

  return Array.from(aliases).filter(Boolean);
}

function newsMatchesSelectedTicker(item: NewsItem, symbol: string) {
  const normalized = normalizeSymbol(symbol);
  const fields = [
    item.title,
    item.summary,
    item.card_summary,
    item.editorial,
    item.market_context,
    item.why_it_matters,
    item.trader_takeaway,
    ...(item.entities || []),
    ...(item.labels || []),
  ]
    .filter(Boolean)
    .join(" ");
  const haystack = fields.toLowerCase();
  const title = String(item.title || "");
  const titleLower = title.toLowerCase();
  const aliases = companyAliasesForSymbol(normalized);
  const aliasHit = aliases.some((alias) => haystack.includes(String(alias).toLowerCase()));
  const titleAliasHit = aliases.some((alias) => titleLower.includes(String(alias).toLowerCase()));
  const tickerMatches = normalizeSymbol(item.ticker || "") === normalized;
  const foreignTickerInTitle = Array.from(title.matchAll(/\(([A-Z]{1,6}\d{0,2})\)/g))
    .map((match) => normalizeSymbol(match[1]))
    .some((ticker) => ticker && ticker !== normalized && !aliases.map(normalizeSymbol).includes(ticker));

  if (foreignTickerInTitle && !titleAliasHit) return false;
  if (tickerMatches && (aliasHit || !foreignTickerInTitle)) return true;
  return aliasHit;
}

function portugueseNewsTitle(item: NewsItem, symbol: string) {
  const title = String(item.title || "").trim();
  if (looksPortuguese(title)) return title;

  const candidate = [
    item.trader_takeaway,
    item.editorial,
    item.why_it_matters,
    item.impact_reason,
    item.market_context,
  ].find((value) => looksPortuguese(value));

  if (candidate) {
    const cleaned = String(candidate).trim().replace(/\s+/g, " ");
    return cleaned.length > 120 ? `${cleaned.slice(0, 117)}...` : cleaned;
  }

  return `Notícia relevante para ${symbol}`;
}

function portugueseNewsBody(item: NewsItem, symbol: string) {
  const candidate = [
    item.editorial,
    item.why_it_matters,
    item.market_context,
    item.impact_reason,
    item.trader_takeaway,
    item.card_summary,
    item.summary,
  ].find((value) => looksPortuguese(value));

  if (candidate) {
    const cleaned = String(candidate).trim().replace(/\s+/g, " ");
    return cleaned.length > 180 ? `${cleaned.slice(0, 177)}...` : cleaned;
  }

  return `Sem resumo em português disponível para ${symbol}.`;
}

function displayNewsTitle(item: NewsItem, symbol: string, locale: AppLocale) {
  if (locale !== "en-US") return portugueseNewsTitle(item, symbol);

  const title = String(item.title || "").trim();
  if (title && !looksPortuguese(title)) return title.length > 130 ? `${title.slice(0, 127)}...` : title;

  const candidate = [
    item.trader_takeaway,
    item.editorial,
    item.why_it_matters,
    item.impact_reason,
    item.market_context,
    item.card_summary,
    item.summary,
  ].find((value) => String(value || "").trim());

  const translated = localizeUiText(candidate || title, locale, symbol);
  if (translated) return translated.length > 130 ? `${translated.slice(0, 127)}...` : translated;
  return `Relevant news for ${symbol}`;
}

function displayNewsBody(item: NewsItem, symbol: string, locale: AppLocale) {
  if (locale !== "en-US") return portugueseNewsBody(item, symbol);

  const candidate = [
    item.editorial,
    item.why_it_matters,
    item.market_context,
    item.impact_reason,
    item.trader_takeaway,
    item.card_summary,
    item.summary,
  ].find((value) => String(value || "").trim());
  const translated = localizeUiText(candidate || "", locale, symbol);
  if (translated) return translated.length > 190 ? `${translated.slice(0, 187)}...` : translated;
  return `No English summary available for ${symbol}.`;
}

function localizeImpactLabel(value: string | null | undefined, locale: AppLocale) {
  const text = String(value || "Neutro").trim();
  if (locale !== "en-US") return text;
  const normalized = normalizeUiText(text);
  if (normalized.includes("positivo")) return "Positive";
  if (normalized.includes("negativo")) return "Negative";
  if (normalized.includes("util")) return "Useful";
  if (normalized.includes("ruido")) return "Noise";
  if (normalized.includes("neutro")) return "Neutral";
  return localizeUiText(text, locale);
}

function isGenericPollQuestion(question?: string | null) {
  return /qual leitura semanal|qual o cen[aá]rio mais prov[aá]vel|o cen[aá]rio favorece|vai bater o an[uú]ncio|estrutura atual|continuidade com vi[eé]s|press[aã]o ou lateraliza[cç][aã]o|leitura da semana/i.test(String(question || ""));
}

function describeDayTradeBias(bias?: string | null, score?: number | null, changePct?: number | null) {
  const text = String(bias || "").toLowerCase();
  const numericScore = Number(score || 0);
  const numericChange = Number(changePct || 0);
  const direction = text.includes("baixa") || text.includes("sell") || numericChange < 0
    ? "tendência de venda ou defesa curta"
    : text.includes("alta") || text.includes("buy") || numericChange > 0
      ? "tendência de compra ou pullback comprador"
      : "regime lateral; espere rompimento ou rejeição clara";
  const quality = numericScore >= 7
    ? "score forte"
    : numericScore >= 5
      ? "score moderado"
      : "score fraco, use apenas como alerta";
  return `${quality}; ${direction}.`;
}

function describeVolumeContext(volumeLabel: string, changePct?: number | null, volumeScore?: number | null) {
  const change = Number(changePct || 0);
  const label = volumeLabel.toLowerCase();
  if (label === "alto" && change > 0) return "volume alto com deslocamento comprador; observe acumulação e defesa de VWAP.";
  if (label === "alto" && change < 0) return "volume alto com pressão vendedora; confirme se é distribuição ou stop hunt.";
  if (label === "alto") return "volume alto sem deslocamento; leitura de absorção no momento.";
  if (label === "baixo") return "volume baixo; evite antecipar entrada sem candle de confirmação.";
  if (volumeScore != null) return "volume normal; use preço, liquidez e notícia como confirmação tática.";
  return "volume ainda sem leitura confiável; não transforme ausência de dado em sinal.";
}

function chartActionLabel(marker?: ChartPayload["markers"][number] | null) {
  const explicit = String(marker?.action_label || marker?.label || "").trim();
  const type = String(marker?.type || explicit || "").toUpperCase();
  if (explicit && !["BUY", "SELL", "SHORT", "COVER"].includes(explicit.toUpperCase())) return explicit;
  if (type === "BUY") return "Buy Long";
  if (type === "SELL") return "Close Long";
  if (type === "SHORT") return "Sell Short";
  if (type === "COVER") return "Close Short";
  return marker?.derived ? "Watch" : "Aguardar";
}

function chartDirectionText(label: string, locale: AppLocale = "pt-BR") {
  const normalized = label.toLowerCase();
  if (locale === "en-US") {
    if (normalized.includes("buy long")) return "Open long only after trigger confirmation; do not buy into resistance.";
    if (normalized.includes("close long")) return "Close long or avoid a new buy until price recovers structure.";
    if (normalized.includes("sell short")) return "Open short only after support/VWAP loss with selling volume.";
    if (normalized.includes("close short")) return "Close short if VWAP/EMA21 recovers or institutional buying appears.";
    return "Watch; no operational order until confirmation is complete.";
  }
  if (normalized.includes("buy long")) return "Abrir long apenas se o trigger confirmar; não comprar resistência sem rompimento.";
  if (normalized.includes("close long")) return "Encerrar long ou evitar nova compra até o preço recuperar estrutura.";
  if (normalized.includes("sell short")) return "Abrir short apenas com perda de suporte/VWAP e volume vendedor.";
  if (normalized.includes("close short")) return "Encerrar short se houver recuperação de VWAP/EMA21 ou compra institucional.";
  return "Observar; sem ordem operacional enquanto faltar confirmação.";
}

function cleanEnglishDecisionText(value: string | undefined | null, fallback: string, symbol: string) {
  const localized = localizeUiText(value || "", "en-US", symbol);
  const dirty = /\b(sem|se|quando|confirmacao|preco|suporte|resistencia|baixo|medio|alto|filtros|principais|alinhados|ordem operacional|tecnico|virada|ausencia|conflito de|divergirem|antes de|recuperar)\b/i.test(localized);
  return localized && !dirty ? localized : fallback;
}

function latestChartMarker(chart?: ChartPayload | null) {
  const markers = Array.isArray(chart?.markers) ? chart?.markers || [] : [];
  return markers.length ? markers[markers.length - 1] : null;
}

function buildChartDecisionCards(
  chart: ChartPayload | null,
  symbol: string,
  price?: number | null,
  locale: AppLocale = "pt-BR",
) {
  const isEnglish = locale === "en-US";
  const rows = chart?.ohlc?.length ? chart.ohlc : chart?.series || [];
  const marker = latestChartMarker(chart);
  const actionLabel = chartActionLabel(marker);
  const trend = chart?.summary?.trend_bias || "sem regime";
  const latestSignal = chart?.summary?.latest_signal || marker?.type || "WATCH";
  const missing: string[] = [];
  if (!rows.length) missing.push("serie OHLC do provider");
  if (price == null) missing.push("preco real confirmado");
  if (!marker) missing.push("marcador operacional confirmado");

  if (missing.length) {
    return [
      { label: "Leitura atual", value: isEnglish ? `${symbol}: missing ${missing.map((item) => localizeUiText(item, locale, symbol)).join(", ")}.` : `${symbol}: faltando ${missing.join(", ")}.` },
      { label: "Direcao operacional", value: isEnglish ? "Wait; the screen must not turn missing data into a trade." : "Aguardar; a tela nao deve transformar dado ausente em trade." },
      { label: "Confirmacao necessaria", value: isEnglish ? "Confirmed price, valid candle, volume and regime/flow on the same side." : "Preco real, candle valido, volume e regime/fluxo no mesmo lado." },
      { label: "Invalidacao", value: isEnglish ? "Any read without real price/volume stays as observation." : "Qualquer leitura sem preco/volume real fica em observacao." },
      { label: "Risco", value: isEnglish ? "High if trading with incomplete data; keep it as watch." : "Alto se operar sem dado completo; manter como watch." },
    ];
  }

  const triggerFallback = `Confirm ${actionLabel} only with candle, volume, VWAP/EMA21 and flow aligned.`;
  const invalidationFallback = `Invalidate if price loses structure, volume or the regime that supported ${actionLabel}.`;
  const riskLevel = localizeUiText(marker?.risk_level || "medium", "en-US", symbol);
  const riskFallback = `Risk ${riskLevel}: size the trade carefully and avoid range noise.`;

  return [
    {
      label: "Leitura atual",
      value: isEnglish
        ? `${symbol}: ${localizeUiText(trend, locale, symbol)}; latest signal ${actionLabel} (${localizeUiText(latestSignal, locale, symbol)}).`
        : `${symbol}: ${trend}; ultimo sinal ${actionLabel} (${latestSignal}).`,
    },
    { label: "Direcao operacional", value: chartDirectionText(actionLabel, locale) },
    {
      label: "Confirmacao necessaria",
      value: isEnglish
        ? cleanEnglishDecisionText(String(marker?.trigger || marker?.confirmation || ""), triggerFallback, symbol)
        : String(marker?.trigger || marker?.confirmation || "Confirmar candle, volume, VWAP/EMA21 e fluxo antes de agir."),
    },
    {
      label: "Invalidacao",
      value: isEnglish
        ? cleanEnglishDecisionText(String(marker?.invalidation || ""), invalidationFallback, symbol)
        : String(marker?.invalidation || "Invalidar se perder estrutura, volume ou regime que sustentou o sinal."),
    },
    {
      label: "Risco",
      value: isEnglish
        ? cleanEnglishDecisionText(String(marker?.risk || ""), riskFallback, symbol)
        : String(marker?.risk || `Risco ${marker?.risk_level || "medio"}; controle tamanho e evite lateralizacao.`),
    },
  ];
}

function quoteFromMap(quotes: Record<string, QuotePayload>, symbol?: string | null) {
  const normalized = normalizeSymbol(String(symbol || ""));
  if (!normalized) return null;
  for (const alias of symbolAliases(symbol)) {
    const quote = quotes[alias] || quotes[normalizeSymbol(alias)];
    if (quote) return quote;
  }
  return null;
}

function resolveQuoteForSymbol(
  symbol: string,
  publicQuotes: Record<string, QuotePayload>,
  tickerTapeQuotes: Record<string, QuotePayload>,
) {
  return quoteFromMap(tickerTapeQuotes, symbol) || quoteFromMap(publicQuotes, symbol);
}

function scoreToolCandidateForTab(
  tabId: string,
  item: {
    symbol?: string | null;
    ticker?: string | null;
    category?: string | null;
    changePct?: number | null;
    score?: number | null;
    volume?: number | null;
    rvol?: number | null;
    rsi?: number | null;
    adx?: number | null;
    atr_pct?: number | null;
    trend?: string | null;
  },
) {
  const hasUsableMarketSignal =
    item.changePct != null ||
    item.score != null ||
    item.volume != null ||
    item.rsi != null ||
    item.rvol != null ||
    item.adx != null ||
    item.atr_pct != null;
  if (!hasUsableMarketSignal) return -999;

  const change = Number(item.changePct || 0);
  const absChange = Math.abs(change);
  const score = Number(item.score || 0);
  const volume = Math.max(0, Number(item.volume || 0));
  const volumeScore = volume > 0 ? clampNumber(Math.log10(volume + 1) - 4, 0, 5) : 0;
  const rvol = Number(item.rvol ?? deriveRelativeVolume(volume));
  const rsi = Number(item.rsi || 50);
  const adx = Number(item.adx || deriveAdx(change, rsi, item.trend));
  const atr = Number(item.atr_pct || deriveAtrPct(change, rsi, volume));
  const trendText = String(item.trend || "").toLowerCase();
  const bullish = change > 0 || trendText.includes("alta") || trendText.includes("buy") || trendText.includes("compra");
  const bearish = change < 0 || trendText.includes("baixa") || trendText.includes("sell") || trendText.includes("venda");
  const stable = Math.max(0, 1.2 - absChange);
  const rsiExtreme = Math.abs(rsi - 50);
  const mildBullish = bullish && change >= 0 && change <= 1.2;
  const mildBearish = bearish && Math.abs(change) <= 1.2;
  const symbolSeed = normalizeSymbol(String(item.symbol || item.ticker || ""))
    .split("")
    .reduce((total, char) => total + char.charCodeAt(0), 0);
  const category = String(item.category || guessCategory(normalizeSymbol(String(item.symbol || item.ticker || "")))).toLowerCase();
  const isCrypto = category === "crypto";
  const isB3 = category === "b3";
  const isBdr = category === "bdr";
  const isUsa = category === "usa";
  const b3LensBonus = isB3 ? 1 : 0;
  const equityLensBonus = isCrypto ? -2.4 : isB3 ? 1.1 : 0.35;
  const institutionalCategoryBonus = isB3 ? 5 : isBdr ? 1.4 : isUsa ? 0.8 : -6;
  const liquidityCategoryBonus = isB3 ? 4.4 : isBdr ? 1.2 : isUsa ? 0.7 : -5;
  const accumulationCategoryBonus = isB3 ? 3.6 : isBdr ? 0.8 : isUsa ? 0.4 : -4.5;
  const smartMoneyCategoryBonus = isCrypto ? -2.2 : isB3 ? 1.8 : isBdr ? 1.1 : 0.8;
  const lensSeed = tabId.split("").reduce((total, char) => total + char.charCodeAt(0), 0);
  const diversityBonus = ((symbolSeed + lensSeed * 7) % 17) / 17;

  switch (tabId) {
    case "heat-map":
      return absChange * 4 + score * 0.55 + rvol * 1.1 + (bullish ? 0.8 : bearish ? 0.6 : 0) + b3LensBonus * 0.35 + diversityBonus * 0.35;
    case "radar":
      return absChange * 6.2 + Math.max(0, rvol - 1) * 3.4 + volumeScore * 0.65 + adx * 0.04 + (isCrypto ? -0.6 : 0.25) + diversityBonus * 0.75;
    case "breakout-probability":
      return (bullish ? 4.5 : -4) + Math.max(0, change) * 3.7 + adx * 0.14 + rvol * 1.05 + score * 0.5 + equityLensBonus * 0.35 + diversityBonus * 0.5;
    case "volatility-squeeze":
      return stable * 4.9 + Math.max(0, 55 - rsiExtreme) * 0.07 + Math.max(0, 2 - atr) * 1.25 + Math.max(0, 1.3 - rvol) * 0.85 + score * 0.2 + equityLensBonus * 0.35 + diversityBonus * 0.65;
    case "institutional-flow":
      return volumeScore * 2.6 + Math.max(0, rvol - 1) * 3.1 + absChange * 0.65 + score * 0.35 + institutionalCategoryBonus + diversityBonus * 0.45;
    case "smart-money":
      return score * 1.18 + stable * 1.9 + Math.max(0, rvol - 1) * 1.35 + adx * 0.05 + (mildBullish ? 1.6 : mildBearish ? 0.7 : 0) + smartMoneyCategoryBonus + diversityBonus * 0.6;
    case "accumulation":
      return (mildBullish ? 3.4 : bearish ? -2.4 : 0.7) + stable * 3.4 + Math.max(0, rvol - 0.8) * 1.25 + score * 0.42 + accumulationCategoryBonus + diversityBonus * 0.7;
    case "liquidity-sweep":
      return absChange * 3.1 + atr * 2.35 + rsiExtreme * 0.09 + Math.max(0, rvol - 1) * 1.15 + adx * 0.035 + equityLensBonus * 0.55 + diversityBonus * 0.8;
    case "liquidity-map":
      return stable * 3.2 + atr * 2.25 + rsiExtreme * 0.11 + Math.max(0, 2.2 - Math.abs(rvol - 1.2)) * 1.35 + score * 0.22 + liquidityCategoryBonus * 0.55 + diversityBonus * 1.9;
    case "market-regime":
      return adx * 0.24 + score * 0.62 + rsiExtreme * 0.08 + absChange * 1.1 + volumeScore * 0.25 + diversityBonus * 0.4;
    case "master-score":
      return score * 1.7 + rvol * 0.85 + adx * 0.08 + absChange * 1.2 + volumeScore * 0.35 + diversityBonus * 0.25;
    default:
      return score;
  }
}

function buildToolLensMetrics(input: {
  tabId: string;
  score?: number | null;
  changePct?: number | null;
  volume?: number | null;
  rvol?: number | null;
  rsi?: number | null;
  adx?: number | null;
  atr_pct?: number | null;
  trend?: string | null;
}): AiToolMetrics {
  const change = Number(input.changePct || 0);
  const absChange = Math.abs(change);
  const rvol = Number(input.rvol ?? deriveRelativeVolume(input.volume));
  const rsi = Number(input.rsi ?? 50);
  const adx = Number(input.adx ?? deriveAdx(change, rsi, input.trend));
  const atrPct = Number(input.atr_pct ?? deriveAtrPct(change, rsi, input.volume));
  const score = Number(input.score || 0);
  const trendText = String(input.trend || "").toLowerCase();
  const bullish = change > 0 || trendText.includes("alta") || trendText.includes("buy") || trendText.includes("compra");
  const bearish = change < 0 || trendText.includes("baixa") || trendText.includes("sell") || trendText.includes("venda");
  const compression = clampNumber(100 - atrPct * 18 - absChange * 10, 0, 100);
  const volumeImpulse = Math.max(0, rvol - 1);

  switch (input.tabId) {
    case "heat-map":
      return {
        forca_relativa: Number((change * 8 + score * 6 + volumeImpulse * 12).toFixed(1)),
        variacao_pct: Number(change.toFixed(2)),
        rvol: Number(rvol.toFixed(2)),
        lado: bullish ? "forte comprador" : bearish ? "fraco/vendedor" : "misto",
      };
    case "radar":
      return {
        aceleracao: Number((absChange * 10 + volumeImpulse * 20).toFixed(1)),
        momentum: Number((change * 1.4).toFixed(2)),
        rvol: Number(rvol.toFixed(2)),
        movimento_anormal: absChange >= 0.35 || rvol >= 1.4,
      };
    case "breakout-probability":
      return {
        pressao_rompimento: Number((Math.max(0, change) * 12 + adx * 0.7 + volumeImpulse * 16).toFixed(1)),
        adx: Number(adx.toFixed(1)),
        rvol: Number(rvol.toFixed(2)),
        risco_falso_rompimento: Number((Math.max(0, atrPct * 9 - volumeImpulse * 6)).toFixed(1)),
      };
    case "volatility-squeeze":
      return {
        compressao: Number(compression.toFixed(1)),
        atr_pct: Number(atrPct.toFixed(2)),
        rsi: Number(rsi.toFixed(1)),
        gatilho: compression >= 55 ? "squeeze armado" : "sem compressao limpa",
      };
    case "institutional-flow":
      return {
        volume_proxy: Number((volumeImpulse * 100).toFixed(1)),
        agressao_proxy: Number((Math.abs(change) * rvol * 8).toFixed(1)),
        rvol: Number(rvol.toFixed(2)),
        confirmacao_preco: bullish ? "deslocamento comprador" : bearish ? "pressao vendedora" : "neutro",
      };
    case "smart-money":
      return {
        posicionamento: Number((score * 8 + volumeImpulse * 12 + adx * 0.4).toFixed(1)),
        absorcao_proxy: Number((Math.max(0, 1.2 - absChange) * rvol * 20).toFixed(1)),
        adx: Number(adx.toFixed(1)),
        rvol: Number(rvol.toFixed(2)),
      };
    case "accumulation":
      return {
        absorcao: Number((Math.max(0, 1.1 - absChange) * 45 + volumeImpulse * 18).toFixed(1)),
        estabilidade: Number(Math.max(0, 100 - absChange * 35).toFixed(1)),
        rvol: Number(rvol.toFixed(2)),
        leitura: bullish && absChange < 1.2 ? "compra discreta" : "acumulacao nao confirmada",
      };
    case "liquidity-sweep":
      return {
        sweep_risk: Number((atrPct * 12 + absChange * 8 + volumeImpulse * 9).toFixed(1)),
        atr_pct: Number(atrPct.toFixed(2)),
        range_proxy: Number((absChange + atrPct).toFixed(2)),
        reacao: absChange >= 0.5 ? "varrida possivel" : "aguardar varrida",
      };
    case "liquidity-map":
      return {
        liquidez: Number((volumeImpulse * 30 + atrPct * 9 + score * 5).toFixed(1)),
        zona_stop: bullish ? "acima da resistencia" : bearish ? "abaixo do suporte" : "bordas do range",
        volume_proxy: Number((volumeImpulse * 100).toFixed(1)),
        atr_pct: Number(atrPct.toFixed(2)),
      };
    case "market-regime":
      return {
        regime: adx >= 22 ? (bullish ? "tendencia de alta" : bearish ? "tendencia de baixa" : "trend indefinido") : "lateral",
        adx: Number(adx.toFixed(1)),
        rsi: Number(rsi.toFixed(1)),
        tendencia: bullish ? "alta" : bearish ? "baixa" : "lateral",
      };
    case "master-score":
      return {
        score_composto: Number((score * 10).toFixed(1)),
        confirmacoes: Number((Number(bullish || bearish) + Number(rvol >= 1.2) + Number(adx >= 18) + Number(absChange >= 0.25)).toFixed(0)),
        classificacao: score >= 7 ? "forte" : score >= 5 ? "moderada" : "fraca",
        divergencia: bearish && score >= 7 ? "risco direcional" : "controlada",
      };
    default:
      return {
        score,
        variacao_pct: Number(change.toFixed(2)),
        rvol: Number(rvol.toFixed(2)),
      };
  }
}

function formatToolMetricLabel(label: string, locale: AppLocale = "pt-BR") {
  return humanizeMachineLabel(label.replace(/_/g, " "), locale);
}

function formatToolMetricValue(value: unknown, locale: AppLocale = "pt-BR") {
  if (typeof value === "boolean") return value ? (locale === "en-US" ? "yes" : "sim") : (locale === "en-US" ? "no" : "não");
  if (typeof value === "number" && Number.isFinite(value)) {
    if (Math.abs(value) >= 1000) return formatCompact(value);
    return Math.abs(value) >= 10 ? value.toFixed(1) : value.toFixed(2);
  }
  return humanizeMachineLabel(String(value ?? "sem leitura"), locale);
}

function buildQuoteFallbackChart(
  symbol: string,
  interval: string,
  quote?: QuotePayload | null,
  trend?: string | null,
): ChartPayload | null {
  const price = firstFiniteNumber(quote?.price);
  if (price == null || price <= 0) return null;

  const normalizedInterval = String(interval || "1D").toUpperCase();
  const countByInterval: Record<string, number> = {
    "1D": 48,
    "1W": 40,
    "1M": 44,
    "3M": 52,
    "6M": 60,
    YTD: 58,
    "1Y": 64,
    ALL: 72,
  };
  const stepMsByInterval: Record<string, number> = {
    "1D": 5 * 60 * 1000,
    "1W": 60 * 60 * 1000,
    "1M": 24 * 60 * 60 * 1000,
    "3M": 2 * 24 * 60 * 60 * 1000,
    "6M": 4 * 24 * 60 * 60 * 1000,
    YTD: 5 * 24 * 60 * 60 * 1000,
    "1Y": 6 * 24 * 60 * 60 * 1000,
    ALL: 10 * 24 * 60 * 60 * 1000,
  };
  const count = countByInterval[normalizedInterval] || 48;
  const stepMs = stepMsByInterval[normalizedInterval] || stepMsByInterval["1D"];
  const change = firstFiniteNumber(quote?.change);
  const changePct = firstFiniteNumber(quote?.change_pct) ?? 0;
  const startPrice = change != null ? Math.max(price - change, price * 0.97) : price * (1 - changePct / 100);
  const seed = normalizeSymbol(symbol).split("").reduce((total, char) => total + char.charCodeAt(0), 0);
  const trendText = String(trend || "").toLowerCase();
  const bullish = changePct > 0 || trendText.includes("alta") || trendText.includes("buy") || trendText.includes("compra");
  const volatility = Math.max(price * 0.0015, Math.abs(price - startPrice) * 0.18, price * 0.0008);
  const now = Date.now();
  const ohlc = Array.from({ length: count }, (_, index) => {
    const t = count === 1 ? 1 : index / (count - 1);
    const wave = Math.sin((index + seed) * 0.72) * volatility + Math.cos((index + seed) * 0.31) * volatility * 0.55;
    const close = index === count - 1 ? price : startPrice + (price - startPrice) * t + wave;
    const previousBase = index === 0 ? startPrice : startPrice + (price - startPrice) * ((index - 1) / (count - 1));
    const open = index === 0 ? startPrice : previousBase + Math.sin((index - 1 + seed) * 0.72) * volatility;
    const high = Math.max(open, close) + volatility * (0.8 + ((index + seed) % 5) / 10);
    const low = Math.min(open, close) - volatility * (0.8 + ((index + seed) % 4) / 10);
    return {
      time: new Date(now - (count - 1 - index) * stepMs).toISOString(),
      open,
      high,
      low,
      close,
      volume: Math.max(1, Number(quote?.volume || 0) / count) * (0.65 + ((index + seed) % 9) / 10),
      ema9: close,
      ema21: close,
      supertrend: close,
      supertrend_side: bullish ? "buy" : "sell",
    };
  });
  const highs = ohlc.map((bar) => bar.high);
  const lows = ohlc.map((bar) => bar.low);
  const resistance = Math.max(...highs);
  const support = Math.min(...lows);
  const markerIndexes = [Math.floor(count * 0.22), Math.floor(count * 0.48), Math.floor(count * 0.73), count - 2]
    .filter((index, position, indexes) => index > 0 && index < count && indexes.indexOf(index) === position);
  const markers = markerIndexes.map((index, markerIndex) => {
    const side: "buy" | "sell" = markerIndex % 2 === 0 ? "buy" : "sell";
    return {
      time: ohlc[index].time,
      price: ohlc[index].close,
      side,
      label: side === "buy" ? "BUY" : "SELL",
      score: Math.max(1, Math.round(Math.abs(changePct) * 10) + markerIndex + 1),
    };
  });

  return {
    ticker: normalizeSymbol(symbol),
    interval: normalizedInterval,
    ohlc,
    series: ohlc,
    markers,
    zones: [
      { label: "resistência", price: resistance },
      { label: "suporte", price: support },
    ],
    summary: {
      ticker: normalizeSymbol(symbol),
      latest_close: price,
      trend_bias: bullish ? "alta" : changePct < 0 ? "baixa" : "lateral",
    },
  };
}

function buildPublicToolNarrative(input: {
  tabId: string;
  symbol: string;
  score: number;
  changePct?: number | null;
  price?: number | null;
  volume?: number | null;
  rsi?: number | null;
  rvol?: number | null;
  adx?: number | null;
  atrPct?: number | null;
  trend?: string | null;
}) {
  const scoreValue = Number.isFinite(Number(input.score)) ? Number(input.score) : 5;
  const changeText = input.changePct != null ? formatSignedPercent(input.changePct) : "sem variação confirmada";
  const priceText = input.price != null ? formatPrice(input.price) : "preço pendente";
  const volumeText = input.volume != null ? formatCompact(input.volume) : "volume pendente";
  const rsiText = input.rsi != null ? input.rsi.toFixed(1) : "RSI pendente";
  const rvolValue = Number(input.rvol ?? deriveRelativeVolume(input.volume));
  const adxValue = Number(input.adx ?? deriveAdx(input.changePct, input.rsi, input.trend));
  const atrValue = Number(input.atrPct ?? deriveAtrPct(input.changePct, input.rsi, input.volume));
  const rvolText = Number.isFinite(rvolValue) ? rvolValue.toFixed(2) : "sem leitura";
  const adxText = Number.isFinite(adxValue) ? adxValue.toFixed(1) : "sem leitura";
  const atrText = Number.isFinite(atrValue) ? `${atrValue.toFixed(1)}%` : "sem leitura";
  const scoreText = scoreValue.toFixed(1);
  const conviction =
    scoreValue >= 7.5
      ? "alta convicção"
      : scoreValue >= 6
        ? "convicção moderada"
        : scoreValue >= 4.5
          ? "observação tática"
          : "baixa convicção";
  const biasText = humanizeMachineLabel(input.trend || (input.changePct != null && input.changePct >= 0 ? "alta" : "baixa"));
  const strongMove = Math.abs(Number(input.changePct || 0)) >= 0.35;
  const isBullish = Number(input.changePct || 0) > 0 || String(input.trend || "").toLowerCase().includes("alta");
  const signal = isBullish ? "BUY" : "SELL";
  const side = isBullish ? "compra" : "venda";
  const oppositeSide = isBullish ? "venda" : "compra";
  const direction = isBullish ? "para cima" : "para baixo";
  const executionLevel = isBullish ? "acima da máxima/rompimento" : "abaixo do suporte/perda da mínima";
  const volumeCondition = Number.isFinite(rvolValue) && rvolValue >= 1.4 ? "volume relativo forte" : "volume ainda sem explosão";
  const trendCondition = Number.isFinite(adxValue) && adxValue >= 25 ? "tendência forte" : "tendência ainda precisa confirmar";
  const volatilityCondition = Number.isFinite(atrValue) && atrValue >= 2.2 ? "volatilidade alta" : "volatilidade controlada";
  const signature = `Score ${scoreText} (${conviction}), RVOL ${rvolText}, ADX ${adxText}, ATR ${atrText}`;

  const base = {
    signal,
    state: "monitorando",
    ai_comment: `${input.symbol}: ${signature}. Preço ${priceText}, variação ${changeText}, volume ${volumeText}; leitura favorece ${side} só se preço e fluxo sustentarem ${direction}.`,
    trigger: `Gatilho de ${side}: confirmar ${executionLevel} com ${volumeCondition} e ${trendCondition}.`,
    invalidation: `Invalida se aparecer ${oppositeSide} com RVOL maior, perda do nível tático ou reversão forte no próximo candle.`,
  };

  switch (input.tabId) {
    case "heat-map":
      return {
        ...base,
        state: isBullish ? "força compradora" : "pressão vendedora",
        ai_comment: `${input.symbol} no mapa de força: ${signature}; variação ${changeText}, volume ${volumeText}, bias ${biasText}. Direção tática: ${side}.`,
        trigger: `Mapa só autoriza ${side} se o ativo mantiver força relativa com RVOL ${rvolText} e romper ${executionLevel}.`,
        invalidation: `Perde a leitura se Score cair abaixo de ${scoreValue >= 7 ? "6.5" : "5.0"}, força voltar a neutra ou surgir ${oppositeSide} dominante no tape.`,
      };
    case "radar":
      return {
        ...base,
        state: strongMove ? "movimento ativo" : "radar inicial",
        ai_comment: `${input.symbol} no radar: ${signature}; aceleração ${changeText}, volume ${volumeText}. Direção preferida: ${side}.`,
        trigger: strongMove
          ? `Entrar só se o próximo candle continuar ${direction}, RVOL ficar perto/acima de ${rvolText} e ADX não perder força.`
          : `Aguardar nova aceleração; com Score ${scoreText}, ${side} ainda exige expansão de preço e volume.`,
        invalidation: `Sai do radar se velocidade cair, RVOL ficar abaixo de 1.00 ou candle forte de ${oppositeSide} devolver o movimento.`,
      };
    case "breakout-probability":
      return {
        ...base,
        state: isBullish ? "testando resistência" : "rompimento negado",
        ai_comment: `${input.symbol} em probabilidade de rompimento: ${signature}; preço ${priceText}, ${changeText}, bias ${biasText}. Plano: ${side} com confirmação.`,
        trigger: isBullish
          ? `Comprar apenas acima da resistência/máxima com RVOL ${rvolText} crescente; Score ${scoreText} define tamanho da convicção.`
          : `Vender/evitar compra se perder suporte com ${volumeCondition}; Score ${scoreText} pede confirmação extra.`,
        invalidation: isBullish
          ? `Invalida se romper e fechar abaixo da resistência ou se RVOL cair antes da continuação.`
          : `Invalida a venda se recuperar suporte com volume comprador e ADX ${adxText} virar a favor.`,
      };
    case "volatility-squeeze":
      return {
        ...base,
        state: strongMove ? "expansão de volatilidade" : "compressão/espera",
        ai_comment: `${input.symbol} em ${strongMove ? "expansão" : "compressão"}: ${signature}; movimento ${changeText}, volume ${volumeText}.`,
        trigger: `Sair da compressão ${direction} com candle amplo, ${volumeCondition} e ATR ${atrText}; antes disso é espera.`,
        invalidation: `Invalida se continuar lateral, ATR não expandir ou rompimento voltar para dentro do range.`,
      };
    case "institutional-flow":
      return {
        ...base,
        state: input.volume && input.volume > 1_000_000 ? "fluxo relevante" : "fluxo em observação",
        ai_comment: `${input.symbol} em fluxo institucional: ${signature}; volume ${volumeText}, variação ${changeText}. Direção de fluxo: ${side}.`,
        trigger: `Executar ${side} só se RVOL sustentar ${rvolText} ou maior junto com deslocamento ${direction}.`,
        invalidation: `Desconsiderar se volume vier sem deslocamento, com pavio contra a tese ou absorção de ${oppositeSide}.`,
      };
    case "smart-money":
      return {
        ...base,
        state: scoreValue >= 7 ? "smart money ativo" : "absorção em teste",
        ai_comment: `${input.symbol} em smart money: ${signature}; plano favorece ${side} apenas se houver defesa de VWAP/zona chave.`,
        trigger: `Confirmar ${side} com rompimento limpo ou pullback defendido; Score ${scoreText} exige que a defesa apareça no tape.`,
        invalidation: `Falha se preço romper contra a tese com RVOL de ${oppositeSide}, perder VWAP ou absorção sumir.`,
      };
    case "accumulation":
      return {
        ...base,
        state: isBullish && !strongMove ? "acumulação discreta" : "acumulação não confirmada",
        ai_comment: `${input.symbol} em acumulação: ${signature}; preço ${changeText}, volume ${volumeText}; leitura favorece entrada gradual, não perseguição.`,
        trigger: `Comprar em pullback curto se preço estabilizar e RVOL subir acima de ${Math.max(1, rvolValue || 1).toFixed(2)} sem candle vendedor forte.`,
        invalidation: `Perde leitura se virar queda forte, gap sem sustentação ou volume vendedor romper suporte.`,
      };
    case "liquidity-sweep":
      return {
        ...base,
        state: "caça liquidez",
        ai_comment: `${input.symbol} em varredura: ${signature}; preço ${priceText}. Procurar stop hunt antes da reação ${direction}.`,
        trigger: `Varrer liquidez, falhar no rompimento e reagir rápido para ${side}; ${volatilityCondition}.`,
        invalidation: `Não operar se a varrida virar tendência contínua contra a reversão esperada ou RVOL confirmar ${oppositeSide}.`,
      };
    case "liquidity-map":
      return {
        ...base,
        state: "zonas de liquidez",
        ai_comment: `${input.symbol} no mapa de liquidez: ${signature}; use bordas do range para planejar ${side} só com reação confirmada.`,
        trigger: `Aguardar toque na zona e reação ${direction} com RVOL ${rvolText}; zona é alerta, não entrada automática.`,
        invalidation: `Zona perde força após muitos testes sem reação, rompimento limpo com volume ou ATR ${atrText} expandindo contra a tese.`,
      };
    case "market-regime":
      return {
        ...base,
        state: isBullish ? "regime de alta" : "regime de baixa/lateral",
        ai_comment: `${input.symbol} em regime ${biasText}: ${signature}; RSI ${rsiText}, movimento ${changeText}. Operação preferida: ${side}.`,
        trigger: isBullish
          ? `Priorizar compras em pullback/rompimento se ADX ${adxText} e RVOL ${rvolText} confirmarem.`
          : `Priorizar defesa/venda/tamanho menor até recuperar estrutura; Score ${scoreText} não autoriza compra isolada.`,
        invalidation: `Regime muda se preço cruzar zona chave com volume e mantiver fechamento contrário por mais de um candle.`,
      };
    case "master-score":
      return {
        ...base,
        state: scoreValue >= 7 ? "oportunidade forte" : scoreValue >= 5 ? "oportunidade moderada" : "oportunidade fraca",
        ai_comment: `${input.symbol} no Score Mestre: ${signature}; preço ${changeText}, volume ${volumeText}, RSI ${rsiText}, bias ${biasText}. Direção final: ${side}.`,
        trigger: `Executar somente quando Score ${scoreText}, preço, RVOL ${rvolText} e regime confirmarem ${side} no mesmo candle.`,
        invalidation: `Baixar prioridade se score cair, volume divergir ou outra IA principal apontar direção oposta.`,
      };
    default:
      return base;
  }
}

function scoreClass(score?: number | null) {
  const numeric = Number(score || 0);
  if (numeric <= 10) {
    if (numeric >= 7) return "up";
    if (numeric >= 5) return "mid";
    return "down";
  }
  if (numeric >= 80) return "up";
  if (numeric >= 50) return "mid";
  return "down";
}

function movementClass(changePct?: number | null, trend?: string | null, score?: number | null) {
  if (changePct != null && !Number.isNaN(Number(changePct))) {
    if (Number(changePct) > 0) return "up";
    if (Number(changePct) < 0) return "down";
  }

  const normalized = String(trend || "").toLowerCase();
  if (normalized.includes("bull") || normalized.includes("alta") || normalized.includes("up")) return "up";
  if (normalized.includes("bear") || normalized.includes("baixa") || normalized.includes("down")) return "down";
  return scoreClass(score);
}

function movementArrow(kind: string) {
  if (kind === "up") return "▲";
  if (kind === "down") return "▼";
  return "•";
}

function sentimentDisplay(sentiment?: string | null, locale: AppLocale = "pt-BR") {
  if (sentiment === "bearish") return locale === "en-US" ? "🐻 Bearish" : "🐻 Urso";
  if (sentiment === "bullish") return locale === "en-US" ? "🐂 Bullish" : "🐂 Touro";
  return locale === "en-US" ? "😐 Neutral" : "😐 Neutro";
}

function humanizeMachineLabel(value?: string | null, locale: AppLocale = "pt-BR") {
  const raw = String(value || "monitorando").trim();
  if (!raw) return locale === "en-US" ? "Watching" : "Monitorando";

  const key = raw
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/[\/_-]+/g, " ")
    .toLowerCase();
  const labels: Record<string, string> = {
    monitoring: "Monitorando",
    monitorando: "Monitorando",
    alta: "Alta",
    baixa: "Baixa",
    lateral: "Lateral",
    buy: "Compra",
    sell: "Venda",
    hold: "Neutro",
    "forca compradora": "Força compradora",
    "pressao vendedora": "Pressão vendedora",
    "movimento ativo": "Movimento ativo",
    "radar inicial": "Radar inicial",
    "testando resistencia": "Testando resistência",
    "expansao de volatilidade": "Expansão de volatilidade",
    "compressao espera": "Compressão/espera",
    "fluxo relevante": "Fluxo relevante",
    "fluxo em observacao": "Fluxo em observação",
    "absorcao em teste": "Absorção em teste",
    "acumulacao discreta": "Acumulação discreta",
    "acumulacao nao confirmada": "Acumulação não confirmada",
    "caca liquidez": "Caça liquidez",
    "mapa quente": "Mapa quente",
    "zonas de liquidez": "Zonas de liquidez",
    "regime de tendencia": "Regime de tendência",
    "regime de alta": "Regime de alta",
    "regime de baixa lateral": "Regime de baixa/lateral",
    "oportunidade forte": "Oportunidade forte",
    "oportunidade moderada": "Oportunidade moderada",
    "oportunidade fraca": "Oportunidade fraca",
  };
  const labelsEn: Record<string, string> = {
    monitoring: "Watching",
    monitorando: "Watching",
    alta: "Uptrend",
    baixa: "Downtrend",
    lateral: "Range",
    buy: "Buy",
    sell: "Sell",
    hold: "Neutral",
    "forca compradora": "Buying strength",
    "pressao vendedora": "Selling pressure",
    "movimento ativo": "Active move",
    "radar inicial": "Early radar",
    "testando resistencia": "Testing resistance",
    "rompimento negado": "Breakout rejected",
    "expansao de volatilidade": "Volatility expansion",
    "compressao espera": "Compression/wait",
    "fluxo relevante": "Relevant flow",
    "fluxo em observacao": "Flow under watch",
    "smart money ativo": "Smart money active",
    "absorcao em teste": "Absorption test",
    "acumulacao discreta": "Discreet accumulation",
    "acumulacao nao confirmada": "Accumulation not confirmed",
    "caca liquidez": "Liquidity hunt",
    "mapa quente": "Hot map",
    "zonas de liquidez": "Liquidity zones",
    "regime de tendencia": "Trend regime",
    "regime de alta": "Uptrend regime",
    "regime de baixa lateral": "Downtrend/range regime",
    "oportunidade forte": "Strong opportunity",
    "oportunidade moderada": "Moderate opportunity",
    "oportunidade fraca": "Weak opportunity",
    forte: "Strong",
    moderada: "Moderate",
    fraca: "Weak",
    "fraco vendedor": "Weak/seller",
    misto: "Mixed",
    "forte comprador": "Strong buyer",
    "squeeze armado": "Squeeze armed",
    "sem compressao limpa": "No clean compression",
    "deslocamento comprador": "Buying displacement",
    "varrida possivel": "Possible sweep",
    "aguardar varrida": "Wait for sweep",
    "acima da resistencia": "Above resistance",
    "abaixo do suporte": "Below support",
    "bordas do range": "Range edges",
    "trend indefinido": "Undefined trend",
    controlada: "Controlled",
    "risco direcional": "Directional risk",
    "forca relativa": "Relative strength",
    "variacao pct": "Change pct",
    lado: "Side",
    "pressao rompimento": "Breakout pressure",
    "risco falso rompimento": "False breakout risk",
    gatilho: "Trigger",
    "volume proxy": "Volume proxy",
    "agressao proxy": "Aggression proxy",
    "confirmacao preco": "Price confirmation",
    "absorcao proxy": "Absorption proxy",
    absorcao: "Absorption",
    estabilidade: "Stability",
    leitura: "Read",
    "sweep risk": "Sweep risk",
    "range proxy": "Range proxy",
    reacao: "Reaction",
    "zona stop": "Stop zone",
    "score composto": "Composite score",
    confirmacoes: "Confirmations",
    classificacao: "Classification",
    divergencia: "Divergence",
  };

  const localized = locale === "en-US" ? labelsEn[key] : labels[key];
  return localized || localizeUiText(raw.replace(/[_-]+/g, " ").replace(/\b\w/g, (letter) => letter.toUpperCase()), locale);
}

function aiSignalTone(signal?: string | null) {
  if (signal === "BUY") return "bullish";
  if (signal === "SELL") return "bearish";
  return "neutral";
}

function formatAiUpdatedAt(value?: string | null, locale: AppLocale = "pt-BR") {
  if (!value) return locale === "en-US" ? "no time" : "sem horário";

  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return locale === "en-US" ? "no time" : "sem horário";

  return parsed.toLocaleTimeString(locale === "en-US" ? "en-US" : "pt-BR", {
    hour: "2-digit",
    minute: "2-digit",
  });
}

function getTabMeta(tab: WorkspaceTab, locale: AppLocale = "pt-BR") {
  const copy = locale === "en-US" ? TAB_META_EN : TAB_META;
  return copy[tab.id] || { label: tab.title, short: tab.title };
}

function buildTabs(source?: WorkspaceTab[]) {
  const byId = new Map<string, WorkspaceTab>();

  for (const tab of source || []) {
    if (!tab?.id) continue;
    byId.set(tab.id, tab);
  }

  for (const fallback of FALLBACK_TABS) {
    if (!byId.has(fallback.id)) byId.set(fallback.id, fallback);
  }

  return TAB_ORDER.filter((id) => byId.has(id)).map((id) => byId.get(id)!);
}

async function fetchReferralLeaderboard(limit = 50): Promise<ReferralLeaderboardPayload> {
  const response = await fetch(`${resolveApiBase()}/billing/referrals/leaderboard?limit=${limit}`, {
    cache: "no-store",
  });

  if (!response.ok) {
    throw new Error(response.statusText || "referral_leaderboard_failed");
  }

  return response.json() as Promise<ReferralLeaderboardPayload>;
}

function readInitialLocale(): AppLocale {
  if (typeof window === "undefined") return "pt-BR";
  const saved = window.localStorage.getItem(APP_LOCALE_STORAGE_KEY);
  return saved === "en-US" ? "en-US" : "pt-BR";
}

function localizeGuideCard(card: { label: string; value: string }, locale: AppLocale) {
  if (locale !== "en-US") return card;

  const labelMap: Record<string, string> = {
    prioridade: "PRIORITY",
    "leitura atual": "CURRENT READ",
    "direcao operacional": "OPERATIONAL DIRECTION",
    "confirmacao necessaria": "CONFIRMATION NEEDED",
    invalidacao: "INVALIDATION",
    risco: "RISK",
  };
  const exactValueMap: Record<string, string> = {
    "Explica melhor o que importa primeiro.": "Explains what matters first.",
    "Comece por preço, notícia útil e leitura final da IA.": "Start with price, useful news and the final AI read.",
    "Risco baixo: filtros principais alinhados.": "Low risk: main filters are aligned.",
  };
  const value = localizeUiText(exactValueMap[card.value] || card.value
    .replace(/Encerrar/g, "Close")
    .replace(/comprada/g, "long")
    .replace(/compra/g, "buy")
    .replace(/venda/g, "sell")
    .replace(/saida/g, "exit")
    .replace(/preco/g, "price")
    .replace(/recuperar/g, "recover")
    .replace(/perda de tendencia/g, "trend loss")
    .replace(/fluxo comprador/g, "buying flow")
    .replace(/fraco/g, "weak")
    .replace(/risco/g, "risk")
    .replace(/lateral/g, "range")
    .replace(/alta/g, "uptrend"), locale);

  return {
    ...card,
    label: labelMap[normalizeUiText(card.label)] || card.label,
    value,
  };
}

function localizePollText(value: string | undefined, locale: AppLocale, selectedTicker: string) {
  if (locale !== "en-US" || !value) return value || "";
  return localizeUiText(value
    .replace(`${selectedTicker}: sem evento dominante, o mercado precisa confirmar fluxo comprador ou rejeicao de risco?`, `${selectedTicker}: with no dominant event, does the market need to confirm buying flow or risk rejection?`)
    .replace("Fluxo comprador precisa aparecer", "Buying flow needs to appear")
    .replace("Rejeicao de risco ainda pesa", "Risk rejection still weighs")
    .replace("sem evento dominante", "no dominant event")
    .replace("mercado precisa confirmar", "market needs to confirm")
    .replace("fluxo comprador", "buying flow")
    .replace("rejeicao de risco", "risk rejection"), locale, selectedTicker);
}

function getBrowserDeviceId() {
  if (typeof window === "undefined") return "web-browser";

  const storageKey = "stocknewsbr.web_device_id";
  const current = window.localStorage.getItem(storageKey);

  if (current) return current;

  const created = typeof crypto !== "undefined" && "randomUUID" in crypto
    ? crypto.randomUUID()
    : `browser-${Date.now()}`;
  window.localStorage.setItem(storageKey, created);
  return created;
}

function getBrowserDeviceLabel() {
  if (typeof navigator === "undefined") return "web_browser";
  return `web_${navigator.platform || "browser"}`;
}

function buildWatchlist(
  ranking: RankingRow[],
  signals: SignalRow[],
  quote: QuotePayload | null,
  quoteMap: Record<string, QuotePayload> = {},
  insight: PublicInsightPayload | null = null,
  selectedTicker: string,
  customItems: WatchlistItem[] = [],
) {
  const bySymbol = new Map<string, WatchlistItem>();

  for (const item of [...PRELOADED_UNIVERSE, ...customItems]) {
    bySymbol.set(item.symbol, { ...item });
  }

  for (const row of ranking || []) {
    const symbol = normalizeSymbol(String(row.symbol || ""));
    if (!symbol) continue;

    const current = bySymbol.get(symbol) || {
      symbol,
      label: symbolName(symbol),
      category: guessCategory(symbol),
    };

    bySymbol.set(symbol, {
      ...current,
      price: row.price ?? current.price ?? null,
      score: row.score ?? current.score ?? null,
      trend: row.trend ?? current.trend ?? null,
    });
  }

  for (const row of signals || []) {
    const symbol = normalizeSymbol(String(row.symbol || row.ticker || ""));
    if (!symbol) continue;

    const current = bySymbol.get(symbol) || {
      symbol,
      label: symbolName(symbol),
      category: guessCategory(symbol),
    };

    bySymbol.set(symbol, {
      ...current,
      price: row.price ?? current.price ?? null,
      score: row.score ?? current.score ?? null,
      trend: row.trend ?? current.trend ?? null,
    });
  }

    for (const [symbol, liveQuote] of Object.entries(quoteMap || {})) {
      const normalized = normalizeSymbol(symbol);
      if (!normalized) continue;
      const current = bySymbol.get(normalized) || {
        symbol: normalized,
        label: symbolName(normalized),
        category: guessCategory(normalized),
      };
      const derivedChangePct = liveQuote.change_pct ?? deriveChangePercent(liveQuote.change ?? null, liveQuote.price ?? null);
      const derivedTrend = current.trend || (derivedChangePct != null ? (derivedChangePct >= 0 ? "alta" : "baixa") : null);
      bySymbol.set(normalized, {
        ...current,
        price: liveQuote.price ?? current.price ?? null,
        change: liveQuote.change ?? current.change ?? null,
        changePct: derivedChangePct ?? current.changePct ?? null,
        volume: liveQuote.volume ?? current.volume ?? null,
        score: current.score ?? derivePublicScore({
          changePct: derivedChangePct ?? null,
          rsi: current.rsi ?? null,
          trend: derivedTrend,
          volume: liveQuote.volume ?? current.volume ?? null,
        }),
        trend: derivedTrend ?? current.trend ?? null,
        rsi: current.rsi ?? derivePublicRsi(derivedChangePct, derivedTrend),
      });
    }

    const selected = bySymbol.get(selectedTicker);
    if (selected && quote?.price != null) {
      selected.price = quote.price;
      selected.changePct = quote.change_pct ?? deriveChangePercent(quote.change ?? null, quote.price ?? null);
      selected.change = quote.change ?? null;
    }

    if (selected) {
      selected.score = insight?.score ?? selected.score ?? null;
    selected.trend = insight?.trend_bias || insight?.signal || selected.trend || null;
    selected.rsi = insight?.rsi ?? selected.rsi ?? null;
    selected.bias = insight?.trend_bias || selected.bias || null;
  }

  return Array.from(bySymbol.values());
}

function buildSyntheticSearchCandidate(query: string, existingSymbols: string[]) {
  const normalized = normalizeSymbol(query);
  if (!normalized || existingSymbols.includes(normalized)) return null;

  let category: string | null = null;

  if (B3_SYMBOL_PATTERN.test(normalized)) {
    category = "B3";
  } else if (BDR_SYMBOL_PATTERN.test(normalized)) {
    category = "BDR";
  } else if (normalized.endsWith("USD")) {
    category = "Crypto";
  } else if (USA_SYMBOL_PATTERN.test(normalized) || /^[A-Z]{1,5}$/.test(normalized)) {
    category = "USA";
  }

  if (!category) return null;

  return {
    symbol: normalized,
    label: symbolName(normalized),
    category,
    price: null,
    changePct: null,
    score: null,
    trend: `${category} manual`,
  } satisfies WatchlistItem;
}

function buildFallbackPoll(symbol: string): PollPayload {
  const normalized = normalizeSymbol(symbol);
  return {
    symbol: normalized,
    status: "fallback_missing_backend_poll",
    question: `${normalized}: sem enquete institucional carregada; qual confirmação falta para validar a tese da semana?`,
    total_votes: 0,
    options: [
      {
        key: "price_volume_confirmation",
        label: "Preço romper nível com volume real",
        votes: 0,
        pct: 0,
      },
      {
        key: "flow_news_confirmation",
        label: "Fluxo ou notícia confirmar contexto",
        votes: 0,
        pct: 0,
      },
    ],
  };
}

type NormalizedPollOption = PollOption & {
  pct: number;
};

type NormalizedPoll = PollPayload & {
  options: NormalizedPollOption[];
  total_votes: number;
};

function normalizePollPayload(poll: PollPayload | null | undefined, symbol: string): NormalizedPoll {
  const fallback = buildFallbackPoll(symbol);
  const source = poll?.options?.length && !isGenericPollQuestion(poll.question)
    ? poll
    : fallback;
  const rawOptions = Array.isArray(source.options) ? source.options : [];
  const sanitizedOptions = rawOptions.map((option) => ({
    ...option,
    votes: Number.isFinite(option.votes) ? Math.max(0, Math.floor(option.votes)) : 0,
    pct: Number.isFinite(option.pct) ? Math.max(0, Math.floor(option.pct ?? 0)) : 0,
  }));
  const votesSum = sanitizedOptions.reduce((sum, option) => sum + option.votes, 0);
  const declaredTotal = Number.isFinite(source.total_votes) ? Math.max(0, Math.floor(source.total_votes ?? 0)) : votesSum;
  const totalVotes = Math.max(declaredTotal, votesSum);

  const normalizedOptions = sanitizedOptions.map((option) => ({
    ...option,
    pct: totalVotes > 0 ? (option.pct || Math.round((option.votes / totalVotes) * 100)) : 0,
  }));
  const fallbackOptions = fallback.options || [];

  return {
    ...fallback,
    ...source,
    symbol,
    question: source.question || fallback.question,
    status: source.status || "active",
    total_votes: totalVotes,
    options: normalizedOptions.length ? normalizedOptions : fallbackOptions.map((option) => ({
      ...option,
      pct: 0,
    })),
  };
}

export function WorkspaceShell({ focusedTab, initialTicker }: Props) {
  const searchParams = useSearchParams();
  const queryToken = searchParams.get("token") || "";
  const queryTicker = normalizeSymbol(searchParams.get("ticker") || initialTicker || "PETR4");

  const [token, setToken] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [otpCode, setOtpCode] = useState("");
  const [pendingLoginToken, setPendingLoginToken] = useState("");
  const [debugOtpCode, setDebugOtpCode] = useState("");
  const [loginError, setLoginError] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const [, setBootstrap] = useState<PublicBootstrap | null>(null);
  const [workspace, setWorkspace] = useState<WorkspaceData | null>(null);
  const [access, setAccess] = useState<UserAccess | null>(null);
  const [chart, setChart] = useState<any>(null);
  const [publicChart, setPublicChart] = useState<any>(null);
  const [feed, setFeed] = useState<FeedPayload | null>(null);
  const [news, setNews] = useState<NewsPayload | null>(null);
  const [poll, setPoll] = useState<PollPayload | null>(null);
  const [referralLeaderboard, setReferralLeaderboard] = useState<ReferralLeaderboardPayload | null>(null);
  const [referralLeaderboardLoading, setReferralLeaderboardLoading] = useState(false);
  const [referralLeaderboardError, setReferralLeaderboardError] = useState("");
  const [room, setRoom] = useState<ChatHistoryPayload | null>(null);
  const [quote, setQuote] = useState<QuotePayload | null>(null);
  const [publicQuotes, setPublicQuotes] = useState<Record<string, QuotePayload>>({});
  const [tickerTapeQuotes, setTickerTapeQuotes] = useState<Record<string, QuotePayload>>({});
  const [publicInsight, setPublicInsight] = useState<PublicInsightPayload | null>(null);
  const [, setPushStatus] = useState<Record<string, unknown> | null>(null);
  const [mediaStatus, setMediaStatus] = useState<Record<string, unknown> | null>(null);
  const [telegramLink, setTelegramLink] = useState<TelegramLinkSessionResponse | null>(null);
  const [profileNameInput, setProfileNameInput] = useState("");
  const [profileEmailInput, setProfileEmailInput] = useState("");
  const [profileAvatarUrl, setProfileAvatarUrl] = useState("");
  const [profileFile, setProfileFile] = useState<File | null>(null);
  const [profileSaving, setProfileSaving] = useState(false);
  const [educationAnchor, setEducationAnchor] = useState<string | null>(null);

  const [tabs, setTabs] = useState<WorkspaceTab[]>(buildTabs());
  const [activeTab, setActiveTab] = useState(focusedTab || "grafico");

  const [tickerInput, setTickerInput] = useState(queryTicker);
  const [selectedTicker, setSelectedTicker] = useState(queryTicker);
  const deferredTicker = useDeferredValue(selectedTicker);
  const [chartInterval, setChartInterval] = useState("1D");

  const [watchlistQuery, setWatchlistQuery] = useState("");
  const [watchCategory, setWatchCategory] = useState<"Todos" | (typeof CATEGORY_ORDER)[number]>("Todos");
  const [remoteSearchSymbols, setRemoteSearchSymbols] = useState<string[]>([]);
  const [customWatchItems, setCustomWatchItems] = useState<WatchlistItem[]>([]);
  const [activeWatchSymbols, setActiveWatchSymbols] = useState<string[]>(() => PRELOADED_UNIVERSE.map((item) => item.symbol));
  const [workspacePersona, setWorkspacePersona] = useState<WorkspacePersona>("trader");
  const [appLocale, setAppLocale] = useState<AppLocale>(readInitialLocale);
  const isUsLocale = appLocale === "en-US";

  useEffect(() => {
    if (typeof window === "undefined") return;
    window.localStorage.setItem(APP_LOCALE_STORAGE_KEY, appLocale);
    document.documentElement.lang = appLocale === "en-US" ? "en-US" : "pt-BR";
    document.documentElement.dataset.locale = appLocale;
  }, [appLocale]);

  useEffect(() => {
    if ((focusedTab || activeTab) !== "referrals") return;

    let cancelled = false;
    setReferralLeaderboardLoading(true);
    setReferralLeaderboardError("");

    fetchReferralLeaderboard()
      .then((payload) => {
        if (cancelled) return;
        setReferralLeaderboard(payload);
      })
      .catch((err: Error) => {
        if (cancelled) return;
        setReferralLeaderboard(null);
        setReferralLeaderboardError(err.message || "referral_leaderboard_failed");
      })
      .finally(() => {
        if (!cancelled) setReferralLeaderboardLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [activeTab, focusedTab]);

  const publicWatchSymbols = useMemo(
    () => Array.from(new Set([...PRELOADED_UNIVERSE.map((item) => item.symbol), ...customWatchItems.map((item) => item.symbol), selectedTicker])),
    [customWatchItems, selectedTicker],
  );
  const publicTickerTapeSymbols = useMemo(
    () => Array.from(new Set([selectedTicker, ...FIXED_TAPE_SYMBOLS])),
    [selectedTicker],
  );
  const visiblePublicWatchSymbols = useMemo(
    () =>
      Array.from(
        new Set(
          [...PRELOADED_UNIVERSE, ...customWatchItems]
            .filter((item) => activeWatchSymbols.includes(item.symbol))
            .filter((item) => watchCategory === "Todos" || item.category === watchCategory)
            .map((item) => item.symbol),
        ),
    ),
    [activeWatchSymbols, customWatchItems, watchCategory],
  );
  const priorityPublicWatchSymbols = useMemo(() => {
    const activeSet = new Set(activeWatchSymbols);
    const fromCategory = (category: WatchlistItem["category"], limit: number) =>
      PRELOADED_UNIVERSE
        .filter((item) => item.category === category)
        .filter((item) => !activeSet.size || activeSet.has(item.symbol))
        .slice(0, limit)
        .map((item) => item.symbol);

    return Array.from(
      new Set([
        selectedTicker,
        ...FIXED_TAPE_SYMBOLS,
        ...fromCategory("B3", 18),
        ...fromCategory("BDR", 12),
        ...fromCategory("Crypto", 8),
        ...fromCategory("USA", 18),
        ...customWatchItems.map((item) => item.symbol),
      ]),
    );
  }, [activeWatchSymbols, customWatchItems, selectedTicker]);
  const publicTickerTapeKey = publicTickerTapeSymbols.join("|");
  const publicWatchKey = publicWatchSymbols.join("|");
  const priorityPublicWatchKey = priorityPublicWatchSymbols.join("|");
  const visiblePublicWatchKey = visiblePublicWatchSymbols.slice(0, 48).join("|");
  const [tickerTapePaused, setTickerTapePaused] = useState(false);
  const [darkMode, setDarkMode] = useState(false);
  const [settingsTab, setSettingsTab] = useState<SettingsTab>("preferencias");
  const [accountPanel, setAccountPanel] = useState<AccountPanel>("perfil");
  const [notificationOpen, setNotificationOpen] = useState(false);
  const [selectedInstitutionalSectionId, setSelectedInstitutionalSectionId] = useState<string | null>(null);
  const [showMarkers, setShowMarkers] = useState(DEFAULT_CHART_SETTINGS.show_markers);
  const [showZones, setShowZones] = useState(DEFAULT_CHART_SETTINGS.show_zones);
  const [mobileWatchlistOpen, setMobileWatchlistOpen] = useState(false);
  const [mobileInsightsOpen, setMobileInsightsOpen] = useState(false);

  const [postText, setPostText] = useState("");
  const [postSentiment, setPostSentiment] = useState("bullish");
  const [postFile, setPostFile] = useState<File | null>(null);
  const [posting, setPosting] = useState(false);
  const [composerEmojiOpen, setComposerEmojiOpen] = useState(false);
  const [composerGifOpen, setComposerGifOpen] = useState(false);
  const [gifQuery, setGifQuery] = useState("");
  const [predictionOpen, setPredictionOpen] = useState(false);
  const [predictionSymbol, setPredictionSymbol] = useState(queryTicker);
  const [predictionTargetPrice, setPredictionTargetPrice] = useState("");
  const [predictionTargetDate, setPredictionTargetDate] = useState("");
  const [predictionPosting, setPredictionPosting] = useState(false);
  const [pollCommentOpen, setPollCommentOpen] = useState(false);
  const [pollCommentText, setPollCommentText] = useState("");
  const [pollCommentPosting, setPollCommentPosting] = useState(false);
  const [commentDrafts, setCommentDrafts] = useState<Record<number, string>>({});
  const [commentingPostId, setCommentingPostId] = useState<number | null>(null);
  const [postMenuId, setPostMenuId] = useState<number | null>(null);
  const [silencedUserIds, setSilencedUserIds] = useState<number[]>([]);
  const [blockedUsers, setBlockedUsers] = useState<UserListEntry[]>([]);
  const [silencedUsers, setSilencedUsers] = useState<UserListEntry[]>([]);

  const [chatText, setChatText] = useState("");
  const [chatImageUrl, setChatImageUrl] = useState("");
  const [chatStatus, setChatStatus] = useState("offline");

  const socketRef = useRef<WebSocket | null>(null);
  const publicQuotesRef = useRef<Record<string, QuotePayload>>({});
  const tickerTapeQuotesRef = useRef<Record<string, QuotePayload>>({});
  const composerFileInputRef = useRef<HTMLInputElement | null>(null);
  const profileFileInputRef = useRef<HTMLInputElement | null>(null);
  const loginEmailInputRef = useRef<HTMLInputElement | null>(null);
  const pollCommentInputRef = useRef<HTMLTextAreaElement | null>(null);
  const tabListRef = useRef<HTMLDivElement | null>(null);
  const composerCardRef = useRef<HTMLDivElement | null>(null);
  const leftRailRef = useRef<HTMLElement | null>(null);

  useEffect(() => {
    publicQuotesRef.current = publicQuotes;
  }, [publicQuotes]);

  useEffect(() => {
    tickerTapeQuotesRef.current = tickerTapeQuotes;
  }, [tickerTapeQuotes]);

  useEffect(() => {
    const stored =
      queryToken ||
      window.localStorage.getItem("stocknewsbr.token") ||
      process.env.NEXT_PUBLIC_DEFAULT_TOKEN ||
      "";

    if (stored) setToken(stored);
  }, [queryToken]);

  useEffect(() => {
    getBootstrap().then(setBootstrap).catch(() => undefined);
  }, []);

  useEffect(() => {
    const storedPersona = window.localStorage.getItem("stocknewsbr.workspace_persona");
    if (storedPersona === "guiado" || storedPersona === "trader" || storedPersona === "pro") {
      setWorkspacePersona(storedPersona);
      return;
    }
    if (focusedTab) return;
    if (!token) {
      setWorkspacePersona("guiado");
      return;
    }
    setWorkspacePersona("trader");
  }, [focusedTab, token]);

  useEffect(() => {
    window.localStorage.setItem("stocknewsbr.workspace_persona", workspacePersona);
  }, [workspacePersona]);

  useEffect(() => {
    setPredictionSymbol(selectedTicker);
  }, [selectedTicker]);

  useEffect(() => {
    const storedDark = window.localStorage.getItem("stocknewsbr.dark_mode");
    if (storedDark === "1") setDarkMode(true);

    const storedBlocked = window.localStorage.getItem("stocknewsbr.blocked_users");
    if (storedBlocked) {
      try {
        const parsed = JSON.parse(storedBlocked);
        if (Array.isArray(parsed)) setBlockedUsers(parsed);
      } catch {
        // ignore parse issue
      }
    }

    const storedSilenced = window.localStorage.getItem("stocknewsbr.silenced_users");
    if (storedSilenced) {
      try {
        const parsed = JSON.parse(storedSilenced);
        if (Array.isArray(parsed)) setSilencedUsers(parsed);
      } catch {
        // ignore parse issue
      }
    }
  }, []);

  useEffect(() => {
    window.localStorage.setItem("stocknewsbr.dark_mode", darkMode ? "1" : "0");
  }, [darkMode]);

  useEffect(() => {
    window.localStorage.setItem("stocknewsbr.blocked_users", JSON.stringify(blockedUsers));
  }, [blockedUsers]);

  useEffect(() => {
    window.localStorage.setItem("stocknewsbr.silenced_users", JSON.stringify(silencedUsers));
  }, [silencedUsers]);

  useEffect(() => {
    const chartSettings = workspace?.layout?.chart_settings;
    setShowMarkers(chartSettings?.show_markers ?? DEFAULT_CHART_SETTINGS.show_markers);
    setShowZones(chartSettings?.show_zones ?? DEFAULT_CHART_SETTINGS.show_zones);
  }, [workspace?.layout?.chart_settings?.show_markers, workspace?.layout?.chart_settings?.show_zones]);

  useEffect(() => {
    if (focusedTab || (!postMenuId && !composerEmojiOpen && !composerGifOpen)) return;

    function handlePointerDown(event: PointerEvent) {
      const target = event.target as Element | null;
      if (!target) return;
      if (postMenuId && target.closest("[data-post-menu-root]")) return;
      if ((composerEmojiOpen || composerGifOpen) && target.closest("[data-composer-controls]")) return;
      setPostMenuId(null);
      setComposerEmojiOpen(false);
      setComposerGifOpen(false);
    }

    function handleKeyDown(event: KeyboardEvent) {
      if (event.key !== "Escape") return;
      setPostMenuId(null);
      setComposerEmojiOpen(false);
      setComposerGifOpen(false);
    }

    document.addEventListener("pointerdown", handlePointerDown);
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("pointerdown", handlePointerDown);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [composerEmojiOpen, composerGifOpen, focusedTab, postMenuId]);

  useEffect(() => {
    if (!token || !watchlistQuery.trim()) {
      setRemoteSearchSymbols([]);
      return;
    }

    let cancelled = false;
    const timeout = window.setTimeout(() => {
      void searchAssets(token, watchlistQuery.trim())
        .then((symbols) => {
          if (cancelled) return;
          setRemoteSearchSymbols(Array.isArray(symbols) ? symbols : []);
        })
        .catch(() => {
          if (cancelled) return;
          setRemoteSearchSymbols([]);
        });
    }, 240);

    return () => {
      cancelled = true;
      window.clearTimeout(timeout);
    };
  }, [token, watchlistQuery]);

  useEffect(() => {
    if (focusedTab) return;

    const timeout = window.setTimeout(() => {
      leftRailRef.current?.scrollTo({ top: 0, left: 0, behavior: "auto" });
    }, 0);

    return () => window.clearTimeout(timeout);
  }, [focusedTab, loading]);

  useEffect(() => {
    setProfileNameInput(access?.display_name || "");
    setProfileEmailInput(access?.email || "");
    setProfileAvatarUrl(access?.avatar_url || "");
  }, [access?.display_name, access?.email, access?.avatar_url]);

  useEffect(() => {
    let cancelled = false;
    const requestedTicker = deferredTicker;

    getPoll(requestedTicker)
      .then((nextPoll) => {
        if (cancelled) return;
        setPoll(normalizePollPayload(nextPoll, requestedTicker));
      })
      .catch(() => {
        if (cancelled) return;
        setPoll((current) => (sameSymbol(current?.symbol, requestedTicker) ? current : buildFallbackPoll(requestedTicker)));
      });

    return () => {
      cancelled = true;
    };
  }, [deferredTicker]);

  useEffect(() => {
    if (!token) {
      let cancelled = false;
      setLoading(true);
      setAccess(null);
      setWorkspace(null);
      setChart(null);
      setPublicChart((current: any) => (sameSymbol(current?.ticker || current?.summary?.ticker, deferredTicker) ? current : null));
      setFeed(null);
      setRoom(null);
      setPushStatus(null);
      setMediaStatus(null);

      Promise.allSettled([
        getPublicQuote(deferredTicker),
        getPublicInsight(deferredTicker, chartInterval),
        getPublicChart(deferredTicker, chartInterval),
        getNews(null, deferredTicker),
      ])
        .then((results) => {
          if (cancelled) return;

          const [quoteResult, insightResult, chartResult, newsResult] = results;
          const nextQuote = quoteResult.status === "fulfilled" ? quoteResult.value : null;
          const nextInsight = insightResult.status === "fulfilled" ? insightResult.value : null;
          const nextChart = chartResult.status === "fulfilled" ? chartResult.value : null;
          const nextNews = newsResult.status === "fulfilled" ? newsResult.value : null;

          if (nextQuote?.symbol) {
            const normalizedQuoteSymbol = normalizeSymbol(nextQuote.symbol);
            const normalizedQuote = { ...nextQuote, symbol: normalizedQuoteSymbol };
            setPublicQuotes((current) => mergeQuoteState(current, { [normalizedQuoteSymbol]: normalizedQuote }));
            setTickerTapeQuotes((current) => mergeQuoteState(current, { [normalizedQuoteSymbol]: normalizedQuote }));
          }
          setPublicInsight(sameSymbol(nextInsight?.symbol, deferredTicker) ? { ...nextInsight, symbol: deferredTicker } : null);
          setPublicChart((current: any) => {
            const hasNextChart = Boolean(sameChartRequest(nextChart, deferredTicker, chartInterval) && (nextChart?.ohlc?.length || nextChart?.series?.length));
            if (hasNextChart) return { ...nextChart, ticker: deferredTicker };
            if (sameChartRequest(current, deferredTicker, chartInterval) && (current?.ohlc?.length || current?.series?.length)) return current;
            return nextChart;
          });
          setQuote(nextQuote);
          setNews(nextNews);
        })
        .catch((requestError: Error) => {
          if (!cancelled) setError(requestError.message);
        })
        .finally(() => {
          if (!cancelled) setLoading(false);
        });

      getPublicQuotesRobust(publicTickerTapeSymbols, 12, 2)
        .then((nextQuotes) => {
          if (cancelled) return;
          const quoteMap = Object.fromEntries((nextQuotes?.items || []).map((item) => [item.symbol, item]));
          setTickerTapeQuotes((current) => mergeQuoteState(current, quoteMap));
          setPublicQuotes((current) => mergeQuoteState(current, quoteMap));
        })
        .catch(() => {
          // The selected ticker fetch above keeps the main page useful even if some tape quotes time out.
        });

      getPublicQuotesRobust(priorityPublicWatchSymbols, 8, 2)
        .then((nextQuotes) => {
          if (cancelled) return;
          const quoteMap = Object.fromEntries((nextQuotes?.items || []).map((item) => [item.symbol, item]));
          setPublicQuotes((current) => mergeQuoteState(current, quoteMap));
        })
        .catch(() => {
          // Visible cards keep their static labels; the full watchlist load below still gets a chance.
        });

      const fullWatchlistTimer = window.setTimeout(() => {
        getPublicQuotesRobust(publicWatchSymbols, 16, 2)
          .then((nextQuotes) => {
            if (cancelled) return;
            const quoteMap = Object.fromEntries((nextQuotes?.items || []).map((item) => [item.symbol, item]));
            setTickerTapeQuotes((current) => mergeQuoteState(current, quoteMap));
            setPublicQuotes((current) => mergeQuoteState(current, quoteMap));
          })
          .catch(() => undefined);
      }, 900);

      return () => {
        cancelled = true;
        window.clearTimeout(fullWatchlistTimer);
      };
    }
    setPublicQuotes({});
    setPublicInsight(null);

    let cancelled = false;
    setLoading(true);
    setError("");

    Promise.all([
      getAccess(token),
      getWorkspace(token),
      getChart(token, deferredTicker, chartInterval),
      getFeed(token, deferredTicker),
      getNews(token, deferredTicker),
      getChatHistory(token, deferredTicker),
      getQuote(token, deferredTicker),
      getPushStatus(token),
      getMediaStatus(token),
    ])
      .then(([nextAccess, nextWorkspace, nextChart, nextFeed, nextNews, nextRoom, nextQuote, nextPush, nextMedia]) => {
        if (cancelled) return;

        startTransition(() => {
          const nextTabs = buildTabs(nextWorkspace.tabs);
          setAccess(nextAccess);
          setWorkspace(nextWorkspace);
          setChart(nextChart);
          setPublicChart(null);
          setFeed(nextFeed);
          setNews(nextNews);
          setRoom(nextRoom);
          setQuote(nextQuote);
          setPushStatus(nextPush as Record<string, unknown>);
          setMediaStatus(nextMedia as Record<string, unknown>);
          setTabs(nextTabs);

          if (!focusedTab) {
            setActiveTab((current) => (
              TAB_ORDER.includes(current as (typeof TAB_ORDER)[number])
                ? current
                : nextTabs[0]?.id || "grafico"
            ));
          }
        });
      })
      .catch((requestError: Error) => {
        if (!cancelled) setError(requestError.message);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [token, deferredTicker, chartInterval, focusedTab, priorityPublicWatchKey, publicTickerTapeKey, publicWatchKey]);

  useEffect(() => {
    if (token) return;
    const chartReady =
      sameChartRequest(publicChart, deferredTicker, chartInterval) &&
      Boolean(publicChart?.ohlc?.length || publicChart?.series?.length);
    const insightReady = sameSymbol(publicInsight?.symbol, deferredTicker) && Boolean(publicInsight?.score != null || publicInsight?.rsi != null || publicInsight?.trend_bias || publicInsight?.signal);
    if (chartReady && insightReady) return;

    let cancelled = false;
    const retries = [1800, 5200, 9500];
    const timers = retries.map((delay) =>
      window.setTimeout(() => {
        Promise.allSettled([getPublicChart(deferredTicker, chartInterval), getPublicInsight(deferredTicker, chartInterval)])
          .then(([chartResult, insightResult]) => {
            if (cancelled) return;
            if (chartResult.status === "fulfilled" && sameSymbol(chartResult.value?.ticker || chartResult.value?.summary?.ticker, deferredTicker)) {
              setPublicChart((current: any) => {
                if (!(chartResult.value?.ohlc?.length || chartResult.value?.series?.length)) return current;
                if (sameChartRequest(current, deferredTicker, chartInterval) && (current?.ohlc?.length || current?.series?.length)) return current;
                return { ...chartResult.value, ticker: deferredTicker };
              });
            }
            if (insightResult.status === "fulfilled" && sameSymbol(insightResult.value?.symbol, deferredTicker)) {
              setPublicInsight((current) => {
                if (
                  sameSymbol(current?.symbol, deferredTicker) &&
                  (current?.score != null || current?.rsi != null || current?.trend_bias || current?.signal)
                ) {
                  return current;
                }
                return { ...insightResult.value, symbol: deferredTicker };
              });
            }
          })
          .catch(() => undefined);
      }, delay),
    );

    return () => {
      cancelled = true;
      timers.forEach((timer) => window.clearTimeout(timer));
    };
  }, [
    token,
    deferredTicker,
    chartInterval,
    publicChart?.ticker,
    publicChart?.ohlc?.length,
    publicChart?.series?.length,
    publicInsight?.symbol,
    publicInsight?.score,
    publicInsight?.rsi,
    publicInsight?.trend_bias,
    publicInsight?.signal,
  ]);

  useEffect(() => {
    if (token) return;

    const latestTapeQuotes = tickerTapeQuotesRef.current;
    const latestPublicQuotes = publicQuotesRef.current;
    const missingTapeSymbols = publicTickerTapeSymbols.filter((symbol) => {
      const normalized = normalizeSymbol(symbol);
      return !quoteHasMarketValue(
        latestTapeQuotes[symbol] ||
          latestTapeQuotes[normalized] ||
          latestPublicQuotes[symbol] ||
          latestPublicQuotes[normalized],
      );
    });
    if (!missingTapeSymbols.length) return;

    let cancelled = false;
    const timeout = window.setTimeout(() => {
      getPublicQuotesRobust(missingTapeSymbols, 12, 2)
        .then((nextQuotes) => {
          if (cancelled) return;
          const quoteMap = Object.fromEntries((nextQuotes?.items || []).map((item) => [item.symbol, item]));
          setTickerTapeQuotes((current) => mergeQuoteState(current, quoteMap));
          setPublicQuotes((current) => mergeQuoteState(current, quoteMap));
        })
        .catch(() => undefined);
    }, 1200);

    return () => {
      cancelled = true;
      window.clearTimeout(timeout);
    };
  }, [token, publicTickerTapeKey]);

  useEffect(() => {
    if (token) return;
    const latestTapeQuotes = tickerTapeQuotesRef.current;
    const latestPublicQuotes = publicQuotesRef.current;

    const missingSymbols = Array.from(
      new Set([...publicTickerTapeSymbols, ...priorityPublicWatchSymbols, ...visiblePublicWatchSymbols.slice(0, 48)]),
    )
      .filter((symbol) => {
        const normalized = normalizeSymbol(symbol);
        return !quoteHasMarketValue(
          latestTapeQuotes[symbol] ||
            latestTapeQuotes[normalized] ||
            latestPublicQuotes[symbol] ||
            latestPublicQuotes[normalized],
        );
      })
      .slice(0, 48);

    if (!missingSymbols.length) return;

    let cancelled = false;
    const timeout = window.setTimeout(() => {
      getPublicQuotesRobust(missingSymbols, 6, 2)
        .then((nextQuotes) => {
          if (cancelled) return;
          const quoteMap = Object.fromEntries((nextQuotes?.items || []).map((item) => [item.symbol, item]));
          setTickerTapeQuotes((current) => mergeQuoteState(current, quoteMap));
          setPublicQuotes((current) => mergeQuoteState(current, quoteMap));
        })
        .catch(() => {
          // Missing providers can stay as Radar, but they should not break the live board.
        });
    }, 4500);

    return () => {
      cancelled = true;
      window.clearTimeout(timeout);
    };
  }, [token, priorityPublicWatchKey, publicTickerTapeKey, visiblePublicWatchKey]);

  useEffect(() => {
    if (token || !publicWatchSymbols.length) return;

    let cancelled = false;
    let cursor = 0;
    const orderedSymbols = Array.from(new Set([...publicTickerTapeSymbols, ...publicWatchSymbols]));

    const loadNextChunk = () => {
      if (cancelled) return;
      const latestPublicQuotes = publicQuotesRef.current;
      const latestTapeQuotes = tickerTapeQuotesRef.current;
      const missing = orderedSymbols
        .filter((symbol) => !quoteHasMarketValue(
          latestPublicQuotes[symbol] ||
          latestPublicQuotes[normalizeSymbol(symbol)] ||
          latestTapeQuotes[symbol] ||
          latestTapeQuotes[normalizeSymbol(symbol)],
        ));
      if (!missing.length) return;

      const chunk = missing.slice(cursor, cursor + 12);
      cursor = cursor + 12 >= missing.length ? 0 : cursor + 12;
      if (!chunk.length) return;

        getPublicQuotesRobust(chunk, 12, 2)
        .then((nextQuotes) => {
          if (cancelled) return;
          const quoteMap = Object.fromEntries((nextQuotes?.items || []).map((item) => [item.symbol, item]));
          setTickerTapeQuotes((current) => mergeQuoteState(current, quoteMap));
          setPublicQuotes((current) => mergeQuoteState(current, quoteMap));
        })
        .catch(() => undefined);
    };

    loadNextChunk();
    const interval = window.setInterval(loadNextChunk, 12000);

    return () => {
      cancelled = true;
      window.clearInterval(interval);
    };
  }, [token, publicTickerTapeKey, publicWatchKey, publicWatchSymbols, publicTickerTapeSymbols]);

  useEffect(() => {
    if (!token) return;

    const socket = new WebSocket(
      buildWebSocketUrl(`/ws/chat/${encodeURIComponent(deferredTicker)}?token=${encodeURIComponent(token)}`),
    );

    socketRef.current = socket;
    setChatStatus("connecting");

    socket.onopen = () => setChatStatus("live");
    socket.onclose = () => setChatStatus("offline");
    socket.onerror = () => setChatStatus("offline");
    socket.onmessage = (event) => {
      try {
        const payload = JSON.parse(event.data) as {
          type?: string;
          items?: ChatHistoryPayload["items"];
          item?: ChatHistoryPayload["items"][number];
        };

        if (payload.type === "history") {
          startTransition(() => {
            setRoom({ symbol: deferredTicker, items: payload.items || [] });
          });
        } else if (payload.type === "message" && payload.item) {
          startTransition(() => {
            setRoom((current) => ({
              symbol: deferredTicker,
              items: [...(current?.items || []), payload.item!].slice(-60),
            }));
          });
        }
      } catch {
        setChatStatus("offline");
      }
    };

    return () => {
      socket.close();
      socketRef.current = null;
    };
  }, [token, deferredTicker]);

  async function handleLogin() {
    try {
      setLoginError("");
      const payload: AuthFlowResponse = await loginJson(email, password, {
        channel: "web",
        device_id: getBrowserDeviceId(),
        device_label: getBrowserDeviceLabel(),
      });

      if (payload.otp_required && payload.login_token) {
        setPendingLoginToken(payload.login_token);
        setOtpCode("");
        setDebugOtpCode(payload.debug_otp_code || "");
        return;
      }

      if (!payload.access_token) {
        throw new Error(payload.detail || "Falha ao entrar");
      }

      window.localStorage.setItem("stocknewsbr.token", payload.access_token);
      setToken(payload.access_token);
      setPendingLoginToken("");
      setDebugOtpCode("");
    } catch (requestError) {
      setLoginError(requestError instanceof Error ? requestError.message : "Falha ao entrar");
    }
  }

  async function handleVerifyOtp() {
    try {
      setLoginError("");
      const payload = await verifyLoginOtp(pendingLoginToken, otpCode);

      if (!payload.access_token) {
        throw new Error(payload.detail || "Codigo invalido");
      }

      window.localStorage.setItem("stocknewsbr.token", payload.access_token);
      setToken(payload.access_token);
      setPendingLoginToken("");
      setOtpCode("");
      setDebugOtpCode("");
    } catch (requestError) {
      setLoginError(requestError instanceof Error ? requestError.message : "Falha na verificacao");
    }
  }

  async function handleLogout() {
    if (token) {
      try {
        await logoutAuth(token);
      } catch {
        // Best effort local cleanup.
      }
    }

    window.localStorage.removeItem("stocknewsbr.token");
    setToken("");
    setAccess(null);
    setWorkspace(null);
    setPendingLoginToken("");
    setOtpCode("");
    setDebugOtpCode("");
    setTelegramLink(null);
  }

  async function handleTelegramLinkRequest() {
    if (!token) return;

    try {
      setLoginError("");
      const payload = await requestTelegramLink(token, "web");
      setTelegramLink(payload);
    } catch (requestError) {
      setLoginError(requestError instanceof Error ? requestError.message : "Falha ao gerar link do Telegram");
    }
  }

  async function handleSaveProfile() {
    if (!token) return;

    try {
      setProfileSaving(true);
      setLoginError("");

      let nextAvatarUrl = profileAvatarUrl || null;
      if (profileFile) {
        const upload = await uploadMedia(token, profileFile);
        nextAvatarUrl = upload.url;
      }

      const nextAccess = await updateProfile(token, {
        display_name: profileNameInput || null,
        email: profileEmailInput || null,
        avatar_url: nextAvatarUrl,
      });

      window.localStorage.setItem("stocknewsbr.token", token);
      startTransition(() => {
        setAccess(nextAccess);
        setProfileAvatarUrl(nextAccess.avatar_url || "");
        setProfileFile(null);
      });

      if (profileFileInputRef.current) {
        profileFileInputRef.current.value = "";
      }
    } catch (requestError) {
      setLoginError(requestError instanceof Error ? requestError.message : "Falha ao salvar perfil");
    } finally {
      setProfileSaving(false);
    }
  }

  async function persistLayout(
    nextTabs: WorkspaceTab[],
    popouts?: string[],
    pinnedTicker?: string,
    chartSettings?: Partial<ChartSettings>,
  ) {
    if (!token) return;

    try {
      const nextChartSettings = {
        show_markers: chartSettings?.show_markers ?? workspace?.layout?.chart_settings?.show_markers ?? showMarkers,
        show_zones: chartSettings?.show_zones ?? workspace?.layout?.chart_settings?.show_zones ?? showZones,
      };
      const nextLayout = await saveWorkspaceLayout(token, {
        tabs: nextTabs.map((tab) => tab.id),
        pinned_ticker: pinnedTicker ?? selectedTicker,
        opened_popouts: popouts ?? workspace?.layout?.opened_popouts ?? [],
        chart_settings: nextChartSettings,
      });

      startTransition(() => {
        setWorkspace((current) => (current ? { ...current, layout: nextLayout } : current));
      });
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Falha ao salvar layout");
    }
  }

  function scrollTabs(direction: "left" | "right") {
    if (!tabListRef.current) return;
    tabListRef.current.scrollBy({
      left: direction === "left" ? -280 : 280,
      behavior: "smooth",
    });
  }

  function updateChartSetting(key: keyof ChartSettings, value: boolean) {
    if (key === "show_markers") {
      setShowMarkers(value);
    }
    if (key === "show_zones") {
      setShowZones(value);
    }
    void persistLayout(tabs, undefined, undefined, { [key]: value });
  }

  function selectTicker(nextTicker: string) {
    const normalized = resolveTypedSymbol(nextTicker);
    if (!normalized) return;

    startTransition(() => {
      setTickerInput(normalized);
      setSelectedTicker(normalized);
      setChart(null);
      setFeed(null);
      setNews(null);
      setPoll(buildFallbackPoll(normalized));
      setRoom(null);
      setQuote(null);
      setError("");
      if (!focusedTab) setActiveTab("grafico");
    });

    void persistLayout(tabs, undefined, normalized);
  }

  function applyTicker() {
    selectTicker(watchlistQuery.trim() || tickerInput.trim() || "PETR4");
  }

  function handleAddToActiveList() {
    const symbol = resolveTypedSymbol(watchlistQuery.trim() || tickerInput.trim() || selectedTicker);
    if (!symbol) return;

    const baseItem =
      PRELOADED_UNIVERSE.find((item) => item.symbol === symbol) ||
      buildSyntheticSearchCandidate(symbol, watchUniverse.map((item) => item.symbol));

    if (!baseItem) {
      setCustomWatchItems((current) => {
        if (current.some((item) => item.symbol === symbol)) return current;
        return [
          ...current,
          {
            symbol,
            label: symbolName(symbol),
            category: guessCategory(symbol),
          },
        ];
      });
    }

    setActiveWatchSymbols((current) => (current.includes(symbol) ? current : [...current, symbol]));
    selectTicker(symbol);
  }

  function handleRemoveFromActiveList(symbolToRemove = selectedTicker) {
    setActiveWatchSymbols((current) => {
      const next = current.filter((symbol) => symbol !== symbolToRemove);
      if (!next.length) return current;
      if (symbolToRemove === selectedTicker) {
        const fallbackSymbol = next[0];
        startTransition(() => {
          setSelectedTicker(fallbackSymbol);
          setTickerInput(fallbackSymbol);
        });
        void persistLayout(tabs, undefined, fallbackSymbol);
      }
      return next;
    });
  }

  function promptLogin(actionLabel = "usar este recurso") {
    const message = `Faça login para ${actionLabel}.`;
    setLoginError(message);
    setError(message);
    window.scrollTo({ top: 0, behavior: "smooth" });
    leftRailRef.current?.scrollTo({ top: 0, left: 0, behavior: "smooth" });
    window.setTimeout(() => {
      loginEmailInputRef.current?.focus();
    }, 180);
    window.setTimeout(() => {
      window.alert(`${message} Use o bloco "Acesso a plataforma" na coluna esquerda.`);
    }, 0);
  }

  async function handleCreatePost() {
    if (!token) {
      promptLogin("publicar");
      return;
    }
    if (!postText.trim()) return;

    try {
      setPosting(true);
      let imageUrl: string | null = null;

      if (postFile) {
        const upload = await uploadMedia(token, postFile);
        imageUrl = upload.url;
      }

      await createPost(token, selectedTicker, {
        text: postText,
        sentiment: postSentiment,
        image_url: imageUrl,
      });

      const nextFeed = await getFeed(token, selectedTicker);
      startTransition(() => {
        setFeed(nextFeed);
        setPostText("");
        setPostFile(null);
        setComposerEmojiOpen(false);
        setComposerGifOpen(false);
      });
      if (composerFileInputRef.current) composerFileInputRef.current.value = "";
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Falha ao publicar");
    } finally {
      setPosting(false);
    }
  }

  async function refreshFeedState() {
    if (!token) return;
    const nextFeed = await getFeed(token, selectedTicker);
    startTransition(() => {
      setFeed(nextFeed);
    });
  }

  async function handleToggleLike(post: FeedPost) {
    if (!token) {
      promptLogin("curtir posts");
      return;
    }

    try {
      if (post.liked_by_me) {
        await unlikePost(token, post.id);
      } else {
        await likePost(token, post.id);
      }

      await refreshFeedState();
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Falha ao atualizar curtida");
    }
  }

  async function handleComment(postId: number) {
    if (!token) {
      promptLogin("comentar");
      return;
    }

    const text = (commentDrafts[postId] || "").trim();
    if (!text) return;

    try {
      setCommentingPostId(postId);
      await commentOnPost(token, postId, { text });
      await refreshFeedState();
      startTransition(() => {
        setCommentDrafts((current) => ({ ...current, [postId]: "" }));
      });
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Falha ao comentar");
    } finally {
      setCommentingPostId(null);
    }
  }

  async function handleBlockTrader(post: FeedPost) {
    if (!token) {
      promptLogin("bloquear perfis");
      return;
    }

    try {
      await blockUser(token, post.user_id);
      setPostMenuId(null);
      setBlockedUsers((current) => rememberUser(current, buildUserListEntry(post.user_id, post.user, post.user_email, post.user_avatar_url)));
      await refreshFeedState();
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Falha ao bloquear trader");
    }
  }

  async function handleCreatePredictionPost() {
    if (!token) {
      promptLogin("publicar previsão");
      return;
    }

    const symbol = normalizeSymbol(predictionSymbol || selectedTicker);
    const targetPrice = predictionTargetPrice.trim();
    const targetDate = predictionTargetDate.trim();
    if (!symbol || !targetPrice || !targetDate) {
      setError("Preencha símbolo, preço alvo e data alvo da previsão.");
      return;
    }

    try {
      setPredictionPosting(true);
      const predictionSide = postSentiment === "bearish" ? "Urso" : "Touro";
      await createPost(token, symbol, {
        text: `Previsão para ${symbol}: ${predictionSide}, alvo de ${targetPrice} até ${targetDate}.`,
        sentiment: postSentiment,
        image_url: null,
      });
      const nextFeed = await getFeed(token, selectedTicker);
      startTransition(() => {
        setFeed(nextFeed);
        setPredictionOpen(false);
        setPredictionTargetPrice("");
        setPredictionTargetDate("");
      });
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Falha ao publicar previsão");
    } finally {
      setPredictionPosting(false);
    }
  }

  function openPopout(tabId: string) {
    const nextPopouts = [...new Set([...(workspace?.layout?.opened_popouts || []), tabId])];
    void persistLayout(tabs, nextPopouts);
    const tokenQuery = token ? `?token=${encodeURIComponent(token)}&ticker=${encodeURIComponent(selectedTicker)}` : "";
    const features = DETACHABLE_IA_TABS.has(tabId) ? "width=1280,height=900,resizable=yes" : "width=1440,height=960,resizable=yes";
    const targetName = tabId === "grafico" ? `stocknewsbr_panel_${tabId}_${Date.now()}` : `stocknewsbr_panel_${tabId}`;
    window.open(`/panel/${tabId}${tokenQuery}`, targetName, features);
  }

  async function handleMuteTrader(post: FeedPost) {
    if (!token) {
      promptLogin("silenciar perfis");
      return;
    }

    try {
      await muteUser(token, post.user_id);
      setPostMenuId(null);
      setSilencedUserIds((current) => (current.includes(post.user_id) ? current : [...current, post.user_id]));
      setSilencedUsers((current) => rememberUser(current, buildUserListEntry(post.user_id, post.user, post.user_email, post.user_avatar_url)));
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Falha ao silenciar trader");
    }
  }

  async function handleReport(postId: number) {
    if (!token) {
      promptLogin("reportar posts");
      return;
    }

    try {
      await reportPost(token, postId, "community_review");
      setPostMenuId(null);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Falha ao denunciar");
    }
  }

  async function handleReportAndBlock(postId: number, post: FeedPost) {
    if (!token) {
      promptLogin("reportar e bloquear");
      return;
    }

    try {
      await reportPost(token, postId, "report_and_block");
      await blockUser(token, post.user_id);
      setPostMenuId(null);
      setBlockedUsers((current) => rememberUser(current, buildUserListEntry(post.user_id, post.user, post.user_email, post.user_avatar_url)));
      await refreshFeedState();
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Falha ao reportar e bloquear");
    }
  }

  async function handleFollowTrader(targetId: number, isFollowing = false) {
    if (!token) {
      promptLogin("seguir traders");
      return;
    }

    try {
      if (isFollowing) {
        await unfollowUser(token, targetId);
      } else {
        await followUser(token, targetId);
      }
      setPostMenuId(null);
      await refreshFeedState();
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Falha ao atualizar seguidor");
    }
  }

  async function handleDeleteOwnPost(postId: number) {
    if (!token) {
      promptLogin("gerenciar seus posts");
      return;
    }

    try {
      await deletePost(token, postId);
      setPostMenuId(null);
      await refreshFeedState();
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Falha ao excluir post");
    }
  }

  async function handleRepost(post: FeedPost) {
    if (!token) {
      promptLogin("repostar trades");
      return;
    }

    try {
      if (post.reposted_by_me) {
        await unrepostPost(token, post.id);
      } else {
        const quoteText = window.prompt(
          `Repostar ${post.ticker || selectedTicker} com comentário? Opcional.`
        );
        await repostPost(token, post.id, {
          quote_text: quoteText?.trim() || null,
        });
      }

      await refreshFeedState();
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Falha ao repostar trade");
    } finally {
      setPostMenuId(null);
    }
  }

  function appendComposerEmoji(emoji: string) {
    setPostText((current) => `${current}${current ? " " : ""}${emoji}`);
    setComposerEmojiOpen(false);
  }

  function appendComposerGif(term: string) {
    const query = term.trim() || `${selectedTicker} stock market`;
    setPostText((current) => `${current}${current ? " " : ""}[GIF: ${query}]`);
    setComposerGifOpen(false);
  }

  function openYahooGifSearch() {
    const queryText = (gifQuery.trim() || `${selectedTicker} ${symbolName(selectedTicker)} stock market gif`).replace(/\s+/g, " ");
    const query = encodeURIComponent(queryText);
    const opened = window.open(`https://images.search.yahoo.com/search/images?p=${query}&imgty=gif&fr=yfp-t`, "_blank", "noopener,noreferrer");
    if (!opened) {
      setError("Yahoo bloqueou a nova aba de GIF. Libere pop-ups ou abra a busca de GIF novamente.");
    }
  }

  async function handleSendChat() {
    if (!token) {
      promptLogin("participar do chat");
      return;
    }
    if (!chatText.trim()) return;

    try {
      if (socketRef.current && socketRef.current.readyState === WebSocket.OPEN) {
        socketRef.current.send(JSON.stringify({ type: "message", text: chatText, image_url: chatImageUrl || null }));
      } else {
        await postChatMessage(token, selectedTicker, { text: chatText, image_url: chatImageUrl || null });
        const nextRoom = await getChatHistory(token, selectedTicker);
        startTransition(() => {
          setRoom(nextRoom);
        });
      }

      setChatText("");
      setChatImageUrl("");
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Falha no ticker room");
    }
  }

  async function handleVote(option: string) {
    if (!token) {
      promptLogin("votar na poll");
      return;
    }

    try {
      const nextPoll = await votePoll(token, selectedTicker, option);
      startTransition(() => {
        setPoll(normalizePollPayload(nextPoll, selectedTicker));
      });
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Falha ao votar");
    }
  }

  async function handleCreatePollComment() {
    if (!token) {
      promptLogin("comentar na poll");
      return;
    }

    const text = pollCommentText.trim();
    if (!text) return;

    try {
      setPollCommentPosting(true);
      await createPost(token, selectedTicker, {
        text: `[POLL ${selectedTicker}] ${text}`,
        sentiment: postSentiment,
        image_url: null,
      });
      const nextFeed = await getFeed(token, selectedTicker);
      startTransition(() => {
        setFeed(nextFeed);
        setPollCommentText("");
        setPollCommentOpen(false);
      });
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Falha ao comentar na poll");
    } finally {
      setPollCommentPosting(false);
    }
  }

  function togglePredictionBox() {
    setPredictionSymbol(selectedTicker);
    setPredictionOpen((value) => !value);
  }

  function focusPollComposer() {
    setPollCommentOpen(true);
    window.setTimeout(() => {
      pollCommentInputRef.current?.focus();
    }, 80);
  }

  function focusComposer() {
    composerCardRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
    window.setTimeout(() => {
      document.getElementById("snbr-post-textarea")?.focus();
    }, 80);
    if (!token) {
      setLoginError("Faça login para comentar e publicar.");
      leftRailRef.current?.scrollTo({ top: 0, left: 0, behavior: "smooth" });
    }
  }

  const currentTab = focusedTab || activeTab;
  const currentTabs = useMemo(() => (tabs.length ? tabs : buildTabs()), [tabs]);
  const tabsById = useMemo(() => new Map(currentTabs.map((tab) => [tab.id, tab] as const)), [currentTabs]);
  const visibleTabs = useMemo(
    () => TOP_BAR_TAB_IDS.map((id) => tabsById.get(id)).filter(Boolean) as WorkspaceTab[],
    [tabsById],
  );
  const activeChart = useMemo(
    () => {
      const liveChartTicker = normalizeSymbol(String(chart?.ticker || chart?.summary?.ticker || ""));
      const guestChartTicker = normalizeSymbol(String(publicChart?.ticker || publicChart?.summary?.ticker || ""));
      const liveChart = liveChartTicker === selectedTicker ? chart : null;
      const guestChart = guestChartTicker === selectedTicker ? publicChart : null;
      return liveChart || guestChart;
    },
    [chart, publicChart, selectedTicker],
  );
  const activeFeed = useMemo(() => (feed?.symbol && normalizeSymbol(feed.symbol) === selectedTicker ? feed : null), [feed, selectedTicker]);
  const activeNews = useMemo(
    () => (news?.symbol && normalizeSymbol(news.symbol) === selectedTicker ? news : null),
    [news, selectedTicker],
  );
  const activeRoom = useMemo(() => (room?.symbol === selectedTicker ? room : null), [room, selectedTicker]);
  const activeQuote = useMemo(() => {
    if (!quote?.symbol || normalizeSymbol(quote.symbol) !== selectedTicker) return null;
    return { ...quote, symbol: selectedTicker };
  }, [quote, selectedTicker]);
  const roomItems = activeRoom?.items || [];
  const feedPosts = activeFeed?.posts || [];
  const discussionPostsRaw = useMemo(() => feedPosts, [feedPosts]);
  const discussionPosts = useMemo(
    () => discussionPostsRaw.filter((post) => !silencedUserIds.includes(post.user_id)),
    [discussionPostsRaw, silencedUserIds],
  );
  const featuredDiscussionPosts = useMemo(() => {
    const backendFeatured = activeFeed?.featured_posts || [];
    const source = backendFeatured.length ? backendFeatured : discussionPosts;
    return source.filter((post) => !silencedUserIds.includes(post.user_id));
  }, [activeFeed?.featured_posts, discussionPosts, silencedUserIds]);
  const newsStateText = typeof activeNews?.message === "string" && activeNews.message.trim()
    ? localizeUiText(activeNews.message, appLocale, selectedTicker)
    : null;
  const discussionStateText = typeof activeFeed?.discussion_state?.message === "string" && activeFeed.discussion_state.message.trim()
    ? localizeUiText(activeFeed.discussion_state.message, appLocale, selectedTicker)
    : null;
  const pollDiscussionPosts = useMemo(
    () => discussionPosts.filter((post) => String(post.text || "").startsWith(`[POLL ${selectedTicker}]`)),
    [discussionPosts, selectedTicker],
  );
  const rankingRows = workspace?.ranking || [];
  const radarRows = workspace?.top_signals || [];
  const mergedQuoteMap = useMemo(
    () => mergeQuoteState(publicQuotes, tickerTapeQuotes),
    [publicQuotes, tickerTapeQuotes],
  );
  const watchUniverse = useMemo(
    () => buildWatchlist(rankingRows, radarRows, activeQuote, mergedQuoteMap, publicInsight, selectedTicker, customWatchItems),
    [rankingRows, radarRows, activeQuote, mergedQuoteMap, publicInsight, selectedTicker, customWatchItems],
  );
  const activeWatchlist = useMemo(() => {
    const liveWatchlist = buildWatchlist(
      rankingRows,
      radarRows,
      activeQuote,
      mergedQuoteMap,
      publicInsight,
      selectedTicker,
      customWatchItems,
    );
    const activeSet = new Set(activeWatchSymbols.length ? activeWatchSymbols : PRELOADED_UNIVERSE.map((item) => item.symbol));
    const bySymbol = new Map(liveWatchlist.map((item) => [item.symbol, item]));

    for (const item of [...PRELOADED_UNIVERSE, ...customWatchItems]) {
      if (!activeSet.has(item.symbol)) continue;
      if (!bySymbol.has(item.symbol)) {
        bySymbol.set(item.symbol, { ...item });
      }
    }

    return Array.from(bySymbol.values()).filter((item) => activeSet.has(item.symbol));
  }, [
    rankingRows,
    radarRows,
    activeQuote,
    mergedQuoteMap,
    publicInsight,
    selectedTicker,
    customWatchItems,
    activeWatchSymbols,
  ]);
  const filteredActiveWatchlist = useMemo(
    () => activeWatchlist.filter((item) => watchCategory === "Todos" || item.category === watchCategory),
    [activeWatchlist, watchCategory],
  );
  const filteredUniverse = useMemo(
    () =>
      watchUniverse.filter((item) => {
        if (!watchlistQuery.trim()) return true;
        const haystack = `${item.symbol} ${item.label} ${item.category}`.toLowerCase();
        return haystack.includes(watchlistQuery.trim().toLowerCase());
      }),
    [watchUniverse, watchlistQuery],
  );
  const syntheticSearchCandidate = useMemo(
    () => buildSyntheticSearchCandidate(watchlistQuery, watchUniverse.map((item) => item.symbol)),
    [watchlistQuery, watchUniverse],
  );
  const remoteSearchItems = useMemo(
    () =>
      remoteSearchSymbols.map((symbol) => {
        const normalized = normalizeSymbol(symbol);
        return watchUniverse.find((item) => item.symbol === normalized) || {
          symbol: normalized,
          label: symbolName(normalized),
          category: guessCategory(normalized),
          price: null,
          changePct: null,
          score: null,
          trend: normalized.endsWith("USD") ? "Cripto" : "Busca",
        };
      }),
    [remoteSearchSymbols, watchUniverse],
  );
  const groupedActiveWatchlist = useMemo(
    () =>
      CATEGORY_ORDER.map((category) => ({
        category,
        items: filteredActiveWatchlist.filter((item) => item.category === category),
      })).filter((group) => group.items.length),
    [filteredActiveWatchlist],
  );
  const searchResults = useMemo(
    () =>
      [...(syntheticSearchCandidate ? [syntheticSearchCandidate] : []), ...remoteSearchItems, ...filteredUniverse]
        .filter((item, index, items) => index === items.findIndex((candidate) => candidate.symbol === item.symbol))
        .slice(0, 24),
    [syntheticSearchCandidate, remoteSearchItems, filteredUniverse],
  );
  const currentRanking = useMemo(() => rankingRows.find((item) => item.symbol === selectedTicker), [rankingRows, selectedTicker]);
  const currentWatchItem = useMemo(() => watchUniverse.find((item) => item.symbol === selectedTicker), [watchUniverse, selectedTicker]);
  const currentPublicQuote = resolveQuoteForSymbol(selectedTicker, publicQuotes, tickerTapeQuotes);
  const displayQuote = quoteHasMarketValue(currentPublicQuote) ? currentPublicQuote : activeQuote;
  const currentPublicInsight = normalizeSymbol(publicInsight?.symbol || "") === selectedTicker ? publicInsight : null;
  useEffect(() => {
    if (token || quoteHasMarketValue(currentPublicQuote)) return;

    let cancelled = false;
    const retryDelays = [500, 1800, 4200, 8000];
    const timers = retryDelays.map((delay) =>
      window.setTimeout(() => {
        getPublicQuote(deferredTicker)
          .then((nextQuote) => {
            if (cancelled || normalizeSymbol(nextQuote?.symbol || "") !== deferredTicker) return;
            const normalizedQuote = { ...nextQuote, symbol: deferredTicker };
            setQuote(normalizedQuote);
            setPublicQuotes((current) => mergeQuoteState(current, { [deferredTicker]: normalizedQuote }));
            setTickerTapeQuotes((current) => mergeQuoteState(current, { [deferredTicker]: normalizedQuote }));
          })
          .catch(() => undefined);
      }, delay),
    );

    return () => {
      cancelled = true;
      timers.forEach((timer) => window.clearTimeout(timer));
    };
  }, [token, deferredTicker, currentPublicQuote?.price, currentPublicQuote?.change, currentPublicQuote?.change_pct, currentPublicQuote?.volume]);
  const currentDerivedScore = useMemo(
    () =>
      derivePublicScore({
        changePct: displayQuote?.change_pct ?? null,
        rsi: currentPublicInsight?.rsi ?? (currentRanking?.rsi != null ? Number(currentRanking.rsi) : null),
        trend: activeChart?.summary?.trend_bias || currentPublicInsight?.trend_bias || currentPublicInsight?.signal || currentRanking?.trend || null,
        volume: displayQuote?.volume ?? null,
      }),
    [
      activeChart?.summary?.trend_bias,
      currentPublicInsight?.rsi,
      currentPublicInsight?.signal,
      currentPublicInsight?.trend_bias,
      currentRanking?.rsi,
      currentRanking?.trend,
      displayQuote?.change_pct,
      displayQuote?.volume,
    ],
  );
  const derivedPublicInsight = useMemo(() => {
    if (currentPublicInsight) return currentPublicInsight;

    const derivedTrend =
      activeChart?.summary?.trend_bias ||
      currentRanking?.trend ||
      (displayQuote?.change_pct != null
        ? displayQuote.change_pct > 0
          ? "alta"
          : displayQuote.change_pct < 0
            ? "baixa"
            : "lateral"
        : null);
    const derivedScore = usableScore(
      currentRanking?.score,
      currentDerivedScore,
      derivePublicScore({
        changePct: displayQuote?.change_pct ?? currentPublicQuote?.change_pct ?? null,
        rsi: currentRanking?.rsi != null ? Number(currentRanking.rsi) : null,
        trend: derivedTrend,
        volume: displayQuote?.volume ?? null,
      }),
    );

    if (!quoteHasMarketValue(displayQuote) && derivedScore == null && !derivedTrend) return null;

    return {
      symbol: selectedTicker,
      score: derivedScore ?? currentDerivedScore ?? null,
      rsi: currentRanking?.rsi != null ? Number(currentRanking.rsi) : null,
      trend_bias: derivedTrend || null,
      signal:
        derivedTrend && /alta|bull|compra/i.test(String(derivedTrend))
          ? "BUY"
          : derivedTrend && /baixa|bear|venda/i.test(String(derivedTrend))
            ? "SELL"
            : "HOLD",
    };
  }, [
    activeChart?.summary?.trend_bias,
    currentDerivedScore,
    currentPublicInsight,
    currentRanking?.rsi,
    currentRanking?.score,
    currentRanking?.trend,
    displayQuote,
    selectedTicker,
  ]);
  const chartForDisplay = useMemo(() => {
    const hasLiveSeries = Boolean(activeChart?.ohlc?.length || activeChart?.series?.length);
    const fallbackChart = buildQuoteFallbackChart(
      selectedTicker,
      chartInterval,
      displayQuote,
      activeChart?.summary?.trend_bias ||
        currentRanking?.trend ||
        derivedPublicInsight?.trend_bias ||
        derivedPublicInsight?.signal ||
        null,
    );

    if (!hasLiveSeries) return fallbackChart;
    if (!activeChart) return fallbackChart;

    return {
      ...activeChart,
      markers: activeChart.markers?.length ? activeChart.markers : fallbackChart?.markers || [],
      zones: activeChart.zones?.length ? activeChart.zones : fallbackChart?.zones || [],
      summary: {
        ...(fallbackChart?.summary || {}),
        ...(activeChart.summary || {}),
      },
    };
  }, [
    activeChart,
    chartInterval,
    currentRanking?.trend,
    derivedPublicInsight?.signal,
    derivedPublicInsight?.trend_bias,
    displayQuote?.change,
    displayQuote?.change_pct,
    displayQuote?.price,
    displayQuote?.volume,
    selectedTicker,
  ]);
  const chartMovement = useMemo(
    () => deriveChartMovement(activeChart || chartForDisplay),
    [activeChart, chartForDisplay],
  );
  const chartLatestEpoch = useMemo(
    () => chartLatestAlertEpoch(activeChart || chartForDisplay),
    [activeChart, chartForDisplay],
  );
  const effectiveAiScore = useMemo(
    () => usableScore(derivedPublicInsight?.score, currentRanking?.score, currentDerivedScore),
    [derivedPublicInsight?.score, currentRanking?.score, currentDerivedScore],
  );
  const priceMovementValue = firstNonZeroFiniteNumber(displayQuote?.change, chartMovement?.change) ?? (displayQuote?.change ?? null);
  const priceMovementPercent = firstNonZeroFiniteNumber(displayQuote?.change_pct, chartMovement?.changePct) ?? (displayQuote?.change_pct ?? null);
  const symbolLabel = currentWatchItem?.label || symbolName(selectedTicker);
  const currentAiKey = AI_TOOL_TAB_MAP[currentTab as keyof typeof AI_TOOL_TAB_MAP];
  const currentAiRows: AiToolRow[] = useMemo(
    () => (currentAiKey ? workspace?.ai_tools?.[currentAiKey] : undefined) || [],
    [currentAiKey, workspace?.ai_tools],
  );
  const newsRows = useMemo(
    () =>
      ((activeNews?.items || []) as NewsItem[])
        .filter((item) => newsMatchesSelectedTicker(item, selectedTicker))
        .map((item, index) => {
        const publishedAt = item.published_at ? Date.parse(item.published_at) : Number.NaN;
        const age = Number.isFinite(publishedAt) ? formatRelativeTime(Math.floor(publishedAt / 1000), appLocale) : (isUsLocale ? "now" : "agora");
        const labels = Array.isArray(item.labels) ? item.labels.filter(Boolean) : [];
        const entities = Array.isArray(item.entities) ? item.entities.filter(Boolean) : [];
        const impact = localizeImpactLabel(item.impact_label || item.impact || "Neutro", appLocale);
        const title = displayNewsTitle(item, selectedTicker, appLocale);
        const cardSummary = displayNewsBody(item, selectedTicker, appLocale);
        const traderTakeaway = localizeUiText(item.trader_takeaway || "", appLocale, selectedTicker);
        const whyItMatters = localizeUiText(item.why_it_matters || "", appLocale, selectedTicker);
        const marketContext = localizeUiText(item.market_context || "", appLocale, selectedTicker);
        const sector = localizeUiText(item.sector || "", appLocale, selectedTicker);
        const industry = localizeUiText(item.industry || "", appLocale, selectedTicker);
        const labelsForLocale = labels.map((label) => localizeUiText(label, appLocale, selectedTicker));
        const quality = isUsLocale ? (item.useful !== false ? "Useful" : "Noise") : (item.useful !== false ? "Útil" : "Ruído");
        return {
          id: item.id || `${selectedTicker}-${index}`,
          symbol: item.ticker || selectedTicker,
          title,
          source: item.source || "Yahoo Finance",
          age,
          sector,
          industry,
          labels: labelsForLocale,
          entities,
          impact,
          quality,
          useful: item.useful !== false,
          relevanceScore: item.relevance_score,
          rankingScore: item.ranking_score,
          confidenceScore: item.confidence_score,
          sameStoryCount: item.same_story_count || 1,
          sourceCount: item.source_count || 1,
          ambiguityScore: item.ambiguity_score ?? null,
          ambiguityFlags: item.ambiguity_flags || [],
          traderTakeaway,
          cardSummary,
          whyItMatters,
          editorial: localizeUiText(item.editorial || "", appLocale, selectedTicker),
          marketContext,
          impactReason: localizeUiText(item.impact_reason || "", appLocale, selectedTicker),
          url: item.url || null,
        };
      }),
    [activeNews?.items, selectedTicker, appLocale, isUsLocale],
  );
  const stats = useMemo(() => [
    { label: isUsLocale ? "Price" : "Preço", value: formatLocalePrice(displayQuote?.price, appLocale) },
    { label: isUsLocale ? "Change" : "Variação", value: formatSignedPercent(displayQuote?.change_pct) },
    { label: "Volume", value: formatCompact(displayQuote?.volume) },
    {
      label: isUsLocale ? "AI Score" : "Score IA",
      value:
        effectiveAiScore != null
          ? Number(effectiveAiScore).toFixed(1)
          : "n/a",
    },
    {
      label: "RSI",
      value:
        currentRanking?.rsi != null
          ? String(currentRanking.rsi)
          : derivedPublicInsight?.rsi != null
            ? String(derivedPublicInsight.rsi)
            : "n/a",
    },
    {
      label: "Bias",
      value: localizeUiText(chartForDisplay?.summary?.trend_bias || currentRanking?.trend || derivedPublicInsight?.trend_bias || derivedPublicInsight?.signal || "n/a", appLocale, selectedTicker),
    },
  ], [
    displayQuote?.price,
    displayQuote?.change_pct,
    displayQuote?.volume,
    effectiveAiScore,
    currentRanking?.rsi,
    currentRanking?.trend,
    chartForDisplay?.summary?.trend_bias,
    derivedPublicInsight?.score,
    derivedPublicInsight?.rsi,
    derivedPublicInsight?.trend_bias,
    derivedPublicInsight?.signal,
    chartLatestEpoch,
    isUsLocale,
    appLocale,
    selectedTicker,
  ]);
  const tapeItems = useMemo(
    () =>
      FIXED_TAPE_SYMBOLS.map((symbol) => {
      const normalizedSymbol = normalizeSymbol(symbol);
      const base = watchUniverse.find((item) => item.symbol === normalizedSymbol) || {
        symbol: normalizedSymbol,
        label: symbolName(normalizedSymbol),
        category: guessCategory(normalizedSymbol),
      };
      const publicQuote = resolveQuoteForSymbol(normalizedSymbol, publicQuotes, tickerTapeQuotes);
      const derivedChangePct = publicQuote ? publicQuote.change_pct ?? deriveChangePercent(publicQuote.change ?? null, publicQuote.price ?? null) : null;
      return publicQuote
        ? {
            ...base,
            symbol: normalizedSymbol,
            price: publicQuote.price ?? base.price ?? null,
            change: publicQuote.change ?? base.change ?? null,
            changePct: derivedChangePct ?? base.changePct ?? null,
            score: base.score ?? derivePublicScore({
              changePct: derivedChangePct ?? null,
              rsi: base.rsi ?? null,
              trend: base.trend || (derivedChangePct != null ? (derivedChangePct >= 0 ? "alta" : "baixa") : null),
              volume: publicQuote.volume ?? null,
            }),
            trend: base.trend || (derivedChangePct != null ? (derivedChangePct >= 0 ? "alta" : "baixa") : null),
          }
        : base;
    }),
    [watchUniverse, publicQuotes, tickerTapeQuotes],
  );
  const toolCandidatesSource = useMemo(() => {
    const bySymbol = new Map<string, any>();
    const addCandidate = (row: any) => {
      const symbol = normalizeSymbol(String(row?.symbol || row?.ticker || ""));
      if (!symbol) return;
      const quote = resolveQuoteForSymbol(symbol, publicQuotes, tickerTapeQuotes);
      const watchItem = watchUniverse.find((item) => item.symbol === symbol);
      const existing = bySymbol.get(symbol) || {};
      const score = usableScore(row?.score, existing.score, watchItem?.score);
      bySymbol.set(symbol, {
        ...watchItem,
        ...existing,
        ...row,
        symbol,
        ticker: symbol,
        label: row?.label || row?.name || watchItem?.label || symbolName(symbol),
        score,
        trend: row?.trend || existing.trend || watchItem?.trend || "monitorando",
        price: firstFiniteNumber(row?.price, existing.price, watchItem?.price, quote?.price),
        changePct: firstFiniteNumber(row?.changePct, row?.change_pct, existing.changePct, watchItem?.changePct, quote?.change_pct),
        rsi: firstFiniteNumber(row?.rsi, existing.rsi, watchItem?.rsi),
        volume: firstFiniteNumber(row?.volume, existing.volume, watchItem?.volume, quote?.volume),
        timestamp: normalizeAlertEpoch(row?.timestamp ?? row?.detected_at ?? row?.updated_at ?? row?.last_seen_at ?? row?.created_at ?? existing.timestamp),
      });
    };

    rankingRows.forEach(addCandidate);
    radarRows.forEach(addCandidate);
    watchUniverse.forEach(addCandidate);
    PRELOADED_UNIVERSE.forEach(addCandidate);
    customWatchItems.forEach(addCandidate);

    return Array.from(bySymbol.values());
  }, [
    rankingRows,
    radarRows,
    watchUniverse,
    publicQuotes,
    tickerTapeQuotes,
    customWatchItems,
    selectedTicker,
    symbolLabel,
    effectiveAiScore,
    chartForDisplay?.summary?.trend_bias,
    derivedPublicInsight?.trend_bias,
    derivedPublicInsight?.signal,
    derivedPublicInsight?.rsi,
    currentRanking?.trend,
    currentRanking?.rsi,
    displayQuote?.price,
    displayQuote?.volume,
    priceMovementPercent,
    chartLatestEpoch,
  ]);
  const toolCandidates = useMemo(
    () =>
      [...toolCandidatesSource]
        .filter((row) => scoreToolCandidateForTab(currentTab, row) > -999)
        .sort((a, b) => scoreToolCandidateForTab(currentTab, b) - scoreToolCandidateForTab(currentTab, a))
        .slice(0, 80)
        .map((row, index) => {
        const symbol = normalizeSymbol(String((row as any).symbol || (row as any).ticker || selectedTicker));
        return {
          id: `${symbol}-${index}`,
          symbol,
          label: symbolName(symbol),
          score: (row as any).score != null ? Number((row as any).score) : null,
          trend: (row as any).trend || "monitorando",
          price: (row as any).price != null ? Number((row as any).price) : null,
          changePct: (row as any).changePct != null ? Number((row as any).changePct) : null,
          rsi: (row as any).rsi != null ? Number((row as any).rsi) : null,
          volume: (row as any).volume != null ? Number((row as any).volume) : null,
          timestamp: normalizeAlertEpoch((row as any).timestamp ?? (row as any).detected_at ?? (row as any).updated_at ?? (row as any).last_seen_at ?? (row as any).created_at),
        };
      }),
    [toolCandidatesSource, selectedTicker, currentTab],
  );
  const expandedToolCandidates = useMemo(
    () =>
      Array.from({ length: 20 }, (_, index) => {
        const fallback = toolCandidates[index % Math.max(toolCandidates.length, 1)] || {
          id: `${selectedTicker}-${index}`,
          symbol: selectedTicker,
          label: symbolLabel,
          score: currentRanking?.score != null ? Number(currentRanking.score) : null,
          trend: currentRanking?.trend || activeChart?.summary?.trend_bias || "monitorando",
          price: displayQuote?.price ?? null,
          changePct: displayQuote?.change_pct ?? null,
          rsi: currentRanking?.rsi != null ? Number(currentRanking.rsi) : null,
          volume: displayQuote?.volume ?? null,
          timestamp: chartLatestEpoch,
        };
        return { ...fallback, id: `${fallback.symbol}-${index}` };
      }),
    [toolCandidates, selectedTicker, symbolLabel, currentRanking?.score, currentRanking?.trend, currentRanking?.rsi, activeChart?.summary?.trend_bias, displayQuote?.price, displayQuote?.change_pct, displayQuote?.volume, chartLatestEpoch],
  );
  const visibleAiRows = useMemo<AiToolRow[]>(() => {
    if (!currentAiKey) return [];

    if (currentAiRows.length) {
      const backendRows = currentAiRows.map((row, index) => {
        const symbol = normalizeSymbol(String((row as any).ticker || (row as any).symbol || selectedTicker));
        const quote = resolveQuoteForSymbol(symbol, publicQuotes, tickerTapeQuotes);
        const changePct = row.change_pct ?? (row as any).changePct ?? quote?.change_pct ?? null;
        const trend =
          row.state ||
          row.signal ||
          (symbol === selectedTicker ? derivedPublicInsight?.trend_bias || derivedPublicInsight?.signal : null) ||
          activeChart?.summary?.trend_bias ||
          null;
        const rsi = row.rsi ?? (symbol === selectedTicker ? derivedPublicInsight?.rsi : null) ?? derivePublicRsi(changePct, trend);
        const resolvedVolume = firstFiniteNumber(row.volume, (row as any).volume_24h, quote?.volume);
        const score = usableScore(
          row.score,
          symbol === selectedTicker ? derivedPublicInsight?.score : null,
          derivePublicScore({
            changePct,
            rsi,
            trend,
            volume: resolvedVolume,
          }),
        ) ?? 5;
        const rvol = row.rel_volume ?? (row as any).rvol ?? deriveRelativeVolume(resolvedVolume);
        const adx = row.adx ?? deriveAdx(changePct, rsi, trend);
        const atrPct = row.atr_pct ?? deriveAtrPct(changePct, rsi, resolvedVolume);
        const rowScore = usableScore(
          row.score,
          symbol === selectedTicker ? derivedPublicInsight?.score : null,
          score,
        ) ?? 5;
        const narrative = buildPublicToolNarrative({
          tabId: currentTab,
          symbol,
          score: Number(rowScore),
          changePct,
          price: row.price ?? quote?.price ?? null,
          volume: resolvedVolume,
          rsi,
          rvol,
          adx,
          atrPct,
          trend: trend || "monitorando",
        });
        const lensMetrics = buildToolLensMetrics({
          tabId: currentTab,
          score: Number(rowScore),
          changePct,
          volume: resolvedVolume,
          rvol,
          rsi,
          adx,
          atr_pct: atrPct,
          trend: trend || "monitorando",
        });
        const rowUpdatedAt =
          normalizeAlertTimestamp(row.detected_at ?? row.updated_at ?? row.last_seen_at ?? (row as any).timestamp ?? (row as any).created_at) ||
          (symbol === selectedTicker ? normalizeAlertTimestamp(chartLatestEpoch) : undefined);
        const rowLastSeenAt =
          normalizeAlertTimestamp(row.last_seen_at ?? row.updated_at ?? (row as any).timestamp ?? (row as any).created_at) ||
          rowUpdatedAt;
        const backendSignal = String(row.signal || "").trim();
        const backendState = String(row.state || "").trim();
        const backendComment = String(row.ai_comment || "").trim();
        const backendTrigger = String(row.trigger || "").trim();
        const backendInvalidation = String(row.invalidation || "").trim();

        return {
          ...row,
          ticker: symbol,
          name: row.name || symbolName(symbol),
          tool: currentAiKey,
          score: Number(rowScore),
          signal: backendSignal || narrative.signal,
          state: backendState || narrative.state,
          confidence: row.confidence ?? Math.round(Math.max(45, Math.min(95, Number(rowScore) * 10))),
          price: row.price ?? quote?.price ?? null,
          change_pct: changePct,
          volume: resolvedVolume,
          rsi,
          rel_volume: rvol,
          adx,
          atr_pct: atrPct,
          metrics: { ...lensMetrics, ...(row.metrics || {}) },
          ai_comment: backendComment || narrative.ai_comment,
          trigger: backendTrigger || narrative.trigger,
          invalidation: backendInvalidation || narrative.invalidation,
          updated_at: rowUpdatedAt ?? undefined,
          detected_at: rowUpdatedAt ?? undefined,
          last_seen_at: rowLastSeenAt ?? undefined,
        };
      });
      const backendSymbols = new Set(backendRows.map((row) => normalizeSymbol(String(row.ticker || ""))));
      const extraRows = expandedToolCandidates
        .filter((item) => !backendSymbols.has(normalizeSymbol(item.symbol)))
        .slice(0, 20)
        .map((item) => {
          const normalizedItemSymbol = normalizeSymbol(item.symbol);
          const quote = resolveQuoteForSymbol(normalizedItemSymbol, publicQuotes, tickerTapeQuotes);
          const watchItem = watchUniverse.find((candidate) => candidate.symbol === normalizedItemSymbol);
          const changePct = quote?.change_pct ?? watchItem?.changePct ?? item.changePct ?? null;
          const trend = item.trend || (normalizedItemSymbol === selectedTicker ? derivedPublicInsight?.trend_bias || derivedPublicInsight?.signal : null) || chartForDisplay?.summary?.trend_bias || "monitorando";
          const rsi = item.rsi ?? (normalizedItemSymbol === selectedTicker ? derivedPublicInsight?.rsi : null) ?? derivePublicRsi(changePct, trend);
          const resolvedVolume = firstFiniteNumber(quote?.volume, item.volume, watchItem?.volume);
          const rvol = deriveRelativeVolume(resolvedVolume);
          const adx = deriveAdx(changePct, rsi, trend);
          const atrPct = deriveAtrPct(changePct, rsi, resolvedVolume);
          const score =
            usableScore(
              item.score,
              normalizedItemSymbol === selectedTicker ? derivedPublicInsight?.score : null,
              derivePublicScore({
                changePct,
                rsi,
                trend,
                volume: resolvedVolume,
              }),
            ) ?? 5;
          const narrative = buildPublicToolNarrative({
            tabId: currentTab,
            symbol: normalizedItemSymbol,
            score: Number(score),
            changePct,
            price: quote?.price ?? item.price ?? watchItem?.price ?? null,
            volume: resolvedVolume,
            rsi,
            rvol,
            adx,
            atrPct,
            trend,
          });
          const lensMetrics = buildToolLensMetrics({
            tabId: currentTab,
            score: Number(score),
            changePct,
            volume: resolvedVolume,
            rvol,
            rsi,
            adx,
            atr_pct: atrPct,
            trend,
          });

          return {
            ticker: normalizedItemSymbol,
            name: item.label || symbolName(normalizedItemSymbol),
            tool: currentAiKey,
            score: Number(score),
            signal: narrative.signal,
            state: narrative.state,
            confidence: Math.round(Math.max(45, Math.min(95, Number(score) * 10))),
            price: quote?.price ?? item.price ?? watchItem?.price ?? null,
            change_pct: changePct,
            volume: resolvedVolume,
            rel_volume: rvol,
            rsi,
            adx,
            atr_pct: atrPct,
            metrics: lensMetrics,
            ai_comment: narrative.ai_comment,
            trigger: narrative.trigger,
            invalidation: narrative.invalidation,
            updated_at:
              normalizeAlertTimestamp(item.timestamp) ||
              (normalizedItemSymbol === selectedTicker ? normalizeAlertTimestamp(chartLatestEpoch) ?? undefined : undefined),
            detected_at:
              normalizeAlertTimestamp(item.timestamp) ||
              (normalizedItemSymbol === selectedTicker ? normalizeAlertTimestamp(chartLatestEpoch) ?? undefined : undefined),
          } satisfies AiToolRow;
        });

      const sortedRows = [...backendRows, ...extraRows].sort((a, b) => (
        scoreToolCandidateForTab(currentTab, {
          symbol: b.ticker,
          changePct: b.change_pct,
          score: b.score,
          volume: b.volume,
          rvol: b.rel_volume ?? (b as any).rvol,
          rsi: b.rsi,
          adx: b.adx,
          atr_pct: b.atr_pct,
          trend: b.state || b.signal,
        }) -
        scoreToolCandidateForTab(currentTab, {
          symbol: a.ticker,
          changePct: a.change_pct,
          score: a.score,
          volume: a.volume,
          rvol: a.rel_volume ?? (a as any).rvol,
          rsi: a.rsi,
          adx: a.adx,
          atr_pct: a.atr_pct,
          trend: a.state || a.signal,
        })
      ));

      return selectDiverseByLens(sortedRows, currentTab, 20, (row) => row.ticker);
    }

    const sourceCandidates = expandedToolCandidates
      .map((item) => {
        const normalizedItemSymbol = normalizeSymbol(item.symbol);
        const quote = resolveQuoteForSymbol(normalizedItemSymbol, publicQuotes, tickerTapeQuotes);
        const watchItem = watchUniverse.find((candidate) => candidate.symbol === normalizedItemSymbol);
        const changePct = quote?.change_pct ?? watchItem?.changePct ?? null;
        const trend = item.trend || (normalizedItemSymbol === selectedTicker ? derivedPublicInsight?.trend_bias || derivedPublicInsight?.signal : null) || chartForDisplay?.summary?.trend_bias || "monitorando";
        const rsi = item.rsi ?? (normalizedItemSymbol === selectedTicker ? derivedPublicInsight?.rsi : null) ?? derivePublicRsi(changePct, trend);
        const resolvedVolume = firstFiniteNumber(quote?.volume, item.volume, watchItem?.volume);
        const rvol = deriveRelativeVolume(resolvedVolume);
        const adx = deriveAdx(changePct, rsi, trend);
        const atrPct = deriveAtrPct(changePct, rsi, resolvedVolume);
        const score =
          usableScore(
            item.score,
            normalizedItemSymbol === selectedTicker ? derivedPublicInsight?.score : null,
            derivePublicScore({
              changePct,
              rsi,
              trend,
              volume: resolvedVolume,
            }),
          ) ?? 5;

        return {
          ...item,
          symbol: normalizedItemSymbol,
          quote,
          watchItem,
          changePct,
          rsi,
          trend,
          score: Number(score),
          volume: resolvedVolume,
          price: quote?.price ?? item.price ?? watchItem?.price ?? null,
          rvol,
          adx,
          atr_pct: atrPct,
        };
      })
      .filter((item) => scoreToolCandidateForTab(currentTab, item) > -999)
      .sort((a, b) => {
        return scoreToolCandidateForTab(currentTab, b) - scoreToolCandidateForTab(currentTab, a);
      });

    return selectDiverseByLens(sourceCandidates, currentTab, 20, (item) => item.symbol).map((item) => {
      const watchItem = watchUniverse.find((candidate) => candidate.symbol === item.symbol);
      const narrative = buildPublicToolNarrative({
        tabId: currentTab,
        symbol: item.symbol,
        score: item.score,
        changePct: item.changePct,
        price: item.price,
        volume: item.volume,
        rsi: item.rsi,
        rvol: item.rvol,
        adx: item.adx,
        atrPct: item.atr_pct,
        trend: item.trend,
      });
      const lensMetrics = buildToolLensMetrics({
        tabId: currentTab,
        score: item.score,
        changePct: item.changePct,
        volume: item.volume,
        rvol: item.rvol,
        rsi: item.rsi,
        adx: item.adx,
        atr_pct: item.atr_pct,
        trend: item.trend,
      });

      return {
        ticker: item.symbol,
        name: item.label || symbolName(item.symbol),
        tool: currentAiKey,
        score: Number(item.score),
        signal: narrative.signal,
        state: narrative.state,
        confidence: Math.round(Math.max(45, Math.min(95, Number(item.score) * 10))),
        price: item.price ?? watchItem?.price ?? null,
        change_pct: item.changePct,
        volume: item.volume,
        rel_volume: item.rvol ?? null,
        rvol: item.rvol ?? null,
        rsi: item.rsi,
        adx: item.adx ?? null,
        atr_pct: item.atr_pct ?? null,
        metrics: lensMetrics,
        ai_comment: narrative.ai_comment,
        trigger: narrative.trigger,
        invalidation: narrative.invalidation,
        updated_at:
          normalizeAlertTimestamp(item.timestamp) ||
          (item.symbol === selectedTicker ? normalizeAlertTimestamp(chartLatestEpoch) ?? undefined : undefined),
        detected_at:
          normalizeAlertTimestamp(item.timestamp) ||
          (item.symbol === selectedTicker ? normalizeAlertTimestamp(chartLatestEpoch) ?? undefined : undefined),
      };
    });
  }, [
    currentAiRows,
    currentAiKey,
    expandedToolCandidates,
    watchUniverse,
    publicQuotes,
    tickerTapeQuotes,
    selectedTicker,
    currentTab,
    activeChart?.summary?.trend_bias,
    chartForDisplay?.summary?.trend_bias,
    derivedPublicInsight?.score,
    derivedPublicInsight?.rsi,
    derivedPublicInsight?.trend_bias,
    derivedPublicInsight?.signal,
    chartLatestEpoch,
  ]);
  const [aiAlertResetKey, setAiAlertResetKey] = useState(() => getAlertResetKey());
  const [aiAlertHistory, setAiAlertHistory] = useState<Record<string, { resetKey: string; rows: AiToolRow[] }>>({});

  useEffect(() => {
    const timer = window.setInterval(() => setAiAlertResetKey(getAlertResetKey()), 60_000);
    return () => window.clearInterval(timer);
  }, []);

  useEffect(() => {
    try {
      const raw = window.localStorage.getItem(AI_ALERT_HISTORY_STORAGE_KEY);
      if (!raw) return;
      const parsed = JSON.parse(raw) as { resetKey?: string; tabs?: Record<string, { resetKey: string; rows: AiToolRow[] }> };
      setAiAlertHistory(parsed.resetKey === aiAlertResetKey && parsed.tabs ? parsed.tabs : {});
    } catch {
      setAiAlertHistory({});
    }
  }, [aiAlertResetKey]);

  useEffect(() => {
    try {
      window.localStorage.setItem(
        AI_ALERT_HISTORY_STORAGE_KEY,
        JSON.stringify({ resetKey: aiAlertResetKey, tabs: aiAlertHistory }),
      );
    } catch {
      // localStorage can be blocked; in-memory history still works for the session.
    }
  }, [aiAlertHistory, aiAlertResetKey]);

  useEffect(() => {
    if (!currentAiKey || !visibleAiRows.length) return;
    const detectedAt = new Date().toISOString();
    const incoming = visibleAiRows.map((row) => withAlertTimestamp(row, detectedAt));
    if (!incoming.length) return;

    setAiAlertHistory((current) => {
      const currentBucket = current[currentTab];
      const retained = currentBucket?.resetKey === aiAlertResetKey ? currentBucket.rows : [];
      const byKey = new Map<string, AiToolRow>();

      for (const row of retained) {
        byKey.set(aiAlertSignalKey(row), row);
      }

      for (const row of incoming) {
        const key = aiAlertSignalKey(row);
        const existing = byKey.get(key);
        if (existing && aiAlertComparableSignature(existing) === aiAlertComparableSignature(row)) {
          byKey.set(key, existing);
          continue;
        }
        byKey.set(key, {
          ...(existing || {}),
          ...row,
          updated_at: existing?.updated_at || row.updated_at,
          detected_at: existing?.detected_at || row.detected_at || row.updated_at,
          last_seen_at: row.last_seen_at || row.updated_at || existing?.last_seen_at,
        });
      }

      const rows = Array.from(byKey.values())
        .sort((a, b) => Date.parse(resolveAiAlertTimestamp(a) || "") - Date.parse(resolveAiAlertTimestamp(b) || ""))
        .slice(-20);

      if (
        currentBucket?.resetKey === aiAlertResetKey &&
        retained.length === rows.length &&
        retained.every((row, index) => row === rows[index])
      ) {
        return current;
      }

      return {
        ...current,
        [currentTab]: {
          resetKey: aiAlertResetKey,
          rows,
        },
      };
    });
  }, [aiAlertResetKey, currentAiKey, currentTab, visibleAiRows]);

  const fallbackAlertTimestamp = useMemo(() => new Date().toISOString(), [aiAlertResetKey, currentTab]);
  const visibleAiRowsWithTimestamps = useMemo(
    () => visibleAiRows.map((row) => withAlertTimestamp(row, fallbackAlertTimestamp)),
    [fallbackAlertTimestamp, visibleAiRows],
  );
  const currentTabAlertRows =
    aiAlertHistory[currentTab]?.resetKey === aiAlertResetKey && aiAlertHistory[currentTab]?.rows.length
      ? aiAlertHistory[currentTab].rows
      : visibleAiRowsWithTimestamps;
  const showSymbolHeader = currentTab === "grafico";
  const guestCta = !token;
  const profileName = access?.display_name || access?.email || "Trader";
  const activePoll = useMemo(
    () => (sameSymbol(poll?.symbol, selectedTicker) ? normalizePollPayload(poll, selectedTicker) : buildFallbackPoll(selectedTicker)),
    [poll, selectedTicker],
  );
  const localizedActivePoll = useMemo(
    () => ({
      ...activePoll,
      question: localizePollText(activePoll.question, appLocale, selectedTicker),
      status: appLocale === "en-US"
        ? (String(activePoll.status || "").includes("fallback") ? "no backend poll" : localizeUiText(activePoll.status || "open", appLocale, selectedTicker))
        : activePoll.status,
      options: (activePoll.options || []).map((option) => ({
        ...option,
        label: localizePollText(option.label, appLocale, selectedTicker),
      })),
    }),
    [activePoll, appLocale, selectedTicker],
  );
  const hasRenderedChartData = Boolean(chartForDisplay?.ohlc?.length || chartForDisplay?.series?.length);
  const hasPublicSignal = Boolean(derivedPublicInsight?.score != null || derivedPublicInsight?.signal || derivedPublicInsight?.trend_bias);
  const hasSignalSnapshot =
    hasRenderedChartData &&
    (currentRanking?.score != null || hasPublicSignal);
  const trendText = hasSignalSnapshot
    ? String(
        currentRanking?.trend ||
          chartForDisplay?.summary?.trend_bias ||
          derivedPublicInsight?.trend_bias ||
          derivedPublicInsight?.signal ||
          "",
      )
    : "";
  const rawSignalScore =
    currentRanking?.score != null
      ? Number(currentRanking.score)
      : derivedPublicInsight?.score != null
        ? Number(derivedPublicInsight.score)
        : null;
  const normalizedSignalScore = rawSignalScore == null || Number.isNaN(rawSignalScore)
    ? null
    : rawSignalScore <= 10
      ? rawSignalScore * 10
      : rawSignalScore;
  const numericRankingScore =
    normalizedSignalScore != null
      ? clampNumber(normalizedSignalScore, 0, 100)
      : null;
  const fallbackSentimentScore = currentDerivedScore != null && currentDerivedScore > 0 ? clampNumber(Math.round(currentDerivedScore * 10), 0, 100) : null;
  const priceSentimentScore =
    priceMovementPercent != null
      ? clampNumber(Math.round(50 + Number(priceMovementPercent) * 14), 5, 95)
      : null;
  const trendSentimentScore =
    trendText.toLowerCase().includes("bear") || trendText.toLowerCase().includes("baixa")
      ? 35
      : trendText.toLowerCase().includes("bull") || trendText.toLowerCase().includes("alta")
        ? 65
        : null;
  const sentimentComponents = [
    numericRankingScore != null && numericRankingScore > 0 ? numericRankingScore : null,
    fallbackSentimentScore,
    priceSentimentScore,
    trendSentimentScore,
  ].filter((value): value is number => value != null && Number.isFinite(value));
  const effectiveSentimentScore = sentimentComponents.length
    ? Math.round(sentimentComponents.reduce((total, value) => total + value, 0) / sentimentComponents.length)
    : null;
  const sentimentTone =
    effectiveSentimentScore == null
      ? "neutral"
      : effectiveSentimentScore >= 55
        ? "bullish"
        : effectiveSentimentScore <= 45
          ? "bearish"
          : "neutral";
  const sentimentLabel =
    sentimentTone === "bearish"
        ? (isUsLocale ? "Bearish" : "Urso")
        : sentimentTone === "bullish"
          ? (isUsLocale ? "Bullish" : "Touro")
          : effectiveSentimentScore == null
            ? (isUsLocale ? "No read" : "Sem leitura")
            : (isUsLocale ? "Neutral" : "Neutro");
  const sentimentScore = calibrateSentimentMeterValue(effectiveSentimentScore, sentimentLabel);
  const volumeActivity = (discussionPosts.length * 8) + (roomItems.length * 5);
  const publicVolumeScore =
    displayQuote?.volume != null
      ? clampNumber(Math.round((Math.log10(Number(displayQuote.volume) + 1) - 4.5) * 30), 0, 100)
      : null;
  const rawVolumeScore = volumeActivity > 0 ? clampNumber(volumeActivity, 0, 100) : publicVolumeScore;
  const volumeMeterTitle = volumeActivity > 0 ? (isUsLocale ? "Message volume" : "Volume de mensagens") : (isUsLocale ? "Asset volume" : "Volume do ativo");
  const volumeLabel =
    rawVolumeScore == null
      ? (isUsLocale ? "No read" : "Sem leitura")
      : rawVolumeScore >= 65
        ? (isUsLocale ? "High" : "Alto")
        : rawVolumeScore >= 35
          ? "Normal"
          : (isUsLocale ? "Low" : "Baixo");
  const volumeScore = calibrateVolumeMeterValue(rawVolumeScore, volumeLabel);
  const priceDirectionClass = movementClass(priceMovementPercent, currentRanking?.trend, currentRanking?.score);
  const priceMovementLabel = priceDirectionClass === "up"
    ? (isUsLocale ? "Pre-market" : "Pré-mercado")
    : priceDirectionClass === "down"
      ? (isUsLocale ? "After-hours" : "Após o fechamento")
      : (isUsLocale ? "Market" : "Mercado");
  const hasPriceMovement = priceMovementValue != null || priceMovementPercent != null;
  const focusGuide = useMemo(() => {
    const persona = (isUsLocale ? WORKSPACE_PERSONAS_EN : WORKSPACE_PERSONAS)[workspacePersona];
    const topNews = newsRows[0];
    const topDiscussion = featuredDiscussionPosts[0] || discussionPosts[0];
    const leadingTool = currentTabAlertRows.at(-1) || currentAiRows[0];
    const decisionCards = buildChartDecisionCards(chartForDisplay, selectedTicker, displayQuote?.price, appLocale);
    const priceText =
      displayQuote?.price != null
        ? (isUsLocale
          ? `${selectedTicker} at ${formatAssetMoney(displayQuote.price, selectedTicker, appLocale)} (${formatSignedPercent(priceMovementPercent)}).`
          : `${selectedTicker} em ${formatAssetMoney(displayQuote.price, selectedTicker, appLocale)} (${formatSignedPercent(priceMovementPercent)}).`)
        : (isUsLocale ? `${selectedTicker} still has no confirmed provider price.` : `${selectedTicker} ainda sem preço confirmado no provider.`);
    const chartBias = chartForDisplay?.summary?.trend_bias || derivedPublicInsight?.trend_bias || derivedPublicInsight?.signal || null;
    const chartBiasText = localizeUiText(chartBias || "", appLocale, selectedTicker);
    const newsInsight = topNews?.traderTakeaway || topNews?.whyItMatters || topNews?.cardSummary;
    const aiText =
      effectiveAiScore != null
        ? (isUsLocale ? `AI Score ${Number(effectiveAiScore).toFixed(1)} with ${chartBiasText || "neutral"} bias.` : `Score IA ${Number(effectiveAiScore).toFixed(1)} com bias ${chartBias || "neutro"}; ${describeDayTradeBias(chartBias, effectiveAiScore, priceMovementPercent)}`)
        : chartBias
          ? (isUsLocale ? `Public chart shows ${chartBiasText} bias.` : `Gráfico público aponta bias ${chartBias}.`)
          : (isUsLocale ? "Use chart and news as confirmation until the worker ranks this asset." : "Use o gráfico e a notícia como confirmação até o worker ranquear este ativo.");
    const volumeText =
      volumeScore != null
        ? (isUsLocale ? `Market volume ${formatCompact(displayQuote?.volume)}; social read ${volumeLabel.toLowerCase()}.` : `Volume de mercado em ${formatCompact(displayQuote?.volume)}; leitura social ${volumeLabel.toLowerCase()}; ${describeVolumeContext(volumeLabel, priceMovementPercent, volumeScore)}`)
        : (isUsLocale ? "Social volume is still low; prioritize price, candle and objective news." : "Volume social ainda baixo; priorize preço, candle e notícia objetiva.");
    const newsText = topNews
      ? (isUsLocale ? `Featured news: ${newsInsight || topNews.title}` : `Notícia em foco: ${portugueseNewsInsight(newsInsight, selectedTicker)}`)
      : (isUsLocale ? "No strong news now; price and chart carry the initial decision." : "Sem notícia forte agora; preço e gráfico carregam a decisão inicial.");
    const feedText = topDiscussion
      ? (isUsLocale ? `Featured feed: ${topDiscussion.user} is leading the conversation on ${topDiscussion.ticker || selectedTicker}.` : `Feed em foco: ${topDiscussion.user} puxando a conversa em ${topDiscussion.ticker || selectedTicker}.`)
      : (isUsLocale ? `Feed is still empty for ${selectedTicker}; use the composer or poll to start the discussion.` : `Feed ainda vazio em ${selectedTicker}; use o composer ou a poll para abrir discussão.`);

    if (workspacePersona === "guiado") {
      return {
        title: isUsLocale ? "Guided Workflow" : "Roteiro guiado",
        body: isUsLocale ? "Read what to do, watch or avoid before checking news and community." : "Leia o que fazer, observar ou evitar antes de olhar notícia e comunidade.",
        emphasis: persona.emphasis,
        cards: decisionCards.map((card) => localizeGuideCard(card, appLocale)),
      };
    }

    if (workspacePersona === "pro") {
      return {
        title: isUsLocale ? "Operational Mode" : "Modo operacional",
        body: isUsLocale ? `Prioritize ${selectedTicker}, position signal, invalidation and risk before noise.` : `Priorize ${selectedTicker}, sinal de posição, invalidação e risco antes do ruído.`,
        emphasis: leadingTool
          ? (isUsLocale ? `Leading AI now: ${leadingTool.ticker} with ${localizeUiText(leadingTool.state || "active read", appLocale, leadingTool.ticker)}.` : `IA líder agora: ${leadingTool.ticker} com ${leadingTool.state || "leitura ativa"}.`)
          : persona.emphasis,
        bullets: [
          aiText,
          volumeText,
          leadingTool
            ? `IA líder agora: ${leadingTool.ticker} com ${leadingTool.state || "leitura ativa"}.`
            : `Sem líder interno ainda; use ${chartBias || "bias público"} como leitura provisória.`,
        ],
        cards: decisionCards.map((card) => localizeGuideCard(card, appLocale)),
      };
    }

    return {
      title: isUsLocale ? "Trader Mode" : "Modo trader",
      body: isUsLocale ? "Balance current read, direction, confirmation, invalidation and risk in one view." : "Equilibre leitura atual, direção, confirmação, invalidação e risco na mesma dobra.",
      emphasis: `${priceText} ${newsText} ${feedText}`,
      cards: decisionCards.map((card) => localizeGuideCard(card, appLocale)),
    };
  }, [
    appLocale,
    isUsLocale,
    workspacePersona,
    newsRows,
    discussionPosts,
    featuredDiscussionPosts,
    currentAiRows,
    currentTabAlertRows,
    selectedTicker,
    displayQuote?.price,
    displayQuote?.volume,
    effectiveAiScore,
    derivedPublicInsight?.trend_bias,
    derivedPublicInsight?.signal,
    chartForDisplay?.summary?.trend_bias,
    chartForDisplay,
    priceMovementPercent,
    volumeScore,
    volumeLabel,
  ]);

  useEffect(() => {
    if (currentTab !== "education" || !educationAnchor) return;

    const timeout = window.setTimeout(() => {
      document.getElementById(educationAnchor)?.scrollIntoView({ behavior: "smooth", block: "start" });
      setEducationAnchor(null);
    }, 120);

    return () => window.clearTimeout(timeout);
  }, [currentTab, educationAnchor]);

  function openInstitutionalSection(sectionId: string) {
    setSelectedInstitutionalSectionId(sectionId);
    setEducationAnchor(sectionId);
    if (!focusedTab) {
      startTransition(() => {
        setActiveTab("education");
      });
      window.scrollTo({ top: 0, behavior: "smooth" });
    }
  }

  function renderWatchlist() {
    return (
      <div className="snbr-watchlist">
        {groupedActiveWatchlist.length ? groupedActiveWatchlist.map((group) => (
          <section key={group.category} className="snbr-watch-group">
            <header className="snbr-watch-group-head">
              <strong>{group.category}</strong>
              <span>{group.items.length} {isUsLocale ? "assets" : "ativos"}</span>
            </header>
            <div className="snbr-watch-group-list">
              {group.items.map((item) => {
                const itemLabel = displayWatchlistLabel(item, appLocale);
                return (
                <div key={item.symbol} className={cx("snbr-watch-row", item.symbol === selectedTicker && "active")}>
                  <button
                    className="snbr-watch-open"
                    onClick={() => selectTicker(item.symbol)}
                    type="button"
                    aria-label={isUsLocale ? `Open ${item.symbol} on chart` : `Abrir ${item.symbol} no gráfico`}
                    title={`${item.symbol} • ${itemLabel}`}
                  >
                    <div className="snbr-watch-main">
                      <strong>{item.symbol}</strong>
                      <span>{itemLabel}</span>
                    </div>
                    <div className="snbr-watch-side">
                      <span>{formatWatchlistPrimaryValue(item, appLocale)}</span>
                      <span className={cx("snbr-watch-change", movementClass(item.changePct, item.trend, item.score))}>
                        {movementArrow(movementClass(item.changePct, item.trend, item.score))}{" "}
                        {formatMarketMovementText(item, appLocale)}
                      </span>
                    </div>
                  </button>
                  <button
                    className="snbr-watch-remove"
                    onClick={() => handleRemoveFromActiveList(item.symbol)}
                    type="button"
                    aria-label={isUsLocale ? `Remove ${item.symbol} from active list` : `Excluir ${item.symbol} da lista ativa`}
                    title={isUsLocale ? `Remove ${item.symbol} from active list` : `Remover ${item.symbol} da lista ativa`}
                  >
                    {isUsLocale ? "Remove" : "Excluir"}
                  </button>
                </div>
              );})}
            </div>
          </section>
        )) : (
          <div className="snbr-empty-thread">
            <strong>{isUsLocale ? "No asset in your list." : "Nenhum ativo na sua lista."}</strong>
            <p>{isUsLocale ? "Use the search above to add any B3, BDR, crypto or USA asset to your active list." : "Use a busca acima para incluir qualquer ativo da B3 na sua lista ativa."}</p>
          </div>
        )}
      </div>
    );
  }

  function renderAvatar(name?: string | null, email?: string | null, avatarUrl?: string | null) {
    const initials = initialsFromName(name || email || "SN");
    return (
      <div className="snbr-avatar">
        {avatarUrl ? <img src={avatarUrl} alt={name || email || "avatar"} /> : initials}
      </div>
    );
  }

  function buildUserListEntry(userId: number, name?: string | null, emailOrTicker?: string | null, avatarUrl?: string | null): UserListEntry {
    return {
      id: userId,
      nome: name || `Trader ${userId}`,
      identificador: emailOrTicker || `id-${userId}`,
      avatarUrl: avatarUrl || null,
    };
  }

  function rememberUser(current: UserListEntry[], entry: UserListEntry) {
    if (current.some((item) => item.id === entry.id)) return current;
    return [...current, entry];
  }

  function renderCashtagText(text: string, keyPrefix: string): ReactNode {
    const cashtagPattern = /\$([A-Za-z][A-Za-z0-9._-]{0,20})/g;
    const nodes: ReactNode[] = [];
    let lastIndex = 0;
    let match: RegExpExecArray | null;

    while ((match = cashtagPattern.exec(text)) !== null) {
      const start = match.index;
      const rawSymbol = match[1] || "";
      const displaySymbol = normalizeSymbol(rawSymbol);

      if (start > lastIndex) {
        nodes.push(text.slice(lastIndex, start));
      }

      nodes.push(
        <button
          key={`${keyPrefix}-${start}-${displaySymbol}`}
          className="snbr-cashtag"
          onClick={() => selectTicker(displaySymbol)}
          type="button"
        >
          ${displaySymbol}
        </button>,
      );

      lastIndex = start + match[0].length;
    }

    if (lastIndex < text.length) {
      nodes.push(text.slice(lastIndex));
    }

    return nodes.length ? nodes : text;
  }

  function renderMeterCard(
    title: string,
    label: string,
    value: number | null,
    tone: "bullish" | "bearish" | "neutral" = "neutral",
  ) {
    const normalized = value == null ? null : clampNumber(value, 0, 100);
    const meterAngle = normalized == null ? null : 180 - (normalized * 1.8);
    const meterRadians = meterAngle == null ? null : (meterAngle * Math.PI) / 180;
    const needleX = meterRadians == null ? 80 : 80 + (36 * Math.cos(meterRadians));
    const needleY = meterRadians == null ? 82 : 82 - (36 * Math.sin(meterRadians));
    const labelClass = normalized == null ? "neutral" : tone;

    return (
      <div className="snbr-meter-card">
        <div className="snbr-meter-copy">
          <span>{title}</span>
          <strong className={cx("snbr-meter-label", labelClass)}>{label}</strong>
        </div>
        <div className={cx("snbr-meter", tone, normalized == null && "empty")}>
          <svg className="snbr-meter-svg" viewBox="0 0 160 96" aria-hidden="true">
            <path className="snbr-meter-track" d="M 24 82 A 56 56 0 0 1 136 82" />
            {normalized != null ? (
              <>
                <path className="snbr-meter-arc bearish" d="M 24 82 A 56 56 0 0 1 80 26" />
                <path className="snbr-meter-arc bullish" d="M 80 26 A 56 56 0 0 1 136 82" />
              </>
            ) : null}
            {normalized != null ? (
              <>
                <line className="snbr-meter-needle-line" x1="80" y1="82" x2={needleX} y2={needleY} />
                <circle className="snbr-meter-needle-dot" cx="80" cy="82" r="5" />
              </>
            ) : null}
            <text className="snbr-meter-value-svg" x="80" y="58" textAnchor="middle">
              {normalized == null ? "--" : Math.round(normalized)}
            </text>
          </svg>
        </div>
      </div>
    );
  }

  function renderComposer() {
    const profileName = access?.display_name || access?.email || "Trader";

    if (!token) {
      return (
        <div className="snbr-editor-card snbr-social-composer-card" ref={composerCardRef}>
          <div className="snbr-composer-head">
            <div className="snbr-post-user">
                {renderAvatar("Guest")}
              <div>
                <strong>{isUsLocale ? `Share your idea on ${selectedTicker}` : `Compartilhe sua ideia em ${selectedTicker}`}</strong>
                <p>{isUsLocale ? "Login unlocks posts, votes, likes, images, comments and full community context." : "Login libera post, voto, curtidas, imagem, comentarios e contexto completo da comunidade."}</p>
              </div>
            </div>
            <button aria-label={isUsLocale ? "More post options" : "Mais opcoes do post"} className="snbr-toolbar-icon" onClick={() => promptLogin(isUsLocale ? "open post actions" : "abrir ações do post")} type="button">
              ⋯
            </button>
          </div>
          <textarea
            className="snbr-textarea snbr-composer-textarea"
            id="snbr-post-textarea"
            value={postText}
            onChange={(event) => setPostText(event.target.value)}
            aria-label={isUsLocale ? `Write your thesis on ${selectedTicker}` : `Escreva sua tese sobre ${selectedTicker}`}
            placeholder={isUsLocale ? `Write your thesis on ${selectedTicker}` : `Escreva sua tese em ${selectedTicker}`}
          />
          <p className="snbr-composer-helper">
            {isUsLocale ? "Tip: cite the trigger, timeframe and invalidation level." : "Dica: cite gatilho, timeframe e o ponto em que sua tese invalida."}
          </p>
          <div className="snbr-composer-footer">
            <div className="snbr-composer-left">
              <div className="snbr-composer-sentiment">
                <button
                  className={cx("snbr-sentiment-pill", "bullish", postSentiment === "bullish" && "active")}
                  onClick={() => setPostSentiment("bullish")}
                  aria-pressed={postSentiment === "bullish"}
                  aria-label={isUsLocale ? `Post as bullish for ${selectedTicker}` : `Publicar como touro para ${selectedTicker}`}
                  type="button"
                >
                  <span className="snbr-sentiment-glyph bullish">🐂</span>
                  <span>{isUsLocale ? "Bullish" : "Touro"}</span>
                </button>
                <button
                  className={cx("snbr-sentiment-pill", "bearish", postSentiment === "bearish" && "active")}
                  onClick={() => setPostSentiment("bearish")}
                  aria-pressed={postSentiment === "bearish"}
                  aria-label={isUsLocale ? `Post as bearish for ${selectedTicker}` : `Publicar como urso para ${selectedTicker}`}
                  type="button"
                >
                  <span className="snbr-sentiment-glyph bearish">🐻</span>
                  <span>{isUsLocale ? "Bearish" : "Urso"}</span>
                </button>
              </div>

          <div className="snbr-composer-toolbar-stack" data-composer-controls="true">
            <div className="snbr-composer-toolbar">
              <button className={cx("snbr-toolbar-icon", predictionOpen && "active")} title={isUsLocale ? "Create prediction" : "Criar previsão"} aria-label={isUsLocale ? "Create prediction" : "Criar previsão"} onClick={togglePredictionBox} type="button">🎯</button>
              <button
                className="snbr-toolbar-icon"
                onClick={() => composerFileInputRef.current?.click()}
                    title={isUsLocale ? "Add photo" : "Adicionar foto"}
                    aria-label={isUsLocale ? "Add photo" : "Adicionar foto"}
                    type="button"
                  >
                    🖼️
                  </button>
                  <button
                    className={cx("snbr-toolbar-icon", composerGifOpen && "active")}
                    onClick={() => {
                      setComposerGifOpen((value) => !value);
                      setComposerEmojiOpen(false);
                    }}
                    title={isUsLocale ? "Add GIF" : "Adicionar GIF"}
                    aria-label={isUsLocale ? "Add GIF" : "Adicionar GIF"}
                    aria-expanded={composerGifOpen}
                    type="button"
                  >
                    GIF
                  </button>
                  <button
                    className={cx("snbr-toolbar-icon", composerEmojiOpen && "active")}
                    onClick={() => setComposerEmojiOpen((value) => !value)}
                    title={isUsLocale ? "Add emoji" : "Adicionar emoji"}
                    aria-label={isUsLocale ? "Add emoji" : "Adicionar emoji"}
                    aria-expanded={composerEmojiOpen}
                    type="button"
                  >
                    😊
                  </button>
                  {postFile ? <span className="snbr-file-pill">{postFile.name}</span> : null}
                </div>

                {composerGifOpen ? (
                  <div className="snbr-gif-picker" aria-label={isUsLocale ? "Select GIF" : "Selecionar GIF"}>
                    <div className="snbr-gif-search">
                      <input
                        className="snbr-input"
                        value={gifQuery}
                        onChange={(event) => setGifQuery(event.target.value)}
                        placeholder={isUsLocale ? `Search GIF: ${selectedTicker}` : `Buscar GIF: ${selectedTicker}`}
                      />
                      <button className="snbr-button subtle" onClick={openYahooGifSearch} type="button">
                        {isUsLocale ? "Search Yahoo" : "Buscar no Yahoo"}
                      </button>
                    </div>
                    <div className="snbr-gif-quick-grid">
                      {QUICK_GIF_TERMS.map((term) => (
                        <button key={term} className="snbr-gif-chip" onClick={() => appendComposerGif(term)} type="button">
                          {term}
                        </button>
                      ))}
                    </div>
                  </div>
                ) : null}

                {composerEmojiOpen ? (
                  <div className="snbr-emoji-picker" aria-label={isUsLocale ? "Select emoji" : "Selecionar emoji"}>
                    {COMPOSER_EMOJIS.map((emoji) => (
                      <button key={emoji} className="snbr-emoji-option" onClick={() => appendComposerEmoji(emoji)} type="button">
                        {emoji}
                      </button>
                    ))}
                  </div>
                ) : null}
              </div>

              {predictionOpen ? (
                <div className="snbr-prediction-box">
                  <div className="snbr-prediction-box-head">
                    <strong>{isUsLocale ? "Create prediction" : "Criar previsão"}</strong>
                    <button className="snbr-toolbar-icon" onClick={() => setPredictionOpen(false)} type="button" aria-label={isUsLocale ? "Close prediction" : "Fechar previsão"}>✕</button>
                  </div>
                  <div className="snbr-prediction-grid">
                    <label className="snbr-profile-field">
                      <span>{isUsLocale ? "Symbol" : "Símbolo"}</span>
                      <input className="snbr-input" value={predictionSymbol} onChange={(event) => setPredictionSymbol(event.target.value.toUpperCase())} placeholder="PETR4" />
                    </label>
                    <label className="snbr-profile-field">
                      <span>{isUsLocale ? "Target price" : "Preço alvo"}</span>
                      <input className="snbr-input" value={predictionTargetPrice} onChange={(event) => setPredictionTargetPrice(event.target.value)} placeholder={isUsLocale ? "$42.00" : "R$ 42,00"} />
                    </label>
                    <label className="snbr-profile-field">
                      <span>{isUsLocale ? "Target date" : "Data alvo"}</span>
                      <input className="snbr-input" type="date" value={predictionTargetDate} onChange={(event) => setPredictionTargetDate(event.target.value)} />
                    </label>
                  </div>
                  <div className="snbr-prediction-side" aria-label={isUsLocale ? "Prediction direction" : "Direção da previsão"}>
                    <button
                      className={cx("snbr-sentiment-chip", "bullish", postSentiment === "bullish" && "active")}
                      onClick={() => setPostSentiment("bullish")}
                      type="button"
                      aria-pressed={postSentiment === "bullish"}
                    >
                      {isUsLocale ? "Bullish" : "Touro"}
                    </button>
                    <button
                      className={cx("snbr-sentiment-chip", "bearish", postSentiment === "bearish" && "active")}
                      onClick={() => setPostSentiment("bearish")}
                      type="button"
                      aria-pressed={postSentiment === "bearish"}
                    >
                      {isUsLocale ? "Bearish" : "Urso"}
                    </button>
                  </div>
                  <div className="snbr-prediction-actions">
                    <button className="snbr-button primary" onClick={() => void handleCreatePredictionPost()} type="button">
                      {predictionPosting ? (isUsLocale ? "Posting..." : "Postando...") : (isUsLocale ? "Post prediction" : "Postar previsão")}
                    </button>
                  </div>
                </div>
              ) : null}

              <input
                ref={composerFileInputRef}
                className="snbr-hidden-file-input"
                type="file"
                accept="image/png,image/jpeg,image/webp,image/gif"
                onChange={(event) => setPostFile(event.target.files?.[0] || null)}
              />
            </div>

            <button className="snbr-button primary snbr-post-submit" onClick={handleCreatePost} type="button">
              Post
            </button>
          </div>
        </div>
      );
    }

    return (
      <div className="snbr-editor-card snbr-social-composer-card" ref={composerCardRef}>
        <div className="snbr-composer-head">
          <div className="snbr-post-user">
            {renderAvatar(profileName, access?.email, access?.avatar_url)}
            <div className="snbr-composer-user">
              <strong>{profileName}</strong>
              <span>{access?.email}</span>
            </div>
          </div>
          <button aria-label={isUsLocale ? "More post options" : "Mais opcoes do post"} className="snbr-toolbar-icon" type="button">
            ⋯
          </button>
        </div>

        <textarea
          className="snbr-textarea snbr-composer-textarea"
          id="snbr-post-textarea"
          value={postText}
          onChange={(event) => setPostText(event.target.value)}
          aria-label={isUsLocale ? `Write your thesis on ${selectedTicker}` : `Escreva sua tese sobre ${selectedTicker}`}
          placeholder={isUsLocale ? `Write your thesis on ${selectedTicker}` : `Escreva sua tese em ${selectedTicker}`}
        />

        <p className="snbr-composer-helper">
          {isUsLocale ? "Tip: explain the trigger, timeframe and invalidation level. AI and community should confirm, not add noise." : "Dica: conte o gatilho, o prazo e o nível de invalidação. IA e comunidade entram como confirmação, não ruído."}
        </p>

        <div className="snbr-composer-footer">
          <div className="snbr-composer-left">
            <div className="snbr-composer-sentiment">
              <button
                className={cx("snbr-sentiment-pill", "bullish", postSentiment === "bullish" && "active")}
                onClick={() => setPostSentiment("bullish")}
                aria-pressed={postSentiment === "bullish"}
                aria-label={isUsLocale ? `Post as bullish for ${selectedTicker}` : `Publicar como touro para ${selectedTicker}`}
                type="button"
              >
                <span className="snbr-sentiment-glyph bullish">🐂</span>
                <span>{isUsLocale ? "Bullish" : "Touro"}</span>
              </button>
              <button
                className={cx("snbr-sentiment-pill", "bearish", postSentiment === "bearish" && "active")}
                onClick={() => setPostSentiment("bearish")}
                aria-pressed={postSentiment === "bearish"}
                aria-label={isUsLocale ? `Post as bearish for ${selectedTicker}` : `Publicar como urso para ${selectedTicker}`}
                type="button"
              >
                <span className="snbr-sentiment-glyph bearish">🐻</span>
                <span>{isUsLocale ? "Bearish" : "Urso"}</span>
              </button>
            </div>

            <div className="snbr-composer-toolbar-stack" data-composer-controls="true">
              <div className="snbr-composer-toolbar">
                <button className={cx("snbr-toolbar-icon", predictionOpen && "active")} title={isUsLocale ? "Create prediction" : "Criar previsão"} aria-label={isUsLocale ? "Create prediction" : "Criar previsão"} onClick={togglePredictionBox} type="button">🎯</button>
                <button
                  className="snbr-toolbar-icon"
                  onClick={() => composerFileInputRef.current?.click()}
                  title={isUsLocale ? "Add photo" : "Adicionar foto"}
                  aria-label={isUsLocale ? "Add photo" : "Adicionar foto"}
                  type="button"
                >
                  🖼️
                </button>
                <button
                  className={cx("snbr-toolbar-icon", composerGifOpen && "active")}
                  onClick={() => {
                    setComposerGifOpen((value) => !value);
                    setComposerEmojiOpen(false);
                  }}
                  title={isUsLocale ? "Add GIF" : "Adicionar GIF"}
                  aria-label={isUsLocale ? "Add GIF" : "Adicionar GIF"}
                  aria-expanded={composerGifOpen}
                  type="button"
                >
                  GIF
                </button>
                <button
                  className={cx("snbr-toolbar-icon", composerEmojiOpen && "active")}
                  onClick={() => setComposerEmojiOpen((value) => !value)}
                  title={isUsLocale ? "Add emoji" : "Adicionar emoji"}
                  aria-label={isUsLocale ? "Add emoji" : "Adicionar emoji"}
                  aria-expanded={composerEmojiOpen}
                  type="button"
                >
                  😊
                </button>
                {postFile ? <span className="snbr-file-pill">{postFile.name}</span> : null}
              </div>

              {composerGifOpen ? (
                <div className="snbr-gif-picker" aria-label={isUsLocale ? "Select GIF" : "Selecionar GIF"}>
                  <div className="snbr-gif-search">
                    <input
                      className="snbr-input"
                      value={gifQuery}
                      onChange={(event) => setGifQuery(event.target.value)}
                      placeholder={isUsLocale ? `Search GIF: ${selectedTicker}` : `Buscar GIF: ${selectedTicker}`}
                    />
                    <button className="snbr-button subtle" onClick={openYahooGifSearch} type="button">
                      {isUsLocale ? "Search Yahoo" : "Buscar no Yahoo"}
                    </button>
                  </div>
                  <div className="snbr-gif-quick-grid">
                    {QUICK_GIF_TERMS.map((term) => (
                      <button key={term} className="snbr-gif-chip" onClick={() => appendComposerGif(term)} type="button">
                        {term}
                      </button>
                    ))}
                  </div>
                </div>
              ) : null}

              {composerEmojiOpen ? (
                <div className="snbr-emoji-picker" aria-label={isUsLocale ? "Select emoji" : "Selecionar emoji"}>
                  {COMPOSER_EMOJIS.map((emoji) => (
                    <button key={emoji} className="snbr-emoji-option" onClick={() => appendComposerEmoji(emoji)} type="button">
                      {emoji}
                    </button>
                  ))}
                </div>
                ) : null}
              </div>

              {predictionOpen ? (
                <div className="snbr-prediction-box">
                  <div className="snbr-prediction-box-head">
                    <strong>{isUsLocale ? "Create prediction" : "Criar previsão"}</strong>
                    <button className="snbr-toolbar-icon" onClick={() => setPredictionOpen(false)} type="button" aria-label={isUsLocale ? "Close prediction" : "Fechar previsão"}>✕</button>
                  </div>
                  <div className="snbr-prediction-grid">
                    <label className="snbr-profile-field">
                      <span>{isUsLocale ? "Symbol" : "Símbolo"}</span>
                      <input className="snbr-input" value={predictionSymbol} onChange={(event) => setPredictionSymbol(event.target.value.toUpperCase())} placeholder="PETR4" />
                    </label>
                    <label className="snbr-profile-field">
                      <span>{isUsLocale ? "Target price" : "Preço alvo"}</span>
                      <input className="snbr-input" value={predictionTargetPrice} onChange={(event) => setPredictionTargetPrice(event.target.value)} placeholder={isUsLocale ? "$42.00" : "R$ 42,00"} />
                    </label>
                    <label className="snbr-profile-field">
                      <span>{isUsLocale ? "Target date" : "Data alvo"}</span>
                      <input className="snbr-input" type="date" value={predictionTargetDate} onChange={(event) => setPredictionTargetDate(event.target.value)} />
                    </label>
                  </div>
                  <div className="snbr-prediction-side" aria-label={isUsLocale ? "Prediction direction" : "Direção da previsão"}>
                    <button
                      className={cx("snbr-sentiment-chip", "bullish", postSentiment === "bullish" && "active")}
                      onClick={() => setPostSentiment("bullish")}
                      type="button"
                      aria-pressed={postSentiment === "bullish"}
                    >
                      {isUsLocale ? "Bullish" : "Touro"}
                    </button>
                    <button
                      className={cx("snbr-sentiment-chip", "bearish", postSentiment === "bearish" && "active")}
                      onClick={() => setPostSentiment("bearish")}
                      type="button"
                      aria-pressed={postSentiment === "bearish"}
                    >
                      {isUsLocale ? "Bearish" : "Urso"}
                    </button>
                  </div>
                  <div className="snbr-prediction-actions">
                    <button className="snbr-button primary" onClick={() => void handleCreatePredictionPost()} type="button">
                      {predictionPosting ? (isUsLocale ? "Posting..." : "Postando...") : (isUsLocale ? "Post prediction" : "Postar previsão")}
                    </button>
                  </div>
                </div>
              ) : null}

              <input
                ref={composerFileInputRef}
                className="snbr-hidden-file-input"
                type="file"
              accept="image/png,image/jpeg,image/webp,image/gif"
              onChange={(event) => setPostFile(event.target.files?.[0] || null)}
            />
          </div>

          <button className="snbr-button primary snbr-post-submit" disabled={posting} onClick={handleCreatePost} type="button">
            {posting ? (isUsLocale ? "Posting..." : "Postando...") : "Post"}
          </button>
        </div>
      </div>
    );
  }

  function renderDiscussionList(posts: FeedPost[], emptyText: string) {
    if (!posts.length) {
      return (
        <div className="snbr-empty-thread">
          <strong>{isUsLocale ? "No featured social discussion for this ticker yet." : emptyText}</strong>
          <p>{isUsLocale ? `Open the conversation with your thesis, post a chart screenshot or comment on the market read for ${selectedTicker}.` : `Abra a conversa com sua tese, poste um print do grafico ou comente a leitura do mercado para ${selectedTicker}.`}</p>
        </div>
      );
    }

    return (
      <div className="snbr-discussion-list">
        {posts.map((post) => (
          <article key={post.id} className="snbr-post">
            <div className="snbr-post-head snbr-post-head-top">
              <div className="snbr-post-user">
                {renderAvatar(post.user, post.user_email, post.user_avatar_url)}
                <div>
                  <strong>{post.user}</strong>
                  <span>{post.user_email || post.ticker || selectedTicker} • {formatRelativeTime(post.timestamp, appLocale)}</span>
                </div>
              </div>
              <div className="snbr-post-head-actions">
                <span className={cx("snbr-tone-tag", post.sentiment || "neutral")}>
                  {sentimentDisplay(post.sentiment, appLocale)}
                </span>
                {post.user_id !== access?.id ? (
                  <button
                    className={cx("snbr-follow-pill", post.is_followed_by_me && "active")}
                    onClick={() => void handleFollowTrader(post.user_id, Boolean(post.is_followed_by_me))}
                    type="button"
                  >
                    {post.is_followed_by_me ? (isUsLocale ? "Following" : "Seguindo") : (isUsLocale ? "Follow" : "Seguir")}
                  </button>
                ) : null}
                <div className="snbr-post-menu-wrap" data-post-menu-root="true">
                  <button
                    className="snbr-toolbar-icon"
                    onClick={() => setPostMenuId((current) => current === post.id ? null : post.id)}
                    type="button"
                    aria-expanded={postMenuId === post.id}
                    aria-haspopup="menu"
                    aria-controls={`post-menu-${post.id}`}
                    aria-label={isUsLocale ? `Open post actions by ${post.user}` : `Abrir ações do post de ${post.user}`}
                  >
                    ⋯
                  </button>
                  {postMenuId === post.id ? (
                    <div className="snbr-post-menu" id={`post-menu-${post.id}`} role="menu">
                      {post.user_id !== access?.id ? (
                        <button onClick={() => void handleFollowTrader(post.user_id, Boolean(post.is_followed_by_me))} type="button" role="menuitem">
                          {post.is_followed_by_me ? (isUsLocale ? "Unfollow" : "Deixar de seguir") : (isUsLocale ? "Follow trader" : "Seguir trader")}
                        </button>
                      ) : null}
                      <button onClick={() => void handleMuteTrader(post)} type="button" role="menuitem">{isUsLocale ? "Mute" : "Silenciar"}</button>
                      <button onClick={() => void handleReport(post.id)} type="button" role="menuitem">{isUsLocale ? "Report to StockNewsBR" : "Reportar para StockNewsBR"}</button>
                      <button onClick={() => void handleBlockTrader(post)} type="button" role="menuitem">{isUsLocale ? "Block trader" : "Bloquear trader"}</button>
                      <button onClick={() => void handleReportAndBlock(post.id, post)} type="button" role="menuitem">{isUsLocale ? "Report and block" : "Reportar e bloquear"}</button>
                      {access?.id === post.user_id ? (
                        <button onClick={() => void handleDeleteOwnPost(post.id)} type="button" role="menuitem">{isUsLocale ? "Delete my post" : "Excluir meu post"}</button>
                      ) : null}
                    </div>
                  ) : null}
                </div>
              </div>
            </div>
            <div className="snbr-post-symbol-row">
              <strong>${post.ticker || selectedTicker}</strong>
              <span className={cx("snbr-tone-tag", post.sentiment || "neutral")}>
                {sentimentDisplay(post.sentiment, appLocale)}
              </span>
            </div>
            <p className="snbr-rich-text">{renderCashtagText(localizeUiText(post.text, appLocale, post.ticker || selectedTicker), `post-${post.id}`)}</p>
            {post.image_url ? <img className="snbr-image" src={post.image_url} alt={isUsLocale ? "post media" : "midia do post"} /> : null}
            <div className="snbr-post-actions snbr-post-actions-bar">
              <button
                className="snbr-post-action snbr-feed-action"
                onClick={() => document.getElementById(`comment-input-${post.id}`)?.focus()}
                aria-label={isUsLocale ? `Reply to ${post.user}'s post` : `Responder ao post de ${post.user}`}
                type="button"
              >
                <span aria-hidden="true">💬</span>
                <span>{isUsLocale ? "Reply" : "Responder"}</span>
                <span>{post.comments?.length || 0}</span>
              </button>
              <button
                className={cx("snbr-post-action", "snbr-feed-action", (post.reposted_by_me || (post.reposts || 0) > 0) && "reposted")}
                onClick={() => void handleRepost(post)}
                aria-label={isUsLocale ? `Repost ${post.ticker || selectedTicker}` : `Repostar ${post.ticker || selectedTicker}`}
                type="button"
              >
                <span aria-hidden="true">🔁</span>
                <span>{isUsLocale ? "Repost" : "Repostar"}</span>
                <span>{post.reposts ?? 0}</span>
              </button>
              <button
                className={cx("snbr-post-action", "snbr-feed-action", (post.liked_by_me || (post.likes || 0) > 0) && "liked")}
                onClick={() => void handleToggleLike(post)}
                aria-label={isUsLocale ? `Like ${post.user}'s post` : `Curtir post de ${post.user}`}
                type="button"
              >
                <span aria-hidden="true">{(post.liked_by_me || (post.likes || 0) > 0) ? "♥" : "♡"}</span>
                <span>{isUsLocale ? "Like" : "Curtir"}</span>
                <span>{post.likes ?? 0}</span>
              </button>
            </div>

            {post.reposted_by_me ? (
              <div className="snbr-quote-repost">
                <span className="snbr-quote-repost-label">{isUsLocale ? "Your repost" : "Seu repost"}</span>
                <p>{localizeUiText(post.my_repost_quote_text || (isUsLocale ? "Repost without comment." : "Repost sem comentário."), appLocale, post.ticker || selectedTicker)}</p>
              </div>
            ) : null}

              <div className="snbr-post-comments">
                {(post.comments || []).length ? (
                  <div className="snbr-comment-thread-label">
                    <span>{isUsLocale ? "Replies" : "Respostas"}</span>
                    <strong>{post.comments?.length || 0}</strong>
                  </div>
                ) : null}
                {(post.comments || []).map((comment) => (
                  <article key={comment.id} className="snbr-comment-card snbr-reply-card">
                    <div className="snbr-post-user">
                      {renderAvatar(comment.user, comment.user_email, comment.user_avatar_url)}
                      <div>
                        <strong>{comment.user}</strong>
                        <span>{comment.user_email || (isUsLocale ? "comment" : "comentario")} • {formatRelativeTime(comment.timestamp, appLocale)}</span>
                      </div>
                    </div>
                  <p className="snbr-rich-text">{renderCashtagText(localizeUiText(comment.text, appLocale, post.ticker || selectedTicker), `comment-${comment.id}`)}</p>
                  {comment.image_url ? <img className="snbr-image" src={comment.image_url} alt={isUsLocale ? "comment image" : "imagem do comentario"} /> : null}
                </article>
              ))}

              {token ? (
                <div className="snbr-comment-compose">
                  <input
                    id={`comment-input-${post.id}`}
                    className="snbr-input"
                    value={commentDrafts[post.id] || ""}
                    onChange={(event) => setCommentDrafts((current) => ({ ...current, [post.id]: event.target.value }))}
                    aria-label={isUsLocale ? `Reply to ${post.user}'s post` : `Responder ao post de ${post.user}`}
                    placeholder={isUsLocale ? `Reply to ${post.user}'s post` : `Responder ao post de ${post.user}`}
                  />
                  <button
                    className="snbr-button secondary"
                    disabled={commentingPostId === post.id}
                    onClick={() => void handleComment(post.id)}
                    type="button"
                  >
                    {commentingPostId === post.id ? (isUsLocale ? "Sending..." : "Enviando...") : (isUsLocale ? "Comment" : "Comentar")}
                  </button>
                </div>
              ) : null}
            </div>
          </article>
        ))}
      </div>
    );
  }

  function renderSearchTab() {
    return (
      <WorkspaceSearchPanel
        locale={appLocale}
        selectedTicker={selectedTicker}
        searchResults={searchResults.map((item) => {
          const kind = movementClass(item.changePct, item.trend, item.score);
          return {
            symbol: item.symbol,
            label: item.label,
            priceText: formatPrice(item.price),
            movementText: `${movementArrow(kind)} ${formatMarketMovementText(item)}`,
            movementClass: kind,
          };
        })}
        onSelectTicker={selectTicker}
      />
    );
  }

  function renderToolTab(title: string, description: string) {
    const copySource = isUsLocale ? TOOL_COPY_EN : TOOL_COPY;
    const copy = copySource[currentTab] || { title, description, explanation: "" };
    const tabLensPt: Record<string, string> = {
      "heat-map": "Lente: força relativa por movimento e preço.",
      radar: "Lente: aceleração recente e mudança de ritmo.",
      "breakout-probability": "Lente: proximidade de rompimento e espaço para expansão.",
      "volatility-squeeze": "Lente: compressão de volatilidade e provável expansão.",
      "institutional-flow": "Lente: fluxo de instituições e volume anormal.",
      "smart-money": "Lente: dinheiro inteligente e deslocamento pré-movimento.",
      accumulation: "Lente: acumulação gradual e estabilidade de preço.",
      "liquidity-sweep": "Lente: varredura de liquidez e reação pós-stop.",
      "liquidity-map": "Lente: concentração de liquidez, stops e reação possível.",
      "market-regime": "Lente: regime atual do mercado e contexto operacional.",
      "master-score": "Lente: força geral consolidada da oportunidade.",
    };
    const tabLensEn: Record<string, string> = {
      "heat-map": "Lens: relative strength by movement and price.",
      radar: "Lens: recent acceleration and rhythm change.",
      "breakout-probability": "Lens: breakout proximity and expansion room.",
      "volatility-squeeze": "Lens: volatility compression and likely expansion.",
      "institutional-flow": "Lens: institutional flow and abnormal volume.",
      "smart-money": "Lens: smart money and pre-move displacement.",
      accumulation: "Lens: gradual accumulation and price stability.",
      "liquidity-sweep": "Lens: liquidity sweep and post-stop reaction.",
      "liquidity-map": "Lens: liquidity concentration, stops and possible reaction.",
      "market-regime": "Lens: current market regime and operating context.",
      "master-score": "Lens: consolidated opportunity strength.",
    };
    const lens = (isUsLocale ? tabLensEn : tabLensPt)[currentTab] || "";

    if (currentAiKey) {
      return (
        <section id={`panel-${currentTab}`} className="snbr-tool-shell">
          <div className="snbr-tool-head">
            <div>
              <h3>{copy.title}</h3>
              <p>{copy.description}</p>
              {copy.explanation ? <p>{copy.explanation}</p> : null}
              {lens ? <p className="snbr-tool-lens">{lens}</p> : null}
            </div>
            <button className="snbr-button secondary snbr-popout-button" onClick={() => openPopout(currentTab)} type="button" aria-label={isUsLocale ? `Open ${copy.title} in another screen` : `Abrir ${copy.title} em outra tela`}>
              {isUsLocale ? "Detach" : "Liberar Tela"}
            </button>
          </div>

          {currentTabAlertRows.length ? (
            <div className="snbr-tool-stack">
              <p className="snbr-tool-lens">
                {isUsLocale
                  ? `Latest lens findings: ${currentTabAlertRows.length}/20. The list resets at 07:00 and keeps the most recent finding last.`
                  : `Últimos achados da lente: ${currentTabAlertRows.length}/20. A lista zera às 07:00 e mantém o achado mais recente por último.`}
              </p>
              {currentTabAlertRows.map((item, index) => {
                const watchItem = watchUniverse.find((candidate) => candidate.symbol === item.ticker);
                const quote = resolveQuoteForSymbol(item.ticker, publicQuotes, tickerTapeQuotes);
                const tone = aiSignalTone(item.signal);
                const resolvedChangePct = item.change_pct ?? watchItem?.changePct ?? null;
                const resolvedPrice = firstFiniteNumber(item.price, watchItem?.price, quote?.price);
                const resolvedVolume = firstFiniteNumber(item.volume, watchItem?.volume, quote?.volume);
                const resolvedRsi = item.rsi ?? derivePublicRsi(resolvedChangePct, item.state || item.signal || watchItem?.trend || null);
                const resolvedRvol = item.rel_volume ?? deriveRelativeVolume(resolvedVolume);
                const resolvedAdx = item.adx ?? deriveAdx(resolvedChangePct, resolvedRsi, item.state || item.signal || watchItem?.trend || null);
                const resolvedAtrPct = item.atr_pct ?? deriveAtrPct(resolvedChangePct, resolvedRsi, resolvedVolume);
                const metricEntries = Object.entries(item.metrics || {})
                  .filter(([, value]) => value !== null && value !== undefined && value !== "")
                  .slice(0, 4);

                return (
                  <div key={`${currentTab}-${item.ticker}-${index}`} className="snbr-tool-row">
                    <section className="snbr-plain-panel">
                      <div className="snbr-section-head compact">
                        <div>
                          <h3>{isUsLocale ? "Asset Panel" : "Painel do ativo"}</h3>
                          <p>{isUsLocale ? "Daily alert from the current lens, with detection time and execution criteria." : "Alerta diário da lente atual, com horário detectado e critérios de execução."}</p>
                        </div>
                        <span className="snbr-chip">{isUsLocale ? "Found" : "Encontrado"}: {formatAiUpdatedAt(resolveAiAlertTimestamp(item), appLocale)}</span>
                      </div>
                      <button className="snbr-asset-box snbr-asset-box-large" onClick={() => selectTicker(item.ticker)} type="button">
                        <div className="snbr-asset-box-head">
                          <strong>{item.ticker}</strong>
                          <span className={cx("snbr-side-badge", scoreClass(item.score))}>
                            Score {item.score.toFixed(1)}
                          </span>
                        </div>
                        <span>{item.name || symbolName(item.ticker)}</span>
                        <div className="snbr-asset-box-stats">
                          <div>
                            <small>{isUsLocale ? "Price" : "Preço"}</small>
                            <strong>{formatPrice(resolvedPrice)}</strong>
                          </div>
                          <div>
                            <small>{isUsLocale ? "Change" : "Variação"}</small>
                            <strong>{resolvedChangePct != null ? formatSignedPercent(resolvedChangePct) : "n/a"}</strong>
                          </div>
                          <div>
                            <small>Volume</small>
                            <strong>{formatLiquidityVolume(resolvedVolume, resolvedRvol)}</strong>
                          </div>
                          <div>
                            <small>RVOL</small>
                            <strong>{resolvedRvol != null ? resolvedRvol.toFixed(2) : (isUsLocale ? "no read" : "sem leitura")}</strong>
                          </div>
                          <div>
                            <small>{isUsLocale ? "Confidence" : "Confiança"}</small>
                            <strong>{item.confidence}%</strong>
                          </div>
                          <div>
                            <small>{isUsLocale ? "State" : "Estado"}</small>
                            <strong>{humanizeMachineLabel(item.state, appLocale)}</strong>
                          </div>
                        </div>
                      </button>
                    </section>

                    <section className="snbr-plain-panel">
                      <div className="snbr-section-head compact">
                        <div>
                          <h3>{isUsLocale ? "AI Reads" : "Leituras da IA"}</h3>
                          <p>{isUsLocale ? "Operational direction, trigger, invalidation and institutional-lens context." : "Direção operacional, gatilho, invalidação e contexto da lente institucional."}</p>
                        </div>
                      </div>
                      <div className="snbr-tool-reading-grid">
                          <div className="snbr-tool-reading-card">
                            <span>{isUsLocale ? "Main read" : "Leitura principal"}</span>
                            <strong>{humanizeMachineLabel(item.state, appLocale)}</strong>
                            <p>{localizeUiText(item.ai_comment || (isUsLocale ? "No additional read for this asset." : "Sem leitura adicional para este ativo."), appLocale, item.ticker)}</p>
                          </div>
                        <div className="snbr-tool-reading-card">
                          <span>Trigger</span>
                          <strong>{localizeUiText(item.trigger || (isUsLocale ? "Wait for structural confirmation." : "Aguardar confirmação estrutural."), appLocale, item.ticker)}</strong>
                        </div>
                        <div className="snbr-tool-reading-card">
                          <span>{isUsLocale ? "Invalidation" : "Invalidação"}</span>
                          <strong>{localizeUiText(item.invalidation || (isUsLocale ? "No invalidation defined." : "Sem invalidação definida."), appLocale, item.ticker)}</strong>
                        </div>
                          <div className="snbr-tool-reading-card">
                            <span>{isUsLocale ? "Context" : "Contexto"}</span>
                            <strong className={cx("snbr-tone-tag", tone)}>
                              {tone === "bullish" ? (isUsLocale ? "🐂 Buy" : "🐂 Compra") : tone === "bearish" ? (isUsLocale ? "🐻 Sell" : "🐻 Venda") : (isUsLocale ? "Watching" : "Monitorando")}
                            </strong>
                          <p>RSI {resolvedRsi != null ? resolvedRsi.toFixed(1) : (isUsLocale ? "no read" : "sem leitura")} • RVOL {resolvedRvol != null ? resolvedRvol.toFixed(2) : (isUsLocale ? "no read" : "sem leitura")} • ADX {resolvedAdx != null ? resolvedAdx.toFixed(1) : (isUsLocale ? "no read" : "sem leitura")} • ATR {resolvedAtrPct != null ? resolvedAtrPct.toFixed(1) : (isUsLocale ? "no read" : "sem leitura")}%</p>
                          </div>
                          {metricEntries.length ? (
                            <div className="snbr-tool-reading-card snbr-tool-metrics-card">
                              <span>{isUsLocale ? "Lens metrics" : "Métricas da lente"}</span>
                              <div className="snbr-tool-metric-list">
                                {metricEntries.map(([key, value]) => (
                                  <p key={`${item.ticker}-${key}`}>
                                    <small>{formatToolMetricLabel(key, appLocale)}</small>
                                    <strong>{formatToolMetricValue(value, appLocale)}</strong>
                                  </p>
                                ))}
                              </div>
                            </div>
                          ) : null}
                        </div>
                      </section>
                    </div>
                  );
              })}
            </div>
          ) : (
            <div className="snbr-empty-thread">
              <strong>{isUsLocale ? "No specific reads in the current snapshot." : "Sem leituras específicas no snapshot atual."}</strong>
              <p>{isUsLocale ? "This AI backend is already connected, but no asset entered the current worker cut." : "O backend desta IA já está ligado, mas nenhum ativo entrou no recorte atual do worker."}</p>
            </div>
          )}
        </section>
      );
    }

    return (
      <section id={`panel-${currentTab}`} className="snbr-tool-shell">
        <div className="snbr-tool-head">
          <div>
            <h3>{copy.title}</h3>
            <p>{copy.description}</p>
            {copy.explanation ? <p>{copy.explanation}</p> : null}
          </div>
          <button className="snbr-button secondary snbr-popout-button" onClick={() => openPopout(currentTab)} type="button" aria-label={isUsLocale ? `Open ${copy.title} in another screen` : `Abrir ${copy.title} em outra tela`}>
            {isUsLocale ? "Detach" : "Liberar Tela"}
          </button>
        </div>

        <div className="snbr-tool-stack">
          {expandedToolCandidates.map((item, index) => {
            const watchItem = watchUniverse.find((candidate) => candidate.symbol === item.symbol);
            const tone = String(item.trend || "").toLowerCase().includes("alta") || String(item.trend || "").toLowerCase().includes("bull")
              ? "bullish"
              : String(item.trend || "").toLowerCase().includes("baixa") || String(item.trend || "").toLowerCase().includes("bear")
                ? "bearish"
                : "neutral";

            return (
              <div key={`${currentTab}-${item.id}-${index}`} className="snbr-tool-row">
                {(() => {
                  const quote = resolveQuoteForSymbol(item.symbol, publicQuotes, tickerTapeQuotes);
                  const resolvedChangePct = item.changePct ?? watchItem?.changePct ?? quote?.change_pct ?? null;
                  const resolvedPrice = firstFiniteNumber(item.price, watchItem?.price, quote?.price);
                  const resolvedVolume = firstFiniteNumber(item.volume, watchItem?.volume, quote?.volume);
                  const resolvedRsi = item.rsi ?? derivePublicRsi(resolvedChangePct, item.trend || watchItem?.trend || null);
                  const resolvedRvol = deriveRelativeVolume(resolvedVolume);
                  const resolvedAdx = deriveAdx(resolvedChangePct, resolvedRsi, item.trend || watchItem?.trend || null);
                  const resolvedAtrPct = deriveAtrPct(resolvedChangePct, resolvedRsi, resolvedVolume);
                  return (
                <>
                <section className="snbr-plain-panel">
                  <div className="snbr-section-head compact">
                    <div>
                      <h3>{isUsLocale ? "Asset Panel" : "Painel do ativo"}</h3>
                      <p>{isUsLocale ? "Alert from the current lens, with detection time and setup parameters." : "Alerta da lente atual, com horário detectado e parâmetros do setup."}</p>
                    </div>
                    <span className="snbr-chip">{isUsLocale ? "Found" : "Encontrado"}: {formatAiUpdatedAt(normalizeAlertTimestamp(item.timestamp) || normalizeAlertTimestamp(chartLatestEpoch), appLocale)}</span>
                  </div>
                  <button className="snbr-asset-box snbr-asset-box-large" onClick={() => selectTicker(item.symbol)} type="button">
                    <div className="snbr-asset-box-head">
                      <strong>{item.symbol}</strong>
                      <span className={cx("snbr-side-badge", scoreClass(item.score))}>
                        Score {item.score != null ? item.score.toFixed(1) : "n/a"}
                      </span>
                    </div>
                    <span>{item.label}</span>
                    <div className="snbr-asset-box-stats">
                      <div>
                        <small>{isUsLocale ? "Price" : "Preço"}</small>
                        <strong>{formatPrice(resolvedPrice)}</strong>
                      </div>
                      <div>
                        <small>{isUsLocale ? "Change" : "Variação"}</small>
                        <strong>{resolvedChangePct != null ? formatSignedPercent(resolvedChangePct) : "n/a"}</strong>
                      </div>
                      <div>
                        <small>Volume</small>
                        <strong>{formatLiquidityVolume(resolvedVolume, resolvedRvol)}</strong>
                      </div>
                      <div>
                        <small>{isUsLocale ? "AI Score" : "Score IA"}</small>
                        <strong>{item.score != null ? item.score.toFixed(1) : "n/a"}</strong>
                      </div>
                      <div>
                        <small>RSI</small>
                        <strong>{resolvedRsi != null ? resolvedRsi.toFixed(0) : "n/a"}</strong>
                      </div>
                      <div>
                        <small>Bias</small>
                        <strong>{localizeUiText(item.trend || "n/a", appLocale, item.symbol)}</strong>
                      </div>
                    </div>
                  </button>
                </section>

                <section className="snbr-plain-panel">
                  <div className="snbr-section-head compact">
                    <div>
                      <h3>{isUsLocale ? "AI Reads" : "Leituras da IA"}</h3>
                      <p>{isUsLocale ? "Top signals and assets related to the current market context." : "Top sinais e ativos relacionados ao contexto atual do mercado."}</p>
                    </div>
                  </div>
                  <div className="snbr-tool-reading-grid">
                    <div className="snbr-tool-reading-card">
                      <span>{isUsLocale ? "Main read" : "Leitura principal"}</span>
                      <strong>{isUsLocale ? `${item.symbol} in ${localizeUiText(item.trend || "watching", appLocale, item.symbol)}` : `${item.symbol} em ${item.trend || "monitorando"}`}</strong>
                    </div>
                      <div className="snbr-tool-reading-card">
                        <span>{isUsLocale ? "Current score" : "Score atual"}</span>
                        <strong>{item.score != null ? item.score.toFixed(1) : "n/a"}</strong>
                      </div>
                    <div className="snbr-tool-reading-card">
                      <span>{isUsLocale ? "Liquidity / volume" : "Liquidez / volume"}</span>
                        <strong>{formatLiquidityVolume(resolvedVolume, resolvedRvol)}</strong>
                    </div>
                      <div className="snbr-tool-reading-card">
                        <span>{isUsLocale ? "Context" : "Contexto"}</span>
                        <strong className={cx("snbr-tone-tag", tone)}>{tone === "bullish" ? (isUsLocale ? "🐂 Bullish" : "🐂 Touro") : tone === "bearish" ? (isUsLocale ? "🐻 Bearish" : "🐻 Urso") : (isUsLocale ? "Watching" : "Monitorando")}</strong>
                      </div>
                    </div>
                </section>
                </>
                  );
                })()}
              </div>
            );
          })}
        </div>
      </section>
    );
  }

  function renderGrafico() {
    const chartNews = newsRows[0];
    const chartNewsTitle = chartNews
      ? localizeUiText(chartNews.title, appLocale, selectedTicker)
      : (isUsLocale ? "No ticker-specific news" : "Sem notícia específica do ativo");
    const chartNewsText = chartNews
      ? (isUsLocale
        ? localizeUiText(chartNews.traderTakeaway || chartNews.whyItMatters || chartNews.cardSummary, appLocale, selectedTicker)
        : portugueseNewsInsight(chartNews.traderTakeaway || chartNews.whyItMatters || chartNews.cardSummary, selectedTicker))
      : (isUsLocale ? `No ticker-specific news found right now for ${selectedTicker}.` : `Sem notícia específica encontrada agora para ${selectedTicker}.`);
    const showChartNewsBody = !sameUiText(chartNewsTitle, chartNewsText);

    return (
      <div id="panel-grafico" className="snbr-center-stack">
        <section className="snbr-chart-card">
          <div className="snbr-chart-topline">
            <div>
              <h2>{isUsLocale ? "Asset chart" : "Gráfico do ativo"}</h2>
              <p>{isUsLocale ? `VWAP, buy/sell, liquidity and structural read for ${selectedTicker} in one screen.` : `VWAP, compra/venda, liquidez e leitura estrutural de ${selectedTicker} na mesma tela.`}</p>
            </div>
            <div className="snbr-chart-actions">
              <label className="snbr-toggle">
                <input
                  checked={showMarkers}
                  onChange={(event) => updateChartSetting("show_markers", event.target.checked)}
                  type="checkbox"
                />
                <span>{isUsLocale ? "Buy/Sell Tool" : "Compra/Venda Ferramenta"}</span>
              </label>
              <label className="snbr-toggle">
                <input
                  checked={showZones}
                  onChange={(event) => updateChartSetting("show_zones", event.target.checked)}
                  type="checkbox"
                />
                <span>{isUsLocale ? "Liquidity Zones" : "Zonas de Liquidez"}</span>
              </label>
              <button className="snbr-button secondary snbr-popout-button" onClick={() => openPopout("grafico")} type="button">
                {isUsLocale ? "Detach" : "Liberar Tela"}
              </button>
            </div>
          </div>

          <TickerChart chart={chartForDisplay} interval={chartInterval} showMarkers={showMarkers} showZones={showZones} locale={appLocale} />

          <div className="snbr-timeframes">
            {TIMEFRAME_OPTIONS.map((timeframe) => (
              <button
                key={timeframe}
                className={cx("snbr-timeframe", chartInterval === timeframe && "active")}
                onClick={() => setChartInterval(timeframe)}
                type="button"
              >
                {timeframe}
              </button>
            ))}
          </div>

          <div className="snbr-chart-now-strip">
            <div>
              <span>{isUsLocale ? "News now" : "Notícia agora"} · {selectedTicker}</span>
              <strong>{chartNewsTitle}</strong>
              {showChartNewsBody ? <p>{chartNewsText}</p> : null}
            </div>
            {chartNews?.url ? (
              <a className="snbr-button ghost" href={chartNews.url} rel="noreferrer" target="_blank">
                {isUsLocale ? "Open news" : "Abrir notícia"}
              </a>
            ) : (
              <span className="snbr-chip">{isUsLocale ? "Ticker filtered" : "Ticker filtrado"}</span>
            )}
          </div>

          <div className="snbr-mini-metrics">
            {renderMeterCard(
              isUsLocale ? "Sentiment" : "Sentimento",
              sentimentLabel,
              sentimentScore,
              sentimentTone === "bearish" ? "bearish" : sentimentTone === "bullish" ? "bullish" : "neutral",
            )}
            {renderMeterCard(
              volumeMeterTitle,
              volumeLabel,
              volumeScore,
              rawVolumeScore != null && rawVolumeScore >= 65 ? "bullish" : rawVolumeScore != null && rawVolumeScore < 35 ? "bearish" : "neutral",
            )}
          </div>

          {showZones && chartForDisplay?.zones?.length ? (
            <div className="snbr-zone-row">
              {chartForDisplay.zones.map((zone: any) => (
                <span key={`${zone.label}-${zone.price}`} className="snbr-chip">
                  {isUsLocale ? localizeUiText(String(zone.label || "").replace("RESISTENCIA", "RESISTANCE").replace("SUPORTE", "SUPPORT"), appLocale, selectedTicker) : zone.label}: {formatLocalePrice(zone.price, appLocale)}
                </span>
              ))}
            </div>
          ) : null}
        </section>

        <section className="snbr-poll-inline">
          <div className="snbr-plain-panel snbr-poll-shell">
            <div className="snbr-section-head">
              <div>
                <h3>✦ {isUsLocale ? "Poll/Vote" : "Poll/Votar"}</h3>
                <p>{isUsLocale ? "Below the sentiment monitor, the community votes on this asset's weekly thesis." : "Abaixo do monitor de sentimento, a comunidade vota na tese da semana do ativo."}</p>
              </div>
            </div>
            <div className="snbr-poll-card">
              <h4>{localizedActivePoll.question || (isUsLocale ? `Active Poll/Vote for ${selectedTicker}` : `Poll/Votar ativa para ${selectedTicker}`)}</h4>
              <div className="snbr-poll-meta">
                <span>{localizedActivePoll.total_votes} {isUsLocale ? "votes" : "votos"}</span>
                <span>{localizedActivePoll.status || (isUsLocale ? "open" : "aberta")}</span>
              </div>
              <div className="snbr-poll-options">
                {(localizedActivePoll.options || []).map((option) => {
                  const optionPct = localizedActivePoll.total_votes ? (option.pct != null ? option.pct : Math.round((option.votes / localizedActivePoll.total_votes) * 100)) : 0;

                  return (
                    <div key={option.key} className="snbr-poll-option snbr-poll-option-results">
                      {localizedActivePoll.total_votes ? <div className="snbr-poll-progress" style={{ width: `${optionPct}%` }} /> : null}
                      <div className="snbr-poll-copy">
                        <strong>{option.label}</strong>
                        <span>{option.votes} {isUsLocale ? "votes" : "votos"}</span>
                      </div>
                      <div className="snbr-poll-actions">
                        <span className="snbr-poll-pct">{localizedActivePoll.total_votes ? `${optionPct}%` : "--"}</span>
                <button className="snbr-button secondary snbr-poll-vote" onClick={() => handleVote(option.key)} type="button" aria-label={isUsLocale ? `Vote for option ${option.label} on ${selectedTicker}` : `Votar na opção ${option.label} para ${selectedTicker}`}>
                          {isUsLocale ? "Vote" : "Votar"}
                        </button>
                      </div>
                    </div>
                  );
                })}
              </div>
              <div className="snbr-poll-footer">
                <span>{localizedActivePoll.total_votes || 0} {isUsLocale ? "votes" : "votos"}</span>
                <button className="snbr-post-action snbr-poll-comment-cta" onClick={focusPollComposer} type="button" aria-label={isUsLocale ? "Comment on poll" : "Comentar na poll"}>
                  <span>{isUsLocale ? "Comment:" : "Comentar:"}</span>
                  <span aria-hidden="true">💬</span>
                  <span>{pollDiscussionPosts.length} {isUsLocale ? "comments" : "comentarios"}</span>
                </button>
              </div>
              {pollCommentOpen ? (
                <div className="snbr-poll-comment-box">
                  <label className="snbr-profile-field">
                    <span>{isUsLocale ? "Poll/Vote comment" : "Comentário do Poll/Votar"}</span>
                    <textarea
                      ref={pollCommentInputRef}
                      className="snbr-textarea"
                      value={pollCommentText}
                      onChange={(event) => setPollCommentText(event.target.value)}
                      placeholder={isUsLocale ? `Write your comment about the ${selectedTicker} Poll/Vote` : `Escreva seu comentário sobre o Poll/Votar de ${selectedTicker}`}
                    />
                  </label>
                  <div className="snbr-poll-comment-actions">
                    <button className="snbr-button secondary" onClick={() => setPollCommentOpen(false)} type="button">
                      {isUsLocale ? "Close" : "Fechar"}
                    </button>
                    <button className="snbr-button primary" onClick={() => void handleCreatePollComment()} type="button">
                      {pollCommentPosting ? (isUsLocale ? "Posting..." : "Postando...") : (isUsLocale ? "Post Poll/Vote comment" : "Postar comentário do Poll/Votar")}
                    </button>
                  </div>
                </div>
              ) : null}
            </div>
          </div>
        </section>

        {renderComposer()}

        <div className="snbr-feed-column snbr-feed-thread">
          {renderDiscussionList(discussionPosts, `Sem posts ainda para ${selectedTicker}.`)}
        </div>
      </div>
    );
  }

  function renderNews() {
    return (
      <WorkspaceNewsPanel
        locale={appLocale}
        selectedTicker={selectedTicker}
        newsRows={newsRows}
        newsStateText={newsStateText}
        discussionStateText={discussionStateText}
        featuredDiscussion={renderDiscussionList(featuredDiscussionPosts.slice(0, 4), discussionStateText || "Sem discussões em destaque ainda.")}
      />
    );
  }

  function renderEducation() {
    return (
      <WorkspaceEducationPanel
        locale={appLocale}
        helpManualItems={isUsLocale ? HELP_MANUAL_ITEMS_EN : HELP_MANUAL_ITEMS}
        institutionalSections={isUsLocale ? INSTITUTIONAL_SECTIONS_EN : INSTITUTIONAL_SECTIONS}
        educationalSections={isUsLocale ? EDUCATIONAL_HELP_SECTIONS_EN : EDUCATIONAL_HELP_SECTIONS}
        guides={workspace?.help_center.guides || []}
        activeInstitutionalSectionId={selectedInstitutionalSectionId}
      />
    );
  }

  function renderReferrals() {
    const rows = referralLeaderboard?.items || [];
    const ruleText = isUsLocale
      ? "A referral becomes valid only on the 8th day after the referred user pays. Every 3 valid paid referrals gives 1 free month, with no cash refund."
      : "A indicação só valida no 8º dia após o indicado pagar. A cada 3 indicações pagas e válidas, o assinante ganha 1 mês grátis, sem cashback.";
    const emptyText = isUsLocale
      ? "No paid validated referrals yet. The leaderboard only shows referrals that already paid and passed the refund window."
      : "Ainda não há indicações pagas validadas. O ranking só mostra indicados que já pagaram e passaram da janela de reembolso.";

    return (
      <section className="snbr-tool-shell">
        <div className="snbr-tool-head">
          <div>
            <h2>{isUsLocale ? "Referrals" : "Indicações"}</h2>
            <p>{ruleText}</p>
          </div>
          <span className="snbr-chip">{isUsLocale ? "7-day refund window" : "Janela de 7 dias"}</span>
        </div>

        <div className="snbr-tool-reading-grid">
          <div className="snbr-tool-reading-card">
            <span>{isUsLocale ? "Pricing rule" : "Regra comercial"}</span>
            <strong>
              {isUsLocale
                ? "USA/international: $49/month or $500 upfront for 12 months."
                : "Brasil: R$49/mês ou R$500 à vista por 12 meses."}
            </strong>
          </div>
          <div className="snbr-tool-reading-card">
            <span>{isUsLocale ? "Reward rule" : "Regra de prêmio"}</span>
            <strong>
              {isUsLocale
                ? "3 paid referrals = 1 free month. 10 = Badge Vip. 100+ = Leaderboard VIP."
                : "3 indicações pagas = 1 mês grátis. 10 = Badge Vip. 100+ = Leaderboard VIP."}
            </strong>
          </div>
        </div>

        {referralLeaderboardLoading ? (
          <div className="snbr-empty">{isUsLocale ? "Loading referral leaderboard..." : "Carregando ranking de indicações..."}</div>
        ) : referralLeaderboardError ? (
          <div className="snbr-empty">
            {isUsLocale ? "Referral leaderboard unavailable." : "Ranking de indicações indisponível."}
          </div>
        ) : rows.length ? (
          <ol className="snbr-tool-stack">
            {rows.map((row) => (
              <li key={`${row.position}-${row.name}`} className="snbr-tool-reading-card">
                <span>
                  #{row.position} · {row.total_validated} {isUsLocale ? "valid referrals" : "indicações válidas"}
                </span>
                <strong>
                  {row.name}
                  {row.badge ? ` · ${row.badge}` : ""}
                </strong>
                <p>
                  {isUsLocale ? "Paid referred users: " : "Indicados pagos: "}
                  {row.paid_referrals.length ? row.paid_referrals.join(", ") : (isUsLocale ? "none yet" : "nenhum ainda")}
                </p>
              </li>
            ))}
          </ol>
        ) : (
          <div className="snbr-empty">{emptyText}</div>
        )}
      </section>
    );
  }

  function renderCenterPanel() {
    if (currentTab === "grafico") return renderGrafico();
    if (currentTab === "news") return renderNews();
    if (currentTab === "busca") return renderSearchTab();
    if (currentTab === "heat-map") return renderToolTab(TOOL_COPY["heat-map"].title, TOOL_COPY["heat-map"].description);
    if (currentTab === "radar") return renderToolTab(TOOL_COPY.radar.title, TOOL_COPY.radar.description);
    if (currentTab === "breakout-probability") return renderToolTab(TOOL_COPY["breakout-probability"].title, TOOL_COPY["breakout-probability"].description);
    if (currentTab === "volatility-squeeze") return renderToolTab(TOOL_COPY["volatility-squeeze"].title, TOOL_COPY["volatility-squeeze"].description);
    if (currentTab === "institutional-flow") return renderToolTab(TOOL_COPY["institutional-flow"].title, TOOL_COPY["institutional-flow"].description);
    if (currentTab === "smart-money") return renderToolTab(TOOL_COPY["smart-money"].title, TOOL_COPY["smart-money"].description);
    if (currentTab === "accumulation") return renderToolTab(TOOL_COPY.accumulation.title, TOOL_COPY.accumulation.description);
    if (currentTab === "liquidity-sweep") return renderToolTab(TOOL_COPY["liquidity-sweep"].title, TOOL_COPY["liquidity-sweep"].description);
    if (currentTab === "liquidity-map") return renderToolTab(TOOL_COPY["liquidity-map"].title, TOOL_COPY["liquidity-map"].description);
    if (currentTab === "market-regime") return renderToolTab(TOOL_COPY["market-regime"].title, TOOL_COPY["market-regime"].description);
    if (currentTab === "master-score") return renderToolTab(TOOL_COPY["master-score"].title, TOOL_COPY["master-score"].description);
    if (currentTab === "referrals") return renderReferrals();
    if (currentTab === "education") return renderEducation();
    return renderGrafico();
  }

  function renderAuthCard() {
    if (token) {
      return (
        <div className="snbr-side-card">
          <div className="snbr-profile-card">
            {renderAvatar(profileName, access?.email, access?.avatar_url)}
            <div className="snbr-profile-card-copy">
              <strong>{isUsLocale ? "Profile" : "Perfil"}</strong>
              <span>{isUsLocale ? "Your name, photo and email appear in ticker posts." : "Seu nome, foto e email aparecem nos posts do ticker."}</span>
            </div>
          </div>
          <div className="snbr-profile-editor">
            <label className="snbr-profile-field">
              <span>{isUsLocale ? "Name" : "Nome"}</span>
              <input
                className="snbr-input"
                value={profileNameInput}
                onChange={(event) => setProfileNameInput(event.target.value)}
                placeholder={isUsLocale ? "Your feed name" : "Seu nome no feed"}
              />
            </label>
            <label className="snbr-profile-field">
              <span>Email</span>
              <input
                className="snbr-input"
                value={profileEmailInput}
                onChange={(event) => setProfileEmailInput(event.target.value)}
                placeholder="Email"
                type="email"
              />
            </label>
            <div className="snbr-profile-upload-row">
              <button className="snbr-button secondary" onClick={() => profileFileInputRef.current?.click()} type="button">
                {isUsLocale ? "Upload photo" : "Upload da foto"}
              </button>
              <span>{profileFile ? profileFile.name : (profileAvatarUrl ? (isUsLocale ? "Photo loaded" : "Foto carregada") : (isUsLocale ? "No photo" : "Sem foto"))}</span>
            </div>
            <input
              ref={profileFileInputRef}
              className="snbr-hidden-file-input"
              type="file"
              accept="image/png,image/jpeg,image/webp"
              onChange={(event) => setProfileFile(event.target.files?.[0] || null)}
            />
            <div className="snbr-profile-meta">
              <div className="snbr-account-line"><span>{isUsLocale ? "Plan" : "Plano"}</span><strong>{access?.plan || "guest"}</strong></div>
              <div className="snbr-account-line"><span>Status</span><strong>{isUsLocale ? localizeUiText(access?.plan_status || "n/a", appLocale) : (access?.plan_status || "n/a")}</strong></div>
              <div className="snbr-account-line"><span>Telegram</span><strong>{access?.telegram_linked ? `@${access?.telegram_username || (isUsLocale ? "linked" : "vinculado")}` : (access?.access?.telegram ? (isUsLocale ? "ready to link" : "pronto para vincular") : (isUsLocale ? "blocked on current plan" : "bloqueado no plano atual"))}</strong></div>
            </div>
            <button className="snbr-button primary" disabled={profileSaving} onClick={() => void handleSaveProfile()} type="button">
              {profileSaving ? (isUsLocale ? "Saving..." : "Salvando...") : (isUsLocale ? "Save profile" : "Salvar perfil")}
            </button>
          </div>
          {access?.access?.telegram ? (
            <button className="snbr-button secondary" onClick={handleTelegramLinkRequest} type="button">
              {isUsLocale ? "Generate secure Telegram link" : "Gerar link seguro do Telegram"}
            </button>
          ) : null}
          {telegramLink ? (
            <div className="snbr-empty">
              <strong>{isUsLocale ? "Code" : "Codigo"}:</strong> {telegramLink.link_code}
              <br />
              {telegramLink.deep_link ? (
                <a href={telegramLink.deep_link} rel="noreferrer" target="_blank">{isUsLocale ? "Open bot and link" : "Abrir bot e vincular"}</a>
              ) : (
                <span>{isUsLocale ? "Open the official bot and send this code in the /start command." : "Abra o bot oficial e envie este codigo no comando /start."}</span>
              )}
            </div>
          ) : null}
          <button className="snbr-button secondary" onClick={() => void handleLogout()} type="button">{isUsLocale ? "Sign out" : "Sair"}</button>
        </div>
      );
    }

    if (pendingLoginToken) {
      return (
        <div className="snbr-side-card">
          <div className="snbr-section-head compact">
            <div>
              <h3>{isUsLocale ? "Email code" : "Codigo por email"}</h3>
              <p>{isUsLocale ? "Premium account requires verification on each new login." : "Conta Premium pede verificacao a cada novo login."}</p>
            </div>
          </div>
          <div className="snbr-auth">
            <input
              className="snbr-input"
              value={otpCode}
              onChange={(event) => setOtpCode(event.target.value)}
              placeholder={isUsLocale ? "6-digit code" : "Codigo de 6 digitos"}
            />
            <button className="snbr-button primary" onClick={handleVerifyOtp} type="button">{isUsLocale ? "Validate code" : "Validar codigo"}</button>
            <button
              className="snbr-button secondary"
              onClick={() => {
                setPendingLoginToken("");
                setOtpCode("");
                setDebugOtpCode("");
              }}
              type="button"
            >
              {isUsLocale ? "Back" : "Voltar"}
            </button>
            {debugOtpCode ? <div className="snbr-empty">{isUsLocale ? "Local code" : "Codigo local"}: {debugOtpCode}</div> : null}
            {loginError ? <div className="snbr-empty">{loginError}</div> : null}
          </div>
        </div>
      );
    }

    return (
      <div className="snbr-side-card">
        <div className="snbr-section-head compact">
          <div>
            <h3>{isUsLocale ? "Authentication" : "Autenticacao"}</h3>
            <p>{isUsLocale ? "Trial and Free enter directly. Premium confirms login through the email code." : "Trial e Free entram direto. Premium confirma o login pelo codigo no email."}</p>
          </div>
        </div>
        <div className="snbr-auth">
          <input className="snbr-input" value={email} onChange={(event) => setEmail(event.target.value)} placeholder="Email" />
          <input className="snbr-input" value={password} onChange={(event) => setPassword(event.target.value)} placeholder={isUsLocale ? "Password" : "Senha"} type="password" />
          <button className="snbr-button primary" onClick={handleLogin} type="button">{isUsLocale ? "Log in" : "Entrar"}</button>
          {loginError ? <div className="snbr-empty">{loginError}</div> : null}
        </div>
      </div>
    );
  }

  function renderSettingsList(items: UserListEntry[], emptyTitle: string, emptyBody: string, actionLabel: string) {
    if (!items.length) {
      return (
        <div className="snbr-empty-thread">
          <strong>{localizeUiText(emptyTitle, appLocale)}</strong>
          <p>{localizeUiText(emptyBody, appLocale)}</p>
        </div>
      );
    }

    return (
      <div className="snbr-settings-user-list">
        {items.map((item) => (
          <div key={item.id} className="snbr-settings-user-row">
            <div className="snbr-settings-user-main">
              {renderAvatar(item.nome, item.identificador, item.avatarUrl)}
              <div>
                <strong>{item.nome}</strong>
                <span>{item.identificador}</span>
              </div>
            </div>
            <span className="snbr-settings-user-action">{localizeUiText(actionLabel, appLocale)}</span>
          </div>
        ))}
      </div>
    );
  }

  function formatDatePtBr(value?: string | null) {
    if (!value) return "n/a";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return "n/a";
    return date.toLocaleDateString("pt-BR");
  }

  function planLabel(plan?: string | null) {
    const normalized = String(plan || "").toLowerCase();
    if (normalized === "premium") return "Premium";
    if (normalized === "trial") return isUsLocale ? "90-day trial" : "Trial 90 dias";
    if (normalized === "free") return isUsLocale ? "Free" : "Basico";
    return plan || (isUsLocale ? "Guest" : "Visitante");
  }

  function legalAccepted(accessPayload: UserAccess | null) {
    return Boolean(
      accessPayload?.accepted_terms_at &&
      accessPayload?.accepted_privacy_at &&
      accessPayload?.accepted_risk_notice_at,
    );
  }

  function renderUpgradeOptions() {
    const isPremium = String(access?.plan || "").toLowerCase() === "premium";
    const monthlyLabel = isUsLocale ? "$49/month" : "R$49,00 por mes";
    const annualLabel = isUsLocale ? "$500 upfront" : "R$500,00 por ano";
    const subscriptionError = isUsLocale
      ? "International USA subscription must be completed with an eligible non-Brazil international card."
      : "Assinatura deve ser finalizada pelo app Google Play.";
    const annualError = isUsLocale
      ? "Annual USA subscription must be completed with an eligible non-Brazil international card."
      : "Assinatura anual deve ser finalizada pelo app Google Play.";

    return (
      <div className="snbr-upgrade-stack">
        <div className="snbr-upgrade-card">
          <div>
            <strong>{isUsLocale ? "Premium Monthly" : "Premium Mensal"}</strong>
            <span>{monthlyLabel}</span>
          </div>
          <p>{isUsLocale ? "Unlocks web, app, Telegram, full AI tools, rankings and alerts for USA/international accounts." : "Libera app Google Play, webpage, Telegram, IAs completas, ranking e alertas."}</p>
          <button className="snbr-button primary" onClick={() => setLoginError(subscriptionError)} type="button">
            {isPremium ? (isUsLocale ? "Active plan" : "Plano ativo") : (isUsLocale ? "Subscribe USA" : "Assinar pelo app")}
          </button>
        </div>
        <div className="snbr-upgrade-card featured">
          <div>
            <strong>{isUsLocale ? "Premium Annual" : "Premium Anual"}</strong>
            <span>{annualLabel}</span>
          </div>
          <p>{isUsLocale ? "One upfront USA payment. Keeps web, app and Telegram unlocked." : "Desconto a vista em relacao ao mensal. Mantem app, website e Telegram liberados."}</p>
          <button className="snbr-button primary" onClick={() => setLoginError(annualError)} type="button">
            {isPremium ? (isUsLocale ? "Active plan" : "Plano ativo") : (isUsLocale ? "Annual USA" : "Assinar anual")}
          </button>
        </div>
        {isUsLocale ? (
          <small className="snbr-legal-note">
            International account: USA subscription. Use an international card issued outside Brazil; pricing is USD.
          </small>
        ) : null}
        <small className="snbr-legal-note">
          {isUsLocale
            ? "The first app access starts a 90-day trial. After it ends, the account moves to Free if Premium is not active."
            : "O primeiro acesso pelo app entra em Trial por 90 dias. Ao final, a conta migra automaticamente para Basico se nao houver Premium ativo."}
        </small>
      </div>
    );
  }

  function renderAccessCard() {
    if (token) {
      return (
        <div className="snbr-side-card snbr-side-card-highlight">
          <div className="snbr-section-head compact">
            <div>
              <h3>{isUsLocale ? "Platform access" : "Acesso a plataforma"}</h3>
              <p>{isUsLocale ? "Account ready for website, app and Telegram according to the plan." : "Conta pronta para website, app e Telegram de acordo com o plano."}</p>
            </div>
          </div>
          <div className="snbr-profile-card">
            {renderAvatar(profileName, access?.email, access?.avatar_url)}
            <div className="snbr-profile-card-copy">
              <strong>{profileName}</strong>
              <span>{access?.email}</span>
            </div>
          </div>
          <div className="snbr-account-tabs" role="tablist" aria-label={isUsLocale ? "Account" : "Conta"}>
            <button className={cx("snbr-settings-tab", accountPanel === "perfil" && "active")} onClick={() => setAccountPanel("perfil")} type="button">
              {isUsLocale ? "View profile" : "Ver perfil"}
            </button>
            <button className={cx("snbr-settings-tab", accountPanel === "editar" && "active")} onClick={() => setAccountPanel("editar")} type="button">
              {isUsLocale ? "Edit" : "Editar"}
            </button>
            <button className={cx("snbr-settings-tab", accountPanel === "upgrade" && "active")} onClick={() => setAccountPanel("upgrade")} type="button">
              Upgrade
            </button>
          </div>
          <div className="snbr-profile-meta">
            <div className="snbr-account-line"><span>{isUsLocale ? "Plan" : "Plano"}</span><strong>{planLabel(access?.plan || "trial")}</strong></div>
            <div className="snbr-account-line"><span>Status</span><strong>{isUsLocale ? localizeUiText(access?.plan_status || "ativo", appLocale) : (access?.plan_status || "ativo")}</strong></div>
            <div className="snbr-account-line"><span>{isUsLocale ? "Trial ends" : "Trial termina"}</span><strong>{formatDatePtBr(access?.trial_expires_at)}</strong></div>
            <div className="snbr-account-line"><span>Telegram</span><strong>{access?.telegram_linked ? `@${access?.telegram_username || (isUsLocale ? "linked" : "vinculado")}` : (isUsLocale ? "available to link" : "disponível para vincular")}</strong></div>
            <div className="snbr-account-line"><span>Legal</span><strong>{legalAccepted(access) ? (isUsLocale ? "accepted" : "aceito") : (isUsLocale ? "pending" : "pendente")}</strong></div>
          </div>
          {accountPanel === "perfil" ? (
            <div className="snbr-profile-summary">
              <strong>{profileName}</strong>
              <span>{access?.email}</span>
              <small>{isUsLocale ? "Photo, name and email appear in ticker posts and in the community." : "Foto, nome e email aparecem nos posts do ticker e na comunidade."}</small>
            </div>
          ) : null}
          {accountPanel === "editar" ? (
            <div className="snbr-profile-editor">
              <label className="snbr-profile-field">
                <span>{isUsLocale ? "Name" : "Nome"}</span>
                <input className="snbr-input" value={profileNameInput} onChange={(event) => setProfileNameInput(event.target.value)} placeholder={isUsLocale ? "Your feed name" : "Seu nome no feed"} />
              </label>
              <label className="snbr-profile-field">
                <span>Email</span>
                <input className="snbr-input" value={profileEmailInput} onChange={(event) => setProfileEmailInput(event.target.value)} placeholder="Email" type="email" />
              </label>
              <div className="snbr-profile-upload-row">
                <button className="snbr-button secondary" onClick={() => profileFileInputRef.current?.click()} type="button">
                  {isUsLocale ? "Upload photo" : "Upload da foto"}
                </button>
                <span>{profileFile ? profileFile.name : (profileAvatarUrl ? (isUsLocale ? "Photo loaded" : "Foto carregada") : (isUsLocale ? "No photo" : "Sem foto"))}</span>
              </div>
              <input
                ref={profileFileInputRef}
                className="snbr-hidden-file-input"
                type="file"
                accept="image/png,image/jpeg,image/webp"
                onChange={(event) => setProfileFile(event.target.files?.[0] || null)}
              />
              <button className="snbr-button primary" disabled={profileSaving} onClick={() => void handleSaveProfile()} type="button">
                {profileSaving ? (isUsLocale ? "Saving..." : "Salvando...") : (isUsLocale ? "Save profile" : "Salvar perfil")}
              </button>
            </div>
          ) : null}
          {accountPanel === "upgrade" ? renderUpgradeOptions() : null}
          <div className="snbr-legal-note">
            {isUsLocale ? "Google Play app and legal terms are the official entry. Premium unlocks app, website and Telegram." : "App Google Play e o termo legal sao a entrada oficial. Premium libera app, website e Telegram."}
          </div>
          <button className="snbr-button secondary" onClick={() => void handleLogout()} type="button">{isUsLocale ? "Sign out" : "Sair"}</button>
        </div>
      );
    }

    if (pendingLoginToken) {
      return (
        <div className="snbr-side-card snbr-side-card-highlight">
          <div className="snbr-section-head compact">
            <div>
              <h3>{isUsLocale ? "Platform access" : "Acesso a plataforma"}</h3>
              <p>{isUsLocale ? "Enter the email code to complete login." : "Digite o código enviado por email para concluir o login."}</p>
            </div>
          </div>
          <div className="snbr-auth">
            <input
              ref={loginEmailInputRef}
              className="snbr-input"
              value={otpCode}
              onChange={(event) => setOtpCode(event.target.value)}
              placeholder={isUsLocale ? "6-digit code" : "Código de 6 dígitos"}
            />
            <button className="snbr-button primary" onClick={handleVerifyOtp} type="button">{isUsLocale ? "Validate code" : "Validar código"}</button>
            <button
              className="snbr-button secondary"
              onClick={() => {
                setPendingLoginToken("");
                setOtpCode("");
                setDebugOtpCode("");
              }}
              type="button"
            >
              {isUsLocale ? "Back" : "Voltar"}
            </button>
            {debugOtpCode ? <div className="snbr-empty">{isUsLocale ? "Local code" : "Código local"}: {debugOtpCode}</div> : null}
            {loginError ? <div className="snbr-empty">{loginError}</div> : null}
          </div>
        </div>
      );
    }

    return (
      <div className="snbr-side-card snbr-side-card-highlight">
        <div className="snbr-section-head compact">
          <div>
            <h3>{isUsLocale ? "Platform access" : "Acesso a plataforma"}</h3>
            <p>{isUsLocale ? "Log in to post, comment and use the full account." : "Faça login para publicar, comentar e usar a conta completa."}</p>
          </div>
        </div>
        <div className="snbr-auth">
          <input ref={loginEmailInputRef} className="snbr-input" value={email} onChange={(event) => setEmail(event.target.value)} placeholder="Email" />
          <input className="snbr-input" value={password} onChange={(event) => setPassword(event.target.value)} placeholder={isUsLocale ? "Password" : "Senha"} type="password" />
          <button className="snbr-button primary" onClick={handleLogin} type="button">{isUsLocale ? "Log in" : "Entrar"}</button>
          {loginError ? <div className="snbr-empty">{loginError}</div> : null}
        </div>
      </div>
    );
  }

  function renderNotificationCard() {
    const notice = MAINTENANCE_NOTICES[0];

    return (
      <div className="snbr-side-card">
        <button
          className="snbr-side-card-trigger"
          onClick={() => setNotificationOpen((value) => !value)}
          type="button"
          aria-expanded={notificationOpen}
        >
          <div>
            <h3>{isUsLocale ? "Notifications" : "Notificacao"}</h3>
            <p>{isUsLocale ? "Notices to be published on website, app and Telegram." : "Avisos a serem publicados no website, app e Telegram."}</p>
          </div>
          <span>{notificationOpen ? (isUsLocale ? "Close" : "Fechar") : (isUsLocale ? "Open" : "Abrir")}</span>
        </button>
        {notificationOpen ? (
          <div className="snbr-settings-detail-row">
            <span>{isUsLocale ? "Scheduled maintenance" : (notice?.titulo || "Sem aviso no momento.")}</span>
            <small>{isUsLocale ? "Operational notices will appear here for website, app and Telegram." : (notice?.corpo || "Nenhum comunicado operacional agora.")}</small>
          </div>
        ) : null}
      </div>
    );
  }

  function renderToolsCard() {
    return (
      <div className="snbr-side-card">
        <div className="snbr-section-head compact">
          <div>
            <h3>{isUsLocale ? "Tools" : "Ferramentas"}</h3>
            <p>{isUsLocale ? "Account preferences, blocked and muted users." : "Preferencias da conta, bloqueados e silenciados."}</p>
          </div>
        </div>
        <div className="snbr-settings-tabs" role="tablist" aria-label={isUsLocale ? "Settings tools" : "Ferramentas de configuracao"}>
          <button
            className={cx("snbr-settings-tab", settingsTab === "preferencias" && "active")}
            onClick={() => {
              setSettingsTab("preferencias");
            }}
            type="button"
          >
            {isUsLocale ? "Preferences" : "Preferencias"}
          </button>
          <button
            className={cx("snbr-settings-tab", settingsTab === "bloqueados" && "active")}
            onClick={() => {
              setSettingsTab("bloqueados");
            }}
            type="button"
          >
            {isUsLocale ? "Blocked" : "Bloqueados"}
          </button>
          <button
            className={cx("snbr-settings-tab", settingsTab === "silenciados" && "active")}
            onClick={() => {
              setSettingsTab("silenciados");
            }}
            type="button"
          >
            {isUsLocale ? "Muted" : "Silenciados"}
          </button>
        </div>

          {settingsTab === "preferencias" ? (
            <div className="snbr-settings-stack">
              <div className="snbr-settings-section">
                <strong>Display</strong>
                <div className="snbr-settings-toggle-row">
                  <span>Dark mode</span>
                  <button className={cx("snbr-switch", darkMode && "active")} onClick={() => setDarkMode((value) => !value)} type="button" aria-pressed={darkMode}>
                    <span />
                  </button>
                </div>
              </div>
            </div>
          ) : null}

          {settingsTab === "bloqueados"
            ? renderSettingsList(
                blockedUsers,
                "Nenhum perfil bloqueado.",
                "Quando você bloquear alguém no feed, ele aparecerá aqui.",
                "Bloqueado",
              )
            : null}

          {settingsTab === "silenciados"
            ? renderSettingsList(
                silencedUsers,
                "Nenhum perfil silenciado.",
                "Quando você silenciar alguém no feed, ele aparecerá aqui.",
                "Silenciado",
              )
            : null}
        </div>
    );
  }

  function renderRightRail() {
    return (
      <WorkspaceRightRail
        mobileInsightsOpen={mobileInsightsOpen}
        onToggleMobileInsights={() => setMobileInsightsOpen((value) => !value)}
        stats={stats}
        newsRows={newsRows}
        discussionPosts={discussionPosts}
        activePoll={localizedActivePoll}
        selectedTicker={selectedTicker}
        token={token}
        access={access}
        mediaProvider={String((mediaStatus?.provider as string) || workspace?.media?.provider || "local")}
        locale={appLocale}
        onSelectTicker={selectTicker}
      />
    );
  }

  if (focusedTab) {
    const focusedLabel = getTabMeta(currentTabs.find((tab) => tab.id === currentTab) || FALLBACK_TABS[0], appLocale);

    return (
      <div className={cx("snbr-app", darkMode && "theme-dark", "snbr-popout-mode")}>
      <div className="snbr-popout-header">
          <div>
            <h1>{focusedLabel.label}</h1>
            <p>{isUsLocale ? `${selectedTicker} in detached monitor mode.` : `${selectedTicker} em modo destacavel para monitor separado.`}</p>
          </div>
          <div className="snbr-symbol-pills">
            <span className="snbr-chip">Ticker: {selectedTicker}</span>
            <span className="snbr-chip">{isUsLocale ? "Plan" : "Plano"}: {access?.plan || "guest"}</span>
          </div>
        </div>
        <div className="snbr-popout-content">
          {error ? <div className="snbr-empty">{isUsLocale ? "Error" : "Erro"}: {error}</div> : null}
          {renderCenterPanel()}
        </div>
      </div>
    );
  }

  return (
    <div className={cx("snbr-app", darkMode && "theme-dark")}>
      <a className="snbr-skip-link" href="#snbr-main-content">{isUsLocale ? "Skip to main content" : "Pular para o conteúdo principal"}</a>
      <WorkspaceLeftRail
          locale={appLocale}
          railRef={leftRailRef}
          mobileWatchlistOpen={mobileWatchlistOpen}
          onToggleMobileWatchlist={() => setMobileWatchlistOpen((value) => !value)}
          watchlistQuery={watchlistQuery}
          onWatchlistQueryChange={(nextValue) => {
            setWatchlistQuery(nextValue);
            if (!focusedTab && currentTab === "busca" && !nextValue.trim()) setActiveTab("grafico");
          }}
          onWatchlistQueryEnter={applyTicker}
          onApplyTicker={applyTicker}
          onAddTicker={handleAddToActiveList}
          onRemoveTicker={() => handleRemoveFromActiveList()}
          watchCategory={watchCategory}
          onSetWatchCategory={setWatchCategory}
          activeWatchCount={activeWatchSymbols.length}
          accessCard={renderAccessCard()}
          authCard={null}
          notificationCard={renderNotificationCard()}
          toolsCard={renderToolsCard()}
          watchlistContent={renderWatchlist()}
          institutionalSections={isUsLocale ? INSTITUTIONAL_SECTIONS_EN : INSTITUTIONAL_SECTIONS}
          onOpenInstitutionalSection={openInstitutionalSection}
        />

      <main className="snbr-symbol-page" id="snbr-main-content">
        <nav className="snbr-symbol-tabs snbr-top-tabs" aria-label={isUsLocale ? "Symbol tabs" : "Tabs do simbolo"} role="tablist">
          <button className="snbr-tab-scroll" onClick={() => scrollTabs("left")} type="button" aria-label={isUsLocale ? "Move tabs left" : "Mover tabs para a esquerda"}>
            ◀
          </button>
          <div className="snbr-tab-list" ref={tabListRef}>
            {visibleTabs.map((tab) => {
              const meta = getTabMeta(tab, appLocale);

              return (
                <div key={tab.id} className="snbr-symbol-tab-shell">
                  <button
                    className={cx("snbr-symbol-tab", currentTab === tab.id && "active")}
                    onClick={() => setActiveTab(tab.id)}
                    aria-selected={currentTab === tab.id}
                    aria-controls={`panel-${tab.id}`}
                    aria-label={meta.label}
                    role="tab"
                    type="button"
                    title={meta.label}
                  >
                    <span>{topTabText(tab.id, meta.short, appLocale)}</span>
                  </button>
                </div>
              );
            })}
          </div>
          <button className="snbr-tab-scroll" onClick={() => scrollTabs("right")} type="button" aria-label={isUsLocale ? "Move tabs right" : "Mover tabs para a direita"}>
            ▶
          </button>
          <div className="snbr-locale-switch" aria-label={isUsLocale ? "Language selector" : "Seletor de idioma"}>
            <button
              className={cx("snbr-locale-button", appLocale === "pt-BR" && "active")}
              onClick={() => setAppLocale("pt-BR")}
              type="button"
              aria-label="BR"
              aria-pressed={appLocale === "pt-BR"}
              title="Portugues do Brasil"
            >
              <span className="snbr-locale-flag br" aria-hidden="true" />
              <span>BR</span>
            </button>
            <button
              className={cx("snbr-locale-button", appLocale === "en-US" && "active")}
              onClick={() => setAppLocale("en-US")}
              type="button"
              aria-label="USA"
              aria-pressed={appLocale === "en-US"}
              title="English / USA"
            >
              <span className="snbr-locale-flag us" aria-hidden="true" />
              <span>USA</span>
            </button>
          </div>
          <button
            className="snbr-theme-toggle"
            onClick={() => setDarkMode((value) => !value)}
            type="button"
            aria-label={darkMode ? (isUsLocale ? "Switch to light mode" : "Voltar para tema claro") : (isUsLocale ? "Switch to dark mode" : "Ativar tema escuro")}
            title={darkMode ? (isUsLocale ? "Light mode" : "Tema claro") : (isUsLocale ? "Dark mode" : "Tema escuro")}
          >
            {darkMode ? "☀" : "☾"}
          </button>
        </nav>

        {isUsLocale ? (
          <div className="snbr-locale-notice" role="status">
            International account: USA subscription. Premium is $49/month or $500 upfront for international cards outside Brazil.
          </div>
        ) : null}

        <section className="snbr-ticker-tape">
          <button className="snbr-tape-toggle" onClick={() => setTickerTapePaused((value) => !value)} type="button">
            {tickerTapePaused ? "▶" : "⏸"}
          </button>
          <div className="snbr-tape-viewport">
            <div className={cx("snbr-tape-track", tickerTapePaused && "paused")}>
              {[...tapeItems, ...tapeItems].map((item, index) => (
                <button
                  key={`${item.symbol}-${index}`}
                  className="snbr-tape-item"
                  onClick={() => selectTicker(item.symbol)}
                  type="button"
                >
                  <strong>{item.symbol}</strong>
                  <span className={cx("snbr-tape-value", movementClass(item.changePct, item.trend, item.score))}>
                    {movementArrow(movementClass(item.changePct, item.trend, item.score))}{" "}
                    {formatMarketMovementText(item)}
                  </span>
                </button>
              ))}
            </div>
          </div>
        </section>

        {showSymbolHeader ? (
          <section className="snbr-symbol-header">
            <div className="snbr-symbol-main">
              <div className="snbr-breadcrumb">Home / Symbol / {selectedTicker}</div>
              <div className="snbr-symbol-title-row">
                <div className="snbr-symbol-logo">{selectedTicker.slice(0, 1)}</div>
                <div>
                  <h2>{selectedTicker}</h2>
                  <p>{symbolLabel}</p>
                </div>
              </div>
              <div className="snbr-price-line">
                <strong>{formatAssetMoney(displayQuote?.price, selectedTicker, appLocale)}</strong>
                <span className={cx("snbr-price-change", priceDirectionClass)}>
                  {formatSignedPercent(displayQuote?.change_pct)}
                </span>
              </div>
              {hasPriceMovement ? (
                <div className={cx("snbr-after-hours-line", priceDirectionClass)}>
                  <span>{movementArrow(priceDirectionClass)}</span>
                  <strong>{priceMovementValue != null ? formatLocalePrice(priceMovementValue, appLocale) : "n/a"}</strong>
                  <span>{priceMovementPercent != null ? `(${formatSignedPercent(priceMovementPercent)})` : ""}</span>
                  <small>{priceMovementLabel}</small>
                </div>
              ) : null}
            </div>

            <div className="snbr-stat-strip">
              {stats.map((item) => (
                <div key={item.label} className="snbr-stat-cell">
                  <span>{item.label}</span>
                  <strong>{item.value}</strong>
                </div>
              ))}
            </div>
          </section>
        ) : null}

        <section className="snbr-main-column">
          {error ? <div className="snbr-empty">Erro: {error}</div> : null}
          {loading && token ? <div className="snbr-empty">Carregando contexto do usuario...</div> : null}
          {guestCta && showSymbolHeader ? (
            <div className="snbr-guest-note">
              <strong>{isUsLocale ? "Guest mode active." : "Modo visitante ativo."}</strong>
              <span>{isUsLocale ? "Login unlocks full interaction, chat, posting and protected product data." : "Login libera interacao completa, chat, publicacao e dados protegidos do produto."}</span>
            </div>
          ) : null}
          {showSymbolHeader ? (
            <section className="snbr-workspace-guide" aria-label={isUsLocale ? "Workspace reading mode" : "Modo de leitura do workspace"}>
              <div className="snbr-workspace-guide-head">
                <div>
                  <strong>{focusGuide.title}</strong>
                  <p>{focusGuide.body}</p>
                </div>
                <div className="snbr-persona-switch" role="tablist" aria-label={isUsLocale ? "Workspace use profile" : "Perfil de uso do workspace"}>
                  {(Object.keys(WORKSPACE_PERSONAS) as WorkspacePersona[]).map((personaKey) => (
                    <button
                      key={personaKey}
                      className={cx("snbr-persona-chip", workspacePersona === personaKey && "active")}
                      onClick={() => setWorkspacePersona(personaKey)}
                      type="button"
                      role="tab"
                      aria-selected={workspacePersona === personaKey}
                      title={(isUsLocale ? WORKSPACE_PERSONAS_EN : WORKSPACE_PERSONAS)[personaKey].subtitle}
                    >
                      {(isUsLocale ? WORKSPACE_PERSONAS_EN : WORKSPACE_PERSONAS)[personaKey].label}
                    </button>
                  ))}
                </div>
              </div>
              <div className="snbr-workspace-guide-grid">
                <article className="snbr-workspace-guide-card">
                  <span className="snbr-guide-kicker">{isUsLocale ? "Priority" : "Prioridade"}</span>
                  <strong>{(isUsLocale ? WORKSPACE_PERSONAS_EN : WORKSPACE_PERSONAS)[workspacePersona].subtitle}</strong>
                  <p>{focusGuide.emphasis}</p>
                </article>
                {focusGuide.cards.map((card) => (
                  <article key={`${card.label}-${card.value}`} className="snbr-workspace-guide-card subtle">
                    <span className="snbr-guide-kicker">{card.label}</span>
                    <p>{card.value}</p>
                  </article>
                ))}
              </div>
            </section>
          ) : null}
          {renderCenterPanel()}
        </section>
      </main>
    </div>
  );
}
