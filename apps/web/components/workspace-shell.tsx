"use client";

import { startTransition, useDeferredValue, useEffect, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";

import { TickerChart } from "@/components/ticker-chart";
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
  getMediaStatus,
  getPoll,
  getPushStatus,
  getQuote,
  searchAssets,
  getWorkspace,
  likePost,
  loginJson,
  logoutAuth,
  muteUser,
  postChatMessage,
  reportPost,
  requestTelegramLink,
  saveWorkspaceLayout,
  unlikePost,
  updateProfile,
  uploadMedia,
  verifyLoginOtp,
  votePoll,
} from "@/lib/api";
import type {
  AuthFlowResponse,
  ChatHistoryPayload,
  FeedPayload,
  FeedPost,
  PollPayload,
  PublicBootstrap,
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
};

type WatchlistItem = {
  symbol: string;
  label: string;
  category: string;
  price?: number | null;
  changePct?: number | null;
  score?: number | null;
  trend?: string | null;
};

type ToolCopyItem = {
  title: string;
  description: string;
  explanation: string;
};

const TAB_META: Record<string, { label: string; short: string }> = {
  grafico: { label: "📈 IA Grafico", short: "Grafico" },
  news: { label: "📰 Noticias", short: "Noticias" },
  busca: { label: "🔎 Busca", short: "Busca" },
  "heat-map": { label: "🗺 IA Heat Map", short: "Heat Map" },
  radar: { label: "⚡ IA Radar", short: "Radar" },
  "breakout-probability": { label: "🎯 IA Breakout Probability", short: "Breakout" },
  "volatility-squeeze": { label: "🟣 IA Volatility Squeeze", short: "Squeeze" },
  "institutional-flow": { label: "🏦 IA Institutional Flow", short: "Flow" },
  "smart-money": { label: "💼 IA Smart Money", short: "Smart Money" },
  accumulation: { label: "📦 IA Accumulation", short: "Accumulation" },
  "liquidity-sweep": { label: "🧲 IA Liquidity Sweep", short: "Sweep" },
  "liquidity-map": { label: "🧭 IA Liquidity Map", short: "Liquidity Map" },
  "market-regime": { label: "📊 IA Market Regime", short: "Regime" },
  "master-score": { label: "⭐ IA Master Score", short: "Master Score" },
  education: { label: "🎓 Ajuda Educacional para o Trader", short: "Ajuda" },
};

const TOP_TAB_TEXT: Record<string, string> = {
  grafico: "IA Grafico",
  news: "Noticias",
  "heat-map": "IA Heat Map",
  radar: "IA Radar",
  "breakout-probability": "IA Breakout",
  "volatility-squeeze": "IA Squeeze",
  "institutional-flow": "IA Flow",
  "smart-money": "IA Smart Money",
  accumulation: "IA Accumulation",
  "liquidity-sweep": "IA Sweep",
  "liquidity-map": "IA Map",
  "market-regime": "IA Regime",
  "master-score": "Master Score",
  education: "Ajuda",
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
  { id: "grafico", title: "IA Grafico" },
  { id: "news", title: "Noticias" },
  { id: "busca", title: "Busca" },
  { id: "heat-map", title: "IA Heat Map" },
  { id: "radar", title: "IA Radar" },
  { id: "breakout-probability", title: "IA Breakout Probability" },
  { id: "volatility-squeeze", title: "IA Volatility Squeeze" },
  { id: "institutional-flow", title: "IA Institutional Flow" },
  { id: "smart-money", title: "IA Smart Money" },
  { id: "accumulation", title: "IA Accumulation" },
  { id: "liquidity-sweep", title: "IA Liquidity Sweep" },
  { id: "liquidity-map", title: "IA Liquidity Map" },
  { id: "market-regime", title: "IA Market Regime" },
  { id: "master-score", title: "IA Master Score" },
  { id: "education", title: "Ajuda Educacional para o Trader" },
];

const CATEGORY_ORDER = ["B3", "BDR", "Crypto", "USA"] as const;
const B3_SYMBOL_PATTERN = /^[A-Z]{4}(?:3|4|5|6|11)$/;
const BDR_SYMBOL_PATTERN = /^[A-Z]{4,5}34$/;
const USA_SYMBOL_PATTERN = /^[A-Z]{1,5}$/;

const WATCHLIST_B3 = [
  "ITUB4.SA", "BBDC4.SA", "BBAS3.SA", "SANB11.SA", "BPAC11.SA",
  "VALE3.SA", "PETR4.SA", "PETR3.SA", "SUZB3.SA", "KLBN11.SA",
  "ELET3.SA", "ELET6.SA", "CPFE3.SA", "EQTL3.SA", "ENBR3.SA",
  "MGLU3.SA", "LREN3.SA", "AMER3.SA", "VIIA3.SA", "ASAI3.SA",
  "WEGE3.SA", "GGBR4.SA", "CSNA3.SA", "USIM5.SA",
  "TOTS3.SA", "POSI3.SA",
  "RAIL3.SA", "CCRO3.SA", "NTCO3.SA", "BRFS3.SA", "JBSS3.SA",
];

const WATCHLIST_BDR = [
  "AAPL34.SA", "MSFT34.SA", "GOGL34.SA", "AMZO34.SA",
  "NVDC34.SA", "TSLA34.SA", "META34.SA", "NFLX34.SA",
  "INTC34.SA", "AMD34.SA", "QCOM34.SA", "IVVB11.SA",
];

