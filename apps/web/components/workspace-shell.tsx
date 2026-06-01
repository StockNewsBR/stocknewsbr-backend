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
  getChatHistory,
  getFeed,
  getNews,
  getPublicMarketBundle,
  getPublicQuotesRobust,
  getPoll,
  searchAssets,
  getWorkspace,
  getWorkspaceTickerBundle,
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
  PublicAiToolsPayload,
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
  show_price_line: boolean;
  show_vwap: boolean;
  show_averages: boolean;
  show_macd: boolean;
  show_rsi: boolean;
  show_supertrend: boolean;
  show_volume: boolean;
};

type WatchlistItem = {
  symbol: string;
  label: string;
  category: string;
  price?: number | null;
  changePct?: number | null;
  change?: number | null;
  volume?: number | null;
  averageVolume?: number | null;
  relVolume?: number | null;
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

function renderCommercialPricingNote(locale: AppLocale) {
  if (locale === "en-US") {
    return (
      <>
        <span>Pricing and plan information:</span>
        <br />
        <br />
        <span>Price operations, payments, plan upgrades (Trial to Pro or Basic to Pro), cancellations and refunds are available exclusively through Google Play.</span>
        <br />
        <br />
        <span>Soon, these features will also be available in the Apple Store.</span>
        <br />
        <br />
        <span>Access for Apple users:</span>
        <br />
        <br />
        <span>While the Apple Store integration is not available, users can access the app directly through play.google.com.</span>
        <br />
        <br />
        <span>The login and password used on the site are the same as the app, ensuring full access to the web version.</span>
      </>
    );
  }

  return (
    <>
      <span>Informações sobre preços e planos:</span>
      <br />
      <br />
      <span>Operações de preço, pagamentos, upgrades de plano (Trial para Pro ou Básico para Pro), cancelamentos e reembolsos estão disponíveis exclusivamente pelo Google Play.</span>
      <br />
      <br />
      <span>Em breve, essas funcionalidades também estarão disponíveis na Apple Store.</span>
      <br />
      <br />
      <span>Acesso para usuários Apple:</span>
      <br />
      <br />
      <span>Enquanto a integração com a Apple Store não está disponível, os usuários podem acessar o aplicativo diretamente pelo site play.google.com.</span>
      <br />
      <br />
      <span>O login e a senha utilizados no site são os mesmos do aplicativo, garantindo acesso completo às funcionalidades na versão web.</span>
    </>
  );
}

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
  grafico: { label: "📈 Gráfico IA / Rede Social", short: "Gráfico/Rede Social" },
  news: { label: "📰 Notícias", short: "Notícias" },
  busca: { label: "🔎 Busca", short: "Busca" },
  "heat-map": { label: "🗺 Mapa de Calor", short: "Mapa" },
  radar: { label: "⚡ Radar", short: "Radar" },
  "breakout-probability": { label: "🎯 Breakout", short: "Breakout" },
  "volatility-squeeze": { label: "🟣 Squeeze", short: "Squeeze" },
  "institutional-flow": { label: "🏦 Fluxo Institucional", short: "Fluxo" },
  "smart-money": { label: "💼 Dinheiro Inteligente", short: "Smart" },
  accumulation: { label: "📦 Acumulação", short: "Acumulação" },
  "liquidity-sweep": { label: "🧲 Varredura de Liquidez", short: "Varredura" },
  "liquidity-map": { label: "🧭 Mapa de Liquidez", short: "Liquidez" },
  "market-regime": { label: "📊 Regime de Mercado", short: "Regime" },
  "master-score": { label: "⭐ Score Mestre", short: "Score Mestre" },
  referrals: { label: "🤝 Indicações", short: "Indicações" },
  education: { label: "🎓 Ajuda ao Trader", short: "Ajuda ao Trader" },
};

const TAB_META_EN: Record<string, { label: string; short: string }> = {
  grafico: { label: "📈 AI Chart / Social Network", short: "Chart/Social" },
  news: { label: "📰 News", short: "News" },
  busca: { label: "🔎 Search", short: "Search" },
  "heat-map": { label: "🗺 Heat Map", short: "Heat Map" },
  radar: { label: "⚡ Radar", short: "Radar" },
  "breakout-probability": { label: "🎯 Breakout", short: "Breakout" },
  "volatility-squeeze": { label: "🟣 Squeeze", short: "Squeeze" },
  "institutional-flow": { label: "🏦 Institutional Flow", short: "Flow" },
  "smart-money": { label: "💼 Smart Money", short: "Smart" },
  accumulation: { label: "📦 Accumulation", short: "Accumulation" },
  "liquidity-sweep": { label: "🧲 Liquidity Sweep", short: "Sweep" },
  "liquidity-map": { label: "🧭 Liquidity Map", short: "Liquidity Map" },
  "market-regime": { label: "📊 Market Regime", short: "Regime" },
  "master-score": { label: "⭐ Master Score", short: "Master Score" },
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
    label: "Pro",
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
    label: "Pro",
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

const VISIBLE_WORKSPACE_PERSONAS: WorkspacePersona[] = ["guiado"];

const TOP_TAB_TEXT: Record<string, string> = {
  grafico: "Gráfico IA / Rede Social",
  news: "Notícias",
  "heat-map": "Mapa de Calor",
  radar: "Radar",
  "breakout-probability": "Breakout",
  "volatility-squeeze": "Squeeze",
  "institutional-flow": "Fluxo",
  "smart-money": "Smart Money",
  accumulation: "Acumulação",
  "liquidity-sweep": "Varredura",
  "liquidity-map": "Mapa de Liquidez",
  "market-regime": "Regime",
  "master-score": "Score Mestre",
  referrals: "Indicações",
  education: "Ajuda ao Trader",
};

const TOP_TAB_TEXT_EN: Record<string, string> = {
  grafico: "AI Chart / Social",
  news: "News",
  "heat-map": "Heat Map",
  radar: "Radar",
  "breakout-probability": "Breakout",
  "volatility-squeeze": "Squeeze",
  "institutional-flow": "Flow",
  "smart-money": "Smart Money",
  accumulation: "Accumulation",
  "liquidity-sweep": "Sweep",
  "liquidity-map": "Liquidity Map",
  "market-regime": "Regime",
  "master-score": "Master Score",
  referrals: "Referrals",
  education: "Help",
};

const TAB_ORDER = [
  "grafico",
  "news",
  "master-score",
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
  "referrals",
  "education",
];

const TOP_BAR_TAB_IDS = TAB_ORDER.filter((id) => id !== "busca");
const SIMPLE_TOP_TAB_IDS = new Set(["grafico", "news", "master-score", "referrals", "education"]);
const WORKSPACE_MODE_STORAGE_KEY = "stocknewsbr.workspace_mode";
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
  { id: "grafico", title: "Gráfico IA / Rede Social" },
  { id: "news", title: "Notícias" },
  { id: "master-score", title: "Score Mestre" },
  { id: "busca", title: "Busca" },
  { id: "heat-map", title: "Mapa de Calor" },
  { id: "radar", title: "Radar" },
  { id: "breakout-probability", title: "Breakout" },
  { id: "volatility-squeeze", title: "Squeeze" },
  { id: "institutional-flow", title: "Fluxo Institucional" },
  { id: "smart-money", title: "Dinheiro Inteligente" },
  { id: "accumulation", title: "Acumulação" },
  { id: "liquidity-sweep", title: "Varredura de Liquidez" },
  { id: "liquidity-map", title: "Mapa de Liquidez" },
  { id: "market-regime", title: "Regime de Mercado" },
  { id: "referrals", title: "Indicações" },
  { id: "education", title: "Ajuda ao Trader" },
];

const CATEGORY_ORDER = ["B3", "BDR", "Crypto", "USA"] as const;
const DEFAULT_CHART_SETTINGS: ChartSettings = {
  show_markers: true,
  show_zones: true,
  show_price_line: true,
  show_vwap: true,
  show_averages: true,
  show_macd: false,
  show_rsi: false,
  show_supertrend: true,
  show_volume: true,
};
const APP_LOCALE_STORAGE_KEY = "snbr-app-locale";
const AI_ALERT_HISTORY_STORAGE_KEY = "snbr-ai-alert-history-v6";
const AI_TOOL_SOUND_STORAGE_KEY = "stocknewsbr.ai_tool_sound.v1";
const AI_DEAL_SOUND_URL = "/sounds/ka-ching.mp3";
const MAINTENANCE_NOTICES: Array<{ id: string; titulo: string; corpo: string }> = [];
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
        ? "Mini Bovespa Index"
        : "Mini Commercial Dollar"
      : root === "WIN"
        ? "Mini Indice Bovespa"
        : "Mini Dolar";
  const monthName =
    locale === "en-US" ? FUTURES_MONTH_NAMES_EN[monthCode] || monthCode : FUTURES_MONTH_NAMES[monthCode] || monthCode;
  return `${contractName} ${monthName}/20${year}`;
}

const WATCHLIST_B3 = [
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
  "F", "AAL", "BA",
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
  "📈 Gráfico IA → exibe sinais no gráfico: COMPRA, VENDA A DESCOBERTO ou ⚠ encerrar posição.",
  "⭐ AI Score Mestre → pontuação geral da oportunidade (90 = forte, 70 = moderada, <50 = fraca). Revê todas as IAs e gera o Score Mestre.",
  "🧠 AI Heat Map → mostra ativos mais fortes (🟢 compra) e mais fracos (🔴 venda).",
  "⚡ AI Radar → detecta ativos que começaram a se mover com velocidade.",
  "🎯 AI Probabilidade de Breakout → indica rompimento de resistências importantes.",
  "🟣 AI Compressão de Volatilidade → alerta quando o mercado está quieto e pode explodir.",
  "🏦 AI Fluxo Institucional → identifica entrada de grandes investidores.",
  "💰 AI Dinheiro Inteligente → revela sinais dos grandes players antes de movimentos fortes.",
  "🏛 AI Acumulação → detecta compras discretas de instituições.",
  "🧲 AI Varredura de Liquidez → mostra rompimentos falsos para buscar liquidez.",
  "🧭 AI Mapa de Liquidez → indica onde há concentração de stops e liquidez.",
  "📊 AI Regime de Mercado → classifica o mercado: 📈 alta, 📉 baixa ou ➡ lateral.",
];

const HELP_MANUAL_ITEMS_EN = [
  "📈 AI Chart / Social Network → displays BUY LONG, CLOSE LONG, SELL SHORT or CLOSE SHORT markers.",
  "⭐ AI Master Score → consolidated opportunity score (90 = strong, 70 = moderate, <50 = weak). It reviews all AIs and generates the Master Score.",
  "🧠 AI Heat Map → shows the strongest assets (🟢 buy) and weakest assets (🔴 sell).",
  "⚡ AI Radar → detects assets that started moving with speed.",
  "🎯 AI Breakout Probability → highlights important resistance breakouts.",
  "🟣 AI Volatility Squeeze → warns when the market is quiet and may expand.",
  "🏦 AI Institutional Flow → identifies large investor participation.",
  "💰 AI Smart Money → reveals large-player signals before stronger moves.",
  "🏛 AI Accumulation → detects discreet institutional buying.",
  "🧲 AI Liquidity Sweep → flags false breakouts used to seek liquidity.",
  "🧭 AI Liquidity Map → shows where stops and liquidity are concentrated.",
  "📊 AI Market Regime → classifies the market: 📈 uptrend, 📉 downtrend or ➡ range.",
];

const EDUCATIONAL_HELP_SECTIONS = [
  {
    title: "📚 Guia Rápido StockNewsBR",
    body: [
      "Inteligência de Mercado com IA para Traders da B3, BDRs, Ações dos EUA e Cripto.",
      "Nosso objetivo é simples: transformar dados complexos em oportunidades claras e práticas para o day trader.",
    ],
  },
  {
    title: "🏛 Sobre a Empresa",
    body: [
      "StockNewsBR é a plataforma inteligente que transforma dados em oportunidades de investimento.",
      "Com tecnologia de Inteligência Artificial, métodos de finanças quânticas e estratégias institucionais inspiradas nos terminais de Hedge Funds norte-americanos, oferecemos análises exclusivas para traders da B3, BDRs, ações dos Estados Unidos e criptoativos.",
      "Nosso compromisso é fornecer insights rápidos, precisos e sofisticados, apoiando decisões estratégicas e fortalecendo sua atuação no mercado financeiro.",
    ],
  },
  {
    title: "🖥️ Plataforma Web Trader Desk",
    body: [
      "Inspirada nos terminais de Hedge Funds dos EUA.",
      "• Suporte a múltiplos monitores. Basta clicar em \"Liberar Tela\" em cada aba.",
      "• Velocidade e análise avançada.",
      "• Interface simples e prática para operação diária.",
      "Exemplo de uso: Monitor 1 → Heat Map; Monitor 2 → Radar; Monitor 3 → Breakout.",
      "Com apenas um monitor, basta alternar entre as abas da plataforma.",
    ],
  },
  {
    title: "⚠ Importante",
    body: [
      "As análises são apoio inteligente, não garantias.",
      "Gestão de risco e disciplina são essenciais.",
      "O mercado é dinâmico: esteja preparado para agir rápido.",
    ],
  },
  {
    title: "🎯 Por que escolher StockNewsBR?",
    body: [
      "Clareza: transformamos informações complexas em sinais simples e objetivos.",
      "Velocidade: análises em tempo real para aproveitar cada oportunidade.",
      "Confiança: tecnologia de IA, cálculos de finanças quânticas e estratégias institucionais inspiradas nos Hedge Funds dos EUA.",
      "Educação: explicações e glossários práticos que você aplica diretamente nas suas operações.",
      "Inteligência: suporte estratégico para decisões mais seguras e rentáveis.",
      "StockNewsBR: Inteligência de Mercado com estrutura institucional e IA's, gerando ao trader uma tomada de decisão superior. Boas Trades !!! $$$$$",
    ],
  },
];

const EDUCATIONAL_HELP_SECTIONS_EN = [
  {
    title: "📚 Quick StockNewsBR Guide",
    body: [
      "Market Intelligence with AI for B3, BDRs, US Stocks and Crypto traders.",
      "The goal is simple: turn complex data into clear, practical opportunities for day traders.",
    ],
  },
  {
    title: "🏛 About the Company",
    body: [
      "StockNewsBR is an intelligent platform that turns data into investment opportunities.",
      "With Artificial Intelligence, quantum finance methods and institutional strategies inspired by North American hedge fund terminals, we provide exclusive analysis for B3, BDR, United States stocks and crypto traders.",
      "Our commitment is to deliver fast, precise and sophisticated insights, supporting strategic decisions and strengthening your performance in the financial market.",
    ],
  },
  {
    title: "🖥️ Web Trader Desk",
    body: [
      "Inspired by US hedge fund terminals.",
      "• Multi-monitor support. Just click \"Detach\" in each tab.",
      "• Speed and advanced analysis.",
      "• Simple, practical interface for daily trading.",
      "Example: Monitor 1 → Heat Map; Monitor 2 → Radar; Monitor 3 → Breakout.",
      "With one monitor, just switch between the platform tabs.",
    ],
  },
  {
    title: "⚠ Important",
    body: [
      "The analyses are intelligent support, not guarantees.",
      "Risk management and discipline are essential.",
      "The market is dynamic: be ready to act quickly.",
    ],
  },
  {
    title: "🎯 Why choose StockNewsBR?",
    body: [
      "Clarity: we turn complex information into simple, objective signals.",
      "Speed: real-time analysis to capture every opportunity.",
      "Confidence: AI, quantum finance methods and institutional strategies inspired by US hedge funds.",
      "Education: practical explanations and glossaries you can apply directly in your operations.",
      "Intelligence: strategic support for safer and more profitable decisions.",
      "StockNewsBR: market intelligence with institutional structure and AI, giving traders superior decision-making.",
    ],
  },
];

