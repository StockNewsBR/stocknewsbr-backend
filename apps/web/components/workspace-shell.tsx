"use client";

import { startTransition, useDeferredValue, useEffect, useMemo, useRef, useState } from "react";
import type { ReactNode } from "react";
import { useSearchParams } from "next/navigation";

import { TickerChart } from "@/components/ticker-chart";
import { ImageLightbox } from "@/components/image-lightbox";
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
  noDataDecisionCopy,
  resolveNoDataReason,
  resolveStrategicSide,
  shouldSkipTradeAlignment,
  sideBlocksOperationalValues,
} from "@/lib/decision-state";
import { CORE_QUOTE_FIELD_IDS } from "@/lib/decision-state";
import { shouldPersistModeChange } from "@/lib/access-bootstrap";
import {
  classifyAccessOutcome,
  createAccessCounters,
  createSingleFlight,
  isRetryableAccessState,
  isStaleAccessResponse,
  isTerminalAccessState,
  resolveAdvancedMode,
} from "@/lib/access-authority";
import type { AccessState } from "@/lib/access-authority";
import { aiPanelKey, createDeadlineRegistry, isAiLoadingStatus } from "@/lib/ai-panel-lifecycle";
import type { OperationalReasonCode, StrategicDecisionSide } from "@/lib/decision-state";
import {
  COOKIE_SESSION_TOKEN,
  SESSION_REPLACED_EVENT,
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
  getPublicAiTools,
  getPublicMarketBundle,
  getPublicQuotesRobust,
  getPoll,
  searchAssets,
  getWorkspace,
  getWorkspaceTickerBundle,
  followUser,
  likePost,
  logoutAllAuth,
  logoutAuth,
  muteUser,
  postChatMessage,
  reportPost,
  requestEmailChange,
  requestLoginCode,
  requestTelegramLink,
  resolveApiBase,
  resolveMediaUrl,
  saveWorkspaceLayout,
  searchGifs,
  unfollowUser,
  unlikePost,
  updateProfile,
  uploadMedia,
  verifyEmailChange,
  verifyLoginOtp,
  votePoll,
} from "@/lib/api";
import { formatSocialTimestamp } from "@/lib/social-time";
import { TICKER_LOGOS } from "@/lib/ticker-logos";
import {
  canonicalSymbol as resolveCanonicalSymbol,
  canonicalSymbolAliases as resolveCanonicalSymbolAliases,
} from "@/lib/symbol-registry";
import type {
  AiToolRow,
  AiToolMetrics,
  ChartPayload,
  ChatHistoryPayload,
  FeedPayload,
  FeedPost,
  GifSearchItem,
  NewsItem,
  NewsPayload,
  PollPayload,
  PollOption,
  PublicAiToolsPayload,
  PublicBootstrap,
  PublicInsightPayload,
  PublicMarketMetrics,
  SymbolMetricComponent,
  SymbolOperationalView,
  QuotePayload,
  RankingRow,
  SignalRow,
  StrategicPanel,
  TelegramLinkSessionResponse,
  UserAccess,
  WorkspaceData,
  WorkspaceTab,
  WorkspaceObservabilityDashboard,
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
  show_macd: boolean;
  show_rsi: boolean;
  show_support: boolean;
  show_resistance: boolean;
  show_supertrend: boolean;
  show_volume: boolean;
};

type CommentComposerState = {
  active: boolean;
  sentiment: "bullish" | "bearish";
  file: File | null;
  previewUrl: string | null;
  gif: GifSearchItem | null;
  tool: "emoji" | "gif" | null;
  error: string;
};

type WatchlistItem = {
  symbol: string;
  label: string;
  category: string;
  logoUrl?: string | null;
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
        <span>The site login uses the same account e-mail as the app: request a secure access code by e-mail to unlock the full web version.</span>
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
      <span>O login do site usa o mesmo e-mail da conta do aplicativo: solicite um código de acesso seguro por e-mail para liberar a versão web completa.</span>
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
  flow: "flow",
  liquidity: "liquidity",
  trend: "trend",
  momentum: "momentum",
  "smart-money": "smart_money",
  risk: "risk",
  "news-ia": "news",
  macro: "macro",
  regime: "regime",
} as const;

const GLOBAL_AI_ALERT_TAB_IDS = new Set(["flow", "liquidity", "trend", "momentum"]);

const TAB_META: Record<string, { label: string; short: string }> = {
  grafico: { label: "📈 Gráfico IA / Rede Social", short: "Gráfico/Rede Social" },
  stockflow: { label: "🔥 Stock Flow", short: "Stock Flow" },
  news: { label: "📰 Notícias", short: "Notícias" },
  busca: { label: "🔎 Busca", short: "Busca" },
  flow: { label: "🏦 Fluxo IA", short: "Fluxo" },
  liquidity: { label: "🧲 Liquidez IA", short: "Liquidez" },
  trend: { label: "📈 Tendência IA", short: "Tendência" },
  momentum: { label: "⚡ Momento IA", short: "Momento" },
  "smart-money": { label: "💼 Dinheiro Inteligente IA", short: "Dinheiro Inteligente IA" },
  risk: { label: "⚠️ Risco IA", short: "Risco" },
  "news-ia": { label: "📰 Notícias IA", short: "Notícias IA" },
  macro: { label: "🌎 Macro IA", short: "Macro" },
  regime: { label: "📊 Regime IA", short: "Regime" },
  referrals: { label: "🤝 Afiliate/Indicações", short: "Afiliate/Indicações" },
  education: { label: "🎓 Ajuda Educacional para o Trader", short: "Ajuda Educacional para o Trader" },
};

const TAB_META_EN: Record<string, { label: string; short: string }> = {
  grafico: { label: "📈 AI Chart / Social Network", short: "Chart/Social" },
  stockflow: { label: "🔥 Stock Flow", short: "Stock Flow" },
  news: { label: "📰 News", short: "News" },
  busca: { label: "🔎 Search", short: "Search" },
  flow: { label: "🏦 Flow AI", short: "Flow" },
  liquidity: { label: "🧲 Liquidity AI", short: "Liquidity" },
  trend: { label: "📈 Trend AI", short: "Trend" },
  momentum: { label: "⚡ Momentum AI", short: "Momentum" },
  "smart-money": { label: "💼 Smart Money", short: "Smart" },
  risk: { label: "⚠️ Risk AI", short: "Risk" },
  "news-ia": { label: "📰 News AI", short: "News AI" },
  macro: { label: "🌎 Macro AI", short: "Macro" },
  regime: { label: "📊 Regime AI", short: "Regime" },
  referrals: { label: "🤝 Referrals", short: "Referrals" },
  education: { label: "🎓 Trader Educational Help", short: "Educational Help" },
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
  stockflow: "🔥 Stock Flow",
  news: "Notícias",
  flow: "Fluxo IA",
  liquidity: "Liquidez IA",
  trend: "Tendência IA",
  momentum: "Momento IA",
  "smart-money": "Dinheiro Inteligente IA",
  risk: "Risco IA",
  "news-ia": "Notícias IA",
  macro: "Macro IA",
  regime: "Regime IA",
  referrals: "Afiliate/Indicações",
  education: "Ajuda Educacional para o Trader",
};

const TOP_TAB_TEXT_EN: Record<string, string> = {
  grafico: "AI Chart / Social",
  stockflow: "🔥 Stock Flow",
  news: "News",
  flow: "Flow AI",
  liquidity: "Liquidity AI",
  trend: "Trend AI",
  momentum: "Momentum AI",
  "smart-money": "Smart Money",
  risk: "Risk AI",
  "news-ia": "News AI",
  macro: "Macro AI",
  regime: "Regime AI",
  referrals: "Referrals",
  education: "Educational Help",
};

const TAB_ORDER = [
  "grafico",
  "stockflow",
  "news",
  "flow",
  "liquidity",
  "trend",
  "momentum",
  "smart-money",
  "risk",
  "news-ia",
  "macro",
  "regime",
  "referrals",
  "education",
];

const TOP_BAR_TAB_IDS = TAB_ORDER.filter((id) => id !== "busca");
const SIMPLE_TOP_TAB_IDS = new Set([
  "grafico",
  // "stockflow" is Pro/Trial-only: excluded from Modo Básico (shown only when advancedMode).
  "news",
  "referrals",
  "education",
]);
const INTERNAL_AI_TAB_IDS = new Set(["risk", "news-ia", "macro", "regime"]);
// Ceiling for a pending AI hydration before the UI stops claiming it is still
// calculating. Backend PENDING_EXPIRED still wins when it arrives first.
const AI_PENDING_CLIENT_TIMEOUT_MS = 8000;
// Entitlement bootstrap retries: a starved or aborted /auth/access is a
// transport failure, not a denial.
const ACCESS_BOOTSTRAP_MAX_ATTEMPTS = 4;
const ACCESS_BOOTSTRAP_RETRY_BASE_MS = 500;
const WORKSPACE_MODE_STORAGE_KEY = "stocknewsbr.workspace_mode";
const WATCHLIST_STATE_STORAGE_KEY = "stocknewsbr.watchlist_state.v1";
const STRATEGIC_PANEL_STORAGE_KEY = "stocknewsbr.strategic_panel.open.v1";
// Non-sensitive resend-cooldown deadline (epoch ms) — survives reloads.
const CODE_COOLDOWN_STORAGE_KEY = "stocknewsbr.code_cooldown_until";
const DETACHABLE_IA_TABS = new Set([
  "grafico",
  "stockflow",
  "flow",
  "liquidity",
  "trend",
  "momentum",
  "smart-money",
  "risk",
  "news-ia",
  "macro",
  "regime",
]);

const FALLBACK_TABS: WorkspaceTab[] = [
  { id: "grafico", title: "Gráfico IA / Rede Social" },
  { id: "stockflow", title: "🔥 Stock Flow" },
  { id: "news", title: "Notícias" },
  { id: "busca", title: "Busca" },
  { id: "flow", title: "Fluxo IA" },
  { id: "liquidity", title: "Liquidez IA" },
  { id: "trend", title: "Tendência IA" },
  { id: "momentum", title: "Momento IA" },
  { id: "smart-money", title: "Dinheiro Inteligente IA" },
  { id: "risk", title: "Risco IA" },
  { id: "news-ia", title: "Notícias IA" },
  { id: "macro", title: "Macro IA" },
  { id: "regime", title: "Regime IA" },
  { id: "referrals", title: "Afiliate/Indicações" },
  { id: "education", title: "Ajuda Educacional para o Trader" },
];

const CATEGORY_ORDER = ["B3", "BDR", "Crypto", "USA"] as const;
const DEFAULT_CHART_SETTINGS: ChartSettings = {
  show_markers: true,
  show_zones: true,
  show_price_line: true,
  show_vwap: true,
  show_macd: true,
  show_rsi: true,
  show_support: true,
  show_resistance: true,
  show_supertrend: true,
  show_volume: true,
};
const APP_LOCALE_STORAGE_KEY = "snbr-app-locale";
const AI_ALERT_HISTORY_STORAGE_KEY = "snbr-ai-alert-history-v7";
const AI_TOOL_SOUND_STORAGE_KEY = "stocknewsbr.ai_tool_sound.v1";
const AI_DEAL_SOUND_URL = "/sounds/ka-ching.mp3";
const MAINTENANCE_NOTICES: Array<{ id: string; titulo: string; corpo: string }> = [];
const B3_SYMBOL_PATTERN = /^[A-Z][A-Z0-9]{3,4}(?:3|4|5|6|11)$/;
const BDR_SYMBOL_PATTERN = /^[A-Z][A-Z0-9]{3,4}34$/;
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
  "AXIA3.SA", "AXIA7.SA", "CPFE3.SA", "EQTL3.SA",
  "MGLU3.SA", "LREN3.SA", "AMER3.SA", "VIIA3.SA", "ASAI3.SA",
  "WEGE3.SA", "GGBR4.SA", "CSNA3.SA", "USIM5.SA",
  "TOTS3.SA", "POSI3.SA",
  "RAIL3.SA", "CCRO3.SA", "NTCO3.SA",
  "ABEV3.SA", "B3SA3.SA", "BBSE3.SA", "BRAP4.SA",
  "CMIG4.SA", "COGN3.SA", "CPLE3.SA", "CSAN3.SA",
  "CYRE3.SA", "DXCO3.SA", "EMBJ3.SA", "ENEV3.SA", "ENGI11.SA",
  "EZTC3.SA", "HAPV3.SA", "HYPE3.SA", "IRBR3.SA", "JBSS32.SA",
  "MBRF3.SA", "MRVE3.SA", "MULT3.SA", "PCAR3.SA", "PRIO3.SA",
  "RADL3.SA", "RAIZ4.SA", "RDOR3.SA", "RENT3.SA", "BRAV3.SA",
  "SBSP3.SA", "SLCE3.SA", "SMTO3.SA", "TAEE11.SA", "TIMS3.SA",
  "UGPA3.SA", "VBBR3.SA", "VIVT3.SA", "YDUQ3.SA",
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
  "AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "TSLA", "SPCX",
  "AMD", "INTC", "AVGO", "TSM",
  "JPM", "BAC", "GS",
  "XOM", "CVX",
  "COST", "WMT", "DIS",
  "CRM", "SNOW", "PLTR",
  "TTWO", "RACE", "LCID", "SAP", "UBER", "BYDDY", "GME", "COIN",
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
  "GOOGL",
  "AMZN",
  "META",
  "COIN",
  "UBER",
  "GME",
  "PLTR",
  "DIS",
  "DOGEUSD",
  "XRPUSD",
];

const INSTITUTIONAL_SECTIONS = [
  {
    id: "sobre-a-empresa",
    label: "1️⃣ Sobre a Empresa",
    title: "🏛 Sobre a Empresa",
    body: [
      "A StockNewsBR é uma plataforma inteligente que transforma dados em oportunidades de investimento.",
      "A plataforma utiliza Inteligência Artificial, cálculos avançados aplicados às finanças e estratégias institucionais inspiradas nos terminais utilizados por hedge funds norte-americanos.",
      "Oferece análises para traders dos mercados brasileiro e americano, com disponibilidade de ativos da B3, BDRs, ações dos Estados Unidos e criptoativos.",
      "A StockNewsBR transforma a leitura institucional, o fluxo e o contexto do mercado em uma tela simples e prática, ajudando o trader a obter insights rápidos, tomar decisões mais seguras e identificar oportunidades em sua operação diária.",
    ],
  },
  {
    id: "principais-modulos",
    label: "2️⃣ Principais Módulos da Plataforma",
    title: "🚀 Principais Módulos da Plataforma",
    body: [
      "Gráfico IA",
      "O Gráfico IA trabalha junto com o Painel de Análise Estratégica e pode apresentar orientações como compra, venda a descoberto, encerrar posição e aguardar confirmação.",
      "Informações apresentadas: direção provável, trade sugerido, regime, fluxo institucional, liquidez-alvo, risco, cenário atual, direção da estratégia, confirmação, interpretação, foco agora e base da análise.",
      "Indicadores disponíveis no gráfico: VWAP, MACD, RSI, SuperTrend e volume.",
      "Rede Social de Traders",
      "A Rede Social de Traders é gratuita e aberta a traders de qualquer corretora. Ela permite trocar ideias, estratégias e análises com outros investidores.",
      "Ao abrir uma ação ou criptoativo, o usuário pode votar na estratégia do ativo e compartilhar sua ideia.",
      "Temas de discussão: condição geral do mercado, rumores e notícias relevantes, análise fundamentalista, possíveis catalisadores, posicionamento dos traders, preços de entrada e saída, indicadores técnicos, análise gráfica, rompimentos, suportes e resistências, alvos de preço, sinais de compra e venda e sentimento coletivo sobre o ativo.",
      "A discussão permanece vinculada ao ativo correspondente, criando um espaço focado e colaborativo para cada ação ou criptoativo.",
      "Stock Flow",
      "Stock Flow — O pulso em tempo real do mercado financeiro. Todos os dias: agenda macro, análises com IA, enquetes de sentimento e debate ao vivo com a comunidade.",
      "Inteligências Artificiais",
      "Notícias IA — analisa a notícia como contexto de mercado, apresentando relevância, confiança e situação do provedor.",
      "Fluxo IA — analisa fluxo institucional, agressão e pressão compradora ou vendedora.",
      "Liquidez IA — consolida zonas de liquidez, varreduras, armadilhas e níveis de invalidação.",
      "Tendência IA — avalia a direção predominante e a estrutura atual do mercado.",
      "Momento IA — consolida aceleração, rompimentos e força relativa em uma única leitura.",
      "Dinheiro Inteligente IA — combina fluxo, acumulação e absorção, evitando duplicidade de confirmações.",
      "Programa de Afiliados",
      "Uma indicação é validada no oitavo dia após o pagamento do usuário indicado. A cada três indicações pagas e válidas, o assinante recebe um mês grátis, sem cashback. Dez indicações pagas e válidas concedem o badge VIP; cem ou mais concedem a classificação Leaderboard King.",
    ],
  },
  {
    id: "glossario-painel-estrategico",
    label: "3️⃣ Glossário: Painel de Análise Estratégica",
    title: "📘 Glossário: Painel de Análise Estratégica",
    body: ["Resumo rápido dos blocos que formam a leitura estratégica do ativo."],
    rows: [
      { item: "Score Mestre", explanation: "Pontuação geral do ativo. Consolida as leituras das IAs, os dados, a auditoria e o risco para resumir a força da oportunidade." },
      { item: "Direção provável", explanation: "Caminho mais provável do preço no curto prazo." },
      { item: "Trade sugerido", explanation: "Ação operacional indicada pela leitura: comprar, vender a descoberto, encerrar ou aguardar." },
      { item: "Regime", explanation: "Contexto predominante do mercado: alta, baixa ou lateralização." },
      { item: "Fluxo institucional", explanation: "Leitura da entrada ou saída dos grandes participantes do mercado." },
      { item: "Liquidez-alvo", explanation: "Zona de suporte ou resistência considerada mais relevante." },
      { item: "Risco", explanation: "Nível de risco da operação: baixo, médio ou alto." },
      { item: "Conclusão", explanation: "Resumo final da IA, incluindo cenário atual, direção da estratégia, confirmação, interpretação e foco atual." },
      { item: "Base da análise", explanation: "Números, indicadores e fatores utilizados para sustentar a leitura." },
    ],
  },
  {
    id: "glossario-grafico-ativo",
    label: "4️⃣ Glossário: Gráfico do Ativo",
    title: "📗 Glossário: Gráfico do Ativo",
    body: ["Resumo rápido dos indicadores e elementos apresentados no gráfico do ativo."],
    rows: [
      { item: "Candlestick ou vela", explanation: "Mostra a abertura, a máxima, a mínima e o fechamento do preço em cada período." },
      { item: "VWAP", explanation: "Preço médio ponderado pelo volume. É utilizado como referência de preço médio negociado." },
      { item: "MACD", explanation: "Indicador que ajuda a avaliar a força da tendência e possíveis mudanças de direção." },
      { item: "RSI", explanation: "Indicador que ajuda a identificar condições de sobrecompra ou sobrevenda." },
      { item: "SuperTrend", explanation: "Indicador técnico para identificar tendência e possíveis pontos de entrada ou saída." },
      { item: "Volume", explanation: "Quantidade negociada, utilizada para ajudar a confirmar a força do movimento." },
      { item: "Liberar Tela", explanation: "Abre o gráfico ou módulo selecionado em uma janela separada, permitindo o uso de vários gráficos e monitores." },
    ],
  },
  {
    id: "glossario-modos-plataforma",
    label: "5️⃣ Glossário: Modos de Uso da Plataforma",
    title: "⚙️ Glossário: Modos de Uso da Plataforma",
    body: ["Resumo dos modos de acesso e dos recursos disponíveis em cada experiência da plataforma."],
    rows: [
      { item: "Modo Básico", explanation: "Versão simplificada com Rede Social de Traders, gráfico do ativo, sentimento, volume relativo (RVOL) e votação da estratégia. Não inclui a leitura completa do Painel de Análise Estratégica, módulos avançados de IA, Telegram, sinais em tempo real, insights instantâneos, oportunidades ao vivo, alertas imediatos ou guidance em tempo real." },
      { item: "Modo Pro", explanation: "Versão completa, com acesso aos painéis avançados, módulos de IA, Telegram, análises adicionais e recursos profissionais." },
      { item: "Abrir", explanation: "Expande uma seção para apresentar o conteúdo completo." },
      { item: "Fechar", explanation: "Recolhe uma seção para deixar a tela mais organizada." },
      { item: "Ajuda Educacional para o Trader", explanation: "Área com explicações práticas para compreender os módulos e as leituras apresentadas pela plataforma." },
    ],
  },
  {
    id: "guia-rapido-stocknewsbr",
    label: "6️⃣ Guia Rápido StockNewsBR",
    title: "📚 Guia Rápido StockNewsBR",
    body: [
      "A StockNewsBR oferece inteligência de mercado com IA para traders da B3, BDRs, ações dos Estados Unidos e criptoativos.",
      "Seu objetivo é transformar dados complexos em oportunidades claras e práticas, atendendo desde investidores até traders que realizam operações de curto prazo.",
      "Fluxo básico de uso: 1. Pesquise ou selecione um ativo. 2. Abra o gráfico. 3. Consulte o Painel de Análise Estratégica. 4. Verifique os indicadores técnicos. 5. Consulte as leituras das IAs. 6. Analise notícias e contexto de mercado. 7. Confira o sentimento e a votação da comunidade. 8. Compartilhe ou consulte ideias na Rede Social de Traders. 9. Utilize as informações como apoio à sua própria decisão e gestão de risco.",
    ],
  },
  {
    id: "plataforma-web-trader-desk",
    label: "7️⃣ Plataforma Web Trader Desk",
    title: "🖥️ Plataforma Web Trader Desk",
    body: [
      "A Plataforma Web Trader Desk foi inspirada nos terminais utilizados por hedge funds dos Estados Unidos.",
      "Recursos: suporte ao uso de múltiplos monitores, abertura de gráficos e módulos em janelas separadas, velocidade de navegação, análises avançadas e interface simples para a operação diária.",
      "Clique em \"Liberar Tela\" no ativo ou módulo selecionado para abrir outra janela.",
      "Exemplo: Monitor 1: AAPL; Monitor 2: Momento IA; Monitor 3: Bitcoin. Também é possível abrir várias janelas em um único monitor.",
    ],
  },
  {
    id: "aviso-legal",
    label: "8️⃣ Aviso legal",
    title: "⚠️ Aviso legal",
    body: [
      "As informações, análises, indicadores, sinais, notícias, opiniões da comunidade e leituras geradas por Inteligência Artificial são fornecidos exclusivamente como apoio educacional e informativo.",
      "A StockNewsBR não garante resultados, rentabilidade ou acerto das análises apresentadas.",
      "As informações da plataforma não constituem recomendação individual de investimento, oferta de compra ou venda, consultoria financeira ou promessa de retorno.",
      "Toda decisão de investimento é de responsabilidade exclusiva do usuário. O mercado financeiro envolve riscos e pode gerar perdas parciais ou totais.",
      "Gestão de risco, disciplina e avaliação independente são essenciais antes de qualquer operação.",
    ],
  },
  {
    id: "por-que-stocknewsbr",
    label: "9️⃣ Por que escolher StockNewsBR?",
    title: "🎯 Por que escolher StockNewsBR?",
    body: [
      "Clareza — transforma informações complexas em leituras simples e objetivas.",
      "Velocidade — apresenta análises e contexto de mercado para ajudar o trader a identificar oportunidades.",
      "Tecnologia — utiliza Inteligência Artificial, cálculos avançados e estratégias institucionais.",
      "Educação — oferece explicações e glossários aplicáveis ao uso diário da plataforma.",
      "Inteligência — fornece suporte estratégico para decisões mais informadas.",
      "StockNewsBR: inteligência de mercado com estrutura institucional e Inteligência Artificial para apoiar a tomada de decisão do trader.",
    ],
  },
];

const INSTITUTIONAL_SECTIONS_EN = [
  {
    id: "sobre-a-empresa",
    label: "1️⃣ About the Company",
    title: "🏛 About the Company",
    body: [
      "StockNewsBR is an intelligent platform that turns data into investment opportunities.",
      "It uses Artificial Intelligence, advanced financial calculations and institutional strategies inspired by North American hedge fund terminals.",
      "It provides analysis for Brazilian and US market traders, including B3 assets, BDRs, US stocks and cryptoassets.",
      "StockNewsBR turns institutional reading, flow and market context into a simple, practical screen to help traders gain fast insights, make safer decisions and identify daily opportunities.",
    ],
  },
  {
    id: "principais-modulos",
    label: "2️⃣ Main Platform Modules",
    title: "🚀 Main Platform Modules",
    body: [
      "AI Chart",
      "The AI Chart works with the Strategic Analysis Panel and may present buy, sell short, close position and wait for confirmation guidance, plus likely direction, suggested trade, regime, institutional flow, liquidity target, risk, current scenario, strategy direction, confirmation, interpretation, focus now and analysis basis.",
      "Available chart indicators: VWAP, MACD, RSI, SuperTrend and volume.",
      "Trader Social Network",
      "The Trader Social Network is free and open to traders from any broker. Users can vote on an asset strategy and share ideas for each stock or cryptoasset. Discussions cover market conditions, news, fundamentals, catalysts, positioning, entry and exit prices, technical indicators, chart analysis, breakouts, support, resistance, price targets, signals and market sentiment.",
      "Stock Flow",
      "Stock Flow — Real-time pulse of the financial market. Every day: macro agenda, AI analysis, sentiment polls and live community debates.",
      "Artificial Intelligence",
      "News AI analyzes news as market context. Flow AI analyzes institutional flow and buying or selling pressure. Liquidity AI consolidates liquidity zones, sweeps, traps and invalidation levels. Trend AI evaluates market direction and structure. Momentum AI consolidates acceleration, breakouts and relative strength. Smart Money AI combines flow, accumulation and absorption without duplicated confirmations.",
      "Affiliate Program",
      "A referral is validated on the eighth day after the referred user's payment. Every three paid and valid referrals grant one free month, with no cashback. Ten paid and valid referrals grant the VIP badge; one hundred or more grant the Leaderboard King classification.",
    ],
  },
  {
    id: "glossario-painel-estrategico",
    label: "3️⃣ Glossary: Strategic Analysis Panel",
    title: "📘 Glossary: Strategic Analysis Panel",
    body: ["Quick overview of the blocks that form the asset's strategic reading."],
    rows: [
      { item: "Master Score", explanation: "Overall asset score. It consolidates AI readings, data, audit and risk to summarize the opportunity's strength." },
      { item: "Likely direction", explanation: "Most likely short-term price path." },
      { item: "Suggested trade", explanation: "Action indicated by the reading: buy, sell short, close or wait." },
      { item: "Regime", explanation: "Predominant market context: uptrend, downtrend or range." },
      { item: "Institutional flow", explanation: "Reading of large market participants entering or leaving." },
      { item: "Liquidity target", explanation: "The most relevant support or resistance zone." },
      { item: "Risk", explanation: "Trade risk level: low, medium or high." },
      { item: "Conclusion", explanation: "Final AI summary, including current scenario, strategy direction, confirmation, interpretation and current focus." },
      { item: "Analysis basis", explanation: "Numbers, indicators and factors used to support the reading." },
    ],
  },
  {
    id: "glossario-grafico-ativo",
    label: "4️⃣ Glossary: Asset Chart",
    title: "📗 Glossary: Asset Chart",
    body: ["Quick overview of the indicators and elements shown on the asset chart."],
    rows: [
      { item: "Candlestick or candle", explanation: "Shows the opening, high, low and closing price for each period." },
      { item: "VWAP", explanation: "Volume-weighted average price, used as a reference for the average traded price." },
      { item: "MACD", explanation: "Helps evaluate trend strength and possible changes in direction." },
      { item: "RSI", explanation: "Helps identify overbought or oversold conditions." },
      { item: "SuperTrend", explanation: "Technical indicator to identify trends and possible entry or exit points." },
      { item: "Volume", explanation: "Traded quantity, used to help confirm movement strength." },
      { item: "Detach", explanation: "Opens the selected chart or module in a separate window, allowing multiple charts and monitors." },
    ],
  },
  {
    id: "glossario-modos-plataforma",
    label: "5️⃣ Glossary: Platform Usage Modes",
    title: "⚙️ Glossary: Platform Usage Modes",
    body: ["Summary of the access modes and resources available in each platform experience."],
    rows: [
      { item: "Basic Mode", explanation: "Simplified version with the Trader Social Network, asset chart, sentiment, relative volume (RVOL) and strategy voting. It does not include the full Strategic Analysis Panel, advanced AI modules, Telegram, real-time signals, instant insights, live opportunities, immediate alerts or real-time guidance." },
      { item: "Pro Mode", explanation: "Full version with advanced panels, AI modules, Telegram, additional analysis and professional features." },
      { item: "Open", explanation: "Expands a section to show its full content." },
      { item: "Close", explanation: "Collapses a section to keep the screen organized." },
      { item: "Trader Educational Help", explanation: "Practical explanations to understand the platform's modules and readings." },
    ],
  },
  {
    id: "guia-rapido-stocknewsbr",
    label: "6️⃣ Quick StockNewsBR Guide",
    title: "📚 Quick StockNewsBR Guide",
    body: [
      "StockNewsBR provides AI market intelligence for B3, BDR, US stock and cryptoasset traders.",
      "Its goal is to turn complex data into clear, practical opportunities for investors and short-term traders.",
      "Basic flow: 1. Search for or select an asset. 2. Open the chart. 3. Consult the Strategic Analysis Panel. 4. Check technical indicators. 5. Consult the AI readings. 6. Analyze news and market context. 7. Check community sentiment and voting. 8. Share or consult ideas in the Trader Social Network. 9. Use the information as support for your own decisions and risk management.",
    ],
  },
  {
    id: "plataforma-web-trader-desk",
    label: "7️⃣ Web Trader Desk Platform",
    title: "🖥️ Web Trader Desk Platform",
    body: [
      "The Web Trader Desk Platform was inspired by terminals used by US hedge funds.",
      "Features include multi-monitor support, charts and modules in separate windows, navigation speed, advanced analysis and a simple daily-trading interface.",
      "Click \"Detach\" on the selected asset or module to open another window.",
      "Example: Monitor 1: AAPL; Monitor 2: Momentum AI; Monitor 3: Bitcoin. Multiple windows can also be opened on one monitor.",
    ],
  },
  {
    id: "aviso-legal",
    label: "8️⃣ Legal Notice",
    title: "⚠️ Legal Notice",
    body: [
      "Information, analysis, indicators, signals, news, community opinions and Artificial Intelligence readings are provided exclusively as educational and informational support.",
      "StockNewsBR does not guarantee results, profitability or accuracy of its analysis.",
      "Platform information is not individualized investment advice, an offer to buy or sell, financial advice or a promise of return.",
      "Every investment decision is the user's sole responsibility. Financial markets involve risk and can result in partial or total losses.",
      "Risk management, discipline and independent evaluation are essential before any trade.",
    ],
  },
  {
    id: "por-que-stocknewsbr",
    label: "9️⃣ Why choose StockNewsBR?",
    title: "🎯 Why choose StockNewsBR?",
    body: [
      "Clarity — turns complex information into simple, objective readings.",
      "Speed — provides market analysis and context to help traders identify opportunities.",
      "Technology — uses Artificial Intelligence, advanced calculations and institutional strategies.",
      "Education — provides explanations and glossaries applicable to everyday platform use.",
      "Intelligence — provides strategic support for more informed decisions.",
      "StockNewsBR: market intelligence with institutional structure and Artificial Intelligence to support trader decision-making.",
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
  AXIA3: "Axia Energia ON",
  AXIA7: "Axia Energia PNB",
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
  ABEV3: "Ambev S.A.",
  MBRF3: "MBRF (BRF+Marfrig)",
  JBSS32: "JBS",
  AAPL34: "Apple BDR",
  MSFT34: "Microsoft BDR",
  GOGL34: "Alphabet BDR",
  AMZN34: "Amazon BDR",
  NVDC34: "NVIDIA BDR",
  TSLA34: "Tesla BDR",
  META34: "Meta BDR",
  TTWO: "Take-Two",
  RACE: "Ferrari",
  LCID: "Lucid",
  SAP: "SAP SE",
  UBER: "Uber",
  BYDDY: "BYD",
  GME: "GameStop",
  COIN: "Coinbase",
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
  flow: {
    title: "🏦 Fluxo IA",
    description: "Lê fluxo institucional, agressão e pressão compradora ou vendedora.",
    explanation: "Mostra interesse institucional, mas não libera operação sem decision ready, dados válidos e risco controlado.",
  },
  liquidity: {
    title: "🧲 Liquidez IA",
    description: "Consolida zonas de liquidez, varreduras, armadilhas e invalidação.",
    explanation: "Une varredura e mapa de liquidez em uma leitura só, evitando duplicidade visual.",
  },
  trend: {
    title: "📈 Tendência IA",
    description: "Avalia direção predominante e estrutura de mercado.",
    explanation: "Tendência IA é dedicada: tendência fica separada de regime, momento e score.",
  },
  momentum: {
    title: "⚡ Momento IA",
    description: "Consolida radar, breakout e heat map em uma leitura de aceleração.",
    explanation: "Momento IA mostra força e exaustão, mas continua não acionável quando a decisão operacional não está pronta.",
  },
  "smart-money": {
    title: "💼 Dinheiro Inteligente IA",
    description: "Lê atuação institucional combinando fluxo, acumulação e absorção.",
    explanation: "Evita mostrar fluxo, dinheiro inteligente e acumulação como três confirmações independentes.",
  },
  risk: {
    title: "⚠️ Risco IA",
    description: "Mostra risco operacional, bloqueios, Can Trade e motivo de não operar.",
    explanation: "Score alto com dado ruim, liquidez fraca ou conflito continua bloqueado.",
  },
  "news-ia": {
    title: "📰 Notícias IA",
    description: "Mostra estado da notícia, relevância, confiança, impacto e status do provedor.",
    explanation: "Notícia é contexto. Não vira compra ou venda isolada.",
  },
  macro: {
    title: "🌎 Macro IA",
    description: "Separa macro real de macro derivado apenas de notícias.",
    explanation: "Macro-news não é apresentado como macro quantitativo.",
  },
  regime: {
    title: "📊 Regime IA",
    description: "Classifica contexto de mercado: tendência, lateralidade e volatilidade.",
    explanation: "Regime orienta o cenário, mas não substitui Risco IA nem decisão operacional.",
  },
};

const TOOL_COPY_EN: Record<string, { title: string; description: string; explanation: string }> = {
  flow: {
    title: "🏦 Flow AI",
    description: "Reads institutional flow, aggression and buying or selling pressure.",
    explanation: "Shows institutional interest, but never makes a trade actionable without decision readiness and valid data.",
  },
  liquidity: {
    title: "🧲 Liquidity AI",
    description: "Consolidates liquidity zones, sweeps, traps and invalidation.",
    explanation: "Combines sweep and liquidity map into one read to avoid duplicate confidence.",
  },
  trend: {
    title: "📈 Trend AI",
    description: "Reads dominant direction and market structure.",
    explanation: "Trend AI is dedicated: trend is separate from regime, momentum and score.",
  },
  momentum: {
    title: "⚡ Momentum AI",
    description: "Consolidates radar, breakout and heat map into one acceleration read.",
    explanation: "Momentum shows acceleration and exhaustion, but remains non-actionable when decision readiness is false.",
  },
  "smart-money": {
    title: "💼 Smart Money AI",
    description: "Reads institutional activity using flow, accumulation and absorption.",
    explanation: "Prevents Flow, Smart Money and Accumulation from appearing as three independent confirmations.",
  },
  risk: {
    title: "⚠️ Risk AI",
    description: "Shows operational risk, blocks, Can Trade and No Trade Reason.",
    explanation: "High score with bad data, weak liquidity or conflict stays blocked.",
  },
  "news-ia": {
    title: "📰 News AI",
    description: "Shows news state, relevance, confidence, impact and provider status.",
    explanation: "News is context. It is never a standalone buy or sell trigger.",
  },
  macro: {
    title: "🌎 Macro AI",
    description: "Separates real macro context from macro inferred only from news.",
    explanation: "Macro-news is not presented as quantitative macro.",
  },
  regime: {
    title: "📊 Regime AI",
    description: "Classifies market context: trend, range and volatility.",
    explanation: "Regime guides the scenario but does not replace Risk AI or operational decision.",
  },
};

const COMPOSER_EMOJI_CATEGORIES: Array<{ key: string; labelPt: string; labelEn: string; emojis: string[] }> = [
  { key: "faces", labelPt: "Carinhas", labelEn: "Faces", emojis: ["🙂", "😄", "😉", "😎", "🤔", "🙁", "😢", "😡", "🤯", "😱", "🥳", "😴"] },
  { key: "gestures", labelPt: "Gestos", labelEn: "Gestures", emojis: ["👍", "👎", "👏", "🙌", "💪", "🙏", "🤝", "✌️", "👌", "🤙", "✊", "👊"] },
  { key: "money", labelPt: "Dinheiro", labelEn: "Money", emojis: ["💰", "🤑", "💵", "💲", "💸", "🏦", "💳", "🪙", "💎", "🧾", "📊", "❤️"] },
  { key: "market", labelPt: "Mercado", labelEn: "Market", emojis: ["🐂", "🐻", "📈", "📉", "🚀", "🔥", "⚠️", "👀", "✅", "❌", "🎯", "🔻"] },
];
const RECENT_EMOJIS_STORAGE_KEY = "stocknewsbr.recent_emojis.v1";
const EMOJI_SHORTCUT_MAP: Record<string, string> = {
  "$$$": "🤑",
  "$$": "💰",
  "$": "💲",
  ":)": "🙂",
  ":(": "🙁",
  ";)": "😉",
  ":D": "😄",
  "<3": "❤️",
};
// Whitespace-token match only: "$PETR4" and "$10" never convert.
const EMOJI_SHORTCUT_REGEX = /(^|\s)(\$\$\$|\$\$|\$|:\)|:\(|;\)|:D|<3)(?=\s|$)/g;

function applyEmojiShortcuts(text: string) {
  return text.replace(EMOJI_SHORTCUT_REGEX, (_match, prefix: string, token: string) => `${prefix}${EMOJI_SHORTCUT_MAP[token] || token}`);
}
const QUICK_GIF_TERMS = ["bull market", "bear market", "stocks rally", "market crash"];
const SOCIAL_REPORT_REASONS = [
  { key: "spam", labelPt: "Spam", labelEn: "Spam" },
  { key: "golpe", labelPt: "Golpe", labelEn: "Scam" },
  { key: "manipulacao", labelPt: "Manipulação", labelEn: "Manipulation" },
  { key: "ofensivo", labelPt: "Ofensivo", labelEn: "Offensive" },
  { key: "fake_news", labelPt: "Fake News", labelEn: "Fake News" },
  { key: "outro", labelPt: "Outro", labelEn: "Other" },
];

function cx(...values: Array<string | false | null | undefined>) {
  return values.filter(Boolean).join(" ");
}

function publicSocialName(value?: string | null) {
  const name = String(value || "").trim();
  return name && !name.includes("@") && !/^user_/i.test(name) && !/^Trader\s+\d+$/i.test(name) ? name : "Trader";
}

function titleFromKey(key: string) {
  return key.replace(/_/g, " ").replace(/\b\w/g, (match) => match.toUpperCase());
}

function normalizeSymbol(raw: string) {
  return resolveCanonicalSymbol(raw);
}

function symbolAliases(raw?: string | null) {
  const source = String(raw || "").trim().toUpperCase();
  const normalized = normalizeSymbol(source);
  const aliases = new Set<string>();
  if (source) aliases.add(source);
  if (normalized) aliases.add(normalized);
  for (const alias of resolveCanonicalSymbolAliases(normalized || source)) aliases.add(alias);
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

function chartFallbackEndMs(interval: string) {
  const normalizedInterval = String(interval || "1D").toUpperCase();
  const now = Date.now();
  if (normalizedInterval !== "1D") return now;

  const local = new Date(now);
  const end = new Date(local);
  end.setHours(17, 55, 0, 0);
  const open = new Date(local);
  open.setHours(10, 0, 0, 0);
  if (local < open) {
    end.setDate(end.getDate() - 1);
  } else if (local <= end) {
    end.setTime(local.getTime());
    end.setMinutes(Math.floor(end.getMinutes() / 5) * 5, 0, 0);
  }
  while (end.getDay() === 0 || end.getDay() === 6) {
    end.setDate(end.getDate() - 1);
  }
  return end.getTime();
}

function chartFallbackShape(interval: string) {
  const normalizedInterval = String(interval || "1D").toUpperCase();
  const now = chartFallbackEndMs(normalizedInterval);
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
  const symbol = normalizeSymbol(item.symbol);
  const label = b3FutureLabel(symbol, locale) || DERIVATIVE_HINTS[symbol] || COMPANY_HINTS[symbol] || String(item.label || "").trim();
  return normalizeSymbol(label) === symbol || normalizeSymbol(label).replace(/\.SA$/, "") === symbol ? "" : label;
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

function renderSocialTimestamp(value: string | number | null | undefined, locale: AppLocale) {
  const formatted = formatSocialTimestamp(value, locale);
  return <time dateTime={formatted.dateTime} title={formatted.title}>{formatted.label}</time>;
}

function formatNewsClock(value?: string | null, locale: AppLocale = "pt-BR") {
  const missing = locale === "en-US" ? "no source time" : "sem horário da fonte";
  if (!value) return missing;
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return missing;
  return new Intl.DateTimeFormat(locale, {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
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
    normalizeSourceTimestamp(raw.published_at_source) ||
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

function formatNewsAge(ageMinutes?: number | null, publishedAtIso?: string | null, locale: AppLocale = "pt-BR") {
  const missing = locale === "en-US" ? "unknown age" : "idade não informada";
  let minutes = Number(ageMinutes);
  if (!Number.isFinite(minutes) && publishedAtIso) {
    const parsed = Date.parse(publishedAtIso);
    if (Number.isFinite(parsed)) minutes = Math.max(0, Math.floor((Date.now() - parsed) / 60000));
  }
  if (!Number.isFinite(minutes)) return missing;
  if (minutes < 60) return locale === "en-US" ? `${Math.round(minutes)} min` : `${Math.round(minutes)} min`;
  if (minutes < 1440) {
    const hours = Math.floor(minutes / 60);
    return locale === "en-US" ? `${hours} h` : `${hours} h`;
  }
  const days = Math.floor(minutes / 1440);
  return locale === "en-US" ? `${days} d` : `${days} d`;
}

function sourceDateIsToday(publishedAtIso?: string | null) {
  if (!publishedAtIso) return false;
  const parsed = new Date(publishedAtIso);
  if (Number.isNaN(parsed.getTime())) return false;
  const formatter = new Intl.DateTimeFormat("en-CA", {
    timeZone: "America/Sao_Paulo",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  });
  return formatter.format(parsed) === formatter.format(new Date());
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

function isGenericNewsHeadline(value?: string | null, symbol?: string | null) {
  const normalized = normalizeUiText(value);
  const ticker = normalizeSymbol(String(symbol || ""));
  if (!normalized || !ticker) return false;
  return (
    normalized === normalizeUiText(`Manchete internacional sobre ${ticker}`) ||
    normalized === normalizeUiText(`Noticia internacional sobre ${ticker}`) ||
    normalized === normalizeUiText(`Notícia internacional sobre ${ticker}`) ||
    normalized === normalizeUiText(`Relevant news for ${ticker}`) ||
    normalized === normalizeUiText(`News for ${ticker}`)
  );
}

function headlineFromNewsUrl(value?: string | null) {
  const raw = String(value || "").trim();
  if (!raw) return "";
  try {
    const url = new URL(raw);
    const slug = (url.pathname.split("/").filter(Boolean).pop() || "")
      .replace(/\.html?$/i, "")
      .replace(/-\d{7,}$/g, "")
      .trim();
    if (!slug || slug.length < 8) return "";
    return clampHeadline(
      slug
        .split("-")
        .filter(Boolean)
        .map((part, index) => {
          const lower = part.toLowerCase();
          if (["ai", "ev", "evs", "ceo", "ceos", "ipo", "etf", "usa"].includes(lower)) return lower.toUpperCase();
          if (["as", "and", "or", "the", "a", "an", "to", "with", "on", "in", "of", "for"].includes(lower) && index > 0) return lower;
          return `${lower.charAt(0).toUpperCase()}${lower.slice(1)}`;
        })
        .join(" "),
      150,
    );
  } catch {
    return "";
  }
}

function bestRawNewsHeadline(item: NewsItem, symbol: string) {
  const title = String(item.title || "").trim();
  if (title && !isGenericNewsHeadline(title, symbol)) return title;
  const fromUrl = headlineFromNewsUrl(item.url);
  if (fromUrl) return fromUrl;
  const candidate = [
    item.editorial,
    item.why_it_matters,
    item.impact_reason,
    item.market_context,
    item.trader_takeaway,
    item.card_summary,
    item.summary,
  ].find((value) => String(value || "").trim() && !isGenericNewsHeadline(String(value), symbol));
  return String(candidate || title || "").trim();
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

  const oilResults = normalized.match(/^(.+?)\s+results?\s+improves?\s+as\s+(.+?)\s+benefits?\s+from\s+stronger\s+oil\s+pricing$/i);
  if (oilResults) {
    return clampHeadline(`Resultados de ${oilResults[1]} melhoram com ${oilResults[2]} beneficiada por petróleo mais forte`);
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
    .replace(/\bresults?\s+improves?\b/gi, "resultados melhoram")
    .replace(/\bbenefits?\s+from\b/gi, "se beneficia de")
    .replace(/\bstronger\s+oil\s+pricing\b/gi, "petróleo mais forte")
    .replace(/\boil\s+pricing\b/gi, "preços do petróleo")
    .replace(/\bearnings?\b/gi, "resultados")
    .replace(/\bguidance\b/gi, "projeções")
    .replace(/\brevenue\b/gi, "receita")
    .replace(/\bprofit\b/gi, "lucro")
    .replace(/\bmarket\b/gi, "mercado")
    .replace(/\bpricing\b/gi, "precificação")
    .replace(/\bstronger\b/gi, "mais forte")
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
    .replace(/\bfrom\b/gi, "de")
    .replace(/\bas\b/gi, "com")
    .replace(/\bwith\b/gi, "com")
    .replace(/\bup to\b/gi, "até")
    .replace(/\bcustomer\b/gi, "cliente")
    .replace(/\bmore\b/gi, "mais")
    .replace(/\band\b/gi, "e");

  // Only publish the word-swapped headline when NOTHING English survives; a partial swap reads as
  // the "PBR ações Sinks com mercado Gains" hybrid the feed kept shipping. Otherwise show the
  // publisher's original English headline -- consistent source language beats a broken half-translation.
  const stillEnglish = /\b(the|and|of|for|to|in|on|is|are|was|with|why|here|amid|after|as|says|report|stock|shares|market|gains?|sinks?|beats?|misses?|jumps?|falls?|rises?|drops?|buy|sell|hold)\b/i.test(cleaned);
  if (cleaned !== normalized && !stillEnglish) return clampHeadline(cleaned);
  return clampHeadline(title);
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
    normalizeAlertTimestamp((row as any).found_at) ||
    normalizeAlertTimestamp((row as any).first_seen_at) ||
    normalizeAlertTimestamp(row.detected_at) ||
    normalizeAlertTimestamp((row as any).deal_detected_at) ||
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
    normalizeAlertTimestamp((row as any).last_confirmed_at) ||
    normalizeAlertTimestamp((row as any).updated_at) ||
    normalizeAlertTimestamp((row as any).as_of) ||
    normalizeAlertTimestamp((row as any).found_at) ||
    normalizeAlertTimestamp((row as any).first_seen_at) ||
    normalizeAlertTimestamp(row.detected_at) ||
    normalizeAlertTimestamp((row as any).deal_detected_at) ||
    normalizeAlertTimestamp(row.market_data_updated_at) ||
    normalizeAlertTimestamp(row.quote_time) ||
    normalizeAlertTimestamp(row.provider_timestamp) ||
    normalizeAlertTimestamp(row.last_bar_at) ||
    normalizeAlertTimestamp(row.bar_time) ||
    normalizeAlertTimestamp(row.time) ||
    normalizeAlertTimestamp(row.timestamp) ||
    normalizeAlertTimestamp(row.created_at)
  );
}

function resolveAiPublishedTimestamp(row: AiToolRow) {
  return (
    normalizeAlertTimestamp(row.published_at) ||
    normalizeAlertTimestamp(row.news_published_at) ||
    normalizeAlertTimestamp(row.provider_publish_time) ||
    normalizeAlertTimestamp((row as any).publishedAt) ||
    normalizeAlertTimestamp((row as any).providerPublishTime)
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
  const detectedAt =
    normalizeAlertTimestamp((row as any).found_at) ||
    normalizeAlertTimestamp((row as any).first_seen_at) ||
    normalizeAlertTimestamp(row.detected_at) ||
    normalizeAlertTimestamp((row as any).deal_detected_at) ||
    normalizeAlertTimestamp(row.market_data_updated_at) ||
    normalizeAlertTimestamp(row.quote_time) ||
    normalizeAlertTimestamp(row.provider_timestamp) ||
    normalizeAlertTimestamp(row.last_bar_at) ||
    normalizeAlertTimestamp(row.bar_time) ||
    normalizeAlertTimestamp(row.time) ||
    normalizeAlertTimestamp(row.timestamp) ||
    normalizeAlertTimestamp(row.created_at) ||
    undefined;
  const lastSeenAt =
    normalizeAlertTimestamp(row.last_seen_at) ||
    normalizeAlertTimestamp(row.updated_at) ||
    normalizeAlertTimestamp(fallbackIso) ||
    detectedAt;

  return {
    ...row,
    ...(detectedAt ? {
      found_at: normalizeAlertTimestamp((row as any).found_at) || detectedAt,
      first_seen_at: normalizeAlertTimestamp((row as any).first_seen_at) || detectedAt,
      detected_at: normalizeAlertTimestamp(row.detected_at) || detectedAt,
      updated_at: normalizeAlertTimestamp(row.updated_at) || lastSeenAt || detectedAt,
    } : {}),
    ...(lastSeenAt ? { last_seen_at: lastSeenAt } : {}),
  };
}

function getAlertResetKey(date = new Date()) {
  const saoPaulo = new Date(date.toLocaleString("en-US", { timeZone: "America/Sao_Paulo" }));
  if (saoPaulo.getHours() < 7) saoPaulo.setDate(saoPaulo.getDate() - 1);
  return saoPaulo.toISOString().slice(0, 10);
}

function aiFindingResetKey(row?: Partial<AiToolRow> | null) {
  const timestamp = row ? resolveAiFindingTimestamp(row as AiToolRow) : null;
  if (!timestamp) return "";
  const date = new Date(timestamp);
  if (Number.isNaN(date.getTime())) return "";
  return saoPauloDateKey(date);
}

function isFreshAiFindingForReset(row?: Partial<AiToolRow> | null, now = new Date()) {
  const rowKey = aiFindingResetKey(row);
  return Boolean(rowKey && rowKey === getAlertResetKey(now));
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
    case "flow":
      return { B3: 15, BDR: 3, USA: 2, Crypto: 0 };
    case "liquidity":
      return { B3: 11, BDR: 4, USA: 4, Crypto: 1 };
    case "trend":
      return { B3: 13, BDR: 3, USA: 4, Crypto: 1 };
    case "momentum":
      return { B3: 9, BDR: 4, USA: 5, Crypto: 2 };
    case "smart-money":
      return { B3: 10, BDR: 5, USA: 5, Crypto: 1 };
    case "risk":
      return { B3: 12, BDR: 4, USA: 4, Crypto: 2 };
    case "news-ia":
    case "macro":
      return { B3: 10, BDR: 4, USA: 5, Crypto: 2 };
    case "regime":
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
  return guessCategory(normalized) === "B3" || /^[A-Z0-9]{3,5}34$/.test(normalized) || normalized.startsWith("WIN") || normalized.startsWith("WDO");
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
  if (parsePriceNumber(value) == null) return locale === "en-US" ? "No confirmed quote" : "Sem cotação confirmada";
  const prefix = isBrazilianMarketSymbol(symbol) ? "R$" : "$";
  return `${prefix} ${formatLocalePrice(value, locale)}`;
}

function formatSignedPrice(value: unknown, locale: AppLocale) {
  const numeric = parsePriceNumber(value);
  if (numeric == null) return "n/a";
  return `${numeric > 0 ? "+" : ""}${formatLocalePrice(numeric, locale)}`;
}

function safeAssetLogoUrl(...values: Array<unknown>) {
  return safeAssetLogoUrls(...values)[0] ?? null;
}

function safeAssetLogoUrls(...values: Array<unknown>) {
  const urls: string[] = [];
  for (const value of values) {
    const url = String(value || "").trim();
    const ok = (url.startsWith("/") && !url.startsWith("//")) || /^https:\/\//i.test(url);
    if (ok && !urls.includes(url)) urls.push(url);
  }
  return urls;
}

const ASSET_MARK_TONES = ["#1bc47d", "#3b82f6", "#f59e0b", "#ef4444", "#8b5cf6", "#06b6d4", "#ec4899", "#14b8a6"];

function assetMarkTone(symbol: string) {
  let hash = 0;
  for (let index = 0; index < symbol.length; index += 1) hash = (hash * 31 + symbol.charCodeAt(index)) >>> 0;
  return ASSET_MARK_TONES[hash % ASSET_MARK_TONES.length];
}

// The initials circle is always rendered; the logo (when it exists and loads)
// paints over it. Nothing here can end up blank.
function AssetMark({ symbol, name, logoUrl, compact = false }: { symbol: string; name?: string | null; logoUrl?: string | null; compact?: boolean }) {
  const [attempt, setAttempt] = useState(0);
  // Ordered candidates: a broken backend logoUrl must fall back to the local
  // /logos map instead of dropping straight to initials (that was the header bug).
  const candidates = safeAssetLogoUrls(logoUrl, TICKER_LOGOS[normalizeSymbol(symbol)]);
  const src = candidates[attempt] ?? null;
  const size = compact ? 32 : 52;

  useEffect(() => {
    setAttempt(0);
  }, [candidates.join("|")]);

  return (
    <span
      className={cx("snbr-asset-mark", compact && "compact")}
      style={{ background: assetMarkTone(symbol), color: "#08150f" }}
      aria-label={name || symbol}
      title={name || symbol}
    >
      {initialsFromName(symbol)}
      {src ? (
        <img
          src={src}
          alt={name || symbol}
          width={size}
          height={size}
          loading="lazy"
          onError={() => setAttempt((current) => current + 1)}
        />
      ) : null}
    </span>
  );
}

type IndexStripItem = {
  symbol: string;
  display_name?: string | null;
  price?: number | null;
  change?: number | null;
  change_pct?: number | null;
  spark?: number[] | null;
  currency?: string | null;
  status?: string | null;
};

const INDEX_SPARK_W = 90;
const INDEX_SPARK_H = 28;

// Same min/max -> polyline mapping the Suporte/Resistência pane uses, without the
// level overlays. No chart library.
function IndexSparkline({ closes }: { closes: number[] }) {
  if (closes.length < 2) return null;

  const min = Math.min(...closes);
  const max = Math.max(...closes);
  const span = (max - min) || Math.max(Math.abs(max) * 0.01, 1e-6);
  const points = closes
    .map((value, index) => {
      const x = (index / (closes.length - 1)) * INDEX_SPARK_W;
      const y = 2 + (1 - (value - min) / span) * (INDEX_SPARK_H - 4);
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");

  return (
    <svg aria-hidden="true" className="snbr-index-spark" height={INDEX_SPARK_H} viewBox={`0 0 ${INDEX_SPARK_W} ${INDEX_SPARK_H}`} width={INDEX_SPARK_W}>
      <polyline points={points} />
    </svg>
  );
}

function friendlyAuthErrorMessage(error: unknown, locale: AppLocale = "pt-BR") {
  const raw = error instanceof Error ? error.message : String(error || "");

  if (/otp_invalid|otp_already_used|otp_expired|invalid_credentials/i.test(raw)) {
    return locale === "en-US" ? "Invalid or expired code." : "Código inválido ou expirado.";
  }
  if (/otp_too_many_attempts|muitas tentativas|429/i.test(raw)) {
    return locale === "en-US"
      ? "Too many attempts. Please wait before trying again."
      : "Muitas tentativas. Aguarde antes de tentar novamente.";
  }
  if (/session_replaced/i.test(raw)) {
    return locale === "en-US"
      ? "Your session ended because a new login happened on another device."
      : "Sua sessão foi encerrada porque houve login em outro dispositivo.";
  }
  if (/email_change_same_email/i.test(raw)) {
    return locale === "en-US"
      ? "The new e-mail must be different from the current one."
      : "O novo e-mail precisa ser diferente do atual.";
  }
  if (/email_change_failed/i.test(raw)) {
    return locale === "en-US"
      ? "It was not possible to change the e-mail."
      : "Não foi possível alterar o e-mail.";
  }
  if (/user_inactive/i.test(raw)) {
    return locale === "en-US" ? "Account unavailable." : "Conta indisponível.";
  }
  if (/failed to fetch|networkerror|load failed|aborterror|fetch failed/i.test(raw) || !raw.trim()) {
    return locale === "en-US"
      ? "Temporary connection issue. Please try again."
      : "Falha temporária de conexão. Tente novamente.";
  }
  // Never surface raw technical/English errors in the auth UI.
  return locale === "en-US" ? "Could not complete the request." : "Não foi possível concluir a solicitação.";
}

function friendlyNetworkErrorMessage(error: unknown, locale: AppLocale = "pt-BR") {
  const raw = error instanceof Error ? error.message : String(error || "");
  if (/failed to fetch|networkerror|load failed|aborterror|fetch failed/i.test(raw)) {
    return locale === "en-US"
      ? "Market data temporarily unavailable. The screen remains usable with cached data and clear fallbacks."
      : "Dados temporariamente indisponíveis. A tela continua funcional com cache e fallbacks claros.";
  }
  if (!raw.trim()) {
    return locale === "en-US" ? "Temporary data failure." : "Falha temporária de dados.";
  }
  return raw;
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
  return locale === "en-US" ? "no confirmed snapshot" : "sem snapshot";
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
  return trend ? localizeUiText(trend, locale) : locale === "en-US" ? "data unavailable" : "dados indisponíveis";
}

function hasWatchlistSnapshotData(item: {
  price?: number | null;
  changePct?: number | null;
}) {
  const price = Number(item.price);
  const changePct = Number(item.changePct);
  return Number.isFinite(price) && price > 0 && Number.isFinite(changePct);
}

function shouldShowTopBarTabId(
  id: string,
  advancedMode: boolean,
) {
  if (INTERNAL_AI_TAB_IDS.has(id)) return false;
  if (!advancedMode && !SIMPLE_TOP_TAB_IDS.has(id)) return false;
  return true;
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
    status === "empty" ||
    status === "partial" ||
    source.includes("no_price") ||
    source.includes("no-price") ||
    source.includes("empty")
  ) {
    return false;
  }
  const price = Number(quote.price);
  return Number.isFinite(price) && price > 0;
}

function quoteMatchesSymbol(quote: QuotePayload | null | undefined, symbol?: string | null) {
  const expectedAliases = new Set(symbolAliases(symbol).map((alias) => normalizeSymbol(alias)).filter(Boolean));
  if (!expectedAliases.size) return false;
  const identityCandidates = [
    quote?.symbol,
    (quote as any)?.provider_symbol,
    (quote as any)?.display_symbol,
    (quote as any)?.reference_symbol,
    (quote as any)?.exact_contract,
  ].map((value) => normalizeSymbol(String(value || ""))).filter(Boolean);
  if (!identityCandidates.length) return true;
  return identityCandidates.some((candidate) => expectedAliases.has(candidate));
}

function mergeQuoteState(current: Record<string, QuotePayload>, incoming: Record<string, QuotePayload>) {
  const next = { ...current };

  for (const [symbol, quote] of Object.entries(incoming)) {
    if (!symbol) continue;
    const quoteIdentity = normalizeSymbol(String(
      quote?.symbol ||
      (quote as any)?.display_symbol ||
      (quote as any)?.provider_symbol ||
      symbol ||
      "",
    ));
    const storageSymbol = quoteIdentity && quoteMatchesSymbol(quote, symbol) ? symbol : quoteIdentity || symbol;
    const normalized = normalizeSymbol(storageSymbol);
    const normalizedQuote = { ...quote, symbol: normalized || quote.symbol || storageSymbol };
    for (const alias of symbolAliases(storageSymbol)) {
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
    if (Number.isFinite(numeric) && numeric > 0) return normalizeMasterScoreForDisplay(numeric);
  }
  return null;
}

function normalizeMasterScoreForDisplay(score: number | null | undefined) {
  const numeric = Number(score);
  if (!Number.isFinite(numeric)) return null;
  if (numeric < 0) {
    console.warn("[StockNewsBR] Score Mestre negativo normalizado para display.", { raw: numeric, display: 0 });
    return 0;
  }
  if (numeric > 10) {
    const display = clampNumber(Number((numeric / 10).toFixed(1)), 0, 10);
    console.warn("[StockNewsBR] Score Mestre bruto normalizado para escala 0..10.", { raw: numeric, display });
    return display;
  }
  return clampNumber(Number(numeric.toFixed(1)), 0, 10);
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

// RVOL is current volume / average volume. This used to return volume/1_000_000,
// so a stock trading 3.5M shares displayed "RVOL 3.50" — read by a trader as 3.5x
// normal activity while being nothing but share count. Without an average volume
// there is no ratio to show: return null and let the caller render "sem leitura".
// A fabricated ratio is worse than a blank one.
function deriveRelativeVolume(volume?: number | null, averageVolume?: number | null) {
  return calculateRelativeVolume(volume, averageVolume);
}

function calculateRelativeVolume(volume?: number | null, averageVolume?: number | null) {
  const current = Number(volume);
  const average = Number(averageVolume);
  if (!Number.isFinite(current) || current <= 0 || !Number.isFinite(average) || average <= 0) return null;
  return clampNumber(Number((current / average).toFixed(2)), 0.1, 12);
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
    if (value == null || value === "") continue;
    const numeric = Number(value);
    if (Number.isFinite(numeric)) return numeric;
  }
  return null;
}

function firstValidRsiNumber(...values: Array<unknown>) {
  for (const value of values) {
    const numeric = Number(value);
    // A real RSI is never exactly 0 — providers send 0 when the indicator is
    // missing, which used to render as "0.0 — sobrevenda". Treat it as absent.
    if (Number.isFinite(numeric) && numeric > 0 && numeric <= 100) return numeric;
  }
  return null;
}

// Candle size the backend actually used -> the tag shown next to the RSI.
// Intraday sizes stay verbatim ("1m"/"5m"/"30m"/"1h"); daily/weekly get the desk
// spelling. Never falls back to the chart range button: that is the lie we removed.
function rsiTimeframeTag(metadata?: { timeframe?: string | null; candle_interval?: string | null } | null) {
  const raw = String(metadata?.candle_interval || metadata?.timeframe || "").trim().toLowerCase();
  if (!raw) return "";
  if (raw === "1d") return "D1";
  if (raw === "1wk" || raw === "1w") return "W1";
  return raw;
}

// Hidden from the page by owner decision; the RSI keeps feeding the strategic
// panel and AI scoring. Flip to true to show the card again.
const RSI_CARD_VISIBLE = true;

function describeRsiValue(value: number | null, locale: AppLocale = "pt-BR", candleTag = "D1", pending = false) {
  if (value == null || !Number.isFinite(value) || value <= 0 || value > 100) {
    return {
      label: "—",
      hint: pending ? (locale === "en-US" ? "Calculating daily RSI…" : "Calculando RSI diário…") : (locale === "en-US" ? "Daily RSI unavailable — insufficient provider data." : "RSI indisponível — dados insuficientes do provedor."),
      tone: "neutral" as const,
      basis: pending ? (locale === "en-US" ? "RSI: calculating." : "RSI: calculando.") : (locale === "en-US" ? "RSI: unavailable." : "RSI: indisponível."),
    };
  }

  // Canonical RSI copy thresholds (same on every surface): <30 sobrevenda,
  // 30-45 pressão vendedora, 45-55 neutro, 55-70 pressão compradora, >70 sobrecompra.
  const formatted = value.toFixed(1);
  // "RSI diário (D1)" only when the value really is daily; otherwise name the
  // candle size it was computed on, so the copy can never overstate the timeframe.
  const tag = (candleTag || "D1").trim() || "D1";
  const timeframeTag =
    tag === "D1"
      ? (locale === "en-US" ? "Daily RSI (D1)" : "RSI diário (D1)")
      : `RSI ${tag}`;
  if (value > 70) {
    return {
      label: locale === "en-US" ? "Overbought" : "Sobrecompra",
      // The band phrase is already the card value; the hint only adds what to do.
      hint: locale === "en-US" ? `${timeframeTag}: avoid chasing late entries.` : `${timeframeTag}: evite perseguir preço atrasado.`,
      tone: "up" as const,
      basis: locale === "en-US" ? `RSI: overbought at ${formatted}.` : `RSI: sobrecompra nos ${formatted}.`,
    };
  }
  if (value >= 55) {
    return {
      label: locale === "en-US" ? "Buying pressure" : "Pressão compradora",
      hint: locale === "en-US" ? `${timeframeTag}: buyers dominate.` : `${timeframeTag}: compradores dominam.`,
      tone: "up" as const,
      basis: locale === "en-US" ? `RSI: buying pressure at ${formatted}.` : `RSI: pressão compradora nos ${formatted}.`,
    };
  }
  if (value >= 45) {
    return {
      label: locale === "en-US" ? "Neutral" : "Neutro",
      hint: locale === "en-US" ? `${timeframeTag}: wait for price/volume confirmation.` : `${timeframeTag}: aguarde confirmação de preço/volume.`,
      tone: "watch" as const,
      basis: locale === "en-US" ? `RSI: neutral at ${formatted}.` : `RSI: neutro nos ${formatted}.`,
    };
  }
  if (value >= 30) {
    return {
      label: locale === "en-US" ? "Selling pressure" : "Pressão vendedora",
      hint: locale === "en-US" ? `${timeframeTag}: buyers need confirmation.` : `${timeframeTag}: compradores precisam confirmar reação.`,
      tone: "down" as const,
      basis: locale === "en-US" ? `RSI: selling pressure at ${formatted}.` : `RSI: pressão vendedora nos ${formatted}.`,
    };
  }
  return {
    label: locale === "en-US" ? "Oversold" : "Sobrevenda",
    hint: locale === "en-US" ? `${timeframeTag}: watch for a technical bounce before selling late.` : `${timeframeTag}: observe repique antes de vender atrasado.`,
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

// Coherence invariant (single reconciliation point for the three voices):
// - painel decision AGUARDAR/WAIT => Bias card may NOT say "Alta forte"/"Baixa forte";
// - price < VWAP => bullish bias copy gets the VWAP qualification line;
// - Score Mestre copy uses fixed bands (0-4 fraqueza, 4-6 neutro, 6-8 força moderada,
//   8-10 força forte) and matches the painel decision state.
function reconcileStatsWithDecision<T extends { label: string; value: string; hint: string }>(
  stats: T[],
  decisionAction: string,
  price: number | null,
  vwap: number | null,
  locale: AppLocale,
  side: StrategicDecisionSide = "wait",
): T[] {
  const isEnglish = locale === "en-US";
  // Canonical no-data state: a stale price, change, volume or VWAP from the
  // previous symbol must never be presented as current operational data.
  if (sideBlocksOperationalValues(side)) {
    const staleHint = isEnglish
      ? "No confirmed snapshot — value unavailable until the provider returns real data."
      : "Sem snapshot confirmado — valor indisponível até o provider retornar dados reais.";
    return stats.map((item) => {
      const label = normalizeUiText(item.label);
      const isOperationalValue = /variacao|change|volume|vwap|preco|price/.test(label);
      return isOperationalValue ? { ...item, value: "—", hint: staleHint } : item;
    });
  }
  const waiting = /AGUARDAR|WAIT/i.test(String(decisionAction || ""));
  const belowVwap = price != null && vwap != null && price < vwap;
  return stats.map((item) => {
    const label = normalizeUiText(item.label);
    if (label === "bias") {
      let value = item.value;
      let hint = item.hint;
      const normalizedValue = normalizeUiText(item.value);
      if (waiting && (normalizedValue.includes("alta forte") || normalizedValue.includes("strong uptrend"))) {
        value = isEnglish ? "Buyer bias" : "Viés comprador";
        hint = isEnglish
          ? "The panel decision is WAIT: buyer bias only counts after price/volume confirmation."
          : "O painel está em AGUARDAR: o viés comprador só vale após confirmação de preço/volume.";
      } else if (waiting && (normalizedValue.includes("baixa forte") || normalizedValue.includes("strong downtrend"))) {
        value = isEnglish ? "Seller bias" : "Viés vendedor";
        hint = isEnglish
          ? "The panel decision is WAIT: seller bias only counts after price/volume confirmation."
          : "O painel está em AGUARDAR: o viés vendedor só vale após confirmação de preço/volume.";
      }
      if (belowVwap && /alta|uptrend|compra|buyer/.test(normalizeUiText(value))) {
        hint = `${hint} ${isEnglish ? "Price below VWAP — limited strength." : "Preço abaixo do VWAP — força limitada."}`;
      }
      return value === item.value && hint === item.hint ? item : { ...item, value, hint };
    }
    if (label.includes("score")) {
      if (label.includes("parcial") || label.includes("partial")) return item;
      const numeric = Number(item.value);
      if (!Number.isFinite(numeric)) return item;
      const strength = numeric < 4
        ? (isEnglish ? "weakness" : "fraqueza")
        : numeric < 6
          ? (isEnglish ? "neutral" : "neutro")
          : numeric < 8
            ? (isEnglish ? "moderate strength" : "força moderada")
            : (isEnglish ? "strong strength" : "força forte");
      const sentence = numeric < 4
        ? (isEnglish ? "avoid longs without confirmation." : "evite compras sem confirmação.")
        : numeric < 6
          ? (isEnglish ? "wait for price/volume confirmation." : "aguarde confirmação de preço/volume.")
          : waiting
            ? (isEnglish ? "favors buying AFTER confirmation." : "favorece compra APÓS confirmação.")
            : (isEnglish ? "favors buying with confirmation." : "favorece compra com confirmação.");
      return { ...item, hint: `${item.value}: ${strength} — ${sentence}` };
    }
    return item;
  });
}

function firstPositiveFiniteNumber(...values: Array<unknown>) {
  for (const value of values) {
    const numeric = Number(value);
    if (Number.isFinite(numeric) && numeric > 0) return numeric;
  }
  return null;
}

function quoteMissingFieldsForUi(payload?: QuotePayload | null) {
  const raw = Array.isArray(payload?.missing_fields) ? payload?.missing_fields : [];
  return Array.from(new Set(raw.map((field) => normalizeUiText(String(field))).filter(Boolean)));
}

function quoteMissingFieldLabel(field: string, locale: AppLocale = "pt-BR") {
  const labels: Record<string, { pt: string; en: string }> = {
    price: { pt: "preço", en: "price" },
    volume: { pt: "volume", en: "volume" },
    score: { pt: "Score Mestre", en: "Master Score" },
    rsi: { pt: "RSI", en: "RSI" },
    bias: { pt: "Bias", en: "Bias" },
  };
  const label = labels[normalizeUiText(field)];
  if (!label) return field;
  return locale === "en-US" ? label.en : label.pt;
}

const DATA_QUALITY_LABELS: Record<string, string> = {
  real_time: "Dados Confiáveis",
  cached: "Dados Confiáveis",
  stale: "Dados Limitados",
  empty: "Dados Limitados",
  invalid: "Dados Limitados",
  score_only: "Dados Parciais",
};

function normalizeDataQuality(value: unknown) {
  const normalized = normalizeUiText(String(value ?? ""));
  if (["real_time", "cached", "stale", "empty", "invalid", "score_only"].includes(normalized)) return normalized;
  if (["priced", "valid", "fresh", "ok", "real", "snapshot", "market_cache"].includes(normalized)) return "cached";
  if (["partial", "limited"].includes(normalized)) return "score_only";
  if (["missing", "no_price", "no price", "sem preco", "sem preço", "unavailable"].includes(normalized)) return "empty";
  if (["error", "failed", "timeout", "provider_failed", "provider failed", "invalid"].includes(normalized)) return "invalid";
  return normalized || "empty";
}

function dataQualityLabel(value: unknown) {
  return DATA_QUALITY_LABELS[normalizeDataQuality(value)] || "Dados Limitados";
}

function dataQualityScore(value: unknown) {
  switch (normalizeDataQuality(value)) {
    case "real_time":
      return 100;
    case "cached":
      return 88;
    case "score_only":
      return 52;
    case "stale":
      return 35;
    case "empty":
      return 12;
    default:
      return 0;
  }
}

type CanonicalSnapshotRow = Partial<RankingRow & SignalRow & AiToolRow> & Record<string, unknown>;

function snapshotNumber(row: CanonicalSnapshotRow | null | undefined, ...keys: string[]) {
  if (!row) return null;
  return firstFiniteNumber(...keys.map((key) => row[key]));
}

function snapshotPositiveNumber(row: CanonicalSnapshotRow | null | undefined, ...keys: string[]) {
  if (!row) return null;
  for (const key of keys) {
    const numeric = firstFiniteNumber(row[key]);
    if (numeric != null && numeric > 0) return numeric;
  }
  return null;
}

function snapshotText(row: CanonicalSnapshotRow | null | undefined, ...keys: string[]) {
  if (!row) return "";
  for (const key of keys) {
    const value = row[key];
    if (typeof value === "string" && value.trim()) return value.trim();
  }
  return "";
}

function snapshotTimestamp(row: CanonicalSnapshotRow | null | undefined) {
  if (!row) return null;
  return (
    row.timestamp ||
    row.generated_at ||
    row.last_updated ||
    row.updated_at ||
    row.detected_at ||
    row.found_at ||
    row.created_at ||
    row.last_bar_at ||
    null
  ) as string | number | null;
}

function snapshotHasCoreData(row: CanonicalSnapshotRow | null | undefined) {
  if (!row) return false;
  const dataQuality = normalizeDataQuality(
    row.data_quality || row.quote_status || (row as any).status || (row as any).provider_status || (row as any).market_data_status,
  );
  if (["score_only", "missing", "empty", "stale", "invalid"].includes(dataQuality)) return false;
  if ((row as any).stale === true || (row as any).is_stale === true) return false;
  if ((row as any).provider_failed === true || (row as any).provider_error) return false;
  return (
    snapshotPositiveNumber(row, "price", "close", "last_price") != null &&
    snapshotPositiveNumber(row, "volume", "last_volume") != null
  );
}

function snapshotQuoteFromRow(symbol: string, row: CanonicalSnapshotRow | null | undefined): QuotePayload | null {
  const price = snapshotPositiveNumber(row, "price", "close", "last_price");
  if (price == null) return null;

  const volume = snapshotPositiveNumber(row, "volume", "last_volume");
  const averageVolume = snapshotPositiveNumber(row, "avg_volume", "average_volume", "averageVolume");
  const timestamp = snapshotTimestamp(row);

  return {
    symbol,
    price,
    change: snapshotNumber(row, "change", "change_abs", "price_change"),
    change_pct: snapshotNumber(row, "change_pct", "changePct", "variation", "variation_pct"),
    volume,
    average_volume: averageVolume,
    avg_volume: averageVolume,
    rel_volume: snapshotPositiveNumber(row, "rel_volume", "rvol", "relative_volume"),
    vwap: snapshotPositiveNumber(row, "vwap"),
    rsi: firstValidRsiNumber(row?.rsi),
    macd: snapshotNumber(row, "macd"),
    macd_signal: snapshotNumber(row, "macd_signal"),
    macd_histogram: snapshotNumber(row, "macd_histogram", "macd_hist"),
    source: "market_snapshot",
    quote_status: snapshotHasCoreData(row) ? "valid" : "partial",
    updated_at: timestamp,
    last_updated: timestamp,
  } as QuotePayload;
}

function snapshotInsightFromRow(symbol: string, row: CanonicalSnapshotRow | null | undefined): PublicInsightPayload | null {
  if (!row) return null;
  const score = usableScore(
    firstFiniteNumber(row.score),
    firstFiniteNumber(row.master_score),
    firstFiniteNumber(row.composite_score),
    firstFiniteNumber(row.final_score),
  );
  const rsi = firstValidRsiNumber(row.rsi);
  const relVolume = snapshotPositiveNumber(row, "rel_volume", "rvol", "relative_volume");
  const trend = snapshotText(row, "trend", "trend_bias", "bias", "state", "regime", "direction");
  const signal = snapshotText(row, "trade_action", "signal", "action", "side");
  if (score == null && rsi == null && relVolume == null && !trend && !signal) return null;
  return {
    symbol,
    score,
    rsi,
    rel_volume: relVolume,
    trend_bias: trend || null,
    signal: signal || null,
  };
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
  return normalizeDataQuality(direct ?? (typeof metrics === "string" ? metrics : ""));
}

function isOperationalAiFinding(row?: Partial<AiToolRow> | null) {
  const rawRow = (row || {}) as any;
  const auditor = rawRow.auditor || {};
  const auditStatus = String(rawRow.audit_status || rawRow.auditor_status || auditor.audit_status || "").toUpperCase();
  if (rawRow.blocked_by_auditor === true || auditor.blocked_by_auditor === true || auditStatus === "BLOCKED") return false;
  const price = firstFiniteNumber(rawRow.price);
  const volume = firstFiniteNumber(rawRow.volume);
  const quality = aiToolDataQuality(row);
  if (quality === "score_only" || quality === "missing") return false;
  return price != null && price > 0 && volume != null && volume > 0;
}

type AiDealRule = {
  high?: number;
  low?: number;
  states?: string[];
};

const AI_DEAL_RULES: Record<string, AiDealRule> = {
  flow: { high: 55, low: 25, states: ["institutional_buying", "institutional_interest", "distribution_risk"] },
  liquidity: { high: 55, states: ["liquidity_trap", "liquidity_zone", "thin_liquidity"] },
  trend: { high: 55, states: ["uptrend_structure", "downtrend_structure"] },
  momentum: { high: 55, states: ["momentum_expansion", "bearish_momentum", "momentum_watch"] },
  smart_money: { high: 55, states: ["institutional_accumulation", "institutional_defense", "possible_manipulation"] },
  risk: { high: 70, states: ["high_risk", "critical_risk"] },
  news: { high: 50, states: ["news_available"] },
  macro: { high: 35, states: ["macro_context_available", "macro_news_only"] },
  regime: { high: 60, states: ["bull_trend", "bear_trend", "high_volatility"] },
};

function isAiDealFinding(row?: Partial<AiToolRow> | null) {
  if (!isOperationalAiFinding(row)) return false;
  const rawRow = (row || {}) as any;
  const tool = String(rawRow.tool || "").trim();
  const state = String(rawRow.state || rawRow.signal || "").trim().toLowerCase();
  const signal = String(rawRow.signal || rawRow.trade_action || "").trim().toUpperCase();
  const score = firstFiniteNumber(rawRow.score ?? rawRow.metrics?.score ?? rawRow.metrics?.composite_score);
  const rule = AI_DEAL_RULES[tool] || { high: 60 };

  if (tool === "risk") {
    if (rawRow.decision_ready === false || rawRow.conflict_detected === true) return false;
    if (["BUY", "SELL", "SHORT", "COVER"].includes(signal)) return true;
  }

  if (rule.states?.some((term) => state.includes(term))) return true;
  if (score == null) return false;
  if (rule.high != null && score >= rule.high) return true;
  if (rule.low != null && score <= rule.low) return true;
  return false;
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
    "manchete relevante, mas ainda ambígua ou indireta para o papel; precisa de confirmação": "Relevant headline, but still ambiguous or indirect for the stock; wait for confirmation.",
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

  if (/^[A-Z][A-Z0-9]{3,4}\d{1,2}$/.test(normalized)) aliases.add(normalized.slice(0, -1));
  if (normalized === "F") {
    aliases.add("Ford");
    aliases.add("Ford Motor");
  }
  if (normalized === "BULL") {
    aliases.add("Webull");
    aliases.add("Webull Corp");
    aliases.add("Webull Corporation");
  }
  if (normalized === "BYDDY") {
    aliases.add("BYD");
    aliases.add("BYD Co");
    aliases.add("BYD Company");
    aliases.add("BYD Co Ltd");
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
    aliases.add("Itau Unibanco");
    aliases.add("Itaú Unibanco");
    aliases.add("ITUB");
  }
  if (normalized.startsWith("BBAS")) {
    aliases.add("Banco do Brasil");
    aliases.add("BBAS");
  }
  if (normalized.startsWith("VALE")) {
    aliases.add("Vale");
    aliases.add("VALE");
  }
  if (normalized === "BTCUSD") {
    aliases.add("Bitcoin");
    aliases.add("BTC");
  }
  if (normalized === "ETHUSD") {
    aliases.add("Ethereum");
    aliases.add("Ether");
    aliases.add("ETH");
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
  const directMarker = item.direct_ticker_match;
  const backendMatchedSymbol = normalizeSymbol((item as any).matched_symbol || "");
  const tickerMatches =
    backendMatchedSymbol === normalized ||
    (directMarker !== false && normalizeSymbol(item.ticker || "") === normalized);
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

function validExternalNewsUrl(value?: string | null) {
  const text = String(value || "").trim();
  if (!text) return "";
  try {
    const parsed = new URL(text);
    const host = parsed.hostname.toLowerCase();
    if (!["http:", "https:"].includes(parsed.protocol)) return "";
    if (!host.includes(".") || ["example.com", "www.example.com", "localhost", "127.0.0.1", "0.0.0.0"].includes(host)) return "";
    if (/(mock|fake|placeholder)/i.test(text)) return "";
    return parsed.toString();
  } catch {
    return "";
  }
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
  const title = bestRawNewsHeadline(item, symbol);
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

  const title = bestRawNewsHeadline(item, symbol);
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
  const fromUrl = headlineFromNewsUrl(item.url);
  if (fromUrl) return fromUrl;
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

function resolveNewsSentiment(item: NewsItem): "bullish" | "bearish" | "neutral" {
  const raw = normalizeUiText((item as any).sentiment || item.impact || item.impact_label || item.impact_reason || "");
  if (raw.includes("bull") || raw.includes("positivo") || raw.includes("alta") || raw.includes("compra")) return "bullish";
  if (raw.includes("bear") || raw.includes("negativo") || raw.includes("baixa") || raw.includes("venda")) return "bearish";
  return "neutral";
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

function cleanEnglishDecisionText(value: string | undefined | null, fallback: string, symbol: string) {
  const localized = localizeUiText(value || "", "en-US", symbol);
  const dirty = /\b(sem|se|quando|confirmacao|preco|suporte|resistencia|baixo|baixa|medio|alto|alta|compra|comprada|comprador|venda|vendida|vendedor|posicao|posição|recebeu|classificada|neutra|fraca|forte|composicao|fragilidades|pontos positivos|filtros|principais|alinhados|ordem operacional|tecnico|virada|ausencia|conflito de|divergirem|antes de|recuperar)\b/i.test(localized);
  return localized && !dirty ? localized : fallback;
}

type DecisionTone = "bullish" | "bearish" | "neutral" | "watch" | "exit";

type EssentialDecisionCard = {
  label: string;
  value: string;
  tone: DecisionTone;
  meta?: string;
  meter?: number | null;
};

type StrategicConclusion = {
  headline: string;
  focus: string;
  basis: string[];
  tone: DecisionTone;
  stamp: string;
  source?: "strategic_panel" | "client_fallback";
  sections?: Array<{
    title: string;
    body?: string;
    items?: string[];
  }>;
};

function strategicPanelText(value: unknown, fallback = "") {
  return typeof value === "string" && value.trim() ? value.trim() : fallback;
}

function strategicPanelTone(panel?: StrategicPanel | null): DecisionTone {
  const canonical = panel?.canonical_analysis;
  if (canonical?.decision === "CONFLICT" || canonical?.decision === "BLOCKED" || canonical?.suggested_trade === "NO_TRADE") return "watch";
  if (canonical?.direction === "BULLISH") return "bullish";
  if (canonical?.direction === "BEARISH") return "bearish";
  const action = strategicPanelText(panel?.recommended_action).toUpperCase();
  const direction = strategicPanelText(panel?.probable_direction_block?.direction).toUpperCase();
  const risk = strategicPanelText(panel?.risk_block?.level).toLowerCase();
  if (panel?.no_trade_now || action.includes("NÃO OPERAR") || action.includes("NAO OPERAR")) return "bearish";
  if (risk.includes("alto") || action.includes("AGUARDAR")) return "watch";
  if (direction === "BULLISH") return "bullish";
  if (direction === "BEARISH") return "bearish";
  return "watch";
}

function strategicPanelDecisionCards(panel: StrategicPanel, locale: AppLocale, trendOverride?: string | null): EssentialDecisionCard[] {
  const isEnglish = locale === "en-US";
  // Read the backend's explicit 0..10 value. Guessing the scale from the number's
  // magnitude turned a real 8/100 into "8.0 / 10" while 100/100 became "10.0" —
  // that is why the same score showed as two different numbers on one screen.
  const score = firstFiniteNumber((panel.master_score_block as any)?.score);
  const displayScore = firstFiniteNumber((panel.master_score_block as any)?.score_0_10)
    ?? normalizeMasterScoreForDisplay(score);
  const canonicalAnalysis = panel.canonical_analysis;
  const override = normalizeUiText(trendOverride || "");
  const direction = override.includes("alta") || override.includes("bull")
    ? (isEnglish ? "Up" : "Alta")
    : override.includes("baixa") || override.includes("bear")
      ? (isEnglish ? "Down" : "Baixa")
      : canonicalAnalysis?.direction === "BULLISH"
    ? (isEnglish ? "Up" : "Alta")
    : canonicalAnalysis?.direction === "BEARISH"
      ? (isEnglish ? "Down" : "Baixa")
      : (isEnglish ? "Neutral" : "Neutra");
  const action = strategicPanelText(panel.recommended_action, isEnglish ? "WAIT" : "AGUARDAR");
  const audit = strategicPanelText(panel.auditor_block?.visual_status, isEnglish ? "Attention" : "Atenção");
  const risk = strategicPanelText(panel.risk_block?.visual_level || panel.risk_block?.level, isEnglish ? "Moderate" : "Moderado");
  const conviction = strategicPanelText((panel.master_score_block as any)?.conviction_visual || (panel.master_score_block as any)?.conviction, isEnglish ? "Low conviction" : "Convicção baixa");
  const confidence = strategicPanelText((panel.master_score_block as any)?.confidence_visual || (panel.master_score_block as any)?.confidence, isEnglish ? "Low confidence" : "Confiança baixa");
  const tone = override ? decisionToneFromText(direction, trendOverride) : strategicPanelTone(panel);
  const riskTone: DecisionTone = /alto|high/i.test(risk) ? "bearish" : /baixo|low/i.test(risk) ? "bullish" : "watch";
  const flowItem = panel.why?.find((item) => item.tool === "flow");
  const flowValue = strategicPanelText(flowItem?.label).replace(/^[✅⚠•]\s*/, "") || (isEnglish ? "No read" : "Sem leitura");
  const flowTone = decisionToneFromText(flowValue, flowItem?.reason);
  const regime = override ? direction : (humanizeMachineLabel(canonicalAnalysis?.regime || "", locale) || (isEnglish ? "No read" : "Sem leitura"));
  const liquidity = firstPositiveFiniteNumber(panel.liquidez_alvo);
  return [
    {
      label: isEnglish ? "Master Score" : "Score Mestre",
      value: displayScore != null ? `${displayScore.toFixed(1)} / 10` : (isEnglish ? "No confirmed score" : "Sem score confirmado"),
      tone: displayScore != null && displayScore >= 8 ? "bullish" : displayScore != null && displayScore < 6 ? "watch" : tone,
      meta: confidence,
      meter: displayScore != null ? clampNumber(displayScore * 10, 0, 100) : null,
    },
    {
      label: isEnglish ? "Likely Direction" : "Direção provável",
      value: direction,
      tone,
    },
    {
      label: isEnglish ? "Recommended Action" : "Ação recomendada",
      value: action,
      tone: action.includes("NÃO OPERAR") || action.includes("NAO OPERAR") ? "bearish" : action.includes("AGUARDAR") ? "watch" : tone,
    },
    {
      label: isEnglish ? "Regime" : "Regime",
      value: regime,
      tone,
    },
    {
      label: isEnglish ? "Institutional Flow" : "Fluxo Institucional",
      value: flowValue,
      tone: flowTone === "exit" ? "neutral" : flowTone,
      meta: strategicPanelText(flowItem?.reason),
    },
    {
      label: isEnglish ? "Liquidity Target" : "Liquidez alvo",
      value: liquidity != null ? formatLocalePrice(liquidity, locale) : (isEnglish ? "No reading" : "Sem leitura"),
      tone,
    },
    {
      label: isEnglish ? "Risk" : "Risco",
      value: risk,
      tone: riskTone,
      meta: undefined,
    },
  ];
}

function strategicConclusionFromPanel(panel: StrategicPanel, locale: AppLocale): StrategicConclusion {
  const isEnglish = locale === "en-US";
  const tone = strategicPanelTone(panel);
  const whyItems = Array.isArray(panel.why)
    ? panel.why.map((item) => strategicPanelText(item?.label)).filter(Boolean)
    : [];
  const changeConditions = Array.isArray(panel.opinion_change_conditions)
    ? panel.opinion_change_conditions.map((item) => strategicPanelText(item)).filter(Boolean)
    : [];
  const noTradeReasons = Array.isArray(panel.no_trade_reasons)
    ? panel.no_trade_reasons.map((item) => strategicPanelText(item)).filter(Boolean)
    : [];
  const action = strategicPanelText(panel.recommended_action, isEnglish ? "WAIT" : "AGUARDAR");
  const summary = strategicPanelText(panel.llm_conclusion, strategicPanelText(panel.strategic_panel_summary, strategicPanelText(panel.master_score_block?.title, isEnglish ? "Strategic read unavailable." : "Leitura estratégica indisponível.")));
  const basis = [
    ...(whyItems.length ? whyItems : [summary]),
    strategicPanelText(panel.auditor_block?.summary),
    strategicPanelText(panel.risk_block?.visual_level || panel.risk_block?.level),
  ].filter(Boolean);
  const sections = [
    { title: isEnglish ? "Current Scenario" : "Cenário Atual", body: summary },
    { title: isEnglish ? "Why?" : "Por quê?", items: whyItems },
    ...(panel.no_trade_now ? [{ title: isEnglish ? "Do Not Trade Now" : "Não operar agora", items: noTradeReasons.length ? noTradeReasons : [summary] }] : []),
    { title: isEnglish ? "What Would Change My Mind?" : "O que mudaria minha opinião?", items: changeConditions },
  ].filter((section) => section.body || section.items?.length);
  return {
    headline: summary,
    focus: action,
    basis,
    tone,
    stamp: new Date().toLocaleTimeString(isEnglish ? "en-US" : "pt-BR", { hour: "2-digit", minute: "2-digit" }),
    source: "strategic_panel",
    sections,
  };
}

function operationalDecisionFromPanel(panel: StrategicPanel, locale: AppLocale): OperationalDecision {
  const isEnglish = locale === "en-US";
  const tone = strategicPanelTone(panel);
  const canonicalAnalysis = panel.canonical_analysis;
  const score = firstFiniteNumber((panel.master_score_block as any)?.score);
  const action = strategicPanelText(panel.recommended_action, isEnglish ? "WAIT" : "AGUARDAR");
  const confidence = strategicPanelText((panel.master_score_block as any)?.confidence, isEnglish ? "Low" : "Baixa");
  const reasons = Array.isArray(panel.no_trade_reasons) && panel.no_trade_reasons.length
    ? panel.no_trade_reasons
    : Array.isArray(panel.why)
      ? panel.why.map((item) => strategicPanelText(item?.label)).filter(Boolean).slice(0, 3)
      : [];
  const conditions = Array.isArray(panel.opinion_change_conditions) ? panel.opinion_change_conditions.slice(0, 4) : [];
  return {
    action,
    tone,
    // Reached only downstream of the canonical core-data gate, which is the
    // single authority for the no-data state.
    reasonCode: null,
    // The percentage MUST come from the same quantity the word is derived from.
    // This printed the Master Score with a "%" sign next to a label computed from
    // master_confidence_pct — two unrelated numbers, so "8%" could read "Alta".
    confidence: firstFiniteNumber(
      (panel as any)?.master_confidence_pct,
      (panel.master_score_block as any)?.confidence_pct,
    ),
    confidenceLabel: confidence,
    bias: canonicalAnalysis?.bias === "BULLISH" ? (isEnglish ? "Bullish" : "Comprador") : canonicalAnalysis?.bias === "BEARISH" ? (isEnglish ? "Bearish" : "Vendedor") : (isEnglish ? "Neutral" : "Neutro"),
    risk: strategicPanelText(panel.risk_block?.visual_level || panel.risk_block?.level, isEnglish ? "Moderate" : "Moderado"),
    reasons: reasons.length ? reasons : [strategicPanelText(panel.strategic_panel_summary, isEnglish ? "Strategic panel still has limited context." : "Painel estratégico ainda com contexto limitado.")],
    // Prefer the backend's PRICED levels (build_operational_levels). The old
    // phrase list was unreadable: four loose sentences with no numbers.
    levels: pricedOperationalLevels(panel, locale)
      ?? (conditions.length
        ? conditions.map((condition, index) => ({ label: index === 0 ? (isEnglish ? "1: Opinion changes if" : "1: Muda opinião se") : `${index + 1}`, value: condition }))
        : [{ label: isEnglish ? "Invalidation" : "Invalidação", value: isEnglish ? "Wait for a clearer snapshot." : "Aguardar snapshot mais claro." }]),
  };
}

function contextDirectionLabel(value: unknown, locale: AppLocale) {
  const tone = decisionToneFromText(value);
  if (tone === "bullish") return locale === "en-US" ? "Up" : "Alta";
  if (tone === "bearish") return locale === "en-US" ? "Down" : "Baixa";
  return locale === "en-US" ? "Neutral" : "Neutra";
}

function currentTechnicalBias(component?: SymbolMetricComponent | null) {
  const status = String(component?.status || "").toUpperCase();
  if (status !== "READY" && status !== "PARTIAL") return null;
  return component?.value ?? component?.label ?? null;
}

function formatMarketSessionTime(value: unknown, locale: AppLocale) {
  if (!value) return null;
  const raw = String(value);
  const dateOnly = raw.match(/^(\d{4})-(\d{2})-(\d{2})$/);
  if (dateOnly) {
    const [, year, month, day] = dateOnly;
    return locale === "en-US" ? `${month}/${day}/${year}` : `${day}/${month}/${year}`;
  }
  const formatted = formatNewsClock(raw, locale);
  return formatted === (locale === "en-US" ? "no source time" : "sem horário da fonte") ? null : formatted;
}

function dailyFreshnessMeta(component: SymbolMetricComponent | undefined, sessionDate: string | null | undefined, locale: AppLocale) {
  if (!component) return undefined;
  const isEnglish = locale === "en-US";
  const freshness = String(component.freshness_status || component.status || "").toUpperCase();
  const dataAsOf = component.data_as_of || component.as_of;
  const formattedDataAsOf = formatMarketSessionTime(dataAsOf, locale);
  const componentSessionDate = component.session_date || sessionDate;
  const formattedSessionDate = formatMarketSessionTime(componentSessionDate, locale);
  const parts: string[] = [];
  if (freshness === "STALE") parts.push(isEnglish ? "Outdated" : "Desatualizada");
  else if (freshness === "PARTIAL") parts.push(isEnglish ? "Partial" : "Parcial");
  if (formattedDataAsOf) parts.push(`${freshness === "STALE" ? (isEnglish ? "Last available session" : "Última sessão disponível") : (isEnglish ? "Data through" : "Dados até")}: ${formattedDataAsOf}`);
  if (formattedSessionDate && String(componentSessionDate).slice(0, 10) !== String(dataAsOf || "").slice(0, 10)) {
    parts.push(`${isEnglish ? "Displayed session" : "Sessão exibida"}: ${formattedSessionDate}`);
  }
  if (component.age_sessions != null) parts.push(`${component.age_sessions} ${isEnglish ? "session(s) old" : "sessão(ões) de defasagem"}`);
  return parts.length ? parts.join(" · ") : undefined;
}

function symbolContextDecisionCards(view: SymbolOperationalView, locale: AppLocale): EssentialDecisionCard[] {
  const isEnglish = locale === "en-US";
  const technical = view.technical_context;
  const operational = view.operational_context;
  const score = firstFiniteNumber(operational.master_score?.value);
  const scoreStatus = String(operational.master_score?.status || "PENDING").toUpperCase();
  const usedScoreComponents = operational.master_score?.used_components?.length || 0;
  const totalScoreComponents = usedScoreComponents + (operational.master_score?.missing_components?.length || 0);
  const trendStatus = String(technical.trend_d1?.freshness_status || technical.trend_d1?.status || "").toUpperCase();
  const trendReading = contextDirectionLabel(technical.trend_d1?.value, locale);
  const trendReadingDate = formatMarketSessionTime(String(technical.trend_d1?.data_as_of || technical.trend_d1?.as_of || "").slice(0, 10), locale);
  const trend = trendStatus === "STALE"
    ? (isEnglish ? "Outdated" : "Desatualizada")
    : technical.trend_d1?.value != null && ["READY", "PARTIAL"].includes(trendStatus)
      ? trendReading
    : (trendStatus === "PENDING" ? (isEnglish ? "Calculating…" : "Calculando…") : (isEnglish ? "Unavailable" : "Indisponível"));
  const trendMeta = trendStatus === "STALE"
    ? `${isEnglish ? "Last reading" : "Última leitura"}: ${trendReading}${trendReadingDate ? ` — ${trendReadingDate}` : ""}`
    : dailyFreshnessMeta(technical.trend_d1, view.session_date, locale);
  const intraday = technical.intraday_direction_5m?.status === "READY"
    ? contextDirectionLabel(technical.intraday_direction_5m?.value, locale)
    : (technical.intraday_direction_5m?.status === "PENDING" ? (isEnglish ? "Calculating…" : "Calculando…") : (isEnglish ? "Unavailable" : "Indisponível"));
  const flowValue = technical.institutional_flow?.status === "READY"
    ? `${technical.institutional_flow.label || (isEnglish ? "Current" : "Atual")}${technical.institutional_flow.value != null ? ` ${Number(technical.institutional_flow.value).toFixed(1)}` : ""}`
    : technical.institutional_flow?.status === "PENDING"
      ? (isEnglish ? "Calculating reading…" : "Calculando leitura…")
      : (isEnglish ? "Flow unavailable" : "Fluxo indisponível");
  const liquidity = operational.liquidity;
  const liquidityReady = liquidity?.status === "READY" && liquidity.side && firstFiniteNumber(liquidity.low) != null && firstFiniteNumber(liquidity.high) != null && firstFiniteNumber(liquidity.distance_from_price_pct) != null;
  const liquidityDistance = firstFiniteNumber(liquidity?.distance_from_price_pct);
  const liquidityValue = liquidityReady
    ? `${liquidity?.label} · ${formatLocalePrice(liquidity?.low, locale)}–${formatLocalePrice(liquidity?.high, locale)} · ${liquidityDistance != null && liquidityDistance > 0 ? "+" : ""}${liquidityDistance?.toFixed(2)}%`
    : liquidity?.status === "PENDING"
      ? (isEnglish ? "Calculating liquidity…" : "Calculando liquidez…")
      : (isEnglish ? "Unavailable" : "Indisponível");
  const liquidityUnavailableReason = liquidity?.reason === "missing_liquidity_bounds"
    ? (isEnglish ? "Liquidity bounds unavailable" : "Limites de liquidez indisponíveis")
    : liquidity?.reason === "missing_reference_price"
      ? (isEnglish ? "Reference price unavailable" : "Preço de referência indisponível")
      : liquidity?.reason === "missing_liquidity_timestamp"
        ? (isEnglish ? "Liquidity timestamp unavailable" : "Horário da liquidez indisponível")
        : liquidity?.reason === "invalid_liquidity_range"
          ? (isEnglish ? "Invalid liquidity range" : "Faixa de liquidez inválida")
          : (isEnglish ? "Insufficient data" : "Dados insuficientes");
  const liquidityMeta = liquidityReady
    ? `${liquidity?.timeframe || "5m"} · ${liquidity?.source || "—"} · ${formatNewsClock(liquidity?.as_of || undefined, locale)}`
    : liquidity?.status === "PENDING" ? undefined : liquidityUnavailableReason;
  const decision = view.decision === "WAIT" || view.decision === "AGUARDAR" ? (isEnglish ? "Wait" : "Aguardar") : view.decision;
  return [
    { label: scoreStatus === "PARTIAL" ? (isEnglish ? "Partial technical score" : "Score técnico parcial") : (isEnglish ? "Master Score" : "Score Mestre"), value: score != null ? `${score.toFixed(1)} / 10` : (isEnglish ? "No confirmed score" : "Sem score confirmado"), tone: scoreStatus === "READY" && score != null && score >= 6 ? "bullish" : "watch", meta: scoreStatus === "PARTIAL" && totalScoreComponents ? (isEnglish ? `Calculated with ${usedScoreComponents} of ${totalScoreComponents} components` : `Calculado com ${usedScoreComponents} de ${totalScoreComponents} componentes`) : scoreStatus, meter: score != null ? clampNumber(score * 10, 0, 100) : null },
    { label: isEnglish ? "D1 Trend" : "Tendência D1", value: trend, tone: trendStatus === "READY" || trendStatus === "PARTIAL" ? decisionToneFromText(technical.trend_d1?.value) : "neutral", meta: trendMeta },
    { label: isEnglish ? "Operational Decision" : "Decisão operacional", value: decision, tone: decision === "Wait" || decision === "Aguardar" ? "watch" : decisionToneFromText(decision) },
    { label: isEnglish ? "Intraday Direction 5m" : "Direção intraday 5m", value: intraday, tone: decisionToneFromText(technical.intraday_direction_5m?.value) },
    { label: isEnglish ? "Institutional Flow 5m" : "Fluxo institucional 5m", value: flowValue, tone: decisionToneFromText(technical.institutional_flow?.label) },
    { label: isEnglish ? "Liquidity 5m" : "Liquidez 5m", value: liquidityValue, tone: liquidityReady ? decisionToneFromText(liquidity?.label) : "neutral", meta: liquidityMeta },
    { label: isEnglish ? "Risk" : "Risco", value: view.risk || (isEnglish ? "Not confirmed" : "Não confirmado"), tone: "watch" },
  ];
}

function operationalDecisionFromSymbolContext(view: SymbolOperationalView, locale: AppLocale): OperationalDecision {
  const isEnglish = locale === "en-US";
  const componentLabels: Record<string, string> = {
    rvol: isEnglish ? "comparable intraday RVOL" : "RVOL intraday comparável",
    intraday_rvol: isEnglish ? "comparable intraday RVOL" : "RVOL intraday comparável",
    sentiment: isEnglish ? "sentiment" : "sentimento", flow: isEnglish ? "flow" : "fluxo",
    liquidity: isEnglish ? "liquidity" : "liquidez", levels: isEnglish ? "operational levels" : "níveis operacionais",
  };
  const blocks = (view.operational_blocks || []).map((item) => componentLabels[item.component] || item.component);
  const listed = blocks.length < 2 ? blocks[0] : `${blocks.slice(0, -1).join(", ")} ${isEnglish ? "and" : "e"} ${blocks[blocks.length - 1]}`;
  const trend = contextDirectionLabel(view.technical_context.trend_d1?.value, locale);
  const technicalBias = currentTechnicalBias(view.technical_context.technical_bias);
  const bias = technicalBias != null
    ? contextDirectionLabel(technicalBias, locale)
    : trend;
  const levels = (view.levels || []).flatMap((item: any) => {
    const price = firstPositiveFiniteNumber(item?.price);
    return price == null ? [] : [{ label: String(item?.label || (isEnglish ? "Level" : "Nível")), value: formatLocalePrice(price, locale) }];
  });
  return {
    action: view.decision === "WAIT" || view.decision === "AGUARDAR" ? (isEnglish ? "WAIT" : "AGUARDAR") : view.decision,
    tone: view.decision === "WAIT" || view.decision === "AGUARDAR" ? "watch" : decisionToneFromText(view.decision),
    // The symbol-context path never carries a no-data state of its own: the
    // core-data gate runs before this function is ever reached.
    reasonCode: null,
    confidence: firstFiniteNumber(view.confidence),
    confidenceLabel: view.confidence_status === "READY" ? (isEnglish ? "Confirmed" : "Confirmada") : (isEnglish ? "Not confirmed" : "Não confirmada"),
    bias,
    risk: view.risk || (isEnglish ? "Not confirmed" : "Não confirmado"),
    reasons: blocks.length ? [isEnglish ? "Technical context remains visible." : "Contexto técnico permanece visível.", `${isEnglish ? "Execution blocked" : "Execução bloqueada"}: ${listed}.`] : [isEnglish ? "Operational components confirmed." : "Componentes operacionais confirmados."],
    levels,
  };
}

type OperationalDecisionLevel = {
  label: string;
  value: string;
};

// Reads the backend's priced NÍVEIS OPERACIONAIS (strategic_panel.build_operational_levels).
// A level with no price is dropped entirely — a label with no number is the
// unreadable "frase jogada" this replaced. Returns null when nothing is priced,
// so the caller can fall back to the legacy phrase list.
function pricedOperationalLevels(panel: StrategicPanel, locale: AppLocale): OperationalDecisionLevel[] | null {
  const block = (panel as any)?.operational_levels_block?.levels ?? (panel as any)?.operational_levels;
  if (!block || typeof block !== "object") return null;
  const rows: OperationalDecisionLevel[] = [];
  for (const entry of Object.values(block as Record<string, any>)) {
    const price = firstPositiveFiniteNumber(entry?.price);
    if (price == null) continue;
    const label = strategicPanelText(entry?.label);
    const reason = strategicPanelText(entry?.reason);
    rows.push({
      label: label || (locale === "en-US" ? "Level" : "Nível"),
      value: reason ? `${formatLocalePrice(price, locale)} — ${reason}` : formatLocalePrice(price, locale),
    });
  }
  return rows.length ? rows : null;
}

type OperationalDecision = {
  action: string;
  tone: DecisionTone;
  confidence: number | null;
  confidenceLabel: string;
  bias: string;
  risk: string;
  reasons: string[];
  levels: OperationalDecisionLevel[];
  // Canonical domain state. `action` above is localized presentation copy and
  // must never be used as a logical authority — see lib/decision-state.ts.
  reasonCode: OperationalReasonCode | null;
};

type StrategicDecisionContract = {
  side: StrategicDecisionSide;
  tone: DecisionTone;
  decisionNow: string;
  tradeSuggested: string;
  direction: string;
  regime: string;
  bias: string;
  risk: string;
  confidence: number | null;
  confidenceLabel: string;
  reasons: string[];
  levels: OperationalDecisionLevel[];
  sections: NonNullable<StrategicConclusion["sections"]>;
  basis: string[];
};

function currentFiveMinuteBucket() {
  return Math.floor(Date.now() / (5 * 60_000)) * 5;
}

function defaultAiToolSoundSettings() {
  const defaults: Record<string, boolean> = {};
  Object.values(AI_TOOL_TAB_MAP).forEach((toolKey) => {
    defaults[toolKey] = toolKey === "risk";
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
  return toolKey === "risk";
}

function decisionToneFromText(...values: Array<unknown>): DecisionTone {
  const normalized = values
    .map((value) => normalizeUiText(String(value || "")))
    .filter(Boolean)
    .join(" ");
  if (!normalized) return "neutral";
  if (/\b(encerrar|cover|close short|close long|saida|sair|exit)\b/.test(normalized)) return "exit";
  if (/\b(short|sell short|venda descoberta|vender|venda|bear|bearish|baixa|queda|vendedor|distribuicao|negativo)\b/.test(normalized)) return "bearish";
  if (/\b(long|buy long|comprar|compra|bull|bullish|alta|comprador|acumulacao|positivo|forca)\b/.test(normalized)) return "bullish";
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
  if (tone === "bearish") return locale === "en-US" ? "Sell/Short" : "Venda / Short";
  return locale === "en-US" ? "Wait" : "Aguardar";
}

function tradeActionSide(value?: string | null): "buy" | "sell" | "wait" | "exit" {
  const normalized = normalizeUiText(String(value || ""));
  if (!normalized) return "wait";
  if (/\b(encerrar|proteger|close|exit|cover|saida|sair)\b/.test(normalized)) return "exit";
  if (/\b(aguardar|wait|sem dados|dados reais|bloquead|monitorar)\b/.test(normalized)) return "wait";
  const sell = /\b(venda|vender|vendido|short|sell|bear|baixa|queda)\b/.test(normalized);
  const buy = /\b(compra|comprar|comprado|buy|long|bull|alta)\b/.test(normalized);
  if (sell && buy) return "wait";
  if (sell) return "sell";
  if (buy) return "buy";
  return "wait";
}

function scoreConvictionLabel(score: number | null, locale: AppLocale) {
  if (score == null || !Number.isFinite(score)) return locale === "en-US" ? "No confirmed score" : "Sem score confirmado";
  if (score >= 8) return locale === "en-US" ? "Strong conviction" : "Convicção forte";
  if (score >= 6) return locale === "en-US" ? "Moderate conviction" : "Convicção moderada";
  if (score >= 4.5) return locale === "en-US" ? "Low conviction" : "Convicção baixa";
  return locale === "en-US" ? "Weak conviction" : "Convicção fraca";
}

function numericScoreFromDecisionCard(card?: EssentialDecisionCard | null) {
  if (!card?.value) return null;
  const match = String(card.value).match(/(\d+(?:[.,]\d+)?)/);
  if (!match) return null;
  const score = Number(match[1].replace(",", "."));
  return Number.isFinite(score) ? score : null;
}

function resolveOperationalZones(chart: ChartPayload | null) {
  const canonicalZones = resolveCanonicalChartLevelZones(chart);
  const support = canonicalZones.find((zone) => zone.kind === "support")?.price;
  const resistance = canonicalZones.find((zone) => zone.kind === "resistance")?.price;
  // A price level of 0 (or negative) means "not computed", not "zero reais".
  // Keeping firstFiniteNumber here is what put "Resistência: 0,00" on screen.
  return {
    support: firstPositiveFiniteNumber(support),
    resistance: firstPositiveFiniteNumber(resistance),
  };
}

type CanonicalChartLevelZone = {
  kind: "support" | "resistance";
  label: string;
  price: number;
  as_of?: string | null;
};

function resolveCanonicalChartLevelZones(chart: ChartPayload | null): CanonicalChartLevelZone[] {
  const zones = Array.isArray(chart?.zones) ? chart?.zones || [] : [];
  const rows = chart?.ohlc?.length ? chart.ohlc : chart?.series || [];
  const latestRow = rows.length ? rows[rows.length - 1] : null;
  const anchorPrice = firstFiniteNumber(chart?.summary?.latest_close, latestRow?.close, (latestRow as any)?.price);

  const parsed = zones
    .map((zone) => {
      const price = firstFiniteNumber(zone?.price);
      if (price == null || price <= 0) return null;
      const label = normalizeUiText(String(zone?.label || ""));
      const kind = /suporte|support/.test(label)
        ? "support"
        : /resistencia|resistance/.test(label)
          ? "resistance"
          : null;
      return kind && zone?.operational !== false && zone?.status !== "INSUFFICIENT_SEPARATION" ? { kind, label: String(zone?.label || kind), price } : null;
    })
    .filter((zone): zone is CanonicalChartLevelZone => zone != null);

  function pick(kind: CanonicalChartLevelZone["kind"]) {
    const candidates = parsed.filter((zone) => zone.kind === kind);
    if (!candidates.length) return null;
    if (anchorPrice == null || anchorPrice <= 0) return candidates[0];
    const directional = candidates.filter((zone) =>
      kind === "resistance" ? zone.price >= anchorPrice : zone.price <= anchorPrice,
    );
    const eligible = directional.length ? directional : candidates;
    return [...eligible].sort((left, right) => Math.abs(left.price - anchorPrice) - Math.abs(right.price - anchorPrice))[0];
  }

  return [pick("resistance"), pick("support")].filter((zone): zone is CanonicalChartLevelZone => zone != null);
}

function buildOperationalDecision(input: {
  locale: AppLocale;
  cards: EssentialDecisionCard[];
  conclusion: StrategicConclusion;
  chart: ChartPayload | null;
  hasCoreData: boolean;
  missingFields?: string[];
}): OperationalDecision {
  const isEnglish = input.locale === "en-US";
  const [, directionCard, tradeCard, regimeCard, flowCard, liquidityCard, riskCard] = input.cards;
  const score = numericScoreFromDecisionCard(scoreDecisionCard(input.cards));
  const suggestedSide = tradeActionSide(tradeCard?.value);
  const forceWait = suggestedSide === "wait" || tradeCard?.tone === "watch";
  const directionTone = forceWait ? "neutral" : decisionToneFromText(directionCard?.value, tradeCard?.value);
  const biasTone = decisionToneFromText(regimeCard?.value, directionCard?.value);
  const flowTone = decisionToneFromText(flowCard?.value);
  const riskLevel = strategicRiskLevelFromText(riskCard?.value);
  const zones = resolveOperationalZones(input.chart);
  const confidenceBase = score == null ? null : clampNumber(Math.round(score * 10), 0, 100);
  const confidence = confidenceBase == null
    ? null
    : clampNumber(
        confidenceBase +
          (riskLevel === "low" ? 5 : riskLevel === "high" ? -12 : -4) +
          (flowTone === "neutral" ? -5 : 0) +
          (!input.hasCoreData ? -35 : 0),
        0,
        100,
      );
  const confidenceLabel = confidence == null
    ? (isEnglish ? "No confidence" : "Sem confiança")
    : confidence >= 75
      ? (isEnglish ? "High confidence" : "Confiança alta")
      : confidence >= 55
        ? (isEnglish ? "Moderate confidence" : "Confiança moderada")
        : (isEnglish ? "Low confidence" : "Confiança baixa");
  const riskText = riskCard?.value || (isEnglish ? "No read" : "Sem leitura");
  const biasText = regimeCard?.value || directionCard?.value || (isEnglish ? "No read" : "Sem leitura");
  // Single canonical completeness predicate — see lib/decision-state.ts.
  const noDataReason = resolveNoDataReason({ hasCoreData: input.hasCoreData, score });
  const incomplete = noDataReason != null;

  let action = isEnglish ? "WAIT FOR CONFIRMATION" : "AGUARDAR CONFIRMAÇÃO";
  let tone: DecisionTone = "watch";
  if (incomplete) {
    action = isEnglish ? "WAIT FOR REAL DATA" : "AGUARDAR DADOS REAIS";
    tone = "watch";
  } else if (suggestedSide === "exit" || directionTone === "exit") {
    action = isEnglish ? "CLOSE OR PROTECT POSITION" : "ENCERRAR / PROTEGER POSIÇÃO";
    tone = "exit";
  } else if (!forceWait && (directionTone === "bearish" || biasTone === "bearish")) {
    action = riskLevel === "high"
      ? (isEnglish ? "WAIT / PROTECT CAPITAL" : "AGUARDAR / PROTEGER CAPITAL")
      : (isEnglish ? "SHORT ONLY WITH CONFIRMATION" : "SHORT SOMENTE COM CONFIRMAÇÃO");
    tone = "bearish";
  } else if (!forceWait && (directionTone === "bullish" || biasTone === "bullish")) {
    action = riskLevel === "low" && confidence != null && confidence >= 70
      ? (isEnglish ? "LOOK FOR BUY TRIGGER" : "BUSCAR GATILHO DE COMPRA")
      : (isEnglish ? "BUY ONLY WITH CONFIRMATION" : "COMPRA SOMENTE COM CONFIRMAÇÃO");
    tone = "bullish";
  }

  const reasons = (() => {
    if (incomplete) {
      return isEnglish
        ? ["Critical data fields are incomplete", "No operational conclusion will be generated", "Wait for provider quote/candles and a confirmed snapshot"]
        : ["Campos críticos de dados estão incompletos", "Nenhuma conclusão operacional será gerada", "Aguardar cotação/candles do provider e snapshot confirmado"];
    }
    if (tone === "bullish") {
      return [
        isEnglish ? `Master Score ${score?.toFixed(1)} supports a controlled buy thesis` : `Score Mestre ${score?.toFixed(1)} sustenta uma tese compradora controlada`,
        flowTone === "bullish"
          ? (isEnglish ? "Institutional flow supports buyers" : "Fluxo institucional apoia compradores")
          : (isEnglish ? "Flow still needs confirmation" : "Fluxo ainda precisa confirmar"),
        isEnglish ? "Entry must happen only after clean price confirmation" : "Entrada somente depois de confirmação limpa no preço",
      ];
    }
    if (tone === "exit") {
      return [
        isEnglish ? "Entry flow is not confirmed" : "Fluxo de entrada não está confirmado",
        isEnglish ? "Protection of the current position is the main decision zone" : "Proteção da posição atual é a principal zona de decisão",
        isEnglish ? "Wait for price and volume trigger before any new execution" : "Aguardar gatilho de preço e volume antes de qualquer nova execução",
      ];
    }
    if (tone === "bearish") {
      return [
        flowTone === "bearish"
          ? (isEnglish ? "Seller flow is stronger now" : "Fluxo vendedor está mais forte agora")
          : (isEnglish ? "Buyer flow is not confirmed" : "Fluxo comprador não está confirmado"),
        isEnglish ? "Resistance/liquidity is the main decision zone" : "Resistência/liquidez é a principal zona de decisão",
        riskLevel === "high"
          ? (isEnglish ? "High risk demands capital protection" : "Risco alto exige preservação de capital")
          : (isEnglish ? "Wait for price and volume trigger before action" : "Aguardar gatilho de preço e volume antes da ação"),
      ];
    }
    return isEnglish
      ? ["No side has enough confirmation", "Price, volume and flow must align", "Waiting is the professional decision now"]
      : ["Nenhum lado tem confirmação suficiente", "Preço, volume e fluxo precisam alinhar", "Aguardar é a decisão profissional agora"];
  })();

  if (incomplete) {
    return {
      action,
      tone,
      reasonCode: noDataReason,
      confidence: null,
      confidenceLabel,
      bias: isEnglish ? "Monitoring" : "Monitorando",
      risk: isEnglish ? "Insufficient data" : "Dados insuficientes",
      reasons,
      levels: [
        {
          label: isEnglish ? "Missing fields" : "Campos faltantes",
          value: input.missingFields?.length
            ? input.missingFields.join(", ")
            : (isEnglish ? "backend field diagnostics unavailable" : "diagnóstico de campos indisponível no backend"),
        },
        {
          label: isEnglish ? "Provider" : "Provider",
          value: isEnglish ? "Awaiting confirmed quote/candles" : "Aguardando cotação/candles confirmados",
        },
        {
          label: isEnglish ? "Snapshot" : "Snapshot",
          value: isEnglish ? "Incomplete" : "Incompleto",
        },
      ],
    };
  }

  const supportText = zones.support != null ? formatLocalePrice(zones.support, input.locale) : (isEnglish ? "No reading" : "Sem leitura");
  const resistanceText = zones.resistance != null ? formatLocalePrice(zones.resistance, input.locale) : (isEnglish ? "No reading" : "Sem leitura");
  const hasAnyLevel = zones.support != null || zones.resistance != null;
  const invalidation = tone === "exit"
    ? (zones.support != null ? `${isEnglish ? "Below protection level" : "Abaixo do nível de proteção"} ${supportText}` : (isEnglish ? "After confirmed protection-level failure" : "Após perda confirmada do nível de proteção"))
    : tone === "bullish"
    ? (zones.support != null ? `${isEnglish ? "Below" : "Abaixo de"} ${supportText}` : (isEnglish ? "Below confirmed support/VWAP" : "Abaixo do suporte/VWAP confirmado"))
    : tone === "bearish"
      ? (zones.resistance != null ? `${isEnglish ? "Above" : "Acima de"} ${resistanceText}` : (isEnglish ? "Above confirmed resistance/VWAP" : "Acima da resistência/VWAP confirmada"))
      : (isEnglish ? "After confirmed range break" : "Após rompimento confirmado da faixa");
  const tradeZone = tone === "exit"
    ? (zones.support != null ? `${isEnglish ? "Protection zone" : "Zona de proteção"}: ${supportText}` : (isEnglish ? "Protection zone: wait for trigger" : "Zona de proteção: aguardar gatilho"))
    : tone === "bullish"
    ? (zones.support != null ? `${isEnglish ? "Buy zone" : "Zona de compra"}: ${supportText}` : (isEnglish ? "Buy zone: wait for trigger" : "Zona de compra: aguardar gatilho"))
    : tone === "bearish"
      ? (zones.resistance != null ? `${isEnglish ? "Sell zone" : "Zona de venda"}: ${resistanceText}` : (isEnglish ? "Sell zone: wait for trigger" : "Zona de venda: aguardar gatilho"))
      : (isEnglish ? "No active zone" : "Sem zona ativa");

  return {
    action,
    tone,
    reasonCode: null,
    confidence,
    confidenceLabel,
    bias: biasText,
    risk: riskText,
    reasons,
    levels: [
      { label: isEnglish ? "Resistance" : "Resistência", value: resistanceText },
      { label: isEnglish ? "Support" : "Suporte", value: supportText },
      // Without a real level, "Invalidação: Acima de 0,00" is worse than silence.
      ...(hasAnyLevel
        ? [
          { label: isEnglish ? "Invalidation" : "Invalidação", value: invalidation },
          { label: isEnglish ? "Trade Zone" : "Zona operacional", value: tradeZone },
        ]
        : []),
    ],
  };
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
  if (conflict) return { label, value: locale === "en-US" ? "High" : "Alto", tone: "bearish" };
  if (effectiveScore == null) {
    return {
      label,
      value: locale === "en-US" ? "Insufficient data" : "Dados insuficientes",
      tone: "watch",
    };
  }
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
  rsiTimeframe?: string | null;
  price: number | null;
  changePct: number | null;
  volume: number | null;
  dailyVolumeRatio: number | null;
  relVolume: number | null;
  chartTrend?: string | null;
  chartSignal?: string | null;
  chartTimeframe?: string | null;
  chartAsOf?: string | null;
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
  const resolvedRvol = firstPositiveFiniteNumber(input.relVolume);
  const rvolBasis = resolvedRvol != null
    ? resolvedRvol >= 1.2
      ? (isEnglish
          ? `Comparable intraday RVOL: ${resolvedRvol.toFixed(2)}. The validated intraday ratio is above normal.`
          : `RVOL intraday comparável: ${resolvedRvol.toFixed(2)}. A razão intraday validada está acima do normal.`)
      : resolvedRvol < 0.8
        ? (isEnglish
            ? `Comparable intraday RVOL: ${resolvedRvol.toFixed(2)}. The validated intraday ratio is below normal.`
            : `RVOL intraday comparável: ${resolvedRvol.toFixed(2)}. A razão intraday validada está abaixo do normal.`)
        : (isEnglish
            ? `Comparable intraday RVOL: ${resolvedRvol.toFixed(2)}. The validated intraday ratio is near normal.`
            : `RVOL intraday comparável: ${resolvedRvol.toFixed(2)}. A razão intraday validada está próxima do normal.`)
    : (isEnglish
        ? "Comparable intraday RVOL: unavailable."
        : "RVOL intraday comparável: indisponível.");
  const priceBasis = input.price != null
    ? `${isEnglish ? "Price" : "Preço"}: ${formatPrice(input.price, input.locale)}`
    : (isEnglish ? "Price: unavailable" : "Preço: indisponível");
  const changeBasis = input.changePct != null
    ? `${isEnglish ? "Change" : "Variação"}: ${formatSignedPercent(input.changePct)}`
    : (isEnglish ? "Change: unavailable" : "Variação: indisponível");
  const volumeBasis = hasVolume
    ? (isEnglish ? `Volume: current ${formatVolumeLong(input.volume, input.locale)}` : `Volume: atual de ${formatVolumeLong(input.volume, input.locale)}`)
    : (isEnglish ? "Volume: unavailable" : "Volume: indisponível");
  const dailyVolumeBasis = input.dailyVolumeRatio != null
    ? `${isEnglish ? "Current volume / daily average" : "Volume atual / média diária"}: ${formatLocalePrice(input.dailyVolumeRatio, input.locale)}× · ${isEnglish ? "informational, not operational RVOL" : "informativo, não é RVOL operacional"}`
    : (isEnglish ? "Current volume / daily average: unavailable" : "Volume atual / média diária: indisponível");
  const rsiDescription = describeRsiValue(input.rsi, input.locale, input.rsiTimeframe || undefined);
  const rsiBasis = rsiDescription.basis.replace(
    /^RSI/i,
    isEnglish ? "Internal snapshot RSI" : "RSI do snapshot interno",
  );
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
  const chartTrend = input.chartTrend || input.regime;
  const chartTimeframe = input.chartTimeframe || input.rsiTimeframe || "—";
  const regimeBasis = chartTrend
    ? (isEnglish ? `Internal snapshot trend (${chartTimeframe}): ${chartTrend}` : `Tendência do snapshot interno (${chartTimeframe}): ${chartTrend}`)
    : (isEnglish ? `Internal snapshot trend (${chartTimeframe}): no clear read` : `Tendência do snapshot interno (${chartTimeframe}): sem leitura clara`);
  const chartSignalBasis = input.chartSignal
    ? (isEnglish
        ? `Latest internal snapshot event (not an operational decision): ${humanizeMachineLabel(input.chartSignal, input.locale)}`
        : `Último evento do snapshot interno (não é decisão operacional): ${humanizeMachineLabel(input.chartSignal, input.locale)}`)
    : (isEnglish ? "Latest internal snapshot event: unavailable" : "Último evento do snapshot interno: indisponível");
  const chartAsOfBasis = input.chartAsOf
    ? `${isEnglish ? "Internal snapshot through" : "Snapshot interno até"}: ${formatNewsClock(input.chartAsOf, input.locale)}`
    : (isEnglish ? "Internal snapshot through: unavailable" : "Snapshot interno até: indisponível");
  const flowBasis = input.flow
    ? (isEnglish ? `Institutional flow: ${input.flow}` : `Fluxo institucional: ${input.flow}`)
    : (isEnglish ? "Institutional flow without read" : "Fluxo institucional sem leitura");
  const liquidityBasis = input.liquidity
    ? `${isEnglish ? "Operational liquidity" : "Liquidez operacional"}: ${input.liquidity}`
    : (isEnglish ? "Operational liquidity: unavailable" : "Liquidez operacional: indisponível");
  const basis = [
    priceBasis,
    changeBasis,
    regimeBasis,
    chartSignalBasis,
    rsiBasis,
    volumeBasis,
    dailyVolumeBasis,
    scoreBasis,
    flowBasis,
    liquidityBasis,
    riskBasis,
    rvolBasis,
    chartAsOfBasis,
  ];
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
          ? "Focus now: use the available chart, price and volume as context, but wait for Master Score, liquidity and flow confirmation before execution."
        : "Foco Agora: usar gráfico, preço e volume disponíveis como contexto, mas aguardar Score Mestre, liquidez e fluxo confirmarem antes da execução.";
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
        ? "The chart has a technical reading, but the operational decision remains blocked until Master Score, flow and liquidity are confirmed."
        : "O gráfico tem leitura técnica, mas a decisão operacional permanece bloqueada até Score Mestre, fluxo e liquidez ficarem confirmados.",
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
  if (conclusion.source === "strategic_panel" && conclusion.sections?.length) {
    return conclusion.sections;
  }
  const isEnglish = locale === "en-US";
  const assetLabel = normalizeSymbol(symbol) || (isEnglish ? "the asset" : "o ativo");
  const basisText = conclusion.basis.join(" | ");
  const scoreLine = conclusion.basis.find((item) => /score|convic/i.test(item)) || "";
  const riskLine = conclusion.basis.find((item) => /risk|risco/i.test(item)) || "";
  const regimeLine = conclusion.basis.find((item) => /bias|trend|tend[eê]ncia|regime/i.test(item)) || "";
  const flowLine = conclusion.basis.find((item) => /flow|fluxo/i.test(item)) || "";
  const rvolLine = conclusion.basis.find((item) => /rvol|volume relativo/i.test(item)) || "";
  const rsiLine = conclusion.basis.find((item) => /\brsi\b/i.test(item)) || "";
  const chartSignalLine = conclusion.basis.find((item) => /latest internal snapshot event|último evento do snapshot interno/i.test(item)) || "";
  const dailyVolumeLine = conclusion.basis.find((item) => /current volume \/ daily average|volume atual \/ média diária/i.test(item)) || "";
  const basisNumber = (line: string) =>
    Number(line.match(/:\s*(-?\d+(?:[.,]\d+)?)/)?.[1]?.replace(",", "."));
  const scoreValue = basisNumber(scoreLine);
  const rvolValue = basisNumber(rvolLine);
  const rsiValue = basisNumber(rsiLine);
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
  const finalToneRequiresProtection = conclusion.tone === "bearish" || conclusion.tone === "exit";
  const directionalBuyBlocked = finalToneRequiresProtection || regimeBear || sellerFlow;
  const directionalSellBlocked = conclusion.tone === "bullish" || (!finalToneRequiresProtection && (regimeBull || buyerFlow));
  const bullishSetup =
    !incompleteRead &&
    !directionalBuyBlocked &&
    (conclusion.tone === "bullish" ||
      (strongConviction && riskLevel === "low" && !sellerFlow) ||
      (regimeBull && buyerFlow && !sellerFlow));
  const bearishSetup =
    !bullishSetup &&
    !incompleteRead &&
    !directionalSellBlocked &&
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

  if (incompleteRead) {
    const technicalRead = regimeBear
      ? (isEnglish ? "the chart currently has a bearish technical structure" : "o gráfico está com estrutura técnica de baixa")
      : regimeBull
        ? (isEnglish ? "the chart currently has a bullish technical structure" : "o gráfico está com estrutura técnica de alta")
        : (isEnglish ? "the chart has no confirmed directional structure" : "o gráfico ainda não tem estrutura direcional confirmada");
    const evidenceLines = [regimeLine, chartSignalLine, rsiLine, dailyVolumeLine]
      .filter((line) => line && !/unavailable|indispon[ií]vel|sem leitura/.test(normalizeUiText(line)))
      .slice(0, 4);
    return isEnglish
      ? [
          {
            title: standardTitles.scenario,
            body: `${assetLabel}: ${technicalRead}. The operational authorization remains blocked because Master Score, institutional flow and operational liquidity are not all confirmed.`,
          },
          {
            title: standardTitles.directive,
            items: [
              ...evidenceLines,
              "Treat the chart direction as technical context, not as permission to execute.",
              "Wait for a Decision Envelope with the required components confirmed before evaluating an entry.",
            ],
          },
          {
            title: standardTitles.between,
            items: [
              regimeBull ? "The bullish chart bias does not authorize a buy without Master Score, flow and liquidity." : "Buy remains blocked without Master Score, flow and liquidity confirmation.",
              regimeBear ? "The bearish chart bias does not authorize a sell/short without Master Score, flow and liquidity." : "Sell/short remains blocked without Master Score, flow and liquidity confirmation.",
              "The daily volume ratio is informational and must not be treated as comparable intraday RVOL.",
            ],
          },
          {
            title: standardTitles.interpretation,
            body: `WAIT is an authorization state, not a neutral trend classification. ${sentenceCaseFirst(technicalRead, locale)}, but the missing operational components prevent a validated trade.`,
          },
          {
            title: standardTitles.focus,
            body: focusText || "Keep the chart bias as context and do not execute until the central decision is READY.",
          },
        ]
      : [
          {
            title: standardTitles.scenario,
            body: `${assetLabel}: ${technicalRead}. A autorização operacional permanece bloqueada porque Score Mestre, fluxo institucional e liquidez operacional não estão todos confirmados.`,
          },
          {
            title: standardTitles.directive,
            items: [
              ...evidenceLines,
              "Tratar a direção do gráfico como contexto técnico, não como autorização de execução.",
              "Aguardar um Decision Envelope com os componentes obrigatórios confirmados antes de avaliar entrada.",
            ],
          },
          {
            title: standardTitles.between,
            items: [
              regimeBull ? "O viés de alta do gráfico não autoriza compra sem Score Mestre, fluxo e liquidez." : "Compra permanece bloqueada sem confirmação de Score Mestre, fluxo e liquidez.",
              regimeBear ? "O viés de baixa do gráfico não autoriza venda/short sem Score Mestre, fluxo e liquidez." : "Venda/short permanece bloqueada sem confirmação de Score Mestre, fluxo e liquidez.",
              "A razão volume atual/média diária é informativa e não deve ser tratada como RVOL intraday comparável.",
            ],
          },
          {
            title: standardTitles.interpretation,
            body: `AGUARDAR é um estado de autorização, não uma classificação de tendência neutra. ${sentenceCaseFirst(technicalRead, locale)}, mas os componentes operacionais ausentes impedem um trade validado.`,
          },
          {
            title: standardTitles.focus,
            body: focusText || "Manter o viés do gráfico como contexto e não executar até a decisão central ficar READY.",
          },
        ];
  }

  const scenarioBody = (() => {
    if (isEnglish) {
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

function textHasBuySide(value: string) {
  return /\b(compra|comprar|comprado|compradora|compradores|alta|comprador|buy|buyer|buyers|long|bullish)\b/i.test(value);
}

function textHasSellSide(value: string) {
  return /\b(venda|vender|vendido|vendedora|vendedores|baixa|queda|vendedor|short|sell|seller|sellers|bearish)\b/i.test(value);
}

function textHasStandAsideSide(value: string) {
  return /\b(ficar de fora|nenhum lado operacional|nenhum lado tem|sem nova opera[cç][aã]o|preservar capital primeiro|reduzir exposi[cç][aã]o|aguardar (a )?decis[aã]o dominante|evitar entradas agressivas|stand aside|no operational side|no new trade|no side has|reduce exposure|waiting is the dominant decision|avoid aggressive entries)\b/i.test(value);
}

function tradeAlignedFallback(side: "buy" | "sell" | "wait" | "exit", locale: AppLocale) {
  if (side === "buy") {
    return locale === "en-US"
      ? "Keep the buy read only with confirmation; if it fails, return to Wait."
      : "Manter a leitura de compra somente com confirmação; se falhar, voltar para Aguardar.";
  }
  if (side === "exit") {
    return locale === "en-US"
      ? "Prioritize position protection: reduce exposure and wait for a clear trigger before any new execution."
      : "Priorizar proteção da posição: reduzir exposição e aguardar gatilho claro antes de qualquer nova execução.";
  }
  if (side === "wait") {
    return locale === "en-US"
      ? "Mixed scenario: wait for price, volume and flow to align before choosing a side."
      : "Cenário misto: aguardar preço, volume e fluxo alinharem antes de escolher um lado.";
  }
  return locale === "en-US"
    ? "Keep the sell read only with confirmation; if it fails, return to Wait."
    : "Manter a leitura de venda somente com confirmação; se falhar, voltar para Aguardar.";
}

function sectionTitleFallback(side: "buy" | "sell" | "wait" | "exit", locale: AppLocale) {
  if (side === "exit") return locale === "en-US" ? "Position protection" : "Proteção da posição";
  if (side === "wait") return locale === "en-US" ? "Wait for confirmation" : "Aguardar confirmação";
  return side === "buy"
    ? (locale === "en-US" ? "Buy confirmation" : "Confirmação da compra")
    : (locale === "en-US" ? "Sell confirmation" : "Confirmação da venda");
}

function positionProtectionSections(locale: AppLocale): NonNullable<StrategicConclusion["sections"]> {
  if (locale === "en-US") {
    return [
      {
        title: "Current Scenario",
        body: "The final decision is to close or protect the current exposure. Do not open a new directional trade until price, volume and flow confirm again.",
      },
      {
        title: "Strategic Directive",
        items: [
          "Reduce exposure and protect capital first.",
          "Wait for a clean 5-minute trigger before any new execution.",
          "Keep invalidation objective around the protection level.",
        ],
      },
      {
        title: "Between Buy And Sell",
        items: [
          "No new side has priority while the decision is protection.",
          "The next trade only becomes valid after price, volume and flow align.",
          "Avoid changing from protection to aggression without a fresh confirmed snapshot.",
        ],
      },
      {
        title: "Interpretation",
        body: "Score and risk can remain useful context, but the active action is defensive: protect, reduce exposure and wait for confirmation.",
      },
      {
        title: "Focus now",
        body: "Preserve capital and wait for the next confirmed structure before acting again.",
      },
    ];
  }
  return [
    {
      title: "Cenário Atual",
      body: "A decisão final é encerrar ou proteger a exposição atual. Não abrir nova operação direcional até preço, volume e fluxo confirmarem de novo.",
    },
    {
      title: "Direção da Estratégia",
      items: [
        "Reduzir exposição e proteger capital primeiro.",
        "Aguardar gatilho limpo de 5 minutos antes de qualquer nova execução.",
        "Manter invalidação objetiva perto do nível de proteção.",
      ],
    },
    {
      title: "Entre Venda e Compra",
      items: [
        "Nenhum lado novo tem prioridade enquanto a decisão for proteção.",
        "A próxima operação só fica válida depois que preço, volume e fluxo alinharem.",
        "Evitar trocar proteção por agressividade sem novo snapshot confirmado.",
      ],
    },
    {
      title: "Interpretação",
      body: "Score e risco podem seguir como contexto, mas a ação ativa é defensiva: proteger, reduzir exposição e aguardar confirmação.",
    },
    {
      title: "Foco Agora",
      body: "Preservar capital e aguardar a próxima estrutura confirmada antes de agir de novo.",
    },
  ];
}

function noDataStrategicSections(locale: AppLocale, symbol: string, focus?: string | null): NonNullable<StrategicConclusion["sections"]> {
  const isEnglish = locale === "en-US";
  const assetLabel = normalizeSymbol(symbol) || (isEnglish ? "the asset" : "o ativo");
  const normalizedFocus = sentenceCaseFirst(String(focus || "").trim(), locale);

  if (isEnglish) {
    return [
      {
        title: "Real data pending",
        body: `${assetLabel}: there is not enough real data for an operational analysis of this asset.`,
      },
      {
        title: "Missing fields",
        items: [
          "price",
          "variation",
          "volume",
          "RSI",
          "Bias",
          "Master Score",
        ],
      },
      {
        title: "Next action",
        body: normalizedFocus || "Wait for a new provider quote/candle set or try refreshing again.",
      },
    ];
  }

  return [
    {
      title: "Dados reais pendentes",
      body: `${assetLabel}: ainda não há dados reais suficientes para análise operacional deste ativo.`,
    },
    {
      title: "Campos faltantes",
      items: [
        "preço",
        "variação",
        "volume",
        "RSI",
        "Bias",
        "Score Mestre",
      ],
    },
    {
      title: "Próxima ação",
      body: normalizedFocus || "Aguardar nova cotação/candles do provider ou tentar atualizar novamente.",
    },
  ];
}

function alignTextWithTradeSide(value: string, side: "buy" | "sell" | "wait" | "exit", locale: AppLocale) {
  if (side === "exit") {
    const conflicts = textHasBuySide(value) || textHasSellSide(value);
    return conflicts ? tradeAlignedFallback(side, locale) : value;
  }
  if (side === "wait") {
    const conflicts = textHasBuySide(value) && textHasSellSide(value);
    return conflicts ? tradeAlignedFallback(side, locale) : value;
  }
  const conflicts = side === "buy"
    ? textHasSellSide(value) || textHasStandAsideSide(value)
    : textHasBuySide(value) || textHasStandAsideSide(value);
  return conflicts ? tradeAlignedFallback(side, locale) : value;
}

function alignStrategicSectionsWithTrade(
  sections: StrategicConclusion["sections"],
  action: string,
  locale: AppLocale,
) {
  const side = tradeActionSide(action);
  if (!sections?.length) return sections || [];
  if (side === "exit") return positionProtectionSections(locale);
  if (side !== "buy" && side !== "sell" && side !== "wait") return sections || [];
  const alignedTitle = side === "buy"
    ? (locale === "en-US" ? "Buy confirmation" : "Confirmação da compra")
    : side === "sell"
      ? (locale === "en-US" ? "Sell confirmation" : "Confirmação da venda")
      : sectionTitleFallback(side, locale);
  return sections.map((section) => {
    const titleHasConflict = side === "buy"
      ? textHasSellSide(section.title)
      : side === "sell"
        ? textHasBuySide(section.title)
        : false;
    return {
      ...section,
      title: titleHasConflict ? alignedTitle : section.title,
      body: section.body ? alignTextWithTradeSide(section.body, side, locale) : section.body,
      items: section.items?.map((item) => alignTextWithTradeSide(item, side, locale)),
    };
  });
}

function alignStrategicBasisWithTrade(items: string[], action: string, locale: AppLocale) {
  const side = tradeActionSide(action);
  if (side !== "buy" && side !== "sell") return items || [];
  return (items || []).map((item) => alignTextWithTradeSide(item, side, locale));
}

function alignOperationalDecisionWithTrade(decision: OperationalDecision, locale: AppLocale): OperationalDecision {
  // A canonical no-data decision passes through untouched. Rewriting its action
  // is exactly what used to demote no_data back to a plain "wait".
  if (shouldSkipTradeAlignment(decision.reasonCode)) return decision;
  const side = tradeActionSide(decision.action);
  const combined = [
    decision.action,
    decision.bias,
    decision.risk,
    ...(decision.reasons || []),
    ...(decision.levels || []).flatMap((level) => [level.label, level.value]),
  ].join(" ");
  const mixed = textHasBuySide(combined) && textHasSellSide(combined);
  if (side === "wait" && mixed) {
    return {
      ...decision,
      action: locale === "en-US" ? "WAIT FOR CONFIRMATION" : "AGUARDAR CONFIRMAÇÃO",
      tone: "watch",
      reasons: locale === "en-US"
        ? ["Mixed scenario: buy and sell arguments conflict", "Wait for price, volume and flow to align"]
        : ["Cenário misto: compra e venda entram em conflito", "Aguardar preço, volume e fluxo alinharem"],
    };
  }
  if (side !== "buy" && side !== "sell") return decision;
  return {
    ...decision,
    reasons: decision.reasons.map((reason) => alignTextWithTradeSide(reason, side, locale)),
    levels: decision.levels.map((level) => ({
      ...level,
      label: alignTextWithTradeSide(level.label, side, locale),
      value: alignTextWithTradeSide(level.value, side, locale),
    })),
  };
}

function decisionCardByLabel(cards: EssentialDecisionCard[], pattern: RegExp) {
  return cards.find((card) => pattern.test(normalizeUiText(card.label)));
}

/**
 * Canonical Master Score card lookup. Matched by label first — the score gate is
 * a documented contract (ESSENTIAL_ANALYSIS_FIELD_IDS), not an accident of card
 * order. The positional fallback only covers legacy card builders.
 */
function scoreDecisionCard(cards: EssentialDecisionCard[]) {
  return decisionCardByLabel(cards, /score mestre|master score/) || cards[0];
}

function decisionSideFromCards(cards: EssentialDecisionCard[], fallbackAction: string): StrategicDecisionSide {
  const tradeCard =
    decisionCardByLabel(cards, /trade sugerido|suggested trade|acao recomendada|recommended action/) ||
    cards[2];
  const fromTrade = tradeActionSide(tradeCard?.value);
  if (fromTrade === "buy" || fromTrade === "sell" || fromTrade === "exit") return fromTrade;
  const fromAction = tradeActionSide(fallbackAction);
  if (fromAction === "buy" || fromAction === "sell" || fromAction === "exit") return fromAction;
  return "wait";
}

function strategicDecisionLabels(side: StrategicDecisionSide, locale: AppLocale) {
  const isEnglish = locale === "en-US";
  if (side === "no_data") {
    return {
      decisionNow: noDataDecisionCopy(locale),
      tradeSuggested: isEnglish ? "Wait" : "Aguardar",
      direction: isEnglish ? "Range" : "Lateral",
      regime: isEnglish ? "Monitoring" : "Monitorando",
      bias: isEnglish ? "Monitoring" : "Monitorando",
      tone: "watch" as DecisionTone,
    };
  }
  if (side === "buy") {
    return {
      decisionNow: isEnglish ? "BUY WITH CONFIRMATION" : "COMPRA COM CONFIRMAÇÃO",
      tradeSuggested: isEnglish ? "Buy/Long" : "Compra",
      direction: isEnglish ? "Up" : "Alta",
      regime: isEnglish ? "Up" : "Alta",
      bias: isEnglish ? "Up" : "Alta",
      tone: "bullish" as DecisionTone,
    };
  }
  if (side === "sell") {
    return {
      decisionNow: isEnglish ? "WAIT FOR SELL/SHORT CONFIRMATION" : "AGUARDAR VENDA / SHORT COM CONFIRMAÇÃO",
      tradeSuggested: isEnglish ? "Sell/Short" : "Venda / Short",
      direction: isEnglish ? "Down" : "Baixa",
      regime: isEnglish ? "Down" : "Baixa",
      bias: isEnglish ? "Down" : "Baixa",
      tone: "bearish" as DecisionTone,
    };
  }
  if (side === "exit") {
    return {
      decisionNow: isEnglish ? "CLOSE / PROTECT POSITION" : "ENCERRAR / PROTEGER POSIÇÃO",
      tradeSuggested: isEnglish ? "Close position" : "Encerrar posição",
      direction: isEnglish ? "Exit" : "Saída",
      regime: isEnglish ? "Protection" : "Proteção",
      bias: isEnglish ? "Defensive" : "Defensivo",
      tone: "exit" as DecisionTone,
    };
  }
  return {
    decisionNow: isEnglish ? "WAIT FOR CONFIRMATION" : "AGUARDAR CONFIRMAÇÃO",
    tradeSuggested: isEnglish ? "Wait" : "Aguardar",
    direction: isEnglish ? "Range" : "Lateral",
    regime: isEnglish ? "Neutral" : "Neutro",
    bias: isEnglish ? "Neutral" : "Neutro",
    tone: "watch" as DecisionTone,
  };
}

function strategicDecisionSections(
  side: StrategicDecisionSide,
  locale: AppLocale,
  symbol: string,
): NonNullable<StrategicConclusion["sections"]> {
  const isEnglish = locale === "en-US";
  const assetLabel = normalizeSymbol(symbol) || (isEnglish ? "the asset" : "o ativo");

  if (side === "no_data") return noDataStrategicSections(locale, symbol);

  if (isEnglish) {
    if (side === "buy") {
      return [
        { title: "Current Scenario", body: `${assetLabel}: controlled long thesis. Execution is valid only after a clean price trigger, real volume and confirmed flow.` },
        { title: "Strategic Directive", items: ["Use the Master Score as strength context.", "Act only after price confirms the trigger.", "Keep invalidation objective below the defended structure."] },
        { title: "Buy Confirmation", items: ["Long execution needs a defended pullback or clean breakout.", "Volume must support the entry candle.", "If the trigger fails, return to Wait."] },
        { title: "Interpretation", body: "The final read is constructive, but the panel is not authorizing anticipation. Confirmation comes first." },
        { title: "Focus now", body: "Wait for the buyer trigger, confirm volume, then execute with defined invalidation." },
      ];
    }
    if (side === "sell") {
      return [
        { title: "Current Scenario", body: `${assetLabel}: downside thesis is active, but execution needs a clear trigger. The panel is not authorizing late action.` },
        { title: "Strategic Directive", items: ["Plan short-side execution only after support failure or resistance rejection.", "Require price, volume and flow confirmation.", "Keep invalidation tight and objective."] },
        { title: "Sell Confirmation", items: ["The sell/short side has priority only with confirmation.", "Avoid late execution into support.", "If the trigger fails, return to Wait."] },
        { title: "Interpretation", body: "The final read is bearish. Action is conditional: sell/short only after the chart confirms the downside trigger." },
        { title: "Focus now", body: "Wait for support loss, resistance rejection or seller flow confirmation before any sell/short execution." },
      ];
    }
    if (side === "exit") {
      return [
        { title: "Current Scenario", body: `${assetLabel}: the active decision is protection of the current exposure.` },
        { title: "Strategic Directive", items: ["Reduce exposure first.", "Keep capital protection as the priority.", "Wait for a fresh confirmed snapshot before acting again."] },
        { title: "Position Protection", items: ["No additional execution while protection is the active decision.", "Use the next confirmed structure to reassess.", "Keep risk limits objective."] },
        { title: "Interpretation", body: "The final read is defensive. The correct action is to protect exposure and wait for a new confirmed setup." },
        { title: "Focus now", body: "Protect capital and reassess only after the next confirmed structure." },
      ];
    }
    return [
      { title: "Current Scenario", body: `${assetLabel}: mixed read. The panel is waiting for price, volume and flow to align.` },
      { title: "Strategic Directive", items: ["Do not anticipate execution.", "Wait for the next confirmed 5-minute structure.", "Use price and volume as context until a clean trigger appears."] },
      { title: "Wait For Confirmation", items: ["No operational side has enough confirmation yet.", "The next trigger must be confirmed by price and volume.", "If signals stay mixed, the correct action remains Wait."] },
      { title: "Interpretation", body: "The final read is neutral. The panel is intentionally blocking directional execution until confirmation improves." },
      { title: "Focus now", body: "Wait for price, volume and flow to align before choosing a side." },
    ];
  }

  if (side === "buy") {
    return [
      { title: "Cenário Atual", body: `${assetLabel}: tese compradora controlada. A execução só fica válida depois de gatilho limpo no preço, volume real e fluxo confirmado.` },
      { title: "Direção da Estratégia", items: ["Usar o Score Mestre como contexto de força.", "Agir apenas depois de confirmação clara no preço.", "Manter invalidação objetiva abaixo da estrutura defendida."] },
      { title: "Confirmação da compra", items: ["A execução compradora precisa de pullback defendido ou rompimento limpo.", "O volume precisa sustentar a vela de entrada.", "Se o gatilho falhar, voltar para Aguardar."] },
      { title: "Interpretação", body: "A leitura final é construtiva, mas o painel não autoriza antecipação. Confirmação vem primeiro." },
      { title: "Foco Agora", body: "Aguardar gatilho comprador, confirmar volume e executar com invalidação definida." },
    ];
  }
  if (side === "sell") {
    return [
      { title: "Cenário Atual", body: `${assetLabel}: tese vendedora ativa, mas a execução precisa de gatilho claro. O painel não autoriza atuação atrasada.` },
      { title: "Direção da Estratégia", items: ["Planejar venda/short apenas após perda de suporte ou rejeição em resistência.", "Exigir confirmação de preço, volume e fluxo.", "Manter invalidação curta e objetiva."] },
      { title: "Confirmação da venda", items: ["Venda/short tem prioridade somente com confirmação.", "Evitar execução atrasada em cima do suporte.", "Se o gatilho falhar, voltar para Aguardar."] },
      { title: "Interpretação", body: "A leitura final é baixista. A ação é condicional: venda/short apenas depois que o gráfico confirmar o gatilho vendedor." },
      { title: "Foco Agora", body: "Aguardar perda de suporte, rejeição em resistência ou confirmação de fluxo vendedor antes de qualquer venda/short." },
    ];
  }
  if (side === "exit") {
    return [
      { title: "Cenário Atual", body: `${assetLabel}: a decisão ativa é proteger a exposição atual.` },
      { title: "Direção da Estratégia", items: ["Reduzir exposição primeiro.", "Manter proteção de capital como prioridade.", "Aguardar novo snapshot confirmado antes de agir novamente."] },
      { title: "Proteção da posição", items: ["Sem execução adicional enquanto proteção for a decisão ativa.", "Usar a próxima estrutura confirmada para reavaliar.", "Manter limites de risco objetivos."] },
      { title: "Interpretação", body: "A leitura final é defensiva. A ação correta é proteger exposição e aguardar novo setup confirmado." },
      { title: "Foco Agora", body: "Proteger capital e reavaliar apenas depois da próxima estrutura confirmada." },
    ];
  }
  return [
    { title: "Cenário Atual", body: `${assetLabel}: leitura mista. O painel aguarda preço, volume e fluxo alinharem.` },
    { title: "Direção da Estratégia", items: ["Não antecipar execução.", "Aguardar a próxima estrutura de 5 minutos confirmada.", "Usar preço e volume como contexto até aparecer gatilho limpo."] },
    { title: "Aguardar confirmação", items: ["Nenhum lado operacional tem confirmação suficiente ainda.", "O próximo gatilho precisa ser confirmado por preço e volume.", "Se os sinais continuarem mistos, a ação correta permanece Aguardar."] },
    { title: "Interpretação", body: "A leitura final é neutra. O painel bloqueia execução direcional até a confirmação melhorar." },
    { title: "Foco Agora", body: "Aguardar preço, volume e fluxo alinharem antes de escolher um lado." },
  ];
}

function symbolContextStrategicSections(
  view: SymbolOperationalView,
  locale: AppLocale,
  symbol: string,
): NonNullable<StrategicConclusion["sections"]> {
  const isEnglish = locale === "en-US";
  const technical = view.technical_context;
  const operational = view.operational_context;
  const asset = normalizeSymbol(symbol) || (isEnglish ? "the asset" : "o ativo");
  const biasValue = String(currentTechnicalBias(technical.technical_bias) || "MIXED").toUpperCase();
  const bias = biasValue === "BULLISH" ? (isEnglish ? "bullish" : "comprador") : biasValue === "BEARISH" ? (isEnglish ? "bearish" : "vendedor") : (isEnglish ? "mixed" : "misto");
  const trendStatus = String(technical.trend_d1?.freshness_status || technical.trend_d1?.status || "").toUpperCase();
  const trendReading = technical.trend_d1?.value != null ? contextDirectionLabel(technical.trend_d1.value, locale) : (isEnglish ? "unavailable" : "indisponível");
  const trendReadingDate = formatMarketSessionTime(String(technical.trend_d1?.data_as_of || technical.trend_d1?.as_of || "").slice(0, 10), locale);
  const trend = trendStatus === "STALE" ? (isEnglish ? "Outdated" : "Desatualizada") : trendReading;
  const trendFreshness = trendStatus === "STALE"
    ? `${isEnglish ? "Last reading" : "Última leitura"}: ${trendReading}${trendReadingDate ? ` — ${trendReadingDate}` : ""}`
    : dailyFreshnessMeta(technical.trend_d1, view.session_date, locale);
  const intraday = technical.intraday_direction_5m?.status === "READY" ? contextDirectionLabel(technical.intraday_direction_5m.value, locale) : (isEnglish ? "unavailable" : "indisponível");
  const flow = technical.institutional_flow?.status === "READY"
    ? `${technical.institutional_flow.label || "—"}${technical.institutional_flow.value != null ? ` ${Number(technical.institutional_flow.value).toFixed(1)}` : ""}`
    : (isEnglish ? "unavailable" : "indisponível");
  const labels: Record<string, string> = {
    intraday_rvol: isEnglish ? "comparable intraday RVOL" : "RVOL intraday comparável",
    rvol: isEnglish ? "comparable intraday RVOL" : "RVOL intraday comparável",
    flow: isEnglish ? "institutional flow" : "fluxo institucional",
    liquidity: isEnglish ? "validated liquidity" : "liquidez validada",
    levels: isEnglish ? "valid operational levels" : "níveis operacionais válidos",
  };
  const blocks = (view.operational_blocks || []).map((item) => labels[item.component] || item.component);
  const joinedBlocks = blocks.length < 2 ? blocks[0] : `${blocks.slice(0, -1).join(", ")} ${isEnglish ? "and" : "e"} ${blocks[blocks.length - 1]}`;
  const sentimentUnavailable = operational.sentiment?.status !== "READY";
  const scenario = trendStatus === "STALE"
    ? (isEnglish ? `${asset}: ${bias} intraday context; D1 trend awaiting update.` : `${asset}: contexto intraday ${bias}; tendência D1 aguardando atualização.`)
    : (isEnglish
      ? `${asset}: ${bias} technical context. D1 trend, 5m direction and institutional flow remain separate from trade authorization.`
      : `${asset}: contexto técnico ${bias}. Tendência D1, direção intraday 5m e fluxo institucional permanecem separados da autorização operacional.`);
  const blockSentence = blocks.length
    ? (isEnglish ? `Execution remains blocked because ${joinedBlocks} ${blocks.length === 1 ? "is" : "are"} unavailable.` : `A execução permanece bloqueada porque ${joinedBlocks} ${blocks.length === 1 ? "está indisponível" : "estão indisponíveis"}.`)
    : (isEnglish ? "The required operational components are confirmed." : "Os componentes operacionais obrigatórios estão confirmados.");
  const sentimentSentence = sentimentUnavailable
    ? (isEnglish ? "Current sentiment also has insufficient data and is not used as a directional signal." : "O sentimento atual também não possui dados suficientes e não é usado como sinal direcional.")
    : (isEnglish ? "Current sentiment is confirmed." : "O sentimento atual está confirmado.");
  return [
    { title: isEnglish ? "Current Scenario" : "Cenário Atual", body: scenario },
    { title: isEnglish ? "Strategic Direction" : "Direção da Estratégia", items: [
      `${isEnglish ? "Structural trend D1" : "Tendência estrutural D1"}: ${trend}${trendFreshness ? ` · ${trendFreshness}` : ""}`,
      `${isEnglish ? "Operational direction 5m" : "Direção operacional 5m"}: ${intraday}`,
      `${isEnglish ? "Institutional flow 5m" : "Fluxo institucional 5m"}: ${flow}`,
    ] },
    { title: isEnglish ? "Wait for confirmation" : "Aguardar confirmação", items: [blockSentence, sentimentSentence] },
    { title: isEnglish ? "Interpretation" : "Interpretação", body: isEnglish
      ? `The technical read is ${bias}; WAIT is an authorization state, not a neutral trend classification.`
      : `A leitura técnica é ${bias}; AGUARDAR é um estado de autorização, não uma classificação de tendência neutra.` },
    { title: isEnglish ? "Focus now" : "Foco Agora", body: blocks.length
      ? (isEnglish ? `Preserve the ${bias} context and wait only for ${joinedBlocks}.` : `Preservar o contexto ${bias} e aguardar somente ${joinedBlocks}.`)
      : (isEnglish ? "Use the confirmed context with objective risk limits." : "Usar o contexto confirmado com limites objetivos de risco.") },
  ];
}

function symbolContextStrategicBasis(view: SymbolOperationalView, locale: AppLocale) {
  const isEnglish = locale === "en-US";
  const technical = view.technical_context;
  const operational = view.operational_context;
  const score = operational.master_score;
  const scoreStatus = String(score?.status || "").toUpperCase();
  const dailyRatio = firstFiniteNumber(operational.volume_vs_daily_average?.ratio);
  const scoreValue = firstFiniteNumber(score?.value);
  const used = score?.used_components?.length || 0;
  const total = used + (score?.missing_components?.length || 0);
  const trendStatus = String(technical.trend_d1?.freshness_status || technical.trend_d1?.status || "").toUpperCase();
  const trendReading = technical.trend_d1?.value != null ? contextDirectionLabel(technical.trend_d1.value, locale) : (isEnglish ? "unavailable" : "indisponível");
  const trendReadingDate = formatMarketSessionTime(String(technical.trend_d1?.data_as_of || technical.trend_d1?.as_of || "").slice(0, 10), locale);
  const trend = trendStatus === "STALE"
    ? `${isEnglish ? "Outdated" : "Desatualizada"} — ${isEnglish ? "last reading" : "última leitura"}: ${trendReading}${trendReadingDate ? ` — ${trendReadingDate}` : ""}`
    : trendReading;
  const directionStatus = String(technical.intraday_direction_5m?.status || "").toUpperCase();
  const flowStatus = String(technical.institutional_flow?.status || "").toUpperCase();
  const isPending = (status: string) => ["PENDING", "REFRESHING", "QUEUED", "RUNNING"].includes(status);
  const formatBasisNumber = (value: number, digits: number) => value.toLocaleString(isEnglish ? "en-US" : "pt-BR", { minimumFractionDigits: digits, maximumFractionDigits: digits });
  return [
    `${isEnglish ? "Technical bias" : "Viés técnico"}: ${technical.technical_bias?.label || technical.technical_bias?.value || "—"}`,
    `${isEnglish ? "D1 trend" : "Tendência D1"}: ${trend}`,
    `${isEnglish ? "Direction 5m" : "Direção 5m"}: ${directionStatus === "READY" ? contextDirectionLabel(technical.intraday_direction_5m?.value, locale) : isPending(directionStatus) ? (isEnglish ? "calculating" : "calculando") : (isEnglish ? "unavailable" : "indisponível")}`,
    `${isEnglish ? "Flow 5m" : "Fluxo 5m"}: ${flowStatus === "READY" ? `${technical.institutional_flow?.label} ${formatBasisNumber(Number(technical.institutional_flow?.value), 1)}` : isPending(flowStatus) ? (isEnglish ? "calculating" : "calculando") : (isEnglish ? "unavailable" : "indisponível")}`,
    `${scoreStatus === "PARTIAL" ? (isEnglish ? "Partial technical score" : "Score técnico parcial") : (score?.label || "Score")}: ${scoreValue != null ? `${formatBasisNumber(scoreValue, 1)}/10` : "—"}${scoreStatus === "PARTIAL" && total ? ` — ${isEnglish ? `${used} of ${total} components` : `${used} de ${total} componentes`}` : ""}`,
    `${isEnglish ? "Current volume / daily average" : "Volume atual / média diária"}: ${dailyRatio != null ? `${formatBasisNumber(dailyRatio, 2)}×` : (isEnglish ? "unavailable" : "indisponível")} · ${isEnglish ? "informational" : "informativo"}`,
  ];
}

function strategicDecisionBasis(contract: Pick<StrategicDecisionContract, "bias" | "risk" | "tradeSuggested" | "decisionNow">, locale: AppLocale) {
  if (locale === "en-US") {
    return [
      `Final decision: ${contract.decisionNow}`,
      `Suggested trade: ${contract.tradeSuggested}`,
      `Bias: ${contract.bias}`,
      `Risk: ${contract.risk}`,
    ];
  }
  return [
    `Decisão final: ${contract.decisionNow}`,
    `Trade sugerido: ${contract.tradeSuggested}`,
    `Viés: ${contract.bias}`,
    `Risco: ${contract.risk}`,
  ];
}

function buildStrategicDecisionContract(input: {
  locale: AppLocale;
  symbol: string;
  cards: EssentialDecisionCard[];
  conclusion: StrategicConclusion;
  operationalDecision: OperationalDecision;
  hasCoreData: boolean;
  executionReady?: boolean;
  pendingComponents?: string[];
  symbolContext?: SymbolOperationalView | null;
}): StrategicDecisionContract {
  // Canonical priority: no_data > wait > cards. Never derived from localized copy.
  const side = resolveStrategicSide({
    reasonCode: input.operationalDecision.reasonCode,
    hasCoreData: input.hasCoreData,
    executionReady: input.executionReady,
    resolveSide: () => decisionSideFromCards(input.cards, input.operationalDecision.action),
  });
  const labels = strategicDecisionLabels(side, input.locale);
  const contextTechnicalBias = currentTechnicalBias(input.symbolContext?.technical_context.technical_bias);
  const contextBias = contextTechnicalBias != null
    ? contextDirectionLabel(contextTechnicalBias, input.locale)
    : input.cards.find((card) => /tendencia d1|d1 trend/.test(normalizeUiText(card.label)))?.value;
  const risk = input.operationalDecision.risk || (input.locale === "en-US" ? "No read" : "Sem leitura");
  const reasons = (() => {
    if (side === "no_data") {
      return input.locale === "en-US"
        ? ["Price, volume or Master Score are not complete", "Operational trade remains blocked", "Wait for the next confirmed snapshot"]
        : ["Preço, volume ou Score Mestre ainda não estão completos", "Trade operacional permanece bloqueado", "Aguardar o próximo snapshot confirmado"];
    }
    if (input.symbolContext) return input.operationalDecision.reasons;
    if (input.executionReady === false) {
      const pending = input.pendingComponents || [];
      const listed = pending.length < 2 ? pending[0] : `${pending.slice(0, -1).join(", ")} e ${pending[pending.length - 1]}`;
      return input.locale === "en-US"
        ? ["Technical context remains visible", `Execution blocked: ${listed || "required components"} not confirmed`]
        : ["Contexto técnico permanece visível", `Execução bloqueada: ${listed || "componentes obrigatórios"} ainda não confirmados.`];
    }
    if (side === "buy") {
      return input.locale === "en-US"
        ? ["Buy thesis is active only with confirmation", "Price and volume must validate the trigger", "Risk stays controlled by objective invalidation"]
        : ["Tese compradora ativa somente com confirmação", "Preço e volume precisam validar o gatilho", "Risco segue controlado por invalidação objetiva"];
    }
    if (side === "sell") {
      return input.locale === "en-US"
        ? ["Bearish bias is active only with confirmation", "Price and volume must validate the sell/short trigger", "Invalidation stays objective above the failed level"]
        : ["Viés vendedor ativo somente com confirmação", "Preço e volume precisam validar o gatilho de venda/short", "Invalidação segue objetiva acima do nível que falhar"];
    }
    if (side === "exit") {
      return input.locale === "en-US"
        ? ["Protection is the active decision", "Reduce exposure before reassessing", "Wait for a fresh confirmed structure"]
        : ["Proteção é a decisão ativa", "Reduzir exposição antes de reavaliar", "Aguardar nova estrutura confirmada"];
    }
    return input.locale === "en-US"
      ? ["No side has enough confirmation", "Price, volume and flow must align", "Waiting is the professional decision now"]
      : ["Nenhum lado tem confirmação suficiente", "Preço, volume e fluxo precisam alinhar", "Aguardar é a decisão profissional agora"];
  })();

  const levelsPending = (input.pendingComponents || []).some((component) => /níveis operacionais|operational levels/i.test(component));
  const levels = levelsPending ? [] : input.operationalDecision.levels.map((level) => ({
    ...level,
    value: alignTextWithTradeSide(level.value, side === "no_data" ? "wait" : side, input.locale),
  }));
  const contract = {
    side,
    tone: labels.tone,
    decisionNow: labels.decisionNow,
    tradeSuggested: labels.tradeSuggested,
    direction: input.symbolContext ? (contextBias || labels.direction) : input.executionReady === false ? (input.cards.find((card) => /direcao provavel|likely direction|tendencia d1|d1 trend/.test(normalizeUiText(card.label)))?.value || labels.direction) : labels.direction,
    regime: input.symbolContext ? (contextBias || labels.regime) : input.executionReady === false ? (input.cards.find((card) => /regime/.test(normalizeUiText(card.label)))?.value || labels.regime) : labels.regime,
    bias: input.symbolContext ? (contextBias || labels.bias) : input.executionReady === false ? (input.cards.find((card) => /direcao provavel|likely direction|tendencia d1|d1 trend/.test(normalizeUiText(card.label)))?.value || labels.bias) : labels.bias,
    risk,
    confidence: input.executionReady === false ? null : input.operationalDecision.confidence,
    confidenceLabel: input.executionReady === false ? (input.locale === "en-US" ? "Not confirmed" : "Não confirmada") : input.operationalDecision.confidenceLabel,
    reasons,
    levels,
    sections: input.symbolContext
      ? symbolContextStrategicSections(input.symbolContext, input.locale, input.symbol)
      : strategicSectionsForRender(input.conclusion, input.locale, input.symbol),
    basis: [] as string[],
  };
  return {
    ...contract,
    basis: input.symbolContext
      ? symbolContextStrategicBasis(input.symbolContext, input.locale)
      : input.conclusion.basis.length
        ? input.conclusion.basis
        : strategicDecisionBasis(contract, input.locale),
  };
}

function operationalDecisionFromStrategicContract(contract: StrategicDecisionContract): OperationalDecision {
  return {
    action: contract.decisionNow,
    tone: contract.tone,
    reasonCode: contract.side === "no_data" ? "NO_CORE_DATA" : null,
    confidence: contract.confidence,
    confidenceLabel: contract.confidenceLabel,
    bias: contract.bias,
    risk: contract.risk,
    reasons: contract.reasons,
    levels: contract.levels,
  };
}

function alignDecisionCardsWithStrategicContract(
  cards: EssentialDecisionCard[],
  contract: StrategicDecisionContract,
  locale: AppLocale,
) {
  const tone = contract.tone;
  return cards.map((card, index) => {
    const label = normalizeUiText(card.label);
    if (/direcao provavel|likely direction/.test(label)) {
      return { ...card, value: contract.direction, tone };
    }
    if (/trade sugerido|suggested trade|acao recomendada|recommended action/.test(label) || index === 2) {
      return { ...card, label: locale === "en-US" ? "Suggested Trade" : "Trade Sugerido", value: contract.tradeSuggested, tone };
    }
    if (/regime/.test(label)) {
      return { ...card, value: contract.regime, tone };
    }
    if (/risco|risk/.test(label)) {
      return { ...card, value: contract.risk, tone: strategicRiskLevelFromText(contract.risk) === "high" ? "bearish" : tone };
    }
    return card;
  });
}

function quoteFromMap(quotes: Record<string, QuotePayload>, symbol?: string | null) {
  const normalized = normalizeSymbol(String(symbol || ""));
  if (!normalized) return null;
  for (const alias of symbolAliases(symbol)) {
    const quote = quotes[alias] || quotes[normalizeSymbol(alias)];
    if (quote && quoteMatchesSymbol(quote, symbol)) return quote;
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
  const rvol = Number(item.rvol ?? deriveRelativeVolume(volume, (item as any)?.average_volume ?? (item as any)?.avg_volume));
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
    case "flow":
      return volumeScore * 2.6 + Math.max(0, rvol - 1) * 3.1 + absChange * 0.65 + score * 0.35 + institutionalCategoryBonus + diversityBonus * 0.45;
    case "liquidity":
      return stable * 3.2 + atr * 2.25 + rsiExtreme * 0.11 + Math.max(0, 2.2 - Math.abs(rvol - 1.2)) * 1.35 + score * 0.22 + liquidityCategoryBonus * 0.55 + diversityBonus * 1.9;
    case "trend":
      return adx * 0.24 + score * 0.62 + rsiExtreme * 0.08 + absChange * 1.1 + volumeScore * 0.25 + diversityBonus * 0.4;
    case "momentum":
      return absChange * 6.2 + Math.max(0, rvol - 1) * 3.4 + volumeScore * 0.65 + adx * 0.04 + (isCrypto ? -0.6 : 0.25) + diversityBonus * 0.75;
    case "smart-money":
      return score * 1.18 + stable * 1.9 + Math.max(0, rvol - 1) * 1.35 + adx * 0.05 + (mildBullish ? 1.6 : mildBearish ? 0.7 : 0) + smartMoneyCategoryBonus + diversityBonus * 0.6;
    case "risk":
      return score * 1.2 + rsiExtreme * 0.08 + Math.max(0, 1 - rvol) * 2.2 + diversityBonus * 0.25;
    case "news-ia":
    case "macro":
      return score * 0.7 + absChange * 0.8 + diversityBonus * 0.7;
    case "regime":
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
  const rvol = Number(input.rvol ?? deriveRelativeVolume(input.volume, (input as any)?.average_volume ?? (input as any)?.avg_volume));
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
    case "flow":
      return {
        volume_proxy: Number((volumeImpulse * 100).toFixed(1)),
        agressao_proxy: Number((Math.abs(change) * rvol * 8).toFixed(1)),
        rvol: Number(rvol.toFixed(2)),
        confirmacao_preco: bullish ? "deslocamento comprador" : bearish ? "pressao vendedora" : "neutro",
      };
    case "liquidity":
      return {
        liquidez: Number((volumeImpulse * 30 + atrPct * 9 + score * 5).toFixed(1)),
        sweep_risk: Number((atrPct * 12 + absChange * 8 + volumeImpulse * 9).toFixed(1)),
        zona_stop: bullish ? "acima da resistencia" : bearish ? "abaixo do suporte" : "bordas do range",
        atr_pct: Number(atrPct.toFixed(2)),
      };
    case "trend":
      return {
        tendencia: bullish ? "alta" : bearish ? "baixa" : "lateral",
        adx: Number(adx.toFixed(1)),
        rsi: Number(rsi.toFixed(1)),
        estrutura: adx >= 22 ? "direcional" : "indefinida",
      };
    case "momentum":
      return {
        aceleracao: Number((absChange * 10 + volumeImpulse * 20).toFixed(1)),
        momentum: Number((change * 1.4).toFixed(2)),
        rvol: Number(rvol.toFixed(2)),
        movimento_anormal: absChange >= 0.35 || rvol >= 1.4,
      };
    case "smart-money":
      return {
        posicionamento: Number((score * 8 + volumeImpulse * 12 + adx * 0.4).toFixed(1)),
        absorcao_proxy: Number((Math.max(0, 1.2 - absChange) * rvol * 20).toFixed(1)),
        adx: Number(adx.toFixed(1)),
        rvol: Number(rvol.toFixed(2)),
      };
    case "risk":
      return {
        risco: Number((score * 10).toFixed(1)),
        rvol: Number(rvol.toFixed(2)),
        dados: rvol > 0 ? "com volume" : "sem volume suficiente",
        decisao: "nao operar sem can_trade",
      };
    case "news-ia":
      return {
        relevancia: Number((score * 10).toFixed(1)),
        impacto: bullish ? "positivo" : bearish ? "negativo" : "neutro",
        provider: "snapshot",
        uso: "contexto",
      };
    case "macro":
      return {
        contexto_macro: "derivado do snapshot",
        score_contexto: Number((score * 10).toFixed(1)),
        quantitativo: false,
      };
    case "regime":
      return {
        regime: adx >= 22 ? (bullish ? "tendencia de alta" : bearish ? "tendencia de baixa" : "trend indefinido") : "lateral",
        adx: Number(adx.toFixed(1)),
        rsi: Number(rsi.toFixed(1)),
        volatilidade: Number(atrPct.toFixed(2)),
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
  const rvolValue = Number(input.rvol ?? deriveRelativeVolume(input.volume, (input as any)?.average_volume ?? (input as any)?.avg_volume));
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
  const isBearish = Number(input.changePct || 0) < 0 || String(input.trend || "").toLowerCase().includes("baixa");
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
    case "flow":
      return {
        ...base,
        state: input.volume && input.volume > 1_000_000 ? "fluxo relevante" : "fluxo em observação",
        ai_comment: `${input.symbol} em Fluxo IA: ${signature}; volume ${volumeText}, variação ${changeText}. Direção de fluxo: ${side}.`,
        trigger: `Executar ${side} só se RVOL sustentar ${rvolText} ou maior junto com deslocamento ${direction}.`,
        invalidation: `Desconsiderar se volume vier sem deslocamento, com pavio contra a tese ou absorção de ${oppositeSide}.`,
      };
    case "liquidity":
      return {
        ...base,
        state: "zonas e traps de liquidez",
        ai_comment: `${input.symbol} em Liquidez IA: ${signature}; use bordas do range para planejar ${side} só com reação confirmada.`,
        trigger: `Aguardar toque na zona, sweep ou trap confirmado com RVOL ${rvolText}; liquidez é alerta, não entrada automática.`,
        invalidation: `Zona perde força após rompimento limpo com volume ou ATR ${atrText} expandindo contra a tese.`,
      };
    case "trend":
      return {
        ...base,
        state: isBullish ? "estrutura de alta" : isBearish ? "estrutura de baixa" : "estrutura indefinida",
        ai_comment: `${input.symbol} em Tendência IA: ${signature}; RSI ${rsiText}, movimento ${changeText}. Direção estrutural: ${side}.`,
        trigger: isBullish
          ? `Priorizar compras apenas se estrutura, VWAP e RVOL ${rvolText} confirmarem.`
          : `Priorizar defesa/venda/tamanho menor até recuperar estrutura; Score ${scoreText} não autoriza compra isolada.`,
        invalidation: isBullish
          ? `Invalida se perder VWAP, fundo relevante ou volume comprador.`
          : `Invalida a baixa se recuperar estrutura com volume comprador e ADX ${adxText} virar a favor.`,
      };
    case "momentum":
      return {
        ...base,
        state: strongMove ? "momentum ativo" : "momentum inicial",
        ai_comment: `${input.symbol} em Momento IA: ${signature}; aceleração ${changeText}, volume ${volumeText}. Direção preferida: ${side}.`,
        trigger: strongMove
          ? `Entrar só se o próximo candle continuar ${direction}, RVOL ficar perto/acima de ${rvolText} e ADX não perder força.`
          : `Aguardar nova aceleração; com Score ${scoreText}, ${side} ainda exige expansão de preço e volume.`,
        invalidation: `Perde momentum se velocidade cair, RVOL ficar abaixo de 1.00 ou candle forte de ${oppositeSide} devolver o movimento.`,
      };
    case "smart-money":
      return {
        ...base,
        state: scoreValue >= 7 ? "smart money ativo" : "absorção em teste",
        ai_comment: `${input.symbol} em smart money: ${signature}; plano favorece ${side} apenas se houver defesa de VWAP/zona chave.`,
        trigger: `Confirmar ${side} com rompimento limpo ou pullback defendido; Score ${scoreText} exige que a defesa apareça no tape.`,
        invalidation: `Falha se preço romper contra a tese com RVOL de ${oppositeSide}, perder VWAP ou absorção sumir.`,
      };
    case "risk":
      return {
        ...base,
        state: scoreValue >= 7 ? "risco elevado" : "risco monitorado",
        ai_comment: `${input.symbol} em Risco IA: ${signature}; preço ${priceText}, volume ${volumeText}. Resultado: não operar sem Can Trade.`,
        trigger: `Liberar somente se dados, liquidez, auditor e decision ready confirmarem ${side}.`,
        invalidation: `Qualquer bloqueio de liquidez, dado ruim, conflito institucional ou auditor bloqueado invalida operação.`,
      };
    case "news-ia":
      return {
        ...base,
        state: "contexto de notícia",
        ai_comment: `${input.symbol} em Notícias IA: ${signature}; notícia é contexto e precisa de confirmação no preço.`,
        trigger: `Usar notícia só junto com preço, volume e fluxo confirmando ${side}.`,
        invalidation: `Notícia perde peso se estiver stale, sem provider confiável ou sem relação direta com o ticker.`,
      };
    case "macro":
      return {
        ...base,
        state: "contexto macro",
        ai_comment: `${input.symbol} em Macro IA: ${signature}; macro-news não é macro quantitativo.`,
        trigger: `Usar macro como filtro apenas quando houver fonte real ou evento macro claro.`,
        invalidation: `Sem fonte macro real, a leitura permanece contexto de baixo peso.`,
      };
    case "regime":
      return {
        ...base,
        state: isBullish ? "regime de alta" : "regime de baixa/lateral",
        ai_comment: `${input.symbol} em Regime IA: ${signature}; RSI ${rsiText}, movimento ${changeText}. Contexto preferido: ${side}.`,
        trigger: `Regime ajuda a tese se ADX ${adxText}, RVOL ${rvolText} e volatilidade forem coerentes.`,
        invalidation: `Regime muda se preço cruzar zona chave com volume e mantiver fechamento contrário por mais de um candle.`,
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

function scoreClass(score?: number | null, tone?: string | null) {
  // The backend already resolved direction into `tone`. The score is only
  // STRENGTH (and for the risk tool it is inverted — higher is worse), so
  // colouring by magnitude painted a max score green on a bearish/critical
  // state. When tone is present it wins; magnitude is just the fallback.
  const normalizedTone = String(tone || "").toLowerCase();
  if (normalizedTone === "bearish" || normalizedTone === "risk") return "down";
  if (normalizedTone === "bullish") return "up";
  if (normalizedTone === "neutral") return "mid";

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
    // Engine states that were reaching the PT UI untranslated (Fluxo/Liquidez IA).
    "institutional buying": "Compra institucional",
    "institutional selling": "Venda institucional",
    "liquidity monitoring": "Monitorando liquidez",
    "liquidity sweep": "Varredura de liquidez",
    "accumulation": "Acumulação",
    "distribution": "Distribuição",
    "breakout": "Rompimento",
    "breakdown": "Perda de suporte",
    "trend continuation": "Continuação de tendência",
    "trend reversal": "Reversão de tendência",
    "momentum expansion": "Expansão de momento",
    "momentum fading": "Momento perdendo força",
    "volatility expansion": "Expansão de volatilidade",
    "volatility compression": "Compressão de volatilidade",
    "no trade": "Sem operação",
    "watching": "Monitorando",
    "neutral": "Neutro",
    "sweep risk": "Risco de varredura",
    // Full canonical engine-state set emitted by the backend (snake_case keys are
    // normalised to spaces above). Without these the fallback only capitalises the
    // raw key, which is how English states like "Downtrend Structure" reached PT.
    "already expanded": "Já expandido",
    "bear trend": "Tendência de baixa",
    "bearish momentum": "Momento vendedor",
    "building pressure": "Pressão em formação",
    "bull trend": "Tendência de alta",
    compression: "Compressão",
    "critical risk": "Risco crítico",
    "distribution or weak": "Distribuição ou fraqueza",
    "distribution risk": "Risco de distribuição",
    "downtrend structure": "Estrutura de baixa",
    "early accumulation": "Acumulação inicial",
    "early radar": "Radar inicial",
    "fast move": "Movimento rápido",
    "high risk": "Risco alto",
    "high volatility": "Volatilidade alta",
    "institutional accumulation": "Acumulação institucional",
    "institutional defense": "Defesa institucional",
    "institutional distribution": "Distribuição institucional",
    "institutional interest": "Interesse institucional",
    "liquidity hotspot": "Ponto quente de liquidez",
    "liquidity sweep detected": "Varredura de liquidez detectada",
    "liquidity trap": "Armadilha de liquidez",
    "liquidity zone": "Zona de liquidez",
    "low risk": "Risco baixo",
    "macro context available": "Contexto macro disponível",
    "macro news only": "Macro apenas por notícia",
    "macro unavailable": "Macro indisponível",
    "medium risk": "Risco médio",
    mixed: "Misto",
    "momentum ignition": "Ignição de momento",
    "momentum quiet": "Momento parado",
    "momentum watch": "Momento em observação",
    "news available": "Notícias disponíveis",
    "news empty": "Sem notícias",
    "news not linked": "Notícias não vinculadas",
    "news provider failed": "Falha no provedor de notícias",
    "no sweep": "Sem varredura",
    "not ready": "Não pronto",
    "possible manipulation": "Possível manipulação",
    quiet: "Parado",
    range: "Lateral",
    "ready to break": "Pronto para romper",
    "retail noise": "Ruído de varejo",
    "reversal down": "Reversão para baixa",
    "reversal up": "Reversão para alta",
    "smart money active": "Dinheiro inteligente ativo",
    "smart money interest": "Interesse do dinheiro inteligente",
    "smart money neutral": "Dinheiro inteligente neutro",
    "squeeze ready": "Squeeze armado",
    "strong buying": "Compra forte",
    "strong selling": "Venda forte",
    "structure mixed": "Estrutura mista",
    "sweep watch": "Varredura em observação",
    "thin liquidity": "Liquidez fina",
    "trend pending": "Tendência indefinida",
    unknown: "Sem leitura",
    "uptrend structure": "Estrutura de alta",
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
    // Mirrors of the engine states added to the PT map, so both locales resolve
    // through the dictionary instead of falling back to raw capitalisation.
    "institutional buying": "Institutional buying",
    "institutional selling": "Institutional selling",
    "liquidity monitoring": "Liquidity monitoring",
    "liquidity sweep": "Liquidity sweep",
    "compra institucional": "Institutional buying",
    "venda institucional": "Institutional selling",
    "monitorando liquidez": "Liquidity monitoring",
    "varredura de liquidez": "Liquidity sweep",
    accumulation: "Accumulation",
    distribution: "Distribution",
    breakout: "Breakout",
    breakdown: "Breakdown",
    "trend continuation": "Trend continuation",
    "trend reversal": "Trend reversal",
    "momentum expansion": "Momentum expansion",
    "momentum fading": "Momentum fading",
    "volatility expansion": "Volatility expansion",
    "volatility compression": "Volatility compression",
    "no trade": "No trade",
    watching: "Watching",
    neutral: "Neutral",
    // EN mirror of the canonical engine-state set, so both locales resolve through
    // the dictionary instead of raw capitalisation.
    "already expanded": "Already expanded",
    "bear trend": "Bear trend",
    "bearish momentum": "Bearish momentum",
    "building pressure": "Building pressure",
    "bull trend": "Bull trend",
    compression: "Compression",
    "critical risk": "Critical risk",
    "distribution or weak": "Distribution or weak",
    "distribution risk": "Distribution risk",
    "downtrend structure": "Downtrend structure",
    "early accumulation": "Early accumulation",
    "early radar": "Early radar",
    "fast move": "Fast move",
    "high risk": "High risk",
    "high volatility": "High volatility",
    "institutional accumulation": "Institutional accumulation",
    "institutional defense": "Institutional defense",
    "institutional distribution": "Institutional distribution",
    "institutional interest": "Institutional interest",
    "liquidity hotspot": "Liquidity hotspot",
    "liquidity sweep detected": "Liquidity sweep detected",
    "liquidity trap": "Liquidity trap",
    "liquidity zone": "Liquidity zone",
    "low risk": "Low risk",
    "macro context available": "Macro context available",
    "macro news only": "Macro from news only",
    "macro unavailable": "Macro unavailable",
    "medium risk": "Medium risk",
    mixed: "Mixed",
    "momentum ignition": "Momentum ignition",
    "momentum quiet": "Momentum quiet",
    "momentum watch": "Momentum watch",
    "news available": "News available",
    "news empty": "No news",
    "news not linked": "News not linked",
    "news provider failed": "News provider failed",
    "no sweep": "No sweep",
    "not ready": "Not ready",
    "possible manipulation": "Possible manipulation",
    quiet: "Quiet",
    range: "Range",
    "ready to break": "Ready to break",
    "retail noise": "Retail noise",
    "reversal down": "Reversal down",
    "reversal up": "Reversal up",
    "smart money active": "Smart money active",
    "smart money interest": "Smart money interest",
    "smart money neutral": "Smart money neutral",
    "squeeze ready": "Squeeze ready",
    "strong buying": "Strong buying",
    "strong selling": "Strong selling",
    "structure mixed": "Structure mixed",
    "sweep watch": "Sweep watch",
    "thin liquidity": "Thin liquidity",
    "trend pending": "Trend pending",
    unknown: "No read",
    "uptrend structure": "Uptrend structure",
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

  return parsed.toLocaleString(locale === "en-US" ? "en-US" : "pt-BR", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function saoPauloDateKey(value: Date) {
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: "America/Sao_Paulo",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(value);
  const pick = (type: string) => parts.find((part) => part.type === type)?.value || "";
  return `${pick("year")}-${pick("month")}-${pick("day")}`;
}

function aiFreshnessStatus(detectedAt?: string | null, viewedAt?: string | null, locale: AppLocale = "pt-BR") {
  const detectedDate = detectedAt ? new Date(detectedAt) : null;
  const viewedDate = viewedAt ? new Date(viewedAt) : new Date();
  const isEnglish = locale === "en-US";
  if (!detectedDate || Number.isNaN(detectedDate.getTime()) || Number.isNaN(viewedDate.getTime())) {
    return {
      label: isEnglish ? "Status: no confirmed timestamp" : "Status: sem horário confirmado",
      tone: "stale",
    };
  }

  const detectedKey = saoPauloDateKey(detectedDate);
  const activeResetKey = getAlertResetKey(viewedDate);
  if (detectedKey === activeResetKey) {
    return {
      label: isEnglish ? "Status: data from today" : "Status: dados de hoje",
      tone: "fresh",
    };
  }

  const viewedParts = getSaoPauloParts(viewedDate);
  const afterDailyReset = viewedParts.hour >= 7;
  if (afterDailyReset) {
    return {
      label: isEnglish
        ? "Status: previous-session data"
        : "Status: dados da sessão anterior",
      tone: "stale",
    };
  }

  return {
    label: isEnglish ? "Status: old read" : "Status: leitura antiga",
    tone: "stale",
  };
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
  canonicalItems: WatchlistItem[] = PRELOADED_UNIVERSE,
) {
  const bySymbol = new Map<string, WatchlistItem>();

  for (const item of [...canonicalItems, ...customItems]) {
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
      bySymbol.set(normalized, {
        ...current,
        logoUrl: safeAssetLogoUrl(liveQuote.logo_url, liveQuote.icon_url, current.logoUrl),
        price: liveQuote.price ?? current.price ?? null,
        change: liveQuote.change ?? current.change ?? null,
        changePct: derivedChangePct ?? current.changePct ?? null,
        volume: liveQuote.volume ?? current.volume ?? null,
        score: current.score ?? null,
        trend: current.trend ?? null,
        rsi: current.rsi ?? null,
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

type NormalizedPollOption = PollOption & {
  pct: number;
};

type NormalizedPoll = PollPayload & {
  options: NormalizedPollOption[];
  total_votes: number;
};

function normalizePollPayload(poll: PollPayload | null | undefined, symbol: string): NormalizedPoll | null {
  if (!poll || !sameSymbol(poll.symbol, symbol)) return null;
  if (!poll.question || !poll.options?.length || isGenericPollQuestion(poll.question)) return null;
  const source = poll;
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
  return {
    ...source,
    symbol,
    question: source.question,
    status: source.status || "active",
    total_votes: totalVotes,
    options: normalizedOptions,
  };
}

export function WorkspaceShell({ focusedTab, initialTicker }: Props) {
  const searchParams = useSearchParams();
  const queryToken = searchParams.get("token") || "";
  const queryTicker = normalizeSymbol(searchParams.get("ticker") || initialTicker || "PETR4");

  const [token, setToken] = useState("");
  const [viewedAtIso] = useState(() => new Date().toISOString());
  const [email, setEmail] = useState("");
  const [otpCode, setOtpCode] = useState("");
  const [pendingLoginToken, setPendingLoginToken] = useState("");
  const [loginError, setLoginError] = useState("");
  // Login modal for the panel route. promptLogin() used to focus a login card
  // that /panel/[slug] never renders (the ref was always null) and then fire a
  // window.alert pointing at a "Acesso a plataforma" block that is not on this
  // route — so a blocked visitor got "Faça login para publicar" with no way to
  // actually log in.
  const [loginModalOpen, setLoginModalOpen] = useState(false);
  const loginDialogEmailRef = useRef<HTMLInputElement | null>(null);
  const loginDialogReturnRef = useRef<HTMLElement | null>(null);
  const [loginNotice, setLoginNotice] = useState("");
  const [loginBusy, setLoginBusy] = useState(false);
  const [resendCooldownUntil, setResendCooldownUntil] = useState(0);
  const [emailChangeInput, setEmailChangeInput] = useState("");
  const [emailChangeToken, setEmailChangeToken] = useState("");
  const [emailChangeCode, setEmailChangeCode] = useState("");
  const [emailChangeNotice, setEmailChangeNotice] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const [bootstrap, setBootstrap] = useState<PublicBootstrap | null>(null);
  const [indexStrip, setIndexStrip] = useState<IndexStripItem[]>([]);
  const [workspace, setWorkspace] = useState<WorkspaceData | null>(null);
  const [publicAiTools, setPublicAiTools] = useState<PublicAiToolsPayload | null>(null);
  const [publicAiCatalog, setPublicAiCatalog] = useState<PublicAiToolsPayload | null>(null);
  const [access, setAccess] = useState<UserAccess | null>(null);
  const [accessState, setAccessState] = useState<AccessState>("UNINITIALIZED");
  const accessGenerationRef = useRef(0);
  const accessFlightRef = useRef(createSingleFlight<UserAccess>());
  const accessCountersRef = useRef(createAccessCounters());
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
  const [publicMarketMetrics, setPublicMarketMetrics] = useState<PublicMarketMetrics | null>(null);
  const [, setPushStatus] = useState<Record<string, unknown> | null>(null);
  const [mediaStatus, setMediaStatus] = useState<Record<string, unknown> | null>(null);
  const [telegramLink, setTelegramLink] = useState<TelegramLinkSessionResponse | null>(null);
  const [profileNameInput, setProfileNameInput] = useState("");
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

  // A ticker change is a hard identity boundary: never leave the previous
  // asset's derived widgets visible while the deferred request is in flight.
  useEffect(() => {
    setPublicInsight(null);
    setPublicMarketMetrics(null);
    setPublicChart(null);
    setPublicAiTools(null);
    setPublicDataStatus({});
    setQuote(null);
  }, [selectedTicker]);

  const [watchlistQuery, setWatchlistQuery] = useState("");
  const [watchCategory, setWatchCategory] = useState<"Todos" | (typeof CATEGORY_ORDER)[number]>("Todos");
  const [remoteSearchSymbols, setRemoteSearchSymbols] = useState<string[]>([]);
  const [customWatchItems, setCustomWatchItems] = useState<WatchlistItem[]>([]);
  const [removedWatchSymbols, setRemovedWatchSymbols] = useState<string[]>([]);
  const [watchlistHydrated, setWatchlistHydrated] = useState(false);
  const [appLocale, setAppLocale] = useState<AppLocale>("pt-BR");
  const [appLocaleHydrated, setAppLocaleHydrated] = useState(false);
  const isUsLocale = appLocale === "en-US";

  const [activeStockFlowDay, setActiveStockFlowDay] = useState("aovivo");
  const [stockFlowPollVote, setStockFlowPollVote] = useState<string | null>(null);
  const [stockFlowChatInput, setStockFlowChatInput] = useState("");
  const [stockFlowChatMessages, setStockFlowChatMessages] = useState<Array<{ id: string; time: string; user: string; text: string }>>([
    { id: "sf1", time: "10:12", user: "@Trader_Zero", text: "PETR4 rompendo a resistência dos 38,50!" },
    { id: "sf2", time: "10:14", user: "@Ana_Stocks", text: "De olho na ata do Copom na terça..." },
    { id: "sf3", time: "10:15", user: "@Lucas_Quant", text: "Fluxo IA apontando forte fluxo comprador em VALE3" },
  ]);

  const handleSendStockFlowChatMessage = () => {
    const text = stockFlowChatInput.trim();
    if (!text) return;
    const now = new Date();
    const timeStr = `${String(now.getHours()).padStart(2, "0")}:${String(now.getMinutes()).padStart(2, "0")}`;
    const newMsg = {
      id: `sf-${Date.now()}`,
      time: timeStr,
      user: profileNameInput.trim() ? `@${profileNameInput.trim()}` : "@Trader_Guest",
      text,
    };
    setStockFlowChatMessages((prev) => [...prev, newMsg]);
    setStockFlowChatInput("");
  };

  const [stockFlowLiveItems, setStockFlowLiveItems] = useState<Array<{ id: string; text: string }>>([]);
  const [stockFlowLiveInput, setStockFlowLiveInput] = useState("");

  const handlePublishStockFlowLiveItem = () => {
    const text = stockFlowLiveInput.trim();
    if (!text) return;
    const newItem = {
      id: `live-${Date.now()}`,
      text,
    };
    setStockFlowLiveItems((prev) => [newItem, ...prev]);
    setStockFlowLiveInput("");
  };

  const [editingStockFlowEditorial, setEditingStockFlowEditorial] = useState(false);
  const [editorialDate, setEditorialDate] = useState("24 de Julho de 2026 — 08:30");
  const [editorialTitle, setEditorialTitle] = useState("📊 ABERTURA DO MERCADO & VISÃO DO DIA");
  const [editorialQuote, setEditorialQuote] = useState("Atenção Traders: Mercado abre de olho nos dados do IPCA e na decisão de juros do Fed nos EUA. Liquidez IA aponta fluxo comprador no setor bancário nas primeiras horas.");
  const [editorialPoints, setEditorialPoints] = useState<string[]>([
    "Agenda econômica",
    "Empresas do trimestre",
    "Eventos do dia",
    "Expectativa institucional",
  ]);

  const [editEditorialDateInput, setEditEditorialDateInput] = useState("");
  const [editEditorialTitleInput, setEditEditorialTitleInput] = useState("");
  const [editEditorialQuoteInput, setEditEditorialQuoteInput] = useState("");
  const [editEditorialPointsInput, setEditEditorialPointsInput] = useState("");

  const handleStartEditEditorial = () => {
    setEditEditorialDateInput(editorialDate);
    setEditEditorialTitleInput(editorialTitle);
    setEditEditorialQuoteInput(editorialQuote);
    setEditEditorialPointsInput(editorialPoints.join("\n"));
    setEditingStockFlowEditorial(true);
  };

  const handleSaveEditorial = () => {
    if (editEditorialDateInput.trim()) setEditorialDate(editEditorialDateInput.trim());
    if (editEditorialTitleInput.trim()) setEditorialTitle(editEditorialTitleInput.trim());
    if (editEditorialQuoteInput.trim()) setEditorialQuote(editEditorialQuoteInput.trim());
    const parsedPoints = editEditorialPointsInput
      .split("\n")
      .map((p) => p.trim())
      .filter(Boolean);
    if (parsedPoints.length) setEditorialPoints(parsedPoints);
    setEditingStockFlowEditorial(false);
  };

  const [stockFlowPollQuestion, setStockFlowPollQuestion] = useState("Qual o seu viés para o Ibovespa hoje?");
  const [editingStockFlowPollQuestion, setEditingStockFlowPollQuestion] = useState(false);
  const [editStockFlowPollQuestionInput, setEditStockFlowPollQuestionInput] = useState("");

  const handleStartEditPollQuestion = () => {
    setEditStockFlowPollQuestionInput(stockFlowPollQuestion);
    setEditingStockFlowPollQuestion(true);
  };

  const handleSavePollQuestion = () => {
    if (editStockFlowPollQuestionInput.trim()) {
      setStockFlowPollQuestion(editStockFlowPollQuestionInput.trim());
    }
    setEditingStockFlowPollQuestion(false);
  };
  const canonicalUniverse = useMemo<WatchlistItem[]>(() => {
    const fromBackend = bootstrap?.market_universe?.items;
    if (!Array.isArray(fromBackend) || !fromBackend.length) return PRELOADED_UNIVERSE;
    const validCategories = new Set<string>(CATEGORY_ORDER);
    const byIdentity = new Map<string, WatchlistItem>();
    for (const item of fromBackend) {
      const symbol = normalizeSymbol(item.symbol);
      const category = String(item.category || "");
      if (!symbol || !validCategories.has(category) || isRemovedFutureSymbol(symbol)) continue;
      const identity = `${String(item.market || category).toUpperCase()}|${String(item.exchange || "").toUpperCase()}|${symbol}`;
      byIdentity.set(identity, {
        symbol,
        label: displayWatchlistLabel({ symbol, label: item.label }, appLocale),
        category,
        logoUrl: safeAssetLogoUrl(item.logo_url, item.icon_url),
      });
    }
    return byIdentity.size ? Array.from(byIdentity.values()) : PRELOADED_UNIVERSE;
  }, [appLocale, bootstrap?.market_universe?.items]);
  const activeWatchSymbols = useMemo(() => {
    const removed = new Set(removedWatchSymbols.map(normalizeSymbol));
    return Array.from(new Set([...canonicalUniverse, ...customWatchItems]
      .map((item) => normalizeSymbol(item.symbol))
      .filter((symbol) => symbol && !removed.has(symbol))));
  }, [canonicalUniverse, customWatchItems, removedWatchSymbols]);
  const [advancedMode, setAdvancedMode] = useState(false);
  const [aiTimedOutKey, setAiTimedOutKey] = useState<string | null>(null);
  const aiDeadlineRegistryRef = useRef(createDeadlineRegistry(AI_PENDING_CLIENT_TIMEOUT_MS));
  const proPreferenceRef = useRef<boolean | null>(null);
  const [modeBootstrapped, setModeBootstrapped] = useState(false);
  const normalizedAccessPlan = String(access?.plan || "").toLowerCase();
  const normalizedAccessStatus = String(access?.plan_status || "").toLowerCase();
  const proModeAllowed = accessState === "ALLOWED";
  const proModeLocked = !proModeAllowed;

  // ponytail: Stock Flow is frontend-only local state today, so admin is a client email gate.
  // When Stock Flow gets a backend, replace with a server-enforced role/is_admin claim (a client
  // check secures nothing on its own).
  const STOCK_FLOW_ADMIN_EMAILS = new Set(["dileno2010@gmail.com"]);
  const isStockFlowAdmin = Boolean(
    access?.email && STOCK_FLOW_ADMIN_EMAILS.has(String(access.email).trim().toLowerCase()),
  );

  useEffect(() => {
    setAppLocale(readInitialLocale());
    setAppLocaleHydrated(true);
  }, []);

  useEffect(() => {
    if (!appLocaleHydrated) return;
    if (typeof window === "undefined") return;
    writeStorageValue(APP_LOCALE_STORAGE_KEY, appLocale);
    document.documentElement.lang = appLocale === "en-US" ? "en-US" : "pt-BR";
    document.documentElement.dataset.locale = appLocale;
  }, [appLocale, appLocaleHydrated]);

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
    () => Array.from(new Set([...canonicalUniverse.map((item) => item.symbol), ...customWatchItems.map((item) => item.symbol), selectedTicker].map(normalizeSymbol).filter(Boolean))).filter((symbol) => !isRemovedFutureSymbol(symbol)),
    [canonicalUniverse, customWatchItems, selectedTicker],
  );
  const publicTickerTapeSymbols = useMemo(
    () => Array.from(new Set([selectedTicker, ...FIXED_TAPE_SYMBOLS])),
    [selectedTicker],
  );
  const visiblePublicWatchSymbols = useMemo(
    () =>
      Array.from(
        new Set(
          [...canonicalUniverse, ...customWatchItems]
            .filter((item) => !isRemovedFutureSymbol(item.symbol))
            .filter((item) => activeWatchSymbols.map(normalizeSymbol).includes(item.symbol))
            .filter((item) => watchCategory === "Todos" || item.category === watchCategory)
            .map((item) => item.symbol),
        ),
    ),
    [activeWatchSymbols, canonicalUniverse, customWatchItems, watchCategory],
  );
  const priorityPublicWatchSymbols = useMemo(() => {
    const activeSet = new Set(activeWatchSymbols.map(normalizeSymbol).filter(Boolean));
    const fromCategory = (category: WatchlistItem["category"], limit: number) =>
      canonicalUniverse
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
        ...customWatchItems.map((item) => normalizeSymbol(item.symbol)).filter((symbol) => symbol && !isRemovedFutureSymbol(symbol)),
      ]),
    );
  }, [activeWatchSymbols, canonicalUniverse, customWatchItems, selectedTicker]);
  const publicTickerTapeKey = publicTickerTapeSymbols.join("|");
  const publicWatchKey = publicWatchSymbols.join("|");
  const priorityPublicWatchKey = priorityPublicWatchSymbols.join("|");
  const visiblePublicWatchKey = visiblePublicWatchSymbols.join("|");
  const [tickerTapePaused, setTickerTapePaused] = useState(false);
  // Dark is the product default; the trader can switch to light and that choice
  // is restored from storage below.
  const [darkMode, setDarkMode] = useState(true);
  const [aiToolSoundSettings, setAiToolSoundSettings] = useState<Record<string, boolean>>(defaultAiToolSoundSettings);
  const [settingsTab, setSettingsTab] = useState<SettingsTab>("preferencias");
  const [accountPanel, setAccountPanel] = useState<AccountPanel>("perfil");
  const [notificationOpen, setNotificationOpen] = useState(false);
  const [toolsOpen, setToolsOpen] = useState(false);
  const [pollOpen, setPollOpen] = useState(false);
  const [accessOpen, setAccessOpen] = useState(false);
  const [strategicPanelOpen, setStrategicPanelOpen] = useState(true);
  const [strategicPanelHydrated, setStrategicPanelHydrated] = useState(false);
  const [strategicConclusionOpen, setStrategicConclusionOpen] = useState(true);
  const [strategicAnalysisMinute, setStrategicAnalysisMinute] = useState(() => currentFiveMinuteBucket());
  const [selectedInstitutionalSectionId, setSelectedInstitutionalSectionId] = useState<string | null>(null);
  const [showMarkers, setShowMarkers] = useState(DEFAULT_CHART_SETTINGS.show_markers);
  const [showZones, setShowZones] = useState(DEFAULT_CHART_SETTINGS.show_zones);
  const [showPriceLine, setShowPriceLine] = useState(DEFAULT_CHART_SETTINGS.show_price_line);
  const [showVwap, setShowVwap] = useState(DEFAULT_CHART_SETTINGS.show_vwap);
  const [showMacd, setShowMacd] = useState(DEFAULT_CHART_SETTINGS.show_macd);
  const [showRsi, setShowRsi] = useState(DEFAULT_CHART_SETTINGS.show_rsi);
  const [showSupport, setShowSupport] = useState(DEFAULT_CHART_SETTINGS.show_support);
  const [showResistance, setShowResistance] = useState(DEFAULT_CHART_SETTINGS.show_resistance);
  const [showSupertrend, setShowSupertrend] = useState(DEFAULT_CHART_SETTINGS.show_supertrend);
  const [showVolume, setShowVolume] = useState(DEFAULT_CHART_SETTINGS.show_volume);
  const [mobileWatchlistOpen, setMobileWatchlistOpen] = useState(false);
  const [mobileInsightsOpen, setMobileInsightsOpen] = useState(false);

  const [postText, setPostText] = useState("");
  const [postSentiment, setPostSentiment] = useState("bullish");
  const [postFile, setPostFile] = useState<File | null>(null);
  const postFilePreviewUrl = useMemo(() => (postFile ? URL.createObjectURL(postFile) : null), [postFile]);
  useEffect(() => () => {
    if (postFilePreviewUrl) URL.revokeObjectURL(postFilePreviewUrl);
  }, [postFilePreviewUrl]);
  const [posting, setPosting] = useState(false);
  const [composerEmojiOpen, setComposerEmojiOpen] = useState(false);
  const [recentComposerEmojis, setRecentComposerEmojis] = useState<string[]>(() => {
    try {
      const parsed = JSON.parse(readStorageValue(RECENT_EMOJIS_STORAGE_KEY) || "[]");
      return Array.isArray(parsed) ? parsed.filter((item): item is string => typeof item === "string").slice(0, 10) : [];
    } catch {
      return [];
    }
  });
  const [composerGifOpen, setComposerGifOpen] = useState(false);
  const [gifQuery, setGifQuery] = useState("");
  const [gifResults, setGifResults] = useState<GifSearchItem[]>([]);
  const [gifSearchStatus, setGifSearchStatus] = useState<"idle" | "loading" | "ready" | "empty" | "unavailable" | "error">("idle");
  const [gifSearchReason, setGifSearchReason] = useState("");
  const [selectedGif, setSelectedGif] = useState<GifSearchItem | null>(null);
  const [pollStatus, setPollStatus] = useState<"loading" | "ready" | "empty" | "error">("loading");
  const [pollReason, setPollReason] = useState("");
  const [aiRequestNonce, setAiRequestNonce] = useState(0);
  const [aiRequestState, setAiRequestState] = useState<{ key: string; status: string; reason: string }>({ key: "", status: "IDLE", reason: "" });
  const [publicDataStatus, setPublicDataStatus] = useState<Record<string, string>>({});
  const publicDataStatusKey = JSON.stringify(publicDataStatus);
  const publicHydrationPending = [
    ...Object.values(publicDataStatus),
    publicMarketMetrics?.sentiment?.status,
    publicMarketMetrics?.intraday_rvol?.status,
    publicMarketMetrics?.levels?.status,
    publicMarketMetrics?.operational_view?.technical_context?.institutional_flow?.status,
    publicMarketMetrics?.operational_view?.operational_context?.liquidity?.status,
  ].some((status) => status === "PENDING" || status === "REFRESHING");
  const [predictionOpen, setPredictionOpen] = useState(false);
  const [predictionSymbol, setPredictionSymbol] = useState(queryTicker);
  const [predictionTargetPrice, setPredictionTargetPrice] = useState("");
  const [predictionTargetDate, setPredictionTargetDate] = useState("");
  const [predictionPosting, setPredictionPosting] = useState(false);
  const [pollCommentOpen, setPollCommentOpen] = useState(false);
  const [pollCommentText, setPollCommentText] = useState("");
  const [pollCommentPosting, setPollCommentPosting] = useState(false);
  const [commentDrafts, setCommentDrafts] = useState<Record<number, string>>({});
  const [commentComposers, setCommentComposers] = useState<Record<number, CommentComposerState>>({});
  const commentFileInputRefs = useRef<Record<number, HTMLInputElement | null>>({});
  const [commentingPostId, setCommentingPostId] = useState<number | null>(null);
  const pendingLikePostIdsRef = useRef(new Set<number>());
  const [pendingLikePostIds, setPendingLikePostIds] = useState<Set<number>>(new Set());
  const [postMenuId, setPostMenuId] = useState<number | null>(null);
  const [reportTargetPost, setReportTargetPost] = useState<FeedPost | null>(null);
  const [reportReason, setReportReason] = useState("spam");
  const [reportNote, setReportNote] = useState("");
  const [reportingPostId, setReportingPostId] = useState<number | null>(null);
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

  useEffect(() => {
    if (!loginModalOpen) return undefined;
    const timer = window.setTimeout(() => loginDialogEmailRef.current?.focus(), 40);
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.stopPropagation();
        closeLoginDialog();
      }
    };
    window.addEventListener("keydown", onKeyDown, true);
    return () => {
      window.clearTimeout(timer);
      window.removeEventListener("keydown", onKeyDown, true);
    };
  }, [loginModalOpen]);

  useEffect(() => {
    // Authenticated: the dialog has done its job. The composer draft is left
    // untouched on purpose — the user re-confirms the post themselves.
    if (loginModalOpen && token) closeLoginDialog();
  }, [loginModalOpen, token]);
  const pollCommentInputRef = useRef<HTMLTextAreaElement | null>(null);
  const composerCardRef = useRef<HTMLDivElement | null>(null);
  const leftRailRef = useRef<HTMLElement | null>(null);
  const aiSoundLastKeyRef = useRef<string | null>(null);
  const aiSoundSuppressedUntilRef = useRef<number>(0);
  const gifSearchAbortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    publicQuotesRef.current = publicQuotes;
  }, [publicQuotes]);

  useEffect(() => {
    tickerTapeQuotesRef.current = tickerTapeQuotes;
  }, [tickerTapeQuotes]);

  useEffect(() => {
    // Mission 31B: web sessions live in an httpOnly cookie. Purge any legacy
    // token persisted by older builds — tokens never touch storage again.
    removeStorageValue("stocknewsbr.token");

    const storedCooldown = Number(readStorageValue(CODE_COOLDOWN_STORAGE_KEY) || 0);
    if (storedCooldown > Date.now()) setResendCooldownUntil(storedCooldown);

    if (queryToken) {
      // Transient app->web handoff token: kept in memory only, and scrubbed
      // from the address bar/history so it never lingers in the URL.
      try {
        const nextUrl = new URL(window.location.href);
        nextUrl.searchParams.delete("token");
        window.history.replaceState(window.history.state, "", `${nextUrl.pathname}${nextUrl.search}${nextUrl.hash}`);
      } catch {
        // history scrub is best-effort
      }
      setToken(queryToken);
      return;
    }

    let cancelled = false;

    // Sole owner of entitlement. Single-flight per generation, stale-guarded,
    // and deliberately independent of any market-data request.
    const generation = accessGenerationRef.current + 1;
    accessGenerationRef.current = generation;
    const counters = accessCountersRef.current;
    counters.logicalRequests += 1;
    setAccessState("PENDING");

    let attempt = 0;
    const settle = (state: AccessState, payload: UserAccess | null) => {
      if (cancelled) {
        counters.aborts += 1;
        return;
      }
      if (isStaleAccessResponse(generation, accessGenerationRef.current)) {
        counters.staleIgnored += 1;
        return;
      }
      if (state === "ALLOWED") counters.allowed += 1;
      else if (state === "DENIED") counters.denied += 1;
      startTransition(() => {
        setAccessState(state);
        setAccess(payload);
        setToken(payload ? COOKIE_SESSION_TOKEN : "");
      });
    };

    const runAccess = () => {
      counters.networkRequests += 1;
      accessFlightRef.current
        .run(`${COOKIE_SESSION_TOKEN}:${generation}:${attempt}`, () => getAccess(COOKIE_SESSION_TOKEN))
        .then((payload) => settle(classifyAccessOutcome({ kind: "response", payload }), payload))
        .catch((error: unknown) => {
          const status = (error as { status?: number } | null)?.status;
          const state = classifyAccessOutcome({ kind: "error", status });
          if (cancelled) {
            counters.aborts += 1;
            return;
          }
          if (isRetryableAccessState(state)) {
            counters.transientError += 1;
            attempt += 1;
            if (attempt < ACCESS_BOOTSTRAP_MAX_ATTEMPTS) {
              window.setTimeout(runAccess, ACCESS_BOOTSTRAP_RETRY_BASE_MS * attempt);
              return;
            }
            // Retries exhausted: hold the preference, never claim a denial.
            if (!isStaleAccessResponse(generation, accessGenerationRef.current)) setAccessState("TRANSIENT_ERROR");
            return;
          }
          settle(state, null);
        });
    };
    runAccess();

    return () => {
      cancelled = true;
    };
  }, [queryToken]);

  useEffect(() => {
    // Re-enable the "Enviar/Reenviar código" button when the cooldown ends.
    if (!resendCooldownUntil) return;

    const remainingMs = resendCooldownUntil - Date.now();

    if (remainingMs <= 0) {
      setResendCooldownUntil(0);
      return;
    }

    const timer = window.setTimeout(() => setResendCooldownUntil(0), remainingMs + 250);
    return () => window.clearTimeout(timer);
  }, [resendCooldownUntil]);

  useEffect(() => {
    function onSessionReplaced() {
      startTransition(() => {
        setToken("");
        setAccess(null);
        setWorkspace(null);
        setPendingLoginToken("");
        setOtpCode("");
        setLoginNotice("");
        setLoginError("Sua sessão foi encerrada porque houve login em outro dispositivo.");
      });
    }

    window.addEventListener(SESSION_REPLACED_EVENT, onSessionReplaced);
    return () => window.removeEventListener(SESSION_REPLACED_EVENT, onSessionReplaced);
  }, []);

  useEffect(() => {
    getBootstrap().then(setBootstrap).catch(() => undefined);
  }, []);

  useEffect(() => {
    try {
      const raw = readStorageValue(WATCHLIST_STATE_STORAGE_KEY);
      if (raw) {
        const parsed = JSON.parse(raw) as { removed_symbols?: unknown; custom_items?: unknown };
        if (Array.isArray(parsed.removed_symbols)) {
          setRemovedWatchSymbols(Array.from(new Set(parsed.removed_symbols.map((item) => normalizeSymbol(String(item))).filter(Boolean))));
        }
        if (Array.isArray(parsed.custom_items)) {
          const allowedCategories = new Set<string>(CATEGORY_ORDER);
          setCustomWatchItems(parsed.custom_items.flatMap((rawItem) => {
            if (!rawItem || typeof rawItem !== "object") return [];
            const item = rawItem as Partial<WatchlistItem>;
            const symbol = normalizeSymbol(String(item.symbol || ""));
            const category = String(item.category || "");
            if (!symbol || !allowedCategories.has(category) || isRemovedFutureSymbol(symbol)) return [];
            return [{ symbol, category, label: String(item.label || symbolName(symbol)) }];
          }));
        }
      }
    } catch {
      setRemovedWatchSymbols([]);
      setCustomWatchItems([]);
    } finally {
      setWatchlistHydrated(true);
    }
  }, []);

  useEffect(() => {
    if (!watchlistHydrated) return;
    writeStorageValue(WATCHLIST_STATE_STORAGE_KEY, JSON.stringify({
      removed_symbols: removedWatchSymbols,
      custom_items: customWatchItems.map(({ symbol, label, category }) => ({ symbol, label, category })),
    }));
  }, [customWatchItems, removedWatchSymbols, watchlistHydrated]);

  useEffect(() => {
    const stored = readStorageValue(STRATEGIC_PANEL_STORAGE_KEY);
    setStrategicPanelOpen(stored !== "closed");
    setStrategicPanelHydrated(true);
  }, []);

  useEffect(() => {
    if (!strategicPanelHydrated) return;
    writeStorageValue(STRATEGIC_PANEL_STORAGE_KEY, strategicPanelOpen ? "open" : "closed");
  }, [strategicPanelHydrated, strategicPanelOpen]);

  // Read-only capture. This effect must never write: the old persistence effect
  // ran on the first commit with advancedMode still false and overwrote the
  // saved "pro" preference before anything could act on it.
  useEffect(() => {
    if (proPreferenceRef.current === null) {
      proPreferenceRef.current = readStorageValue(WORKSPACE_MODE_STORAGE_KEY) === "pro";
    }
  }, []);

  // Single authority for the bootstrap — see lib/access-bootstrap.ts.
  useEffect(() => {
    const decision = resolveAdvancedMode({
      state: accessState,
      preferPro: proPreferenceRef.current === true,
      current: advancedMode,
    });
    if (decision.advancedMode !== null && decision.advancedMode !== advancedMode) setAdvancedMode(decision.advancedMode);
    if (decision.persist) writeStorageValue(WORKSPACE_MODE_STORAGE_KEY, decision.persist);
    if (isTerminalAccessState(accessState) && !modeBootstrapped) setModeBootstrapped(true);
  }, [accessState, advancedMode, modeBootstrapped]);

  // Persist only real, post-bootstrap changes. Hydration, symbol switches and
  // re-renders can no longer rewrite the preference.
  // Test-only observability: lets the audit assert one logical access request
  // per page instead of inferring it from timing.
  useEffect(() => {
    if (typeof window === "undefined") return;
    (window as unknown as Record<string, unknown>).__snbrAccess = {
      state: accessState,
      ...accessCountersRef.current,
    };
  }, [accessState]);


  useEffect(() => {
    if (!shouldPersistModeChange(modeBootstrapped)) return;
    writeStorageValue(WORKSPACE_MODE_STORAGE_KEY, advancedMode ? "pro" : "simple");
  }, [advancedMode, modeBootstrapped]);

  useEffect(() => {
    setPredictionSymbol(selectedTicker);
  }, [selectedTicker]);

  useEffect(() => {
    const storedDark = readStorageValue("stocknewsbr.dark_mode");
    // Honour BOTH stored values: "0" must restore light. Only-checking "1" left a
    // returning light-mode user stuck on the dark default.
    if (storedDark === "1") setDarkMode(true);
    else if (storedDark === "0") setDarkMode(false);
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
    setShowMacd(chartSettings?.show_macd ?? DEFAULT_CHART_SETTINGS.show_macd);
    setShowRsi(chartSettings?.show_rsi ?? DEFAULT_CHART_SETTINGS.show_rsi);
    setShowSupport(chartSettings?.show_support ?? DEFAULT_CHART_SETTINGS.show_support);
    setShowResistance(chartSettings?.show_resistance ?? DEFAULT_CHART_SETTINGS.show_resistance);
    setShowSupertrend(chartSettings?.show_supertrend ?? DEFAULT_CHART_SETTINGS.show_supertrend);
    setShowVolume(chartSettings?.show_volume ?? DEFAULT_CHART_SETTINGS.show_volume);
  }, [
    workspace?.layout?.chart_settings?.show_markers,
    workspace?.layout?.chart_settings?.show_zones,
    workspace?.layout?.chart_settings?.show_price_line,
    workspace?.layout?.chart_settings?.show_vwap,
    workspace?.layout?.chart_settings?.show_macd,
    workspace?.layout?.chart_settings?.show_rsi,
    workspace?.layout?.chart_settings?.show_support,
    workspace?.layout?.chart_settings?.show_resistance,
    workspace?.layout?.chart_settings?.show_supertrend,
    workspace?.layout?.chart_settings?.show_volume,
  ]);

  useEffect(() => {
    const commentToolOpen = Object.values(commentComposers).some((composer) => Boolean(composer.tool));
    if (!postMenuId && !composerEmojiOpen && !composerGifOpen && !commentToolOpen) return;

    function closeCommentTools() {
      setCommentComposers((current) => Object.fromEntries(
        Object.entries(current).map(([postId, composer]) => [postId, { ...composer, tool: null }]),
      ));
    }

    function handlePointerDown(event: PointerEvent) {
      const target = event.target as Element | null;
      if (!target) return;
      if (postMenuId && target.closest("[data-post-menu-root]")) return;
      if ((composerEmojiOpen || composerGifOpen) && target.closest("[data-composer-controls]")) return;
      if (commentToolOpen && target.closest("[data-comment-composer]")) return;
      setPostMenuId(null);
      setComposerEmojiOpen(false);
      setComposerGifOpen(false);
      closeCommentTools();
    }

    function handleKeyDown(event: KeyboardEvent) {
      if (event.key !== "Escape") return;
      setPostMenuId(null);
      setComposerEmojiOpen(false);
      setComposerGifOpen(false);
      closeCommentTools();
    }

    document.addEventListener("pointerdown", handlePointerDown);
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("pointerdown", handlePointerDown);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [commentComposers, composerEmojiOpen, composerGifOpen, postMenuId]);

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
      getPublicQuotesRobust([symbol], 1, 1)
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
    setProfileAvatarUrl(access?.avatar_url || "");
  }, [access?.display_name, access?.avatar_url]);

  useEffect(() => {
    let cancelled = false;
    const controller = new AbortController();
    const requestedTicker = deferredTicker;
    setPoll(null);
    setPollStatus("loading");
    setPollReason("");

    getPoll(requestedTicker, appLocale, controller.signal)
      .then((nextPoll) => {
        if (cancelled) return;
        const normalized = normalizePollPayload(nextPoll, requestedTicker);
        setPoll(normalized);
        setPollStatus(normalized ? "ready" : "empty");
        setPollReason(normalized ? "" : String(nextPoll?.reason || nextPoll?.status || "NO_CONTEXTUAL_EVENT"));
      })
      .catch((requestError: Error) => {
        if (cancelled) return;
        if (requestError.name === "AbortError") return;
        setPoll(null);
        setPollStatus("error");
        setPollReason(requestError.message || "poll_request_failed");
      });

    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [appLocale, deferredTicker]);

  useEffect(() => {
    if (proModeLocked) {
      setPublicAiCatalog(null);
      return undefined;
    }

    // The endpoint is public at the routing layer, but premium fields are
    // entitlement-gated. Always carry the current token so Trial/Pro users
    // receive the real catalog instead of the anonymous PREMIUM_LOCKED shape.
    let cancelled = false;
    const controller = new AbortController();
    getPublicAiTools(undefined, undefined, undefined, controller.signal, token)
      .then((payload) => {
        if (!cancelled && payload && typeof payload === "object") {
          setPublicAiCatalog(payload);
        }
      })
      .catch(() => {
        if (!cancelled) setPublicAiCatalog(null);
      });
    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [proModeLocked, token]);

  useEffect(() => {
    if (!token) {
      let cancelled = false;
      const controller = new AbortController();
      setLoading(true);
      setError("");
      setAccess(null);
      setWorkspace(null);
      setChart(null);
      setPublicChart((current: any) => (sameChartRequest(current, deferredTicker, chartInterval) ? current : null));
      setFeed(null);
      setRoom(null);
      setPushStatus(null);
      setMediaStatus(null);
      setPublicDataStatus({});

      getPublicMarketBundle(deferredTicker, chartInterval, appLocale, controller.signal)
        .then((bundle) => {
          if (cancelled) return;

          const nextQuote = bundle?.quote || null;
          const nextInsight = bundle?.insight || null;
          const nextChart = bundle?.chart || null;
          const nextNews = !bundle?.news?.locale || bundle.news.locale === appLocale ? bundle.news : null;
          const nextPublicAiTools = bundle?.ai_tools || null;
          setPublicDataStatus(bundle?.data_status || {});
          setPublicMarketMetrics(
            bundle?.market_metrics && sameSymbol(bundle.market_metrics.canonical_symbol, deferredTicker)
              ? bundle.market_metrics
              : null,
          );

          if (nextQuote?.symbol) {
            const normalizedQuoteSymbol = normalizeSymbol(nextQuote.symbol);
            const normalizedQuote = { ...nextQuote, symbol: normalizedQuoteSymbol };
            setPublicQuotes((current) => mergeQuoteState(current, { [normalizedQuoteSymbol]: normalizedQuote }));
            setTickerTapeQuotes((current) => mergeQuoteState(current, { [normalizedQuoteSymbol]: normalizedQuote }));
          }
          setPublicInsight(sameSymbol(nextInsight?.symbol, deferredTicker) ? { ...nextInsight, market_metrics: bundle?.market_metrics || null, symbol: deferredTicker } : null);
          setPublicChart(sameChartRequest(nextChart, deferredTicker, chartInterval) ? { ...nextChart, ticker: deferredTicker } : null);
          setQuote(nextQuote);
          setNews((current) => {
            const currentCount = Number(current?.count ?? current?.items?.length ?? 0);
            const nextCount = Number(nextNews?.count ?? nextNews?.items?.length ?? 0);
            if (sameSymbol(current?.symbol, deferredTicker) && currentCount > 0 && nextCount <= 0) return current;
            return nextNews ?? null;
          });
          setPublicAiTools(nextPublicAiTools);
        })
        .catch((requestError: Error) => {
          if (!cancelled) setError(friendlyNetworkErrorMessage(requestError, appLocale));
        })
        .finally(() => {
          if (!cancelled) setLoading(false);
        });

      const initialQuoteSymbols = Array.from(new Set([...priorityPublicWatchSymbols, ...publicTickerTapeSymbols]));

      getPublicQuotesRobust(publicTickerTapeSymbols, 16, 0)
        .then((nextQuotes) => {
          if (cancelled) return;
          const quoteMap = Object.fromEntries((nextQuotes?.items || []).map((item) => [item.symbol, item]));
          setTickerTapeQuotes((current) => mergeQuoteState(current, quoteMap));
          setPublicQuotes((current) => mergeQuoteState(current, quoteMap));
        })
        .catch(() => undefined);

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
        controller.abort();
        window.clearTimeout(fullWatchlistTimer);
      };
    }
    setPublicQuotes({});
    setPublicInsight(null);
    setPublicMarketMetrics(null);
    setPublicAiTools(null);
    setPublicDataStatus({});

    let cancelled = false;
    const controller = new AbortController();
    setLoading(true);
    setError("");

    // getAccess deliberately removed: entitlement has a single owner and must
    // not wait on chart/news bundles that routinely lose the connection pool.
    getWorkspace(token)
      .then((nextWorkspace) => {
        if (cancelled) return;
        const nextTabs = buildTabs(nextWorkspace.tabs);
        setWorkspace(nextWorkspace);
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
      })
      .catch(() => {
        if (!cancelled) setWorkspace(null);
      });

    getWorkspaceTickerBundle(token, deferredTicker, chartInterval, appLocale, controller.signal)
      .then((nextTickerBundle) => {
        if (cancelled) return;
        setChart(nextTickerBundle.chart || null);
        setFeed(nextTickerBundle.feed || null);
        setNews((current) => {
          const nextNews = nextTickerBundle.news || null;
          const currentCount = Number(current?.count ?? current?.items?.length ?? 0);
          const nextCount = Number(nextNews?.count ?? nextNews?.items?.length ?? 0);
          if (sameSymbol(current?.symbol, deferredTicker) && currentCount > 0 && nextCount <= 0) return current;
          return nextNews;
        });
        setRoom(nextTickerBundle.room || null);
      })
      .catch(() => undefined);

    getPublicMarketBundle(deferredTicker, chartInterval, appLocale, controller.signal, false, token)
      .then((publicBundle) => {
        if (cancelled) return;
        const publicBundleInsight = publicBundle?.insight || null;
        setPublicInsight(
          sameSymbol(publicBundleInsight?.symbol, deferredTicker)
            ? { ...publicBundleInsight, market_metrics: publicBundle?.market_metrics || null, symbol: deferredTicker }
            : null,
        );
        setPublicMarketMetrics(
          publicBundle?.market_metrics && sameSymbol(publicBundle.market_metrics.canonical_symbol, deferredTicker)
            ? publicBundle.market_metrics
            : null,
        );
        setPublicChart(sameChartRequest(publicBundle?.chart, deferredTicker, chartInterval) ? { ...publicBundle.chart, ticker: deferredTicker } : null);
        setPublicDataStatus(publicBundle?.data_status || {});
        setPublicAiTools(publicBundle?.ai_tools || null);
        setQuote(publicBundle?.quote || null);
      })
      .catch((requestError: Error) => {
        if (!cancelled) setError(friendlyNetworkErrorMessage(requestError, appLocale));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [token, deferredTicker, chartInterval, appLocale, focusedTab]);

  useEffect(() => {
    if (!publicHydrationPending) return;

    let cancelled = false;
    const controller = new AbortController();
    const retries = [3000, 5000, 10000];
    const timers = retries.map((delay) =>
      window.setTimeout(() => {
        getPublicMarketBundle(deferredTicker, chartInterval, appLocale, controller.signal, true, token || undefined)
          .then((bundle) => {
            if (cancelled) return;
            const nextQuote = bundle?.quote || null;
            const nextInsight = bundle?.insight || null;
            const nextChart = bundle?.chart || null;
            const nextNews = !bundle?.news?.locale || bundle.news.locale === appLocale ? bundle.news : null;
            const nextPublicAiTools = bundle?.ai_tools || null;
            setPublicDataStatus(bundle?.data_status || {});
            if (bundle?.market_metrics && sameSymbol(bundle.market_metrics.canonical_symbol, deferredTicker)) {
              setPublicMarketMetrics(bundle.market_metrics);
            }
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
                if (!sameSymbol(current?.symbol, deferredTicker)) {
                  return { ...nextInsight, market_metrics: bundle?.market_metrics || null, symbol: deferredTicker };
                }
                return { ...current, ...nextInsight, market_metrics: bundle?.market_metrics || null, symbol: deferredTicker };
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
      controller.abort();
      timers.forEach((timer) => window.clearTimeout(timer));
    };
  }, [
    deferredTicker,
    chartInterval,
    publicHydrationPending,
    publicDataStatusKey,
    appLocale,
    token,
  ]);

  useEffect(() => {
    // "Notícia agora" lives on the grafico tab (default), so the public news
    // fallback must also run there — not only when the news tab is open.
    const activePanel = focusedTab || activeTab;
    const newsCardVisible = activePanel === "news" || activePanel === "grafico";
    const newsReady = sameSymbol(news?.symbol, deferredTicker) && Number(news?.count ?? news?.items?.length ?? 0) > 0;
    if (!newsCardVisible || newsReady) return;

    let cancelled = false;
    const controller = new AbortController();
    const refreshNews = () => {
      getNews(token, deferredTicker, appLocale, true, controller.signal)
        .then((payload) => {
          if (cancelled || !sameSymbol(payload?.symbol, deferredTicker) || (payload.locale && payload.locale !== appLocale)) return;
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
      controller.abort();
      timers.forEach((timer) => window.clearTimeout(timer));
    };
  }, [token, deferredTicker, appLocale, activeTab, focusedTab, news?.symbol, news?.count, news?.items?.length, strategicAnalysisMinute]);

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

      // Ask for every symbol still without a quote. The old numeric cursor walked
      // a list that got shorter on each tick, so whole blocks of the watchlist
      // were skipped and stayed on "sem snapshot". getPublicQuotesRobust already
      // splits this into 24-symbol requests.
      getPublicQuotesRobust(missing, 24, 0)
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

  // Index strip, same 15s cadence as the tape. Inline fetch on purpose: lib/api.ts
  // is owned by another agent this cycle. Anything not status="valid" is dropped so
  // a 404 or a half-filled payload hides the strip instead of rendering zero cards.
  useEffect(() => {
    let cancelled = false;

    const loadIndices = () => {
      fetch(`${resolveApiBase()}/public/market/indices`)
        .then((response) => (response.ok ? response.json() : null))
        .then((payload) => {
          if (cancelled) return;
          const items: IndexStripItem[] = Array.isArray(payload?.items) ? payload.items : [];
          setIndexStrip(
            items.filter(
              (item) =>
                item?.status === "valid" &&
                // typeof, not Number(): Number(null) is 0, which would pass a
                // finite check and render a zero card.
                typeof item?.price === "number" &&
                Number.isFinite(item.price) &&
                item.price !== 0 &&
                Array.isArray(item?.spark) &&
                item.spark.length > 1,
            ),
          );
        })
        .catch(() => {
          if (!cancelled) setIndexStrip([]);
        });
    };

    loadIndices();
    const timer = window.setInterval(loadIndices, 15000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, []);

  useEffect(() => {
    if (!token) return;

    // Cookie sessions authenticate the handshake via the httpOnly cookie;
    // only real bearer tokens (app handoff) travel in the URL.
    const wsQuery = token === COOKIE_SESSION_TOKEN ? "" : `?token=${encodeURIComponent(token)}`;
    const socket = new WebSocket(
      buildWebSocketUrl(`/ws/chat/${encodeURIComponent(deferredTicker)}${wsQuery}`),
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

  function _startResendCooldown(seconds = 60) {
    const deadline = Date.now() + seconds * 1000;
    setResendCooldownUntil(deadline);
    writeStorageValue(CODE_COOLDOWN_STORAGE_KEY, String(deadline));
  }

  async function handleRequestCode() {
    const normalizedEmail = email.trim().toLowerCase();

    if (!normalizedEmail || !normalizedEmail.includes("@")) {
      setLoginError("Informe um e-mail válido.");
      return;
    }

    if (resendCooldownUntil > Date.now()) {
      setLoginError("Muitas tentativas. Aguarde antes de tentar novamente.");
      return;
    }

    try {
      setLoginBusy(true);
      setLoginError("");
      setLoginNotice("Enviando código...");
      const payload = await requestLoginCode(normalizedEmail, {
        device_id: getBrowserDeviceId(),
        device_label: getBrowserDeviceLabel(),
      });

      setPendingLoginToken(payload.login_token || "");
      setOtpCode("");
      setLoginNotice("Se o e-mail estiver apto, enviaremos um código de acesso.");
      _startResendCooldown(60);
    } catch (requestError) {
      setLoginNotice("");
      const raw = requestError instanceof Error ? requestError.message : "";
      if (raw.includes("Muitas tentativas")) {
        setLoginError("Muitas tentativas. Aguarde antes de tentar novamente.");
        _startResendCooldown(60);
      } else {
        setLoginError(friendlyAuthErrorMessage(requestError, appLocale));
      }
    } finally {
      setLoginBusy(false);
    }
  }

  async function handleVerifyOtp() {
    try {
      setLoginBusy(true);
      setLoginError("");
      setLoginNotice("Verificando...");
      const payload = await verifyLoginOtp(pendingLoginToken, otpCode.trim());

      // Web login: the session token lives in an httpOnly cookie; the JSON
      // payload intentionally carries no token.
      const nextToken = payload.access_token || COOKIE_SESSION_TOKEN;
      setToken(nextToken);
      setPendingLoginToken("");
      setOtpCode("");
      setLoginNotice("");
    } catch (requestError) {
      setLoginNotice("");
      setLoginError(friendlyAuthErrorMessage(requestError, appLocale));
    } finally {
      setLoginBusy(false);
    }
  }

  function _clearAuthState() {
    removeStorageValue("stocknewsbr.token");
    setToken("");
    setAccess(null);
    setWorkspace(null);
    setPendingLoginToken("");
    setOtpCode("");
    setLoginNotice("");
    setEmailChangeInput("");
    setEmailChangeToken("");
    setEmailChangeCode("");
    setEmailChangeNotice("");
    setTelegramLink(null);
  }

  async function handleLogout() {
    if (token) {
      try {
        await logoutAuth(token);
      } catch {
        // Best effort local cleanup.
      }
    }

    _clearAuthState();
    setLoginError("");
    setLoginNotice("Sessão encerrada.");
  }

  async function handleLogoutAll() {
    if (!token) return;

    try {
      await logoutAllAuth(token);
    } catch {
      // Best effort local cleanup.
    }

    _clearAuthState();
    setLoginError("");
    setLoginNotice("Sessão encerrada em todos os dispositivos.");
  }

  async function handleRequestEmailChange() {
    if (!token) return;
    const normalized = emailChangeInput.trim().toLowerCase();

    if (!normalized || !normalized.includes("@")) {
      setEmailChangeNotice("Informe um e-mail válido.");
      return;
    }

    try {
      setEmailChangeNotice("Enviando código...");
      const payload = await requestEmailChange(token, normalized);
      setEmailChangeToken(payload.login_token || "");
      setEmailChangeCode("");
      setEmailChangeNotice("Se o e-mail informado estiver apto, enviaremos um código de confirmação.");
    } catch (requestError) {
      setEmailChangeToken("");
      setEmailChangeNotice(friendlyAuthErrorMessage(requestError, appLocale));
    }
  }

  async function handleVerifyEmailChange() {
    if (!token || !emailChangeToken) return;

    try {
      setEmailChangeNotice("Verificando...");
      const nextAccess = await verifyEmailChange(token, emailChangeToken, emailChangeCode.trim());
      startTransition(() => {
        setAccess(nextAccess);
        setEmailChangeInput("");
        setEmailChangeToken("");
        setEmailChangeCode("");
        setEmailChangeNotice("E-mail alterado com sucesso.");
      });
    } catch (requestError) {
      setEmailChangeNotice(friendlyAuthErrorMessage(requestError, appLocale));
    }
  }

  async function handleTelegramLinkRequest() {
    if (!token) return;

    try {
      setLoginError("");
      const payload = await requestTelegramLink(token, "web");
      setTelegramLink(payload);
    } catch (requestError) {
      setLoginError(friendlyNetworkErrorMessage(requestError, appLocale));
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

      // Mission 31B: e-mail changes go through the verified
      // /auth/email-change flow — never through profile updates.
      const nextAccess = await updateProfile(token, {
        display_name: profileNameInput || null,
        avatar_url: nextAvatarUrl,
      });

      startTransition(() => {
        setAccess(nextAccess);
        setProfileAvatarUrl(nextAccess.avatar_url || "");
        setProfileFile(null);
      });

      if (profileFileInputRef.current) {
        profileFileInputRef.current.value = "";
      }
    } catch (requestError) {
      setLoginError(friendlyNetworkErrorMessage(requestError, appLocale));
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
        show_macd: chartSettings?.show_macd ?? workspace?.layout?.chart_settings?.show_macd ?? showMacd,
        show_rsi: chartSettings?.show_rsi ?? workspace?.layout?.chart_settings?.show_rsi ?? showRsi,
        show_support: chartSettings?.show_support ?? workspace?.layout?.chart_settings?.show_support ?? showSupport,
        show_resistance: chartSettings?.show_resistance ?? workspace?.layout?.chart_settings?.show_resistance ?? showResistance,
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
      setError(friendlyNetworkErrorMessage(requestError, appLocale));
    }
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
    if (key === "show_macd") {
      setShowMacd(value);
    }
    if (key === "show_rsi") {
      setShowRsi(value);
    }
    if (key === "show_support") {
      setShowSupport(value);
    }
    if (key === "show_resistance") {
      setShowResistance(value);
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
      setPublicChart(null);
      setFeed(null);
      setNews(null);
      setPoll(null);
      setPollStatus("loading");
      setPollReason("");
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
        const nextQuotes = await getPublicQuotesRobust([symbol], 1, 1);
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
        const nextQuotes = await getPublicQuotesRobust([symbol], 1, 1);
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
      canonicalUniverse.find((item) => item.symbol === symbol) ||
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

    setRemovedWatchSymbols((current) => current.filter((item) => normalizeSymbol(item) !== symbol));
    selectTicker(symbol);
  }

  function handleRemoveFromActiveList(symbolToRemove = selectedTicker) {
    const normalized = normalizeSymbol(symbolToRemove);
    const next = activeWatchSymbols.filter((symbol) => normalizeSymbol(symbol) !== normalized);
    if (!normalized || !next.length) return;
    setRemovedWatchSymbols((current) => Array.from(new Set([...current, normalized])));
    if (normalized === selectedTicker) {
      const fallbackSymbol = next[0];
      aiSoundSuppressedUntilRef.current = Date.now() + 1500;
      startTransition(() => {
        setSelectedTicker(fallbackSymbol);
        setTickerInput(fallbackSymbol);
      });
      void persistLayout(tabs, undefined, fallbackSymbol);
    }
  }

  function promptLogin(actionLabel = "usar este recurso") {
    const message = `Faça login para ${actionLabel}.`;
    setLoginError(message);
    setError(message);
    // Remember what opened the dialog so focus can be handed back on close.
    if (typeof document !== "undefined") {
      loginDialogReturnRef.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    }
    setLoginModalOpen(true);
  }

  function closeLoginDialog() {
    setLoginModalOpen(false);
    setLoginNotice("");
    const target = loginDialogReturnRef.current;
    loginDialogReturnRef.current = null;
    window.setTimeout(() => target?.focus?.(), 0);
  }

  async function handleCreatePost() {
    if (!token) {
      promptLogin("publicar");
      return;
    }
    if (!postText.trim() && !selectedGif && !postFile) return;

    try {
      setPosting(true);
      let imageUrl: string | null = selectedGif?.media_url || null;

      if (postFile) {
        const upload = await uploadMedia(token, postFile);
        imageUrl = upload.url;
      }

      await createPost(token, selectedTicker, {
        text: applyEmojiShortcuts(postText),
        sentiment: postSentiment,
        image_url: imageUrl,
      });

      const nextFeed = await getFeed(token, selectedTicker);
      startTransition(() => {
        setFeed(nextFeed);
        setPostText("");
        setPostFile(null);
        setSelectedGif(null);
        setComposerEmojiOpen(false);
        setComposerGifOpen(false);
      });
      if (composerFileInputRef.current) composerFileInputRef.current.value = "";
    } catch (requestError) {
      setError(friendlyNetworkErrorMessage(requestError, appLocale));
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

    if (pendingLikePostIdsRef.current.has(post.id)) return;
    pendingLikePostIdsRef.current.add(post.id);
    setPendingLikePostIds(new Set(pendingLikePostIdsRef.current));

    try {
      let result;
      if (post.liked_by_me) {
        result = await unlikePost(token, post.id);
      } else {
        result = await likePost(token, post.id);
      }

      const updatePost = (item: FeedPost) => item.id === post.id
        ? { ...item, likes: result.likes, liked_by_me: !post.liked_by_me }
        : item;
      setFeed((current) => current ? {
        ...current,
        posts: current.posts.map(updatePost),
        featured_posts: current.featured_posts?.map(updatePost),
      } : current);
      await refreshFeedState();
    } catch (requestError) {
      setError(friendlyNetworkErrorMessage(requestError, appLocale));
    } finally {
      pendingLikePostIdsRef.current.delete(post.id);
      setPendingLikePostIds(new Set(pendingLikePostIdsRef.current));
    }
  }

  function updateCommentComposer(postId: number, patch: Partial<CommentComposerState>) {
    setCommentComposers((current) => {
      const existing = current[postId] || {
        active: false,
        sentiment: "bullish",
        file: null,
        previewUrl: null,
        gif: null,
        tool: null,
        error: "",
      };
      return { ...current, [postId]: { ...existing, ...patch } };
    });
  }

  function activateCommentComposer(postId: number) {
    updateCommentComposer(postId, { active: true });
    window.setTimeout(() => {
      document.querySelector<HTMLInputElement>(`[data-comment-input="${postId}"]`)?.focus();
    }, 0);
  }

  function selectCommentFile(postId: number, file: File | null) {
    const previous = commentComposers[postId]?.previewUrl;
    if (previous?.startsWith("blob:")) URL.revokeObjectURL(previous);
    updateCommentComposer(postId, {
      active: true,
      file,
      gif: null,
      previewUrl: file ? URL.createObjectURL(file) : null,
      error: "",
    });
  }

  async function handleComment(postId: number) {
    if (!token) {
      promptLogin("comentar");
      return;
    }

    const composer = commentComposers[postId];
    const text = (commentDrafts[postId] || "").trim();
    if (!text && !composer?.file && !composer?.gif) return;

    try {
      setCommentingPostId(postId);
      updateCommentComposer(postId, { error: "" });
      let imageUrl = composer?.gif?.media_url || null;
      if (composer?.file) {
        const upload = await uploadMedia(token, composer.file);
        imageUrl = upload.url;
      }
      const sentiment = composer?.sentiment === "bearish" ? "🐻" : "🐂";
      const comment = await commentOnPost(token, postId, {
        text: `${sentiment} ${applyEmojiShortcuts(text)}`.trim(),
        image_url: imageUrl,
      });
      const appendComment = (post: FeedPost) => post.id === postId
        ? { ...post, comments: [...(post.comments || []), comment] }
        : post;
      setFeed((current) => current ? {
        ...current,
        posts: current.posts.map(appendComment),
        featured_posts: current.featured_posts?.map(appendComment),
      } : current);
      startTransition(() => {
        setCommentDrafts((current) => ({ ...current, [postId]: "" }));
      });
      if (composer?.previewUrl?.startsWith("blob:")) URL.revokeObjectURL(composer.previewUrl);
      updateCommentComposer(postId, { file: null, gif: null, previewUrl: null, tool: null, error: "" });
      if (commentFileInputRefs.current[postId]) commentFileInputRefs.current[postId]!.value = "";
      await refreshFeedState();
    } catch (requestError) {
      const message = friendlyNetworkErrorMessage(requestError, appLocale);
      updateCommentComposer(postId, { error: message });
      setError(message);
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
      setBlockedUsers((current) => rememberUser(current, buildUserListEntry(post.user_id, publicSocialName(post.user), null, post.user_avatar_url)));
      await refreshFeedState();
    } catch (requestError) {
      setError(friendlyNetworkErrorMessage(requestError, appLocale));
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
      setError(friendlyNetworkErrorMessage(requestError, appLocale));
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
      setSilencedUsers((current) => rememberUser(current, buildUserListEntry(post.user_id, publicSocialName(post.user), null, post.user_avatar_url)));
    } catch (requestError) {
      setError(friendlyNetworkErrorMessage(requestError, appLocale));
    }
  }

  function openReportDialog(post: FeedPost) {
    if (!token) {
      promptLogin("denunciar posts");
      return;
    }
    setReportTargetPost(post);
    setReportReason("spam");
    setReportNote("");
    setPostMenuId(null);
  }

  async function handleReport(postId: number, reason = reportReason, note = reportNote) {
    if (!token) {
      promptLogin("denunciar posts");
      return;
    }

    try {
      setReportingPostId(postId);
      await reportPost(token, postId, reason, note || null);
      setPostMenuId(null);
      setReportTargetPost(null);
      setReportNote("");
      await refreshFeedState();
    } catch (requestError) {
      setError(friendlyNetworkErrorMessage(requestError, appLocale));
    } finally {
      setReportingPostId(null);
    }
  }

  async function handleReportAndBlock(postId: number, post: FeedPost) {
    if (!token) {
      promptLogin("reportar e bloquear");
      return;
    }

    try {
      await reportPost(token, postId, "golpe", "report_and_block");
      await blockUser(token, post.user_id);
      setPostMenuId(null);
      setBlockedUsers((current) => rememberUser(current, buildUserListEntry(post.user_id, publicSocialName(post.user), null, post.user_avatar_url)));
      await refreshFeedState();
    } catch (requestError) {
      setError(friendlyNetworkErrorMessage(requestError, appLocale));
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
      setError(friendlyNetworkErrorMessage(requestError, appLocale));
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
      setFeed((current) => current ? {
        ...current,
        count: Math.max(0, current.count - Number(current.posts.some((post) => post.id === postId))),
        posts: current.posts.filter((post) => post.id !== postId),
        featured_posts: current.featured_posts?.filter((post) => post.id !== postId),
      } : current);
      await refreshFeedState();
    } catch (requestError) {
      setError(friendlyNetworkErrorMessage(requestError, appLocale));
    }
  }

  function appendComposerEmoji(emoji: string) {
    setPostText((current) => `${current}${current ? " " : ""}${emoji}`);
    const nextRecents = [emoji, ...recentComposerEmojis.filter((item) => item !== emoji)].slice(0, 10);
    setRecentComposerEmojis(nextRecents);
    writeStorageValue(RECENT_EMOJIS_STORAGE_KEY, JSON.stringify(nextRecents));
    setComposerEmojiOpen(false);
  }

  async function handleGifSearch(term?: string) {
    if (!token) {
      promptLogin(isUsLocale ? "search GIFs" : "buscar GIFs");
      return;
    }
    const query = (term?.trim() || gifQuery.trim() || `${selectedTicker} stock market`).replace(/\s+/g, " ");
    setGifQuery(query);
    gifSearchAbortRef.current?.abort();
    const controller = new AbortController();
    gifSearchAbortRef.current = controller;
    setGifSearchStatus("loading");
    setGifSearchReason("");
    try {
      const payload = await searchGifs(token, query, appLocale, controller.signal);
      if (controller.signal.aborted) return;
      setGifResults(payload.items || []);
      setGifSearchReason(payload.reason || "");
      setGifSearchStatus(
        payload.status === "READY"
          ? (payload.items?.length ? "ready" : "empty")
          : payload.status === "UNAVAILABLE"
            ? "unavailable"
            : payload.status === "ERROR"
              ? "error"
              : "empty"
      );
    } catch (requestError) {
      if (controller.signal.aborted) return;
      setGifResults([]);
      setGifSearchStatus("error");
      setGifSearchReason(friendlyNetworkErrorMessage(requestError, appLocale));
    }
  }

  function selectComposerGif(item: GifSearchItem) {
    setSelectedGif(item);
    setPostFile(null);
    if (composerFileInputRef.current) composerFileInputRef.current.value = "";
    setComposerGifOpen(false);
  }

  function toggleComposerGifPicker() {
    const opening = !composerGifOpen;
    setComposerGifOpen(opening);
    setComposerEmojiOpen(false);
    if (opening && gifSearchStatus === "idle") void handleGifSearch();
  }

  function renderComposerGifPicker(onSelect: (item: GifSearchItem) => void = selectComposerGif) {
    if (gifSearchStatus === "unavailable") {
      return <div className="snbr-gif-picker"><p className="snbr-muted" role="status">{isUsLocale ? "GIF search is currently unavailable" : "Busca de GIF indisponível no momento"}</p></div>;
    }
    return (
      <div className="snbr-gif-picker" aria-label={isUsLocale ? "Select GIF" : "Selecionar GIF"}>
        <div className="snbr-gif-search">
          <input
            className="snbr-input"
            value={gifQuery}
            onChange={(event) => setGifQuery(event.target.value)}
            placeholder={isUsLocale ? `Search GIF: ${selectedTicker}` : `Buscar GIF: ${selectedTicker}`}
          />
          <button className="snbr-button subtle" onClick={() => void handleGifSearch()} type="button">
            {gifSearchStatus === "loading" ? (isUsLocale ? "Searching..." : "Buscando...") : isUsLocale ? "Search" : "Buscar"}
          </button>
        </div>
        <div className="snbr-gif-quick-grid">
          {QUICK_GIF_TERMS.map((term) => (
            <button key={term} className="snbr-gif-chip" onClick={() => void handleGifSearch(term)} type="button">
              {term}
            </button>
          ))}
        </div>
        {gifSearchStatus === "ready" ? (
          <div className="snbr-gif-results">
            {gifResults.map((item) => (
              <button key={item.id || item.media_url} className="snbr-gif-result" onClick={() => onSelect(item)} type="button">
                <img src={item.preview_url} alt={item.title} loading="lazy" />
              </button>
            ))}
          </div>
        ) : null}
        {["empty", "unavailable", "error"].includes(gifSearchStatus) ? (
          <p className="snbr-muted" role="status">{gifSearchReason || (isUsLocale ? "No GIFs available." : "Nenhum GIF disponível.")}</p>
        ) : null}
      </div>
    );
  }

  function renderComposerEmojiPicker(onSelect: (emoji: string) => void = appendComposerEmoji) {
    const sections = [
      ...(recentComposerEmojis.length
        ? [{ key: "recents", label: isUsLocale ? "Recent" : "Recentes", emojis: recentComposerEmojis }]
        : []),
      ...COMPOSER_EMOJI_CATEGORIES.map((category) => ({
        key: category.key,
        label: isUsLocale ? category.labelEn : category.labelPt,
        emojis: category.emojis,
      })),
    ];
    return (
      <div className="snbr-emoji-picker" aria-label={isUsLocale ? "Select emoji" : "Selecionar emoji"}>
        {sections.map((section) => (
          <div key={section.key} className="snbr-emoji-section">
            <span className="snbr-emoji-section-label">{section.label}</span>
            <div className="snbr-emoji-grid">
              {section.emojis.map((emoji) => (
                <button key={`${section.key}-${emoji}`} className="snbr-emoji-option" onClick={() => onSelect(emoji)} type="button">
                  {emoji}
                </button>
              ))}
            </div>
          </div>
        ))}
      </div>
    );
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
      setError(friendlyNetworkErrorMessage(requestError, appLocale));
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
      setError(friendlyNetworkErrorMessage(requestError, appLocale));
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
      setError(friendlyNetworkErrorMessage(requestError, appLocale));
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

  const activeChart = useMemo(
    () => {
      const liveChart = sameChartRequest(chart, selectedTicker, chartInterval) ? chart : null;
      const guestChart = sameChartRequest(publicChart, selectedTicker, chartInterval) ? publicChart : null;
      return guestChart || liveChart;
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
    () => buildWatchlist(rankingRows, radarRows, activeQuote, mergedQuoteMap, publicInsight, selectedTicker, customWatchItems, canonicalUniverse),
    [rankingRows, radarRows, activeQuote, mergedQuoteMap, publicInsight, selectedTicker, customWatchItems, canonicalUniverse],
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
      canonicalUniverse,
    );
    const activeSet = new Set(
      (activeWatchSymbols.length ? activeWatchSymbols : canonicalUniverse.map((item) => item.symbol))
        .map(normalizeSymbol)
        .filter(Boolean),
    );
    const bySymbol = new Map(liveWatchlist.map((item) => [item.symbol, item]));

    for (const item of [...canonicalUniverse, ...customWatchItems]) {
      if (isRemovedFutureSymbol(item.symbol)) continue;
      if (!activeSet.has(normalizeSymbol(item.symbol))) continue;
      if (!bySymbol.has(item.symbol)) {
        bySymbol.set(item.symbol, { ...item });
      }
    }

    return Array.from(bySymbol.values()).filter((item) => activeSet.has(normalizeSymbol(item.symbol)));
  }, [
    rankingRows,
    radarRows,
    activeQuote,
    mergedQuoteMap,
    publicInsight,
    selectedTicker,
    customWatchItems,
    activeWatchSymbols,
    canonicalUniverse,
  ]);
  const filteredActiveWatchlist = useMemo(
    () => sortWatchlistItemsAlphabetically(
      activeWatchlist.filter((item) => watchCategory === "Todos" || item.category === watchCategory),
      appLocale,
    ),
    [activeWatchlist, appLocale, watchCategory],
  );
  const activeWatchCategoryCounts = useMemo(
    () => CATEGORY_ORDER.reduce((counts, category) => {
      counts[category] = activeWatchlist.filter((item) => item.category === category).length;
      return counts;
    }, {} as Record<(typeof CATEGORY_ORDER)[number], number>),
    [activeWatchlist],
  );
  const activeWatchCountForFilter = useMemo(
    () => (watchCategory === "Todos"
      ? CATEGORY_ORDER.reduce((total, category) => total + (activeWatchCategoryCounts[category] || 0), 0)
      : activeWatchCategoryCounts[watchCategory] || 0),
    [activeWatchCategoryCounts, watchCategory],
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
  const currentTopSignal = useMemo(
    () => radarRows.find((item) => normalizeSymbol(item.ticker || item.symbol || "") === selectedTicker),
    [radarRows, selectedTicker],
  );
  const workspaceSymbolSnapshot = useMemo<CanonicalSnapshotRow | null>(() => {
    const snapshots = workspace?.symbol_snapshots || {};
    const direct = snapshots[selectedTicker] || snapshots[selectedTicker.toUpperCase()];
    return direct ? (direct as CanonicalSnapshotRow) : null;
  }, [workspace?.symbol_snapshots, selectedTicker]);
  const currentSnapshotRow = useMemo<CanonicalSnapshotRow | null>(() => {
    const candidates = [workspaceSymbolSnapshot, currentRanking, currentTopSignal] as Array<
      CanonicalSnapshotRow | null | undefined
    >;
    return candidates.find(snapshotHasCoreData) || candidates.find(Boolean) || null;
  }, [currentRanking, currentTopSignal, workspaceSymbolSnapshot]);
  const currentStrategicPanel = useMemo<StrategicPanel | null>(() => {
    const currentPublicPanel = sameSymbol(publicInsight?.symbol, selectedTicker) ? publicInsight?.strategic_panel : null;
    if (currentPublicPanel && typeof currentPublicPanel === "object") return currentPublicPanel as StrategicPanel;
    return null;
  }, [publicInsight, selectedTicker]);
  const canonicalAnalysis = currentStrategicPanel?.canonical_analysis || null;
  const snapshotQuote = useMemo(
    () => snapshotQuoteFromRow(selectedTicker, currentSnapshotRow),
    [currentSnapshotRow, selectedTicker],
  );
  const currentWatchItem = useMemo(() => watchUniverse.find((item) => item.symbol === selectedTicker), [watchUniverse, selectedTicker]);
  const currentPublicQuote = resolveQuoteForSymbol(selectedTicker, publicQuotes, tickerTapeQuotes);
  const displayQuote = quoteHasMarketValue(activeQuote)
    ? activeQuote
      : quoteHasMarketValue(snapshotQuote)
        ? snapshotQuote
      : quoteHasMarketValue(currentPublicQuote)
        ? currentPublicQuote
        : currentPublicQuote || activeQuote || snapshotQuote || null;
  const backendQuoteCoreData = typeof displayQuote?.core_data === "boolean" ? displayQuote.core_data : null;
  const displayQuoteHasCoreData = backendQuoteCoreData === false
    ? false
    : quoteHasMarketValue(displayQuote) && firstPositiveFiniteNumber(displayQuote?.volume) != null;
  const currentPublicInsight = normalizeSymbol(publicInsight?.symbol || "") === selectedTicker ? publicInsight : null;
  useEffect(() => {
    if (token || quoteHasMarketValue(currentPublicQuote)) return;

    let cancelled = false;
    const retryDelays = [1800, 6000];
    const timers = retryDelays.map((delay) =>
      window.setTimeout(() => {
        getPublicQuotesRobust([deferredTicker], 1, 1)
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
  const derivedPublicInsight = useMemo<PublicInsightPayload | null>(() => {
    if (!displayQuoteHasCoreData) return null;
    return currentPublicInsight;
  }, [currentPublicInsight, displayQuoteHasCoreData]);
  const chartForDisplay = useMemo(() => {
    const hasLiveSeries = Boolean(activeChart?.ohlc?.length || activeChart?.series?.length);
    return hasLiveSeries && activeChart && sameChartRequest(activeChart, selectedTicker, chartInterval) ? activeChart : null;
  }, [
    activeChart,
    chartInterval,
    selectedTicker,
  ]);
  const assetMetrics = publicMarketMetrics && sameSymbol(publicMarketMetrics.canonical_symbol, selectedTicker)
    ? publicMarketMetrics
    : null;
  const symbolOperationalView = assetMetrics?.operational_view || null;
  const operationalBlockComponents = (symbolOperationalView?.operational_blocks || []).map((item) => ({
    rvol: isUsLocale ? "comparable intraday RVOL" : "RVOL intraday comparável",
    intraday_rvol: isUsLocale ? "comparable intraday RVOL" : "RVOL intraday comparável",
    flow: isUsLocale ? "flow" : "fluxo",
    liquidity: isUsLocale ? "validated liquidity" : "liquidez validada",
    levels: isUsLocale ? "valid operational levels" : "níveis operacionais válidos",
  }[item.component] || item.component));
  const executionMetricsReady = Boolean(symbolOperationalView && operationalBlockComponents.length === 0);
  const chartCanonicalLevelZones = useMemo(
    () => resolveCanonicalChartLevelZones(chartForDisplay),
    [chartForDisplay],
  );
  const chartForOperationalLevels = useMemo(
    () => chartForDisplay ? { ...chartForDisplay, zones: chartCanonicalLevelZones } : chartForDisplay,
    [chartForDisplay, chartCanonicalLevelZones],
  );
  const chartSupportResistanceLevels = useMemo(() => ({
    resistance: chartCanonicalLevelZones.find((zone: any) => zone.kind === "resistance")?.price ?? null,
    support: chartCanonicalLevelZones.find((zone: any) => zone.kind === "support")?.price ?? null,
    zones: chartCanonicalLevelZones,
  }), [chartCanonicalLevelZones]);
  const chartMicroRange = useMemo(() => {
    const zones = (chartForDisplay?.zones || []).filter((zone: any) => zone?.status === "INSUFFICIENT_SEPARATION");
    const support = zones.find((zone: any) => zone.kind === "support")?.price;
    const resistance = zones.find((zone: any) => zone.kind === "resistance")?.price;
    return support != null && resistance != null ? { support, resistance, timeframe: zones[0]?.micro_timeframe || chartInterval } : null;
  }, [chartForDisplay?.zones, chartInterval]);
  const operationalLevelsStatus = String(assetMetrics?.levels?.status || "PENDING").toUpperCase();
  // The selected-symbol bundle is the only source for Score Mestre.
  const effectiveAiScore = useMemo(
    () => {
      if (!displayQuoteHasCoreData) return null;
      return firstFiniteNumber(symbolOperationalView?.operational_context.master_score?.value);
    },
    [displayQuoteHasCoreData, symbolOperationalView],
  );
  // ONE RSI for every surface (top card, chart chip, bottom panel): the daily
  // RSI-14 served by /public/market/bundle (insight.rsi, canonical_indicator_engine).
  // Snapshot/ranking RSI is only a fallback when the bundle has no value.
  const panelRsiValue = useMemo(
    () =>
      displayQuoteHasCoreData
        ? firstValidRsiNumber(symbolOperationalView?.technical_context.rsi_d1?.value,
            currentPublicInsight?.rsi,
          )
        : null,
    [currentPublicInsight?.rsi, displayQuoteHasCoreData, symbolOperationalView],
  );
  // Mission 68: the chart chip + RSI panel follow the SELECTED timeframe, computed on
  // the exact chart candle series (activeChart is gated on ticker+interval, so it clears
  // on a switch). Feature-detect the field; fall back to the D1 panel value on old payloads.
  const chartTimeframeRsi = useMemo(() => {
    if (activeChart && Object.prototype.hasOwnProperty.call(activeChart, "rsi")) {
      return firstValidRsiNumber((activeChart as any).rsi);
    }
    return panelRsiValue;
  }, [activeChart, panelRsiValue]);
  const chartRsiMetadata = useMemo(() => {
    if (activeChart && Object.prototype.hasOwnProperty.call(activeChart, "rsi")) {
      return (activeChart as any).rsi_metadata || null;
    }
    return currentPublicInsight?.rsi_metadata || derivedPublicInsight?.rsi_metadata || null;
  }, [activeChart, currentPublicInsight?.rsi_metadata, derivedPublicInsight?.rsi_metadata]);
  // The label must state the candles the RSI was actually computed on, which the
  // backend reports in rsi_metadata. The range button ("1D" = one day of 5m candles)
  // is NOT the candle size, so it must never be used as the tag.
  const rsiTimeframeLabel = rsiTimeframeTag(chartRsiMetadata);
  const cardRsiTimeframeLabel = rsiTimeframeTag(
    currentPublicInsight?.rsi_metadata || derivedPublicInsight?.rsi_metadata || null,
  );
  const priceMovementValue = firstFiniteNumber(displayQuote?.change) ?? null;
  const priceMovementPercent = firstFiniteNumber(displayQuote?.change_pct) ?? null;
  const headerVolume = firstPositiveFiniteNumber(displayQuote?.volume);
  const backendMissingFields = useMemo(() => {
    const reported = quoteMissingFieldsForUi(displayQuote);
    if (reported.length > 0) return reported;
    // A panel that says "no data" without naming a single missing field explains
    // nothing. When the backend returns no diagnostics at all (empty or timed-out
    // payload) derive them from the canonical core fields so the contract
    // "core_data=false => campos faltantes" always holds.
    if (displayQuoteHasCoreData) return reported;
    return CORE_QUOTE_FIELD_IDS.filter(
      (field) => firstFiniteNumber((displayQuote as any)?.[field]) == null,
    );
  }, [displayQuote, displayQuoteHasCoreData]);
  const backendMissingFieldLabels = useMemo(
    () => backendMissingFields.map((field) => quoteMissingFieldLabel(field, appLocale)),
    [appLocale, backendMissingFields],
  );
  const symbolLabel = displayWatchlistLabel({ symbol: selectedTicker, label: currentWatchItem?.label }, appLocale);
  const symbolLogoUrl = safeAssetLogoUrl(displayQuote?.logo_url, displayQuote?.icon_url, currentWatchItem?.logoUrl);
  const selectedTickerMarketLabel = currentWatchItem?.category || guessCategory(selectedTicker);
  const currentAiKey = AI_TOOL_TAB_MAP[currentTab as keyof typeof AI_TOOL_TAB_MAP];
  const aiPayloadLocked = Boolean(
    publicAiTools?.locked ||
      publicAiCatalog?.locked ||
      String(publicAiTools?.status || "").toUpperCase() === "PREMIUM_LOCKED" ||
      String(publicAiCatalog?.status || "").toUpperCase() === "PREMIUM_LOCKED",
  );
  const aiAccessLocked = proModeLocked || aiPayloadLocked;
  const currentAiRows: AiToolRow[] = useMemo(
    () => {
      if (!currentAiKey || aiAccessLocked) return [];
      const publicForSelected = normalizeSymbol(String(publicAiTools?.selected_symbol || publicAiTools?.symbol || "")) === selectedTicker;
      return (publicForSelected ? publicAiTools?.tools?.[currentAiKey] : workspace?.ai_tools?.[currentAiKey] || publicAiTools?.tools?.[currentAiKey]) || [];
    },
    [aiAccessLocked, currentAiKey, publicAiTools?.selected_symbol, publicAiTools?.symbol, publicAiTools?.tools, selectedTicker, workspace?.ai_tools],
  );
  useEffect(() => {
    if (!currentAiKey) return undefined;
    const key = `${selectedTicker}|${currentAiKey}|${chartInterval}|${aiRequestNonce}`;
    if (proModeLocked) {
      setPublicAiTools(null);
      setAiRequestState({
        key,
        status: "PREMIUM_LOCKED",
        reason: token ? "premium_plan_required" : "authentication_required",
      });
      return undefined;
    }

    const controller = new AbortController();
    setAiRequestState({ key, status: "LOADING", reason: "" });
    getPublicAiTools(selectedTicker, currentAiKey, chartInterval, controller.signal, token)
      .then((payload) => {
        if (controller.signal.aborted) return;
        setPublicAiTools(payload);
        setAiRequestState({ key, status: payload.status || "READY", reason: payload.reason || "" });
      })
      .catch((requestError: Error) => {
        if (controller.signal.aborted) return;
        setPublicAiTools(null);
        setAiRequestState({ key, status: "ERROR", reason: requestError.message || "ai_request_failed" });
      });
    return () => controller.abort();
  }, [aiRequestNonce, chartInterval, currentAiKey, proModeLocked, selectedTicker, token]);
  const aiToolFindingCounts = useMemo(() => {
    const counts: Record<string, number> = {};
    if (aiAccessLocked) {
      Object.keys(AI_TOOL_TAB_MAP).forEach((tabId) => {
        counts[tabId] = 0;
      });
      return counts;
    }
    for (const [tabId, toolKey] of Object.entries(AI_TOOL_TAB_MAP)) {
      const typedKey = toolKey as keyof WorkspaceData["ai_tools"];
      const globalScope = GLOBAL_AI_ALERT_TAB_IDS.has(tabId);
      const rows = globalScope
        ? (publicAiCatalog?.tools?.[typedKey] || [])
        : [
            ...(workspace?.ai_tools?.[typedKey] || []),
            ...(publicAiTools?.tools?.[typedKey] || []),
          ];
      const unique = new Set<string>();
      rows.forEach((row) => {
        const ticker = normalizeSymbol(String((row as any).ticker || (row as any).symbol || ""));
        if (!ticker || (!globalScope && ticker !== selectedTicker)) return;
        const candidate = { ...(row as AiToolRow), tool: toolKey, ticker };
        if (!isFreshAiFindingForReset(candidate)) return;
        if (!isAiDealFinding(candidate)) return;
        unique.add(aiAlertSignalKey(candidate));
      });
      counts[tabId] = unique.size;
      if (!globalScope && !counts[tabId]) {
        // No fresh finding for the selected ticker: fall back to the real
        // per-tool count from the unfiltered public catalog (anonymous only).
        counts[tabId] = (publicAiCatalog?.tools?.[typedKey] || []).length;
      }
    }
    return counts;
  }, [aiAccessLocked, publicAiCatalog?.tools, publicAiTools?.tools, selectedTicker, workspace?.ai_tools]);
  const aiFindingSignalKey = useMemo(() => {
    if (aiAccessLocked) return "";
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
        if (!isFreshAiFindingForReset(candidate)) return;
        if (!isAiDealFinding(candidate)) return;
        signatures.push(aiAlertComparableSignature(candidate));
      });
    }
    return Array.from(new Set(signatures)).sort().join("||");
  }, [aiAccessLocked, aiToolSoundSettings, publicAiTools?.tools, workspace?.ai_tools]);
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
      const sortedTickerNews = ([...(activeNews?.items || [])] as NewsItem[])
        .filter((item) => newsMatchesSelectedTicker(item, selectedTicker))
        .sort((a, b) => {
          const bTime = Date.parse(newsSourceTimestamp(b) || "");
          const aTime = Date.parse(newsSourceTimestamp(a) || "");
          if (Number.isFinite(bTime) && Number.isFinite(aTime) && bTime !== aTime) return bTime - aTime;
          if (Number.isFinite(bTime)) return -1;
          if (Number.isFinite(aTime)) return 1;
          return String(a.id || "").localeCompare(String(b.id || ""));
        });
      const matchedNews = dedupeNewsForTicker(
        sortedTickerNews,
        selectedTicker,
      );
      return matchedNews.map((item, index) => {
        const publishedAtIso = newsSourceTimestamp(item);
        const publishedTime = formatNewsClock(publishedAtIso, appLocale);
        const ageMinutes = Number.isFinite(Number(item.age_minutes)) ? Number(item.age_minutes) : null;
        const age = formatNewsAge(ageMinutes, publishedAtIso, appLocale);
        const sourceName = item.source_name || item.source || "Yahoo Finance";
        const sourceUrl = validExternalNewsUrl(item.source_url || item.url || null) || null;
        const itemUrl = validExternalNewsUrl(item.url || item.source_url || null) || null;
        const matchedSymbol = normalizeSymbol(item.matched_symbol || item.ticker || selectedTicker) || selectedTicker;
        const isToday = typeof item.is_today === "boolean" ? item.is_today : sourceDateIsToday(publishedAtIso);
        const isStale = typeof item.is_stale === "boolean" ? item.is_stale : !isToday;
        const freshnessBucket = typeof item.freshness_bucket === "string" ? item.freshness_bucket : null;
        const freshnessLabel = typeof item.freshness_label === "string" ? item.freshness_label : null;
        const isIncomplete = Boolean(item.is_incomplete || !publishedAtIso || !sourceName || !sourceUrl);
        const labels = Array.isArray(item.labels) ? item.labels.filter(Boolean) : [];
        const entities = Array.isArray(item.entities)
          ? item.entities.filter(Boolean).map((entity) => appLocale === "en-US" ? localizeUiText(entity, appLocale, selectedTicker) : expandPortugueseMarketTerms(entity))
          : [];
        const impact = localizeImpactLabel(item.impact_label || item.impact || "Neutro", appLocale);
        const sentiment = resolveNewsSentiment(item);
        const title = displayNewsTitle(item, selectedTicker, appLocale);
        const rawHeadline = bestRawNewsHeadline(item, selectedTicker);
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
          symbol: matchedSymbol,
          headline,
          title,
          source: sourceName,
          sourceName,
          sourceUrl,
          age,
          publishedTime,
          publishedAtIso,
          fetchedAt: item.fetched_at || item.detected_at || null,
          ageMinutes,
          isToday,
          isStale,
          freshnessBucket,
          freshnessLabel,
          matchedSymbol,
          language: item.language || null,
          publicationStatus: item.publication_status || (publishedAtIso ? "ok" : "missing_source_time"),
          isIncomplete,
          sector,
          industry,
          labels: labelsForLocale,
          entities,
          impact,
          sentiment,
          quality,
          useful: item.useful !== false,
          relevanceScore: item.relevance_score ?? item.relevance,
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
          url: itemUrl,
        };
      });
    },
    [activeNews?.items, selectedTicker, appLocale, isUsLocale],
  );
  const freshNewsCount = useMemo(
    () => newsRows.filter((item) => item.isToday === true && item.isStale !== true).length,
    [newsRows],
  );
  const backendNewsStatus = String(
    activeNews?.status ||
      (activeNews?.state && typeof activeNews.state === "object" ? (activeNews.state as Record<string, unknown>).status : "") ||
      "",
  ).toLowerCase();
  const backendNewsReason = String(
    (activeNews?.state && typeof activeNews.state === "object" ? (activeNews.state as Record<string, unknown>).reason : "") ||
      activeNews?.message ||
      "",
  ).toLowerCase();
  const newsIsHistorical = Boolean(
    newsRows.length > 0 &&
      (
        freshNewsCount === 0 ||
        ["historical", "stale", "no_fresh_news"].includes(backendNewsStatus) ||
        /histor|stale|no_fresh_news|sem noticia atual|sem notícia atual/.test(backendNewsReason)
      ),
  );
  const newsStatusForPanel = newsIsHistorical ? "historical" : (activeNews?.status || null);
  const visibleTabs = useMemo(
    () => TOP_BAR_TAB_IDS
      .filter((id) => shouldShowTopBarTabId(id, advancedMode))
      // Stock Flow is a Pro/Trial surface: hide it for Básico/free/expired plans.
      .filter((id) => id !== "stockflow" || !proModeLocked)
      .map((id) => tabsById.get(id))
      .filter(Boolean) as WorkspaceTab[],
    [advancedMode, tabsById, proModeLocked],
  );

  useEffect(() => {
    if (focusedTab || visibleTabs.some((tab) => tab.id === currentTab)) return;
    setActiveTab("grafico");
  }, [currentTab, focusedTab, visibleTabs]);

  const stats = useMemo(() => {
    const emptyChangeText = isUsLocale ? "no confirmed change" : "sem variação confirmada";
    const emptyScoreText = isUsLocale ? "no confirmed score" : "sem Score confirmado";
    const emptyBiasText = isUsLocale ? "no confirmed bias" : "sem Bias confirmado";
    const masterScoreContract = symbolOperationalView?.operational_context.master_score;
    const masterScoreStatus = String(masterScoreContract?.status || "PENDING").toUpperCase();
    const usedScoreComponents = masterScoreContract?.used_components?.length || 0;
    const missingScoreComponents = masterScoreContract?.missing_components || [];
    const totalScoreComponents = usedScoreComponents + missingScoreComponents.length;
    const changeValue = displayQuoteHasCoreData ? formatSignedPercent(displayQuote?.change_pct) : emptyChangeText;
    const aiScoreValue = effectiveAiScore != null ? Number(effectiveAiScore).toFixed(1) : emptyScoreText;
    const scoreNumber = effectiveAiScore != null ? Number(effectiveAiScore) : Number.NaN;
    const rawChangeNumber = displayQuoteHasCoreData ? Number(displayQuote?.change_pct) : Number.NaN;
    const changeNumber = Number.isFinite(rawChangeNumber) ? rawChangeNumber : null;
    const operationalTechnicalBias = currentTechnicalBias(symbolOperationalView?.technical_context.technical_bias);
    const operationalBias = operationalTechnicalBias != null
      ? contextDirectionLabel(operationalTechnicalBias, appLocale)
      : "";
    const rawBias = displayQuoteHasCoreData ? operationalBias || derivedPublicInsight?.trend_bias || derivedPublicInsight?.signal || currentRanking?.trend || "" : "";
    const biasValue = displayQuoteHasCoreData ? biasStrengthLabel(rawBias, scoreNumber, changeNumber ?? 0, appLocale) : emptyBiasText;
    const rsiDescriptor = describeRsiValue(panelRsiValue, appLocale, cardRsiTimeframeLabel, currentPublicInsight?.rsi_metadata?.status === "PENDING");
    const rsiValue = rsiDescriptor.label;
    // describeRsiValue already returns "—" when there is no usable RSI, so no
    // oversold/overbought copy can reach the screen from a 0/null payload.
    const rsiScoreValue = rsiValue;
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
      derivedPublicInsight?.rel_volume,
      currentRanking?.rel_volume,
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
    const scoreHint = masterScoreStatus === "PARTIAL"
      ? (isUsLocale
          ? `${aiScoreValue}: partial technical score, calculated with ${usedScoreComponents} of ${totalScoreComponents} components${missingScoreComponents.length ? `; missing ${missingScoreComponents.join(", ")}` : ""}.`
          : `${aiScoreValue}: score técnico parcial, calculado com ${usedScoreComponents} de ${totalScoreComponents} componentes${missingScoreComponents.length ? `; faltam ${missingScoreComponents.join(", ")}` : ""}.`)
      : Number.isFinite(scoreNumber)
      ? scoreNumber >= 7
        ? (isUsLocale ? `${aiScoreValue} favors strength/buy only with confirmation.` : `${aiScoreValue} favorece força/compra apenas com confirmação.`)
        : scoreNumber <= 5.5
          ? (isUsLocale ? `${aiScoreValue} indicates weak/sell bias; avoid long without confirmation.` : `${aiScoreValue} indicando baixa/venda; evite compra sem confirmação.`)
          : (isUsLocale ? `${aiScoreValue} is moderate: wait for price/volume confirmation.` : `${aiScoreValue} é moderado: aguarde confirmação de preço/volume.`)
      : (isUsLocale ? "No Master Score confirmed for this asset yet." : "Sem Score Mestre confirmado para este ativo ainda.");
    const rsiFreshness = dailyFreshnessMeta(symbolOperationalView?.technical_context.rsi_d1, symbolOperationalView?.session_date, appLocale);
    const rsiHint = rsiFreshness ? `${rsiDescriptor.hint} ${rsiFreshness}.` : rsiDescriptor.hint;

    const quoteStats = [
      {
        label: isUsLocale ? "Change" : "Variação",
        value: changeValue,
        hint: displayQuoteHasCoreData
          ? (isUsLocale ? `${changeValue} indicates ${changeDirection} now.` : `${changeValue} indicando ${changeDirection} do ativo.`)
          : (isUsLocale ? "No confirmed real change in the current payload." : "Sem variação real confirmada no payload atual."),
        tone: changeNumber != null && changeNumber > 0 ? "up" : changeNumber != null && changeNumber < 0 ? "down" : "neutral",
      },
      {
        label: isUsLocale ? "Snapshot Volume" : "Volume snapshot",
        value: volumeValue,
        hint: isUsLocale ? `${volumeValue}; ${volumeContext}.` : `${volumeValue}, ${volumeContext}.`,
        tone: relVolume != null && relVolume > 1.2 ? "up" : relVolume != null && relVolume < 0.8 ? "down" : "neutral",
      },
    ];
    if (!displayQuoteHasCoreData) return quoteStats;
    return [
      ...quoteStats,
      {
        label: masterScoreStatus === "PARTIAL" ? (isUsLocale ? "Partial technical score" : "Score técnico parcial") : (isUsLocale ? "Master Score" : "Score Mestre"),
        value: masterScoreStatus === "PARTIAL" && effectiveAiScore != null ? `${aiScoreValue}/10` : aiScoreValue,
        hint: scoreHint,
        tone: masterScoreStatus === "READY" && Number.isFinite(scoreNumber) && scoreNumber >= 7 ? "up" : masterScoreStatus === "READY" && Number.isFinite(scoreNumber) && scoreNumber <= 5.5 ? "down" : "neutral",
      },
      // Owner decision: the RSI card is hidden from the page. The value is still
      // computed and feeds the strategic panel / AI scoring; only the card is gone.
      // Flip RSI_CARD_VISIBLE to true to bring it back.
      ...(RSI_CARD_VISIBLE
        ? [{
            label: (isUsLocale ? "RSI VIEW" : "RSI VISÃO"),
            value: rsiScoreValue,
            hint: rsiHint,
            tone: ["READY", "PARTIAL"].includes(String(symbolOperationalView?.technical_context.rsi_d1?.freshness_status || symbolOperationalView?.technical_context.rsi_d1?.status || "").toUpperCase()) ? rsiDescriptor.tone : "neutral",
          }]
        : []),
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
    currentRanking?.rel_volume,
    currentRanking?.trend,
    currentWatchItem?.averageVolume,
    currentWatchItem?.relVolume,
    derivedPublicInsight?.score,
    derivedPublicInsight?.rel_volume,
    derivedPublicInsight?.trend_bias,
    derivedPublicInsight?.signal,
    isUsLocale,
    appLocale,
    selectedTicker,
    displayQuote,
    displayQuoteHasCoreData,
    panelRsiValue,
    cardRsiTimeframeLabel,
    currentPublicInsight?.rsi_metadata?.status,
    symbolOperationalView,
  ]);
  const displayStats = useMemo(
    () => {
      if (advancedMode) return stats;
      const lockedValue = isUsLocale ? "🔒 Available on Pro" : "🔒 Disponível no Pro";
      return stats.map((item) => ({
        ...item,
        value: lockedValue,
        hint: "",
        tone: "neutral",
      }));
    },
    [advancedMode, isUsLocale, stats],
  );
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
        timestamp: normalizeAlertEpoch(row?.timestamp ?? row?.detected_at ?? row?.market_data_updated_at ?? row?.quote_time ?? row?.provider_timestamp ?? row?.created_at ?? existing.timestamp),
      });
    };

    currentAiRows.forEach(addCandidate);

    return Array.from(bySymbol.values());
  }, [
    currentAiRows,
    watchUniverse,
    publicQuotes,
    tickerTapeQuotes,
    selectedTicker,
    symbolLabel,
    effectiveAiScore,
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
        .filter((row) => isAiDealFinding({ ...(row as Partial<AiToolRow>), tool: currentAiKey }) && scoreToolCandidateForTab(currentTab, row) > -999)
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
          data_quality: (row as any).data_quality ?? null,
          quote_status: (row as any).quote_status ?? null,
          status: (row as any).status ?? null,
          timestamp: normalizeAlertEpoch((row as any).timestamp ?? (row as any).detected_at ?? (row as any).market_data_updated_at ?? (row as any).quote_time ?? (row as any).provider_timestamp ?? (row as any).created_at),
        };
      }),
    [toolCandidatesSource, selectedTicker, currentTab, currentAiKey],
  );
  const backendToolCandidates = toolCandidates;
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
          null;
        const rsi = firstValidRsiNumber(row.rsi, symbol === selectedTicker ? derivedPublicInsight?.rsi : null);
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
        const rvol = row.rel_volume ?? (row as any).rvol ?? deriveRelativeVolume(resolvedVolume, (row as any)?.average_volume ?? (row as any)?.avg_volume);
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
        .filter((row) => normalizeSymbol(row.ticker) === selectedTicker)
        .filter((row) => isFreshAiFindingForReset(row))
        .filter(isAiDealFinding)
        .sort((a, b) => {
          const bTime = Date.parse(resolveAiAlertTimestamp(b) || "");
          const aTime = Date.parse(resolveAiAlertTimestamp(a) || "");
          if (Number.isFinite(bTime) && Number.isFinite(aTime) && bTime !== aTime) return bTime - aTime;
          return Number(b.score || 0) - Number(a.score || 0);
        })
        .slice(0, 20);
    }

    const sourceCandidates = backendToolCandidates
      .map((item) => {
        const normalizedItemSymbol = normalizeSymbol(item.symbol);
        if (normalizedItemSymbol !== selectedTicker) return null;
        const quote = resolveQuoteForSymbol(normalizedItemSymbol, publicQuotes, tickerTapeQuotes);
        const watchItem = watchUniverse.find((candidate) => candidate.symbol === normalizedItemSymbol);
        const changePct = quote?.change_pct ?? watchItem?.changePct ?? null;
        const trend = item.trend || (normalizedItemSymbol === selectedTicker ? derivedPublicInsight?.trend_bias || derivedPublicInsight?.signal : null) || "monitorando";
        const rsi = firstValidRsiNumber(item.rsi, normalizedItemSymbol === selectedTicker ? derivedPublicInsight?.rsi : null);
        const resolvedVolume = firstPositiveFiniteNumber(quote?.volume, item.volume, watchItem?.volume);
        const rvol = deriveRelativeVolume(
          resolvedVolume,
          (quote as any)?.average_volume ?? (quote as any)?.avg_volume ?? (item as any)?.average_volume,
        );
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
      .filter((item): item is NonNullable<typeof item> => item != null)
      .filter((item) => isAiDealFinding({ ...(item as Partial<AiToolRow>), tool: currentAiKey }) && scoreToolCandidateForTab(currentTab, item) > -999)
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
    backendToolCandidates,
    watchUniverse,
    publicQuotes,
    tickerTapeQuotes,
    selectedTicker,
    currentTab,
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
        .filter((row) => isFreshAiFindingForReset(row))
        .filter(isAiDealFinding)
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
          const existingFoundAt = resolveAiFindingTimestamp(existing);
          const rowFoundAt = resolveAiFindingTimestamp(row);
          const stableFoundAt = existingFoundAt || rowFoundAt || row.detected_at || existing.detected_at;
          if (isNewerAiAlert(row, existing)) {
            byKey.set(key, {
              ...existing,
              ...row,
              updated_at: row.updated_at || row.detected_at || existing.updated_at,
              found_at: (existing as any).found_at || (row as any).found_at || stableFoundAt,
              first_seen_at: (existing as any).first_seen_at || (row as any).first_seen_at || stableFoundAt,
              detected_at: existing.detected_at || row.detected_at || stableFoundAt,
              last_seen_at: row.last_seen_at || row.updated_at || row.detected_at || existing.last_seen_at,
            });
          } else {
            byKey.set(key, existing);
          }
          continue;
        }
        const existingFoundAt = existing ? resolveAiFindingTimestamp(existing) : null;
        const rowFoundAt = resolveAiFindingTimestamp(row);
        const stableFoundAt = existingFoundAt || rowFoundAt || row.detected_at;
        byKey.set(key, {
          ...(existing || {}),
          ...row,
          updated_at: isNewerAiAlert(row, existing) ? row.updated_at : existing?.updated_at || row.updated_at,
          found_at: (existing as any)?.found_at || (row as any).found_at || stableFoundAt,
          first_seen_at: (existing as any)?.first_seen_at || (row as any).first_seen_at || stableFoundAt,
          detected_at: existing?.detected_at || row.detected_at || stableFoundAt,
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
  // AI tabs are a market-wide ranked list, not a per-symbol read: the
  // per-selected-ticker pipeline above collapses each tab to 0-1 rows even though
  // the badge counts the full catalog. Render the whole unfiltered catalog
  // (already backend-ranked and shaped) whenever the per-ticker pipeline has
  // nothing, so lists always match badges; a row click switches the ticker.
  const aiCatalogFallbackRows = useMemo<AiToolRow[]>(() => {
    if (!currentAiKey || aiAccessLocked) return [];
    const rows = publicAiCatalog?.tools?.[currentAiKey as keyof WorkspaceData["ai_tools"]];
    if (!Array.isArray(rows) || !rows.length) return [];
    return rows
      .map((row) =>
        withAlertTimestamp({
          ...(row as AiToolRow),
          tool: currentAiKey,
          ticker: normalizeSymbol(String((row as any).ticker || (row as any).symbol || "")),
        }),
      )
      .filter((row) => isFreshAiFindingForReset(row))
      .filter(isAiDealFinding);
  }, [aiAccessLocked, currentAiKey, publicAiCatalog?.tools]);
  const currentTabHistory =
    aiAlertHistory[currentTab]?.resetKey === aiAlertResetKey &&
    aiAlertHistory[currentTab]?.source === "real" &&
    aiAlertHistory[currentTab]?.rows.length
      ? aiAlertHistory[currentTab].rows
      : null;
  const currentTabOwnRows = (currentTabHistory?.length ? currentTabHistory : visibleAiRowsWithTimestamps)
    .filter((row) => isFreshAiFindingForReset(row))
    .filter(isAiDealFinding);
  const normalizedAiRequestStatus = aiAccessLocked
    ? "PREMIUM_LOCKED"
    : String(aiRequestState.status || "").toUpperCase();
  const normalizedAiRequestReason = String(aiRequestState.reason || "").toLowerCase();
  // The backend can stay in LOADING/PENDING indefinitely (no signals published,
  // hydration worker down). Without a client-side ceiling the panel sits on
  // "Calculando análise…" forever — a loading state impersonating a reading.
  // Past the ceiling we fall through to the honest terminal state the product
  // already defines for an expired hydration.
  const aiPendingKey = aiPanelKey(selectedTicker, currentAiKey ?? "");
  const aiPendingIsLoadingStatus = isAiLoadingStatus(normalizedAiRequestStatus);
  useEffect(() => {
    const registry = aiDeadlineRegistryRef.current;
    // Deliberately NOT cleared when the status leaves the loading family: the
    // backend dips out of LOADING/PENDING/REFRESHING between polls, and
    // clearing there let the next poll mint a fresh deadline — the very restart
    // this registry exists to prevent.
    if (!aiPendingIsLoadingStatus) return undefined;
    // Created once per lens. Re-running this effect (status oscillation, a
    // re-render, Strict Mode) returns the ORIGINAL deadline, so the ceiling can
    // never be pushed out — which is what left `momentum` loading forever.
    registry.ensure(aiPendingKey, Date.now());
    const key = aiPendingKey;
    const timer = setTimeout(() => setAiTimedOutKey(key), registry.remaining(key, Date.now()));
    return () => clearTimeout(timer);
  }, [aiPendingKey, aiPendingIsLoadingStatus]);
  const aiRequestLocked = normalizedAiRequestStatus === "PREMIUM_LOCKED";
  const aiRequestPendingExpired = normalizedAiRequestStatus === "PENDING_EXPIRED"
    || (normalizedAiRequestStatus === "PENDING" && /expired|timeout|ttl/.test(normalizedAiRequestReason))
    // Expiry is scoped to the exact lens that timed out, and only while it is
    // still loading — a payload that lands late still wins.
    // Scoped to the exact lens and only while it is genuinely still loading.
    // No row-count guard here: currentAiRows carries catalog/history entries, so
    // gating on it suppressed expiry for lenses that legitimately have history
    // (smart-money, flow) and left them loading forever.
    || (aiTimedOutKey === aiPendingKey && aiPendingIsLoadingStatus);
  const aiRequestUnsupported = normalizedAiRequestStatus === "UNSUPPORTED" || normalizedAiRequestReason.includes("unsupported");
  // Test-only: lets the audit assert that no lens deadline outlives its panel.
  useEffect(() => {
    if (typeof window === "undefined") return;
    (window as unknown as Record<string, unknown>).__snbrAiPanel = {
      key: aiPendingKey,
      loading: aiPendingIsLoadingStatus,
      expired: aiRequestPendingExpired,
      liveDeadlines: aiDeadlineRegistryRef.current.size(),
    };
  }, [aiPendingKey, aiPendingIsLoadingStatus, aiRequestPendingExpired]);
  const aiRequestFailed = normalizedAiRequestStatus === "ERROR" || normalizedAiRequestStatus === "PROVIDER_ERROR";
  const aiRequestTerminal = aiRequestLocked || aiRequestPendingExpired || aiRequestUnsupported || aiRequestFailed || normalizedAiRequestStatus === "INSUFFICIENT_DATA";
  // Same precedence as aiToolFindingCounts below (own rows, else catalog), so the
  // badge number and the rendered list can never disagree.
  // Most recent finding first. The history bucket sorts by alert timestamp and the
  // catalog fallback arrives score-ranked, so sort here on the same timestamp the
  // card prints as "Detectado" — that is the only ordering the owner can verify.
  const currentTabAlertSourceRows = aiAccessLocked
    ? []
    : GLOBAL_AI_ALERT_TAB_IDS.has(currentTab)
      ? aiCatalogFallbackRows
      : aiRequestTerminal
      ? []
      : currentTabOwnRows.length
        ? currentTabOwnRows
        : aiCatalogFallbackRows;
  const currentTabAlertRows = [...currentTabAlertSourceRows].sort(
    (a, b) => (Date.parse(resolveAiFindingTimestamp(b) || "") || 0) - (Date.parse(resolveAiFindingTimestamp(a) || "") || 0),
  );
  const currentAiStaleRows = useMemo(
    () => aiAccessLocked
      ? []
      : currentAiRows
      .map((row) => ({
        ...(row as AiToolRow),
        tool: currentAiKey || (row as AiToolRow).tool,
        ticker: normalizeSymbol(String((row as any).ticker || (row as any).symbol || selectedTicker)),
      }))
      .filter((row) => row.ticker === selectedTicker)
      .filter((row) => aiFindingResetKey(row) && !isFreshAiFindingForReset(row)),
    [aiAccessLocked, currentAiKey, currentAiRows, selectedTicker],
  );
  const currentAiFreshnessStatus = aiRequestLocked
    ? "premium_locked"
    : aiRequestTerminal && !GLOBAL_AI_ALERT_TAB_IDS.has(currentTab)
    ? normalizedAiRequestStatus.toLowerCase()
    : currentTabAlertRows.length
    ? "updated_today"
    : currentAiStaleRows.length
      ? "awaiting_new_daily_read"
      : currentAiRows.length
        ? "no_current_asset_finding"
        : "no_payload_rows";
  const currentAiPayloadAvailable = Boolean(
    !aiAccessLocked &&
    currentAiKey &&
    (
      aiCatalogFallbackRows.length > 0 ||
      (workspace?.ai_tools && Object.prototype.hasOwnProperty.call(workspace.ai_tools, currentAiKey)) ||
      (publicAiTools?.tools && Object.prototype.hasOwnProperty.call(publicAiTools.tools, currentAiKey))
    ),
  );
  const currentAiEmptyState = useMemo(() => {
    if (!currentAiKey) return null;
    if (aiRequestLocked) {
      return {
        title: isUsLocale ? "AI Pro is locked." : "IA Pro bloqueada.",
        body: token
          ? (isUsLocale
              ? "Your current plan does not unlock these AI lenses. An active Trial, Premium or Enterprise plan is required."
              : "Seu plano atual não libera estas lentes de IA. É necessário um plano Trial, Premium ou Enterprise ativo.")
          : (isUsLocale
              ? "Sign in with your email and activate Trial or Premium access to use these AI lenses."
              : "Entre com seu e-mail e ative o acesso Trial ou Premium para usar estas lentes de IA."),
      };
    }
    if (aiRequestPendingExpired) {
      return {
        title: isUsLocale ? "Analysis did not finish in time." : "A análise não ficou pronta a tempo.",
        body: isUsLocale ? "The pending hydration expired; no current reading was published." : "A hidratação pendente expirou; nenhuma leitura atual foi publicada.",
      };
    }
    if (loading) {
      return {
        title: isUsLocale ? "AI loading." : "IA carregando.",
        body: isUsLocale ? "Waiting for the current payload." : "Aguardando o payload atual.",
      };
    }
    if (aiRequestUnsupported) {
      return {
        title: isUsLocale ? "This analysis is not supported." : "Esta análise não é suportada.",
        body: isUsLocale ? "The backend does not support this tool or timeframe for the current request." : "O backend não suporta esta ferramenta ou timeframe para a solicitação atual.",
      };
    }
    if (aiRequestFailed) {
      return {
        title: isUsLocale ? "AI analysis failed." : "Falha na análise da IA.",
        body: isUsLocale ? "The backend finished with an error; this is not an analysis still in progress." : "O backend terminou com erro; esta não é uma análise ainda em processamento.",
      };
    }
    if (normalizedAiRequestStatus === "INSUFFICIENT_DATA") {
      return {
        title: isUsLocale ? "Insufficient current data." : "Dados atuais insuficientes.",
        body: isUsLocale ? "The attempt finished without enough data for a validated reading." : "A tentativa terminou sem dados suficientes para uma leitura validada.",
      };
    }
    if (["LOADING", "PENDING", "REFRESHING"].includes(normalizedAiRequestStatus)) {
      return {
        title: isUsLocale ? "Calculating analysis…" : "Calculando análise…",
        body: isUsLocale ? "Calculating the reading for this asset from its current quote, charts and news." : "Calculando a leitura deste ativo com cotação, gráficos e notícias atuais.",
      };
    }
    if (!currentAiPayloadAvailable) {
      return {
        title: isUsLocale ? "AI temporarily has no data." : "IA temporariamente sem dados.",
        body: isUsLocale ? "No AI finding for this asset right now." : "Nenhum achado desta IA para este ativo agora.",
      };
    }
    if (currentAiStaleRows.length > 0 && currentTabAlertRows.length === 0) {
      return {
        title: isUsLocale ? "Waiting for today's new read." : "Aguardando nova leitura do dia.",
        body: isUsLocale
          ? "Previous reads are visible only as stale context and do not count as current AI findings after the 07:00 reset."
          : "Leituras anteriores ficam apenas como contexto antigo e não contam como achados atuais depois do reset das 07:00.",
      };
    }
    if (currentAiRows.length > 0 && currentTabAlertRows.length === 0) {
      return {
        title: isUsLocale ? "No new read validated today." : "Sem nova leitura validada hoje.",
        body: isUsLocale ? "Older readings remain historical only." : "Leituras antigas ficam somente no histórico.",
      };
    }
    if (currentAiRows.length === 0) {
      return {
        title: isUsLocale ? "No new read validated today." : "Sem nova leitura validada hoje.",
        body: isUsLocale ? "Waiting for a current validation." : "Aguardando validação atual.",
      };
    }
    return null;
  }, [aiRequestFailed, aiRequestLocked, aiRequestPendingExpired, aiRequestUnsupported, currentAiKey, currentAiPayloadAvailable, currentAiRows.length, currentAiStaleRows.length, currentTabAlertRows.length, isUsLocale, loading, normalizedAiRequestStatus, token]);
  const showSymbolHeader = currentTab === "grafico";
  const profileName = publicSocialName(access?.display_name);
  const activePoll = useMemo(
    () => (sameSymbol(poll?.symbol, selectedTicker) ? normalizePollPayload(poll, selectedTicker) : null),
    [poll, selectedTicker],
  );
  const localizedActivePoll = useMemo(
    () => activePoll ? ({
      ...activePoll,
      question: localizePollText(activePoll.question, appLocale, selectedTicker),
      status: appLocale === "en-US"
        ? localizeUiText(activePoll.status || "open", appLocale, selectedTicker)
        : activePoll.status,
      options: activePoll.options.map((option) => ({
        ...option,
        label: localizePollText(option.label, appLocale, selectedTicker),
      })),
    }) : ({
      symbol: selectedTicker,
      question: "",
      options: [],
      total_votes: 0,
      status: pollStatus,
      reason: pollReason,
    }),
    [activePoll, appLocale, pollReason, pollStatus, selectedTicker],
  );
  const hasPublicSignal = Boolean(displayQuoteHasCoreData && symbolOperationalView);
  const hasSignalSnapshot = hasPublicSignal;
  const chartTrendText = String(activeChart?.summary?.trend_bias || "");
  const chartSignalText = String(activeChart?.summary?.latest_signal || "");
  const chartDataAsOf = String(activeChart?.summary?.as_of || "");
  const chartAnalysisTimeframe = String(activeChart?.summary?.interval || activeChart?.interval || chartInterval || "");
  const trendText = hasPublicSignal
    ? String(symbolOperationalView?.technical_context.trend_d1?.value || "")
    : chartTrendText || String(currentPublicInsight?.trend_bias || currentPublicInsight?.signal || "");
  const rawSignalScore = firstFiniteNumber(symbolOperationalView?.operational_context.master_score?.value);
  const normalizedSignalScore = rawSignalScore == null || Number.isNaN(rawSignalScore)
    ? null : rawSignalScore <= 10 ? rawSignalScore * 10 : rawSignalScore;
  const numericRankingScore = normalizedSignalScore != null ? clampNumber(normalizedSignalScore, 0, 100) : null;
  const sentimentContract = assetMetrics?.sentiment;
  const rawSentimentValue = sentimentContract?.status === "READY" ? sentimentContract.value : null;
  const effectiveSentimentScore = firstFiniteNumber(rawSentimentValue);
  const categoricalSentiment = typeof rawSentimentValue === "string" ? rawSentimentValue.toLowerCase() : "";
  const sentimentTone =
    categoricalSentiment === "bullish"
      ? "bullish"
      : categoricalSentiment === "bearish"
        ? "bearish"
        : categoricalSentiment === "neutral" || categoricalSentiment === "mixed"
          ? "neutral"
    : effectiveSentimentScore == null
      ? "neutral"
      : effectiveSentimentScore >= 55
        ? "bullish"
        : effectiveSentimentScore <= 45
          ? "bearish"
          : "neutral";
  const sentimentSampleSize = firstFiniteNumber(sentimentContract?.components?.classified_total);
  const sentimentBaseLabel =
    categoricalSentiment === "mixed"
      ? (isUsLocale ? "Mixed" : "Misto")
      : categoricalSentiment === "neutral"
        ? (isUsLocale ? "Neutral" : "Neutro")
      : sentimentTone === "bearish"
        ? (isUsLocale ? "Bearish" : "Urso")
        : sentimentTone === "bullish"
          ? (isUsLocale ? "Bullish" : "Touro")
          : effectiveSentimentScore == null
            ? (isUsLocale ? "Current sentiment unavailable" : "Sentimento atual indisponível")
            : (isUsLocale ? "Neutral" : "Neutro");
  const sentimentLabel = sentimentSampleSize != null && sentimentSampleSize > 0
    ? `${sentimentBaseLabel} · ${sentimentSampleSize} ${isUsLocale ? "classified" : "classificada(s)"}`
    : sentimentBaseLabel;
  const sentimentScore = effectiveSentimentScore;
  const dailyVolumeRatio = firstFiniteNumber(assetMetrics?.volume_vs_daily_average?.status === "READY" ? assetMetrics.volume_vs_daily_average.ratio : null);
  const dailyVolumeLabel = dailyVolumeRatio != null
    ? dailyVolumeRatio >= 1.3
      ? (isUsLocale ? "Above average" : "Acima da média")
      : dailyVolumeRatio < 0.7
        ? (isUsLocale ? "Below average" : "Abaixo da média")
        : (isUsLocale ? "Near average" : "Na média")
    : (isUsLocale ? "Daily average unavailable" : "Média diária indisponível");
  const priceDirectionClass = movementClass(priceMovementPercent, currentRanking?.trend, currentRanking?.score);
  const priceMovementLabel = marketSessionLabel(selectedTicker, appLocale);
  const hasPriceMovement = priceMovementValue != null || priceMovementPercent != null;
  const essentialDecisionCards = useMemo<EssentialDecisionCard[]>(() => {
    if (symbolOperationalView) {
      return symbolContextDecisionCards(symbolOperationalView, appLocale);
    }
    if (displayQuoteHasCoreData && currentStrategicPanel) {
      return strategicPanelDecisionCards(currentStrategicPanel, appLocale, derivedPublicInsight?.trend_bias);
    }
    const rawScoreValue = effectiveAiScore != null && Number.isFinite(Number(effectiveAiScore))
      ? Number(effectiveAiScore)
      : numericRankingScore != null
        ? numericRankingScore / 10
        : null;
    const hasCoreData = Boolean(displayQuoteHasCoreData && displayQuote?.price != null && headerVolume != null && headerVolume > 0);
    const scoreValue = hasCoreData ? rawScoreValue : null;
    const scoreTone: DecisionTone = scoreValue == null ? "neutral" : scoreValue >= 6 ? "bullish" : scoreValue <= 4.8 ? "bearish" : "neutral";
    const trendTone = decisionToneFromText(trendText, derivedPublicInsight?.trend_bias, derivedPublicInsight?.signal);
    const sameTicker = (row: AiToolRow) => normalizeSymbol(row.ticker || "") === selectedTicker;
    const toolRows = (keys: Array<keyof WorkspaceData["ai_tools"]>) =>
      keys.flatMap((key) => [
        ...(workspace?.ai_tools?.[key] || []),
        ...(publicAiTools?.tools?.[key] || []),
      ])
        .map((row) => ({
          ...(row as AiToolRow),
          ticker: normalizeSymbol(String((row as any).ticker || (row as any).symbol || selectedTicker)),
        }))
        .filter((row) => isFreshAiFindingForReset(row))
        .filter(sameTicker);
    const flowCard = currentStrategicPanel
      ? strategicPanelDecisionCards(currentStrategicPanel, appLocale, derivedPublicInsight?.trend_bias)[4]
      : resolveFlowCard(toolRows(["flow", "smart_money"]), appLocale);
    const flowTone = flowCard.tone;
    const baseTone = trendTone !== "neutral"
      ? trendTone
      : flowTone !== "neutral"
        ? flowTone
        : scoreTone;
    const directionTone = !hasCoreData
      ? "neutral"
      : baseTone !== "neutral"
        ? baseTone
        : scoreTone;
    const structuralConflict = tonesConflict(trendTone, flowTone) || tonesConflict(directionTone, flowTone);
    const scoreConflict = scoreTone !== "neutral" && directionTone !== "neutral" && directionTone !== "exit" && tonesConflict(directionTone, scoreTone);
    const conflict = structuralConflict || scoreConflict;
    const tradeTone = conflict ? "watch" : directionTone === "exit" ? "exit" : directionTone;
    const scoreCardTone: DecisionTone = scoreValue == null ? "neutral" : scoreValue >= 7 ? "bullish" : scoreValue <= 5.5 ? "bearish" : "watch";
    const riskCard = resolveRiskCard(scoreValue, hasCoreData, conflict, appLocale, derivedPublicInsight?.rsi ?? currentRanking?.rsi, rawScoreValue);
    const regimeValue = humanizeMachineLabel(trendText || derivedPublicInsight?.trend_bias || derivedPublicInsight?.signal || "", appLocale);
    return [
      {
        label: isUsLocale ? "Master Score" : "Score Mestre",
        value: scoreValue != null ? `${scoreValue.toFixed(1)} / 10` : (isUsLocale ? "No confirmed score" : "Sem score confirmado"),
        tone: scoreCardTone,
        meta: scoreConvictionLabel(scoreValue, appLocale),
        meter: scoreValue != null ? clampNumber(scoreValue * 10, 0, 100) : null,
      },
      {
        label: isUsLocale ? "Likely Direction" : "Direção provável",
        value: decisionDirectionLabel(directionTone, appLocale),
        tone: directionTone === "exit" ? "watch" : directionTone,
      },
      {
        label: isUsLocale ? "Suggested Trade" : "Trade sugerido",
        value: decisionTradeLabel(tradeTone, hasCoreData, appLocale),
        tone: tradeTone,
      },
      {
        label: isUsLocale ? "Regime" : "Regime",
        value: regimeValue || (isUsLocale ? "No read" : "Sem leitura"),
        tone: trendTone === "exit" ? "neutral" : trendTone,
      },
      flowCard,
      {
        label: isUsLocale ? "Asset Liquidity" : "Liquidez Ativo",
        value: assetMetrics?.rvol?.status === "READY"
          ? `RVOL ${Number(assetMetrics.rvol.rvol_ratio).toFixed(2)} — ${assetMetrics.rvol.label}`
          : (isUsLocale ? "Calculating liquidity…" : "Calculando liquidez…"),
        tone: assetMetrics?.rvol?.status === "READY" && Number(assetMetrics.rvol.rvol_ratio) < 0.7 ? "bearish" : "neutral",
      },
      riskCard,
    ];
  }, [
    appLocale,
    assetMetrics,
    currentStrategicPanel,
    currentRanking?.rsi,
    derivedPublicInsight?.rsi,
    derivedPublicInsight?.signal,
    derivedPublicInsight?.trend_bias,
    displayQuote?.price,
    displayQuoteHasCoreData,
    effectiveAiScore,
    headerVolume,
    isUsLocale,
    numericRankingScore,
    publicAiTools?.tools,
    selectedTicker,
    symbolOperationalView,
    trendText,
    workspace?.ai_tools,
  ]);
  const strategicConclusion = useMemo(() => {
    // The per-asset LLM conclusion, once generated, is the richest read -- prefer it over the
    // operational-context template below (symbolContextStrategicSections), which otherwise wins
    // first and hides it. strategicConclusionFromPanel surfaces panel.llm_conclusion. When it is
    // still null (cold LLM), the existing paths render as before.
    if (!proModeLocked && currentStrategicPanel?.llm_conclusion) {
      return strategicConclusionFromPanel(currentStrategicPanel, appLocale);
    }
    if (symbolOperationalView) {
      const sections = symbolContextStrategicSections(symbolOperationalView, appLocale, selectedTicker);
      return {
        headline: sections[0]?.body || (isUsLocale ? "Selected-symbol operational context" : "Contexto operacional do ativo"),
        focus: sections[sections.length - 1]?.body || "",
        basis: symbolContextStrategicBasis(symbolOperationalView, appLocale),
        tone: symbolOperationalView.decision === "WAIT" ? "watch" as DecisionTone : decisionToneFromText(symbolOperationalView.technical_context.technical_bias?.value),
        stamp: formatNewsClock(symbolOperationalView.as_of || undefined, appLocale),
        source: "client_fallback" as const,
        sections,
      };
    }
    if (!proModeLocked && displayQuoteHasCoreData && currentStrategicPanel) {
      return strategicConclusionFromPanel(currentStrategicPanel, appLocale);
    }
    const hasCoreData = Boolean(displayQuoteHasCoreData && displayQuote?.price != null && headerVolume != null && headerVolume > 0);
    const scoreValue = hasCoreData && effectiveAiScore != null && Number.isFinite(Number(effectiveAiScore))
      ? Number(effectiveAiScore)
      : hasCoreData && numericRankingScore != null
        ? numericRankingScore / 10
        : null;
    const rsiNumber = firstValidRsiNumber(
      chartTimeframeRsi,
      panelRsiValue,
      derivedPublicInsight?.rsi,
      currentRanking?.rsi,
      (displayQuote as any)?.rsi,
    );
    const averageVolume = firstPositiveFiniteNumber(
      (displayQuote as any)?.average_volume,
      (displayQuote as any)?.averageVolume,
      (displayQuote as any)?.avg_volume,
      currentWatchItem?.averageVolume,
    );
    const resolvedVolume = firstPositiveFiniteNumber(headerVolume, displayQuote?.volume);
    const resolvedDailyVolumeRatio = firstPositiveFiniteNumber(
      dailyVolumeRatio,
      calculateRelativeVolume(resolvedVolume, averageVolume),
    );
    const relVolume = firstPositiveFiniteNumber(
      assetMetrics?.rvol?.status === "READY" ? assetMetrics.rvol.rvol_ratio : null,
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
      rsiTimeframe: rsiTimeframeLabel,
      price: firstFiniteNumber(displayQuote?.price),
      changePct: firstFiniteNumber(displayQuote?.change_pct),
      volume: resolvedVolume,
      dailyVolumeRatio: resolvedDailyVolumeRatio,
      relVolume,
      chartTrend: humanizeMachineLabel(chartTrendText || trendText, appLocale),
      chartSignal: chartSignalText,
      chartTimeframe: chartAnalysisTimeframe,
      chartAsOf: chartDataAsOf || null,
      hasCoreData: Boolean(hasCoreData && resolvedVolume != null && resolvedVolume > 0 && numericScoreFromDecisionCard(scoreCard) != null),
    });
  }, [
    appLocale,
    assetMetrics,
    chartAnalysisTimeframe,
    chartDataAsOf,
    chartSignalText,
    chartTimeframeRsi,
    chartTrendText,
    currentStrategicPanel,
    currentRanking?.rsi,
    currentWatchItem?.averageVolume,
    derivedPublicInsight?.rsi,
    dailyVolumeRatio,
    displayQuote,
    displayQuoteHasCoreData,
    effectiveAiScore,
    essentialDecisionCards,
    headerVolume,
    isUsLocale,
    numericRankingScore,
    panelRsiValue,
    proModeLocked,
    rsiTimeframeLabel,
    selectedTicker,
    strategicAnalysisMinute,
    symbolOperationalView,
    trendText,
  ]);
  const hasStrategicCoreData = Boolean(displayQuoteHasCoreData && displayQuote?.price != null && headerVolume != null && headerVolume > 0);
  const rawOperationalDecision = useMemo(() => {
    // Canonical core-data gate. Runs before any decision source is chosen so a
    // truthy symbolOperationalView can never escape it.
    const score = numericScoreFromDecisionCard(scoreDecisionCard(essentialDecisionCards));
    const noDataReason = resolveNoDataReason({ hasCoreData: hasStrategicCoreData, score });

    if (noDataReason != null) {
      return buildOperationalDecision({
        locale: appLocale,
        cards: essentialDecisionCards,
        conclusion: strategicConclusion,
        chart: chartForOperationalLevels,
        hasCoreData: false,
        missingFields: backendMissingFieldLabels,
      });
    }

    if (symbolOperationalView) {
      return operationalDecisionFromSymbolContext(symbolOperationalView, appLocale);
    }
    if (!proModeLocked && displayQuoteHasCoreData && currentStrategicPanel) {
      return operationalDecisionFromPanel(currentStrategicPanel, appLocale);
    }
    return buildOperationalDecision({
      locale: appLocale,
      cards: essentialDecisionCards,
      conclusion: strategicConclusion,
      chart: chartForOperationalLevels,
      hasCoreData: true,
      missingFields: backendMissingFieldLabels,
    });
  }, [
    appLocale,
    backendMissingFieldLabels,
    chartForOperationalLevels,
    currentStrategicPanel,
    displayQuoteHasCoreData,
    essentialDecisionCards,
    hasStrategicCoreData,
    proModeLocked,
    strategicConclusion,
    symbolOperationalView,
  ]);
  const alignedOperationalDecision = useMemo(
    () => alignOperationalDecisionWithTrade(rawOperationalDecision, appLocale),
    [appLocale, rawOperationalDecision],
  );
  const strategicDecisionContract = useMemo(
    () => buildStrategicDecisionContract({
      locale: appLocale,
      symbol: selectedTicker,
      cards: essentialDecisionCards,
      conclusion: strategicConclusion,
      operationalDecision: alignedOperationalDecision,
      hasCoreData: hasStrategicCoreData,
      executionReady: executionMetricsReady,
      pendingComponents: operationalBlockComponents,
      symbolContext: symbolOperationalView,
    }),
    [alignedOperationalDecision, appLocale, essentialDecisionCards, executionMetricsReady, hasStrategicCoreData, operationalBlockComponents, selectedTicker, strategicConclusion, symbolOperationalView],
  );
  const operationalDecision = useMemo(
    () => operationalDecisionFromStrategicContract(strategicDecisionContract),
    [strategicDecisionContract],
  );
  const coherentDisplayStats = useMemo(
    () => reconcileStatsWithDecision(
      displayStats,
      operationalDecision.action,
      firstFiniteNumber(displayQuote?.price),
      firstFiniteNumber((displayQuote as any)?.vwap),
      appLocale,
      strategicDecisionContract.side,
    ),
    [appLocale, displayStats, operationalDecision.action, displayQuote, strategicDecisionContract.side],
  );
  const decisionCardsForRender = useMemo(
    () => alignDecisionCardsWithStrategicContract(essentialDecisionCards, strategicDecisionContract, appLocale),
    [appLocale, essentialDecisionCards, strategicDecisionContract],
  );
  const shouldRenderStrategicDetails = hasStrategicCoreData;
  const strategicConclusionSections = useMemo(
    () => strategicDecisionContract.sections,
    [strategicDecisionContract.sections],
  );
  const strategicConclusionBasis = useMemo(
    () => strategicDecisionContract.basis,
    [strategicDecisionContract.basis],
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
    const renderWatchRow = (item: WatchlistItem, unavailable = false) => {
      const itemLabel = displayWatchlistLabel(item, appLocale);
      return (
        <div key={item.symbol} className={cx("snbr-watch-row", unavailable && "unavailable", item.symbol === selectedTicker && "active")}>
          <button
            className="snbr-watch-open"
            onClick={() => selectTicker(item.symbol)}
            type="button"
            aria-label={isUsLocale ? `Open ${item.symbol} on chart` : `Abrir ${item.symbol} no gráfico`}
            title={`${item.symbol} • ${itemLabel}`}
          >
            <div className="snbr-watch-identity">
              <AssetMark symbol={item.symbol} name={itemLabel} logoUrl={item.logoUrl} compact />
              <div className="snbr-watch-main">
                <strong>{item.symbol}</strong>
                {itemLabel ? <span>{itemLabel}</span> : null}
              </div>
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
      );
    };

    return (
      <div className="snbr-watchlist">
        {groupedActiveWatchlist.length ? groupedActiveWatchlist.map((group) => (
          <section key={group.category} className="snbr-watch-group">
            <header className="snbr-watch-group-head">
              <strong>{group.category}</strong>
              <span>{group.items.length} {isUsLocale ? "assets" : "ativos"}</span>
            </header>
            <div className="snbr-watch-group-list">
              {group.items.map((item) => renderWatchRow(item, !hasWatchlistSnapshotData(item)))}
            </div>
          </section>
        )) : (
          <div className="snbr-empty-thread">
            <strong>{isUsLocale ? "No asset in this filter." : "Nenhum ativo neste filtro."}</strong>
            <p>{isUsLocale ? "The filter does not remove assets from your active list." : "O filtro não remove ativos da sua lista ativa."}</p>
          </div>
        )}
        {filteredActiveWatchlist.length ? (
          <footer className="snbr-watch-total">
            <strong>{watchCategory === "Todos" ? (isUsLocale ? "All" : "Todos") : watchCategory}</strong>
            <span>{filteredActiveWatchlist.length} {isUsLocale ? "assets" : "ativos"}</span>
          </footer>
        ) : null}
      </div>
    );
  }

  function renderAvatar(name?: string | null, email?: string | null, avatarUrl?: string | null) {
    const initials = initialsFromName(name || email || "SN");
    return (
      <div className="snbr-avatar">
        {avatarUrl ? <img src={resolveMediaUrl(avatarUrl)} alt={name || "avatar"} /> : initials}
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
    displayValue?: string | null,
    subtext?: string,
  ) {
    const normalized = value == null ? null : clampNumber(value, 0, 100);
    const meterAngle = 180 - ((normalized ?? 50) * 1.8);
    const meterRadians = (meterAngle * Math.PI) / 180;
    const needleX = 80 + (36 * Math.cos(meterRadians));
    const needleY = 82 - (36 * Math.sin(meterRadians));
    const labelClass = normalized == null ? "neutral" : tone;

    return (
      <div className="snbr-meter-card">
        <div className="snbr-meter-copy">
          <span>{title}</span>
          <strong className={cx("snbr-meter-label", labelClass)}>{label}</strong>
          {subtext ? <small>{subtext}</small> : null}
        </div>
        <div className={cx("snbr-meter", tone)}>
          <svg className="snbr-meter-svg" viewBox="0 0 160 96" aria-hidden="true">
            <path className="snbr-meter-track" d="M 24 82 A 56 56 0 0 1 136 82" />
            <path className="snbr-meter-arc bearish" d="M 24 82 A 56 56 0 0 1 80 26" />
            <path className="snbr-meter-arc bullish" d="M 80 26 A 56 56 0 0 1 136 82" />
            {normalized != null ? (
              <>
                <line className="snbr-meter-needle-line" x1="80" y1="82" x2={needleX} y2={needleY} />
                <circle className="snbr-meter-needle-dot" cx="80" cy="82" r="5" />
              </>
            ) : null}
            <text className="snbr-meter-value-svg" x="80" y="58" textAnchor="middle">
              {displayValue ?? (normalized == null ? "—" : Math.round(normalized))}
            </text>
          </svg>
        </div>
      </div>
    );
  }

  function renderComposer() {
    const profileName = access?.display_name && !access.display_name.includes("@") ? access.display_name : "Trader";

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
            aria-label={isUsLocale ? `Write your idea for ${selectedTicker}` : `Escreva sua ideia para ${selectedTicker}`}
            placeholder={isUsLocale ? `Write your idea for ${selectedTicker}` : `Escreva sua ideia para ${selectedTicker}`}
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
                    onClick={toggleComposerGifPicker}
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

                {renderComposerAttachmentPreview()}

                {composerGifOpen ? renderComposerGifPicker() : null}

                {composerEmojiOpen ? renderComposerEmojiPicker() : null}
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
                onChange={(event) => {
                  setPostFile(event.target.files?.[0] || null);
                  setSelectedGif(null);
                }}
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
            {renderAvatar(profileName, null, access?.avatar_url)}
            <div className="snbr-composer-user">
              <strong>{profileName}</strong>
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
          aria-label={isUsLocale ? `Write your idea for ${selectedTicker}` : `Escreva sua ideia para ${selectedTicker}`}
          placeholder={isUsLocale ? `Write your idea for ${selectedTicker}` : `Escreva sua ideia para ${selectedTicker}`}
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
                  onClick={toggleComposerGifPicker}
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

              {renderComposerAttachmentPreview()}

              {composerGifOpen ? renderComposerGifPicker() : null}

              {composerEmojiOpen ? renderComposerEmojiPicker() : null}
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
              onChange={(event) => {
                setPostFile(event.target.files?.[0] || null);
                setSelectedGif(null);
              }}
            />
          </div>

          <button className="snbr-button primary snbr-post-submit" disabled={posting} onClick={handleCreatePost} type="button">
            {posting ? (isUsLocale ? "Posting..." : "Postando...") : "Post"}
          </button>
        </div>
      </div>
    );
  }

  function renderComposerAttachmentPreview() {
    const previewUrl = postFilePreviewUrl || selectedGif?.media_url || null;
    if (!previewUrl) return null;
    return (
      <div className="snbr-composer-attachment-preview">
        <img className="snbr-image" src={previewUrl} alt={postFile?.name || (isUsLocale ? "Selected GIF" : "GIF selecionado")} />
        <button
          aria-label={isUsLocale ? "Remove attachment" : "Remover anexo"}
          onClick={() => {
            setPostFile(null);
            setSelectedGif(null);
            if (composerFileInputRef.current) composerFileInputRef.current.value = "";
          }}
          type="button"
        >
          ✕
        </button>
      </div>
    );
  }

  function renderDiscussionList(posts: FeedPost[], emptyText: string) {
    if (!posts.length) {
      return null;
    }

    return (
      <div className="snbr-discussion-list">
        {posts.map((post) => (
          <article key={post.id} className="snbr-post">
            <div className="snbr-post-head snbr-post-head-top">
              <div className="snbr-post-user">
                {renderAvatar(publicSocialName(post.user), null, post.user_avatar_url)}
                <div>
                  <strong>{publicSocialName(post.user)}</strong>
                  <span>{post.ticker || selectedTicker} • {renderSocialTimestamp(post.created_at ?? post.timestamp, appLocale)}</span>
                </div>
              </div>
              <div className="snbr-post-head-actions">
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
                    aria-label={isUsLocale ? `Open post actions by ${publicSocialName(post.user)}` : `Abrir ações do post de ${publicSocialName(post.user)}`}
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
                      <button onClick={() => openReportDialog(post)} type="button" role="menuitem">{isUsLocale ? "Report to StockNewsBR" : "Denunciar para StockNewsBR"}</button>
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
            {post.image_url ? <div className="snbr-published-media"><ImageLightbox src={resolveMediaUrl(post.image_url)} alt={isUsLocale ? "post media" : "mídia do post"} locale={appLocale} /></div> : null}
            <div className="snbr-post-actions snbr-post-actions-bar">
              <button
                className="snbr-post-action snbr-feed-action"
                onClick={() => activateCommentComposer(post.id)}
                aria-label={isUsLocale ? `Reply to ${publicSocialName(post.user)}'s post` : `Responder ao post de ${publicSocialName(post.user)}`}
                type="button"
              >
                <span aria-hidden="true">💬</span>
                <span>{isUsLocale ? "Reply" : "Responder"}</span>
                <span>{post.comments?.length || 0}</span>
              </button>
              <button
                className={cx("snbr-post-action", "snbr-feed-action", (post.liked_by_me || (post.likes || 0) > 0) && "liked")}
                onClick={() => void handleToggleLike(post)}
                aria-label={isUsLocale ? `Like ${publicSocialName(post.user)}'s post` : `Curtir post de ${publicSocialName(post.user)}`}
                aria-pressed={Boolean(post.liked_by_me)}
                disabled={pendingLikePostIds.has(post.id)}
                type="button"
              >
                <span aria-hidden="true">{(post.liked_by_me || (post.likes || 0) > 0) ? "♥" : "♡"}</span>
                <span>{isUsLocale ? "Like" : "Curtir"}</span>
                <span>{post.likes ?? 0}</span>
              </button>
              <button
                className="snbr-post-action snbr-feed-action snbr-report-action"
                onClick={() => openReportDialog(post)}
                aria-label={isUsLocale ? `Report ${publicSocialName(post.user)}'s post` : `Denunciar post de ${publicSocialName(post.user)}`}
                data-social-report-button="true"
                type="button"
              >
                <span aria-hidden="true">!</span>
                <span>{isUsLocale ? "Report" : "Denunciar"}</span>
              </button>
            </div>

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
                      {renderAvatar(publicSocialName(comment.user), null, comment.user_avatar_url)}
                      <div>
                        <strong>{publicSocialName(comment.user)}</strong>
                        <span>{isUsLocale ? "comment" : "comentário"} • {renderSocialTimestamp(comment.created_at ?? comment.timestamp, appLocale)}</span>
                      </div>
                    </div>
                  <p className="snbr-rich-text">{renderCashtagText(localizeUiText(comment.text, appLocale, post.ticker || selectedTicker), `comment-${comment.id}`)}</p>
                  {comment.image_url ? <div className="snbr-published-media"><ImageLightbox src={resolveMediaUrl(comment.image_url)} alt={isUsLocale ? "comment image" : "imagem do comentário"} locale={appLocale} /></div> : null}
                </article>
              ))}

              {token ? (
                <div className="snbr-comment-compose" data-comment-composer={post.id}>
                  <textarea
                    data-comment-input={post.id}
                    className="snbr-textarea"
                    value={commentDrafts[post.id] || ""}
                    onChange={(event) => setCommentDrafts((current) => ({ ...current, [post.id]: event.target.value }))}
                    onFocus={() => updateCommentComposer(post.id, { active: true })}
                    aria-label={isUsLocale ? `Reply to ${publicSocialName(post.user)}'s post` : `Responder ao post de ${publicSocialName(post.user)}`}
                    placeholder={isUsLocale ? `Reply to ${publicSocialName(post.user)}'s post` : `Responder ao post de ${publicSocialName(post.user)}`}
                  />
                  {commentComposers[post.id]?.active ? (
                    <div className="snbr-composer-left">
                      <div className="snbr-composer-sentiment">
                        <button
                          className={cx("snbr-sentiment-pill", "bullish", commentComposers[post.id]?.sentiment !== "bearish" && "active")}
                          onClick={() => updateCommentComposer(post.id, { sentiment: "bullish" })}
                          aria-pressed={commentComposers[post.id]?.sentiment !== "bearish"}
                          type="button"
                        ><MarketAnimalIcon tone="bullish" /><span>{isUsLocale ? "Bullish" : "Touro"}</span></button>
                        <button
                          className={cx("snbr-sentiment-pill", "bearish", commentComposers[post.id]?.sentiment === "bearish" && "active")}
                          onClick={() => updateCommentComposer(post.id, { sentiment: "bearish" })}
                          aria-pressed={commentComposers[post.id]?.sentiment === "bearish"}
                          type="button"
                        ><MarketAnimalIcon tone="bearish" /><span>{isUsLocale ? "Bearish" : "Urso"}</span></button>
                      </div>
                      <div className="snbr-composer-toolbar">
                        <button className="snbr-toolbar-icon" onClick={() => commentFileInputRefs.current[post.id]?.click()} aria-label={isUsLocale ? "Add photo to reply" : "Adicionar foto à resposta"} type="button">🖼️</button>
                        <button
                          className={cx("snbr-toolbar-icon", commentComposers[post.id]?.tool === "gif" && "active")}
                          onClick={() => {
                            const opening = commentComposers[post.id]?.tool !== "gif";
                            updateCommentComposer(post.id, { tool: opening ? "gif" : null });
                            if (opening && gifSearchStatus === "idle") void handleGifSearch();
                          }}
                          aria-expanded={commentComposers[post.id]?.tool === "gif"}
                          type="button"
                        >GIF</button>
                        <button
                          className={cx("snbr-toolbar-icon", commentComposers[post.id]?.tool === "emoji" && "active")}
                          onClick={() => updateCommentComposer(post.id, { tool: commentComposers[post.id]?.tool === "emoji" ? null : "emoji" })}
                          aria-expanded={commentComposers[post.id]?.tool === "emoji"}
                          aria-label={isUsLocale ? "Add emoji to reply" : "Adicionar emoji à resposta"}
                          type="button"
                        >😊</button>
                      </div>
                      {commentComposers[post.id]?.previewUrl || commentComposers[post.id]?.gif?.media_url ? (
                        <div className="snbr-composer-attachment-preview">
                          <img className="snbr-image" src={commentComposers[post.id]?.previewUrl || commentComposers[post.id]?.gif?.media_url || ""} alt={isUsLocale ? "Reply attachment preview" : "Prévia do anexo da resposta"} />
                          <button onClick={() => selectCommentFile(post.id, null)} aria-label={isUsLocale ? "Remove reply attachment" : "Remover anexo da resposta"} type="button">✕</button>
                        </div>
                      ) : null}
                      {commentComposers[post.id]?.tool === "emoji" ? renderComposerEmojiPicker((emoji) => {
                        setCommentDrafts((current) => ({ ...current, [post.id]: `${current[post.id] || ""}${current[post.id] ? " " : ""}${emoji}` }));
                        updateCommentComposer(post.id, { tool: null });
                      }) : null}
                      {commentComposers[post.id]?.tool === "gif" ? renderComposerGifPicker((item) => {
                        const preview = commentComposers[post.id]?.previewUrl;
                        if (preview?.startsWith("blob:")) URL.revokeObjectURL(preview);
                        updateCommentComposer(post.id, { file: null, previewUrl: null, gif: item, tool: null });
                        if (commentFileInputRefs.current[post.id]) commentFileInputRefs.current[post.id]!.value = "";
                      }) : null}
                      <input
                        ref={(element) => { commentFileInputRefs.current[post.id] = element; }}
                        className="snbr-hidden-file-input"
                        type="file"
                        accept="image/png,image/jpeg,image/webp,image/gif"
                        onChange={(event) => selectCommentFile(post.id, event.target.files?.[0] || null)}
                      />
                      {commentComposers[post.id]?.error ? <p className="snbr-error" role="alert">{commentComposers[post.id].error}</p> : null}
                    </div>
                  ) : null}
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
            movementText: `${movementArrow(kind)} ${formatMarketMovementText(item, appLocale)}`,
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
      flow: "Lente: fluxo institucional e agressão compradora/vendedora.",
      liquidity: "Lente: zonas de liquidez, varreduras, armadilhas e invalidação.",
      trend: "Lente: direção predominante e estrutura de mercado.",
      momentum: "Lente: aceleração, força e exaustão.",
      "smart-money": "Lente: dinheiro inteligente e deslocamento pré-movimento.",
      risk: "Lente: risco operacional, bloqueios e Can Trade.",
      "news-ia": "Lente: notícias como contexto, relevância e status do provedor.",
      macro: "Lente: macro real separado de macro-news.",
      regime: "Lente: regime atual, lateralidade e volatilidade.",
    };
    const tabLensEn: Record<string, string> = {
      flow: "Lens: institutional flow and buy/sell aggression.",
      liquidity: "Lens: liquidity zones, sweeps, traps and invalidation.",
      trend: "Lens: dominant direction and market structure.",
      momentum: "Lens: acceleration, strength and exhaustion.",
      "smart-money": "Lens: smart money and pre-move displacement.",
      risk: "Lens: operational risk, blocks and Can Trade.",
      "news-ia": "Lens: news context, relevance and provider status.",
      macro: "Lens: real macro separated from macro-news.",
      regime: "Lens: current regime, range and volatility.",
    };
    const lens = (isUsLocale ? tabLensEn : tabLensPt)[currentTab] || "";

    if (currentAiKey) {
      const currentAiSoundEnabled = aiToolSoundEnabled(aiToolSoundSettings, currentAiKey);
      const aiSoundLocked = aiAccessLocked;
      return (
        <section
          id={`panel-${currentTab}`}
          className="snbr-tool-shell"
          data-ai-freshness-status={currentAiFreshnessStatus}
          data-ai-visible-count={currentTabAlertRows.length}
          data-ai-stale-count={currentAiStaleRows.length}
          data-ai-badge-count={aiToolFindingCounts[currentTab] || 0}
        >
          <div className="snbr-tool-head">
            <div>
              <h3>{copy.title}</h3>
              <p>{copy.description}</p>
              {copy.explanation ? <p>{copy.explanation}</p> : null}
              {lens ? <p className="snbr-tool-lens">{lens}</p> : null}
              {GLOBAL_AI_ALERT_TAB_IDS.has(currentTab) ? (
                <p
                  className="snbr-tool-lens"
                  title={isUsLocale ? "Global market alerts; they do not replace the selected asset's on-demand analysis." : "Alertas globais do mercado; não substituem a análise sob demanda do ativo selecionado."}
                >
                  {isUsLocale ? "Global market alerts. The selected asset analysis remains in the Strategic Panel." : "Alertas globais do mercado. A análise do ativo selecionado permanece no Painel Estratégico."}
                </p>
              ) : null}
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
                const resolvedRsi = firstValidRsiNumber(item.rsi);
                const resolvedRvol = item.rel_volume ?? deriveRelativeVolume(resolvedVolume, (item as any)?.average_volume ?? (item as any)?.avg_volume);
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
                const detectedAt = resolveAiFindingTimestamp(item);
                const updatedAt = normalizeAlertTimestamp((item as any).last_confirmed_at) || normalizeAlertTimestamp((item as any).updated_at);
                const asOf = normalizeAlertTimestamp((item as any).as_of);
                const sourceAsOf = normalizeAlertTimestamp(item.source_as_of) || asOf;
                const evaluatedAt = normalizeAlertTimestamp(item.evaluated_at) || updatedAt || detectedAt;
                const publishedAt = resolveAiPublishedTimestamp(item);
                const freshness = aiFreshnessStatus(sourceAsOf || detectedAt, viewedAtIso, appLocale);

                return (
                  <div key={`${currentTab}-${item.ticker}-${index}`} className="snbr-tool-row">
                    <section className="snbr-plain-panel">
                      <div className="snbr-section-head compact">
                        <div>
                          <h3>{isUsLocale ? "Asset Panel" : "Painel do ativo"}</h3>
                          <p>{isUsLocale ? "Daily alert from the current lens, with detection time and execution criteria." : "Alerta diário da lente atual, com horário detectado e critérios de execução."}</p>
                        </div>
                        <div className="snbr-news-chip-row snbr-temporal-chip-row">
                          <span className="snbr-chip">{isUsLocale ? "Analysis calculated at" : "Análise calculada em"}: {formatAiUpdatedAt(evaluatedAt, appLocale)}</span>
                          {sourceAsOf ? <span className="snbr-chip">{isUsLocale ? "Data used through" : "Dados usados até"}: {formatAiUpdatedAt(sourceAsOf, appLocale)}</span> : null}
                          {publishedAt ? <span className="snbr-chip">{isUsLocale ? "Published at" : "Publicado às"}: {formatAiUpdatedAt(publishedAt, appLocale)}</span> : null}
                          <span className={cx("snbr-chip", freshness.tone)}>{freshness.label}</span>
                        </div>
                      </div>
                      <button className="snbr-asset-box snbr-asset-box-large" onClick={() => selectTicker(item.ticker)} type="button">
                        <div className="snbr-asset-box-head">
                          <strong>{item.ticker}</strong>
                          <span className={cx("snbr-side-badge", scoreClass(item.score, (item as any).tone))}>
                            {currentTab === "flow" ? <i className={cx("snbr-score-dot", tone)} aria-hidden="true" /> : null}
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
              <strong>
                {currentAiEmptyState?.title || (currentTab === "news-ia"
                  ? (isUsLocale ? "No news analysis available for this asset right now." : "Nenhuma análise de notícia disponível para este ativo no momento.")
                  : (isUsLocale ? "No read available for this asset right now." : "Sem leitura disponível para este ativo no momento."))}
              </strong>
              <p>{currentAiEmptyState?.body || (isUsLocale ? "When the backend sends a valid payload, this card shows the content; otherwise the absence is explicit." : "Quando o backend enviar um payload válido, este card mostra o conteúdo; caso contrário, a ausência fica explícita.")}</p>
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
          {backendToolCandidates.map((item, index) => {
            const watchItem = watchUniverse.find((candidate) => candidate.symbol === item.symbol);
            const tone = String(item.trend || "").toLowerCase().includes("alta") || String(item.trend || "").toLowerCase().includes("bull")
              ? "bullish"
              : String(item.trend || "").toLowerCase().includes("baixa") || String(item.trend || "").toLowerCase().includes("bear")
                ? "bearish"
                : "neutral";
            const detectedAt = normalizeAlertTimestamp(item.timestamp);
            const freshness = aiFreshnessStatus(detectedAt, viewedAtIso, appLocale);

            return (
              <div key={`${currentTab}-${item.id}-${index}`} className="snbr-tool-row">
                {(() => {
                  const quote = resolveQuoteForSymbol(item.symbol, publicQuotes, tickerTapeQuotes);
                  const resolvedChangePct = item.changePct ?? watchItem?.changePct ?? quote?.change_pct ?? null;
                  const resolvedPrice = firstFiniteNumber(item.price, watchItem?.price, quote?.price);
                  const resolvedVolume = firstPositiveFiniteNumber(item.volume, watchItem?.volume, quote?.volume);
                  const resolvedRsi = firstValidRsiNumber(item.rsi);
                  const resolvedRvol = deriveRelativeVolume(resolvedVolume, (item as any)?.average_volume ?? (item as any)?.avg_volume);
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
                    <div className="snbr-news-chip-row snbr-temporal-chip-row">
                      <span className="snbr-chip">{isUsLocale ? "Detected" : "Detectado"}: {formatAiUpdatedAt(detectedAt, appLocale)}</span>
                      <span className={cx("snbr-chip", freshness.tone)}>{freshness.label}</span>
                    </div>
                  </div>
                  <button className="snbr-asset-box snbr-asset-box-large" onClick={() => selectTicker(item.symbol)} type="button">
                    <div className="snbr-asset-box-head">
                      <strong>{item.symbol}</strong>
                      <span className={cx("snbr-side-badge", scoreClass(item.score, (item as any).tone))}>
                        {currentTab === "flow" ? <i className={cx("snbr-score-dot", tone)} aria-hidden="true" /> : null}
                        Score {item.score != null ? item.score.toFixed(1) : "n/a"}
                      </span>
                    </div>
                    <span className={cx("snbr-data-quality-badge", `snbr-data-quality-${normalizeDataQuality(item.data_quality || item.quote_status || item.status)}`)}>
                      {dataQualityLabel(item.data_quality || item.quote_status || item.status)}
                      <small> • {dataQualityScore(item.data_quality || item.quote_status || item.status)}</small>
                    </span>
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
    // Prefer a complete row, but never claim "sem notícia" while the badge shows
    // a count: an item missing only a source_url is still worth reading.
    const chartNews = newsRows.find((item) => !item.isIncomplete) || newsRows[0];
    const chartNewsTime = chartNews?.publishedTime || "";
    const chartNewsHistorical = Boolean(
      chartNews && (newsIsHistorical || chartNews.isStale === true || chartNews.isToday === false),
    );
    const chartNewsTitle = chartNews
      ? chartNews.headline
      : (isUsLocale ? "No ticker-specific news" : "Sem notícia específica do ativo");
    const chartNewsText = chartNews
      ? (isUsLocale
        ? localizeUiText(chartNews.traderTakeaway || chartNews.whyItMatters || chartNews.cardSummary, appLocale, selectedTicker)
        : portugueseNewsInsight(chartNews.traderTakeaway || chartNews.whyItMatters || chartNews.cardSummary, selectedTicker))
      : (isUsLocale ? `No ticker-specific news found right now for ${selectedTicker}.` : `Sem notícia específica encontrada agora para ${selectedTicker}.`);
    const showChartNewsBody = !sameUiText(chartNewsTitle, chartNewsText);
    const chartToolToggles: Array<{ key: keyof ChartSettings; checked: boolean; label: string }> = [
      { key: "show_vwap", checked: showVwap, label: "VWAP" },
      { key: "show_macd", checked: showMacd, label: "MACD" },
      { key: "show_rsi", checked: showRsi, label: isUsLocale ? "Panel RSI" : "RSI painel" },
      { key: "show_supertrend", checked: showSupertrend, label: "Supertrend" },
      { key: "show_volume", checked: showVolume, label: isUsLocale ? "Chart volume" : "Volume gráfico" },
    ];

    return (
      <div id="panel-grafico" className="snbr-center-stack">
        <section className="snbr-chart-card">
          <div className="snbr-chart-topline">
            <div>
              <h2>{isUsLocale ? "Asset chart" : "Gráfico do ativo"}</h2>
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
            chart={chartForOperationalLevels}
            ticker={selectedTicker}
            interval={chartInterval}
            showMarkers={showMarkers}
            showZones={showZones}
            showPriceLine={showPriceLine}
            showVwap={showVwap}
            showMacd={showMacd}
            showRsi={showRsi}
            showSupertrend={showSupertrend}
            showVolume={showVolume}
            showSupport={showSupport}
            showResistance={showResistance}
            supportLevel={chartSupportResistanceLevels.support}
            resistanceLevel={chartSupportResistanceLevels.resistance}
            institutionalRsiValue={chartTimeframeRsi}
            rsiTimeframeLabel={rsiTimeframeLabel}
            rsiMetadata={chartRsiMetadata}
            levelMetadata={{
              symbol: selectedTicker,
              timeframe: chartInterval,
              as_of: chartSupportResistanceLevels.zones[0]?.as_of || null,
            }}
            locale={appLocale}
          />
          <p className="snbr-assistive-copy" data-chart-analysis-source-note="true">
            {isUsLocale
              ? "TradingView indicators use an external feed. The AI conclusion uses the normalized internal snapshot whose timeframe and cutoff are shown in the analysis basis; a provider difference never authorizes a trade."
              : "Os indicadores da TradingView usam fonte externa. A conclusão da IA usa o snapshot interno normalizado, com timeframe e horário-limite informados na base da análise; divergência entre provedores nunca autoriza operação."}
          </p>

          <div className="snbr-chart-now-strip">
            <div>
              <span>
                {chartNewsHistorical
                  ? (isUsLocale ? "Latest available news (historical)" : "Última notícia disponível (histórico)")
                  : (isUsLocale ? "Latest news" : "Última notícia")} · {selectedTicker}
                {chartNews?.source ? ` · ${chartNews.source}` : ""}
                {chartNewsTime ? ` · ${chartNewsTime}` : ""}
              </span>
              {chartNewsHistorical ? (
                <p className="snbr-assistive-copy">
                  {isUsLocale
                    ? `No current validated news for ${selectedTicker}. Showing the latest historical item available${chartNewsTime ? ` from ${chartNewsTime}` : ""}.`
                    : `Sem notícia atual validada para ${selectedTicker}. Exibindo a última disponível no histórico${chartNewsTime ? `, de ${chartNewsTime}` : ""}.`}
                </p>
              ) : null}
              <strong>{chartNewsTitle}</strong>
              {showChartNewsBody ? <p>{chartNewsText}</p> : null}
            </div>
            {chartNews?.url ? (
              <a className="snbr-section-head-action snbr-collapse-toggle snbr-open-news" href={chartNews.url} rel="noreferrer" target="_blank">
                {isUsLocale ? "Open news" : "Abrir notícia"}
              </a>
            ) : (
              <span className="snbr-chip">{isUsLocale ? "Real URL unavailable" : "URL real indisponível"}</span>
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
              isUsLocale ? "Current volume / daily average" : "Volume atual / média diária",
              dailyVolumeLabel,
              dailyVolumeRatio == null ? null : dailyVolumeRatio * 50,
              dailyVolumeRatio != null && dailyVolumeRatio >= 1.3 ? "bullish" : dailyVolumeRatio != null && dailyVolumeRatio < 0.7 ? "bearish" : "neutral",
              dailyVolumeRatio == null ? "—" : `${formatLocalePrice(dailyVolumeRatio, appLocale)}×`,
              isUsLocale ? "Informational data" : "Dado informativo",
            )}
          </div>

          {showZones && chartSupportResistanceLevels.zones.length ? (
            <div className="snbr-zone-row">
              {chartSupportResistanceLevels.zones.map((zone) => (
                <span key={`${zone.label}-${zone.price}`} className="snbr-chip">
                  {isUsLocale ? localizeUiText(String(zone.label || "").replace("RESISTENCIA", "RESISTANCE").replace("SUPORTE", "SUPPORT"), appLocale, selectedTicker) : zone.label}: {formatLocalePrice(zone.price, appLocale)}
                </span>
              ))}
            </div>
          ) : null}
          {showZones && chartMicroRange ? (
            <div className="snbr-zone-row">
              <span className="snbr-chip neutral">
                {isUsLocale ? "Intraday micro-range" : "Microfaixa intraday"} {chartMicroRange.timeframe}: {formatLocalePrice(chartMicroRange.support, appLocale)}–{formatLocalePrice(chartMicroRange.resistance, appLocale)}
              </span>
              <span className="snbr-chip neutral">{isUsLocale ? "Informational — non-operational" : "Informativa — não operacional"}</span>
              <span className="snbr-chip neutral">
                {operationalLevelsStatus === "INSUFFICIENT_SEPARATION"
                  ? (isUsLocale ? "Operational levels: insufficient separation" : "Níveis operacionais: sem separação suficiente")
                  : operationalLevelsStatus === "PENDING" || operationalLevelsStatus === "REFRESHING"
                    ? (isUsLocale ? "Operational levels: calculating…" : "Níveis operacionais: calculando…")
                    : operationalLevelsStatus === "READY"
                      ? (isUsLocale ? "Operational levels: confirmed" : "Níveis operacionais: confirmados")
                      : (isUsLocale ? "Operational levels: unavailable" : "Níveis operacionais: indisponíveis")}
              </span>
              {operationalLevelsStatus === "INSUFFICIENT_SEPARATION" ? (
                <span className="snbr-chip neutral">{isUsLocale ? "No support, resistance or operational entry was validated." : "Nenhum suporte, resistência ou entrada operacional validado."}</span>
              ) : null}
            </div>
          ) : null}
        </section>

        <div className="snbr-trader-social-banner">
          <h2>{isUsLocale ? "Trader Social Network" : "Rede Social do Trader"}</h2>
        </div>

        <section className="snbr-poll-inline">
          <div className="snbr-plain-panel snbr-poll-shell">
            <button
              className="snbr-side-card-trigger"
              onClick={() => setPollOpen((value) => !value)}
              type="button"
              aria-expanded={pollOpen}
            >
              <div>
                <h3>✦ {isUsLocale ? "Vote" : "Votar"}</h3>
                <p>{isUsLocale ? "Asset strategy vote" : "Votação da estratégia do ativo"}</p>
              </div>
              <span className="snbr-collapse-toggle">{pollOpen ? (isUsLocale ? "Close" : "Fechar") : (isUsLocale ? "Open" : "Abrir")}</span>
            </button>
            {pollOpen && activePoll ? (
            <div className="snbr-poll-card">
              <h4>{localizedActivePoll.question}</h4>
              <div className="snbr-poll-meta">
                <span>{localizedActivePoll.total_votes} {isUsLocale ? "votes" : "votos"}</span>
                <span>{localizedActivePoll.status || (isUsLocale ? "open" : "aberta")}</span>
                {activePoll.event_type ? <span>{localizeUiText(activePoll.event_type, appLocale, selectedTicker)}</span> : null}
                {activePoll.event_date ? <span>{new Date(activePoll.event_date).toLocaleDateString(appLocale)}</span> : null}
                {activePoll.event_source ? <span>{isUsLocale ? "Source" : "Fonte"}: {activePoll.event_source}</span> : null}
                {activePoll.valid_until ? <span>{isUsLocale ? "Valid until" : "Válida até"}: {new Date(activePoll.valid_until).toLocaleDateString(appLocale)}</span> : null}
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
            ) : pollOpen ? (
              <p className="snbr-assistive-copy snbr-poll-empty">
                {isUsLocale
                  ? "No active vote. Votes open automatically around the asset's relevant events."
                  : "Sem votação ativa. As votações são abertas automaticamente quando há eventos relevantes do ativo."}
              </p>
            ) : null}
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
        newsStatus={newsStatusForPanel}
      />
    );
  }

  function renderEducation() {
    return (
      <WorkspaceEducationPanel
        locale={appLocale}
        institutionalSections={isUsLocale ? INSTITUTIONAL_SECTIONS_EN : INSTITUTIONAL_SECTIONS}
        guides={workspace?.help_center.guides || []}
        activeInstitutionalSectionId={selectedInstitutionalSectionId}
      />
    );
  }

  function renderObservability() {
    const observability = (workspace?.observability || {}) as WorkspaceObservabilityDashboard;
    const providerItems = observability.providers?.items || [];
    const recentErrors = observability.recent_errors || [];
    const alertItems = (observability.alerts || []).filter(Boolean);

    return (
      <section className="snbr-tool-shell">
        <div className="snbr-tool-head">
          <div>
            <h2>{isUsLocale ? "Observability" : "Observabilidade"}</h2>
            <p>{isUsLocale ? "Admin view for health, providers and recent errors." : "Visão administrativa de saúde, providers e erros recentes."}</p>
          </div>
          <span className={cx("snbr-chip", String(observability.system_status || "HEALTHY").toLowerCase())}>{String(observability.system_status || "HEALTHY")}</span>
        </div>

        <div className="snbr-tool-reading-grid">
          <div className="snbr-tool-reading-card">
            <span>{isUsLocale ? "System" : "Sistema"}</span>
            <strong>{String(observability.system_status || "HEALTHY")}</strong>
            <p>{isUsLocale ? "Consolidated health center." : "Health center consolidado."}</p>
          </div>
          <div className="snbr-tool-reading-card">
            <span>{isUsLocale ? "Snapshot health" : "Saúde do snapshot"}</span>
            <strong>{String(observability.snapshot_health?.status || "HEALTHY")}</strong>
            <p>{observability.snapshot_health?.signals_generated || 0} {isUsLocale ? "generated" : "gerados"}</p>
          </div>
          <div className="snbr-tool-reading-card">
            <span>{isUsLocale ? "Auditor health" : "Saúde do auditor"}</span>
            <strong>{String(observability.auditor_health?.status || "IDLE")}</strong>
            <p>{observability.auditor_health?.blocked_ratio != null ? `${Math.round((observability.auditor_health.blocked_ratio || 0) * 100)}% blocked` : "--"}</p>
          </div>
          <div className="snbr-tool-reading-card">
            <span>{isUsLocale ? "Radar health" : "Saúde do radar"}</span>
            <strong>{String(observability.radar_health?.status || "IDLE")}</strong>
            <p>{observability.radar_health?.generated || 0} / {observability.radar_health?.blocked || 0}</p>
          </div>
          <div className="snbr-tool-reading-card">
            <span>{isUsLocale ? "Ranking health" : "Saúde do ranking"}</span>
            <strong>{String(observability.ranking_health?.status || "IDLE")}</strong>
            <p>{observability.ranking_health?.eligible || 0} {isUsLocale ? "eligible" : "elegíveis"}</p>
          </div>
          <div className="snbr-tool-reading-card">
            <span>{isUsLocale ? "Telegram health" : "Saúde do Telegram"}</span>
            <strong>{String(observability.telegram_health?.status || "IDLE")}</strong>
            <p>{observability.telegram_health?.sent || 0} {isUsLocale ? "sent" : "enviados"}</p>
          </div>
        </div>

        <div className="snbr-tool-stack">
          <div className="snbr-tool-reading-card">
            <span>{isUsLocale ? "Providers" : "Providers"}</span>
            <strong>{isUsLocale ? "Current status" : "Status atual"}</strong>
            <div className="snbr-pill-row">
              {providerItems.length ? providerItems.map((item: any) => (
                <span key={`${item.provider}-${item.status}`} className={cx("snbr-chip", String(item.status || "HEALTHY").toLowerCase())}>
                  {item.provider}: {item.status}
                </span>
              )) : <span className="snbr-chip">{isUsLocale ? "No provider data" : "Sem dados de provider"}</span>}
            </div>
          </div>

          <div className="snbr-tool-reading-card">
            <span>{isUsLocale ? "Error center" : "Centro de erros"}</span>
            <strong>{recentErrors.length} {isUsLocale ? "recent errors" : "erros recentes"}</strong>
            <p>{isUsLocale ? "Grouped without log spam." : "Agrupado sem spam de logs."}</p>
            <div className="snbr-tool-stack">
              {recentErrors.slice(0, 6).map((item: any, index: number) => (
                <div key={`${item.kind || "error"}-${item.timestamp || index}`} className="snbr-chip">
                  {item.kind}: {item.message}
                </div>
              ))}
            </div>
          </div>

          <div className="snbr-tool-reading-card">
            <span>{isUsLocale ? "Internal alerts" : "Alertas internos"}</span>
            <strong>{alertItems.length}</strong>
            <div className="snbr-tool-stack">
              {alertItems.slice(0, 6).map((item: any, index: number) => (
                <div key={`${item.kind || "alert"}-${index}`} className="snbr-chip">
                  {item.message} · {item.severity}
                </div>
              ))}
            </div>
          </div>
        </div>
      </section>
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
            <h2>{isUsLocale ? "Referrals" : "Afiliate Programa"}</h2>
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

  function renderStockFlowPanel() {
    return (
      <div className="snbr-stock-flow-container">
        <div className="snbr-stock-flow-banner">
          <div className="snbr-stock-flow-title-row">
            <div className="snbr-stock-flow-brand-title">
              <h2>🔥 STOCK FLOW</h2>
              <span className="snbr-stock-flow-badge">{isUsLocale ? "Official Real-Time Market Flow" : "O fluxo oficial do mercado em tempo real"}</span>
            </div>
            <span className="snbr-chip neutral">{isUsLocale ? "Monday 07/27" : "Segunda 27/07"}</span>
          </div>
          <p className="snbr-stock-flow-desc">
            {isUsLocale
              ? "The heart of StockNewsBR community. Every day a new theme, exclusive analysis, polls and community discussions."
              : "O coração da comunidade StockNewsBR. Todos os dias um novo tema, análises exclusivas, enquetes e discussão da comunidade."}
          </p>
        </div>

        <div className="snbr-stock-flow-subnav" role="tablist" aria-label="Stock Flow Days">
          {[
            { id: "aovivo", label: "🔴 Ao Vivo" },
            { id: "seg", label: "Seg" },
            { id: "ter", label: "Ter" },
            { id: "qua", label: "Qua" },
            { id: "qui", label: "Qui" },
            { id: "sex", label: "Sex" },
            { id: "sab", label: "Sáb" },
            { id: "dom", label: "Dom" },
          ].map((dayItem) => (
            <button
              key={dayItem.id}
              className={cx("snbr-stock-flow-subnav-btn", activeStockFlowDay === dayItem.id && "active")}
              onClick={() => setActiveStockFlowDay(dayItem.id)}
              type="button"
              role="tab"
              aria-selected={activeStockFlowDay === dayItem.id}
            >
              {dayItem.label}
            </button>
          ))}
        </div>

        {activeStockFlowDay === "aovivo" ? (
          <div className="snbr-stock-flow-live-card">
            <div className="snbr-stock-flow-live-header">
              <span className="snbr-live-pulse-dot">🔴</span>
              <strong>AO VIVO</strong>
              <span className="snbr-chip neutral">{isUsLocale ? "Se acontecer algo importante... fica fixo no topo." : "Se acontecer algo importante... fica fixo no topo."}</span>
            </div>
            {stockFlowLiveItems.length > 0 ? (
              <div className="snbr-stock-flow-live-updates">
                {stockFlowLiveItems.map((item) => (
                  <div key={item.id} className="snbr-live-update-item">
                    {item.text}
                  </div>
                ))}
              </div>
            ) : null}
            {isStockFlowAdmin ? (
            <div className="snbr-live-composer">
              <textarea
                className="snbr-input"
                style={{ minHeight: "180px" }}
                value={stockFlowLiveInput}
                onChange={(e) => setStockFlowLiveInput(e.target.value)}
                placeholder=""
              />
              <button className="snbr-button primary" onClick={handlePublishStockFlowLiveItem} type="button">
                {isUsLocale ? "PUBLICAR AO VIVO" : "PUBLICAR AO VIVO"}
              </button>
            </div>
            ) : null}
          </div>
        ) : null}

        <div className="snbr-plain-panel snbr-stock-flow-card">
          <div className="snbr-stock-flow-card-head">
            <div>
              <h3>📢 EDITORIAL OFICIAL STOCKNEWSBR</h3>
              <span>{editorialDate}</span>
            </div>
            {isStockFlowAdmin ? (
            <div className="snbr-pill-row">
              <button
                className="snbr-button secondary"
                onClick={editingStockFlowEditorial ? () => setEditingStockFlowEditorial(false) : handleStartEditEditorial}
                type="button"
              >
                {editingStockFlowEditorial ? (isUsLocale ? "Cancelar" : "Cancelar") : (isUsLocale ? "✍️ Editar" : "✍️ Editar")}
              </button>
            </div>
            ) : null}
          </div>

          {editingStockFlowEditorial ? (
            <div className="snbr-editorial-form">
              <div className="snbr-editorial-field">
                <label>{isUsLocale ? "Data / Horário" : "Data / Horário"}</label>
                <input
                  className="snbr-input"
                  value={editEditorialDateInput}
                  onChange={(e) => setEditEditorialDateInput(e.target.value)}
                  placeholder="Ex: 24 de Julho de 2026 — 08:30"
                />
              </div>
              <div className="snbr-editorial-field">
                <label>{isUsLocale ? "Título do Editorial" : "Título do Editorial"}</label>
                <input
                  className="snbr-input"
                  value={editEditorialTitleInput}
                  onChange={(e) => setEditEditorialTitleInput(e.target.value)}
                  placeholder="Ex: 📊 ABERTURA DO MERCADO & VISÃO DO DIA"
                />
              </div>
              <div className="snbr-editorial-field">
                <label>{isUsLocale ? "Texto Principal / Citação" : "Texto Principal / Citação"}</label>
                <textarea
                  className="snbr-input"
                  style={{ minHeight: "80px" }}
                  value={editEditorialQuoteInput}
                  onChange={(e) => setEditEditorialQuoteInput(e.target.value)}
                  placeholder="Escreva a visão de mercado do dia..."
                />
              </div>
              <div className="snbr-editorial-field">
                <label>{isUsLocale ? "Pontos Importantes (1 por linha)" : "Pontos Importantes (1 por linha)"}</label>
                <textarea
                  className="snbr-input"
                  style={{ minHeight: "80px" }}
                  value={editEditorialPointsInput}
                  onChange={(e) => setEditEditorialPointsInput(e.target.value)}
                  placeholder="Agenda econômica&#10;Empresas do trimestre&#10;Eventos do dia"
                />
              </div>
              <button className="snbr-button primary" onClick={handleSaveEditorial} type="button">
                {isUsLocale ? "PUBLICAR EDITORIAL" : "PUBLICAR EDITORIAL"}
              </button>
            </div>
          ) : (
            <div className="snbr-stock-flow-editorial-body">
              <h4>{editorialTitle}</h4>
              <p className="snbr-editorial-quote">
                &quot;{editorialQuote}&quot;
              </p>
              <div className="snbr-editorial-points">
                <strong>Pontos importantes:</strong>
                <ul>
                  {editorialPoints.map((pt, idx) => (
                    <li key={idx}>{pt}</li>
                  ))}
                </ul>
              </div>
            </div>
          )}
        </div>

        <div className="snbr-plain-panel snbr-stock-flow-card">
          <div className="snbr-stock-flow-card-head">
            {editingStockFlowPollQuestion ? (
              <div style={{ flex: 1, marginRight: "12px" }}>
                <input
                  className="snbr-input"
                  value={editStockFlowPollQuestionInput}
                  onChange={(e) => setEditStockFlowPollQuestionInput(e.target.value)}
                  onKeyDown={(e) => { if (e.key === "Enter") handleSavePollQuestion(); }}
                  placeholder="Qual o seu viés para o Ibovespa hoje?"
                />
              </div>
            ) : (
              <h3>📊 ENQUETE DO DIA: {stockFlowPollQuestion}</h3>
            )}
            <div className="snbr-pill-row">
              <span className="snbr-chip">1.910 {isUsLocale ? "votes" : "votos"}</span>
              {isStockFlowAdmin ? (
              <button
                className="snbr-button secondary"
                onClick={editingStockFlowPollQuestion ? handleSavePollQuestion : handleStartEditPollQuestion}
                type="button"
              >
                {editingStockFlowPollQuestion ? (isUsLocale ? "Salvar" : "Salvar") : (isUsLocale ? "✍️ Editar" : "✍️ Editar")}
              </button>
              ) : null}
            </div>
          </div>
          <div className="snbr-stock-flow-poll-options">
            <div className={cx("snbr-stock-flow-poll-option", stockFlowPollVote === "A" && "selected")}>
              <div className="snbr-poll-opt-info">
                <strong>[ A ] 🐂 Touro (Alta)</strong>
                <span>{stockFlowPollVote ? "65% (1.240 votos)" : "65%"}</span>
              </div>
              <div className="snbr-poll-bar-bg"><div className="snbr-poll-bar-fill bullish" style={{ width: "65%" }}></div></div>
              <button className="snbr-button secondary" onClick={() => setStockFlowPollVote("A")} type="button">
                {stockFlowPollVote === "A" ? (isUsLocale ? "Voted ✓" : "Votado ✓") : (isUsLocale ? "VOTAR AGORA" : "VOTAR AGORA")}
              </button>
            </div>
            <div className={cx("snbr-stock-flow-poll-option", stockFlowPollVote === "B" && "selected")}>
              <div className="snbr-poll-opt-info">
                <strong>[ B ] 🐻 Urso (Baixa)</strong>
                <span>{stockFlowPollVote ? "35% (670 votos)" : "35%"}</span>
              </div>
              <div className="snbr-poll-bar-bg"><div className="snbr-poll-bar-fill bearish" style={{ width: "35%" }}></div></div>
              <button className="snbr-button secondary" onClick={() => setStockFlowPollVote("B")} type="button">
                {stockFlowPollVote === "B" ? (isUsLocale ? "Voted ✓" : "Votado ✓") : (isUsLocale ? "VOTAR AGORA" : "VOTAR AGORA")}
              </button>
            </div>
          </div>
        </div>

        <div className="snbr-plain-panel snbr-stock-flow-card">
          <div className="snbr-stock-flow-card-head">
            <h3>💬 CHAT DOS TRADERS | NOTICIA DO DIA</h3>
            <span className="snbr-chip bullish">342 online</span>
          </div>
          <div className="snbr-stock-flow-chat-messages">
            {stockFlowChatMessages.map((msg) => (
              <div key={msg.id} className="snbr-stock-flow-chat-line">
                <span className="snbr-chat-time">[{msg.time}]</span>
                <strong className="snbr-chat-user">{msg.user}:</strong>
                <span className="snbr-chat-text">&quot;{msg.text}&quot;</span>
              </div>
            ))}
          </div>
          <div className="snbr-stock-flow-chat-composer">
            <input
              className="snbr-input"
              value={stockFlowChatInput}
              onChange={(e) => setStockFlowChatInput(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter") handleSendStockFlowChatMessage(); }}
              placeholder={isUsLocale ? "Type your message or analysis here..." : "✍️ Digite sua mensagem ou análise aqui..."}
            />
            <button className="snbr-button primary" onClick={handleSendStockFlowChatMessage} type="button">
              {isUsLocale ? "SEND" : "ENVIAR"}
            </button>
          </div>
        </div>
      </div>
    );
  }

  function renderCenterPanel() {
    if (currentTab === "grafico") return renderGrafico();
    if (currentTab === "stockflow") return renderStockFlowPanel();
    if (currentTab === "news") return renderNews();
    if (currentTab === "busca") return renderSearchTab();
    if (currentTab === "flow") return renderToolTab(TOOL_COPY.flow.title, TOOL_COPY.flow.description);
    if (currentTab === "liquidity") return renderToolTab(TOOL_COPY.liquidity.title, TOOL_COPY.liquidity.description);
    if (currentTab === "trend") return renderToolTab(TOOL_COPY.trend.title, TOOL_COPY.trend.description);
    if (currentTab === "momentum") return renderToolTab(TOOL_COPY.momentum.title, TOOL_COPY.momentum.description);
    if (currentTab === "smart-money") return renderToolTab(TOOL_COPY["smart-money"].title, TOOL_COPY["smart-money"].description);
    if (currentTab === "risk") return renderToolTab(TOOL_COPY.risk.title, TOOL_COPY.risk.description);
    if (currentTab === "news-ia") return renderToolTab(TOOL_COPY["news-ia"].title, TOOL_COPY["news-ia"].description);
    if (currentTab === "macro") return renderToolTab(TOOL_COPY.macro.title, TOOL_COPY.macro.description);
    if (currentTab === "regime") return renderToolTab(TOOL_COPY.regime.title, TOOL_COPY.regime.description);
    if (currentTab === "referrals") return renderReferrals();
    if (currentTab === "education") return renderEducation();
    if (currentTab === "observability") return renderObservability();
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
              <div className="snbr-account-line"><span>{isUsLocale ? "System" : "Sistema"}</span><strong>{statusLabel(access?.plan_status)}</strong></div>
              <div className="snbr-account-line"><span>Telegram</span><strong>{access?.telegram_linked ? `@${access?.telegram_username || (isUsLocale ? "linked" : "vinculado")}` : (access?.access?.telegram ? (isUsLocale ? "ready to link" : "pronto para vincular") : (isUsLocale ? "blocked on current plan" : "bloqueado no plano atual"))}</strong></div>
            </div>
            <button className="snbr-button primary" disabled={profileSaving} onClick={() => void handleSaveProfile()} type="button">
              {profileSaving ? (isUsLocale ? "Saving..." : "Salvando...") : (isUsLocale ? "Save profile" : "Salvar perfil")}
            </button>
          </div>
          <div className="snbr-profile-editor">
            <label className="snbr-profile-field">
              <span>{isUsLocale ? "Change e-mail" : "Alterar e-mail"}</span>
              <input
                className="snbr-input"
                value={emailChangeInput}
                onChange={(event) => setEmailChangeInput(event.target.value)}
                placeholder={isUsLocale ? "New e-mail" : "Novo e-mail"}
                type="email"
                autoComplete="email"
              />
            </label>
            {emailChangeToken ? (
              <>
                <label className="snbr-profile-field">
                  <span>{isUsLocale ? "Access code" : "Código de acesso"}</span>
                  <input
                    className="snbr-input"
                    value={emailChangeCode}
                    onChange={(event) => setEmailChangeCode(event.target.value.replace(/\D/g, "").slice(0, 6))}
                    placeholder="000000"
                    inputMode="numeric"
                    pattern="[0-9]*"
                    maxLength={6}
                    autoComplete="one-time-code"
                    aria-label={isUsLocale ? "E-mail change code" : "Código de confirmação do novo e-mail"}
                  />
                </label>
                <button className="snbr-button primary" onClick={() => void handleVerifyEmailChange()} type="button">
                  {isUsLocale ? "Confirm new e-mail" : "Confirmar novo e-mail"}
                </button>
              </>
            ) : (
              <button className="snbr-button secondary" onClick={() => void handleRequestEmailChange()} type="button">
                {isUsLocale ? "Send code" : "Enviar código"}
              </button>
            )}
            {emailChangeNotice ? <div className="snbr-empty">{emailChangeNotice}</div> : null}
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
          <button className="snbr-button secondary" onClick={() => void handleLogoutAll()} type="button">
            {isUsLocale ? "Sign out of all devices" : "Sair de todos os dispositivos"}
          </button>
        </div>
      );
    }

    if (pendingLoginToken) {
      return (
        <div className="snbr-side-card">
          <div className="snbr-section-head compact">
            <div>
              <h3>{isUsLocale ? "Access code" : "Código de acesso"}</h3>
              <p>{isUsLocale ? "Enter the 6-digit code we sent to your e-mail." : "Digite o código de 6 dígitos enviado para o seu e-mail."}</p>
            </div>
          </div>
          <div className="snbr-auth">
            <label className="snbr-profile-field">
              <span>{isUsLocale ? "Access code" : "Código de acesso"}</span>
              <input
                className="snbr-input"
                value={otpCode}
                onChange={(event) => setOtpCode(event.target.value.replace(/\D/g, "").slice(0, 6))}
                placeholder="000000"
                inputMode="numeric"
                pattern="[0-9]*"
                maxLength={6}
                autoComplete="one-time-code"
                aria-label={isUsLocale ? "6-digit access code" : "Código de acesso de 6 dígitos"}
              />
            </label>
            <button className="snbr-button primary" disabled={loginBusy || otpCode.length !== 6} onClick={handleVerifyOtp} type="button">
              {loginBusy ? (isUsLocale ? "Verifying..." : "Verificando...") : (isUsLocale ? "Log in" : "Entrar")}
            </button>
            <button
              className="snbr-button secondary"
              disabled={loginBusy || resendCooldownUntil > Date.now()}
              onClick={() => void handleRequestCode()}
              type="button"
            >
              {isUsLocale ? "Resend code" : "Reenviar código"}
            </button>
            <button
              className="snbr-button secondary"
              onClick={() => {
                setPendingLoginToken("");
                setOtpCode("");
                setLoginNotice("");
              }}
              type="button"
            >
              {isUsLocale ? "Back" : "Voltar"}
            </button>
            {loginNotice ? <div className="snbr-empty">{loginNotice}</div> : null}
            {loginError ? <div className="snbr-empty">{loginError}</div> : null}
          </div>
        </div>
      );
    }

    return (
      <div className="snbr-side-card">
        <div className="snbr-section-head compact">
          <div>
            <h3>{isUsLocale ? "Authentication" : "Autenticação"}</h3>
            <p>{isUsLocale ? "Enter your e-mail to receive a secure access code." : "Informe seu e-mail para receber um código de acesso seguro."}</p>
          </div>
        </div>
        <div className="snbr-auth">
          <label className="snbr-profile-field">
            <span>E-mail</span>
            <input
              className="snbr-input"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              placeholder="E-mail"
              type="email"
              autoComplete="email"
              ref={loginEmailInputRef}
            />
          </label>
          <button className="snbr-button primary" disabled={loginBusy || resendCooldownUntil > Date.now()} onClick={() => void handleRequestCode()} type="button">
            {loginBusy ? (isUsLocale ? "Sending..." : "Enviando...") : (isUsLocale ? "Send code" : "Enviar código")}
          </button>
          {loginNotice ? <div className="snbr-empty">{loginNotice}</div> : null}
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

  function statusLabel(status?: string | null) {
    const normalized = String(status || "").toLowerCase();
    if (normalized === "trialing" || normalized === "trial") return isUsLocale ? "TEST" : "TESTE";
    if (["active", "premium", "paid", "ativo"].includes(normalized)) return "PRO";
    return status || "n/a";
  }

  function planLabel(plan?: string | null) {
    const normalized = String(plan || "").toLowerCase();
    if (normalized === "premium") return "Premium";
    if (normalized === "trial") return isUsLocale ? "30-day trial" : "Trial 30 dias";
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
            ? "The first app access starts a 30-day trial. After it ends, the account moves to Free if Premium is not active."
            : "O primeiro acesso pelo app entra em Trial por 30 dias. Ao final, a conta migra automaticamente para Basico se nao houver Premium ativo."}
        </small>
      </div>
    );
  }

  function renderAccessCard() {
    if (token) {
      return (
        <div className="snbr-side-card snbr-side-card-highlight">
          <button
            className="snbr-side-card-trigger"
            onClick={() => setAccessOpen((value) => !value)}
            type="button"
            aria-expanded={accessOpen}
          >
            <div>
              <h3>{isUsLocale ? "Platform access" : "Acesso à plataforma"}</h3>
              <p>{isUsLocale ? "Account ready for website, app and Telegram according to the plan." : "Conta pronta para website, app e Telegram de acordo com o plano."}</p>
            </div>
            <span className="snbr-collapse-toggle">{accessOpen ? (isUsLocale ? "Close" : "Fechar") : (isUsLocale ? "Open" : "Abrir")}</span>
          </button>
          {accessOpen ? <>
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
            <div className="snbr-account-line"><span>{isUsLocale ? "System" : "Sistema"}</span><strong>{statusLabel(access?.plan_status)}</strong></div>
            <div className="snbr-account-line"><span>{isUsLocale ? "Test ends" : "Teste termina"}</span><strong>{formatDatePtBr(access?.trial_expires_at)}</strong></div>
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
              <label className="snbr-profile-field">
                <span>{isUsLocale ? "Change e-mail" : "Alterar e-mail"}</span>
                <input
                  className="snbr-input"
                  value={emailChangeInput}
                  onChange={(event) => setEmailChangeInput(event.target.value)}
                  placeholder={isUsLocale ? "New e-mail" : "Novo e-mail"}
                  type="email"
                  autoComplete="email"
                />
              </label>
              {emailChangeToken ? (
                <>
                  <label className="snbr-profile-field">
                    <span>{isUsLocale ? "Access code" : "Código de acesso"}</span>
                    <input
                      className="snbr-input"
                      value={emailChangeCode}
                      onChange={(event) => setEmailChangeCode(event.target.value.replace(/\D/g, "").slice(0, 6))}
                      placeholder="000000"
                      inputMode="numeric"
                      pattern="[0-9]*"
                      maxLength={6}
                      autoComplete="one-time-code"
                      aria-label={isUsLocale ? "E-mail change code" : "Código de confirmação do novo e-mail"}
                    />
                  </label>
                  <button className="snbr-button primary" onClick={() => void handleVerifyEmailChange()} type="button">
                    {isUsLocale ? "Confirm new e-mail" : "Confirmar novo e-mail"}
                  </button>
                </>
              ) : (
                <button className="snbr-button secondary" onClick={() => void handleRequestEmailChange()} type="button">
                  {isUsLocale ? "Send code" : "Enviar código"}
                </button>
              )}
              {emailChangeNotice ? <div className="snbr-empty">{emailChangeNotice}</div> : null}
            </div>
          ) : null}
          {accountPanel === "upgrade" ? renderUpgradeOptions() : null}
          <div className="snbr-legal-note">
            {isUsLocale ? "Google Play app and legal terms are the official entry. Premium unlocks app, website and Telegram." : "App Google Play e o termo legal sao a entrada oficial. Premium libera app, website e Telegram."}
          </div>
          <button className="snbr-button secondary" onClick={() => void handleLogout()} type="button">{isUsLocale ? "Sign out" : "Sair"}</button>
          <button className="snbr-button secondary" onClick={() => void handleLogoutAll()} type="button">
            {isUsLocale ? "Sign out of all devices" : "Sair de todos os dispositivos"}
          </button>
          </> : null}
        </div>
      );
    }

    if (pendingLoginToken) {
      return (
        <div className="snbr-side-card snbr-side-card-highlight">
          <button className="snbr-side-card-trigger" onClick={() => setAccessOpen((value) => !value)} type="button" aria-expanded={accessOpen}>
            <div>
              <h3>{isUsLocale ? "Platform access" : "Acesso à plataforma"}</h3>
              <p>{isUsLocale ? "Enter the 6-digit code we sent to your e-mail." : "Digite o código de 6 dígitos enviado para o seu e-mail."}</p>
            </div>
            <span className="snbr-collapse-toggle">{accessOpen ? (isUsLocale ? "Close" : "Fechar") : (isUsLocale ? "Open" : "Abrir")}</span>
          </button>
          {accessOpen ? (
          <div className="snbr-auth">
            <label className="snbr-profile-field">
              <span>{isUsLocale ? "Access code" : "Código de acesso"}</span>
              <input
                className="snbr-input"
                value={otpCode}
                onChange={(event) => setOtpCode(event.target.value.replace(/\D/g, "").slice(0, 6))}
                placeholder="000000"
                inputMode="numeric"
                pattern="[0-9]*"
                maxLength={6}
                autoComplete="one-time-code"
                aria-label={isUsLocale ? "6-digit access code" : "Código de acesso de 6 dígitos"}
              />
            </label>
            <button className="snbr-button primary" disabled={loginBusy || otpCode.length !== 6} onClick={handleVerifyOtp} type="button">
              {loginBusy ? (isUsLocale ? "Verifying..." : "Verificando...") : (isUsLocale ? "Log in" : "Entrar")}
            </button>
            <button
              className="snbr-button secondary"
              disabled={loginBusy || resendCooldownUntil > Date.now()}
              onClick={() => void handleRequestCode()}
              type="button"
            >
              {isUsLocale ? "Resend code" : "Reenviar código"}
            </button>
            <button
              className="snbr-button secondary"
              onClick={() => {
                setPendingLoginToken("");
                setOtpCode("");
                setLoginNotice("");
              }}
              type="button"
            >
              {isUsLocale ? "Back" : "Voltar"}
            </button>
            {loginNotice ? <div className="snbr-empty">{loginNotice}</div> : null}
            {loginError ? <div className="snbr-empty">{loginError}</div> : null}
          </div>
          ) : null}
        </div>
      );
    }

    return (
      <div className="snbr-side-card snbr-side-card-highlight">
        <button className="snbr-side-card-trigger" onClick={() => setAccessOpen((value) => !value)} type="button" aria-expanded={accessOpen}>
          <div>
            <h3>{isUsLocale ? "Platform access" : "Acesso à plataforma"}</h3>
            <p>{isUsLocale ? "Enter your e-mail to receive a secure access code." : "Informe seu e-mail para receber um código de acesso seguro."}</p>
          </div>
          <span className="snbr-collapse-toggle">{accessOpen ? (isUsLocale ? "Close" : "Fechar") : (isUsLocale ? "Open" : "Abrir")}</span>
        </button>
        {accessOpen ? (
        <div className="snbr-auth">
          <label className="snbr-profile-field">
            <span>E-mail</span>
            <input
              ref={loginEmailInputRef}
              className="snbr-input"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              placeholder="E-mail"
              type="email"
              autoComplete="email"
            />
          </label>
          <button className="snbr-button primary" disabled={loginBusy || resendCooldownUntil > Date.now()} onClick={() => void handleRequestCode()} type="button">
            {loginBusy ? (isUsLocale ? "Sending..." : "Enviando...") : (isUsLocale ? "Send code" : "Enviar código")}
          </button>
          {loginNotice ? <div className="snbr-empty">{loginNotice}</div> : null}
          {loginError ? <div className="snbr-empty">{loginError}</div> : null}
        </div>
        ) : null}
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
            <h3>{isUsLocale ? "Notifications" : "Notificação"}</h3>
            <p>{isUsLocale ? "Notices to be published on website, app and Telegram." : "Avisos a serem publicados no website, app e Telegram."}</p>
          </div>
          <span className="snbr-collapse-toggle">{notificationOpen ? (isUsLocale ? "Close" : "Fechar") : (isUsLocale ? "Open" : "Abrir")}</span>
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
            <p>{isUsLocale ? "Account preferences, blocked and muted users." : "Preferências da conta, bloqueados e silenciados."}</p>
          </div>
          <span className="snbr-collapse-toggle">{toolsOpen ? (isUsLocale ? "Close" : "Fechar") : (isUsLocale ? "Open" : "Abrir")}</span>
        </button>
        {toolsOpen ? (
          <>
        <div className="snbr-settings-tabs" role="tablist" aria-label={isUsLocale ? "Settings tools" : "Ferramentas de configuração"}>
          <button
            className={cx("snbr-settings-tab", settingsTab === "preferencias" && "active")}
            onClick={() => {
              setSettingsTab("preferencias");
            }}
            type="button"
          >
            {isUsLocale ? "Preferences" : "Preferências"}
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
                <strong>{isUsLocale ? "Display" : "Exibição"}</strong>
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
        stats={coherentDisplayStats}
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

  function renderReportDialog() {
    if (!reportTargetPost) return null;

    return (
      <div className="snbr-report-panel" role="dialog" aria-modal="true" aria-label={isUsLocale ? "Report post" : "Denunciar post"} data-social-report-dialog="true">
        <div className="snbr-report-panel-card">
          <div className="snbr-report-panel-head">
            <strong>{isUsLocale ? "Report to StockNewsBR" : "Denunciar para StockNewsBR"}</strong>
            <button
              className="snbr-toolbar-icon"
              onClick={() => setReportTargetPost(null)}
              type="button"
              aria-label={isUsLocale ? "Close report" : "Fechar denúncia"}
            >
              x
            </button>
          </div>
          <p>{isUsLocale ? "Choose the reason so moderation can audit this post." : "Escolha o motivo para a moderação auditar este post."}</p>
          <div className="snbr-report-reasons">
            {SOCIAL_REPORT_REASONS.map((reason) => (
              <button
                key={reason.key}
                className={cx("snbr-report-reason", reportReason === reason.key && "active")}
                onClick={() => setReportReason(reason.key)}
                type="button"
                aria-pressed={reportReason === reason.key}
                data-report-reason={reason.key}
              >
                {isUsLocale ? reason.labelEn : reason.labelPt}
              </button>
            ))}
          </div>
          <textarea
            className="snbr-input snbr-report-note"
            value={reportNote}
            onChange={(event) => setReportNote(event.target.value)}
            placeholder={isUsLocale ? "Optional note" : "Observação opcional"}
          />
          <div className="snbr-report-actions">
            <button className="snbr-button subtle" onClick={() => setReportTargetPost(null)} type="button">
              {isUsLocale ? "Cancel" : "Cancelar"}
            </button>
            <button
              className="snbr-button danger"
              disabled={reportingPostId === reportTargetPost.id}
              onClick={() => void handleReport(reportTargetPost.id)}
              type="button"
              data-social-report-submit="true"
            >
              {reportingPostId === reportTargetPost.id ? (isUsLocale ? "Reporting..." : "Denunciando...") : (isUsLocale ? "Report" : "Denunciar")}
            </button>
          </div>
        </div>
      </div>
    );
  }

  if (focusedTab) {
    const focusedLabel = getTabMeta(currentTabs.find((tab) => tab.id === currentTab) || FALLBACK_TABS[0], appLocale);

    return (
      <div className={cx("snbr-app", darkMode && "theme-dark", "snbr-popout-mode")}>
      <div className="snbr-popout-header">
          <div>
            <h1>{focusedLabel.label}</h1>
            <p>{isUsLocale ? `${selectedTicker} in detached monitor mode.` : `${selectedTicker} em modo destacável para monitor separado.`}</p>
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
        {renderReportDialog()}
      {renderLoginDialog()}
      </div>
    );
  }

  function renderLoginDialog() {
    if (!loginModalOpen) return null;
    const busyLabel = isUsLocale ? "Working..." : "Processando...";
    return (
      <div className="snbr-modal-backdrop" onClick={() => closeLoginDialog()}>
        <div
          className="snbr-modal snbr-login-modal"
          role="dialog"
          aria-modal="true"
          aria-labelledby="snbr-login-dialog-title"
          onClick={(event) => event.stopPropagation()}
        >
          <h3 id="snbr-login-dialog-title">{isUsLocale ? "Sign in" : "Entrar"}</h3>
          <p>
            {isUsLocale
              ? "Enter your e-mail to receive a secure access code."
              : "Informe seu e-mail para receber um código de acesso seguro."}
          </p>
          {pendingLoginToken ? (
            <label className="snbr-profile-field">
              <span>{isUsLocale ? "Access code" : "Código de acesso"}</span>
              <input
                className="snbr-input"
                value={otpCode}
                onChange={(event) => setOtpCode(event.target.value)}
                placeholder={isUsLocale ? "Access code" : "Código de acesso"}
                inputMode="numeric"
                autoComplete="one-time-code"
              />
            </label>
          ) : (
            <label className="snbr-profile-field">
              <span>E-mail</span>
              <input
                className="snbr-input"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                placeholder="E-mail"
                type="email"
                autoComplete="email"
                ref={loginDialogEmailRef}
              />
            </label>
          )}
          {loginNotice ? <div className="snbr-empty">{loginNotice}</div> : null}
          {loginError ? <div className="snbr-empty" role="alert">{loginError}</div> : null}
          <div className="snbr-modal-actions">
            <button
              className="snbr-button primary"
              type="button"
              disabled={loginBusy || (!pendingLoginToken && resendCooldownUntil > Date.now())}
              onClick={() => void (pendingLoginToken ? handleVerifyOtp() : handleRequestCode())}
            >
              {loginBusy
                ? busyLabel
                : pendingLoginToken
                  ? (isUsLocale ? "Sign in" : "Entrar")
                  : (isUsLocale ? "Send code" : "Enviar código")}
            </button>
            <button className="snbr-button secondary" type="button" onClick={() => closeLoginDialog()}>
              {isUsLocale ? "Cancel" : "Cancelar"}
            </button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className={cx("snbr-app", darkMode && "theme-dark")}>
      <a className="snbr-skip-link" href="#snbr-main-content">{isUsLocale ? "Skip to main content" : "Pular para o conteúdo principal"}</a>
      {renderReportDialog()}
      {renderLoginDialog()}
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
          activeWatchCount={activeWatchCountForFilter}
          watchCategoryCounts={activeWatchCategoryCounts}
          accessCard={renderAccessCard()}
          authCard={null}
          notificationCard={renderNotificationCard()}
          toolsCard={renderToolsCard()}
          watchlistContent={renderWatchlist()}
          institutionalSections={isUsLocale ? INSTITUTIONAL_SECTIONS_EN : INSTITUTIONAL_SECTIONS}
          onOpenInstitutionalSection={openInstitutionalSection}
          activeInstitutionalSectionId={selectedInstitutionalSectionId}
        />

      <main className="snbr-symbol-page" id="snbr-main-content">
        {loginError === "Sua sessão foi encerrada porque houve login em outro dispositivo." ? (
          <div className="snbr-empty" role="status">{loginError}</div>
        ) : null}
        <div className="snbr-sticky-top">
        <nav className="snbr-symbol-tabs snbr-top-tabs" aria-label={isUsLocale ? "Symbol tabs" : "Tabs do símbolo"} role="tablist">
          <div className="snbr-tab-list">
            {visibleTabs.map((tab) => {
              const meta = getTabMeta(tab, appLocale);
              const isAiTab = Boolean(AI_TOOL_TAB_MAP[tab.id as keyof typeof AI_TOOL_TAB_MAP]);
              const isGlobalAiAlertTab = GLOBAL_AI_ALERT_TAB_IDS.has(tab.id);
              const tabCount = tab.id === "news"
                ? freshNewsCount
                : isAiTab
                  ? aiToolFindingCounts[tab.id] ?? 0
                  : 0;
              // A "0" chip on every AI tab reads as a broken feature. The count badge is meant to
              // flag "N findings here" -- with none, show just the tab name (the panel itself says
              // "no signals" on open). Only surface the chip when there is a real count.
              const showTabCount = tabCount != null && tabCount > 0 && (tab.id === "news" || isAiTab);
              const tabTitle = tab.id === "news"
                ? newsIsHistorical
                  ? (isUsLocale
                      ? `${meta.label} — no current validated news; ${newsRows.length} historical item(s) available.`
                      : `${meta.label} — nenhuma notícia atual validada; ${newsRows.length} item(ns) histórico(s) disponível(is).`)
                  : (isUsLocale
                      ? `${meta.label} — ${freshNewsCount} current validated news item(s).`
                      : `${meta.label} — ${freshNewsCount} notícia(s) atual(is) validada(s).`)
                : isGlobalAiAlertTab
                  ? (isUsLocale
                    ? `${meta.label} — ${tabCount} current global market alerts; not the selected asset's on-demand analysis.`
                    : `${meta.label} — ${tabCount} alertas globais atuais do mercado; não são a análise sob demanda do ativo selecionado.`)
                  : meta.label;

              return (
                <div key={tab.id} className="snbr-symbol-tab-shell">
                  <button
                    className={cx("snbr-symbol-tab", currentTab === tab.id && "active")}
                    onClick={() => setActiveTab(tab.id)}
                    aria-selected={currentTab === tab.id}
                    aria-controls={`panel-${tab.id}`}
                    aria-label={tabTitle}
                    role="tab"
                    type="button"
                    title={tabTitle}
                    data-tab-id={tab.id}
                    data-tab-count={String(tabCount)}
                    data-tab-scope={isGlobalAiAlertTab ? "global" : "selected-symbol"}
                  >
                    <span>{topTabText(tab.id, meta.short, appLocale)}</span>
                    {showTabCount ? (
                      <span
                        className="snbr-tab-count-badge"
                        aria-label={isGlobalAiAlertTab
                          ? (isUsLocale ? `${tabCount} current global market alerts` : `${tabCount} alertas globais atuais do mercado`)
                          : (isUsLocale ? `${tabCount} current items` : `${tabCount} itens atuais`)}
                        title={isGlobalAiAlertTab ? tabTitle : undefined}
                      >
                        {tabCount}
                      </span>
                    ) : null}
                  </button>
                </div>
              );
            })}
          </div>
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
            aria-label={
              proModeLocked
                ? (isUsLocale ? "Pro Mode locked" : "Modo Pro bloqueado")
                : advancedMode
                  ? (isUsLocale ? "Switch to Basic Mode" : "Mudar para Modo Básico")
                  : (isUsLocale ? "Switch to Pro Mode" : "Mudar para Modo Pro")
            }
            title={
              proModeLocked
                ? (isUsLocale ? "Pro Mode locked after trial unless Premium is active" : "Modo Pro bloqueado após o trial sem Premium ativo")
                : advancedMode
                  ? (isUsLocale ? "Show simple mode" : "Mostrar modo simples")
                  : (isUsLocale ? "Open Pro details" : "Abrir detalhes Pro")
            }
          >
            {proModeLocked
              ? (isUsLocale ? "🔒 Pro Mode" : "🔒 Modo Pro")
              : advancedMode
                ? (isUsLocale ? "Basic Mode" : "Modo Básico")
                : (isUsLocale ? "Pro Mode" : "Modo Pro")}
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

        {indexStrip.length ? (
          <section className="snbr-index-strip" aria-label={isUsLocale ? "Market indices" : "Índices de mercado"}>
            {indexStrip.map((item) => {
              // Not movementClass(): indices carry no score, and its score fallback
              // paints a flat (0%) index red.
              const pct = Number(item.change_pct);
              const tone = !Number.isFinite(pct) || pct === 0 ? "mid" : pct > 0 ? "up" : "down";
              return (
                <div key={item.symbol} className={cx("snbr-index-card", tone)}>
                  <div className="snbr-index-copy">
                    <strong>{item.display_name || item.symbol}</strong>
                    <span className="snbr-index-price">{formatLocalePrice(item.price, appLocale)}</span>
                    <span className={cx("snbr-index-change", tone)}>
                      {formatSignedPrice(item.change, appLocale)} ({formatSignedPercent(item.change_pct)})
                    </span>
                  </div>
                  <IndexSparkline closes={(item.spark || []).map(Number).filter((value) => Number.isFinite(value))} />
                </div>
              );
            })}
          </section>
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
                  <AssetMark
                    symbol={item.symbol}
                    name={item.label}
                    logoUrl={(item as { logoUrl?: string | null }).logoUrl}
                    compact
                  />
                  <strong>{item.symbol}</strong>
                  <span className={cx("snbr-tape-value", movementClass(item.changePct, item.trend, item.score))}>
                    {movementArrow(movementClass(item.changePct, item.trend, item.score))}{" "}
                    {formatMarketMovementText(item, appLocale)}
                  </span>
                </button>
              ))}
            </div>
          </div>
        </section>
        </div>

        {showSymbolHeader ? (
          <section className="snbr-symbol-header">
            <div className="snbr-symbol-main">
              <div className="snbr-breadcrumb">Home / Symbol / {selectedTicker}</div>
              <div className="snbr-symbol-title-row">
                <AssetMark symbol={selectedTicker} name={symbolLabel} logoUrl={symbolLogoUrl} />
                <div>
                  <h2>{selectedTicker}</h2>
                  {symbolLabel ? <p>{symbolLabel}</p> : null}
                </div>
                <span className="snbr-chip">{selectedTickerMarketLabel}</span>
              </div>
              <div className="snbr-price-line">
                <strong>{formatAssetMoney(displayQuote?.price, selectedTicker, appLocale)}</strong>
              </div>
              <div className={cx("snbr-daily-change-line", priceDirectionClass)}>
                {displayQuoteHasCoreData ? (
                  <>
                    <span aria-hidden="true">{movementArrow(priceDirectionClass)}</span>
                    <strong>{formatSignedPrice(priceMovementValue, appLocale)}</strong>
                    <span>({formatSignedPercent(priceMovementPercent)})</span>
                    <small>{isUsLocale ? "Today" : "Hoje"} · {priceMovementLabel}</small>
                  </>
                ) : (
                  <small>{isUsLocale ? "No confirmed daily change" : "Sem variação diária confirmada"}</small>
                )}
              </div>
              {!advancedMode ? (
                <div className="snbr-basic-pro-lock" aria-label={isUsLocale ? "Premium metrics hidden in Basic Mode" : "Métricas premium ocultas no Modo Básico"}>
                  {isUsLocale ? "Premium metrics available on the Pro Plan" : "Métricas premium disponíveis no Plano Pro"}
                </div>
              ) : null}
            </div>

            <div className="snbr-stat-strip" aria-label={isUsLocale ? "Indicator explanation boxes" : "Boxes explicativos dos indicadores"}>
              {coherentDisplayStats.map((item) => (
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
          {loading && token ? <div className="snbr-empty">Carregando contexto do usuário...</div> : null}
          {showSymbolHeader ? (
            <section
              className="snbr-decision-panel"
              aria-label={isUsLocale ? "Strategic Analysis Panel" : "Painel de Análise Estratégica"}
              data-core-data={hasStrategicCoreData ? "true" : "false"}
              data-missing-fields={backendMissingFields.join(",")}
              data-master-score-value={effectiveAiScore ?? ""}
              data-rsi-value={panelRsiValue ?? ""}
              data-bias-value={strategicDecisionContract.side}
              data-decision-now={operationalDecision.action}
              data-decision-side={strategicDecisionContract.side}
              data-selected-symbol={selectedTicker}
              data-trade-suggested={strategicDecisionContract.tradeSuggested}
            >
              <div className="snbr-decision-head">
                <strong>{isUsLocale ? "Strategic Analysis Panel" : "Painel de Análise Estratégica"}</strong>
                <div className="snbr-decision-mode-actions">
                  <strong className="snbr-decision-mode-label">
                    {advancedMode ? (isUsLocale ? "Pro Mode" : "Modo Pro") : (isUsLocale ? "Basic Mode" : "Modo Básico")}
                  </strong>
                  <button
                    aria-controls="strategic-analysis-panel-body"
                    aria-expanded={advancedMode && strategicPanelOpen}
                    className="snbr-section-head-action snbr-collapse-toggle"
                    onClick={() => {
                      if (advancedMode) {
                        setStrategicPanelOpen((current) => !current);
                      } else if (!proModeLocked) {
                        setAdvancedMode(true);
                        setStrategicPanelOpen(true);
                      }
                    }}
                    type="button"
                  >
                    {advancedMode && strategicPanelOpen ? (isUsLocale ? "Close" : "Fechar") : (isUsLocale ? "Open" : "Abrir")}
                  </button>
                </div>
              </div>
              {advancedMode && strategicPanelOpen ? (
                <div id="strategic-analysis-panel-body" data-canonical-analysis={canonicalAnalysis?.validation_status || "UNAVAILABLE"}>
                  <article className={cx("snbr-operational-decision", operationalDecision.tone)}>
                    <div className="snbr-operational-main">
                      <span className="snbr-operational-kicker">{isUsLocale ? "Decision Now" : "Decisão Agora"}</span>
                      <strong>{operationalDecision.action}</strong>
                      <div className="snbr-operational-confidence">
                        <span>{isUsLocale ? "Confidence" : "Confiança"}</span>
                        <strong>{operationalDecision.confidence != null ? `${operationalDecision.confidence}%` : (isUsLocale ? "Not confirmed" : "Não confirmada")}</strong>
                        <small>{operationalDecision.confidenceLabel}</small>
                      </div>
                    </div>
                    <div className="snbr-operational-reasons">
                      <span>{isUsLocale ? "Reason" : "Motivo"}</span>
                      <ul>
                        {operationalDecision.reasons.map((reason) => (
                          <li key={reason}>{reason}</li>
                        ))}
                      </ul>
                    </div>
                    <div className="snbr-operational-summary" aria-label={isUsLocale ? "Executive summary" : "Resumo executivo"}>
                      <div>
                        <span>{isUsLocale ? "Bias" : "Viés"}</span>
                        <strong>{operationalDecision.bias}</strong>
                      </div>
                      <div>
                        <span>{isUsLocale ? "Risk" : "Risco"}</span>
                        <strong>{operationalDecision.risk}</strong>
                      </div>
                      <div>
                        <span>{isUsLocale ? "Conviction" : "Convicção"}</span>
                        <strong>{symbolOperationalView
                          ? symbolOperationalView.conviction_status === "READY" && firstFiniteNumber(symbolOperationalView.conviction) != null
                            ? `${firstFiniteNumber(symbolOperationalView.conviction)}%`
                            : (isUsLocale ? "Not calculated" : "Não calculada")
                          : operationalDecision.confidence != null
                            ? `${operationalDecision.confidence}%`
                            : (isUsLocale ? "Not calculated" : "Não calculada")}</strong>
                      </div>
                    </div>
                    <div className="snbr-operational-levels">
                      <span>{isUsLocale ? "Operational Levels" : "Níveis Operacionais"}</span>
                      <div>
                        {operationalDecision.levels.map((level) => (
                          <small key={level.label}>
                            <b>{level.label}:</b> {level.value}
                          </small>
                        ))}
                      </div>
                    </div>
                  </article>
                  {shouldRenderStrategicDetails ? (
                    <div className="snbr-decision-grid">
                      {decisionCardsForRender.map((card) => (
                        <article key={`${card.label}-${card.value}`} className={cx("snbr-decision-card", card.tone)}>
                          <span>{card.label}</span>
                          <strong>{card.value}</strong>
                          {card.meta ? <small>{card.meta}</small> : null}
                          {card.meter != null ? (
                            <div className="snbr-decision-meter" aria-hidden="true">
                              <i style={{ width: `${card.meter}%` }} />
                            </div>
                          ) : null}
                        </article>
                      ))}
                    </div>
                  ) : null}
                  {shouldRenderStrategicDetails ? (
                    <article className={cx("snbr-decision-conclusion", strategicDecisionContract.tone, !strategicConclusionExpanded && "collapsed")}>
                    <div className="snbr-conclusion-topline">
                      <span>{isUsLocale ? "Conclusion" : "Conclusão"}</span>
                      <small>{symbolOperationalView?.as_of
                        ? `${isUsLocale ? "Market data through" : "Dados de mercado até"} ${formatNewsClock(symbolOperationalView.as_of, appLocale)}`
                        : (isUsLocale ? `AI Analysis Time ${strategicConclusion.stamp}` : `IA Análise Hora ${strategicConclusion.stamp}`)}</small>
                      <button
                        aria-expanded={strategicConclusionExpanded}
                        className="snbr-collapse-toggle"
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
                              {strategicConclusionSections.map((section) => {
                                const renderedItems = section.items?.filter((item: string) => (
                                  normalizeUiText(item) !== "manter a leitura de compra somente com confirmacao; se falhar, voltar para aguardar."
                                ));
                                return (
                                  <section key={section.title}>
                                    <strong>{section.title}</strong>
                                    {section.body ? <p>{section.body}</p> : null}
                                    {renderedItems?.length ? (
                                      <ul>
                                        {renderedItems.map((item: string) => (
                                          <li key={item}>{item}</li>
                                        ))}
                                      </ul>
                                    ) : null}
                                  </section>
                                );
                              })}
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
                            {strategicConclusionBasis.map((item) => (
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
                  ) : null}
                </div>
              ) : null}
            </section>
          ) : null}
          {renderCenterPanel()}
        </section>
      </main>
    </div>
  );
}