const WATCHLIST_US = [
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
  "MATIC-USD",
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
  "🎯 Breakout Probability → indica rompimento de resistência importante.",
  "🟣 Volatility Squeeze → alerta quando o mercado está “quieto” e pode explodir.",
  "🏦 Institutional Flow → identifica entrada de grandes investidores.",
  "💰 Smart Money → mostra sinais dos grandes players antes de movimentos fortes.",
  "🏛 Accumulation → detecta compras discretas de instituições.",
  "🧲 Liquidity Sweep → mostra rompimentos falsos para buscar liquidez.",
  "🗺 Liquidity Map → indica onde há concentração de stops e liquidez.",
  "📊 Market Regime → classifica o mercado: 📈 alta, 📉 baixa ou ➡ lateral.",
  "⭐ Master Score → pontuação geral da oportunidade (90 = forte, 70 = moderada, <50 = fraca).",
  "📈 Gráfico IA → exibe sinais no gráfico: BUY, SHORT ou ⚠ encerrar posição.",
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
    title: "🎯 IA Breakout Probability",
    body: [
      "Indica quando um ativo está prestes a romper uma resistência.",
      "👉 Exemplo: Um papel ficou entre 10 e 10.20. Se romper 10.20 com volume, pode iniciar uma alta forte. 🚀",
    ],
  },
  {
    title: "🟣 IA Volatility Squeeze",
    body: [
      "Mostra quando o mercado está “quieto demais” e pode explodir em movimento.",
      "👉 Exemplo: Preço andando de lado por dias → depois vem uma expansão forte. 💥",
    ],
  },
  {
    title: "🏦 IA Institutional Flow",
    body: [
      "Detecta entrada de investidores grandes (institucionais).",
      "👉 Exemplo: Um ativo sobe com volume muito acima da média → sinal de possível compra institucional. 🏦",
    ],
  },
  {
    title: "💰 IA Smart Money",
    body: [
      "Mostra sinais de movimentação dos grandes players.",
      "👉 Exemplo: Volume crescente antes de uma alta ou queda forte. 📊",
    ],
  },
  {
    title: "🏛 IA Accumulation",
    body: [
      "Identifica quando grandes investidores estão comprando aos poucos.",
      "👉 Exemplo: Preço estável, mas volume aumentando devagar. 📈",
    ],
  },
  {
    title: "🧲 IA Liquidity Sweep",
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
  AMZO34: "Amazon BDR",
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
    title: "🗺 IA Heat Map",
    description: "Mostra quais ativos estão mais fortes ou mais fracos no mercado.",
    explanation: "🟢 Verde = força compradora. 🔴 Vermelho = pressão vendedora. Exemplo: se PETR4 aparece bem verde, o ativo está ganhando força agora.",
  },
  radar: {
    title: "⚡ IA Radar",
    description: "Detecta ativos que começaram a se movimentar rapidamente no mercado.",
    explanation: "Funciona como um radar para encontrar oportunidades antes da maioria dos traders perceber.",
  },
  "breakout-probability": {
    title: "🎯 IA Breakout Probability",
    description: "Identifica quando um ativo está próximo de romper uma resistência importante.",
    explanation: "Breakout significa que o preço pode iniciar uma tendência forte. Exemplo: se romper uma faixa lateral com volume, a probabilidade sobe.",
  },
  "volatility-squeeze": {
    title: "🟣 IA Volatility Squeeze",
    description: "Detecta momentos em que a volatilidade do mercado está muito comprimida.",
    explanation: "Depois de muita compressão costuma vir expansão forte. A IA busca exatamente esse ponto.",
  },
  "institutional-flow": {
    title: "🏦 IA Institutional Flow",
    description: "Identifica quando investidores institucionais estão entrando no mercado.",
    explanation: "Instituições movem muito volume e muitas vezes iniciam movimentos importantes antes do varejo perceber.",
  },
  "smart-money": {
    title: "💼 IA Smart Money",
    description: "Busca sinais de movimentação de grandes players antes de movimentos importantes no mercado.",
    explanation: "É a leitura do dinheiro inteligente: absorção, deslocamento e volume anormal.",
  },
  accumulation: {
    title: "📦 IA Accumulation",
    description: "Detecta quando um ativo está sendo acumulado lentamente por grandes investidores.",
    explanation: "A acumulação costuma acontecer com preço estável e volume subindo aos poucos, sem chamar tanta atenção do mercado.",
  },
  "liquidity-sweep": {
    title: "🧲 IA Liquidity Sweep",
    description: "Detecta quando o mercado busca liquidez antes de mudar de direção.",
    explanation: "É quando o preço varre stops, busca liquidez e depois reage na direção contrária.",
  },
  "liquidity-map": {
    title: "🧭 IA Liquidity Map",
    description: "Mostra onde existe maior concentração de liquidez no mercado.",
    explanation: "Esses pontos costumam atrair o preço e ajudam o trader a entender onde a reação pode acontecer.",
  },
  "market-regime": {
    title: "📊 IA Market Regime",
    description: "Mostra qual é o tipo de mercado atual.",
    explanation: "A IA identifica se o mercado está em tendência de alta, tendência de baixa ou lateral, para o trader usar a ferramenta certa no cenário certo.",
  },
  "master-score": {
    title: "⭐ IA Master Score",
    description: "É a pontuação geral do sistema.",
    explanation: "Combina diversas análises da IA para classificar oportunidades. Score alto = oportunidade mais forte.",
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

function cx(...values: Array<string | false | null | undefined>) {
  return values.filter(Boolean).join(" ");
}

function titleFromKey(key: string) {
  return key.replace(/_/g, " ").replace(/\b\w/g, (match) => match.toUpperCase());
}

function normalizeSymbol(raw: string) {
  return raw.trim().toUpperCase().replace(/\.SA$/, "").replace(/-USD$/, "USD");
}

function topTabText(tabId: string, fallback: string) {
  return TOP_TAB_TEXT[tabId] || fallback;
}

function guessCategory(symbol: string) {
  if (symbol.endsWith("USD")) return "Crypto";
  if (symbol.endsWith("34") || symbol === "IVVB11") return "BDR";
  if (/\d/.test(symbol)) return "B3";
  return "USA";
}

function symbolName(symbol: string) {
  return COMPANY_HINTS[symbol] || symbol;
}

function initialsFromName(value?: string | null) {
  const source = String(value || "").trim();
  if (!source) return "SN";

  const parts = source.split(/\s+/).filter(Boolean);
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return `${parts[0][0] || ""}${parts[parts.length - 1][0] || ""}`.toUpperCase();
}

function formatRelativeTime(timestamp?: number | null) {
  if (!timestamp) return "agora";

  const diffSeconds = Math.max(0, Math.floor(Date.now() / 1000) - Number(timestamp));
  if (diffSeconds < 60) return "agora";
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

function formatAlertTime(symbol: string, rawTimestamp?: number | null) {
  if (!isB3Symbol(symbol)) return "--:--";
  const date = rawTimestamp ? new Date(rawTimestamp) : new Date();
  if (!isB3MarketOpen(date)) return "--:--";
  const { hour, minute } = getSaoPauloParts(date);
  return `${String(hour).padStart(2, "0")}:${String(minute).padStart(2, "0")}`;
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

function formatPrice(value?: number | null) {
  if (value == null || Number.isNaN(Number(value))) return "n/a";
  return Number(value).toLocaleString("pt-BR", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

function formatSignedPercent(value?: number | null) {
  if (value == null || Number.isNaN(Number(value))) return "n/a";
  const numeric = Number(value);
  return `${numeric > 0 ? "+" : ""}${numeric.toFixed(2)}%`;
}

function formatCompact(value?: number | null) {
  if (value == null || Number.isNaN(Number(value))) return "n/a";
  return Intl.NumberFormat("pt-BR", {
    notation: "compact",
    maximumFractionDigits: 1,
  }).format(Number(value));
}

function scoreClass(score?: number | null) {
  const numeric = Number(score || 0);
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

function getTabMeta(tab: WorkspaceTab) {
  return TAB_META[tab.id] || { label: tab.title, short: tab.title };
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

  const selected = bySymbol.get(selectedTicker);
  if (selected && quote?.price != null) {
    selected.price = quote.price;
    selected.changePct = quote.change_pct ?? null;
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
  } else if (USA_SYMBOL_PATTERN.test(normalized)) {
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
    trend: category === "B3" ? "B3 manual" : "Busca manual",
  } satisfies WatchlistItem;
}

function buildFallbackPoll(symbol: string): PollPayload {
  return {
    symbol,
    question: `${symbol}: qual o cenário mais provável para esta semana?`,
    total_votes: 0,
    options: [
      {
        key: "bullish_week",
        label: "Semana com tendência de alta para este ativo",
        votes: 0,
        pct: 0,
      },
      {
        key: "bearish_week",
        label: "Semana sem tendência aparente ou com viés de baixa",
        votes: 0,
        pct: 0,
      },
    ],
  };
}

export function WorkspaceShell({ focusedTab }: Props) {
  const searchParams = useSearchParams();
  const queryToken = searchParams.get("token") || "";
  const queryTicker = (searchParams.get("ticker") || "PETR4").toUpperCase();

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
  const [feed, setFeed] = useState<FeedPayload | null>(null);
  const [poll, setPoll] = useState<PollPayload | null>(null);
  const [room, setRoom] = useState<ChatHistoryPayload | null>(null);
  const [quote, setQuote] = useState<QuotePayload | null>(null);
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

  const [watchlistQuery, setWatchlistQuery] = useState("");
  const [watchCategory, setWatchCategory] = useState<"Todos" | (typeof CATEGORY_ORDER)[number]>("Todos");
  const [remoteSearchSymbols, setRemoteSearchSymbols] = useState<string[]>([]);
  const [customWatchItems, setCustomWatchItems] = useState<WatchlistItem[]>([]);
  const [activeWatchSymbols, setActiveWatchSymbols] = useState<string[]>(() => PRELOADED_UNIVERSE.map((item) => item.symbol));
  const [tickerTapePaused, setTickerTapePaused] = useState(false);
  const [darkMode, setDarkMode] = useState(false);
  const [showMarkers, setShowMarkers] = useState(true);
  const [showZones, setShowZones] = useState(true);
  const [mobileWatchlistOpen, setMobileWatchlistOpen] = useState(false);
  const [mobileInsightsOpen, setMobileInsightsOpen] = useState(false);

  const [postText, setPostText] = useState("");
  const [postSentiment, setPostSentiment] = useState("bullish");
  const [postFile, setPostFile] = useState<File | null>(null);
  const [posting, setPosting] = useState(false);
  const [composerEmojiOpen, setComposerEmojiOpen] = useState(false);
  const [commentDrafts, setCommentDrafts] = useState<Record<number, string>>({});
  const [commentingPostId, setCommentingPostId] = useState<number | null>(null);
  const [postMenuId, setPostMenuId] = useState<number | null>(null);
  const [silencedUserIds, setSilencedUserIds] = useState<number[]>([]);

  const [chatText, setChatText] = useState("");
  const [chatImageUrl, setChatImageUrl] = useState("");
  const [chatStatus, setChatStatus] = useState("offline");

  const socketRef = useRef<WebSocket | null>(null);
  const composerFileInputRef = useRef<HTMLInputElement | null>(null);
  const profileFileInputRef = useRef<HTMLInputElement | null>(null);
  const tabListRef = useRef<HTMLDivElement | null>(null);
  const composerCardRef = useRef<HTMLDivElement | null>(null);
  const leftRailRef = useRef<HTMLElement | null>(null);

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
    getPoll(deferredTicker).then(setPoll).catch(() => undefined);
  }, [deferredTicker]);

  useEffect(() => {
    if (!token) {
      setLoading(false);
      setAccess(null);
      setWorkspace(null);
      setChart(null);
      setFeed(null);
      setRoom(null);
      setQuote(null);
      setPushStatus(null);
      setMediaStatus(null);
      return;
    }

    let cancelled = false;
    setLoading(true);
    setError("");

    Promise.all([
      getAccess(token),
      getWorkspace(token),
      getChart(token, deferredTicker),
      getFeed(token, deferredTicker),
      getChatHistory(token, deferredTicker),
      getQuote(token, deferredTicker),
      getPushStatus(token),
      getMediaStatus(token),
    ])
      .then(([nextAccess, nextWorkspace, nextChart, nextFeed, nextRoom, nextQuote, nextPush, nextMedia]) => {
        if (cancelled) return;

        startTransition(() => {
          const nextTabs = buildTabs(nextWorkspace.tabs);
          setAccess(nextAccess);
          setWorkspace(nextWorkspace);
          setChart(nextChart);
          setFeed(nextFeed);
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
  }, [token, deferredTicker, focusedTab]);

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

  async function persistLayout(nextTabs: WorkspaceTab[], popouts?: string[], pinnedTicker?: string) {
    if (!token) return;

    try {
      const nextLayout = await saveWorkspaceLayout(token, {
        tabs: nextTabs.map((tab) => tab.id),
        pinned_ticker: pinnedTicker ?? selectedTicker,
        opened_popouts: popouts ?? workspace?.layout?.opened_popouts ?? [],
      });

      startTransition(() => {
        setWorkspace((current) => (current ? { ...current, layout: nextLayout } : current));
      });
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Falha ao salvar layout");
    }
  }

  function openPopout(tabId: string) {
    const nextPopouts = [...new Set([...(workspace?.layout?.opened_popouts || []), tabId])];
    void persistLayout(tabs, nextPopouts);
    const tokenQuery = token ? `?token=${encodeURIComponent(token)}&ticker=${encodeURIComponent(selectedTicker)}` : "";
    const features = DETACHABLE_IA_TABS.has(tabId)
      ? "width=760,height=560,resizable=yes"
      : "width=1440,height=960,resizable=yes";
    const targetName = tabId === "grafico"
      ? `stocknewsbr_panel_${tabId}_${Date.now()}`
      : `stocknewsbr_panel_${tabId}`;
    window.open(`/panel/${tabId}${tokenQuery}`, targetName, features);
  }

  function scrollTabs(direction: "left" | "right") {
    if (!tabListRef.current) return;
    tabListRef.current.scrollBy({
      left: direction === "left" ? -280 : 280,
      behavior: "smooth",
    });
  }

  function selectTicker(nextTicker: string) {
    const normalized = normalizeSymbol(nextTicker);

    startTransition(() => {
      setTickerInput(normalized);
      setSelectedTicker(normalized);
      if (!focusedTab) setActiveTab("grafico");
    });

    void persistLayout(tabs, undefined, normalized);
  }

  function applyTicker() {
    selectTicker(watchlistQuery.trim().toUpperCase() || tickerInput.trim().toUpperCase() || "PETR4");
  }

  function handleAddToActiveList() {
    const symbol = normalizeSymbol(watchlistQuery.trim() || tickerInput.trim() || selectedTicker);
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

  async function handleCreatePost() {
    if (!token || !postText.trim()) return;

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
    if (!token) return;

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
    if (!token) return;

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

  async function handleBlockTrader(targetId: number) {
    if (!token) return;

    try {
      await blockUser(token, targetId);
      setPostMenuId(null);
      await refreshFeedState();
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Falha ao bloquear trader");
    }
  }

  async function handleMuteTrader(targetId: number) {
    if (!token) return;

    try {
      await muteUser(token, targetId);
      setPostMenuId(null);
      setSilencedUserIds((current) => (current.includes(targetId) ? current : [...current, targetId]));
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Falha ao silenciar trader");
    }
  }

  async function handleReport(postId: number) {
    if (!token) return;

    try {
      await reportPost(token, postId, "community_review");
      setPostMenuId(null);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Falha ao denunciar");
    }
  }

  async function handleReportAndBlock(postId: number, targetId: number) {
    if (!token) return;

    try {
      await reportPost(token, postId, "report_and_block");
      await blockUser(token, targetId);
      setPostMenuId(null);
      await refreshFeedState();
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Falha ao reportar e bloquear");
    }
  }

  async function handleDeleteOwnPost(postId: number) {
    if (!token) return;

    try {
      await deletePost(token, postId);
      setPostMenuId(null);
      await refreshFeedState();
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Falha ao excluir post");
    }
  }

  function handleSilenceTrader(targetId: number) {
    setPostMenuId(null);
    setSilencedUserIds((current) => (current.includes(targetId) ? current : [...current, targetId]));
  }

  function handleRepost(post: FeedPost) {
    if (!token) {
      setError("Faça login para repostar este trade.");
      return;
    }

    setPostSentiment(post.sentiment || "neutral");
    setPostText(`Repost de @${post.user} em $${post.ticker || selectedTicker}: ${post.text}`);
    setPostMenuId(null);
    composerCardRef.current?.scrollIntoView({ behavior: "smooth", block: "center" });
  }

  function appendComposerEmoji(emoji: string) {
    setPostText((current) => `${current}${current ? " " : ""}${emoji}`);
    setComposerEmojiOpen(false);
  }

  async function handleSendChat() {
    if (!token || !chatText.trim()) return;

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
    if (!token) return;

    try {
      const nextPoll = await votePoll(token, selectedTicker, option);
      startTransition(() => {
        setPoll(nextPoll);
      });
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Falha ao votar");
    }
  }

  const currentTab = focusedTab || activeTab;
  const currentTabs = tabs.length ? tabs : buildTabs();
  const tabsById = new Map(currentTabs.map((tab) => [tab.id, tab] as const));
  const visibleTabs = TOP_BAR_TAB_IDS.map((id) => tabsById.get(id)).filter(Boolean) as WorkspaceTab[];
  const currentTabMeta = getTabMeta(tabsById.get(currentTab) || FALLBACK_TABS[0]);
  const roomItems = room?.items || [];
  const feedPosts = feed?.posts || [];
  const discussionPostsRaw = feedPosts.length ? feedPosts : workspace?.featured_posts || [];
  const discussionPosts = discussionPostsRaw.filter((post) => !silencedUserIds.includes(post.user_id));
  const rankingRows = workspace?.ranking || [];
  const radarRows = workspace?.top_signals || [];
  const watchUniverse = buildWatchlist(rankingRows, radarRows, quote, selectedTicker, customWatchItems);
  const activeWatchlist = watchUniverse.filter((item) => activeWatchSymbols.includes(item.symbol));
  const filteredActiveWatchlist = activeWatchlist.filter((item) => watchCategory === "Todos" || item.category === watchCategory);
  const filteredUniverse = watchUniverse.filter((item) => {
    if (!watchlistQuery.trim()) return true;
    const haystack = `${item.symbol} ${item.label} ${item.category}`.toLowerCase();
    return haystack.includes(watchlistQuery.trim().toLowerCase());
  });
  const syntheticSearchCandidate = buildSyntheticSearchCandidate(
    watchlistQuery,
    watchUniverse.map((item) => item.symbol),
  );
  const remoteSearchItems = remoteSearchSymbols.map((symbol) => {
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
  });
  const groupedActiveWatchlist = CATEGORY_ORDER.map((category) => ({
    category,
    items: filteredActiveWatchlist.filter((item) => item.category === category),
  })).filter((group) => group.items.length);
  const searchResults = [...(syntheticSearchCandidate ? [syntheticSearchCandidate] : []), ...remoteSearchItems, ...filteredUniverse]
    .filter((item, index, items) => index === items.findIndex((candidate) => candidate.symbol === item.symbol))
    .slice(0, 24);
  const currentRanking = rankingRows.find((item) => item.symbol === selectedTicker);
  const currentWatchItem = watchUniverse.find((item) => item.symbol === selectedTicker);
  const symbolLabel = currentWatchItem?.label || symbolName(selectedTicker);
  const newsRows = (radarRows.length ? radarRows : rankingRows).slice(0, 6).map((row, index) => {
    const symbol = String((row as any).symbol || (row as any).ticker || selectedTicker);
    const score = (row as any).score != null ? Number((row as any).score).toFixed(1) : "n/a";
    const trend = (row as any).trend || "monitorando";
    return {
      id: `${symbol}-${index}`,
      symbol,
      title: `${symbol} entra no radar com vies ${trend}`,
      source: "Radar IA",
      age: index === 0 ? "agora" : `${index + 1}h`,
      score,
    };
  });
  const stats = [
    { label: "Preco", value: formatPrice(quote?.price) },
    { label: "Variacao", value: formatSignedPercent(quote?.change_pct) },
    { label: "Volume", value: formatCompact(quote?.volume) },
    { label: "Score IA", value: currentRanking?.score != null ? Number(currentRanking.score).toFixed(1) : "n/a" },
    { label: "RSI", value: currentRanking?.rsi != null ? String(currentRanking.rsi) : "n/a" },
    { label: "Bias", value: chart?.summary?.trend_bias || currentRanking?.trend || "n/a" },
  ];
  const tapeItems = FIXED_TAPE_SYMBOLS.map((symbol) => watchUniverse.find((item) => item.symbol === symbol) || {
    symbol,
    label: symbolName(symbol),
    category: guessCategory(symbol),
  });
  const toolCandidatesSource = (radarRows.length ? radarRows : rankingRows).length
    ? (radarRows.length ? radarRows : rankingRows)
    : watchUniverse.slice(0, 20).map((item) => ({
        symbol: item.symbol,
        trend: item.trend || "monitorando",
        score: item.score ?? null,
        price: item.price ?? null,
        rsi: null,
      }));
  const toolCandidates = toolCandidatesSource.slice(0, 20).map((row, index) => {
    const symbol = normalizeSymbol(String((row as any).symbol || (row as any).ticker || selectedTicker));
    return {
      id: `${symbol}-${index}`,
      symbol,
      label: symbolName(symbol),
      score: (row as any).score != null ? Number((row as any).score) : null,
      trend: (row as any).trend || "monitorando",
      price: (row as any).price != null ? Number((row as any).price) : null,
      rsi: (row as any).rsi != null ? Number((row as any).rsi) : null,
      volume: (row as any).volume != null ? Number((row as any).volume) : null,
      timestamp: Number((row as any).timestamp || (row as any).updated_at || Date.now()),
    };
  });
  const expandedToolCandidates = Array.from({ length: 20 }, (_, index) => {
    const fallback = toolCandidates[index % Math.max(toolCandidates.length, 1)] || {
      id: `${selectedTicker}-${index}`,
      symbol: selectedTicker,
      label: symbolLabel,
      score: currentRanking?.score != null ? Number(currentRanking.score) : null,
      trend: currentRanking?.trend || chart?.summary?.trend_bias || "monitorando",
      price: quote?.price ?? null,
      rsi: currentRanking?.rsi != null ? Number(currentRanking.rsi) : null,
      volume: quote?.volume ?? null,
      timestamp: Date.now(),
    };
    return { ...fallback, id: `${fallback.symbol}-${index}` };
  });
  const showSymbolHeader = ["grafico", "news", "education"].includes(currentTab);
  const guestCta = !token;
  const activePoll = poll?.options?.length ? poll : buildFallbackPoll(selectedTicker);
  const hasRenderedChartData = Boolean(chart?.ohlc?.length || chart?.series?.length);
  const hasSignalSnapshot =
    hasRenderedChartData &&
    currentRanking?.score != null &&
    !Number.isNaN(Number(currentRanking.score));
  const trendText = hasSignalSnapshot ? String(currentRanking?.trend || chart?.summary?.trend_bias || "") : "";
  const numericRankingScore =
    hasSignalSnapshot && currentRanking?.score != null && !Number.isNaN(Number(currentRanking.score))
      ? clampNumber(Number(currentRanking.score), 0, 100)
      : null;
  const sentimentTone =
    !hasSignalSnapshot
      ? "neutral"
      : trendText.toLowerCase().includes("bear") || trendText.toLowerCase().includes("baixa")
        ? "bearish"
        : trendText.toLowerCase().includes("bull") || trendText.toLowerCase().includes("alta")
          ? "bullish"
          : numericRankingScore != null && numericRankingScore >= 50
            ? "bullish"
            : numericRankingScore != null && numericRankingScore < 50
              ? "bearish"
              : "neutral";
  const sentimentLabel =
    !hasSignalSnapshot
      ? "Sem leitura"
      : sentimentTone === "bearish"
        ? "Urso"
        : sentimentTone === "bullish"
          ? "Touro"
          : "Neutro";
  const sentimentScore = hasSignalSnapshot ? numericRankingScore : null;
  const volumeActivity = (discussionPosts.length * 8) + (roomItems.length * 5);
  const volumeScore = volumeActivity > 0 ? clampNumber(volumeActivity, 0, 100) : null;
  const volumeLabel =
    volumeScore == null
      ? "Sem leitura"
      : volumeScore >= 65
        ? "Alto"
        : volumeScore >= 35
          ? "Normal"
          : "Baixo";
  const priceMovementValue = quote?.change ?? null;
  const priceMovementPercent = quote?.change_pct ?? null;
  const priceDirectionClass = movementClass(priceMovementPercent, currentRanking?.trend, currentRanking?.score);
  const priceMovementLabel = priceDirectionClass === "up" ? "Pre-mercado" : priceDirectionClass === "down" ? "Apos o fechamento" : "Mercado";
  const hasPriceMovement = priceMovementValue != null || priceMovementPercent != null;

  useEffect(() => {
    if (currentTab !== "education" || !educationAnchor) return;

    const timeout = window.setTimeout(() => {
      document.getElementById(educationAnchor)?.scrollIntoView({ behavior: "smooth", block: "start" });
      setEducationAnchor(null);
    }, 120);

    return () => window.clearTimeout(timeout);
  }, [currentTab, educationAnchor]);

  function openInstitutionalSection(sectionId: string) {
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
              <span>{group.items.length} ativos</span>
            </header>
            <div className="snbr-watch-group-list">
              {group.items.map((item) => (
                <div key={item.symbol} className={cx("snbr-watch-row", item.symbol === selectedTicker && "active")}>
                  <button className="snbr-watch-open" onClick={() => selectTicker(item.symbol)} type="button">
                    <div className="snbr-watch-main">
                      <strong>{item.symbol}</strong>
                      <span>{item.label}</span>
                    </div>
                    <div className="snbr-watch-side">
                      <span>{formatPrice(item.price)}</span>
                      <span className={cx("snbr-watch-change", movementClass(item.changePct, item.trend, item.score))}>
                        {movementArrow(movementClass(item.changePct, item.trend, item.score))}{" "}
                        {item.changePct != null ? formatSignedPercent(item.changePct) : item.score != null ? `${Number(item.score).toFixed(0)} pts` : item.trend || "Radar"}
                      </span>
                    </div>
                  </button>
                  <button className="snbr-watch-remove" onClick={() => handleRemoveFromActiveList(item.symbol)} type="button">
                    Excluir
                  </button>
                </div>
              ))}
            </div>
          </section>
        )) : (
          <div className="snbr-empty-thread">
            <strong>Nenhum ativo na sua lista.</strong>
            <p>Use a busca acima e o botao Adicionar para montar sua lista ativa.</p>
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
                <path className="snbr-meter-arc bullish" d="M 24 82 A 56 56 0 0 1 80 26" />
                <path className="snbr-meter-arc bearish" d="M 80 26 A 56 56 0 0 1 136 82" />
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
                <strong>Compartilhe sua ideia em ${selectedTicker}</strong>
                <p>Login libera post, voto, curtidas, foto, comentarios e integracao total com a comunidade.</p>
              </div>
            </div>
            <button aria-label="Mais opcoes do post" className="snbr-toolbar-icon" type="button">
              ⋯
            </button>
          </div>
          <div className="snbr-composer-sentiment">
            <button className="snbr-sentiment-pill bullish" type="button">
              <span className="snbr-sentiment-glyph bullish">🐂</span>
              <span>Touro</span>
            </button>
            <button className="snbr-sentiment-pill bearish" type="button">
              <span className="snbr-sentiment-glyph bearish">🐻</span>
              <span>Urso</span>
            </button>
          </div>
          <textarea
            className="snbr-textarea"
            disabled
            placeholder={`Compartilhe sua ideia em $${selectedTicker}`}
          />
          <div className="snbr-composer-toolbar">
            <button className="snbr-toolbar-icon" disabled type="button">🎯</button>
            <button className="snbr-toolbar-icon" disabled type="button">🖼️</button>
            <button className="snbr-toolbar-icon" disabled type="button">GIF</button>
            <button className="snbr-toolbar-icon" disabled type="button">😊</button>
            <button className="snbr-button primary" disabled type="button">Post</button>
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
          <button aria-label="Mais opcoes do post" className="snbr-toolbar-icon" type="button">
            ⋯
          </button>
        </div>

        <textarea
          className="snbr-textarea snbr-composer-textarea"
          value={postText}
          onChange={(event) => setPostText(event.target.value)}
          placeholder={`Compartilhe sua ideia em $${selectedTicker}`}
        />

        <div className="snbr-composer-footer">
          <div className="snbr-composer-left">
            <div className="snbr-composer-sentiment">
              <button
                className={cx("snbr-sentiment-pill", "bullish", postSentiment === "bullish" && "active")}
                onClick={() => setPostSentiment("bullish")}
                type="button"
              >
                <span className="snbr-sentiment-glyph bullish">🐂</span>
                <span>Touro</span>
              </button>
              <button
                className={cx("snbr-sentiment-pill", "bearish", postSentiment === "bearish" && "active")}
                onClick={() => setPostSentiment("bearish")}
                type="button"
              >
                <span className="snbr-sentiment-glyph bearish">🐻</span>
                <span>Urso</span>
              </button>
            </div>

            <div className="snbr-composer-toolbar">
              <button className="snbr-toolbar-icon" title="Mover foco para o ticker" type="button">🎯</button>
              <button
                className="snbr-toolbar-icon"
                onClick={() => composerFileInputRef.current?.click()}
                title="Adicionar foto"
                type="button"
              >
                🖼️
              </button>
              <button
                className="snbr-toolbar-icon"
                onClick={() => setPostText((current) => `${current}${current ? " " : ""}[GIF]`)}
                title="Adicionar GIF"
                type="button"
              >
                GIF
              </button>
              <button
                className={cx("snbr-toolbar-icon", composerEmojiOpen && "active")}
                onClick={() => setComposerEmojiOpen((value) => !value)}
                title="Adicionar emoji"
                type="button"
              >
                😊
              </button>
              {postFile ? <span className="snbr-file-pill">{postFile.name}</span> : null}
            </div>

            {composerEmojiOpen ? (
              <div className="snbr-emoji-picker">
                {COMPOSER_EMOJIS.map((emoji) => (
                  <button key={emoji} className="snbr-emoji-option" onClick={() => appendComposerEmoji(emoji)} type="button">
                    {emoji}
                  </button>
                ))}
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
            {posting ? "Postando..." : "Post"}
          </button>
        </div>
      </div>
    );
  }

  function renderDiscussionList(posts: FeedPost[], emptyText: string) {
    if (!posts.length) {
      return (
        <div className="snbr-empty-thread">
          <strong>{emptyText}</strong>
          <p>Abra a conversa com sua tese, poste um print do grafico ou comente a leitura do mercado para {selectedTicker}.</p>
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
                  <span>{post.user_email || post.ticker || selectedTicker} • {formatRelativeTime(post.timestamp)}</span>
                </div>
              </div>
              <div className="snbr-post-head-actions">
                <span className={cx("snbr-tone-tag", post.sentiment || "neutral")}>
                  {post.sentiment === "bearish" ? "🐻 Urso" : post.sentiment === "bullish" ? "🐂 Touro" : "😐 Neutro"}
                </span>
                <div className="snbr-post-menu-wrap">
                  <button className="snbr-toolbar-icon" onClick={() => setPostMenuId((current) => current === post.id ? null : post.id)} type="button">
                    ⋯
                  </button>
                  {postMenuId === post.id ? (
                    <div className="snbr-post-menu">
                      <button onClick={() => void handleMuteTrader(post.user_id)} type="button">Silenciar</button>
                      <button onClick={() => void handleReport(post.id)} type="button">Reportar para StockNewsBR</button>
                      <button onClick={() => void handleBlockTrader(post.user_id)} type="button">Bloquear trader</button>
                      <button onClick={() => void handleReportAndBlock(post.id, post.user_id)} type="button">Reportar e bloquear</button>
                      {access?.id === post.user_id ? (
                        <button onClick={() => void handleDeleteOwnPost(post.id)} type="button">Excluir meu post</button>
                      ) : null}
                    </div>
                  ) : null}
                </div>
              </div>
            </div>
            <div className="snbr-post-symbol-row">
              <strong>${post.ticker || selectedTicker}</strong>
              <span className={cx("snbr-tone-tag", post.sentiment || "neutral")}>
                {post.sentiment === "bearish" ? "🐻 Urso" : post.sentiment === "bullish" ? "🐂 Touro" : "😐 Neutro"}
              </span>
            </div>
            <p>{post.text}</p>
            {post.image_url ? <img className="snbr-image" src={post.image_url} alt="midia do post" /> : null}
            <div className="snbr-post-actions snbr-post-actions-bar">
              <button
                className="snbr-post-action snbr-feed-action"
                onClick={() => document.getElementById(`comment-input-${post.id}`)?.focus()}
                type="button"
              >
                💬 <span>{post.comments?.length || 0}</span>
              </button>
              <button
                className="snbr-post-action snbr-feed-action"
                onClick={() => handleRepost(post)}
                type="button"
              >
                🔁
              </button>
              <button
                className={cx("snbr-post-action", "snbr-feed-action", (post.liked_by_me || (post.likes || 0) > 0) && "liked")}
                onClick={() => void handleToggleLike(post)}
                type="button"
              >
                <span>{(post.liked_by_me || (post.likes || 0) > 0) ? "♥" : "♡"}</span>
                {(post.likes || 0) > 0 ? <span>{post.likes || 0}</span> : null}
              </button>
            </div>

              <div className="snbr-post-comments">
                {(post.comments || []).map((comment) => (
                  <article key={comment.id} className="snbr-comment-card">
                    <div className="snbr-post-user">
                      {renderAvatar(comment.user, comment.user_email, comment.user_avatar_url)}
                      <div>
                        <strong>{comment.user}</strong>
                        <span>{comment.user_email || "comentario"} • {formatRelativeTime(comment.timestamp)}</span>
                      </div>
                    </div>
                  <p>{comment.text}</p>
                  {comment.image_url ? <img className="snbr-image" src={comment.image_url} alt="imagem do comentario" /> : null}
                </article>
              ))}

              {token ? (
                <div className="snbr-comment-compose">
                  <input
                    id={`comment-input-${post.id}`}
                    className="snbr-input"
                    value={commentDrafts[post.id] || ""}
                    onChange={(event) => setCommentDrafts((current) => ({ ...current, [post.id]: event.target.value }))}
                    placeholder={`Responder ao post de ${post.user}`}
                  />
                  <button
                    className="snbr-button secondary"
                    disabled={commentingPostId === post.id}
                    onClick={() => void handleComment(post.id)}
                    type="button"
                  >
                    {commentingPostId === post.id ? "Enviando..." : "Comentar"}
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
      <section className="snbr-plain-panel">
        <div className="snbr-section-head">
          <div>
            <h3>Busca</h3>
            <p>Encontre ativos da B3 pra sua lista ativa. Adicione ou exclua.</p>
          </div>
        </div>
        <div className="snbr-search-results">
          {searchResults.length ? searchResults.map((item) => (
            <button key={item.symbol} className="snbr-search-result" onClick={() => selectTicker(item.symbol)} type="button">
              <div>
                <strong>{item.symbol}</strong>
                <span>{item.label}</span>
              </div>
              <div className="snbr-watch-side">
                <span>{formatPrice(item.price)}</span>
                <span className={cx("snbr-watch-change", movementClass(item.changePct, item.trend, item.score))}>
                  {movementArrow(movementClass(item.changePct, item.trend, item.score))}{" "}
                  {item.changePct != null ? formatSignedPercent(item.changePct) : item.score != null ? `${Number(item.score).toFixed(0)} pts` : item.trend || "Radar"}
                </span>
              </div>
            </button>
          )) : (
            <div className="snbr-empty-thread">
              <strong>Nenhum ticker encontrado.</strong>
              <p>Digite simbolo ou nome na busca da esquerda para abrir resultados aqui.</p>
            </div>
          )}
        </div>
      </section>
    );
  }

  function renderToolTab(title: string, description: string) {
    const copy = TOOL_COPY[currentTab] || { title, description, explanation: "" };

    return (
      <section className="snbr-tool-shell">
        <div className="snbr-tool-head">
          <div>
            <h3>{copy.title}</h3>
            <p>{copy.description}</p>
            {copy.explanation ? <p>{copy.explanation}</p> : null}
          </div>
          <button className="snbr-button secondary" onClick={() => openPopout(currentTab)} type="button">
            Liberar Tela
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
                <section className="snbr-plain-panel">
                  <div className="snbr-section-head compact">
                    <div>
                      <h3>Painel do ativo</h3>
                      <p>Leitura instantanea do simbolo usando score, regime e estrutura do grafico.</p>
                    </div>
                    <span className="snbr-chip">Hora: {formatAlertTime(item.symbol, item.timestamp)}</span>
                  </div>
                  <button className="snbr-asset-box snbr-asset-box-large" onClick={() => selectTicker(item.symbol)} type="button">
                    <div className="snbr-asset-box-head">
                      <strong>{item.symbol}</strong>
                      <span className={cx("snbr-side-badge", scoreClass(item.score))}>
                        {item.score != null ? item.score.toFixed(0) : "n/a"}
                      </span>
                    </div>
                    <span>{item.label}</span>
                    <div className="snbr-asset-box-stats">
                      <div>
                        <small>Preco</small>
                        <strong>{formatPrice(item.price)}</strong>
                      </div>
                      <div>
                        <small>Variacao</small>
                        <strong>{watchItem?.changePct != null ? formatSignedPercent(watchItem.changePct) : "n/a"}</strong>
                      </div>
                      <div>
                        <small>Volume</small>
                        <strong>{item.volume != null ? formatCompact(item.volume) : "n/a"}</strong>
                      </div>
                      <div>
                        <small>Score IA</small>
                        <strong>{item.score != null ? item.score.toFixed(1) : "n/a"}</strong>
                      </div>
                      <div>
                        <small>RSI</small>
                        <strong>{item.rsi != null ? item.rsi.toFixed(0) : "n/a"}</strong>
                      </div>
                      <div>
                        <small>Bias</small>
                        <strong>{item.trend || "n/a"}</strong>
                      </div>
                    </div>
                  </button>
                </section>

                <section className="snbr-plain-panel">
                  <div className="snbr-section-head compact">
                    <div>
                      <h3>Leituras da IA</h3>
                      <p>Top sinais e ativos relacionados ao contexto atual do mercado.</p>
                    </div>
                  </div>
                  <div className="snbr-tool-reading-grid">
                    <div className="snbr-tool-reading-card">
                      <span>Leitura principal</span>
                      <strong>{item.symbol} em {item.trend || "monitorando"}</strong>
                    </div>
                    <div className="snbr-tool-reading-card">
                      <span>Score atual</span>
                      <strong>{item.score != null ? item.score.toFixed(1) : "n/a"}</strong>
                    </div>
                    <div className="snbr-tool-reading-card">
                      <span>Liquidez / volume</span>
                      <strong>{item.volume != null ? formatCompact(item.volume) : "n/a"}</strong>
                    </div>
                    <div className="snbr-tool-reading-card">
                      <span>Contexto</span>
                      <strong className={cx("snbr-tone-tag", tone)}>{tone === "bullish" ? "🐂 Touro" : tone === "bearish" ? "🐻 Urso" : "Monitorando"}</strong>
                    </div>
                  </div>
                </section>
              </div>
            );
          })}
        </div>
      </section>
    );
  }

  function renderGrafico() {
    return (
      <div className="snbr-center-stack">
        <section className="snbr-chart-card">
          <div className="snbr-chart-topline">
            <div>
              <h2>Grafico do ativo</h2>
              <p>VWAP, compra/venda, liquidez e leitura estrutural de {selectedTicker} na mesma tela.</p>
            </div>
            <div className="snbr-chart-actions">
              <label className="snbr-toggle">
                <input checked={showMarkers} onChange={() => setShowMarkers((value) => !value)} type="checkbox" />
                <span>Compra/Venda Ferramenta</span>
              </label>
              <label className="snbr-toggle">
                <input checked={showZones} onChange={() => setShowZones((value) => !value)} type="checkbox" />
                <span>Zonas de Liquidez</span>
              </label>
              <button className="snbr-button secondary" onClick={() => openPopout("grafico")} type="button">
                Liberar Tela
              </button>
            </div>
          </div>

          <TickerChart chart={chart} showMarkers={showMarkers} />

          <div className="snbr-timeframes">
            {TIMEFRAME_OPTIONS.map((timeframe, index) => (
              <button key={timeframe} className={cx("snbr-timeframe", index === 0 && "active")} type="button">
                {timeframe}
              </button>
            ))}
          </div>

          <div className="snbr-mini-metrics">
            {renderMeterCard(
              "Sentimento",
              sentimentLabel,
              sentimentScore,
              sentimentLabel === "Urso" ? "bearish" : sentimentLabel === "Touro" ? "bullish" : "neutral",
            )}
            {renderMeterCard(
              "Volume de mensagens",
              volumeLabel,
              volumeScore,
              volumeLabel === "Alto" ? "bullish" : volumeLabel === "Baixo" ? "bearish" : "neutral",
            )}
          </div>

          {showZones && chart?.zones?.length ? (
            <div className="snbr-zone-row">
              {chart.zones.map((zone: any) => (
                <span key={`${zone.label}-${zone.price}`} className="snbr-chip">
                  {zone.label}: {zone.price}
                </span>
              ))}
            </div>
          ) : null}
        </section>

        <section className="snbr-poll-inline">
          <div className="snbr-plain-panel snbr-poll-shell">
            <div className="snbr-section-head">
              <div>
                <h3>✦ Poll</h3>
                <p>Abaixo do monitor de sentimento, a comunidade vota na tese da semana do ativo.</p>
              </div>
            </div>
            <div className="snbr-poll-card">
              <h4>{activePoll.question || `Poll ativa para ${selectedTicker}`}</h4>
              <div className="snbr-poll-options">
                {(activePoll.options || []).map((option) => {
                  const calculatedPct = activePoll.total_votes ? Math.round((option.votes / activePoll.total_votes) * 100) : 0;
                  const optionPct = activePoll.total_votes ? (option.pct != null ? option.pct : calculatedPct) : 0;

                  return (
                    <div key={option.key} className="snbr-poll-option snbr-poll-option-results">
                      {activePoll.total_votes ? <div className="snbr-poll-progress" style={{ width: `${optionPct}%` }} /> : null}
                      <div className="snbr-poll-copy">
                        <strong>{option.label}</strong>
                        <span>{option.votes} votos</span>
                      </div>
                      <div className="snbr-poll-actions">
                        <span className="snbr-poll-pct">{activePoll.total_votes ? `${optionPct}%` : "--"}</span>
                        <button className="snbr-button secondary snbr-poll-vote" onClick={() => handleVote(option.key)} type="button">
                          Votar
                        </button>
                      </div>
                    </div>
                  );
                })}
              </div>
              <div className="snbr-poll-footer">
                <span>{activePoll.total_votes || 0} votos</span>
                <div className="snbr-poll-comment-cta">
                  <span>Comentar:</span>
                  <button className="snbr-post-action" type="button">
                  <span>💬</span>
                  <span>{discussionPosts.length} comentarios</span>
                  </button>
                </div>
              </div>
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
      <section className="snbr-two-column">
        <div className="snbr-plain-panel">
          <div className="snbr-section-head">
            <div>
              <h3>Noticias de {selectedTicker}</h3>
              <p>Faixa editorial do simbolo, pronta para plugar noticias reais e, hoje, alimentada pelo radar da IA.</p>
            </div>
          </div>
          <div className="snbr-headline-list">
            {newsRows.map((item) => (
              <article key={item.id} className="snbr-headline-row">
                <div>
                  <strong>{item.title}</strong>
                  <p>{item.source} • {item.age} • score {item.score}</p>
                </div>
                <span className="snbr-headline-symbol">{item.symbol}</span>
              </article>
            ))}
          </div>
        </div>

        <div className="snbr-plain-panel">
          <div className="snbr-section-head">
            <div>
              <h3>Top discussions</h3>
              <p>As conversas mais ativas do ticker e os posts que mais puxam o sentimento da tela.</p>
            </div>
          </div>
          {renderDiscussionList(discussionPosts.slice(0, 4), "Sem discussoes em destaque ainda.")}
        </div>
      </section>
    );
  }

  function renderEducation() {
    return (
      <section className="snbr-plain-panel">
        <div className="snbr-section-head">
          <div>
            <h3>Ajuda Educacional para o Trader</h3>
            <p>Explicacao clara de cada modulo da plataforma, com foco no uso real no dia a dia do trader.</p>
          </div>
        </div>
        <div className="snbr-help-stack">
          <div className="snbr-help-manual">
            <img
              className="snbr-help-manual-image"
              src="/manual-rapido-stocknewsbr.svg"
              alt="Manual rapido StockNewsBR"
            />
          </div>

          <article className="snbr-guide-card">
            <h4>📋 Manual Rápido StockNewsBR</h4>
            <ul className="snbr-bullet-list">
              {HELP_MANUAL_ITEMS.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          </article>

          {INSTITUTIONAL_SECTIONS.map((section) => (
            <article id={section.id} key={section.id} className="snbr-guide-card snbr-help-section">
              <h4>{section.title}</h4>
              <div className="snbr-help-body">
                {section.body.map((line) => (
                  <p key={line}>{line}</p>
                ))}
              </div>
            </article>
          ))}

          {EDUCATIONAL_HELP_SECTIONS.map((section) => (
            <article key={section.title} className="snbr-guide-card snbr-help-section">
              <h4>{section.title}</h4>
              <div className="snbr-help-body">
                {section.body.map((line) => (
                  <p key={line}>{line}</p>
                ))}
              </div>
            </article>
          ))}

          {(workspace?.help_center.guides || []).map((guide) => (
            <article key={guide.slug} className="snbr-guide-card snbr-help-section">
              <h4>{guide.title}</h4>
              <div className="snbr-help-body">
                <p>{guide.tagline || guide.description}</p>
              </div>
              <div className="snbr-guide-meta">
                <span>Video: {guide.video_status || "preview"}</span>
                <span>{guide.mp4_url ? "MP4 pronto" : "Roteiro pronto"}</span>
              </div>
              {guide.demo_video_url ? (
                <a className="snbr-button secondary" href={guide.demo_video_url} rel="noreferrer" target="_blank">
                  Abrir demo
                </a>
              ) : null}
            </article>
          ))}
        </div>
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
    if (currentTab === "education") return renderEducation();
    return renderGrafico();
  }

  function renderAuthCard() {
    if (token) {
      const profileName = access?.display_name || access?.email || "Trader";

      return (
        <div className="snbr-side-card">
          <div className="snbr-profile-card">
            {renderAvatar(profileName, access?.email, access?.avatar_url)}
            <div className="snbr-profile-card-copy">
              <strong>Profile ▾</strong>
              <span>Seu nome, foto e email aparecem nos posts do ticker.</span>
            </div>
          </div>
          <div className="snbr-profile-editor">
            <label className="snbr-profile-field">
              <span>Nome</span>
              <input
                className="snbr-input"
                value={profileNameInput}
                onChange={(event) => setProfileNameInput(event.target.value)}
                placeholder="Seu nome no feed"
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
                Upload da foto
              </button>
              <span>{profileFile ? profileFile.name : (profileAvatarUrl ? "Foto carregada" : "Sem foto")}</span>
            </div>
            <input
              ref={profileFileInputRef}
              className="snbr-hidden-file-input"
              type="file"
              accept="image/png,image/jpeg,image/webp"
              onChange={(event) => setProfileFile(event.target.files?.[0] || null)}
            />
            <div className="snbr-profile-meta">
              <div className="snbr-account-line"><span>Plano</span><strong>{access?.plan || "guest"}</strong></div>
              <div className="snbr-account-line"><span>Status</span><strong>{access?.plan_status || "n/a"}</strong></div>
              <div className="snbr-account-line"><span>Telegram</span><strong>{access?.telegram_linked ? `@${access?.telegram_username || "vinculado"}` : (access?.access?.telegram ? "pronto para vincular" : "bloqueado no plano atual")}</strong></div>
            </div>
            <button className="snbr-button primary" disabled={profileSaving} onClick={() => void handleSaveProfile()} type="button">
              {profileSaving ? "Salvando..." : "Salvar perfil"}
            </button>
          </div>
          {access?.access?.telegram ? (
            <button className="snbr-button secondary" onClick={handleTelegramLinkRequest} type="button">
              Gerar link seguro do Telegram
            </button>
          ) : null}
          {telegramLink ? (
            <div className="snbr-empty">
              <strong>Codigo:</strong> {telegramLink.link_code}
              <br />
              {telegramLink.deep_link ? (
                <a href={telegramLink.deep_link} rel="noreferrer" target="_blank">Abrir bot e vincular</a>
              ) : (
                <span>Abra o bot oficial e envie este codigo no comando /start.</span>
              )}
            </div>
          ) : null}
          <button className="snbr-button secondary" onClick={() => void handleLogout()} type="button">Sair</button>
        </div>
      );
    }

    if (pendingLoginToken) {
      return (
        <div className="snbr-side-card">
          <div className="snbr-section-head compact">
            <div>
              <h3>Codigo por email</h3>
              <p>Conta Premium pede verificacao a cada novo login.</p>
            </div>
          </div>
          <div className="snbr-auth">
            <input
              className="snbr-input"
              value={otpCode}
              onChange={(event) => setOtpCode(event.target.value)}
              placeholder="Codigo de 6 digitos"
            />
            <button className="snbr-button primary" onClick={handleVerifyOtp} type="button">Validar codigo</button>
            <button
              className="snbr-button secondary"
              onClick={() => {
                setPendingLoginToken("");
                setOtpCode("");
                setDebugOtpCode("");
              }}
              type="button"
            >
              Voltar
            </button>
            {debugOtpCode ? <div className="snbr-empty">Codigo local: {debugOtpCode}</div> : null}
            {loginError ? <div className="snbr-empty">{loginError}</div> : null}
          </div>
        </div>
      );
    }

    return (
      <div className="snbr-side-card">
        <div className="snbr-section-head compact">
          <div>
            <h3>Autenticacao</h3>
            <p>Trial e Free entram direto. Premium confirma o login pelo codigo no email.</p>
          </div>
        </div>
        <div className="snbr-auth">
          <input className="snbr-input" value={email} onChange={(event) => setEmail(event.target.value)} placeholder="Email" />
          <input className="snbr-input" value={password} onChange={(event) => setPassword(event.target.value)} placeholder="Senha" type="password" />
          <button className="snbr-button primary" onClick={handleLogin} type="button">Entrar</button>
          {loginError ? <div className="snbr-empty">{loginError}</div> : null}
        </div>
      </div>
    );
  }

  function renderRightRail() {
    return (
      <aside className="snbr-right-rail">
        <div className="snbr-mobile-rail-header">
          <div>
            <span className="snbr-small-eyebrow">Lateral</span>
            <h2>Contexto do simbolo</h2>
          </div>
          <button className="snbr-mobile-rail-toggle" onClick={() => setMobileInsightsOpen((value) => !value)} type="button">
            {mobileInsightsOpen ? "Fechar" : "Abrir"}
          </button>
        </div>

        <div className={cx("snbr-collapsible-panel", mobileInsightsOpen && "open")}>
          <div className="snbr-side-card">
            <div className="snbr-section-head compact">
              <div>
                <h3>Ativo em foco</h3>
                <p>Preco, score e leitura rapida ao lado do feed.</p>
              </div>
            </div>
            {stats.map((item) => (
              <div key={item.label} className="snbr-account-line">
                <span>{item.label}</span>
                <strong>{item.value}</strong>
              </div>
            ))}
          </div>

          <div className="snbr-side-card">
            <div className="snbr-section-head compact">
              <div>
                <h3>Latest news</h3>
                <p>Trilho editorial no estilo Stocktwits, alimentado pelo radar do sistema enquanto o feed de noticias real nao entra.</p>
              </div>
            </div>
            <div className="snbr-headline-list compact">
              {newsRows.slice(0, 3).map((item) => {
                return (
                  <button key={item.id} className="snbr-headline-row side" onClick={() => selectTicker(item.symbol)} type="button">
                    <div>
                      <strong>{item.title}</strong>
                      <p>{item.source} • {item.age}</p>
                    </div>
                    <span className="snbr-headline-symbol">{item.symbol}</span>
                  </button>
                );
              })}
            </div>
          </div>

          <div className="snbr-side-card">
            <div className="snbr-section-head compact">
              <div>
                <h3>Top discussions</h3>
                <p>Conversas que estao puxando reacao e engajamento agora.</p>
              </div>
            </div>
            <div className="snbr-discussion-mini-list">
              {discussionPosts.slice(0, 4).map((post) => (
                <article key={post.id} className="snbr-mini-post">
                  <strong>{post.user}</strong>
                  <p>{post.text}</p>
                  <span>{post.likes || 0} likes</span>
                </article>
              ))}
              {!discussionPosts.length ? <div className="snbr-empty">Sem conversas em destaque ainda.</div> : null}
            </div>
          </div>

          <div className="snbr-side-card">
            <div className="snbr-section-head compact">
              <div>
                <h3>Poll ativa</h3>
                <p>Votacao semanal aberta para a comunidade do ticker.</p>
              </div>
            </div>
            <div className="snbr-poll-mini">
              <strong>{activePoll.question || `Poll de ${selectedTicker}`}</strong>
              {(activePoll.options || []).slice(0, 2).map((option) => (
                <div key={option.key} className="snbr-account-line">
                  <span>{option.label}</span>
                  <strong>{option.votes}</strong>
                </div>
              ))}
            </div>
          </div>

          {token ? (
            <div className="snbr-side-card">
              <div className="snbr-section-head compact">
                <div>
                  <h3>Conta e acesso</h3>
                  <p>Seu plano e os canais liberados agora.</p>
                </div>
              </div>
              <div className="snbr-account-line"><span>Plano</span><strong>{access?.plan || "guest"}</strong></div>
              <div className="snbr-account-line"><span>Web</span><strong>{access?.access?.web ? "ativo" : "bloqueado"}</strong></div>
              <div className="snbr-account-line"><span>Telegram</span><strong>{access?.access?.telegram ? "ativo" : "bloqueado"}</strong></div>
              <div className="snbr-account-line"><span>Storage</span><strong>{String((mediaStatus?.provider as string) || workspace?.media?.provider || "local")}</strong></div>
            </div>
          ) : null}
        </div>
      </aside>
    );
  }

  if (focusedTab) {
    const focusedLabel = getTabMeta(currentTabs.find((tab) => tab.id === currentTab) || FALLBACK_TABS[0]);

    return (
      <div className={cx("snbr-app", darkMode && "theme-dark", "snbr-popout-mode")}>
      <div className="snbr-popout-header">
          <div>
            <h1>{focusedLabel.label}</h1>
            <p>{selectedTicker} em modo destacavel para monitor separado.</p>
          </div>
          <div className="snbr-symbol-pills">
            <span className="snbr-chip">Ticker: {selectedTicker}</span>
            <span className="snbr-chip">Plano: {access?.plan || "guest"}</span>
          </div>
        </div>
        <div className="snbr-popout-content">
          {error ? <div className="snbr-empty">Erro: {error}</div> : null}
          {renderCenterPanel()}
        </div>
      </div>
    );
  }

  return (
    <div className={cx("snbr-app", darkMode && "theme-dark")}>
      <aside className="snbr-left-rail" ref={leftRailRef}>
        <div className="snbr-left-header">
          <div>
            <h1>StockNewsBR</h1>
            <p>Inteligencia de Mercado com IA</p>
          </div>
          <button className="snbr-mobile-rail-toggle" onClick={() => setMobileWatchlistOpen((value) => !value)} type="button">
            {mobileWatchlistOpen ? "Fechar" : "Abrir"}
          </button>
        </div>

        <div className={cx("snbr-collapsible-panel", "snbr-left-panel-stack", mobileWatchlistOpen && "open")}>
          {renderAuthCard()}

          <div className="snbr-search-block">
            <div className="snbr-section-head compact">
              <div>
                <h3>Busca</h3>
                <p>Encontre ativos da B3 pra sua lista ativa. Adicione ou exclua.</p>
              </div>
            </div>
            <input
              className="snbr-input"
              value={watchlistQuery}
              onChange={(event) => {
                const nextValue = event.target.value;
                setWatchlistQuery(nextValue);
                if (!focusedTab && currentTab === "busca" && !nextValue.trim()) setActiveTab("grafico");
              }}
              onKeyDown={(event) => {
                if (event.key === "Enter") {
                  applyTicker();
                }
              }}
              placeholder="Buscar ativo da B3, BDR, cripto ou USA"
            />
            <div className="snbr-watch-actions">
              <button className="snbr-button primary" onClick={applyTicker} type="button">
                Busca
              </button>
              <button className="snbr-button secondary" onClick={handleAddToActiveList} type="button">
                Adicionar
              </button>
              <button className="snbr-button secondary" onClick={() => handleRemoveFromActiveList()} type="button">
                Excluir
              </button>
            </div>
          </div>

            <div className="snbr-side-card snbr-active-list-shell">
              <div className="snbr-watch-toolbar snbr-watch-toolbar-inline">
                <div>
                  <strong>Minha Lista Ativa</strong>
                  <p>Ativos preloaded por categoria + qualquer ativo da B3 adicionado pela busca.</p>
                </div>
                <span className="snbr-chip">{activeWatchSymbols.length} ativos</span>
              </div>
              <div className="snbr-active-filter-row" aria-label="Filtros da lista ativa">
                <button className={cx("snbr-filter-chip", watchCategory === "Todos" && "active")} onClick={() => setWatchCategory("Todos")} type="button">Todos</button>
                <button className={cx("snbr-filter-chip", watchCategory === "B3" && "active")} onClick={() => setWatchCategory("B3")} type="button">B3</button>
                <button className={cx("snbr-filter-chip", watchCategory === "BDR" && "active")} onClick={() => setWatchCategory("BDR")} type="button">BDR</button>
                <button className={cx("snbr-filter-chip", watchCategory === "Crypto" && "active")} onClick={() => setWatchCategory("Crypto")} type="button">Crypto</button>
                <button className={cx("snbr-filter-chip", watchCategory === "USA" && "active")} onClick={() => setWatchCategory("USA")} type="button">USA</button>
              </div>

            <div className="snbr-active-list-scroll">
              {renderWatchlist()}
            </div>
          </div>

          <div className="snbr-left-footer">
            <span className="snbr-left-footer-title">🏛 Estrutura institucional StockNewsBR – Inteligência de Mercado com IA</span>
            {INSTITUTIONAL_SECTIONS.map((section) => (
              <button key={section.id} onClick={() => openInstitutionalSection(section.id)} type="button">
                {section.label}
              </button>
            ))}
          </div>
        </div>
      </aside>

      <main className="snbr-symbol-page">
        <nav className="snbr-symbol-tabs snbr-top-tabs" aria-label="Tabs do simbolo">
          <button className="snbr-tab-scroll" onClick={() => scrollTabs("left")} type="button" aria-label="Mover tabs para a esquerda">
            ◀
          </button>
          <div className="snbr-tab-list" ref={tabListRef}>
            {visibleTabs.map((tab, index) => {
              const meta = getTabMeta(tab);

              return (
                <div key={tab.id} className="snbr-symbol-tab-shell">
                  <button
                    className={cx("snbr-symbol-tab", currentTab === tab.id && "active")}
                    onClick={() => setActiveTab(tab.id)}
                    type="button"
                    title={meta.label}
                  >
                    <span>{topTabText(tab.id, meta.short)}</span>
                  </button>
                </div>
              );
            })}
          </div>
          {DETACHABLE_IA_TABS.has(currentTab) ? (
            <button
              aria-label={`Liberar ${currentTabMeta.short}`}
              className="snbr-inline-popout snbr-top-popout"
              onClick={() => openPopout(currentTab)}
              type="button"
            >
              Liberar Tela
            </button>
          ) : null}
          <button className="snbr-tab-scroll" onClick={() => scrollTabs("right")} type="button" aria-label="Mover tabs para a direita">
            ▶
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
                    {item.changePct != null ? formatSignedPercent(item.changePct) : item.score != null ? `${Number(item.score).toFixed(0)} pts` : "Radar"}
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
                <strong>R$ {formatPrice(quote?.price)}</strong>
                <span className={cx("snbr-price-change", priceDirectionClass)}>
                  {formatSignedPercent(quote?.change_pct)}
                </span>
              </div>
              {hasPriceMovement ? (
                <div className={cx("snbr-after-hours-line", priceDirectionClass)}>
                  <span>{movementArrow(priceDirectionClass)}</span>
                  <strong>{priceMovementValue != null ? formatPrice(priceMovementValue) : "n/a"}</strong>
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
              <strong>Modo visitante ativo.</strong>
              <span>Login libera interacao completa, chat, publicacao e dados protegidos do produto.</span>
            </div>
          ) : null}
          {renderCenterPanel()}
        </section>
      </main>
    </div>
  );
}