const INSTITUTIONAL_SECTIONS = [
  {
    id: "institucional-sobre",
    label: "1️⃣ Sobre a Empresa",
    title: "🏛 Sobre a Empresa",
    body: [
      "StockNewsBR é a plataforma inteligente que transforma dados em oportunidades. Com tecnologia de IA e cálculos financeiros quânticos, oferece análises exclusivas para traders da B3, BDRs, ações dos EUA e criptoativos.",
      "Nosso objetivo é entregar insights rápidos, decisões mais seguras e aumentar seu potencial de lucro com melhor tomada de decisão.",
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
    id: "institucional-glossario-painel",
    label: "4️⃣ Glosário: Painel de Análise Estratégica",
    title: "📘 Glosário: Painel de Análise Estratégica",
    body: ["Resumo rápido dos blocos que formam a leitura estratégica do ativo."],
    rows: [
      { item: "Score Mestre", explanation: "Pontuação geral do ativo; resume a força da oportunidade." },
      { item: "Direção Provável", explanation: "Caminho mais provável do preço no curto prazo." },
      { item: "Trade Sugerido", explanation: "Ação operacional indicada pela leitura: compra, short ou aguardar." },
      { item: "Regime", explanation: "Contexto do mercado: alta, baixa ou lateral." },
      { item: "Fluxo Institucional", explanation: "Leitura de entrada ou saída dos grandes players." },
      { item: "Liquidez Alvo", explanation: "Zona de suporte ou resistência mais relevante." },
      { item: "Risco", explanation: "Nível de perigo da operação: baixo, médio ou alto." },
      { item: "Conclusão", explanation: "Resumo final da IA para apoiar a tomada de decisão." },
      { item: "Base da Análise", explanation: "Números e fatores usados para sustentar a leitura." },
      { item: "Foco Agora", explanation: "Ação prática imediata recomendada ao trader." },
    ],
  },
  {
    id: "institucional-glossario-grafico",
    label: "5️⃣ Glosário: Gráfico do Ativo",
    title: "📗 Glosário: Gráfico do Ativo",
    body: ["Resumo rápido dos indicadores e elementos que aparecem no gráfico do ativo."],
    rows: [
      { item: "Candlestick (vela)", explanation: "Mostra abertura, máxima, mínima e fechamento do preço em cada período." },
      { item: "VWAP", explanation: "Preço médio ponderado pelo volume; indica referência justa do ativo." },
      { item: "Médias Móveis", explanation: "Linhas que suavizam o preço e mostram tendência." },
      { item: "Supertrend", explanation: "Indicador que mostra direção e possíveis pontos de compra ou venda." },
      { item: "MACD", explanation: "Mede a força da tendência e possíveis mudanças de direção." },
      { item: "RSI", explanation: "Mostra se o ativo está sobrecomprado ou sobrevendido." },
      { item: "Volume", explanation: "Quantidade negociada; confirma a força do movimento." },
      { item: "Suporte", explanation: "Preço onde compradores costumam segurar quedas." },
      { item: "Resistência", explanation: "Preço onde vendedores costumam segurar altas." },
      { item: "Aguardar", explanation: "Sinal para não operar ainda; esperar confirmação." },
    ],
  },
  {
    id: "institucional-glossario-modos",
    label: "6️⃣ Glosário: Modos de Uso da Plataforma",
    title: "⚙️ Glosário: Modos de Uso da Plataforma",
    body: ["Resumo dos modos de acesso e do que cada um libera na experiência da plataforma."],
    rows: [
      { item: "Modo Básico", explanation: "Versão simples da plataforma, com leitura essencial e menos painéis abertos." },
      { item: "Modo Pro", explanation: "Versão completa, com acesso aos painéis avançados, análises extras e recursos profissionais." },
      { item: "Abrir", explanation: "Expande uma seção para mostrar o conteúdo completo." },
      { item: "Fechar", explanation: "Recolhe uma seção para deixar a tela mais limpa e rápida." },
      { item: "Ajuda ao Trader", explanation: "Área com explicações práticas para entender a leitura da plataforma." },
    ],
  },
  {
    id: "institucional-aviso-legal",
    label: "7️⃣ Aviso legal",
    title: "⚠️ Aviso legal",
    body: [
      "As ferramentas do StockNewsBR são apoio analítico e educacional. Elas não constituem recomendação individual de compra, venda ou manutenção de ativos.",
      "Mercado financeiro envolve risco. O usuário deve tomar decisões por conta própria e usar gestão de risco em todas as operações.",
    ],
  },
  {
    id: "institucional-termos",
    label: "8️⃣ Termos de uso",
    title: "📄 Termos de uso",
    body: [
      "O acesso ao produto depende do plano contratado e do respeito às regras da comunidade, incluindo uso responsável do feed social, polls e ferramentas de IA.",
      "Contas Premium usam OTP por email e política de sessão mais rígida para evitar compartilhamento indevido.",
    ],
  },
  {
    id: "institucional-privacidade",
    label: "9️⃣ Política de privacidade",
    title: "🔐 Política de privacidade",
    body: [
      "Dados básicos de conta, autenticação, perfil e preferências são usados para operar o acesso ao app, website, Telegram e recursos da comunidade.",
      "Quando o trader publica no feed, o nome, a foto e o email configurados no profile são usados para identificar o post dentro do ticker.",
    ],
  },
  {
    id: "institucional-cookies",
    label: "🔟 Política de cookies",
    title: "🍪 Política de cookies",
    body: [
      "A versão web utiliza cookies e armazenamento local para manter sessão, preferências de layout, ticker selecionado e continuidade da experiência do trader.",
      "Esses recursos ajudam a salvar workspace, autenticação e contexto entre visitas.",
    ],
  },
  {
    id: "institucional-contato",
    label: "1️⃣1️⃣ Contato / empresa",
    title: "📬 Contato / empresa",
    body: [
      "Canal institucional principal: https://www.stocknewsbr.com",
      "As comunicações oficiais da empresa devem ser publicadas nos canais institucionais da própria StockNewsBR.",
    ],
  },
  {
    id: "institucional-redes",
    label: "1️⃣2️⃣ Redes sociais",
    title: "🌐 Redes sociais",
    body: [
      "As redes sociais oficiais e o Telegram da StockNewsBR servem para distribuição de alertas, novidades do produto e comunicação institucional.",
      "Sempre confirme se o canal está vinculado aos endereços oficiais da empresa antes de confiar em qualquer mensagem.",
    ],
  },
  {
    id: "institucional-ajuda-trader",
    label: "1️⃣3️⃣ Ajuda Educacional para o Trader",
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
      "StockNewsBR is an intelligent platform that turns data into opportunities. With AI technology and quantum financial calculations, it provides exclusive analysis for B3, BDR, US stock and crypto traders.",
      "The goal is to deliver fast insights, safer decisions and better decision-making potential.",
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
    id: "institucional-glossario-painel",
    label: "4️⃣ Glossary: Strategic Analysis Panel",
    title: "📘 Glossary: Strategic Analysis Panel",
    body: ["Quick overview of the blocks that make up the asset's strategic read."],
    rows: [
      { item: "Master Score", explanation: "Overall asset score; summarizes how strong the opportunity is." },
      { item: "Likely Direction", explanation: "Most likely short-term price path." },
      { item: "Suggested Trade", explanation: "Operational action indicated by the read: buy, short or wait." },
      { item: "Regime", explanation: "Market context: uptrend, downtrend or range." },
      { item: "Institutional Flow", explanation: "Read of large-player inflow or outflow." },
      { item: "Liquidity Target", explanation: "Most relevant support or resistance zone." },
      { item: "Risk", explanation: "Trade danger level: low, medium or high." },
      { item: "Conclusion", explanation: "Final AI summary to support the decision." },
      { item: "Analysis Basis", explanation: "Numbers and factors used to support the read." },
      { item: "Focus Now", explanation: "Immediate practical action for the trader." },
    ],
  },
  {
    id: "institucional-glossario-grafico",
    label: "5️⃣ Glossary: Asset Chart",
    title: "📗 Glossary: Asset Chart",
    body: ["Quick overview of the indicators and elements shown on the asset chart."],
    rows: [
      { item: "Candlestick (candle)", explanation: "Shows open, high, low and close for each period." },
      { item: "VWAP", explanation: "Volume-weighted average price; a fair-value reference for the asset." },
      { item: "Moving Averages", explanation: "Lines that smooth price and show trend." },
      { item: "Supertrend", explanation: "Indicator that shows direction and possible buy or sell points." },
      { item: "MACD", explanation: "Measures trend strength and possible direction changes." },
      { item: "RSI", explanation: "Shows whether the asset is overbought or oversold." },
      { item: "Volume", explanation: "Traded quantity; confirms move strength." },
      { item: "Support", explanation: "Price where buyers usually hold drops." },
      { item: "Resistance", explanation: "Price where sellers usually hold rallies." },
      { item: "Wait", explanation: "Signal to avoid trading yet; wait for confirmation." },
    ],
  },
  {
    id: "institucional-glossario-modos",
    label: "6️⃣ Platform Usage Modes Glossary",
    title: "⚙️ Platform Usage Modes Glossary",
    body: ["Quick summary of the access modes and what each one unlocks in the platform experience."],
    rows: [
      { item: "Basic Mode", explanation: "Simplified platform version with essential reading and fewer panels open." },
      { item: "Pro Mode", explanation: "Full version with advanced panels, extra analysis and professional features." },
      { item: "Open", explanation: "Expands a section to show the full content." },
      { item: "Close", explanation: "Collapses a section to keep the screen cleaner and faster." },
      { item: "Trader Help", explanation: "Area with practical explanations to understand the platform read." },
    ],
  },
  {
    id: "institucional-aviso-legal",
    label: "7️⃣ Legal notice",
    title: "⚠️ Legal notice",
    body: [
      "StockNewsBR tools are analytical and educational support. They are not individualized recommendations to buy, sell, hold or short any asset.",
      "Financial markets involve risk. Users make their own decisions and must manage risk on every trade.",
    ],
  },
  {
    id: "institucional-termos",
    label: "8️⃣ Terms of use",
    title: "📄 Terms of use",
    body: [
      "Product access depends on the contracted plan and compliance with community rules, including responsible use of social feed, polls and AI tools.",
      "Premium accounts use email OTP and stricter session policy to reduce account sharing.",
    ],
  },
  {
    id: "institucional-privacidade",
    label: "9️⃣ Privacy policy",
    title: "🔐 Privacy policy",
    body: [
      "Basic account, authentication, profile and preference data are used to operate app, website, Telegram and community access.",
      "When a trader posts in the feed, the configured display name, image and email identify the post inside that ticker room.",
    ],
  },
  {
    id: "institucional-cookies",
    label: "🔟 Cookie policy",
    title: "🍪 Cookie policy",
    body: [
      "The web version uses cookies and local storage to keep session, layout preferences, selected ticker and workspace continuity.",
      "These resources preserve authentication, workspace state and context between visits.",
    ],
  },
  {
    id: "institucional-contato",
    label: "1️⃣1️⃣ Contact / company",
    title: "📬 Contact / company",
    body: [
      "Main institutional channel: https://www.stocknewsbr.com",
      "Official company communications should be published through StockNewsBR institutional channels.",
    ],
  },
  {
    id: "institucional-redes",
    label: "1️⃣2️⃣ Social channels",
    title: "🌐 Social channels",
    body: [
      "Official social channels and Telegram distribute alerts, product news and institutional communication.",
      "Always confirm that a channel is linked to the company's official addresses before trusting any message.",
    ],
  },
  {
    id: "institucional-ajuda-trader",
    label: "1️⃣3️⃣ Trader Educational Help",
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
  AAL: "American Airlines Group",
  BA: "Boeing",
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
    title: "🗺 Mapa de Calor",
    description: "Mostra quais ativos estão mais fortes ou mais fracos no mercado.",
    explanation: "🟢 Verde = força compradora. 🔴 Vermelho = pressão vendedora. Exemplo: se PETR4 aparece bem verde, o ativo está ganhando força agora.",
  },
  radar: {
    title: "⚡ Radar",
    description: "Detecta ativos que começaram a se movimentar rapidamente no mercado.",
    explanation: "Funciona como um radar para encontrar oportunidades antes da maioria dos traders perceber.",
  },
  "breakout-probability": {
    title: "🎯 Breakout",
    description: "Identifica quando um ativo está próximo de romper uma resistência importante.",
    explanation: "Breakout significa que o preço pode iniciar uma tendência forte. Exemplo: se romper uma faixa lateral com volume, a probabilidade sobe.",
  },
  "volatility-squeeze": {
    title: "🟣 Squeeze",
    description: "Detecta momentos em que a volatilidade do mercado está muito comprimida.",
    explanation: "Depois de muita compressão costuma vir expansão forte. A leitura busca exatamente esse ponto.",
  },
  "institutional-flow": {
    title: "🏦 Fluxo Institucional",
    description: "Identifica quando investidores institucionais estão entrando no mercado.",
    explanation: "Instituições movem muito volume e muitas vezes iniciam movimentos importantes antes do varejo perceber.",
  },
  "smart-money": {
    title: "💼 Dinheiro Inteligente",
    description: "Busca sinais de movimentação de grandes players antes de movimentos importantes no mercado.",
    explanation: "É a leitura do dinheiro inteligente: absorção, deslocamento e volume anormal.",
  },
  accumulation: {
    title: "📦 Acumulação",
    description: "Detecta quando um ativo está sendo acumulado lentamente por grandes investidores.",
    explanation: "A acumulação costuma acontecer com preço estável e volume subindo aos poucos, sem chamar tanta atenção do mercado.",
  },
  "liquidity-sweep": {
    title: "🧲 Varredura de Liquidez",
    description: "Detecta quando o mercado busca liquidez antes de mudar de direção.",
    explanation: "É quando o preço varre stops, busca liquidez e depois reage na direção contrária.",
  },
  "liquidity-map": {
    title: "🧭 Mapa de Liquidez",
    description: "Mostra onde existe maior concentração de liquidez no mercado.",
    explanation: "Esses pontos costumam atrair o preço e ajudam o trader a entender onde a reação pode acontecer.",
  },
  "market-regime": {
    title: "📊 Regime de Mercado",
    description: "Mostra qual é o tipo de mercado atual.",
    explanation: "Identifica se o mercado está em tendência de alta, tendência de baixa ou lateral, para o trader usar a ferramenta certa no cenário certo.",
  },
  "master-score": {
    title: "⭐ Score Mestre",
    description: "É a pontuação geral do sistema.",
    explanation: "Combina regime, fluxo, liquidez, timing e risco para classificar oportunidades. Score alto = oportunidade mais forte.",
  },
};

const TOOL_COPY_EN: Record<string, { title: string; description: string; explanation: string }> = {
  "heat-map": {
    title: "🗺 Heat Map",
    description: "Shows which assets are stronger or weaker in the market.",
    explanation: "🟢 Green = buying strength. 🔴 Red = selling pressure. If PETR4 appears strongly green, the asset is gaining strength now.",
  },
  radar: {
    title: "⚡ Radar",
    description: "Detects assets that started moving quickly.",
    explanation: "Works as a radar for opportunities before most traders notice the move.",
  },
  "breakout-probability": {
    title: "🎯 Breakout",
    description: "Identifies when an asset is close to breaking important resistance.",
    explanation: "Breakout means price may start a stronger trend. If range breaks with volume, probability improves.",
  },
  "volatility-squeeze": {
    title: "🟣 Squeeze",
    description: "Detects moments when market volatility is highly compressed.",
    explanation: "After strong compression, expansion often follows. This read looks for that point.",
  },
  "institutional-flow": {
    title: "🏦 Institutional Flow",
    description: "Identifies when institutional investors may be entering the market.",
    explanation: "Institutions move large volume and often start important moves before retail notices.",
  },
  "smart-money": {
    title: "💼 Smart Money",
    description: "Looks for large-player movement before important market moves.",
    explanation: "It reads smart money through absorption, displacement and abnormal volume.",
  },
  accumulation: {
    title: "📦 Accumulation",
    description: "Detects when an asset may be slowly accumulated by large investors.",
    explanation: "Accumulation often appears as stable price with gradually rising volume.",
  },
  "liquidity-sweep": {
    title: "🧲 Liquidity Sweep",
    description: "Detects when the market seeks liquidity before changing direction.",
    explanation: "Price sweeps stops, takes liquidity and then reacts in the opposite direction.",
  },
  "liquidity-map": {
    title: "🧭 Liquidity Map",
    description: "Shows where liquidity is more concentrated in the market.",
    explanation: "These zones often attract price and help the trader understand where reaction can happen.",
  },
  "market-regime": {
    title: "📊 Market Regime",
    description: "Shows the current market environment.",
    explanation: "Identifies uptrend, downtrend or range so the trader uses the right tool for the right scenario.",
  },
  "master-score": {
    title: "⭐ Master Score",
    description: "The system's consolidated score.",
    explanation: "Combines regime, flow, liquidity, timing and risk to classify opportunities. Higher score means stronger opportunity.",
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
const COMPOSER_EMOJIS = ["🔥", "📈", "🚀", "💰", "⚠️", "👀", "✅", "🔻"];
const QUICK_GIF_TERMS = ["bull market", "bear market", "stocks rally", "market crash"];

function cx(...values: Array<string | false | null | undefined>) {
  return values.filter(Boolean).join(" ");
}

function titleFromKey(key: string) {
  return key.replace(/_/g, " ").replace(/\b\w/g, (match) => match.toUpperCase());
}

function normalizeSymbol(raw: string) {
  const value = String(raw || "").trim().toUpperCase().replace(/\.SA$/, "").replace(/[^A-Z0-9-]/g, "");
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

function chartFallbackShape(interval: string) {
  const normalizedInterval = String(interval || "1D").toUpperCase();
  const now = Date.now();
  if (normalizedInterval === "1D") {
    return { count: 78, stepMs: 5 * 60 * 1000, startMs: now - 77 * 5 * 60 * 1000 };
  }
  if (normalizedInterval === "1W") {
    return { count: 7, stepMs: 24 * 60 * 60 * 1000, startMs: now - 6 * 24 * 60 * 60 * 1000 };
  }
  if (normalizedInterval === "1M") {
    return { count: 22, stepMs: 24 * 60 * 60 * 1000, startMs: now - 21 * 24 * 60 * 60 * 1000 };
  }
  if (normalizedInterval === "3M") {
    return { count: 63, stepMs: 24 * 60 * 60 * 1000, startMs: now - 62 * 24 * 60 * 60 * 1000 };
  }
  if (normalizedInterval === "6M") {
    return { count: 90, stepMs: 2 * 24 * 60 * 60 * 1000, startMs: now - 178 * 24 * 60 * 60 * 1000 };
  }
  if (normalizedInterval === "YTD") {
    const yearStart = new Date(new Date(now).getFullYear(), 0, 1).getTime();
    const days = Math.max(1, Math.ceil((now - yearStart) / (24 * 60 * 60 * 1000)));
    const count = Math.min(120, days + 1);
    const stepMs = Math.max(24 * 60 * 60 * 1000, Math.ceil(days / Math.max(count - 1, 1)) * 24 * 60 * 60 * 1000);
    return { count, stepMs, startMs: now - (count - 1) * stepMs };
  }
  if (normalizedInterval === "1Y") {
    return { count: 122, stepMs: 3 * 24 * 60 * 60 * 1000, startMs: now - 363 * 24 * 60 * 60 * 1000 };
  }
  return { count: 156, stepMs: 7 * 24 * 60 * 60 * 1000, startMs: now - 155 * 7 * 24 * 60 * 60 * 1000 };
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

function sortWatchlistItemsAlphabetically(items: WatchlistItem[], locale: AppLocale = "pt-BR") {
  return [...items].sort((left, right) => {
    const symbolOrder = left.symbol.localeCompare(right.symbol, locale, { numeric: true, sensitivity: "base" });
    if (symbolOrder !== 0) return symbolOrder;
    return displayWatchlistLabel(left, locale).localeCompare(displayWatchlistLabel(right, locale), locale, {
      numeric: true,
      sensitivity: "base",
    });
  });
}

const REMOVED_FUTURES_SYMBOLS = new Set(["CME", "NQ", "MNQ", "MNO", "ES", "MES", "MYM"]);

function isRemovedFutureSymbol(symbol?: string | null) {
  const normalized = normalizeSymbol(String(symbol || ""));
  if (!normalized) return false;
  return /^(WIN|WDO)[FGHJKMNQUVXZ]\d{2}$/.test(normalized) || REMOVED_FUTURES_SYMBOLS.has(normalized);
}

function resolveTypedSymbol(raw: string) {
  const trimmed = String(raw || "").trim();
  const normalized = normalizeSymbol(trimmed);
  if (!trimmed) return "";

  const lower = trimmed.toLowerCase();
  const exactSymbolMatch = Object.keys(COMPANY_HINTS).find((symbol) => lower === symbol.toLowerCase());
  if (exactSymbolMatch) return exactSymbolMatch;

  const exactNameMatch = Object.entries(COMPANY_HINTS).find(([, name]) => lower === name.toLowerCase());
  if (exactNameMatch) return exactNameMatch[0];

  if (lower.length > 1) {
    const partialNameMatch = Object.entries(COMPANY_HINTS).find(([, name]) => name.toLowerCase().includes(lower));
    if (partialNameMatch) return partialNameMatch[0];
  }

  return normalized;
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

function formatNewsClock(value?: string | null, locale: AppLocale = "pt-BR") {
  const missing = locale === "en-US" ? "no source time" : "sem horário da fonte";
  if (!value) return missing;
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return missing;
  return new Intl.DateTimeFormat(locale, {
    day: "2-digit",
    month: "2-digit",
    timeZone: "America/Sao_Paulo",
    hour: "2-digit",
    minute: "2-digit",
  }).format(parsed);
}

function normalizeSourceTimestamp(value: unknown): string | null {
  if (value == null || value === "") return null;
  if (typeof value === "number" && Number.isFinite(value)) {
    const millis = value > 10_000_000_000 ? value : value * 1000;
    const parsed = new Date(millis);
    return Number.isNaN(parsed.getTime()) ? null : parsed.toISOString();
  }
  const text = String(value).trim();
  if (!text) return null;
  const numeric = Number(text);
  if (Number.isFinite(numeric) && /^\d+(\.\d+)?$/.test(text)) {
    return normalizeSourceTimestamp(numeric);
  }
  const parsed = new Date(text);
  return Number.isNaN(parsed.getTime()) ? null : parsed.toISOString();
}

function newsSourceTimestamp(item: NewsItem): string | null {
  const raw = item as any;
  return (
    normalizeSourceTimestamp(raw.published_at) ||
    normalizeSourceTimestamp(raw.provider_publish_time) ||
    normalizeSourceTimestamp(raw.providerPublishTime) ||
    normalizeSourceTimestamp(raw.pubDate) ||
    normalizeSourceTimestamp(raw.publishedAt) ||
    normalizeSourceTimestamp(raw.displayTime) ||
    normalizeSourceTimestamp(raw.content?.providerPublishTime) ||
    normalizeSourceTimestamp(raw.content?.pubDate) ||
    normalizeSourceTimestamp(raw.content?.publishedAt) ||
    normalizeSourceTimestamp(raw.content?.displayTime)
  );
}

function expandPortugueseMarketTerms(value?: string | null) {
  return String(value || "")
    .replace(/\bM\s*&\s*A\b/gi, "Fusões e aquisições")
    .replace(/\bMergers?\s*&\s*Acquisitions?\b/gi, "Fusões e aquisições");
}

function newsThemeFromText(value?: string | null) {
  const normalized = normalizeUiText(value);
  if (!normalized) return "";
  if (normalized.includes("m&a") || normalized.includes("fusoes e aquisicoes") || normalized.includes("merger") || normalized.includes("acquisition")) return "mna";
  if (normalized.includes("dividend") || normalized.includes("dividendo") || normalized.includes("income investors")) return "dividend";
  if (normalized.includes(" ev") || normalized.includes(" evs") || normalized.includes("electric vehicle") || normalized.includes("veiculo eletrico")) return "ev";
  if (normalized.includes("mover") || normalized.includes("destaque")) return "movers";
  return "";
}

function newsFieldMatchesTheme(value: string | null | undefined, titleTheme: string) {
  const fieldTheme = newsThemeFromText(value);
  return !titleTheme || !fieldTheme || fieldTheme === titleTheme;
}

function localizedNewsFallbackLine(item: NewsItem, symbol: string, locale: AppLocale, kind: "summary" | "trader" | "why" | "context") {
  const theme = newsThemeFromText(item.title || item.summary || item.card_summary);
  const ticker = normalizeSymbol(symbol) || "ativo";

  const pt = {
    mna: {
      summary: `Fusões e aquisições em ${ticker} podem criar prêmio de evento; confirme preço e volume.`,
      trader: `Para trader: trate a notícia como contexto e só opere se ${ticker} confirmar fluxo.`,
      why: `Pode alterar expectativa de lucro, múltiplos e precificação do setor.`,
      context: `Evento corporativo pode acelerar reprecificação, mas não substitui gatilho no gráfico.`,
    },
    dividend: {
      summary: `Dividendos em ${ticker} aumentam interesse de renda, mas exigem qualidade de caixa e tendência confirmando.`,
      trader: `Para trader: não compre só pelo yield; espere preço, volume e regime alinharem.`,
      why: `Dividend yield muda a atratividade, mas pode esconder risco de queda ou lucro menor.`,
      context: `Leitura de renda deve ser confirmada por fluxo e suporte no preço.`,
    },
    ev: {
      summary: `Notícia de EV/baterias muda a leitura estratégica; confirme impacto em demanda, margem e fluxo.`,
      trader: `Para trader: use a manchete como alerta e espere reação real do preço em ${ticker}.`,
      why: `EVs e armazenamento podem mexer em crescimento, capex e percepção de longo prazo.`,
      context: `Tema estratégico costuma gerar volatilidade; o gráfico decide o timing.`,
    },
    movers: {
      summary: `Lista de destaques mostra contexto relativo; compare força antes de usar como gatilho.`,
      trader: `Para trader: use a lista para filtrar ativos e só aja com confirmação no gráfico.`,
      why: `Movers ajudam a ver onde o mercado está concentrando atenção e volume.`,
      context: `Contexto de mercado, não recomendação isolada de operação.`,
    },
    generic: {
      summary: `Notícia relevante em ${ticker}; confirme impacto em preço, volume e leitura da IA.`,
      trader: `Para trader: espere confirmação operacional antes de agir em ${ticker}.`,
      why: `A manchete pode alterar percepção de risco, lucro ou fluxo do ativo.`,
      context: `Use como contexto e valide no gráfico antes de entrar ou sair.`,
    },
  } as const;

  const en = {
    mna: {
      summary: `M&A involving ${ticker} can create event premium; confirm price and volume first.`,
      trader: `Trader note: treat the headline as context and trade only if ${ticker} confirms flow.`,
      why: `It can change earnings expectations, multiples and sector pricing.`,
      context: `Corporate events can accelerate repricing, but the chart still controls timing.`,
    },
    dividend: {
      summary: `Dividend news in ${ticker} improves income appeal, but cash quality and trend must confirm.`,
      trader: `Trader note: do not buy on yield alone; wait for price, volume and regime alignment.`,
      why: `Dividend yield changes attractiveness, but can hide downside or weaker earnings risk.`,
      context: `Income reads need flow and price support confirmation.`,
    },
    ev: {
      summary: `EV/battery news changes the strategic read; confirm demand, margin and flow impact.`,
      trader: `Trader note: use the headline as an alert and wait for real price reaction in ${ticker}.`,
      why: `EV and storage themes can affect growth, capex and long-term perception.`,
      context: `Strategic themes often add volatility; the chart decides timing.`,
    },
    movers: {
      summary: `Mover lists are relative-market context; compare strength before using them as a trigger.`,
      trader: `Trader note: use the list to filter assets and act only with chart confirmation.`,
      why: `Movers show where attention and volume are concentrating.`,
      context: `Market context, not a standalone trading recommendation.`,
    },
    generic: {
      summary: `Relevant news in ${ticker}; confirm price, volume and AI impact before acting.`,
      trader: `Trader note: wait for operational confirmation before acting in ${ticker}.`,
      why: `The headline may change perceived risk, earnings or flow for the asset.`,
      context: `Use it as context and validate on the chart before entering or exiting.`,
    },
  } as const;

  const group = (theme || "generic") as keyof typeof pt;
  return locale === "en-US" ? en[group][kind] : pt[group][kind];
}

function buildNewsTraderTakeaway(item: NewsItem, symbol: string, locale: AppLocale, index = 0) {
  const ticker = normalizeSymbol(symbol) || (locale === "en-US" ? "the asset" : "o ativo");
  const text = normalizeUiText(
    [
      item.title,
      item.summary,
      item.card_summary,
      item.why_it_matters,
      ...(Array.isArray(item.labels) ? item.labels : []),
      ...(Array.isArray(item.entities) ? item.entities : []),
    ].filter(Boolean).join(" "),
  );
  const impact = normalizeUiText(item.impact || item.impact_label || "");
  const isBullish = impact.includes("bull") || impact.includes("positivo") || impact.includes("alta");
  const isBearish = impact.includes("bear") || impact.includes("negativo") || impact.includes("baixa");
  const theme = newsThemeFromText(text);

  const ptRotations = [
    `Para trader: acompanhe ${ticker} pelo preço e volume; só transforme a manchete em operação se houver confirmação no gráfico.`,
    `Para trader: use a notícia de ${ticker} como contexto e aguarde fluxo real antes de comprar, vender ou encerrar.`,
    `Para trader: compare a reação de ${ticker} com o setor; sem confirmação, a leitura fica apenas como alerta.`,
  ];
  const enRotations = [
    `Trader note: track ${ticker} through price and volume; turn the headline into a trade only after chart confirmation.`,
    `Trader note: use the ${ticker} headline as context and wait for real flow before buying, selling or closing.`,
    `Trader note: compare ${ticker}'s reaction with the sector; without confirmation, keep it as an alert only.`,
  ];

  if (locale === "en-US") {
    if (theme === "mna") {
      const reads = [
        `Trader note: event risk can reprice ${ticker}; wait for spread, volume and price confirmation before acting.`,
        `Trader note: this corporate-event headline matters only if ${ticker} reacts with real flow, not just headline volatility.`,
        `Trader note: M&A premium can fade quickly; use ${ticker}'s VWAP and volume as the execution filter.`,
      ];
      return reads[index % reads.length];
    }
    if (theme === "dividend") {
      const reads = [
        `Trader note: do not buy ${ticker} on yield alone; confirm cash quality, trend and volume first.`,
        `Trader note: income appeal can support ${ticker}, but price must hold structure before a long setup is valid.`,
        `Trader note: compare the dividend read with sector flow; weak volume keeps this as context only.`,
      ];
      return reads[index % reads.length];
    }
    if (theme === "ev") {
      const reads = [
        `Trader note: EV or battery news can move expectations; let ${ticker}'s price reaction confirm the trade.`,
        `Trader note: strategic EV news is not an entry by itself; wait for ${ticker} to break or defend a clear level.`,
        `Trader note: watch whether the market prices this as growth or margin risk before acting in ${ticker}.`,
      ];
      return reads[index % reads.length];
    }
    if (theme === "movers") {
      const reads = [
        `Trader note: mover lists are filters, not signals; trade ${ticker} only if relative strength and volume confirm.`,
        `Trader note: use this list to compare flows; ${ticker} still needs its own chart trigger.`,
        `Trader note: broad mover context can change fast, so protect size until ${ticker} confirms direction.`,
      ];
      return reads[index % reads.length];
    }
    if (text.includes("earnings") || text.includes("guidance") || text.includes("resultado")) {
      return index % 2 === 0
        ? `Trader note: earnings or guidance can change ${ticker}'s intraday trend; watch price, volume and margin reaction.`
        : `Trader note: separate the headline from execution; ${ticker} needs a confirmed reaction after the earnings read.`;
    }
    if (text.includes("regulation") || text.includes("regulacao")) {
      return index % 2 === 0
        ? `Trader note: regulatory news can increase volatility in ${ticker}; reduce size until direction is confirmed.`
        : `Trader note: regulation changes risk perception; wait for ${ticker} to show whether sellers or buyers control the move.`;
    }
    if (isBullish) return `Trader note: favor continuation in ${ticker} only if buyers hold the breakout and volume confirms.`;
    if (isBearish) return `Trader note: prioritize protection or short-side setups in ${ticker} only if support fails with volume.`;
    return enRotations[index % enRotations.length];
  }

  if (theme === "mna") {
    const reads = [
      `Para trader: evento de fusões e aquisições pode reprecificar ${ticker}; espere preço, spread e volume confirmarem antes de agir.`,
      `Para trader: manchete corporativa só vira operação se ${ticker} reagir com fluxo real, não apenas volatilidade de notícia.`,
      `Para trader: prêmio de fusões e aquisições pode sumir rápido; use VWAP e volume de ${ticker} como filtro de execução.`,
    ];
    return reads[index % reads.length];
  }
  if (theme === "dividend") {
    const reads = [
      `Para trader: não compre ${ticker} só pelo dividendo; confirme caixa, tendência e volume antes da entrada.`,
      `Para trader: renda pode apoiar ${ticker}, mas o preço precisa defender estrutura antes da compra ficar válida.`,
      `Para trader: compare dividendo com fluxo do setor; volume fraco mantém a leitura só como contexto.`,
    ];
    return reads[index % reads.length];
  }
  if (theme === "ev") {
    const reads = [
      `Para trader: notícia de EV ou baterias pode mexer nas expectativas; deixe a reação do preço em ${ticker} confirmar o trade.`,
      `Para trader: notícia estratégica não é entrada sozinha; espere ${ticker} romper ou defender nível claro.`,
      `Para trader: observe se o mercado precifica crescimento ou risco de margem antes de agir em ${ticker}.`,
    ];
    return reads[index % reads.length];
  }
  if (theme === "movers") {
    const reads = [
      `Para trader: lista de destaques é filtro, não sinal; opere ${ticker} só se força relativa e volume confirmarem.`,
      `Para trader: use a lista para comparar fluxos; ${ticker} ainda precisa do próprio gatilho no gráfico.`,
      `Para trader: contexto de movers muda rápido; proteja tamanho até ${ticker} confirmar direção.`,
    ];
    return reads[index % reads.length];
  }
  if (text.includes("earnings") || text.includes("guidance") || text.includes("resultado")) {
    return index % 2 === 0
      ? `Para trader: resultado ou guidance pode mudar a tendência intraday de ${ticker}; monitore preço, volume e margem.`
      : `Para trader: separe manchete de execução; ${ticker} precisa de reação confirmada depois do resultado.`;
  }
  if (text.includes("regulation") || text.includes("regulacao")) {
    return index % 2 === 0
      ? `Para trader: notícia regulatória pode aumentar volatilidade em ${ticker}; reduza tamanho até confirmar direção.`
      : `Para trader: regulação muda percepção de risco; espere ${ticker} mostrar se vendedores ou compradores controlam o movimento.`;
  }
  if (isBullish) return `Para trader: priorize continuação compradora em ${ticker} só se compradores sustentarem rompimento e volume confirmar.`;
  if (isBearish) return `Para trader: priorize proteção ou venda em ${ticker} só se suporte falhar com volume.`;
  return ptRotations[index % ptRotations.length];
}

function clampHeadline(value: string, maxLength = 130) {
  const cleaned = value.trim().replace(/\s+/g, " ");
  return cleaned.length > maxLength ? `${cleaned.slice(0, maxLength - 3)}...` : cleaned;
}

function translateEnglishNewsHeadlineToPt(value?: string | null, symbol?: string | null) {
  const title = String(value || "").trim();
  if (!title) return "";
  if (looksPortuguese(title)) return clampHeadline(expandPortugueseMarketTerms(title));

  const ticker = normalizeSymbol(String(symbol || "")) || "ativo";
  const normalized = title
    .replace(/[’]/g, "'")
    .replace(/\s+/g, " ")
    .trim();

  const batteryDeal = normalized.match(/^(.+?)\s+and\s+(.+?)\s+signs?\s+major\s+battery\s+storage\s+supply\s+deal$/i);
  if (batteryDeal) {
    return clampHeadline(`${batteryDeal[1]} e ${batteryDeal[2]} assinam grande acordo de fornecimento de armazenamento em baterias`);
  }

  const evDrawingBoard = normalized.match(/^(.+?)\s+CEOs?\s+go\s+back\s+to\s+the\s+drawing\s+board\s+with\s+EVs$/i);
  if (evDrawingBoard) {
    return clampHeadline(`CEOs de ${evDrawingBoard[1]} revisam estratégia de veículos elétricos`);
  }

  const dividendYield = normalized.match(/^Is\s+a\s+(.+?)\s+Dividend\s+Yield\s+Enough\s+to\s+Make\s+This\s+Stock\s+a\s+Buy\s+for\s+Income\s+Investors\??$/i);
  if (dividendYield) {
    return clampHeadline(`Rendimento de dividendos de ${dividendYield[1]} é suficiente para tornar ${ticker} uma compra para investidores de renda?`);
  }

  const movers = normalized.match(/^(?:these\s+)?stocks\s+are\s+today'?s\s+movers:\s*(.+)$/i);
  if (movers) {
    const list = movers[1]
      .replace(/,\s*and\s+more\.?$/i, " e mais")
      .replace(/\s+and\s+/gi, " e ");
    return clampHeadline(`Ações em destaque hoje: ${list}`);
  }

  const firstCustomerStorage = normalized.match(/^(.+?)\s+lands\s+its\s+first\s+customer\s+in\s+battery\s+storage\s+deal$/i);
  if (firstCustomerStorage) {
    return clampHeadline(`${firstCustomerStorage[1]} conquista primeiro cliente em acordo de armazenamento em baterias`);
  }

  const firstGridStorage = normalized.match(/^(.+?)\s+signs?\s+first\s+grid\s+storage\s+deal\s+with\s+(.+?),\s+up\s+to\s+(.+)$/i);
  if (firstGridStorage) {
    return clampHeadline(`${firstGridStorage[1]} assina primeiro acordo de armazenamento de rede com ${firstGridStorage[2]}, de até ${firstGridStorage[3]}`);
  }

  const europeanGrowthStorage = normalized.match(/^(.+?)\s+details\s+european\s+growth\s+strategy,\s+signs?\s+(.+?)\s+energy-storage\s+agreement$/i);
  if (europeanGrowthStorage) {
    return clampHeadline(`${europeanGrowthStorage[1]} detalha estratégia de crescimento na Europa e assina acordo de armazenamento de energia com ${europeanGrowthStorage[2]}`);
  }

  const acquisition = normalized.match(/^(.+?)\s+(?:to\s+)?acquires?\s+(.+)$/i);
  if (acquisition) {
    return clampHeadline(`${acquisition[1]} compra ${acquisition[2]}`);
  }

  const merger = normalized.match(/^(.+?)\s+and\s+(.+?)\s+announce\s+merger/i);
  if (merger) {
    return clampHeadline(`${merger[1]} e ${merger[2]} anunciam fusão`);
  }

  const cleaned = normalized
    .replace(/\bM\s*&\s*A\b/gi, "fusões e aquisições")
    .replace(/\bMergers?\s*&\s*Acquisitions?\b/gi, "fusões e aquisições")
    .replace(/\btoday'?s\b/gi, "de hoje")
    .replace(/\bstocks?\b/gi, "ações")
    .replace(/\bmovers?\b/gi, "destaques")
    .replace(/\bmajor\b/gi, "grande")
    .replace(/\bsupply deal\b/gi, "acordo de fornecimento")
    .replace(/\bbattery storage\b/gi, "armazenamento em baterias")
    .replace(/\benergy-storage agreement\b/gi, "acordo de armazenamento de energia")
    .replace(/\beuropean growth strategy\b/gi, "estratégia de crescimento na Europa")
    .replace(/\bgrid storage\b/gi, "armazenamento de rede")
    .replace(/\bfirst customer\b/gi, "primeiro cliente")
    .replace(/\bdeal\b/gi, "acordo")
    .replace(/\bsigns?\b/gi, "assina")
    .replace(/\blands\b/gi, "conquista")
    .replace(/\bdetails\b/gi, "detalha")
    .replace(/\bfirst\b/gi, "primeiro")
    .replace(/\bwith\b/gi, "com")
    .replace(/\bup to\b/gi, "até")
    .replace(/\bcustomer\b/gi, "cliente")
    .replace(/\bmore\b/gi, "mais")
    .replace(/\band\b/gi, "e");

  if (cleaned !== normalized) return clampHeadline(cleaned);
  return `Manchete internacional sobre ${ticker}`;
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

function marketSessionLabel(symbol: string, locale: AppLocale = "pt-BR", date = new Date()) {
  const { weekday, hour, minute } = getSaoPauloParts(date);
  const minutes = hour * 60 + minute;
  const isWeekday = ["mon", "tue", "wed", "thu", "fri"].includes(weekday);
  const closed = locale === "en-US" ? "Market closed" : "Mercado fechado";

  if (!isWeekday) return closed;

  if (isB3Symbol(symbol)) {
    if (minutes >= 9 * 60 + 45 && minutes < 10 * 60) return locale === "en-US" ? "Pre-open" : "Pré-abertura";
    if (minutes >= 10 * 60 && minutes <= 17 * 60 + 55) return locale === "en-US" ? "Market open" : "Mercado aberto";
    return closed;
  }

  if (minutes >= 5 * 60 && minutes < 10 * 60 + 30) return locale === "en-US" ? "Pre-market" : "Pré-mercado";
  if (minutes >= 10 * 60 + 30 && minutes <= 17 * 60) return locale === "en-US" ? "Market open" : "Mercado aberto";
  if (minutes > 17 * 60 && minutes <= 21 * 60) return locale === "en-US" ? "After-hours" : "Após o fechamento";
  return closed;
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
    normalizeAlertTimestamp((row as any).deal_detected_at) ||
    normalizeAlertTimestamp((row as any).found_at) ||
    normalizeAlertTimestamp((row as any).first_seen_at) ||
    normalizeAlertTimestamp(row.detected_at) ||
    normalizeAlertTimestamp(row.market_data_updated_at) ||
    normalizeAlertTimestamp(row.last_bar_at) ||
    normalizeAlertTimestamp(row.bar_time) ||
    normalizeAlertTimestamp(row.time) ||
    normalizeAlertTimestamp(row.timestamp) ||
    normalizeAlertTimestamp(row.quote_time) ||
    normalizeAlertTimestamp(row.provider_timestamp) ||
    normalizeAlertTimestamp(row.updated_at) ||
    normalizeAlertTimestamp(row.last_seen_at) ||
    normalizeAlertTimestamp(row.created_at) ||
    normalizeAlertTimestamp(fallbackIso)
  );
}

function resolveAiFindingTimestamp(row: AiToolRow) {
  return (
    normalizeAlertTimestamp((row as any).deal_detected_at) ||
    normalizeAlertTimestamp((row as any).found_at) ||
    normalizeAlertTimestamp((row as any).first_seen_at) ||
    normalizeAlertTimestamp(row.detected_at) ||
    normalizeAlertTimestamp(row.market_data_updated_at) ||
    normalizeAlertTimestamp(row.quote_time) ||
    normalizeAlertTimestamp(row.provider_timestamp) ||
    normalizeAlertTimestamp(row.last_bar_at) ||
    normalizeAlertTimestamp(row.bar_time) ||
    normalizeAlertTimestamp(row.time) ||
    normalizeAlertTimestamp(row.timestamp) ||
    normalizeAlertTimestamp(row.created_at) ||
    normalizeAlertTimestamp(row.updated_at) ||
    normalizeAlertTimestamp(row.last_seen_at)
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

function isNewerAiAlert(next: AiToolRow, current?: AiToolRow | null) {
  if (!current) return true;
  const nextTime = Date.parse(resolveAiAlertTimestamp(next) || "");
  const currentTime = Date.parse(resolveAiAlertTimestamp(current) || "");
  if (!Number.isFinite(nextTime)) return false;
  if (!Number.isFinite(currentTime)) return true;
  return nextTime > currentTime;
}

function withAlertTimestamp(row: AiToolRow, fallbackIso?: string): AiToolRow {
  const detectedAt = resolveAiFindingTimestamp(row) || normalizeAlertTimestamp(fallbackIso) || undefined;
  const lastSeenAt =
    normalizeAlertTimestamp(row.last_seen_at) ||
    normalizeAlertTimestamp(row.updated_at) ||
    detectedAt;

  return {
    ...row,
    ...(detectedAt ? { updated_at: normalizeAlertTimestamp(row.updated_at) || detectedAt, detected_at: normalizeAlertTimestamp(row.detected_at) || detectedAt } : {}),
    ...(lastSeenAt ? { last_seen_at: lastSeenAt } : {}),
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
  for (const row of rows) tryPush(row, false, false);
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

function formatPrice(value?: number | null, locale: AppLocale = "pt-BR") {
  if (value == null || Number.isNaN(Number(value))) return "n/a";
  return Number(value).toLocaleString(locale === "en-US" ? "en-US" : "pt-BR", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

function isBrazilianMarketSymbol(symbol?: string | null) {
  const normalized = normalizeSymbol(String(symbol || ""));
  return /^[A-Z]{4}\d{1,2}$/.test(normalized) || /^[A-Z0-9]{3,5}34$/.test(normalized) || normalized.startsWith("WIN") || normalized.startsWith("WDO");
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

function formatCompact(value?: number | null, locale: AppLocale = "pt-BR") {
  if (value == null || Number.isNaN(Number(value))) return "n/a";
  return Intl.NumberFormat(locale === "en-US" ? "en-US" : "pt-BR", {
    notation: "compact",
    maximumFractionDigits: 1,
  }).format(Number(value));
}

function formatVolumeLong(value?: number | null, locale: AppLocale = "pt-BR") {
  const numeric = Number(value);
  if (!Number.isFinite(numeric) || numeric <= 0) return locale === "en-US" ? "not available" : "indisponível";
  const numberLocale = locale === "en-US" ? "en-US" : "pt-BR";
  if (numeric >= 1_000_000_000) {
    const valueText = (numeric / 1_000_000_000).toLocaleString(numberLocale, { maximumFractionDigits: 1 });
    return locale === "en-US" ? `${valueText} billion` : `${valueText} bilhões`;
  }
  if (numeric >= 1_000_000) {
    const valueText = (numeric / 1_000_000).toLocaleString(numberLocale, { maximumFractionDigits: 1 });
    return locale === "en-US" ? `${valueText} million` : `${valueText} milhões`;
  }
  if (numeric >= 1_000) {
    const valueText = (numeric / 1_000).toLocaleString(numberLocale, { maximumFractionDigits: 1 });
    return locale === "en-US" ? `${valueText} thousand` : `${valueText} mil`;
  }
  return numeric.toLocaleString(numberLocale, { maximumFractionDigits: 0 });
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
  if (
    source === "empty" ||
    source.includes("stale") ||
    source.includes("last_good") ||
    status === "empty" ||
    status === "partial" ||
    status === "stale" ||
    (quote as any).stale === true
  ) {
    return false;
  }
  const price = Number(quote.price);
  return Number.isFinite(price) && price > 0;
}

function watchlistItemHasMarketValue(item?: WatchlistItem | null) {
  if (!item) return false;
  const price = Number(item.price);
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

function calculateRelativeVolume(volume?: number | null, averageVolume?: number | null) {
  const current = Number(volume);
  const average = Number(averageVolume);
  if (!Number.isFinite(current) || current <= 0 || !Number.isFinite(average) || average <= 0) return null;
  return clampNumber(Number((current / average).toFixed(2)), 0.1, 12);
}

function estimateRelativeVolumeFromActivity(volume?: number | null) {
  const current = Number(volume);
  if (!Number.isFinite(current) || current <= 0) return null;
  return clampNumber(Number((Math.log10(current) - 6).toFixed(2)), 0.6, 3);
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

function firstValidRsiNumber(...values: Array<unknown>) {
  for (const value of values) {
    const numeric = Number(value);
    if (Number.isFinite(numeric) && numeric > 0 && numeric <= 100) return numeric;
  }
  return null;
}

function describeRsiValue(value: number | null, locale: AppLocale = "pt-BR") {
  if (value == null || !Number.isFinite(value)) {
    return {
      label: "n/a",
      hint: locale === "en-US" ? "RSI missing from the current payload." : "RSI ausente no payload atual.",
      tone: "neutral" as const,
      basis: locale === "en-US" ? "RSI: no read." : "RSI: sem leitura.",
    };
  }

  const formatted = value.toFixed(1);
  if (value >= 70) {
    return {
      label: formatted,
      hint: locale === "en-US" ? `${formatted}: strong up momentum, but overbought; avoid chasing late.` : `${formatted}: alta forte, mas sobrecomprado; evite perseguir preço atrasado.`,
      tone: "up" as const,
      basis: locale === "en-US" ? `RSI: strong/up and overbought at ${formatted}.` : `RSI: alta forte e sobrecomprado nos ${formatted}.`,
    };
  }
  if (value > 60) {
    return {
      label: formatted,
      hint: locale === "en-US" ? `${formatted}: strong uptrend momentum; buyers still dominate.` : `${formatted}: tendência de alta forte; compradores ainda dominam.`,
      tone: "up" as const,
      basis: locale === "en-US" ? `RSI: strong up momentum at ${formatted}.` : `RSI: tendência de alta forte nos ${formatted}.`,
    };
  }
  if (value >= 50) {
    return {
      label: formatted,
      hint: locale === "en-US" ? `${formatted}: moderate up bias, still needs confirmation.` : `${formatted}: alta moderada, ainda precisa de confirmação.`,
      tone: "watch" as const,
      basis: locale === "en-US" ? `RSI: neutral to moderately bullish at ${formatted}.` : `RSI: neutro a alta moderada nos ${formatted}.`,
    };
  }
  if (value >= 40) {
    return {
      label: formatted,
      hint: locale === "en-US" ? `${formatted}: seller bias; buyers need confirmation.` : `${formatted}: viés vendedor; compradores precisam confirmar reação.`,
      tone: "watch" as const,
      basis: locale === "en-US" ? `RSI: seller bias at ${formatted}.` : `RSI: viés vendedor nos ${formatted}.`,
    };
  }
  if (value > 30) {
    return {
      label: formatted,
      hint: locale === "en-US" ? `${formatted}: relevant downtrend pressure.` : `${formatted}: pressão de baixa relevante.`,
      tone: "down" as const,
      basis: locale === "en-US" ? `RSI: bearish pressure at ${formatted}.` : `RSI: pressão de baixa nos ${formatted}.`,
    };
  }
  return {
    label: formatted,
    hint: locale === "en-US" ? `${formatted}: extreme sell pressure/oversold; watch for technical bounce before selling late.` : `${formatted}: venda extrema/sobrevenda; observe repique antes de vender atrasado.`,
    tone: "down" as const,
    basis: locale === "en-US" ? `RSI: oversold at ${formatted}.` : `RSI: sobrevenda nos ${formatted}.`,
  };
}

function biasStrengthLabel(bias?: string | null, score?: number | null, changePct?: number | null, locale: AppLocale = "pt-BR") {
  const text = normalizeUiText(String(bias || ""));
  const numericScore = Number(score);
  const numericChange = Number(changePct);
  const bullish = text.includes("alta") || text.includes("uptrend") || text.includes("buy") || numericChange > 0.05;
  const bearish = text.includes("baixa") || text.includes("downtrend") || text.includes("sell") || numericChange < -0.05;
  const strong = Number.isFinite(numericScore) && numericScore >= 7;
  const weak = Number.isFinite(numericScore) && numericScore <= 4.5;

  if (bullish && strong) return locale === "en-US" ? "Strong uptrend" : "Alta forte";
  if (bullish) return locale === "en-US" ? "Uptrend" : "Alta";
  if (bearish && weak) return locale === "en-US" ? "Strong downtrend" : "Baixa forte";
  if (bearish) return locale === "en-US" ? "Downtrend" : "Baixa";
  return locale === "en-US" ? "Neutral" : "Neutro";
}

function biasTone(value?: string | null) {
  const normalized = normalizeUiText(String(value || ""));
  if (normalized.includes("alta") || normalized.includes("uptrend")) return "up";
  if (normalized.includes("baixa") || normalized.includes("downtrend")) return "down";
  return "watch";
}

function describeBiasValue(value: string, locale: AppLocale = "pt-BR") {
  const normalized = normalizeUiText(value);
  if (normalized.includes("alta forte") || normalized.includes("strong uptrend")) {
    return locale === "en-US"
      ? "Strong buyer dominance. Long setups have better asymmetry while structure remains positive."
      : "Forte predominância compradora. Operações compradas possuem melhor assimetria enquanto a estrutura permanecer positiva.";
  }
  if (normalized.includes("alta") || normalized.includes("uptrend")) {
    return locale === "en-US"
      ? "Buyer bias. Pullbacks can be buy opportunities only with confirmation."
      : "Viés comprador predominante. Pullbacks podem ser compra apenas com confirmação.";
  }
  if (normalized.includes("baixa forte") || normalized.includes("strong downtrend")) {
    return locale === "en-US"
      ? "Strong selling pressure and weaker structure. Avoid long trades against the trend."
      : "Forte pressão vendedora e deterioração estrutural. Evite compras contra a tendência.";
  }
  if (normalized.includes("baixa") || normalized.includes("downtrend")) {
    return locale === "en-US"
      ? "Seller bias. Short-side setups have more support while price remains pressured."
      : "Viés vendedor predominante. Vendas/short têm mais suporte enquanto o preço seguir pressionado.";
  }
  return locale === "en-US"
    ? "No clear directional edge. Wait for confirmation before increasing exposure."
    : "Sem vantagem direcional clara. Aguarde confirmação antes de aumentar exposição.";
}

function firstPositiveFiniteNumber(...values: Array<unknown>) {
  for (const value of values) {
    const numeric = Number(value);
    if (Number.isFinite(numeric) && numeric > 0) return numeric;
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

function deriveChartVolume(chart?: ChartPayload | null) {
  const rows = chart?.ohlc?.length ? chart.ohlc : chart?.series || [];
  for (let index = rows.length - 1; index >= 0; index -= 1) {
    const volume = firstPositiveFiniteNumber((rows[index] as any).volume);
    if (volume != null) return volume;
  }
  return null;
}

function formatLiquidityVolume(volume?: number | null, rvol?: number | null, locale: AppLocale = "pt-BR") {
  const numericVolume = firstFiniteNumber(volume);
  if (numericVolume != null && numericVolume > 0) return formatCompact(numericVolume, locale);
  const numericRvol = firstFiniteNumber(rvol);
  if (numericRvol != null && numericRvol > 0) return `RVOL ${numericRvol.toFixed(2)}`;
  return locale === "en-US" ? "No real volume" : "Sem volume real";
}

function aiToolDataQuality(row?: Partial<AiToolRow> | null) {
  const rawRow = (row || {}) as any;
  const metrics = rawRow.metrics;
  const direct = rawRow.data_quality ?? rawRow.dataQuality ?? metrics?.data_quality ?? metrics?.dataQuality;
  const text = String(direct ?? (typeof metrics === "string" ? metrics : "")).toLowerCase();
  if (text.includes("score_only")) return "score_only";
  if (text.includes("empty") || text.includes("missing")) return "missing";
  if (text.includes("real") || text.includes("confirmed")) return "real";
  return String(direct || "").trim().toLowerCase();
}

function isOperationalAiFinding(row?: Partial<AiToolRow> | null) {
  const rawRow = (row || {}) as any;
  const price = firstFiniteNumber(rawRow.price);
  const volume = firstFiniteNumber(rawRow.volume);
  const quality = aiToolDataQuality(row);
  if (quality === "score_only" || quality === "missing") return false;
  return price != null && price > 0 && volume != null && volume > 0;
}

function looksPortuguese(text?: string | null) {
  const value = String(text || "").trim();
  if (!value) return false;
  const normalized = normalizeUiText(value);
  const hasPortugueseMarketTerm =
    /\b(preco|mercado|acao|noticia|volume|alta|baixa|trimestre|resultado|ativo|risco|fluxo|regulacao|leitura|sinal|comprador|vendedor|lateral|rompimento|suporte|resistencia)\b/.test(
      normalized,
    );
  if (hasPortugueseMarketTerm) return true;
  const hasAccent = /[ãõçáéíóúàêô]/i.test(value);
  const hasPortugueseConnector = /\b(de|da|do|das|dos|para|por|com|sem|em|ao|aos|uma|um|que|se|nao|apos|ate)\b/.test(normalized);
  return hasAccent && hasPortugueseConnector;
}

function normalizeUiText(value?: string | null) {
  return String(value || "")
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/\s+/g, " ")
    .trim()
    .toLowerCase();
}

function sentenceCaseFirst(value?: string | null, locale: AppLocale = "pt-BR") {
  const text = String(value || "").trim();
  const firstLetterIndex = text.search(/[A-Za-zÀ-ÖØ-öø-ÿ]/);
  if (firstLetterIndex < 0) return text;
  return `${text.slice(0, firstLetterIndex)}${text[firstLetterIndex].toLocaleUpperCase(locale)}${text.slice(firstLetterIndex + 1)}`;
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
  const normalizedKey = normalized.replace(/[.,;:!?]+$/g, "");
  const exactTranslations: Record<string, string> = {
    "leitura favoravel ao ativo no curto prazo": "Short-term read is favorable for the asset.",
    "manchete relevante, mas ainda ambigua ou indireta para o papel; precisa de confirmacao": "Relevant headline, but still ambiguous or indirect for the stock; wait for confirmation.",
    "consumo": "Consumer",
    "varejo": "Retail",
    "energia": "Energy",
    "petroleo e gas": "Oil and gas",
    "financeiro": "Financials",
    "financeiro / bancos": "Financials / Banks",
    "bancos": "Banks",
    "bancos de investimento": "Investment banks",
    "macro / mercado": "Macro / Market",
    "mercado": "Market",
    "geral": "General",
    "macro": "Macro",
    "tecnologia": "Technology",
    "resultado": "Earnings",
    "guidance": "Guidance",
    "regulacao": "Regulation",
    "juridico": "Legal",
    "fato relevante": "Material fact",
    "fusoes e aquisicoes": "M&A",
    "m&a": "M&A",
  };
  if (exactTranslations[normalized] || exactTranslations[normalizedKey]) return exactTranslations[normalized] || exactTranslations[normalizedKey];

  if (normalized.includes("leitura favoravel ao ativo") || normalized.includes("leitura favoravel ao asset")) {
    return "Short-term read is favorable for the asset.";
  }
  if (normalized.includes("pode gerar reprecificacao rapida") || normalized.includes("pode gerar repricing rapida")) {
    return `Can generate quick repricing in ${ticker} through event premium and strategic read.`;
  }
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
  if (normalized.includes("evento de m&a") || normalized.includes("evento de fusoes e aquisicoes")) {
    return "M&A event can create event premium and accelerate repricing.";
  }
  if (normalized.includes("m&a em") || normalized.includes("fusoes e aquisicoes em")) {
    return `M&A involving ${ticker} favors upside only if price and volume confirm.`;
  }
  if (normalized.includes("resultado") && normalized.includes("macro") && normalized.includes("zona neutra")) {
    return `Earnings and macro context keep ${ticker} neutral; treat it as context until price confirms direction.`;
  }
  if ((normalized.includes("fusoes e aquisicoes") || normalized.includes("m&a")) && normalized.includes("macro") && normalized.includes("favorece alta")) {
    return `M&A and macro context favor upside in ${ticker}, but only after price and volume confirm.`;
  }
  if (normalized.includes("macro em") && normalized.includes("favorece alta")) {
    return `Macro context favors upside in ${ticker}; confirm with price, volume and flow before acting.`;
  }
  if (normalized.includes("noticia para") && normalized.includes("favorece alta")) {
    return `News context favors upside in ${ticker}; confirm with price, volume and flow before acting.`;
  }
  if (normalized.includes("importa porque") && normalized.includes("pano de fundo macro")) {
    return "It matters because the macro backdrop can change market flow and risk appetite.";
  }
  if (normalized.includes("ajuda a entender") && normalized.includes("fluxo")) {
    return `Helps explain the flow and context that may affect ${ticker} in the short term.`;
  }
  if (normalized.includes("contexto mais ligado") && normalized.includes("fluxo do papel")) {
    return "Context is more tied to the sector and short-term stock flow.";
  }
  if ((normalized.includes("resultado") || normalized.includes("guidance")) && normalized.includes("favorece alta")) {
    return `Earnings or guidance favor upside in ${ticker}; confirm with price, volume and flow.`;
  }
  if ((normalized.includes("resultado") || normalized.includes("guidance")) && normalized.includes("zona neutra")) {
    return `Earnings or guidance keep ${ticker} neutral; wait for price confirmation.`;
  }
  if (normalized.includes("regulacao") && normalized.includes("zona neutra")) {
    return `Regulatory context keeps ${ticker} neutral; use it as context until price confirms direction.`;
  }
  if (normalized.includes("pode mexer") && (normalized.includes("risco percebido") || normalized.includes("risk percebido"))) {
    return `It can change perceived risk in ${ticker} and the sector read.`;
  }
  if (normalized.includes("noticia regulatoria") || normalized.includes("news regulatoria")) {
    return "Regulatory news can increase volatility and affect the sector.";
  }
  if (normalized.includes("resultado") && normalized.includes("fato relevante")) {
    return `Earnings or material facts keep ${ticker} in context; confirm with price before acting.`;
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
  if (normalized.includes("baixar prioridade se score cair")) {
    return "Lower priority if Score drops, volume diverges or another main AI points to the opposite direction.";
  }
  if (normalized.includes("mapa so autoriza") || normalized.includes("mapa só autoriza")) {
    return `Heat Map only authorizes action if ${ticker} keeps relative strength, RVOL confirms and price breaks the tactical level.`;
  }
  if (normalized.includes("close sell descoberta") || normalized.includes("vwap") && normalized.includes("short")) {
    return "Close short if VWAP/EMA21 recovers or institutional buying appears.";
  }
  if (normalized.includes("leitura operacional esta incompleta")) {
    return "The operational read is incomplete. Treat the panel as context and avoid execution until price and volume are confirmed.";
  }
  if (normalized.includes("a oportunidade esta classificada como") || normalized.includes("oportunidade esta classificada como")) {
    return original
      .replace(/A oportunidade está classificada como/gi, "The opportunity is classified as")
      .replace(/A oportunidade esta classificada como/gi, "The opportunity is classified as")
      .replace(/oportunidade está classificada como/gi, "opportunity is classified as")
      .replace(/oportunidade esta classificada como/gi, "opportunity is classified as")
      .replace(/neutra/gi, "neutral")
      .replace(/moderada/gi, "moderate")
      .replace(/forte/gi, "strong")
      .replace(/fraca/gi, "weak")
      .replace(/Composição/gi, "Composition")
      .replace(/forças em/gi, "strengths in")
      .replace(/forcas em/gi, "strengths in")
      .replace(/fragilidades em/gi, "weaknesses in")
      .replace(/Pontos positivos/gi, "Positive points")
      .replace(/acima da VWAP/gi, "above VWAP")
      .replace(/volume relativo forte/gi, "strong relative volume")
      .replace(/Riscos/gi, "Risks")
      .replace(/tendência fraca/gi, "weak trend")
      .replace(/tendencia fraca/gi, "weak trend")
      .replace(/Decisão final/gi, "Final decision")
      .replace(/Decisao final/gi, "Final decision");
  }
  if (normalized.includes("encerrar posicao comprada") || normalized.includes("encerrar posição comprada")) {
    return original
      .replace(/Encerrar posição comprada em/gi, "Close the long position in")
      .replace(/Encerrar posicao comprada em/gi, "Close the long position in")
      .replace(/quando houver perda de tendência/gi, "when trend is lost")
      .replace(/quando houver perda de tendencia/gi, "when trend is lost")
      .replace(/fluxo comprador fraco/gi, "weak buying flow")
      .replace(/conflito de regime\/liquidez contra a compra/gi, "regime/liquidity conflict against the buy")
    .replace(/compradas/gi, "long positions")
    .replace(/comprada/gi, "long")
    .replace(/compra/gi, "buy")
    .replace(/\bou\b/gi, "or")
    .replace(/posição/gi, "position")
      .replace(/posicao/gi, "position");
  }
  if (normalized.includes("sem volume real")) return "No real volume";
  if (normalized.includes("volume pouco confiavel")) return "Unreliable or missing volume";
  if (normalized.includes("fluxo institucional sem leitura")) return "Institutional flow without read";
  if (normalized.includes("score mestre sem leitura")) return "Master Score without confirmed reading";
  if (normalized.includes("tendencia principal")) return original.replace(/Tendência principal/gi, "Main trend").replace(/tendencia principal/gi, "main trend");
  if (normalized.includes("conviccao forte")) return original.replace(/Convicção forte/gi, "Strong conviction").replace(/conviccao forte/gi, "strong conviction");
  if (normalized.includes("conviccao moderada")) return original.replace(/Convicção moderada/gi, "Moderate conviction").replace(/conviccao moderada/gi, "moderate conviction");
  if (normalized.includes("pouca conviccao")) return original.replace(/Pouca convicção/gi, "Low conviction").replace(/pouca conviccao/gi, "low conviction");
  if (normalized.includes("risco baixo") && normalized.includes("filtros principais alinhados")) {
    return "Low risk: main filters are aligned.";
  }
  if (normalized.includes("low risk")) return original;

  return original
    .replace(/Preço/g, "Price")
    .replace(/preço pendente/g, "pending price")
    .replace(/Preço pendente/g, "Pending price")
    .replace(/volume pendente/g, "pending volume")
    .replace(/Volume pendente/g, "Pending volume")
    .replace(/RSI pendente/g, "pending RSI")
    .replace(/\bFusões e aquisições\b/gi, "M&A")
    .replace(/\bfusões e aquisições\b/gi, "M&A")
    .replace(/\bEvento\b/g, "Event")
    .replace(/\bevento\b/g, "event")
    .replace(/\bprêmio\b/g, "premium")
    .replace(/\bpremio\b/g, "premium")
    .replace(/\breprecificação\b/g, "repricing")
    .replace(/\breprecificacao\b/g, "repricing")
    .replace(/\bacelerar\b/g, "accelerate")
    .replace(/\balterar\b/g, "change")
    .replace(/\bfato relevante\b/g, "material fact")
    .replace(/preço/g, "price")
    .replace(/Variação/g, "Change")
    .replace(/variação/g, "change")
    .replace(/Confiança/g, "Confidence")
    .replace(/confiança/g, "confidence")
    .replace(/Estado/g, "State")
    .replace(/estado/g, "state")
    .replace(/Leitura principal/g, "Main Read")
    .replace(/leitura principal/g, "main read")
    .replace(/leitura adicional/g, "additional read")
    .replace(/Leitura adicional/g, "Additional read")
    .replace(/leitura operacional/g, "operational read")
    .replace(/Leitura operacional/g, "Operational read")
    .replace(/no Score Mestre/g, "in Master Score")
    .replace(/No Score Mestre/g, "In Master Score")
    .replace(/no mapa de liquidez/g, "in the liquidity map")
    .replace(/no Mapa de Liquidez/g, "in the Liquidity Map")
    .replace(/no radar/g, "on radar")
    .replace(/No radar/g, "On radar")
    .replace(/em probabilidade de rompimento/g, "in breakout probability")
    .replace(/em fluxo institucional/g, "in institutional flow")
    .replace(/em smart money/g, "in smart money")
    .replace(/em acumulação/g, "in accumulation")
    .replace(/em acumulacao/g, "in accumulation")
    .replace(/em varredura/g, "in liquidity sweep")
    .replace(/em regime/g, "in regime")
    .replace(/Direção final/g, "Final direction")
    .replace(/Direcao final/g, "Final direction")
    .replace(/direção final/g, "final direction")
    .replace(/direcao final/g, "final direction")
    .replace(/Operação preferida/g, "Preferred operation")
    .replace(/operacao preferida/g, "preferred operation")
    .replace(/Invalidação/g, "Invalidation")
    .replace(/Invalidacao/g, "Invalidation")
    .replace(/invalidação/g, "invalidation")
    .replace(/Métricas da lente/g, "Lens Metrics")
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
    .replace(/\bbaixo\b/g, "low")
    .replace(/\bBaixo\b/g, "Low")
    .replace(/\balto\b/g, "high")
    .replace(/\bAlto\b/g, "High")
    .replace(/compra/g, "buy")
    .replace(/Compra/g, "Buy")
    .replace(/venda/g, "sell")
    .replace(/Venda/g, "Sell")
    .replace(/\balta\b/g, "uptrend")
    .replace(/\bAlta\b/g, "Uptrend")
    .replace(/\bbaixa\b/g, "downtrend")
    .replace(/\bBaixa\b/g, "Downtrend")
    .replace(/\bneutro\b/g, "neutral")
    .replace(/\bNeutro\b/g, "Neutral")
    .replace(/\blateral\b/g, "range")
    .replace(/\bLateral\b/g, "Range")
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
    .replace(/sem volume real/g, "no real volume")
    .replace(/Sem volume real/g, "No real volume")
    .replace(/sem volume confiável/g, "no reliable volume")
    .replace(/sem volume confiavel/g, "no reliable volume")
    .replace(/Sem volume confiável/g, "No reliable volume")
    .replace(/Sem volume confiavel/g, "No reliable volume")
    .replace(/pouco confiável/g, "unreliable")
    .replace(/pouco confiavel/g, "unreliable")
    .replace(/ausente/g, "missing")
    .replace(/Ausente/g, "Missing")
    .replace(/tendência principal/g, "main trend")
    .replace(/Tendência principal/g, "Main trend")
    .replace(/tendencia principal/g, "main trend")
    .replace(/Tendencia principal/g, "Main trend")
    .replace(/fluxo institucional/g, "institutional flow")
    .replace(/Fluxo institucional/g, "Institutional flow")
    .replace(/filtros principais alinhados/g, "main filters are aligned")
    .replace(/Filtros principais alinhados/g, "Main filters are aligned")
    .replace(/compradas/g, "long positions")
    .replace(/Compradas/g, "Long positions")
    .replace(/comprada/g, "long")
    .replace(/Comprada/g, "Long")
    .replace(/vendidas/g, "short positions")
    .replace(/Vendidas/g, "Short positions")
    .replace(/vendida/g, "short")
    .replace(/Vendida/g, "Short")
    .replace(/aguardar/g, "wait")
    .replace(/Aguardar/g, "Wait")
    .replace(/monitorando/g, "watching")
    .replace(/Monitorando/g, "Watching");
}

function localizeUiText(value?: string | null, locale: AppLocale = "pt-BR", symbol?: string | null) {
  const text = String(value || "").trim();
  if (!text) return "";
  if (locale !== "en-US") return expandPortugueseMarketTerms(text);
  return translatePtToEn(text, symbol);
}

function localizeNewsField(item: NewsItem, symbol: string, locale: AppLocale, field: keyof NewsItem, kind: "summary" | "trader" | "why" | "context") {
  const titleTheme = newsThemeFromText(item.title);
  const raw = String((item as any)[field] || "").trim();
  if (raw && newsFieldMatchesTheme(raw, titleTheme)) {
    const translated = localizeUiText(raw, locale, symbol);
    if (translated && !(locale === "en-US" && looksPortuguese(translated))) return translated;
  }
  return localizedNewsFallbackLine(item, symbol, locale, kind);
}

function localizeInvalidationText(value: string | null | undefined, locale: AppLocale, symbol?: string | null) {
  return localizeUiText(value || (locale === "en-US" ? "No invalidation defined." : "Sem invalidação definida."), locale, symbol)
    .replace(/^(se|if)\s*:\s*/i, "")
    .trim();
}

function invalidationConflictsWithCurrentScore(value: string | null | undefined, score?: number | null) {
  const text = normalizeUiText(value);
  const numericScore = Number(score);
  if (!text || !Number.isFinite(numericScore)) return false;

  const thresholdMatch = text.match(/score\s+(?:cair|caia|drop|drops|below|abaixo)\D*(\d+(?:[.,]\d+)?)/i);
  if (!thresholdMatch) return false;

  const threshold = Number(thresholdMatch[1].replace(",", "."));
  return Number.isFinite(threshold) && numericScore < threshold;
}

function formatAiMainReadText(text: string, locale: AppLocale) {
  const labels = locale === "en-US"
    ? ["Composition", "Positive points", "Risks", "Final decision"]
    : ["Composição", "Pontos positivos", "Riscos", "Decisão final"];
  let formatted = String(text || "").trim();
  labels.forEach((label) => {
    const pattern = new RegExp(`\\s*(${label.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}\\s*:)`, "gi");
    formatted = formatted.replace(pattern, "\n$1");
  });
  return formatted.split(/\n+/).map((line) => line.trim()).filter(Boolean);
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

function newsDedupeKey(item: NewsItem, symbol: string) {
  const storyKey = normalizeUiText(item.story_key || "");
  if (storyKey) return `story:${storyKey}`;
  const url = String(item.url || "").trim().toLowerCase();
  if (url) return `url:${url.split("#", 1)[0].split("?", 1)[0].replace(/\/$/, "")}`;
  const raw = [
    item.title,
    item.trader_takeaway,
    item.card_summary,
    item.summary,
    item.why_it_matters,
  ].find((value) => normalizeUiText(value).length > 0);
  const normalized = normalizeUiText(raw || "");
  return normalized ? `text:${normalized.slice(0, 180)}` : `id:${item.id || symbol}`;
}

function dedupeNewsForTicker(items: NewsItem[], symbol: string) {
  const seen = new Set<string>();
  return items.filter((item) => {
    const key = newsDedupeKey(item, symbol);
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

function portugueseNewsTitle(item: NewsItem, symbol: string) {
  const title = String(item.title || "").trim();
  const translatedTitle = translateEnglishNewsHeadlineToPt(title, symbol);
  if (translatedTitle) return translatedTitle;

  const candidate = [
    item.trader_takeaway,
    item.editorial,
    item.why_it_matters,
    item.impact_reason,
    item.market_context,
  ].find((value) => looksPortuguese(value));

  if (candidate) {
    return clampHeadline(expandPortugueseMarketTerms(candidate), 120);
  }

  return `Notícia relevante para ${symbol}`;
}

function portugueseNewsBody(item: NewsItem, symbol: string) {
  const titleTheme = newsThemeFromText(item.title);
  const candidate = [
    item.editorial,
    item.why_it_matters,
    item.market_context,
    item.impact_reason,
    item.trader_takeaway,
    item.card_summary,
    item.summary,
  ].find((value) => looksPortuguese(value) && newsFieldMatchesTheme(value, titleTheme));

  if (candidate) {
    return clampHeadline(expandPortugueseMarketTerms(candidate), 180);
  }

  return localizedNewsFallbackLine(item, symbol, "pt-BR", "summary");
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
  if (translated && !looksPortuguese(translated)) return translated.length > 130 ? `${translated.slice(0, 127)}...` : translated;
  return `Relevant news for ${symbol}`;
}

function displayNewsBody(item: NewsItem, symbol: string, locale: AppLocale) {
  if (locale !== "en-US") return portugueseNewsBody(item, symbol);

  const titleTheme = newsThemeFromText(item.title);
  const candidate = [
    item.editorial,
    item.why_it_matters,
    item.market_context,
    item.impact_reason,
    item.trader_takeaway,
    item.card_summary,
    item.summary,
  ].find((value) => String(value || "").trim() && newsFieldMatchesTheme(value, titleTheme));
  const translated = localizeUiText(candidate || "", locale, symbol);
  if (translated && !looksPortuguese(translated)) return translated.length > 190 ? `${translated.slice(0, 187)}...` : translated;
  return localizedNewsFallbackLine(item, symbol, locale, "summary");
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

function chartActionLabel(marker?: ChartPayload["markers"][number] | null, locale: AppLocale = "pt-BR") {
  const explicit = String(marker?.action_label || marker?.label || "").trim();
  const type = String(marker?.type || explicit || "").toUpperCase();
  const normalizedExplicit = explicit.toUpperCase();
  if (normalizedExplicit === "BUY" || normalizedExplicit === "BUY LONG") return locale === "en-US" ? "Buy Long" : "Comprar";
  if (normalizedExplicit === "SELL" || normalizedExplicit === "CLOSE LONG") return locale === "en-US" ? "Close Long" : "Encerrar long";
  if (normalizedExplicit === "SHORT" || normalizedExplicit === "SELL SHORT") return locale === "en-US" ? "Sell Short" : "Short";
  if (normalizedExplicit === "COVER" || normalizedExplicit === "CLOSE SHORT") return locale === "en-US" ? "Close Short" : "Encerrar short";
  if (explicit) return explicit;
  if (type === "BUY") return locale === "en-US" ? "Buy Long" : "Comprar";
  if (type === "SELL") return locale === "en-US" ? "Close Long" : "Encerrar long";
  if (type === "SHORT") return locale === "en-US" ? "Sell Short" : "Short";
  if (type === "COVER") return locale === "en-US" ? "Close Short" : "Encerrar short";
  return locale === "en-US" ? "Watch" : "Aguardar";
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
  if (normalized.includes("buy long") || normalized.includes("comprar")) return "Comprar apenas se o trigger confirmar; não comprar resistência sem rompimento.";
  if (normalized.includes("close long") || normalized.includes("encerrar long")) return "Encerrar long ou evitar nova compra até o preço recuperar estrutura.";
  if (normalized.includes("sell short") || normalized.includes("short")) return "Abrir short apenas com perda de suporte/VWAP e volume vendedor.";
  if (normalized.includes("close short") || normalized.includes("encerrar short")) return "Encerrar short se houver recuperação de VWAP/EMA21 ou compra institucional.";
  return "Observar; sem ordem operacional enquanto faltar confirmação.";
}

function cleanEnglishDecisionText(value: string | undefined | null, fallback: string, symbol: string) {
  const localized = localizeUiText(value || "", "en-US", symbol);
  const dirty = /\b(sem|se|quando|confirmacao|preco|suporte|resistencia|baixo|baixa|medio|alto|alta|compra|comprada|comprador|venda|vendida|vendedor|posicao|posição|recebeu|classificada|neutra|fraca|forte|composicao|fragilidades|pontos positivos|filtros|principais|alinhados|ordem operacional|tecnico|virada|ausencia|conflito de|divergirem|antes de|recuperar)\b/i.test(localized);
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
  const actionLabel = chartActionLabel(marker, locale);
  const trend = chart?.summary?.trend_bias || "sem regime";
  const latestSignal = chart?.summary?.latest_signal || marker?.type || "WATCH";
  const missing: string[] = [];
  if (!rows.length) missing.push("serie OHLC do provider");
  if (price == null) missing.push("preco real confirmado");
  if (!marker) missing.push("marcador operacional confirmado");

  if (missing.length) {
    return [
      { label: isEnglish ? "Current Read" : "Leitura atual", value: isEnglish ? `${symbol}: missing ${missing.map((item) => localizeUiText(item, locale, symbol)).join(", ")}.` : `${symbol}: faltando ${missing.join(", ")}.` },
      { label: isEnglish ? "Operational Direction" : "Direcao operacional", value: isEnglish ? "Wait; the screen must not turn missing data into a trade." : "Aguardar; a tela nao deve transformar dado ausente em trade." },
      { label: isEnglish ? "Required Confirmation" : "Confirmacao necessaria", value: isEnglish ? "Confirmed price, valid candle, volume and regime/flow on the same side." : "Preco real, candle valido, volume e regime/fluxo no mesmo lado." },
      { label: isEnglish ? "Invalidation If" : "Invalidação Se", value: isEnglish ? "Any read without real price/volume stays as observation." : "Qualquer leitura sem preco/volume real fica em observacao." },
      { label: isEnglish ? "Risk" : "Risco", value: isEnglish ? "High if trading with incomplete data; keep it as watch." : "Alto se operar sem dado completo; manter como watch." },
    ];
  }

  const triggerFallback = `Confirm ${actionLabel} only with candle, volume, VWAP/EMA21 and flow aligned.`;
  const invalidationFallback = `Invalidate if price loses structure, volume or the regime that supported ${actionLabel}.`;
  const riskLevel = localizeUiText(marker?.risk_level || "medium", "en-US", symbol);
  const riskFallback = `Risk ${riskLevel}: size the trade carefully and avoid range noise.`;

  return [
    {
      label: isEnglish ? "Current Read" : "Leitura atual",
      value: isEnglish
        ? `${symbol}: ${localizeUiText(trend, locale, symbol)}; latest signal ${actionLabel} (${localizeUiText(latestSignal, locale, symbol)}).`
        : `${symbol}: ${trend}; ultimo sinal ${actionLabel} (${latestSignal}).`,
    },
    { label: isEnglish ? "Operational Direction" : "Direcao operacional", value: chartDirectionText(actionLabel, locale) },
    {
      label: isEnglish ? "Required Confirmation" : "Confirmacao necessaria",
      value: isEnglish
        ? cleanEnglishDecisionText(String(marker?.trigger || marker?.confirmation || ""), triggerFallback, symbol)
        : String(marker?.trigger || marker?.confirmation || "Confirmar candle, volume, VWAP/EMA21 e fluxo antes de agir."),
    },
    {
      label: isEnglish ? "Invalidation If" : "Invalidação Se",
      value: isEnglish
        ? cleanEnglishDecisionText(String(marker?.invalidation || ""), invalidationFallback, symbol)
        : String(marker?.invalidation || "Invalidar se perder estrutura, volume ou regime que sustentou o sinal."),
    },
    {
      label: isEnglish ? "Risk" : "Risco",
      value: isEnglish
        ? cleanEnglishDecisionText(String(marker?.risk || ""), riskFallback, symbol)
        : String(marker?.risk || `Risco ${marker?.risk_level || "medio"}; controle tamanho e evite lateralizacao.`),
    },
  ];
}

type DecisionTone = "bullish" | "bearish" | "neutral" | "watch" | "exit";

type EssentialDecisionCard = {
  label: string;
  value: string;
  tone: DecisionTone;
};

type StrategicConclusion = {
  headline: string;
  focus: string;
  basis: string[];
  tone: DecisionTone;
  stamp: string;
  sections?: Array<{
    title: string;
    body?: string;
    items?: string[];
  }>;
};

function currentFiveMinuteBucket() {
  return Math.floor(Date.now() / (5 * 60_000)) * 5;
}

function defaultAiToolSoundSettings() {
  const defaults: Record<string, boolean> = {};
  Object.values(AI_TOOL_TAB_MAP).forEach((toolKey) => {
    defaults[toolKey] = toolKey === "master_score";
  });
  return defaults;
}

function parseAiToolSoundSettings(value?: string | null) {
  const defaults = defaultAiToolSoundSettings();
  if (!value) return defaults;
  try {
    const parsed = JSON.parse(value);
    if (!parsed || typeof parsed !== "object") return defaults;
    return Object.fromEntries(
      Object.entries(defaults).map(([key, fallback]) => [key, typeof (parsed as Record<string, unknown>)[key] === "boolean" ? Boolean((parsed as Record<string, unknown>)[key]) : fallback]),
    ) as Record<string, boolean>;
  } catch {
    return defaults;
  }
}

function aiToolSoundEnabled(settings: Record<string, boolean>, toolKey?: string | null) {
  if (!toolKey) return false;
  if (typeof settings[toolKey] === "boolean") return settings[toolKey];
  return toolKey === "master_score";
}

function decisionToneFromText(...values: Array<unknown>): DecisionTone {
  const normalized = values
    .map((value) => normalizeUiText(String(value || "")))
    .filter(Boolean)
    .join(" ");
  if (!normalized) return "neutral";
  if (/\b(encerrar|cover|close short|close long|saida|sair|exit)\b/.test(normalized)) return "exit";
  if (/\b(short|sell short|venda descoberta|vender|venda|bear|baixa|queda|vendedor|distribuicao|negativo)\b/.test(normalized)) return "bearish";
  if (/\b(long|buy long|comprar|compra|bull|alta|comprador|acumulacao|positivo|forca)\b/.test(normalized)) return "bullish";
  return "neutral";
}

function decisionDirectionLabel(tone: DecisionTone, locale: AppLocale) {
  if (tone === "exit") return locale === "en-US" ? "Exit" : "Saída";
  if (tone === "bullish") return locale === "en-US" ? "Up" : "Alta";
  if (tone === "bearish") return locale === "en-US" ? "Down" : "Baixa";
  return locale === "en-US" ? "Range" : "Lateral";
}

function decisionTradeLabel(tone: DecisionTone, hasCoreData: boolean, locale: AppLocale) {
  if (tone === "exit") return locale === "en-US" ? "Close position" : "Encerrar posição";
  if (!hasCoreData) return locale === "en-US" ? "Wait" : "Aguardar";
  if (tone === "bullish") return locale === "en-US" ? "Buy/Long" : "Compra";
  if (tone === "bearish") return locale === "en-US" ? "Sell/Short" : "Short / Comprar vendido";
  return locale === "en-US" ? "Wait" : "Aguardar";
}

function tonesConflict(left: DecisionTone, right: DecisionTone) {
  return (left === "bullish" && right === "bearish") || (left === "bearish" && right === "bullish");
}

function resolveFlowCard(rows: AiToolRow[], locale: AppLocale): EssentialDecisionCard {
  const ranked = [...rows].sort((a, b) => Number(b.confidence || b.score || 0) - Number(a.confidence || a.score || 0));
  const best = ranked[0];
  if (!best) {
    return { label: locale === "en-US" ? "Institutional Flow" : "Fluxo Institucional", value: locale === "en-US" ? "No read" : "Sem leitura", tone: "neutral" };
  }
  const tone = decisionToneFromText(best.signal, best.state, best.ai_comment);
  const side = tone === "bullish"
    ? (locale === "en-US" ? "Buyer" : "Comprador")
    : tone === "bearish"
      ? (locale === "en-US" ? "Seller" : "Vendedor")
      : (locale === "en-US" ? "Neutral" : "Neutro");
  const score = Number(best.score);
  const suffix = Number.isFinite(score) ? ` ${score.toFixed(1)}` : "";
  return {
    label: locale === "en-US" ? "Institutional Flow" : "Fluxo Institucional",
    value: `${side}${suffix}`,
    tone: tone === "exit" ? "neutral" : tone,
  };
}

function resolveLiquidityTarget(chart: ChartPayload | null, price: number | null | undefined, tone: DecisionTone, locale: AppLocale) {
  const zones = Array.isArray(chart?.zones) ? chart?.zones || [] : [];
  const priceNumber = firstFiniteNumber(price);
  const preferred = zones
    .filter((zone: any) => {
      const label = normalizeUiText(zone?.label);
      if (tone === "bearish") return label.includes("suporte") || label.includes("support");
      if (tone === "bullish") return label.includes("resistencia") || label.includes("resistance");
      return true;
    })
    .map((zone: any) => {
      const zonePrice = firstFiniteNumber(zone?.price);
      const distance = priceNumber != null && zonePrice != null ? Math.abs(zonePrice - priceNumber) : Number.MAX_SAFE_INTEGER;
      return { zone, distance };
    })
    .sort((a, b) => a.distance - b.distance)[0]?.zone || zones[0];
  if (!preferred) return locale === "en-US" ? "No level" : "Sem nível";
  const rawLabel = String(preferred.label || "");
  const label = locale === "en-US"
    ? localizeUiText(rawLabel.replace("RESISTENCIA", "RESISTANCE").replace("SUPORTE", "SUPPORT"), locale)
    : rawLabel;
  return `${label || (locale === "en-US" ? "Level" : "Nível")}: ${formatLocalePrice(preferred.price, locale)}`;
}

function resolveRiskCard(
  score: number | null,
  hasCoreData: boolean,
  conflict: boolean,
  locale: AppLocale,
  rsi?: number | string | null,
  fallbackScore?: number | null,
): EssentialDecisionCard {
  const label = locale === "en-US" ? "Risk" : "Risco";
  const rsiNumber = firstValidRsiNumber(rsi);
  const extremeRsi = rsiNumber != null && (rsiNumber >= 70 || rsiNumber <= 30);
  const effectiveScore = score ?? fallbackScore;
  if (conflict || effectiveScore == null) return { label, value: locale === "en-US" ? "High" : "Alto", tone: "bearish" };
  if (!hasCoreData) {
    if (effectiveScore >= 7 && !extremeRsi) return { label, value: locale === "en-US" ? "Medium" : "Médio", tone: "watch" };
    if (effectiveScore >= 5.5) return { label, value: locale === "en-US" ? "Medium" : "Médio", tone: "watch" };
    return { label, value: locale === "en-US" ? "High" : "Alto", tone: "bearish" };
  }
  if (effectiveScore >= 7 && !extremeRsi) return { label, value: locale === "en-US" ? "Low" : "Baixo", tone: "bullish" };
  if (effectiveScore >= 5.5) return { label, value: locale === "en-US" ? "Medium" : "Médio", tone: "watch" };
  return { label, value: locale === "en-US" ? "High" : "Alto", tone: "bearish" };
}

type StrategicRiskLevel = "low" | "medium" | "high";

function strategicRiskLevelFromText(value?: string | null): StrategicRiskLevel {
  const normalized = normalizeUiText(value || "");
  if (/\b(high|alto|alta|elevado|elevada|forte)\b/.test(normalized)) return "high";
  if (/\b(low|baixo|baixa|reduzido|reduzida)\b/.test(normalized)) return "low";
  return "medium";
}

function buildStrategicConclusion(input: {
  locale: AppLocale;
  minuteTick: number;
  symbol: string;
  score: number | null;
  direction: string;
  trade: string;
  regime: string;
  flow: string;
  liquidity: string;
  risk: string;
  rsi: number | null;
  volume: number | null;
  averageVolume: number | null;
  relVolume: number | null;
  hasCoreData: boolean;
}): StrategicConclusion {
  const isEnglish = input.locale === "en-US";
  const assetLabel = input.symbol || (isEnglish ? "the asset" : "o ativo");
  const score = input.score;
  const regimeTone = decisionToneFromText(input.regime);
  const flowTone = decisionToneFromText(input.flow);
  const directionTone = decisionToneFromText(input.direction, input.trade);
  const riskTone = decisionToneFromText(input.risk);
  const riskLevel = strategicRiskLevelFromText(input.risk);
  const weakScore = score == null || score < 5.5;
  const strongScore = score != null && score >= 7;
  const moderateScore = score != null && score >= 5.5 && score < 7;
  const hasVolume = input.volume != null && input.volume > 0;
  const calculatedRvol = firstPositiveFiniteNumber(
    input.relVolume,
    calculateRelativeVolume(input.volume, input.averageVolume),
  );
  const estimatedRvol = calculatedRvol == null ? estimateRelativeVolumeFromActivity(input.volume) : null;
  const resolvedRvol = calculatedRvol ?? estimatedRvol;
  const rvolIsEstimated = calculatedRvol == null && estimatedRvol != null;
  const rvolBasis = resolvedRvol != null
    ? resolvedRvol >= 1.2
      ? (isEnglish
          ? `Relative Volume (RVOL): ${resolvedRvol.toFixed(2)}${rvolIsEstimated ? " estimated from current activity" : ""}. The asset is trading above normal volume, which can indicate stronger institutional interest and more relevant moves.`
          : `Volume Relativo (RVOL): ${resolvedRvol.toFixed(2)}${rvolIsEstimated ? " estimado pela atividade atual" : ""}. Significa que o ativo está negociando ${resolvedRvol.toFixed(2)} vezes acima do volume normal, o que costuma indicar maior interesse institucional e movimentos mais relevantes.`)
      : resolvedRvol < 0.8
        ? (isEnglish
            ? `Relative Volume (RVOL): ${resolvedRvol.toFixed(2)}${rvolIsEstimated ? " estimated from current activity" : ""}. The asset is trading below normal volume, so conviction is weaker.`
            : `Volume Relativo (RVOL): ${resolvedRvol.toFixed(2)}${rvolIsEstimated ? " estimado pela atividade atual" : ""}. O ativo negocia abaixo do volume normal, então a convicção é menor.`)
        : (isEnglish
            ? `Relative Volume (RVOL): ${resolvedRvol.toFixed(2)}${rvolIsEstimated ? " estimated from current activity" : ""}. Volume is close to the normal range, so price needs more confirmation.`
            : `Volume Relativo (RVOL): ${resolvedRvol.toFixed(2)}${rvolIsEstimated ? " estimado pela atividade atual" : ""}. O volume está perto do normal, então o preço ainda precisa confirmar melhor.`)
    : (isEnglish
        ? "Relative Volume (RVOL): unavailable."
        : "Volume Relativo (RVOL): indisponível.");
  const volumeBasis = hasVolume
    ? (isEnglish ? `Volume: current ${formatVolumeLong(input.volume, input.locale)}` : `Volume: atual de ${formatVolumeLong(input.volume, input.locale)}`)
    : (isEnglish ? "Volume: unavailable" : "Volume: indisponível");
  const rsiBasis = describeRsiValue(input.rsi, input.locale).basis;
  const scoreBasis = score == null
    ? (isEnglish ? "Master Score: no confirmed reading" : "Score Mestre: sem leitura confirmada")
    : score < 5.5
      ? (isEnglish ? `Low conviction: Score ${score.toFixed(1)}` : `Pouca convicção: Score ${score.toFixed(1)}`)
      : score < 7
        ? (isEnglish ? `Moderate conviction: Score ${score.toFixed(1)}` : `Convicção moderada: Score ${score.toFixed(1)}`)
        : (isEnglish ? `Strong conviction: Score ${score.toFixed(1)}` : `Convicção forte: Score ${score.toFixed(1)}`);
  const riskBasis = input.risk
    ? (isEnglish ? `Risk: ${input.risk}` : `Risco: ${input.risk}`)
    : (isEnglish ? "Risk: no read" : "Risco: sem leitura");
  const regimeBasis = input.regime
    ? (isEnglish ? `Main trend (BIAS): ${input.regime}` : `Tendência principal (BIAS): ${input.regime}`)
    : (isEnglish ? "Main trend (BIAS): no clear read" : "Tendência principal (BIAS): sem leitura clara");
  const flowBasis = input.flow
    ? (isEnglish ? `Institutional flow: ${input.flow}` : `Fluxo institucional: ${input.flow}`)
    : (isEnglish ? "Institutional flow without read" : "Fluxo institucional sem leitura");
  const basis = [regimeBasis, scoreBasis, riskBasis, flowBasis, volumeBasis, rvolBasis, rsiBasis];
  const stamp = new Date(input.minuteTick * 60_000).toLocaleTimeString(isEnglish ? "en-US" : "pt-BR", {
    hour: "2-digit",
    minute: "2-digit",
  });
  const normalizedDirection = normalizeUiText(input.direction);
  const normalizedTrade = normalizeUiText(input.trade);
  const normalizedRegime = normalizeUiText(input.regime);
  const sellPressure =
    directionTone === "bearish" ||
    normalizedDirection.includes("baixa") ||
    normalizedDirection.includes("short") ||
    normalizedTrade.includes("short") ||
    normalizedTrade.includes("venda") ||
    flowTone === "bearish";
  const regimePressure = regimeTone === "bearish" || normalizedRegime.includes("baixa");
  const bearishContext =
    sellPressure ||
    (regimePressure && !strongScore) ||
    (regimePressure && riskLevel === "high" && flowTone !== "bullish");
  const protectiveContext =
    directionTone === "exit" ||
    normalizedDirection.includes("saida") ||
    normalizedTrade.includes("encerrar") ||
    normalizedTrade.includes("cover") ||
    riskTone === "bearish";
  const dynamicFocus = (() => {
    if (!input.hasCoreData || !hasVolume) {
      if (hasVolume) {
        return isEnglish
          ? "Focus now: treat price and volume as context, but wait for real chart, liquidity and flow confirmation before execution."
        : "Foco Agora: usar preço e volume como contexto, mas aguardar gráfico real, liquidez e fluxo confirmarem antes da execução.";
      }
      return isEnglish
        ? "Focus now: do not execute operational trades until real price and volume are confirmed."
        : "Foco Agora: não executar operação até preço e volume reais ficarem confirmados.";
    }
    if (bearishContext || protectiveContext) {
      if (strongScore) {
        return isEnglish
          ? "Focus now: prioritize capital protection and only use short-side setups with chart confirmation."
          : "Foco Agora: preservar capital e considerar venda/short apenas com confirmação no gráfico.";
      }
      return isEnglish
        ? "Focus now: avoid long exposure while downside arguments remain stronger."
        : "Foco Agora: evitar exposição comprada enquanto os argumentos de baixa forem mais fortes.";
    }
    if (regimeTone === "bullish" && strongScore) {
      return resolvedRvol != null && resolvedRvol >= 1.2
        ? (isEnglish
            ? "Focus now: look for a clean pullback or breakout with volume confirmation."
            : "Foco Agora: buscar pullback defendido ou rompimento limpo com confirmação de volume.")
        : (isEnglish
            ? "Focus now: wait for volume to confirm before increasing long exposure."
            : "Foco Agora: aguardar o volume confirmar antes de aumentar exposição comprada.");
    }
    if (weakScore) {
      return isEnglish
        ? "Focus now: monitor only; conviction is too low to force a trade."
        : "Foco Agora: apenas monitorar; a convicção está baixa para forçar operação.";
    }
    return isEnglish
      ? "Focus now: wait for price, liquidity and flow to align before acting."
      : "Foco Agora: aguardar preço, liquidez e fluxo alinharem antes de agir.";
  })();

  if (!input.hasCoreData || !hasVolume || score == null) {
    return {
      headline: isEnglish
        ? "The operational read is incomplete. Use the panel as context and avoid execution until real price, volume and score are confirmed."
        : "A leitura operacional está incompleta. Use o painel como contexto e evite execução até preço, volume e Score Mestre ficarem confirmados.",
      focus: dynamicFocus,
      basis,
      tone: "watch",
      stamp,
    };
  }

  if ((bearishContext || protectiveContext) && flowTone !== "bullish") {
    return {
      headline: isEnglish ? "Current Scenario" : "Cenário Atual",
      focus: dynamicFocus,
      basis,
      tone: "bearish",
      stamp,
      sections: isEnglish
        ? [
            {
              title: "Current Scenario",
              body: `At this moment, ${assetLabel} shows higher downside probability or the need for caution instead of upside. Avoid long positions until the technical structure shows improvement, or consider short-side execution.`,
            },
            {
              title: "Strategic Directive",
              items: [
                "Preserve capital",
                "Reduce position size",
                "Wait for confirmation before entering",
                "Avoid aggressive entries",
              ],
            },
            {
              title: "Between Buy And Sell",
              items: [
                "The sell side has stronger arguments than the buy side",
                "Resistance zones are holding price",
                "Flow and aggression favor sellers",
              ],
            },
            {
              title: "Interpretation",
              body: "There is no certainty of a drop, but the current scenario favors short-side operations. Downside probability is higher than upside probability.",
            },
          ]
        : [
            {
              title: "📉 Cenário Atual",
              body: `O ativo ${assetLabel}: no momento, a análise indica maior probabilidade de queda ou necessidade de cautela, em vez de alta. A recomendação é evitar posições compradas até que a estrutura técnica mostre sinais de melhora. Ou comprar vendido.`,
            },
            {
              title: "🎯 Diretriz Estratégica",
              items: [
                "Preservar capital",
                "Reduzir tamanho das operações",
                "Aguardar confirmações antes de entrar",
                "Evitar entradas agressivas",
              ],
            },
            {
              title: "⚖️ Entre compra e venda",
              items: [
                "A venda apresenta mais argumentos do que a compra",
                "Resistências estão segurando o preço",
                "Fluxo e agressão favorecem os vendedores",
              ],
            },
            {
              title: "🔎 Interpretação",
              body: "Não há certeza de queda, mas o cenário atual favorece operações vendidas (short). A probabilidade de baixa é maior do que de alta.",
            },
          ],
    };
  }

  if ((directionTone === "exit" || normalizeUiText(input.trade).includes("encerrar") || normalizeUiText(input.trade).includes("close")) && !strongScore) {
    return {
      headline: isEnglish
        ? "The system is prioritizing protection. There is not enough evidence to open a new position now."
        : "O sistema está priorizando proteção. Ainda não há evidência suficiente para abrir uma nova posição agora.",
      focus: dynamicFocus,
      basis,
      tone: "exit",
      stamp,
    };
  }

  if (regimeTone === "bullish" && weakScore) {
    return {
      headline: isEnglish
        ? "The larger trend is still bullish, but there is not enough strength right now to justify a buy."
        : "A tendência maior ainda é de alta, mas neste momento não há força suficiente para justificar uma compra.",
      focus: dynamicFocus,
      basis,
      tone: "watch",
      stamp,
    };
  }

  if (regimeTone === "bearish" && weakScore) {
    return {
      headline: isEnglish
        ? "The structure remains weak. Avoid buying against the tape until flow or price reverses clearly."
        : "A estrutura continua fraca. Evite compra contra o movimento até fluxo ou preço virarem com clareza.",
      focus: dynamicFocus,
      basis,
      tone: "bearish",
      stamp,
    };
  }

  if (strongScore && (directionTone === "bullish" || regimeTone === "bullish")) {
    return {
      headline: isEnglish
        ? "The read favors continuation or buying, but the entry still needs chart confirmation."
        : "A leitura favorece continuação ou compra, mas a entrada ainda precisa de confirmação no gráfico.",
      focus: dynamicFocus,
      basis,
      tone: "bullish",
      stamp,
    };
  }

  if (strongScore && riskLevel !== "low" && regimeTone === "bearish" && flowTone !== "bullish") {
    return {
      headline: isEnglish
        ? "Current Scenario"
        : "Cenário Atual",
      focus: dynamicFocus,
      basis,
      tone: "bearish",
      stamp,
      sections: isEnglish
        ? [
            {
              title: "Current Scenario",
              body: `At this moment, ${assetLabel} shows higher downside probability or the need for caution instead of chasing upside. Avoid long exposure until the technical structure starts improving, or consider short-side execution only with confirmation.`,
            },
            {
              title: "Strategic Directive",
              items: [
                "Preserve capital",
                "Reduce position size",
                "Wait for confirmation before entering",
                "Avoid aggressive entries",
              ],
            },
            {
              title: "Between Buy And Sell",
              items: [
                "The sell side has stronger arguments than the buy side",
                "Resistance zones are holding price",
                "Flow and aggression favor sellers",
              ],
            },
            {
              title: "Interpretation",
              body: "There is no certainty of a drop, but the current scenario favors short-side operations. Downside probability is higher than upside probability.",
            },
          ]
        : [
            {
              title: "📉 Cenário Atual",
              body: `O ativo ${assetLabel}: no momento, a análise indica maior probabilidade de queda ou necessidade de cautela, em vez de alta. A recomendação é evitar posições compradas até que a estrutura técnica mostre sinais de melhora. Ou comprar vendido.`,
            },
            {
              title: "🎯 Diretriz Estratégica",
              items: [
                "Preservar capital",
                "Reduzir tamanho das operações",
                "Aguardar confirmações antes de entrar",
                "Evitar entradas agressivas",
              ],
            },
            {
              title: "⚖️ Entre compra e venda",
              items: [
                "A venda apresenta mais argumentos do que a compra",
                "Resistências estão segurando o preço",
                "Fluxo e agressão favorecem os vendedores",
              ],
            },
            {
              title: "🔎 Interpretação",
              body: "Não há certeza de queda, mas o cenário atual favorece operações vendidas (short). A probabilidade de baixa é maior do que a de alta.",
            },
          ],
    };
  }

  return {
    headline: moderateScore
      ? (isEnglish
          ? "The opportunity is moderate. The best action is to wait for confirmation instead of forcing a trade."
          : "A oportunidade é moderada. A melhor ação é aguardar confirmação em vez de forçar operação.")
      : (isEnglish
          ? "The reading is neutral. Let price, liquidity and flow choose the direction."
          : "A leitura está neutra. Deixe preço, liquidez e fluxo definirem a direção."),
    focus: dynamicFocus,
    basis,
    tone: "watch",
    stamp,
  };
}

function strategicSectionsForRender(conclusion: StrategicConclusion, locale: AppLocale, symbol: string) {
  const isEnglish = locale === "en-US";
  const assetLabel = normalizeSymbol(symbol) || (isEnglish ? "the asset" : "o ativo");
  const basisText = conclusion.basis.join(" | ");
  const scoreLine = conclusion.basis.find((item) => /score|convic/i.test(item)) || "";
  const riskLine = conclusion.basis.find((item) => /risk|risco/i.test(item)) || "";
  const regimeLine = conclusion.basis.find((item) => /bias|trend|tend[eê]ncia|regime/i.test(item)) || "";
  const flowLine = conclusion.basis.find((item) => /flow|fluxo/i.test(item)) || "";
  const rvolLine = conclusion.basis.find((item) => /rvol|volume relativo/i.test(item)) || "";
  const rsiLine = conclusion.basis.find((item) => /^rsi:/i.test(item)) || "";
  const scoreValue = Number(scoreLine.match(/(\d+(?:[.,]\d+)?)/)?.[1]?.replace(",", "."));
  const rvolValue = Number(rvolLine.match(/(\d+(?:[.,]\d+)?)/)?.[1]?.replace(",", "."));
  const rsiValue = Number(rsiLine.match(/(\d+(?:[.,]\d+)?)/)?.[1]?.replace(",", "."));
  const riskLevel = strategicRiskLevelFromText(riskLine);
  const lowConviction = /low conviction|pouca convic/i.test(basisText) || (Number.isFinite(scoreValue) && scoreValue < 5.5);
  const strongConviction = /strong conviction|convic[cç][aã]o forte/i.test(basisText) || (Number.isFinite(scoreValue) && scoreValue >= 7);
  const noFlow = /no read|sem leitura/i.test(flowLine);
  const buyerFlow = /buyer|comprador|buying/i.test(flowLine);
  const sellerFlow = /seller|vendedor|selling/i.test(flowLine);
  const regimeBull = /alta|uptrend|strong uptrend/i.test(regimeLine);
  const regimeBear = /baixa|downtrend|strong downtrend/i.test(regimeLine);
  const hasVolumeBoost = /above normal|acima do volume normal|maior interesse institucional/i.test(rvolLine) || (Number.isFinite(rvolValue) && rvolValue >= 1.2);
  const weakVolume = /below normal|abaixo do volume normal|convic/i.test(rvolLine) || (Number.isFinite(rvolValue) && rvolValue < 0.8);
  const overbought = Number.isFinite(rsiValue) && rsiValue >= 70;
  const oversold = Number.isFinite(rsiValue) && rsiValue <= 30;
  const rsiBullish = Number.isFinite(rsiValue) && rsiValue > 60;
  const rsiBearish = Number.isFinite(rsiValue) && rsiValue < 40;
  const scoreText = Number.isFinite(scoreValue) ? scoreValue.toFixed(1) : (isEnglish ? "n/a" : "sem leitura");
  const rvolText = Number.isFinite(rvolValue) ? rvolValue.toFixed(2) : (isEnglish ? "no read" : "sem leitura");
  const focusText = sentenceCaseFirst(
    conclusion.focus
      .replace(/^Focus now:\s*/i, "")
      .replace(/^Foco agora:\s*/i, "")
      .trim(),
    locale,
  );
  const incompleteRead =
    /incomplete|incompleta|sem leitura confirmada|no confirmed reading|n\/a|indispon/i.test(`${conclusion.headline} ${basisText}`) ||
    !Number.isFinite(scoreValue);
  const bullishSetup =
    !incompleteRead &&
    (conclusion.tone === "bullish" ||
      (strongConviction && riskLevel === "low" && !sellerFlow) ||
      (regimeBull && buyerFlow && !sellerFlow));
  const bearishSetup =
    !bullishSetup &&
    !incompleteRead &&
    (conclusion.tone === "bearish" ||
      conclusion.tone === "exit" ||
      sellerFlow ||
      (regimeBear && (riskLevel !== "low" || lowConviction)) ||
      (rsiBearish && lowConviction));
  const standardTitles = isEnglish
    ? {
        scenario: "Current Scenario",
        directive: "Strategic Directive",
        between: "Between Buy And Sell",
        interpretation: "Interpretation",
        focus: "Focus now",
      }
    : {
        scenario: "Cenário Atual",
        directive: "Direção da Estratégia",
        between: "Entre Venda e Compra",
        interpretation: "Interpretação",
        focus: "Foco Agora",
      };

  const scenarioBody = (() => {
    if (isEnglish) {
      if (incompleteRead) {
        return `${assetLabel}: the operational read is incomplete. Treat the panel as context and do not execute until price, volume, Master Score and chart structure are confirmed.`;
      }
      if (bullishSetup) {
        if (riskLevel === "low") return `${assetLabel}: low-risk constructive read. The buy side has priority, but execution still needs a clean 5-minute candle, volume and flow confirmation.`;
        if (riskLevel === "medium") return `${assetLabel}: constructive but not free risk. The buy thesis exists, yet size must be reduced until confirmation improves.`;
        return `${assetLabel}: upside signs exist, but risk is high. Do not chase; wait for stronger confirmation before any long exposure.`;
      }
      if (bearishSetup) {
        if (riskLevel === "low") return `${assetLabel}: downside pressure is present, but risk is low enough to require precision rather than panic. Shorts need a clear trigger and tight invalidation.`;
        if (riskLevel === "medium") return `${assetLabel}: medium-risk defensive read. Sellers have more evidence now, but entry needs price and volume confirmation.`;
        return `${assetLabel}: high-risk defensive read. Preserve capital and avoid new exposure until the next 5-minute structure confirms direction.`;
      }
      if (riskLevel === "low") return `${assetLabel}: neutral read with low risk. Wait for the market to choose a side; do not turn the low-risk label into an automatic trade.`;
      if (riskLevel === "medium") return `${assetLabel}: neutral read with medium risk. The correct stance is patience, smaller size and confirmation.`;
      return `${assetLabel}: neutral read with high risk. No operational side has enough quality for aggressive execution.`;
    }

    if (incompleteRead) {
      return `${assetLabel}: a leitura operacional está incompleta. Use o painel como contexto e não execute até preço, volume, Score Mestre e estrutura do gráfico ficarem confirmados.`;
    }
    if (bullishSetup) {
      if (riskLevel === "low") return `${assetLabel}: leitura construtiva com risco baixo. A compra tem prioridade, mas a execução ainda precisa de vela de 5 minutos limpa, volume e fluxo confirmando.`;
      if (riskLevel === "medium") return `${assetLabel}: leitura construtiva, porém com risco médio. A tese de compra existe, mas o tamanho deve ser reduzido até a confirmação melhorar.`;
      return `${assetLabel}: existem sinais de alta, mas o risco está alto. Não perseguir preço; aguardar confirmação mais forte antes de exposição comprada.`;
    }
    if (bearishSetup) {
      if (riskLevel === "low") return `${assetLabel}: há pressão de baixa, mas o risco baixo pede precisão, não pânico. Short precisa de gatilho claro e invalidação curta.`;
      if (riskLevel === "medium") return `${assetLabel}: leitura defensiva com risco médio. Vendedores têm mais evidência agora, mas a entrada precisa de confirmação de preço e volume.`;
      return `${assetLabel}: leitura defensiva com risco alto. Preservar capital e evitar nova exposição até a próxima estrutura de 5 minutos confirmar direção.`;
    }
    if (riskLevel === "low") return `${assetLabel}: leitura neutra com risco baixo. Espere o mercado escolher o lado; não transforme risco baixo em entrada automática.`;
    if (riskLevel === "medium") return `${assetLabel}: leitura neutra com risco médio. A postura correta é paciência, tamanho menor e confirmação.`;
    return `${assetLabel}: leitura neutra com risco alto. Nenhum lado operacional tem qualidade suficiente para execução agressiva.`;
  })();

  const directiveItems = (() => {
    if (isEnglish) {
      if (bullishSetup) {
        if (riskLevel === "low") {
          return [
            `Use Score ${scoreText} as a strength filter, but buy only after the 5-minute trigger confirms.`,
            hasVolumeBoost ? `Keep RVOL near ${rvolText} during the entry candle.` : "Require volume to improve before adding size.",
            "Place invalidation below support/VWAP or the failed breakout level.",
            overbought ? "RSI is stretched; prefer pullback entries, not chasing." : "Prefer defended pullbacks or clean breakouts.",
          ];
        }
        if (riskLevel === "medium") {
          return [
            "Reduce size until price, volume and flow align.",
            `Score ${scoreText} is useful, but not enough for aggressive execution.`,
            noFlow ? "Wait for institutional flow to confirm buyers." : "Use flow as the final confirmation.",
            "Avoid entering in the middle of the range.",
          ];
        }
        return [
          "Preserve capital even if the setup looks constructive.",
          "Do not open a full-size long while risk is high.",
          "Wait for a new 5-minute candle with volume and flow confirmation.",
          "Cancel the long plan if support/VWAP fails.",
        ];
      }
      if (bearishSetup) {
        if (riskLevel === "low") {
          return [
            "Plan short-side execution only with a clear trigger and tight invalidation.",
            `Respect Score ${scoreText}, but do not sell late into support.`,
            hasVolumeBoost ? `Use RVOL ${rvolText} as confirmation that the move matters.` : "Require volume before trusting the downside move.",
            oversold ? "RSI is oversold; wait for a fresh rejection before selling." : "Prefer resistance rejection, VWAP loss or support failure.",
          ];
        }
        if (riskLevel === "medium") {
          return [
            "Preserve capital and operate smaller size.",
            "Short only after support/VWAP loss or seller pressure confirms.",
            "Do not fight a sudden buyer-flow reversal.",
            "Avoid long exposure until structure improves.",
          ];
        }
        return [
          "Do not force a new position; high risk requires patience.",
          "Protect open trades and reduce exposure.",
          "Wait for the next 5-minute candle to confirm direction.",
          "Avoid leverage and late entries.",
        ];
      }
      if (riskLevel === "low") {
        return [
          `Score ${scoreText} allows monitoring with less defensive pressure, but confirmation is still mandatory.`,
          noFlow ? "Wait for institutional flow to choose a side." : "Let flow confirm the side.",
          weakVolume ? "Low RVOL keeps position size small." : "Use volume only if price confirms direction.",
          "Avoid entering before breakout or support defense.",
        ];
      }
      if (riskLevel === "medium") {
        return [
          "Keep position size reduced.",
          "Wait for price and volume confirmation before entering.",
          "Do not chase the first candle after a range move.",
          rsiBullish ? "RSI leans bullish, but still needs price confirmation." : rsiBearish ? "RSI leans bearish, but still needs support loss." : "RSI is neutral; do not force direction.",
        ];
      }
      return [
        "Preserve capital first.",
        "No new trade until real confirmation appears.",
        "Reduce exposure and wait for a cleaner 5-minute structure.",
        "Avoid aggressive entries while risk remains high.",
      ];
    }

    if (bullishSetup) {
      if (riskLevel === "low") {
        return [
          `Usar o Score ${scoreText} como filtro de força, mas comprar só após gatilho confirmado na vela de 5 minutos.`,
          hasVolumeBoost ? `Manter RVOL perto de ${rvolText} durante a vela de entrada.` : "Exigir melhora de volume antes de aumentar tamanho.",
          "Invalidação abaixo do suporte/VWAP ou do rompimento que falhar.",
          overbought ? "RSI está esticado; preferir pullback, não perseguição." : "Preferir pullback defendido ou rompimento limpo.",
        ];
      }
      if (riskLevel === "medium") {
        return [
          "Reduzir tamanho até preço, volume e fluxo alinharem.",
          `Score ${scoreText} ajuda, mas não autoriza execução agressiva sozinho.`,
          noFlow ? "Aguardar fluxo institucional confirmar compradores." : "Usar fluxo como confirmação final.",
          "Evitar entrada no meio da faixa.",
        ];
      }
      return [
        "Preservar capital mesmo com sinais construtivos.",
        "Não abrir compra cheia enquanto o risco estiver alto.",
        "Aguardar nova vela de 5 minutos com volume e fluxo confirmando.",
        "Cancelar plano comprado se perder suporte/VWAP.",
      ];
    }
    if (bearishSetup) {
      if (riskLevel === "low") {
        return [
          "Planejar venda/short apenas com gatilho claro e invalidação curta.",
          `Respeitar o Score ${scoreText}, mas não vender atrasado em cima do suporte.`,
          hasVolumeBoost ? `Usar RVOL ${rvolText} como confirmação de que o movimento importa.` : "Exigir volume antes de confiar na queda.",
          oversold ? "RSI está em sobrevenda; aguardar nova rejeição antes de vender." : "Preferir rejeição em resistência, perda de VWAP ou rompimento de suporte.",
        ];
      }
      if (riskLevel === "medium") {
        return [
          "Preservar capital e operar menor.",
          "Short somente após perda de suporte/VWAP ou pressão vendedora confirmada.",
          "Não brigar contra reversão repentina de fluxo comprador.",
          "Evitar exposição comprada até a estrutura melhorar.",
        ];
      }
      return [
        "Não forçar nova posição; risco alto exige paciência.",
        "Proteger operações abertas e reduzir exposição.",
        "Aguardar a próxima vela de 5 minutos confirmar direção.",
        "Evitar alavancagem e entradas atrasadas.",
      ];
    }
    if (riskLevel === "low") {
      return [
        `Score ${scoreText} permite monitorar com menor pressão defensiva, mas confirmação continua obrigatória.`,
        noFlow ? "Aguardar fluxo institucional escolher um lado." : "Deixar o fluxo confirmar o lado.",
        weakVolume ? "RVOL baixo mantém tamanho pequeno." : "Usar volume apenas se o preço confirmar direção.",
        "Evitar entrada antes de rompimento ou defesa clara de suporte.",
      ];
    }
    if (riskLevel === "medium") {
      return [
        "Manter tamanho reduzido.",
        "Aguardar confirmação de preço e volume antes de entrar.",
        "Não perseguir a primeira vela depois de lateralização.",
        rsiBullish ? "RSI inclina para alta, mas ainda precisa de preço confirmando." : rsiBearish ? "RSI inclina para baixa, mas ainda precisa de perda de suporte." : "RSI está neutro; não force direção.",
      ];
    }
    return [
      "Preservar capital primeiro.",
      "Sem nova operação até aparecer confirmação real.",
      "Reduzir exposição e esperar estrutura de 5 minutos mais limpa.",
      "Evitar entradas agressivas enquanto o risco permanecer alto.",
    ];
  })();

  const betweenItems = (() => {
    if (isEnglish) {
      if (incompleteRead) {
        return [
          "Buy is blocked until real price, volume and Master Score are confirmed.",
          "Sell/short is also blocked; incomplete data cannot create an operational edge.",
          "Waiting is the only valid decision until the real snapshot updates.",
        ];
      }
      if (bullishSetup) {
        if (riskLevel === "low") return [
          "Buy has the stronger argument if price holds support/VWAP.",
          "Sell only becomes attractive if the breakout fails or support is lost.",
          buyerFlow ? "Buyer flow supports the long thesis." : "Buyer flow still needs to confirm before sizing up.",
        ];
        if (riskLevel === "medium") return [
          "Buy has a thesis, but not enough freedom for aggressive size.",
          "Sell gains weight if support/VWAP fails with volume.",
          "The next confirmed 5-minute candle decides the side.",
        ];
        return [
          "Buy has signals, but risk blocks aggressive execution.",
          "Sell can appear quickly if the structure fails.",
          "Waiting is stronger than choosing a side too early.",
        ];
      }
      if (bearishSetup) {
        if (riskLevel === "low") return [
          "Sell has more evidence, but needs a precise trigger.",
          "Buy becomes valid only after buyer flow or resistance reclaim.",
          "Risk is low, so invalidation must be short and objective.",
        ];
        if (riskLevel === "medium") return [
          "Sell has more arguments than buy, but confirmation is mandatory.",
          "Buy is only a reaction trade if sellers lose control.",
          "Resistance and flow decide whether the short is worth taking.",
        ];
        return [
          "Neither side deserves aggressive execution under high risk.",
          "Selling late can be as dangerous as buying against the trend.",
          "Wait for liquidity and flow to stop conflicting.",
        ];
      }
      return [
        `Buy needs breakout or buyer flow because Score ${scoreText} is not enough alone.`,
        `Sell needs support loss or seller pressure; RVOL ${rvolText} shows whether the move matters.`,
        riskLevel === "high" ? "High risk makes waiting the dominant decision." : "Without confirmation, waiting is the strongest decision.",
      ];
    }

    if (incompleteRead) {
      return [
        "Compra fica bloqueada até preço, volume e Score Mestre reais confirmarem.",
        "Venda/short também fica bloqueada; dado incompleto não gera vantagem operacional.",
        "Aguardar é a única decisão válida até o snapshot real atualizar.",
      ];
    }
    if (bullishSetup) {
      if (riskLevel === "low") return [
        "A compra tem argumento mais forte se o preço sustentar suporte/VWAP.",
        "A venda só fica atraente se o rompimento falhar ou perder suporte.",
        buyerFlow ? "Fluxo comprador apoia a tese comprada." : "Fluxo comprador ainda precisa confirmar antes de aumentar tamanho.",
      ];
      if (riskLevel === "medium") return [
        "A compra tem tese, mas ainda não tem liberdade para tamanho agressivo.",
        "A venda ganha peso se perder suporte/VWAP com volume.",
        "A próxima vela de 5 minutos confirmada decide o lado.",
      ];
      return [
        "A compra tem sinais, mas o risco bloqueia execução agressiva.",
        "A venda pode aparecer rápido se a estrutura falhar.",
        "Aguardar é melhor do que escolher lado cedo demais.",
      ];
    }
    if (bearishSetup) {
      if (riskLevel === "low") return [
        "A venda tem mais evidência, mas precisa de gatilho preciso.",
        "A compra só fica válida com fluxo comprador ou retomada de resistência.",
        "Risco baixo exige invalidação curta e objetiva.",
      ];
      if (riskLevel === "medium") return [
        "A venda tem mais argumentos do que a compra, mas confirmação é obrigatória.",
        "Compra é apenas reação se vendedores perderem controle.",
        "Resistência e fluxo decidem se o short vale o risco.",
      ];
      return [
        "Nenhum lado merece execução agressiva com risco alto.",
        "Vender atrasado pode ser tão perigoso quanto comprar contra a tendência.",
        "Aguardar liquidez e fluxo pararem de conflitar.",
      ];
    }
    return [
      `A compra precisa de rompimento ou fluxo comprador porque Score ${scoreText} sozinho não basta.`,
      `A venda precisa de perda de suporte ou pressão vendedora; RVOL ${rvolText} mostra se o movimento tem relevância.`,
      riskLevel === "high" ? "Risco alto torna aguardar a decisão dominante." : "Sem confirmação, aguardar é a melhor decisão.",
    ];
  })();

  const interpretationBody = (() => {
    if (isEnglish) {
      if (incompleteRead) return "There is not enough real data for an operational decision. The professional choice is to wait until price, volume and score are confirmed.";
      if (bullishSetup) {
        if (riskLevel === "low") return `Low risk plus Score ${scoreText} favors a controlled long plan, but only if the chart confirms. ${overbought ? "RSI is stretched, so wait for a pullback." : "The probability of upside is better while structure holds."}`;
        if (riskLevel === "medium") return `The long thesis is possible, but medium risk requires smaller size and confirmation from ${hasVolumeBoost ? `RVOL ${rvolText}` : "volume"} and flow.`;
        return "Upside exists, but high risk makes the setup unsuitable for aggressive execution right now.";
      }
      if (bearishSetup) {
        if (riskLevel === "low") return `The sell/short side has evidence, but low risk means the setup should be executed with precision, not emotion. ${oversold ? "RSI is already stretched lower, so avoid selling late." : "A clean trigger is still required."}`;
        if (riskLevel === "medium") return `Medium risk means the bearish read is tradable only after confirmation. Until then, the right action is defensive patience.`;
        return "High risk means capital preservation comes first. Do not force buy or short until the next confirmed structure appears.";
      }
      if (riskLevel === "low") return "The read is neutral with controlled risk; the trader should wait for a clean trigger instead of guessing direction.";
      if (riskLevel === "medium") return "The read is mixed; medium risk demands confirmation and smaller sizing before any execution.";
      return "The read is mixed and risk is high; the correct professional action is to stand aside.";
    }

    if (incompleteRead) return "Não há dados reais suficientes para decisão operacional. A escolha profissional é aguardar até preço, volume e score ficarem confirmados.";
    if (bullishSetup) {
      if (riskLevel === "low") return `Risco baixo com Score ${scoreText} favorece um plano comprador controlado, mas só se o gráfico confirmar. ${overbought ? "RSI está esticado; aguarde pullback." : "A probabilidade de alta é melhor enquanto a estrutura sustentar."}`;
      if (riskLevel === "medium") return `A tese comprada existe, mas risco médio exige tamanho menor e confirmação de ${hasVolumeBoost ? `RVOL ${rvolText}` : "volume"} e fluxo.`;
      return "Existe leitura de alta, mas risco alto torna o setup inadequado para execução agressiva agora.";
    }
    if (bearishSetup) {
      if (riskLevel === "low") return `Venda/short tem evidência, mas risco baixo exige execução precisa, não emocional. ${oversold ? "RSI já está esticado para baixo; evite vender atrasado." : "Ainda precisa de gatilho limpo."}`;
      if (riskLevel === "medium") return "Risco médio significa que a leitura de baixa só vira trade após confirmação. Até lá, a postura correta é paciência defensiva.";
      return "Risco alto coloca preservação de capital em primeiro lugar. Não force compra nem short até aparecer nova estrutura confirmada.";
    }
    if (riskLevel === "low") return "A leitura é neutra com risco controlado; o trader deve esperar gatilho limpo em vez de adivinhar direção.";
    if (riskLevel === "medium") return "A leitura está mista; risco médio exige confirmação e tamanho menor antes de qualquer execução.";
    return "A leitura está mista e o risco está alto; a decisão profissional é ficar de fora.";
  })();

  const focusBody = (() => {
    if (focusText) return focusText;
    if (isEnglish) {
      if (riskLevel === "low") return bullishSetup ? "Wait for the 5-minute trigger, then execute with defined invalidation." : "Wait for a clean trigger; low risk is not a license to enter early.";
      if (riskLevel === "medium") return "Trade smaller and only after price, volume and flow confirm.";
      return "Protect capital and wait for risk to drop before acting.";
    }
    if (riskLevel === "low") return bullishSetup ? "Aguardar gatilho de 5 minutos e executar com invalidação definida." : "Aguardar gatilho limpo; risco baixo não autoriza entrada antecipada.";
    if (riskLevel === "medium") return "Operar menor e só depois de preço, volume e fluxo confirmarem.";
    return "Proteger capital e aguardar o risco cair antes de agir.";
  })();

  return [
    { title: standardTitles.scenario, body: scenarioBody },
    { title: standardTitles.directive, items: directiveItems },
    { title: standardTitles.between, items: betweenItems },
    { title: standardTitles.interpretation, body: interpretationBody },
    { title: standardTitles.focus, body: focusBody },
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
    if (Math.abs(value) >= 1000) return formatCompact(value, locale);
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
  const { count, stepMs, startMs } = chartFallbackShape(normalizedInterval);
  const change = firstFiniteNumber(quote?.change);
  const changePct = firstFiniteNumber(quote?.change_pct) ?? 0;
  const startPrice = change != null ? Math.max(price - change, price * 0.97) : price * (1 - changePct / 100);
  const seed = normalizeSymbol(symbol).split("").reduce((total, char) => total + char.charCodeAt(0), 0);
  const trendText = String(trend || "").toLowerCase();
  const bullish = changePct > 0 || trendText.includes("alta") || trendText.includes("buy") || trendText.includes("compra");
  const volatility = Math.max(price * 0.0015, Math.abs(price - startPrice) * 0.18, price * 0.0008);
  const ohlc = Array.from({ length: count }, (_, index) => {
    const t = count === 1 ? 1 : index / (count - 1);
    const wave = Math.sin((index + seed) * 0.72) * volatility + Math.cos((index + seed) * 0.31) * volatility * 0.55;
    const close = index === count - 1 ? price : startPrice + (price - startPrice) * t + wave;
    const previousBase = index === 0 ? startPrice : startPrice + (price - startPrice) * ((index - 1) / (count - 1));
    const open = index === 0 ? startPrice : previousBase + Math.sin((index - 1 + seed) * 0.72) * volatility;
    const high = Math.max(open, close) + volatility * (0.8 + ((index + seed) % 5) / 10);
    const low = Math.min(open, close) - volatility * (0.8 + ((index + seed) % 4) / 10);
    return {
      time: new Date(startMs + index * stepMs).toISOString(),
      open,
      high,
      low,
      close,
      volume: Math.max(1, Number(quote?.volume || 0) / count) * (0.65 + ((index + seed) % 9) / 10),
      ema9: close,
      ema21: close,
      supertrend: close,
      supertrend_side: bullish ? "buy" : "sell",
      source: "quote_visual_fallback",
    };
  });
  const highs = ohlc.map((bar) => bar.high);
  const lows = ohlc.map((bar) => bar.low);
  const resistance = Math.max(...highs);
  const support = Math.min(...lows);

  return {
    ticker: normalizeSymbol(symbol),
    interval: normalizedInterval,
    ohlc,
    series: ohlc,
    markers: [],
    zones: [
      { label: "resistência", price: resistance },
      { label: "suporte", price: support },
    ],
    summary: {
      ticker: normalizeSymbol(symbol),
      latest_close: price,
      trend_bias: bullish ? "alta" : changePct < 0 ? "baixa" : "lateral",
      source: "quote_visual_fallback",
      fallback: true,
      synthetic: true,
      interval: normalizedInterval,
    },
    fallback: true,
    synthetic: true,
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
  locale?: AppLocale;
}) {
  const locale = input.locale ?? "pt-BR";
  const scoreValue = Number.isFinite(Number(input.score)) ? Number(input.score) : 5;
  const changeText = input.changePct != null ? formatSignedPercent(input.changePct) : "sem variação confirmada";
  const priceText = input.price != null ? formatPrice(input.price, locale) : "preço pendente";
  const volumeText = input.volume != null ? formatCompact(input.volume, locale) : "volume pendente";
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
  const scoreInvalidation = isBullish && scoreValue >= 5
    ? `Perde a leitura se Score cair abaixo de ${scoreValue >= 7 ? "6.5" : "5.0"}, força voltar a neutra ou surgir ${oppositeSide} dominante no tape.`
    : `Perde a leitura se o preço recuperar VWAP/zona chave, fluxo comprador dominar ou Score voltar acima de 5.0.`;

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
        invalidation: scoreInvalidation,
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
        invalidation: scoreValue >= 5
          ? `Baixar prioridade se Score perder força, volume divergir ou outra IA principal apontar direção oposta.`
          : `Perde leitura se preço e volume não confirmarem a tese, fluxo virar contra o sinal ou outra IA principal apontar direção oposta.`,
      };
    default:
      return base;
  }
}

function buildAiToolTextFallback(
  row: Partial<AiToolRow>,
  locale: AppLocale,
  symbol: string,
  kind: "main" | "trigger" | "invalidation" = "main",
) {
  const ticker = normalizeSymbol(symbol || row.ticker || "");
  const score = Number(row.score);
  const scoreText = Number.isFinite(score) ? score.toFixed(1) : "n/a";
  const priceText = formatLocalePrice(row.price, locale);
  const changeText = row.change_pct != null ? formatSignedPercent(row.change_pct) : "n/a";
  const volumeText = formatLiquidityVolume(row.volume ?? null, row.rel_volume ?? null, locale);
  const rvolText = row.rel_volume != null && Number(row.rel_volume) > 0 ? Number(row.rel_volume).toFixed(2) : (locale === "en-US" ? "no read" : "sem leitura");
  const rsiText = row.rsi != null ? Number(row.rsi).toFixed(1) : (locale === "en-US" ? "no read" : "sem leitura");
  const tone = decisionToneFromText(row.signal, row.state, row.ai_comment);
  const sideEn = tone === "bullish" ? "buy side" : tone === "bearish" ? "sell/short side" : "watch side";
  const sidePt = tone === "bullish" ? "lado comprador" : tone === "bearish" ? "lado vendedor/short" : "monitoramento";

  if (locale === "en-US") {
    if (kind === "trigger") return `Act only when ${ticker} confirms the ${sideEn} with price, volume and RVOL ${rvolText}.`;
    if (kind === "invalidation") return `Cancel the read if price, flow or liquidity turns against the ${sideEn}.`;
    return `${ticker}: Score ${scoreText}, price ${priceText}, change ${changeText}, volume ${volumeText}, RVOL ${rvolText}, RSI ${rsiText}. Treat it as an operational read only after confirmation.`;
  }

  if (kind === "trigger") return `Agir somente quando ${ticker} confirmar o ${sidePt} com preço, volume e RVOL ${rvolText}.`;
  if (kind === "invalidation") return `Cancelar a leitura se preço, fluxo ou liquidez virarem contra o ${sidePt}.`;
  return `${ticker}: Score ${scoreText}, preço ${priceText}, variação ${changeText}, volume ${volumeText}, RVOL ${rvolText}, RSI ${rsiText}. Use como leitura operacional apenas com confirmação.`;
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
  if (sentiment === "bearish") return locale === "en-US" ? "Bearish" : "Urso";
  if (sentiment === "bullish") return locale === "en-US" ? "Bullish" : "Touro";
  return locale === "en-US" ? "😐 Neutral" : "😐 Neutro";
}

function MarketAnimalIcon({ tone }: { tone: "bullish" | "bearish" }) {
  return (
    <span className={`snbr-market-icon ${tone}`} aria-hidden="true">
      {tone === "bullish" ? "🐂" : "🐻"}
    </span>
  );
}

function SentimentLabel({ sentiment, locale }: { sentiment?: string | null; locale: AppLocale }) {
  if (sentiment === "bullish" || sentiment === "bearish") {
    return (
      <>
        <MarketAnimalIcon tone={sentiment} />
        <span>{sentimentDisplay(sentiment, locale)}</span>
      </>
    );
  }
  return <>{sentimentDisplay(sentiment, locale)}</>;
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
    "weak setup": "Setup Fraco",
    "neutral setup": "Setup Neutro",
    "moderate setup": "Setup Neutro",
    "good setup": "Setup Bom",
    "strong setup": "Setup Bom",
    "excellent setup": "Setup Ótimo",
    "great setup": "Setup Ótimo",
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
    "weak setup": "Weak Setup",
    "neutral setup": "Neutral Setup",
    "moderate setup": "Moderate Setup",
    "good setup": "Good Setup",
    "strong setup": "Strong Setup",
    "excellent setup": "Excellent Setup",
    "great setup": "Excellent Setup",
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

function playSyntheticMoneyFindingSound() {
  if (typeof window === "undefined") return;
  const AudioCtor = window.AudioContext || (window as Window & typeof globalThis & { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
  if (!AudioCtor) return;

  const context = new AudioCtor();
  const now = context.currentTime;
  const notes = [
    { frequency: 880, start: 0, duration: 0.09 },
    { frequency: 1174.66, start: 0.1, duration: 0.11 },
    { frequency: 1567.98, start: 0.22, duration: 0.16 },
  ];

  notes.forEach((note) => {
    const oscillator = context.createOscillator();
    const gain = context.createGain();
    oscillator.type = "triangle";
    oscillator.frequency.setValueAtTime(note.frequency, now + note.start);
    gain.gain.setValueAtTime(0.001, now + note.start);
    gain.gain.exponentialRampToValueAtTime(0.18, now + note.start + 0.02);
    gain.gain.exponentialRampToValueAtTime(0.001, now + note.start + note.duration);
    oscillator.connect(gain);
    gain.connect(context.destination);
    oscillator.start(now + note.start);
    oscillator.stop(now + note.start + note.duration + 0.03);
  });

  window.setTimeout(() => {
    void context.close().catch(() => undefined);
  }, 650);
}

function playMoneyFindingSound() {
  if (typeof window === "undefined") return;

  try {
    const audio = new Audio(AI_DEAL_SOUND_URL);
    audio.preload = "auto";
    audio.volume = 0.9;
    audio.currentTime = 0;
    void audio.play().catch(() => playSyntheticMoneyFindingSound());
  } catch {
    playSyntheticMoneyFindingSound();
  }
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
  const saved = readStorageValue(APP_LOCALE_STORAGE_KEY);
  return saved === "en-US" ? "en-US" : "pt-BR";
}

function readStorageValue(key: string) {
  if (typeof window === "undefined") return null;
  try {
    return window.localStorage.getItem(key);
  } catch {
    return null;
  }
}

function writeStorageValue(key: string, value: string) {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(key, value);
  } catch {
    // Storage can be unavailable in private/locked browser contexts.
  }
}

function removeStorageValue(key: string) {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.removeItem(key);
  } catch {
    // Best-effort cleanup only.
  }
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
  const normalized = normalizeUiText(value);
  const ticker = normalizeSymbol(selectedTicker);

  if (
    normalized.includes("nesta semana") &&
    (normalized.includes("confirmacao mais importante") || normalized.includes("mais importante vem")) &&
    normalized.includes("volume") &&
    normalized.includes("rompimento") &&
    normalized.includes("defesa de faixa")
  ) {
    return `${ticker}: this week, does the most important confirmation come from breakout volume or range defense?`;
  }
  if (normalized.includes("sem enquete institucional carregada")) {
    return `${ticker}: no institutional poll is loaded; which confirmation is still missing to validate this week's thesis?`;
  }
  if (normalized.includes("volume confirma rompimento da faixa")) return "Volume confirms the range breakout";
  if (normalized.includes("volume no rompimento")) return "Breakout volume";
  if (normalized.includes("preco romper nivel com volume real")) return "Price breaks a level with real volume";
  if (normalized.includes("fluxo ou noticia confirmar contexto")) return "Flow or news confirms the context";
  if (normalized.includes("defesa de faixa ainda manda")) return "Range defense is still in control";
  if (normalized.includes("defesa de faixa")) return "Range defense";

  return localizeUiText(value
    .replace(`${selectedTicker}: sem evento dominante, o mercado precisa confirmar fluxo comprador ou rejeicao de risco?`, `${selectedTicker}: with no dominant event, does the market need to confirm buying flow or risk rejection?`)
    .replace("Fluxo comprador precisa aparecer", "Buying flow needs to appear")
    .replace("Rejeicao de risco ainda pesa", "Risk rejection still weighs")
    .replace("Volume confirma rompimento da faixa", "Volume confirms the range breakout")
    .replace("Defesa de faixa ainda manda", "Range defense is still in control")
    .replace("sem evento dominante", "no dominant event")
    .replace("mercado precisa confirmar", "market needs to confirm")
    .replace("fluxo comprador", "buying flow")
    .replace("rejeicao de risco", "risk rejection"), locale, selectedTicker);
}

function getBrowserDeviceId() {
  if (typeof window === "undefined") return "web-browser";

  const storageKey = "stocknewsbr.web_device_id";
  const current = readStorageValue(storageKey);

  if (current) return current;

  const created = typeof crypto !== "undefined" && "randomUUID" in crypto
    ? crypto.randomUUID()
    : `browser-${Date.now()}`;
  writeStorageValue(storageKey, created);
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
    if (isRemovedFutureSymbol(item.symbol)) continue;
    bySymbol.set(item.symbol, { ...item });
  }

  for (const row of ranking || []) {
    const symbol = normalizeSymbol(String(row.symbol || ""));
    if (!symbol || isRemovedFutureSymbol(symbol)) continue;

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
    if (!symbol || isRemovedFutureSymbol(symbol)) continue;

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
      if (!normalized || isRemovedFutureSymbol(normalized)) continue;
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
  if (!normalized || existingSymbols.includes(normalized) || isRemovedFutureSymbol(normalized)) return null;

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
  const [publicAiTools, setPublicAiTools] = useState<PublicAiToolsPayload | null>(null);
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
  const [advancedMode, setAdvancedMode] = useState(false);
  const [appLocale, setAppLocale] = useState<AppLocale>(readInitialLocale);
  const isUsLocale = appLocale === "en-US";
  const normalizedAccessPlan = String(access?.plan || "").toLowerCase();
  const normalizedAccessStatus = String(access?.plan_status || "").toLowerCase();
  const proModeLocked = Boolean(
    token &&
      access &&
      (["free", "basic", "basico", "básico"].includes(normalizedAccessPlan) ||
        ["expired", "inactive", "cancelled", "canceled", "trial_expired"].includes(normalizedAccessStatus)),
  );

  useEffect(() => {
    if (typeof window === "undefined") return;
    writeStorageValue(APP_LOCALE_STORAGE_KEY, appLocale);
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
    () => Array.from(new Set([...PRELOADED_UNIVERSE.map((item) => item.symbol), ...customWatchItems.map((item) => item.symbol), selectedTicker])).filter((symbol) => !isRemovedFutureSymbol(symbol)),
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
            .filter((item) => !isRemovedFutureSymbol(item.symbol))
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
        ...customWatchItems.map((item) => item.symbol).filter((symbol) => !isRemovedFutureSymbol(symbol)),
      ]),
    );
  }, [activeWatchSymbols, customWatchItems, selectedTicker]);
  const publicTickerTapeKey = publicTickerTapeSymbols.join("|");
  const publicWatchKey = publicWatchSymbols.join("|");
  const priorityPublicWatchKey = priorityPublicWatchSymbols.join("|");
  const visiblePublicWatchKey = visiblePublicWatchSymbols.join("|");
  const [tickerTapePaused, setTickerTapePaused] = useState(false);
  const [darkMode, setDarkMode] = useState(false);
  const [aiToolSoundSettings, setAiToolSoundSettings] = useState<Record<string, boolean>>(defaultAiToolSoundSettings);
  const [settingsTab, setSettingsTab] = useState<SettingsTab>("preferencias");
  const [accountPanel, setAccountPanel] = useState<AccountPanel>("perfil");
  const [notificationOpen, setNotificationOpen] = useState(false);
  const [toolsOpen, setToolsOpen] = useState(false);
  const [strategicConclusionOpen, setStrategicConclusionOpen] = useState(true);
  const [strategicAnalysisMinute, setStrategicAnalysisMinute] = useState(() => currentFiveMinuteBucket());
  const [selectedInstitutionalSectionId, setSelectedInstitutionalSectionId] = useState<string | null>(null);
  const [showMarkers, setShowMarkers] = useState(DEFAULT_CHART_SETTINGS.show_markers);
  const [showZones, setShowZones] = useState(DEFAULT_CHART_SETTINGS.show_zones);
  const [showPriceLine, setShowPriceLine] = useState(DEFAULT_CHART_SETTINGS.show_price_line);
  const [showVwap, setShowVwap] = useState(DEFAULT_CHART_SETTINGS.show_vwap);
  const [showAverages, setShowAverages] = useState(DEFAULT_CHART_SETTINGS.show_averages);
  const [showMacd, setShowMacd] = useState(DEFAULT_CHART_SETTINGS.show_macd);
  const [showRsi, setShowRsi] = useState(DEFAULT_CHART_SETTINGS.show_rsi);
  const [showSupertrend, setShowSupertrend] = useState(DEFAULT_CHART_SETTINGS.show_supertrend);
  const [showVolume, setShowVolume] = useState(DEFAULT_CHART_SETTINGS.show_volume);
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
  const aiSoundLastKeyRef = useRef<string | null>(null);
  const aiSoundSuppressedUntilRef = useRef<number>(0);

  useEffect(() => {
    publicQuotesRef.current = publicQuotes;
  }, [publicQuotes]);

  useEffect(() => {
    tickerTapeQuotesRef.current = tickerTapeQuotes;
  }, [tickerTapeQuotes]);

  useEffect(() => {
    const stored =
      queryToken ||
      readStorageValue("stocknewsbr.token") ||
      process.env.NEXT_PUBLIC_DEFAULT_TOKEN ||
      "";

    if (stored) setToken(stored);
  }, [queryToken]);

  useEffect(() => {
    getBootstrap().then(setBootstrap).catch(() => undefined);
  }, []);

  useEffect(() => {
    const storedMode = readStorageValue(WORKSPACE_MODE_STORAGE_KEY);
    setAdvancedMode(storedMode === "pro");
  }, []);

  useEffect(() => {
    writeStorageValue(WORKSPACE_MODE_STORAGE_KEY, advancedMode ? "pro" : "simple");
  }, [advancedMode]);

  useEffect(() => {
    if (proModeLocked && advancedMode) setAdvancedMode(false);
  }, [advancedMode, proModeLocked]);

  useEffect(() => {
    setPredictionSymbol(selectedTicker);
  }, [selectedTicker]);

  useEffect(() => {
    const storedDark = readStorageValue("stocknewsbr.dark_mode");
    if (storedDark === "1") setDarkMode(true);
    setAiToolSoundSettings(parseAiToolSoundSettings(readStorageValue(AI_TOOL_SOUND_STORAGE_KEY)));

    const storedBlocked = readStorageValue("stocknewsbr.blocked_users");
    if (storedBlocked) {
      try {
        const parsed = JSON.parse(storedBlocked);
        if (Array.isArray(parsed)) setBlockedUsers(parsed);
      } catch {
        // ignore parse issue
      }
    }

    const storedSilenced = readStorageValue("stocknewsbr.silenced_users");
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
    writeStorageValue("stocknewsbr.dark_mode", darkMode ? "1" : "0");
  }, [darkMode]);

  useEffect(() => {
    writeStorageValue(AI_TOOL_SOUND_STORAGE_KEY, JSON.stringify(aiToolSoundSettings));
  }, [aiToolSoundSettings]);

  useEffect(() => {
    writeStorageValue("stocknewsbr.blocked_users", JSON.stringify(blockedUsers));
  }, [blockedUsers]);

  useEffect(() => {
    writeStorageValue("stocknewsbr.silenced_users", JSON.stringify(silencedUsers));
  }, [silencedUsers]);

  useEffect(() => {
    const chartSettings = workspace?.layout?.chart_settings;
    setShowMarkers(chartSettings?.show_markers ?? DEFAULT_CHART_SETTINGS.show_markers);
    setShowZones(chartSettings?.show_zones ?? DEFAULT_CHART_SETTINGS.show_zones);
    setShowPriceLine(chartSettings?.show_price_line ?? DEFAULT_CHART_SETTINGS.show_price_line);
    setShowVwap(chartSettings?.show_vwap ?? DEFAULT_CHART_SETTINGS.show_vwap);
    setShowAverages(chartSettings?.show_averages ?? DEFAULT_CHART_SETTINGS.show_averages);
    setShowMacd(chartSettings?.show_macd ?? DEFAULT_CHART_SETTINGS.show_macd);
    setShowRsi(chartSettings?.show_rsi ?? DEFAULT_CHART_SETTINGS.show_rsi);
    setShowSupertrend(chartSettings?.show_supertrend ?? DEFAULT_CHART_SETTINGS.show_supertrend);
    setShowVolume(chartSettings?.show_volume ?? DEFAULT_CHART_SETTINGS.show_volume);
  }, [
    workspace?.layout?.chart_settings?.show_markers,
    workspace?.layout?.chart_settings?.show_zones,
    workspace?.layout?.chart_settings?.show_price_line,
    workspace?.layout?.chart_settings?.show_vwap,
    workspace?.layout?.chart_settings?.show_averages,
    workspace?.layout?.chart_settings?.show_macd,
    workspace?.layout?.chart_settings?.show_rsi,
    workspace?.layout?.chart_settings?.show_supertrend,
    workspace?.layout?.chart_settings?.show_volume,
  ]);

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
    if (token || !watchlistQuery.trim()) return;
    const symbol = resolveTypedSymbol(watchlistQuery.trim());
    if (!symbol || isRemovedFutureSymbol(symbol)) return;
    const currentQuote = resolveQuoteForSymbol(symbol, publicQuotesRef.current, tickerTapeQuotesRef.current);
    if (quoteHasMarketValue(currentQuote)) return;

    let cancelled = false;
    const timeout = window.setTimeout(() => {
      getPublicQuotesRobust([symbol], 1, 0)
        .then((nextQuotes) => {
          if (cancelled) return;
          const quoteMap = Object.fromEntries((nextQuotes?.items || []).map((item) => [item.symbol, item]));
          if (Object.keys(quoteMap).length) {
            setTickerTapeQuotes((current) => mergeQuoteState(current, quoteMap));
            setPublicQuotes((current) => mergeQuoteState(current, quoteMap));
          }
        })
        .catch(() => undefined);
    }, 260);

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
      setPublicChart((current: any) => (sameChartRequest(current, deferredTicker, chartInterval) ? current : null));
      setFeed(null);
      setRoom(null);
      setPushStatus(null);
      setMediaStatus(null);

      getPublicMarketBundle(deferredTicker, chartInterval)
        .then((bundle) => {
          if (cancelled) return;

          const nextQuote = bundle?.quote || null;
          const nextInsight = bundle?.insight || null;
          const nextChart = bundle?.chart || null;
          const nextNews = bundle?.news || null;
          const nextPublicAiTools = bundle?.ai_tools || null;

          if (nextQuote?.symbol) {
            const normalizedQuoteSymbol = normalizeSymbol(nextQuote.symbol);
            const normalizedQuote = { ...nextQuote, symbol: normalizedQuoteSymbol };
            setPublicQuotes((current) => mergeQuoteState(current, { [normalizedQuoteSymbol]: normalizedQuote }));
            setTickerTapeQuotes((current) => mergeQuoteState(current, { [normalizedQuoteSymbol]: normalizedQuote }));
          }
          setPublicInsight(sameSymbol(nextInsight?.symbol, deferredTicker) ? { ...nextInsight, symbol: deferredTicker } : null);
          setPublicChart(sameChartRequest(nextChart, deferredTicker, chartInterval) ? { ...nextChart, ticker: deferredTicker } : null);
          setQuote(nextQuote);
          setNews((current) => {
            const currentCount = Number(current?.count ?? current?.items?.length ?? 0);
            const nextCount = Number(nextNews?.count ?? nextNews?.items?.length ?? 0);
            if (sameSymbol(current?.symbol, deferredTicker) && currentCount > 0 && nextCount <= 0) return current;
            return nextNews;
          });
          setPublicAiTools(nextPublicAiTools);
        })
        .catch((requestError: Error) => {
          if (!cancelled) setError(requestError.message);
        })
        .finally(() => {
          if (!cancelled) setLoading(false);
        });

      const initialQuoteSymbols = Array.from(new Set([...priorityPublicWatchSymbols, ...publicTickerTapeSymbols]));

      getPublicQuotesRobust(initialQuoteSymbols, 32, 0)
        .then((nextQuotes) => {
          if (cancelled) return;
          const quoteMap = Object.fromEntries((nextQuotes?.items || []).map((item) => [item.symbol, item]));
          setTickerTapeQuotes((current) => mergeQuoteState(current, quoteMap));
          setPublicQuotes((current) => mergeQuoteState(current, quoteMap));
        })
        .catch(() => {
          // The selected ticker bundle keeps the main page useful even if some tape quotes time out.
        });

      const fullWatchlistTimer = window.setTimeout(() => {
        getPublicQuotesRobust(publicWatchSymbols, 48, 0)
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
    setPublicAiTools(null);

    let cancelled = false;
    setLoading(true);
    setError("");

    Promise.all([
      getAccess(token),
      getWorkspace(token),
      getWorkspaceTickerBundle(token, deferredTicker, chartInterval),
    ])
      .then(([nextAccess, nextWorkspace, nextTickerBundle]) => {
        if (cancelled) return;

        startTransition(() => {
          const nextTabs = buildTabs(nextWorkspace.tabs);
          setAccess(nextAccess);
          setWorkspace(nextWorkspace);
          setChart(nextTickerBundle.chart || null);
          setPublicChart(null);
          setFeed(nextTickerBundle.feed || null);
          setNews((current) => {
            const nextNews = nextTickerBundle.news || null;
            const currentCount = Number(current?.count ?? current?.items?.length ?? 0);
            const nextCount = Number(nextNews?.count ?? nextNews?.items?.length ?? 0);
            if (sameSymbol(current?.symbol, deferredTicker) && currentCount > 0 && nextCount <= 0) return current;
            return nextNews;
          });
          setRoom(nextTickerBundle.room || null);
          setQuote(nextTickerBundle.quote || null);
          setPushStatus(nextWorkspace.push as Record<string, unknown>);
          setMediaStatus(nextWorkspace.media as Record<string, unknown>);
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
  }, [token, deferredTicker, chartInterval, focusedTab, priorityPublicWatchKey, publicTickerTapeKey, publicWatchKey, strategicAnalysisMinute]);

  useEffect(() => {
    if (token) return;
    const chartReady =
      sameChartRequest(publicChart, deferredTicker, chartInterval) &&
      Boolean(publicChart?.ohlc?.length || publicChart?.series?.length);
    const insightReady = sameSymbol(publicInsight?.symbol, deferredTicker) && Boolean(publicInsight?.score != null || publicInsight?.rsi != null || publicInsight?.trend_bias || publicInsight?.signal);
    const newsTabOpen = (focusedTab || activeTab) === "news";
    const newsReady = sameSymbol(news?.symbol, deferredTicker) && Number(news?.count ?? news?.items?.length ?? 0) > 0;
    if (chartReady && insightReady && (!newsTabOpen || newsReady)) return;

    let cancelled = false;
    const retries = [1800, 5200, 9500];
    const timers = retries.map((delay) =>
      window.setTimeout(() => {
        getPublicMarketBundle(deferredTicker, chartInterval)
          .then((bundle) => {
            if (cancelled) return;
            const nextQuote = bundle?.quote || null;
            const nextInsight = bundle?.insight || null;
            const nextChart = bundle?.chart || null;
            const nextNews = bundle?.news || null;
            const nextPublicAiTools = bundle?.ai_tools || null;
            if (nextQuote?.symbol) {
              const normalizedQuoteSymbol = normalizeSymbol(nextQuote.symbol);
              const normalizedQuote = { ...nextQuote, symbol: normalizedQuoteSymbol };
              setPublicQuotes((current) => mergeQuoteState(current, { [normalizedQuoteSymbol]: normalizedQuote }));
              setTickerTapeQuotes((current) => mergeQuoteState(current, { [normalizedQuoteSymbol]: normalizedQuote }));
              setQuote(nextQuote);
            }
            if (sameSymbol(nextChart?.ticker || nextChart?.summary?.ticker, deferredTicker)) {
              setPublicChart(sameChartRequest(nextChart, deferredTicker, chartInterval) ? { ...nextChart, ticker: deferredTicker } : null);
            }
            if (sameSymbol(nextInsight?.symbol, deferredTicker)) {
              setPublicInsight((current) => {
                if (
                  sameSymbol(current?.symbol, deferredTicker) &&
                  (current?.score != null || current?.rsi != null || current?.trend_bias || current?.signal)
                ) {
                  return current;
                }
                return { ...nextInsight, symbol: deferredTicker };
              });
            }
            if (nextNews) {
              setNews((current) => {
                const currentCount = Number(current?.count ?? current?.items?.length ?? 0);
                const nextCount = Number(nextNews?.count ?? nextNews?.items?.length ?? 0);
                if (sameSymbol(current?.symbol, deferredTicker) && currentCount > 0 && nextCount <= 0) return current;
                return nextNews;
              });
            }
            if (nextPublicAiTools) setPublicAiTools(nextPublicAiTools);
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
    news?.symbol,
    news?.count,
    news?.items?.length,
    activeTab,
    focusedTab,
    strategicAnalysisMinute,
  ]);

  useEffect(() => {
    const newsTabOpen = (focusedTab || activeTab) === "news";
    const newsReady = sameSymbol(news?.symbol, deferredTicker) && Number(news?.count ?? news?.items?.length ?? 0) > 0;
    if (!newsTabOpen || newsReady) return;

    let cancelled = false;
    const refreshNews = () => {
      getNews(token, deferredTicker, Date.now())
        .then((payload) => {
          if (cancelled || !sameSymbol(payload?.symbol, deferredTicker)) return;
          setNews((current) => {
            const currentCount = Number(current?.count ?? current?.items?.length ?? 0);
            const nextCount = Number(payload?.count ?? payload?.items?.length ?? 0);
            if (sameSymbol(current?.symbol, deferredTicker) && currentCount > 0 && nextCount <= 0) return current;
            return payload;
          });
        })
        .catch(() => undefined);
    };

    const timers = [0, 2400, 6500, 12000, 22000].map((delay) => window.setTimeout(refreshNews, delay));
    return () => {
      cancelled = true;
      timers.forEach((timer) => window.clearTimeout(timer));
    };
  }, [token, deferredTicker, activeTab, focusedTab, news?.symbol, news?.count, news?.items?.length, strategicAnalysisMinute]);

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
      getPublicQuotesRobust(missingTapeSymbols, 32, 0)
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
      new Set([...publicTickerTapeSymbols, ...priorityPublicWatchSymbols, ...visiblePublicWatchSymbols]),
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
      .slice(0, 80);

    if (!missingSymbols.length) return;

    let cancelled = false;
    const timeout = window.setTimeout(() => {
      getPublicQuotesRobust(missingSymbols, 32, 0)
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

        getPublicQuotesRobust(chunk, 32, 0)
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
    const liveSymbols = Array.from(new Set([selectedTicker, ...publicTickerTapeSymbols, ...priorityPublicWatchSymbols])).slice(0, 48);
    if (!liveSymbols.length) return;

    let cancelled = false;
    const loadLiveQuotes = () => {
      getPublicQuotesRobust(liveSymbols, 48, 0)
        .then((nextQuotes) => {
          if (cancelled) return;
          const quoteMap = Object.fromEntries((nextQuotes?.items || []).map((item) => [normalizeSymbol(item.symbol), item]));
          if (!Object.keys(quoteMap).length) return;
          setTickerTapeQuotes((current) => mergeQuoteState(current, quoteMap));
          setPublicQuotes((current) => mergeQuoteState(current, quoteMap));
          const selectedQuote = quoteFromMap(quoteMap, selectedTicker);
          if (selectedQuote && quoteHasMarketValue(selectedQuote)) {
            setQuote({ ...selectedQuote, symbol: selectedTicker });
          }
        })
        .catch(() => undefined);
    };

    loadLiveQuotes();
    const timer = window.setInterval(loadLiveQuotes, 15000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [priorityPublicWatchKey, publicTickerTapeKey, selectedTicker]);

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

      writeStorageValue("stocknewsbr.token", payload.access_token);
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

      writeStorageValue("stocknewsbr.token", payload.access_token);
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

    removeStorageValue("stocknewsbr.token");
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

      writeStorageValue("stocknewsbr.token", token);
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
        show_price_line: chartSettings?.show_price_line ?? workspace?.layout?.chart_settings?.show_price_line ?? showPriceLine,
        show_vwap: chartSettings?.show_vwap ?? workspace?.layout?.chart_settings?.show_vwap ?? showVwap,
        show_averages: chartSettings?.show_averages ?? workspace?.layout?.chart_settings?.show_averages ?? showAverages,
        show_macd: chartSettings?.show_macd ?? workspace?.layout?.chart_settings?.show_macd ?? showMacd,
        show_rsi: chartSettings?.show_rsi ?? workspace?.layout?.chart_settings?.show_rsi ?? showRsi,
        show_supertrend: chartSettings?.show_supertrend ?? workspace?.layout?.chart_settings?.show_supertrend ?? showSupertrend,
        show_volume: chartSettings?.show_volume ?? workspace?.layout?.chart_settings?.show_volume ?? showVolume,
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
    if (key === "show_price_line") {
      setShowPriceLine(value);
    }
    if (key === "show_vwap") {
      setShowVwap(value);
    }
    if (key === "show_averages") {
      setShowAverages(value);
    }
    if (key === "show_macd") {
      setShowMacd(value);
    }
    if (key === "show_rsi") {
      setShowRsi(value);
    }
    if (key === "show_supertrend") {
      setShowSupertrend(value);
    }
    if (key === "show_volume") {
      setShowVolume(value);
    }
    void persistLayout(tabs, undefined, undefined, { [key]: value });
  }

  function selectTicker(nextTicker: string) {
    const normalized = resolveTypedSymbol(nextTicker);
    if (!normalized) return;

    aiSoundSuppressedUntilRef.current = Date.now() + 1500;
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

  async function applyTicker() {
    const typedInput = watchlistQuery.trim() || tickerInput.trim();
    const symbol = resolveTypedSymbol(typedInput || "PETR4");
    if (!symbol) return;
    let quote = resolveQuoteForSymbol(symbol, publicQuotesRef.current, tickerTapeQuotesRef.current);
    if (typedInput && !quoteHasMarketValue(quote)) {
      try {
        const nextQuotes = await getPublicQuotesRobust([symbol], 1, 0);
        const quoteMap = Object.fromEntries((nextQuotes?.items || []).map((item) => [item.symbol, item]));
        if (Object.keys(quoteMap).length) {
          setTickerTapeQuotes((current) => mergeQuoteState(current, quoteMap));
          setPublicQuotes((current) => mergeQuoteState(current, quoteMap));
          quote = resolveQuoteForSymbol(symbol, quoteMap, quoteMap) || quote;
        }
      } catch {
        // Cache-only public search can fail without blocking the rest of the workspace.
      }
    }
    setError("");
    selectTicker(symbol);
  }

  async function handleAddToActiveList() {
    const symbol = resolveTypedSymbol(watchlistQuery.trim() || tickerInput.trim() || selectedTicker);
    if (!symbol || isRemovedFutureSymbol(symbol)) return;

    let quote = resolveQuoteForSymbol(symbol, publicQuotesRef.current, tickerTapeQuotesRef.current);
    if (!quoteHasMarketValue(quote)) {
      try {
        const nextQuotes = await getPublicQuotesRobust([symbol], 1, 0);
        const quoteMap = Object.fromEntries((nextQuotes?.items || []).map((item) => [item.symbol, item]));
        if (Object.keys(quoteMap).length) {
          setTickerTapeQuotes((current) => mergeQuoteState(current, quoteMap));
          setPublicQuotes((current) => mergeQuoteState(current, quoteMap));
          quote = resolveQuoteForSymbol(symbol, quoteMap, quoteMap) || quote;
        }
      } catch {
        // Keep search cache-only; do not invent an asset when no market quote exists.
      }
    }
    const baseItem =
      PRELOADED_UNIVERSE.find((item) => item.symbol === symbol) ||
      remoteSearchItems.find((item) => item.symbol === symbol) ||
      buildSyntheticSearchCandidate(symbol, watchUniverse.map((item) => item.symbol));

    if (!quoteHasMarketValue(quote)) {
      setError(isUsLocale ? `No cached market data found for ${symbol}.` : `Sem dado de mercado em cache para ${symbol}.`);
      return;
    }
    setError("");

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
        aiSoundSuppressedUntilRef.current = Date.now() + 1500;
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

  function openGifSearch() {
    const queryText = (gifQuery.trim() || `${selectedTicker} ${symbolName(selectedTicker)} stock market gif`).replace(/\s+/g, " ");
    const query = encodeURIComponent(queryText);
    const opened = window.open(`https://tenor.com/search/${query}-gifs`, "_blank", "noopener,noreferrer");
    if (!opened) {
      setError(isUsLocale ? "The GIF window was blocked. Allow pop-ups and try again." : "A janela de GIF foi bloqueada. Libere pop-ups e tente novamente.");
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
    () => TOP_BAR_TAB_IDS
      .filter((id) => advancedMode || SIMPLE_TOP_TAB_IDS.has(id))
      .map((id) => tabsById.get(id))
      .filter(Boolean) as WorkspaceTab[],
    [advancedMode, tabsById],
  );

  useEffect(() => {
    if (focusedTab || advancedMode || SIMPLE_TOP_TAB_IDS.has(currentTab)) return;
    setActiveTab("grafico");
  }, [advancedMode, currentTab, focusedTab]);

  const activeChart = useMemo(
    () => {
      const liveChart = sameChartRequest(chart, selectedTicker, chartInterval) ? chart : null;
      const guestChart = sameChartRequest(publicChart, selectedTicker, chartInterval) ? publicChart : null;
      return liveChart || guestChart;
    },
    [chart, chartInterval, publicChart, selectedTicker],
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
      if (isRemovedFutureSymbol(item.symbol)) continue;
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
  const availableActiveWatchlist = useMemo(
    () => activeWatchlist.filter(watchlistItemHasMarketValue),
    [activeWatchlist],
  );
  const filteredActiveWatchlist = useMemo(
    () => sortWatchlistItemsAlphabetically(
      availableActiveWatchlist.filter((item) => watchCategory === "Todos" || item.category === watchCategory),
      appLocale,
    ),
    [availableActiveWatchlist, appLocale, watchCategory],
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
      remoteSearchSymbols.filter((symbol) => !isRemovedFutureSymbol(symbol)).map((symbol) => {
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
  const displayQuoteHasCoreData = quoteHasMarketValue(displayQuote) && firstPositiveFiniteNumber(displayQuote?.volume) != null;
  const currentPublicInsight = normalizeSymbol(publicInsight?.symbol || "") === selectedTicker ? publicInsight : null;
  useEffect(() => {
    if (token || quoteHasMarketValue(currentPublicQuote)) return;

    let cancelled = false;
    const retryDelays = [1800, 6000];
    const timers = retryDelays.map((delay) =>
      window.setTimeout(() => {
        getPublicQuotesRobust([deferredTicker], 1, 0)
          .then((nextQuotes) => {
            const nextQuote = (nextQuotes?.items || [])[0];
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
    () => {
      if (!displayQuoteHasCoreData) return null;
      return derivePublicScore({
        changePct: displayQuote?.change_pct ?? null,
        rsi: currentPublicInsight?.rsi ?? (currentRanking?.rsi != null ? Number(currentRanking.rsi) : null),
        trend: activeChart?.summary?.trend_bias || currentPublicInsight?.trend_bias || currentPublicInsight?.signal || currentRanking?.trend || null,
        volume: displayQuote?.volume ?? null,
      });
    },
    [
      activeChart?.summary?.trend_bias,
      currentPublicInsight?.rsi,
      currentPublicInsight?.signal,
      currentPublicInsight?.trend_bias,
      currentRanking?.rsi,
      currentRanking?.trend,
      displayQuoteHasCoreData,
      displayQuote?.change_pct,
      displayQuote?.volume,
    ],
  );
  const derivedPublicInsight = useMemo<PublicInsightPayload | null>(() => {
    if (!displayQuoteHasCoreData) return null;
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
      rel_volume: currentRanking?.rel_volume != null ? Number(currentRanking.rel_volume) : null,
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
    currentRanking?.rel_volume,
    currentRanking?.score,
    currentRanking?.trend,
    displayQuoteHasCoreData,
    displayQuote,
    selectedTicker,
  ]);
  const chartForDisplay = useMemo(() => {
    const hasLiveSeries = Boolean(activeChart?.ohlc?.length || activeChart?.series?.length);
    if (hasLiveSeries && activeChart) return activeChart;
    return buildQuoteFallbackChart(
      selectedTicker,
      chartInterval,
      displayQuote,
      derivedPublicInsight?.trend_bias || derivedPublicInsight?.signal || currentRanking?.trend || null,
    );
  }, [
    activeChart,
    chartInterval,
    currentRanking?.trend,
    derivedPublicInsight?.signal,
    derivedPublicInsight?.trend_bias,
    displayQuote,
    selectedTicker,
  ]);
  const chartMovement = useMemo(
    () => deriveChartMovement(chartForDisplay || activeChart),
    [activeChart, chartForDisplay],
  );
  const chartVolume = useMemo(
    () => deriveChartVolume(chartForDisplay || activeChart),
    [activeChart, chartForDisplay],
  );
  const effectiveAiScore = useMemo(
    () => displayQuoteHasCoreData ? usableScore(derivedPublicInsight?.score, currentRanking?.score, currentDerivedScore) : null,
    [derivedPublicInsight?.score, currentRanking?.score, currentDerivedScore, displayQuoteHasCoreData],
  );
  const priceMovementValue = firstNonZeroFiniteNumber(displayQuote?.change, chartMovement?.change) ?? (displayQuote?.change ?? null);
  const priceMovementPercent = firstNonZeroFiniteNumber(displayQuote?.change_pct, chartMovement?.changePct) ?? (displayQuote?.change_pct ?? null);
  const headerVolume = firstPositiveFiniteNumber(displayQuote?.volume, chartVolume);
  const symbolLabel = currentWatchItem?.label || symbolName(selectedTicker);
  const currentAiKey = AI_TOOL_TAB_MAP[currentTab as keyof typeof AI_TOOL_TAB_MAP];
  const currentAiRows: AiToolRow[] = useMemo(
    () => (currentAiKey ? workspace?.ai_tools?.[currentAiKey] || publicAiTools?.tools?.[currentAiKey] : undefined) || [],
    [currentAiKey, workspace?.ai_tools, publicAiTools?.tools],
  );
  const aiToolFindingCounts = useMemo(() => {
    const counts: Record<string, number> = {};
    for (const [tabId, toolKey] of Object.entries(AI_TOOL_TAB_MAP)) {
      const typedKey = toolKey as keyof WorkspaceData["ai_tools"];
      const rows = [
        ...(workspace?.ai_tools?.[typedKey] || []),
        ...(publicAiTools?.tools?.[typedKey] || []),
      ];
      const unique = new Set<string>();
      rows.forEach((row) => {
        const ticker = normalizeSymbol(String((row as any).ticker || (row as any).symbol || ""));
        if (!ticker) return;
        const candidate = { ...(row as AiToolRow), tool: toolKey, ticker };
        if (!isOperationalAiFinding(candidate)) return;
        unique.add(aiAlertSignalKey(candidate));
      });
      counts[tabId] = unique.size;
    }
    return counts;
  }, [publicAiTools?.tools, workspace?.ai_tools]);
  const aiFindingSignalKey = useMemo(() => {
    const signatures: string[] = [];
    for (const [, toolKey] of Object.entries(AI_TOOL_TAB_MAP)) {
      if (!aiToolSoundEnabled(aiToolSoundSettings, toolKey)) continue;
      const typedKey = toolKey as keyof WorkspaceData["ai_tools"];
      const rows = [
        ...(workspace?.ai_tools?.[typedKey] || []),
        ...(publicAiTools?.tools?.[typedKey] || []),
      ];
      rows.forEach((row) => {
        const ticker = normalizeSymbol(String((row as any).ticker || (row as any).symbol || ""));
        if (!ticker) return;
        const candidate = { ...(row as AiToolRow), tool: toolKey, ticker };
        if (!isOperationalAiFinding(candidate)) return;
        signatures.push(aiAlertComparableSignature(candidate));
      });
    }
    return Array.from(new Set(signatures)).sort().join("||");
  }, [aiToolSoundSettings, publicAiTools?.tools, workspace?.ai_tools]);
  useEffect(() => {
    if (aiSoundLastKeyRef.current === null) {
      aiSoundLastKeyRef.current = aiFindingSignalKey;
      return;
    }
    if (Date.now() < aiSoundSuppressedUntilRef.current) {
      aiSoundLastKeyRef.current = aiFindingSignalKey;
      return;
    }
    if (aiFindingSignalKey && aiFindingSignalKey !== aiSoundLastKeyRef.current) {
      playMoneyFindingSound();
    }
    aiSoundLastKeyRef.current = aiFindingSignalKey;
  }, [aiFindingSignalKey]);
  const newsRows = useMemo(
    () => {
      const matchedNews = dedupeNewsForTicker(
        ((activeNews?.items || []) as NewsItem[]).filter((item) => newsMatchesSelectedTicker(item, selectedTicker)),
        selectedTicker,
      );
      return matchedNews.map((item, index) => {
        const publishedAtIso = newsSourceTimestamp(item);
        const publishedTime = formatNewsClock(publishedAtIso, appLocale);
        const age = publishedTime;
        const labels = Array.isArray(item.labels) ? item.labels.filter(Boolean) : [];
        const entities = Array.isArray(item.entities)
          ? item.entities.filter(Boolean).map((entity) => appLocale === "en-US" ? localizeUiText(entity, appLocale, selectedTicker) : expandPortugueseMarketTerms(entity))
          : [];
        const impact = localizeImpactLabel(item.impact_label || item.impact || "Neutro", appLocale);
        const title = displayNewsTitle(item, selectedTicker, appLocale);
        const rawHeadline = String(item.title || "").trim();
        const headline = isUsLocale ? clampHeadline(rawHeadline || title, 150) : title;
        const cardSummary = displayNewsBody(item, selectedTicker, appLocale);
        const traderTakeaway = buildNewsTraderTakeaway(item, selectedTicker, appLocale, index);
        const whyItMatters = localizeNewsField(item, selectedTicker, appLocale, "why_it_matters", "why");
        const marketContext = localizeNewsField(item, selectedTicker, appLocale, "market_context", "context");
        const sector = localizeUiText(item.sector || "", appLocale, selectedTicker);
        const industry = localizeUiText(item.industry || "", appLocale, selectedTicker);
        const labelsForLocale = labels.map((label) => localizeUiText(label, appLocale, selectedTicker));
        const quality = isUsLocale ? (item.useful !== false ? "Useful" : "Noise") : (item.useful !== false ? "Útil" : "Ruído");
        return {
          id: item.id || `${selectedTicker}-${index}`,
          symbol: item.ticker || selectedTicker,
          headline,
          title,
          source: item.source || "Yahoo Finance",
          age,
          publishedTime,
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
      });
    },
    [activeNews?.items, selectedTicker, appLocale, isUsLocale],
  );
  const stats = useMemo(() => {
    const changeValue = displayQuoteHasCoreData ? formatSignedPercent(displayQuote?.change_pct) : "n/a";
    const aiScoreValue = effectiveAiScore != null ? Number(effectiveAiScore).toFixed(1) : "n/a";
    const scoreNumber = effectiveAiScore != null ? Number(effectiveAiScore) : Number.NaN;
    const rawChangeNumber = displayQuoteHasCoreData ? Number(displayQuote?.change_pct) : Number.NaN;
    const changeNumber = Number.isFinite(rawChangeNumber) ? rawChangeNumber : null;
    const rawBias = displayQuoteHasCoreData ? chartForDisplay?.summary?.trend_bias || currentRanking?.trend || derivedPublicInsight?.trend_bias || derivedPublicInsight?.signal || "" : "";
    const biasValue = displayQuoteHasCoreData ? biasStrengthLabel(rawBias, scoreNumber, changeNumber ?? 0, appLocale) : "n/a";
    const fallbackRsi = displayQuoteHasCoreData ? derivePublicRsi(changeNumber ?? 0, rawBias || biasValue) : null;
    const rsiRaw = firstValidRsiNumber(currentRanking?.rsi, derivedPublicInsight?.rsi, fallbackRsi);
    const rsiDescriptor = describeRsiValue(rsiRaw, appLocale);
    const rsiValue = rsiDescriptor.label;
    const changeDirection = changeNumber == null
      ? (isUsLocale ? "no confirmed change" : "sem variação real")
      : changeNumber < 0
      ? (isUsLocale ? "falling" : "queda")
      : changeNumber > 0
        ? (isUsLocale ? "rising" : "alta")
        : (isUsLocale ? "stable" : "estável");
    const quoteAverageVolume = firstPositiveFiniteNumber(
      (displayQuote as any)?.average_volume,
      (displayQuote as any)?.averageVolume,
      (displayQuote as any)?.avg_volume,
      currentWatchItem?.averageVolume,
    );
    const relVolume = firstPositiveFiniteNumber(
      currentRanking?.rel_volume,
      derivedPublicInsight?.rel_volume,
      (displayQuote as any)?.rel_volume,
      (displayQuote as any)?.rvol,
      currentWatchItem?.relVolume,
      calculateRelativeVolume(headerVolume, quoteAverageVolume),
    );
    const hasVolume = headerVolume != null && headerVolume > 0;
    const volumeValue = formatLiquidityVolume(headerVolume, relVolume, appLocale);
    const volumeContext = relVolume != null
      ? relVolume < 0.8
        ? (isUsLocale ? "below this asset's average" : "abaixo da média deste ativo")
        : relVolume > 1.2
          ? (isUsLocale ? "above this asset's average" : "acima da média deste ativo")
        : (isUsLocale ? "near this asset's average" : "perto da média deste ativo")
      : hasVolume
        ? (isUsLocale ? "real volume confirmed; RVOL depends on historical average" : "volume real confirmado; RVOL depende da média histórica")
        : (isUsLocale ? "no reliable volume in the current provider payload" : "sem volume confiável no payload atual");
    const scoreHint = Number.isFinite(scoreNumber)
      ? scoreNumber >= 7
        ? (isUsLocale ? `${aiScoreValue} favors strength/buy only with confirmation.` : `${aiScoreValue} favorece força/compra apenas com confirmação.`)
        : scoreNumber <= 5.5
          ? (isUsLocale ? `${aiScoreValue} indicates weak/sell bias; avoid long without confirmation.` : `${aiScoreValue} indicando baixa/venda; evite compra sem confirmação.`)
          : (isUsLocale ? `${aiScoreValue} is moderate: wait for price/volume confirmation.` : `${aiScoreValue} é moderado: aguarde confirmação de preço/volume.`)
      : (isUsLocale ? "No Master Score confirmed for this asset yet." : "Sem Score Mestre confirmado para este ativo ainda.");
    const rsiHint = rsiDescriptor.hint;

    return [
      {
        label: isUsLocale ? "Price" : "Preço",
        value: formatLocalePrice(displayQuote?.price, appLocale),
        hint: isUsLocale ? "Current quote" : "Cotação atual",
        tone: "neutral",
      },
      {
        label: isUsLocale ? "Change" : "Variação",
        value: changeValue,
        hint: displayQuoteHasCoreData
          ? (isUsLocale ? `${changeValue} indicates ${changeDirection} now.` : `${changeValue} indicando ${changeDirection} do ativo.`)
          : (isUsLocale ? "No confirmed real change in the current payload." : "Sem variação real confirmada no payload atual."),
        tone: changeNumber != null && changeNumber > 0 ? "up" : changeNumber != null && changeNumber < 0 ? "down" : "neutral",
      },
      {
        label: "Volume",
        value: volumeValue,
        hint: isUsLocale ? `${volumeValue}; ${volumeContext}.` : `${volumeValue}, ${volumeContext}.`,
        tone: relVolume != null && relVolume > 1.2 ? "up" : relVolume != null && relVolume < 0.8 ? "down" : "neutral",
      },
      {
        label: isUsLocale ? "Master Score" : "Score Mestre",
        value: aiScoreValue,
        hint: scoreHint,
        tone: Number.isFinite(scoreNumber) && scoreNumber >= 7 ? "up" : Number.isFinite(scoreNumber) && scoreNumber <= 5.5 ? "down" : "neutral",
      },
      {
        label: "RSI",
        value: rsiValue,
        hint: rsiHint,
        tone: rsiDescriptor.tone,
      },
      {
        label: "Bias",
        value: biasValue,
        hint: displayQuoteHasCoreData
          ? describeBiasValue(biasValue, appLocale)
          : (isUsLocale ? "No confirmed Bias in the current payload." : "Sem Bias confirmado no payload atual."),
        tone: displayQuoteHasCoreData ? biasTone(biasValue) : "neutral",
      },
    ];
  }, [
    displayQuote?.price,
    displayQuote?.change_pct,
    headerVolume,
    effectiveAiScore,
    currentRanking?.rsi,
    currentRanking?.rel_volume,
    currentRanking?.trend,
    currentWatchItem?.averageVolume,
    currentWatchItem?.relVolume,
    chartForDisplay?.summary?.trend_bias,
    derivedPublicInsight?.score,
    derivedPublicInsight?.rel_volume,
    derivedPublicInsight?.rsi,
    derivedPublicInsight?.trend_bias,
    derivedPublicInsight?.signal,
    isUsLocale,
    appLocale,
    selectedTicker,
    displayQuote,
    displayQuoteHasCoreData,
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
        volume: firstPositiveFiniteNumber(row?.volume, existing.volume, watchItem?.volume, quote?.volume),
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
  ]);
  const toolCandidates = useMemo(
    () =>
      [...toolCandidatesSource]
        .filter((row) => isOperationalAiFinding(row as Partial<AiToolRow>) && scoreToolCandidateForTab(currentTab, row) > -999)
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
          rsi: firstValidRsiNumber(currentRanking?.rsi),
          volume: displayQuote?.volume ?? null,
          timestamp: null,
        };
        return { ...fallback, id: `${fallback.symbol}-${index}` };
      }),
    [toolCandidates, selectedTicker, symbolLabel, currentRanking?.score, currentRanking?.trend, currentRanking?.rsi, activeChart?.summary?.trend_bias, displayQuote?.price, displayQuote?.change_pct, displayQuote?.volume],
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
        const rsi = firstValidRsiNumber(row.rsi, symbol === selectedTicker ? derivedPublicInsight?.rsi : null, derivePublicRsi(changePct, trend));
        const resolvedVolume = firstPositiveFiniteNumber(row.volume, (row as any).volume_24h, quote?.volume);
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
          locale: appLocale,
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
        const rowDetectedAt = resolveAiFindingTimestamp(row) ?? undefined;
        const rowUpdatedAt = normalizeAlertTimestamp(row.updated_at) || rowDetectedAt;
        const rowLastSeenAt = normalizeAlertTimestamp(row.last_seen_at) || rowUpdatedAt || rowDetectedAt;
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
          detected_at: rowDetectedAt ?? undefined,
          last_seen_at: rowLastSeenAt ?? undefined,
        };
      });
      return [...backendRows]
        .filter(isOperationalAiFinding)
        .sort((a, b) => {
          const bTime = Date.parse(resolveAiAlertTimestamp(b) || "");
          const aTime = Date.parse(resolveAiAlertTimestamp(a) || "");
          if (Number.isFinite(bTime) && Number.isFinite(aTime) && bTime !== aTime) return bTime - aTime;
          return Number(b.score || 0) - Number(a.score || 0);
        })
        .slice(0, 20);
    }

    const sourceCandidates = expandedToolCandidates
      .map((item) => {
        const normalizedItemSymbol = normalizeSymbol(item.symbol);
        const quote = resolveQuoteForSymbol(normalizedItemSymbol, publicQuotes, tickerTapeQuotes);
        const watchItem = watchUniverse.find((candidate) => candidate.symbol === normalizedItemSymbol);
        const changePct = quote?.change_pct ?? watchItem?.changePct ?? null;
        const trend = item.trend || (normalizedItemSymbol === selectedTicker ? derivedPublicInsight?.trend_bias || derivedPublicInsight?.signal : null) || chartForDisplay?.summary?.trend_bias || "monitorando";
        const rsi = firstValidRsiNumber(item.rsi, normalizedItemSymbol === selectedTicker ? derivedPublicInsight?.rsi : null, derivePublicRsi(changePct, trend));
        const resolvedVolume = firstPositiveFiniteNumber(quote?.volume, item.volume, watchItem?.volume);
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
      .filter((item) => isOperationalAiFinding(item as Partial<AiToolRow>) && scoreToolCandidateForTab(currentTab, item) > -999)
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
        locale: appLocale,
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
        market_data_updated_at: normalizeAlertTimestamp(item.quote?.market_data_updated_at) ?? undefined,
        quote_time: normalizeAlertTimestamp(item.quote?.quote_time) ?? undefined,
        provider_timestamp: normalizeAlertTimestamp(item.quote?.provider_timestamp) ?? undefined,
        updated_at: normalizeAlertTimestamp(item.quote?.market_data_updated_at) ?? normalizeAlertTimestamp(item.timestamp) ?? undefined,
        detected_at: normalizeAlertTimestamp(item.quote?.market_data_updated_at) ?? normalizeAlertTimestamp(item.timestamp) ?? undefined,
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
    appLocale,
  ]);
  const [aiAlertResetKey, setAiAlertResetKey] = useState(() => getAlertResetKey());
  const [aiAlertHistory, setAiAlertHistory] = useState<Record<string, { resetKey: string; rows: AiToolRow[]; source?: "real" }>>({});

  useEffect(() => {
    const timer = window.setInterval(() => setAiAlertResetKey(getAlertResetKey()), 60_000);
    return () => window.clearInterval(timer);
  }, []);

  useEffect(() => {
    const timer = window.setInterval(() => setStrategicAnalysisMinute(currentFiveMinuteBucket()), 60_000);
    return () => window.clearInterval(timer);
  }, []);

  useEffect(() => {
    try {
      const raw = readStorageValue(AI_ALERT_HISTORY_STORAGE_KEY);
      if (!raw) return;
      const parsed = JSON.parse(raw) as { resetKey?: string; tabs?: Record<string, { resetKey: string; rows: AiToolRow[]; source?: "real" }> };
      setAiAlertHistory(parsed.resetKey === aiAlertResetKey && parsed.tabs ? parsed.tabs : {});
    } catch {
      setAiAlertHistory({});
    }
  }, [aiAlertResetKey]);

  useEffect(() => {
    try {
      writeStorageValue(
        AI_ALERT_HISTORY_STORAGE_KEY,
        JSON.stringify({ resetKey: aiAlertResetKey, tabs: aiAlertHistory }),
      );
    } catch {
      // localStorage can be blocked; in-memory history still works for the session.
    }
  }, [aiAlertHistory, aiAlertResetKey]);

  const realAiVisibleRows = useMemo(() => {
    if (!currentAiKey || !currentAiRows.length || !visibleAiRows.length) return [];
    const realKeys = new Set(
      currentAiRows
        .map((row) => ({
          ...(row as AiToolRow),
          tool: currentAiKey,
          ticker: normalizeSymbol(String((row as any).ticker || (row as any).symbol || "")),
        }))
        .filter(isOperationalAiFinding)
        .map((row) => aiAlertSignalKey(row)),
    );
    return visibleAiRows.filter((row) => realKeys.has(aiAlertSignalKey(row)));
  }, [currentAiKey, currentAiRows, visibleAiRows]);

  useEffect(() => {
    if (!currentAiKey || !realAiVisibleRows.length) return;
    const incoming = realAiVisibleRows.map((row) => withAlertTimestamp(row));
    if (!incoming.length) return;

    setAiAlertHistory((current) => {
      const currentBucket = current[currentTab];
      const retained = currentBucket?.resetKey === aiAlertResetKey && currentBucket.source === "real" ? currentBucket.rows : [];
      const byKey = new Map<string, AiToolRow>();

      for (const row of retained) {
        byKey.set(aiAlertSignalKey(row), row);
      }

      for (const row of incoming) {
        const key = aiAlertSignalKey(row);
        const existing = byKey.get(key);
        if (existing && aiAlertComparableSignature(existing) === aiAlertComparableSignature(row)) {
          if (isNewerAiAlert(row, existing)) {
            byKey.set(key, {
              ...existing,
              ...row,
              updated_at: row.updated_at || row.detected_at || existing.updated_at,
              detected_at: row.detected_at || row.updated_at || existing.detected_at,
              last_seen_at: row.last_seen_at || row.updated_at || row.detected_at || existing.last_seen_at,
            });
          } else {
            byKey.set(key, existing);
          }
          continue;
        }
        byKey.set(key, {
          ...(existing || {}),
          ...row,
          updated_at: isNewerAiAlert(row, existing) ? row.updated_at : existing?.updated_at || row.updated_at,
          detected_at: isNewerAiAlert(row, existing) ? row.detected_at || row.updated_at : existing?.detected_at || row.detected_at || row.updated_at,
          last_seen_at: row.last_seen_at || row.updated_at || existing?.last_seen_at,
        });
      }

      const rows = Array.from(byKey.values())
        .sort((a, b) => Date.parse(resolveAiAlertTimestamp(b) || "") - Date.parse(resolveAiAlertTimestamp(a) || ""))
        .slice(0, 20);

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
          source: "real",
          rows,
        },
      };
    });
  }, [aiAlertResetKey, currentAiKey, currentTab, realAiVisibleRows]);

  const visibleAiRowsWithTimestamps = useMemo(
    () => visibleAiRows.map((row) => withAlertTimestamp(row)),
    [visibleAiRows],
  );
  const currentTabAlertRows = (
    currentAiRows.length &&
    aiAlertHistory[currentTab]?.resetKey === aiAlertResetKey &&
    aiAlertHistory[currentTab]?.source === "real" &&
    aiAlertHistory[currentTab]?.rows.length
      ? aiAlertHistory[currentTab].rows
      : visibleAiRowsWithTimestamps
  ).filter(isOperationalAiFinding);
  const showSymbolHeader = currentTab === "grafico";
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
  const priceMovementLabel = marketSessionLabel(selectedTicker, appLocale);
  const hasPriceMovement = priceMovementValue != null || priceMovementPercent != null;
  const essentialDecisionCards = useMemo(() => {
    const rawScoreValue = effectiveAiScore != null && Number.isFinite(Number(effectiveAiScore))
      ? Number(effectiveAiScore)
      : numericRankingScore != null
        ? numericRankingScore / 10
        : null;
    const chartTicker = normalizeSymbol(String(chartForDisplay?.summary?.ticker || chartForDisplay?.ticker || ""));
    const chartMatchesTicker = !chartTicker || chartTicker === selectedTicker;
    const hasCoreData = Boolean(chartMatchesTicker && hasRenderedChartData && displayQuote?.price != null && headerVolume != null && headerVolume > 0);
    const scoreValue = hasCoreData ? rawScoreValue : null;
    const scoreTone: DecisionTone = scoreValue == null ? "neutral" : scoreValue >= 6 ? "bullish" : scoreValue <= 4.8 ? "bearish" : "neutral";
    const decisionChart = chartMatchesTicker ? chartForDisplay : null;
    const marker = latestChartMarker(decisionChart);
    const rawMarkerTone = decisionToneFromText(chartActionLabel(marker, appLocale), marker?.type, marker?.label, marker?.action_label);
    const markerTone = rawMarkerTone === "exit" && scoreTone === "bullish" ? "watch" : rawMarkerTone;
    const trendTone = decisionToneFromText(trendText, decisionChart?.summary?.trend_bias, derivedPublicInsight?.trend_bias, derivedPublicInsight?.signal);
    const sameTicker = (row: AiToolRow) => normalizeSymbol(row.ticker || "") === selectedTicker;
    const toolRows = (keys: Array<keyof WorkspaceData["ai_tools"]>) =>
      keys.flatMap((key) => [
        ...(workspace?.ai_tools?.[key] || []),
        ...(publicAiTools?.tools?.[key] || []),
      ]).filter(sameTicker);
    const flowCard = resolveFlowCard(toolRows(["institutional_flow", "smart_money", "accumulation"]), appLocale);
    const flowTone = flowCard.tone;
    const baseTone = trendTone !== "neutral"
      ? trendTone
      : flowTone !== "neutral"
        ? flowTone
        : scoreTone;
    const markerConflictsBase = markerTone !== "neutral" && markerTone !== "exit" && baseTone !== "neutral" && tonesConflict(markerTone, baseTone);
    const directionTone = !hasCoreData
      ? "neutral"
      : markerTone !== "neutral" && markerTone !== "exit" && !markerConflictsBase
        ? markerTone
        : baseTone !== "neutral"
          ? baseTone
          : markerTone === "exit"
            ? "exit"
            : scoreTone;
    const structuralConflict = markerTone !== "exit" && (tonesConflict(trendTone, flowTone) || tonesConflict(directionTone, flowTone));
    const scoreConflict = markerTone !== "exit" && scoreTone !== "neutral" && directionTone !== "neutral" && directionTone !== "exit" && tonesConflict(directionTone, scoreTone);
    const conflict = structuralConflict || scoreConflict;
    const tradeTone = conflict ? "watch" : directionTone === "exit" ? "exit" : directionTone;
    const scoreCardTone: DecisionTone = scoreValue == null ? "neutral" : scoreValue >= 7 ? "bullish" : scoreValue <= 5.5 ? "bearish" : "watch";
    const riskCard = resolveRiskCard(scoreValue, hasCoreData, conflict, appLocale, currentRanking?.rsi ?? derivedPublicInsight?.rsi, rawScoreValue);
    const regimeValue = humanizeMachineLabel(decisionChart?.summary?.trend_bias || trendText || derivedPublicInsight?.trend_bias || derivedPublicInsight?.signal || "", appLocale);
    return [
      {
        label: isUsLocale ? "Master Score" : "Score Mestre",
        value: scoreValue != null ? scoreValue.toFixed(1) : "n/a",
        tone: scoreCardTone,
      },
      {
        label: isUsLocale ? "Likely Direction" : "Direção provável",
        value: decisionDirectionLabel(directionTone, appLocale),
        tone: directionTone === "exit" ? "watch" : directionTone,
      },
      {
        label: isUsLocale ? "Suggested Trade" : "Trade sugerido",
        value: decisionTradeLabel(directionTone, hasCoreData, appLocale),
        tone: tradeTone,
      },
      {
        label: isUsLocale ? "Regime" : "Regime",
        value: regimeValue || (isUsLocale ? "No read" : "Sem leitura"),
        tone: trendTone === "exit" ? "neutral" : trendTone,
      },
      flowCard,
      {
        label: isUsLocale ? "Liquidity Target" : "Liquidez alvo",
        value: resolveLiquidityTarget(decisionChart, displayQuote?.price, directionTone, appLocale),
        tone: directionTone === "exit" ? "watch" : directionTone,
      },
      riskCard,
    ];
  }, [
    appLocale,
    chartForDisplay,
    currentRanking?.rsi,
    derivedPublicInsight?.rsi,
    derivedPublicInsight?.signal,
    derivedPublicInsight?.trend_bias,
    displayQuote?.price,
    effectiveAiScore,
    headerVolume,
    hasRenderedChartData,
    isUsLocale,
    numericRankingScore,
    publicAiTools?.tools,
    selectedTicker,
    trendText,
    workspace?.ai_tools,
  ]);
  const strategicConclusion = useMemo(() => {
    const hasCoreData = Boolean(hasRenderedChartData && displayQuote?.price != null && headerVolume != null && headerVolume > 0);
    const scoreValue = hasCoreData && effectiveAiScore != null && Number.isFinite(Number(effectiveAiScore))
      ? Number(effectiveAiScore)
      : hasCoreData && numericRankingScore != null
        ? numericRankingScore / 10
        : null;
    const fallbackRsi = quoteHasMarketValue(displayQuote)
      ? derivePublicRsi(displayQuote?.change_pct ?? 0, chartForDisplay?.summary?.trend_bias || currentRanking?.trend || derivedPublicInsight?.trend_bias || derivedPublicInsight?.signal || "")
      : null;
    const rsiNumber = firstValidRsiNumber(currentRanking?.rsi, derivedPublicInsight?.rsi, fallbackRsi);
    const averageVolume = firstPositiveFiniteNumber(
      (displayQuote as any)?.average_volume,
      (displayQuote as any)?.averageVolume,
      (displayQuote as any)?.avg_volume,
      currentWatchItem?.averageVolume,
    );
    const resolvedVolume = firstPositiveFiniteNumber(headerVolume, displayQuote?.volume);
    const relVolume = firstPositiveFiniteNumber(
      currentRanking?.rel_volume,
      derivedPublicInsight?.rel_volume,
      (displayQuote as any)?.rel_volume,
      (displayQuote as any)?.rvol,
      currentWatchItem?.relVolume,
      calculateRelativeVolume(resolvedVolume, averageVolume),
    );
    const [scoreCard, directionCard, tradeCard, regimeCard, flowCard, liquidityCard, riskCard] = essentialDecisionCards;
    return buildStrategicConclusion({
      locale: appLocale,
      minuteTick: strategicAnalysisMinute,
      symbol: selectedTicker,
      score: scoreValue,
      direction: directionCard?.value || "",
      trade: tradeCard?.value || "",
      regime: regimeCard?.value || "",
      flow: flowCard?.value || "",
      liquidity: liquidityCard?.value || "",
      risk: riskCard?.value || "",
      rsi: rsiNumber,
      volume: resolvedVolume,
      averageVolume,
      relVolume,
      hasCoreData: Boolean(hasCoreData && resolvedVolume != null && resolvedVolume > 0 && scoreCard?.value !== "n/a"),
    });
  }, [
    appLocale,
    currentRanking?.rel_volume,
    currentRanking?.rsi,
    chartForDisplay?.summary?.trend_bias,
    currentRanking?.trend,
    currentWatchItem?.averageVolume,
    currentWatchItem?.relVolume,
    derivedPublicInsight?.rel_volume,
    derivedPublicInsight?.rsi,
    displayQuote,
    displayQuote?.price,
    displayQuote?.volume,
    effectiveAiScore,
    essentialDecisionCards,
    hasRenderedChartData,
    headerVolume,
    numericRankingScore,
    selectedTicker,
    strategicAnalysisMinute,
  ]);
  const strategicConclusionSections = useMemo(
    () => strategicSectionsForRender(strategicConclusion, appLocale, selectedTicker),
    [appLocale, selectedTicker, strategicConclusion],
  );
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
    setAdvancedMode(true);
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
                  <MarketAnimalIcon tone="bullish" />
                  <span>{isUsLocale ? "Bullish" : "Touro"}</span>
                </button>
                <button
                  className={cx("snbr-sentiment-pill", "bearish", postSentiment === "bearish" && "active")}
                  onClick={() => setPostSentiment("bearish")}
                  aria-pressed={postSentiment === "bearish"}
                  aria-label={isUsLocale ? `Post as bearish for ${selectedTicker}` : `Publicar como urso para ${selectedTicker}`}
                  type="button"
                >
                  <MarketAnimalIcon tone="bearish" />
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
                      <button className="snbr-button subtle" onClick={openGifSearch} type="button">
                        {isUsLocale ? "Open GIFs" : "Abrir GIFs"}
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
                      <MarketAnimalIcon tone="bullish" />
                      <span>{isUsLocale ? "Bullish" : "Touro"}</span>
                    </button>
                    <button
                      className={cx("snbr-sentiment-chip", "bearish", postSentiment === "bearish" && "active")}
                      onClick={() => setPostSentiment("bearish")}
                      type="button"
                      aria-pressed={postSentiment === "bearish"}
                    >
                      <MarketAnimalIcon tone="bearish" />
                      <span>{isUsLocale ? "Bearish" : "Urso"}</span>
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
                <MarketAnimalIcon tone="bullish" />
                <span>{isUsLocale ? "Bullish" : "Touro"}</span>
              </button>
              <button
                className={cx("snbr-sentiment-pill", "bearish", postSentiment === "bearish" && "active")}
                onClick={() => setPostSentiment("bearish")}
                aria-pressed={postSentiment === "bearish"}
                aria-label={isUsLocale ? `Post as bearish for ${selectedTicker}` : `Publicar como urso para ${selectedTicker}`}
                type="button"
              >
                <MarketAnimalIcon tone="bearish" />
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
                    <button className="snbr-button subtle" onClick={openGifSearch} type="button">
                      {isUsLocale ? "Open GIFs" : "Abrir GIFs"}
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
                      <MarketAnimalIcon tone="bullish" />
                      <span>{isUsLocale ? "Bullish" : "Touro"}</span>
                    </button>
                    <button
                      className={cx("snbr-sentiment-chip", "bearish", postSentiment === "bearish" && "active")}
                      onClick={() => setPostSentiment("bearish")}
                      type="button"
                      aria-pressed={postSentiment === "bearish"}
                    >
                      <MarketAnimalIcon tone="bearish" />
                      <span>{isUsLocale ? "Bearish" : "Urso"}</span>
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
                  <SentimentLabel sentiment={post.sentiment} locale={appLocale} />
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
                <SentimentLabel sentiment={post.sentiment} locale={appLocale} />
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
            priceText: formatPrice(item.price, appLocale),
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
      const currentAiSoundEnabled = aiToolSoundEnabled(aiToolSoundSettings, currentAiKey);
      const aiSoundLocked = proModeLocked && currentAiKey !== "master_score";
      return (
        <section id={`panel-${currentTab}`} className="snbr-tool-shell">
          <div className="snbr-tool-head">
            <div>
              <h3>{copy.title}</h3>
              <p>{copy.description}</p>
              {copy.explanation ? <p>{copy.explanation}</p> : null}
              {lens ? <p className="snbr-tool-lens">{lens}</p> : null}
            </div>
            <div className="snbr-tool-actions">
              <button className="snbr-button secondary snbr-popout-button" onClick={() => openPopout(currentTab)} type="button" aria-label={isUsLocale ? `Open ${copy.title} in another screen` : `Abrir ${copy.title} em outra tela`}>
                {isUsLocale ? "Detach" : "Liberar Tela"}
              </button>
              <div className="snbr-tool-sound-row">
                <span>{isUsLocale ? "Sound Alert" : "Alerta de Som"}</span>
                <button
                  className={cx("snbr-switch", currentAiSoundEnabled && "active")}
                  disabled={aiSoundLocked}
                  onClick={() => {
                    if (aiSoundLocked) return;
                    setAiToolSoundSettings((current) => ({ ...defaultAiToolSoundSettings(), ...current, [currentAiKey]: !aiToolSoundEnabled(current, currentAiKey) }));
                  }}
                  type="button"
                  aria-pressed={currentAiSoundEnabled}
                  title={aiSoundLocked ? (isUsLocale ? "Available in Pro for this AI." : "Disponível no Pro para esta IA.") : undefined}
                >
                  <span />
                </button>
              </div>
            </div>
          </div>

          {currentTabAlertRows.length ? (
            <div className="snbr-tool-stack">
              <p className="snbr-tool-lens">
                {isUsLocale
                  ? `Visible lens findings: ${currentTabAlertRows.length}/20. A new finding appears first and the oldest visible row leaves the screen.`
                  : `Achados visíveis da lente: ${currentTabAlertRows.length}/20. Um novo achado aparece primeiro e o último visível sai da tela.`}
              </p>
              {currentTabAlertRows.map((item, index) => {
                const watchItem = watchUniverse.find((candidate) => candidate.symbol === item.ticker);
                const quote = resolveQuoteForSymbol(item.ticker, publicQuotes, tickerTapeQuotes);
                const tone = aiSignalTone(item.signal);
                const resolvedChangePct = item.change_pct ?? watchItem?.changePct ?? null;
                const resolvedPrice = firstFiniteNumber(item.price, watchItem?.price, quote?.price);
                const resolvedVolume = firstPositiveFiniteNumber(item.volume, watchItem?.volume, quote?.volume);
                const resolvedRsi = firstValidRsiNumber(item.rsi, derivePublicRsi(resolvedChangePct, item.state || item.signal || watchItem?.trend || null));
                const resolvedRvol = item.rel_volume ?? deriveRelativeVolume(resolvedVolume);
                const resolvedAdx = item.adx ?? deriveAdx(resolvedChangePct, resolvedRsi, item.state || item.signal || watchItem?.trend || null);
                const resolvedAtrPct = item.atr_pct ?? deriveAtrPct(resolvedChangePct, resolvedRsi, resolvedVolume);
                const metricEntries = Object.entries(item.metrics || {})
                  .filter(([, value]) => value !== null && value !== undefined && value !== "")
                  .slice(0, 4);
                const mainReadText = isUsLocale
                  ? cleanEnglishDecisionText(item.ai_comment, buildAiToolTextFallback(item, appLocale, item.ticker, "main"), item.ticker)
                  : localizeUiText(item.ai_comment || buildAiToolTextFallback(item, appLocale, item.ticker, "main"), appLocale, item.ticker);
                const triggerText = isUsLocale
                  ? cleanEnglishDecisionText(item.trigger, buildAiToolTextFallback(item, appLocale, item.ticker, "trigger"), item.ticker)
                  : localizeUiText(item.trigger || buildAiToolTextFallback(item, appLocale, item.ticker, "trigger"), appLocale, item.ticker);
                const invalidationFallback = buildAiToolTextFallback(item, appLocale, item.ticker, "invalidation");
                const invalidationSource = invalidationConflictsWithCurrentScore(item.invalidation, item.score)
                  ? invalidationFallback
                  : (item.invalidation || invalidationFallback);
                const invalidationText = isUsLocale && looksPortuguese(localizeInvalidationText(invalidationSource, appLocale, item.ticker))
                  ? localizeInvalidationText(invalidationFallback, appLocale, item.ticker)
                  : localizeInvalidationText(invalidationSource, appLocale, item.ticker);
                const mainReadLines = formatAiMainReadText(mainReadText, appLocale);

                return (
                  <div key={`${currentTab}-${item.ticker}-${index}`} className="snbr-tool-row">
                    <section className="snbr-plain-panel">
                      <div className="snbr-section-head compact">
                        <div>
                          <h3>{isUsLocale ? "Asset Panel" : "Painel do ativo"}</h3>
                          <p>{isUsLocale ? "Daily alert from the current lens, with detection time and execution criteria." : "Alerta diário da lente atual, com horário detectado e critérios de execução."}</p>
                        </div>
                        <span className="snbr-chip">{isUsLocale ? "Found" : "Encontrado"}: {formatAiUpdatedAt(resolveAiFindingTimestamp(item), appLocale)}</span>
                      </div>
                      <button className="snbr-asset-box snbr-asset-box-large" onClick={() => selectTicker(item.ticker)} type="button">
                        <div className="snbr-asset-box-head">
                          <strong>{item.ticker}</strong>
                          <span className={cx("snbr-side-badge", scoreClass(item.score))}>
                            {currentTab === "heat-map" ? <i className={cx("snbr-score-dot", tone)} aria-hidden="true" /> : null}
                            Score {item.score.toFixed(1)}
                          </span>
                        </div>
                        <span>{item.name || symbolName(item.ticker)}</span>
                        <div className="snbr-asset-box-stats">
                          <div>
                            <small>{isUsLocale ? "Price:" : "Preço:"}</small>
                            <strong>{formatPrice(resolvedPrice, appLocale)}</strong>
                          </div>
                          <div>
                            <small>{isUsLocale ? "Change:" : "Variação:"}</small>
                            <strong>{resolvedChangePct != null ? formatSignedPercent(resolvedChangePct) : "n/a"}</strong>
                          </div>
                          <div>
                            <small>Volume:</small>
                            <strong>{formatLiquidityVolume(resolvedVolume, resolvedRvol, appLocale)}</strong>
                          </div>
                          <div>
                            <small>RVOL:</small>
                            <strong>{resolvedRvol != null && resolvedRvol > 0 ? resolvedRvol.toFixed(2) : (isUsLocale ? "no read" : "sem leitura")}</strong>
                          </div>
                          <div>
                            <small>{isUsLocale ? "Confidence:" : "Confiança:"}</small>
                            <strong>{item.confidence}%</strong>
                          </div>
                          <div>
                            <small>{isUsLocale ? "State:" : "Estado:"}</small>
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
                            <span>{isUsLocale ? "Main Read" : "Leitura Principal"}</span>
                            <strong>{humanizeMachineLabel(item.state, appLocale)}</strong>
                            {mainReadLines.map((line) => {
                              const [label, ...rest] = line.split(":");
                              const hasLabel = rest.length > 0 && /^(composition|positive points|risks|final decision|composição|pontos positivos|riscos|decisão final)$/i.test(label.trim());
                              return (
                                <p key={`${item.ticker}-${line}`} className={hasLabel ? "snbr-tool-read-line labeled" : "snbr-tool-read-line"}>
                                  {hasLabel ? <><strong>{label.trim()}:</strong> {rest.join(":").trim()}</> : line}
                                </p>
                              );
                            })}
                          </div>
                        <div className="snbr-tool-reading-card">
                          <span>{isUsLocale ? "Trigger" : "Gatilho"}</span>
                          <strong>{triggerText}</strong>
                        </div>
                        <div className="snbr-tool-reading-card">
                          <span>{isUsLocale ? "Invalidation If" : "Invalidação Se"}</span>
                          <strong>{invalidationText}</strong>
                        </div>
                          <div className="snbr-tool-reading-card">
                            <span>{isUsLocale ? "Context" : "Contexto"}</span>
                            <strong className={cx("snbr-tone-tag", tone)}>
                              {tone === "bullish" ? (
                                <>
                                  <MarketAnimalIcon tone="bullish" />
                                  <span>{isUsLocale ? "Buy" : "Compra"}</span>
                                </>
                              ) : tone === "bearish" ? (
                                <>
                                  <MarketAnimalIcon tone="bearish" />
                                  <span>{isUsLocale ? "Sell" : "Venda"}</span>
                                </>
                              ) : (isUsLocale ? "Watching" : "Monitorando")}
                            </strong>
                          <p>RSI {resolvedRsi != null ? resolvedRsi.toFixed(1) : (isUsLocale ? "no read" : "sem leitura")} • RVOL {resolvedRvol != null && resolvedRvol > 0 ? resolvedRvol.toFixed(2) : (isUsLocale ? "no read" : "sem leitura")} • ADX {resolvedAdx != null ? resolvedAdx.toFixed(1) : (isUsLocale ? "no read" : "sem leitura")} • ATR {resolvedAtrPct != null ? resolvedAtrPct.toFixed(1) : (isUsLocale ? "no read" : "sem leitura")}%</p>
                          </div>
                          {metricEntries.length ? (
                            <div className="snbr-tool-reading-card snbr-tool-metrics-card">
                              <span>{isUsLocale ? "Lens Metrics" : "Métricas da Lente"}</span>
                              <div className="snbr-tool-metric-list">
                                {metricEntries.map(([key, value]) => (
                                  <p key={`${item.ticker}-${key}`}>
                                    <small>{formatToolMetricLabel(key, appLocale)}:</small>
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
              <strong>{isUsLocale ? "No operational read with confirmed price and volume." : "Sem leitura operacional com preço e volume confirmados."}</strong>
              <p>{isUsLocale ? "Score-only or zero-volume rows are kept as context, but they are not counted as findings." : "Linhas score_only ou com volume zerado ficam apenas como contexto; não contam como achado."}</p>
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
                  const resolvedVolume = firstPositiveFiniteNumber(item.volume, watchItem?.volume, quote?.volume);
                  const resolvedRsi = firstValidRsiNumber(item.rsi, derivePublicRsi(resolvedChangePct, item.trend || watchItem?.trend || null));
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
                    <span className="snbr-chip">{isUsLocale ? "Found" : "Encontrado"}: {formatAiUpdatedAt(normalizeAlertTimestamp(item.timestamp), appLocale)}</span>
                  </div>
                  <button className="snbr-asset-box snbr-asset-box-large" onClick={() => selectTicker(item.symbol)} type="button">
                    <div className="snbr-asset-box-head">
                      <strong>{item.symbol}</strong>
                      <span className={cx("snbr-side-badge", scoreClass(item.score))}>
                        {currentTab === "heat-map" ? <i className={cx("snbr-score-dot", tone)} aria-hidden="true" /> : null}
                        Score {item.score != null ? item.score.toFixed(1) : "n/a"}
                      </span>
                    </div>
                    <span>{item.label}</span>
                    <div className="snbr-asset-box-stats">
                      <div>
                        <small>{isUsLocale ? "Price:" : "Preço:"}</small>
                        <strong>{formatPrice(resolvedPrice, appLocale)}</strong>
                      </div>
                      <div>
                        <small>{isUsLocale ? "Change:" : "Variação:"}</small>
                        <strong>{resolvedChangePct != null ? formatSignedPercent(resolvedChangePct) : "n/a"}</strong>
                      </div>
                      <div>
                        <small>Volume:</small>
                        <strong>{formatLiquidityVolume(resolvedVolume, resolvedRvol, appLocale)}</strong>
                      </div>
                      <div>
                        <small>{isUsLocale ? "Master Score:" : "Score Mestre:"}</small>
                        <strong>{item.score != null ? item.score.toFixed(1) : "n/a"}</strong>
                      </div>
                      <div>
                        <small>RSI:</small>
                        <strong>{resolvedRsi != null ? resolvedRsi.toFixed(0) : "n/a"}</strong>
                      </div>
                      <div>
                        <small>Bias:</small>
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
                      <span>{isUsLocale ? "Main Read" : "Leitura Principal"}</span>
                      <strong>{isUsLocale ? `${item.symbol} in ${localizeUiText(item.trend || "watching", appLocale, item.symbol)}` : `${item.symbol} em ${item.trend || "monitorando"}`}</strong>
                    </div>
                      <div className="snbr-tool-reading-card">
                        <span>{isUsLocale ? "Current score" : "Score atual"}</span>
                        <strong>{item.score != null ? item.score.toFixed(1) : "n/a"}</strong>
                      </div>
                    <div className="snbr-tool-reading-card">
                      <span>{isUsLocale ? "Liquidity / volume" : "Liquidez / volume"}</span>
                        <strong>{formatLiquidityVolume(resolvedVolume, resolvedRvol, appLocale)}</strong>
                    </div>
                      <div className="snbr-tool-reading-card">
                        <span>{isUsLocale ? "Context" : "Contexto"}</span>
                        <strong className={cx("snbr-tone-tag", tone)}>
                          {tone === "bullish" ? (
                            <>
                              <MarketAnimalIcon tone="bullish" />
                              <span>{isUsLocale ? "Bullish" : "Touro"}</span>
                            </>
                          ) : tone === "bearish" ? (
                            <>
                              <MarketAnimalIcon tone="bearish" />
                              <span>{isUsLocale ? "Bearish" : "Urso"}</span>
                            </>
                          ) : (isUsLocale ? "Watching" : "Monitorando")}
                        </strong>
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
    const chartToolToggles: Array<{ key: keyof ChartSettings; checked: boolean; label: string }> = [
      { key: "show_markers", checked: showMarkers, label: isUsLocale ? "Buy/Sell" : "Compra/Venda" },
      { key: "show_zones", checked: showZones, label: isUsLocale ? "Liquidity" : "Liquidez" },
      { key: "show_price_line", checked: showPriceLine, label: isUsLocale ? "Price line" : "Linha preço" },
      { key: "show_vwap", checked: showVwap, label: "VWAP" },
      { key: "show_averages", checked: showAverages, label: isUsLocale ? "Averages" : "Médias" },
      { key: "show_supertrend", checked: showSupertrend, label: "Supertrend" },
      { key: "show_macd", checked: showMacd, label: "MACD" },
      { key: "show_rsi", checked: showRsi, label: "RSI" },
      { key: "show_volume", checked: showVolume, label: "Volume" },
    ];

    return (
      <div id="panel-grafico" className="snbr-center-stack">
        <section className="snbr-chart-card">
          <div className="snbr-chart-topline">
            <div>
              <h2>{isUsLocale ? "Asset chart" : "Gráfico do ativo"}</h2>
              <p>{isUsLocale ? `VWAP, buy/sell, liquidity and structural read for ${selectedTicker} in one screen.` : `VWAP, compra/venda, liquidez e leitura estrutural de ${selectedTicker} na mesma tela.`}</p>
            </div>
            <div className="snbr-chart-actions">
              {chartToolToggles.map((item) => (
                <label key={item.key} className="snbr-toggle">
                  <input
                    checked={item.checked}
                    onChange={(event) => updateChartSetting(item.key, event.target.checked)}
                    type="checkbox"
                  />
                  <span>{item.label}</span>
                </label>
              ))}
              <button className="snbr-button secondary snbr-popout-button" onClick={() => openPopout("grafico")} type="button">
                {isUsLocale ? "Detach" : "Liberar Tela"}
              </button>
            </div>
          </div>

          <TickerChart
            chart={chartForDisplay}
            ticker={selectedTicker}
            interval={chartInterval}
            showMarkers={showMarkers}
            showZones={showZones}
            showPriceLine={showPriceLine}
            showVwap={showVwap}
            showAverages={showAverages}
            showMacd={showMacd}
            showRsi={showRsi}
            showSupertrend={showSupertrend}
            showVolume={showVolume}
            locale={appLocale}
          />

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
            <span>{isUsLocale ? "Reward rule" : "Regra de prêmio"}</span>
            <strong>
              {isUsLocale
                ? "3 valid paid referrals = 1 free month. 10 = Badge Vip. 100+ = Leaderboard King."
                : "3 indicações pagas e válidas = 1 mês grátis. 10 = Badge Vip. 100+ = Leaderboard King."}
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
    const monthlyLabel = isUsLocale ? "Managed in Google Play" : "Gerenciado no Google Play";
    const annualLabel = isUsLocale ? "Managed in Google Play" : "Gerenciado no Google Play";
    const subscriptionError = isUsLocale
      ? "Subscription, price and refund are handled in Google Play."
      : "Assinatura, preço e reembolso ficam no Google Play.";
    const annualError = subscriptionError;

    return (
      <div className="snbr-upgrade-stack">
        <div className="snbr-upgrade-card">
          <div>
            <strong>{isUsLocale ? "Premium Monthly" : "Premium Mensal"}</strong>
            <span>{monthlyLabel}</span>
          </div>
          <p>{isUsLocale ? "Unlocks web, app, Telegram, full AI tools, rankings and alerts. Price appears only in Google Play." : "Libera app Google Play, webpage, Telegram, IAs completas, ranking e alertas. Preço aparece somente no Google Play."}</p>
          <button className="snbr-button primary" onClick={() => setLoginError(subscriptionError)} type="button">
            {isPremium ? (isUsLocale ? "Active plan" : "Plano ativo") : (isUsLocale ? "Subscribe USA" : "Assinar pelo app")}
          </button>
        </div>
        <div className="snbr-upgrade-card featured">
          <div>
            <strong>{isUsLocale ? "Premium Annual" : "Premium Anual"}</strong>
            <span>{annualLabel}</span>
          </div>
          <p>{isUsLocale ? "Keeps web, app and Telegram unlocked. Checkout stays inside Google Play." : "Mantém app, website e Telegram liberados. Checkout fica no Google Play."}</p>
          <button className="snbr-button primary" onClick={() => setLoginError(annualError)} type="button">
            {isPremium ? (isUsLocale ? "Active plan" : "Plano ativo") : (isUsLocale ? "Annual USA" : "Assinar anual")}
          </button>
        </div>
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
            <span>{notice ? (isUsLocale ? "Scheduled maintenance" : notice.titulo) : (isUsLocale ? "No notice right now." : "Sem aviso no momento.")}</span>
            <small>{notice ? notice.corpo : (isUsLocale ? "Operational notices will appear here for website, app and Telegram." : "Nenhum comunicado operacional agora.")}</small>
          </div>
        ) : null}
      </div>
    );
  }

  function renderToolsCard() {
    return (
      <div className="snbr-side-card">
        <button
          className="snbr-side-card-trigger snbr-tools-card-trigger"
          onClick={() => setToolsOpen((value) => !value)}
          type="button"
          aria-expanded={toolsOpen}
        >
          <div>
            <h3>{isUsLocale ? "Tools" : "Ferramentas"}</h3>
            <p>{isUsLocale ? "Account preferences, blocked and muted users." : "Preferencias da conta, bloqueados e silenciados."}</p>
          </div>
          <span>{toolsOpen ? (isUsLocale ? "Close" : "Fechar") : (isUsLocale ? "Open" : "Abrir")}</span>
        </button>
        {toolsOpen ? (
          <>
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
                  <span>{isUsLocale ? "Dark mode" : "Modo escuro"}</span>
                  <button className={cx("snbr-switch", darkMode && "active")} onClick={() => setDarkMode((value) => !value)} type="button" aria-pressed={darkMode}>
                    <span />
                  </button>
                </div>
                <div className="snbr-settings-toggle-row">
                  <span>{isUsLocale ? "Cancel subscription" : "Encerrar assinatura"}</span>
                  <button className="snbr-switch" type="button" aria-pressed={false} disabled title={isUsLocale ? "Managed in Google Play." : "Gerenciado no Google Play."}>
                    <span />
                  </button>
                </div>
                <small>{renderCommercialPricingNote(appLocale)}</small>
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
          </>
        ) : null}
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

  const strategicConclusionExpanded = advancedMode && strategicConclusionOpen;
  const strategicConclusionPreview = strategicConclusionSections[0]?.body || strategicConclusion.headline;
  function toggleStrategicConclusion() {
    if (strategicConclusionExpanded) {
      setStrategicConclusionOpen(false);
      return;
    }
    if (proModeLocked) return;
    setAdvancedMode(true);
    setStrategicConclusionOpen(true);
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
          activeWatchCount={availableActiveWatchlist.length}
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
              const isAiTab = Boolean(AI_TOOL_TAB_MAP[tab.id as keyof typeof AI_TOOL_TAB_MAP]);
              const aiCount = aiToolFindingCounts[tab.id] ?? 0;

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
                    {isAiTab ? (
                      <span className="snbr-tab-count-badge" aria-label={isUsLocale ? `${aiCount} findings` : `${aiCount} achados`}>
                        {aiCount}
                      </span>
                    ) : null}
                  </button>
                </div>
              );
            })}
          </div>
          <button className="snbr-tab-scroll" onClick={() => scrollTabs("right")} type="button" aria-label={isUsLocale ? "Move tabs right" : "Mover tabs para a direita"}>
            ▶
          </button>
          <button
            className={cx("snbr-mode-toggle", advancedMode && "active", proModeLocked && "locked")}
            onClick={() => {
              if (proModeLocked) {
                setAdvancedMode(false);
                return;
              }
              setAdvancedMode((value) => !value);
            }}
            type="button"
            aria-pressed={advancedMode}
            aria-disabled={proModeLocked}
            title={
              proModeLocked
                ? (isUsLocale ? "Pro Mode locked after trial unless Premium is active" : "Modo Pro bloqueado após o trial sem Premium ativo")
                : advancedMode
                  ? (isUsLocale ? "Show simple mode" : "Mostrar modo simples")
                  : (isUsLocale ? "Open Pro details" : "Abrir detalhes Pro")
            }
          >
            {proModeLocked ? (isUsLocale ? "🔒 Pro Mode" : "🔒 Modo Pro") : (isUsLocale ? "Pro Mode" : "Modo Pro")}
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

            <div className="snbr-stat-strip" aria-label={isUsLocale ? "Indicator explanation boxes" : "Boxes explicativos dos indicadores"}>
              {stats.map((item) => (
                <div key={item.label} className={cx("snbr-stat-cell", item.tone)}>
                  <span className="snbr-stat-label">{item.label}</span>
                  <strong className="snbr-stat-value">{item.value}</strong>
                  {item.hint ? <small className="snbr-stat-help">{item.hint}</small> : null}
                </div>
              ))}
            </div>
          </section>
        ) : null}

        <section className="snbr-main-column">
          {error ? <div className="snbr-empty">Erro: {error}</div> : null}
          {loading && token ? <div className="snbr-empty">Carregando contexto do usuario...</div> : null}
          {showSymbolHeader ? (
            <section className="snbr-decision-panel" aria-label={isUsLocale ? "Strategic Analysis Panel" : "Painel de Análise Estratégica"}>
              <div className="snbr-decision-head">
                <strong>{isUsLocale ? "Strategic Analysis Panel" : "Painel de Análise Estratégica"}</strong>
                <div className="snbr-decision-mode-actions">
                  <strong className="snbr-decision-mode-label">
                    {advancedMode ? (isUsLocale ? "Pro Mode" : "Modo Pro") : (isUsLocale ? "Basic Mode" : "Modo Básico")}
                  </strong>
                  {!advancedMode ? (
                    <button
                      aria-label={isUsLocale ? "Open strategic analysis panel" : "Abrir painel de análise estratégica"}
                      className="snbr-section-head-action"
                      onClick={() => {
                        if (!proModeLocked) setAdvancedMode(true);
                      }}
                      type="button"
                    >
                      {isUsLocale ? "Open" : "Abrir"}
                    </button>
                  ) : null}
                </div>
              </div>
              {advancedMode ? (
                <>
                  <div className="snbr-decision-grid">
                    {essentialDecisionCards.map((card) => (
                      <article key={`${card.label}-${card.value}`} className={cx("snbr-decision-card", card.tone)}>
                        <span>{card.label}</span>
                        <strong>{card.value}</strong>
                      </article>
                    ))}
                  </div>
                  <article className={cx("snbr-decision-conclusion", strategicConclusion.tone, !strategicConclusionExpanded && "collapsed")}>
                    <div className="snbr-conclusion-topline">
                      <span>{isUsLocale ? "Conclusion" : "Conclusão"}</span>
                      <small>{isUsLocale ? `AI Analysis Time ${strategicConclusion.stamp}` : `IA Análise Hora ${strategicConclusion.stamp}`}</small>
                      <button
                        aria-expanded={strategicConclusionExpanded}
                        disabled={!strategicConclusionExpanded && proModeLocked}
                        onClick={toggleStrategicConclusion}
                        type="button"
                      >
                        {strategicConclusionExpanded ? (isUsLocale ? "Close" : "Fechar") : (isUsLocale ? "Open" : "Abrir")}
                      </button>
                    </div>
                    {strategicConclusionExpanded ? (
                      <>
                        <div className="snbr-conclusion-copy">
                          {strategicConclusionSections.length ? (
                            <div className="snbr-conclusion-sections">
                              {strategicConclusionSections.map((section) => (
                                <section key={section.title}>
                                  <strong>{section.title}</strong>
                                  {section.body ? <p>{section.body}</p> : null}
                                  {section.items?.length ? (
                                    <ul>
                                      {section.items.map((item: string) => (
                                        <li key={item}>{item}</li>
                                      ))}
                                    </ul>
                                  ) : null}
                                </section>
                              ))}
                            </div>
                          ) : (
                            <strong>{strategicConclusion.headline}</strong>
                          )}
                        </div>
                        <div className="snbr-conclusion-basis">
                          <div className="snbr-conclusion-basis-head">
                            <strong>{isUsLocale ? "Analysis basis" : "Base da análise"}</strong>
                          </div>
                          <ul>
                            {strategicConclusion.basis.map((item) => (
                              <li key={item}>{item}</li>
                            ))}
                          </ul>
                        </div>
                      </>
                    ) : (
                      <div className="snbr-conclusion-copy snbr-conclusion-preview">
                        <strong>{strategicConclusionPreview}</strong>
                      </div>
                    )}
                  </article>
                </>
              ) : null}
            </section>
          ) : null}
          {renderCenterPanel()}
        </section>
      </main>
    </div>
  );
}
