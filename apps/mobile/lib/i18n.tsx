import * as SecureStore from "expo-secure-store";
import type { ReactNode } from "react";
import { createContext, useContext, useEffect, useState } from "react";
import { Pressable, Text, View } from "react-native";

import { theme } from "@/components/ui";

const LANG_KEY = "stocknewsbr.lang";

export type Lang = "pt" | "en";

const pt = {
  // login
  appTag: "StockNewsBR Mobile",
  loginTitle: "A central completa do projeto no celular.",
  loginSubtitle: "Login, mercado, social, polls e telegram em um fluxo unico, rapido e sem crash.",
  accessTitle: "Acesso",
  accessSubtitle: "Use a conta do produto. Trial entra direto; Premium pode pedir OTP por email.",
  emailPh: "Email",
  passwordPh: "Senha",
  signIn: "Entrar no app",
  otpFallbackPill: "email otp",
  otpHelp: "Confirme o codigo recebido por email para concluir o login Premium.",
  otpPh: "Codigo de 6 digitos",
  otpValidate: "Validar codigo",
  otpLocalCode: "Codigo local:",
  msgOtpRequired: "Conta Premium exige confirmacao por email.",
  msgSessionOk: "Sessao liberada com sucesso.",
  planTitle: "Plano e lancamento",
  planSubtitle: "Trial, Premium e regra de refund sincronizados com o backend.",
  trialBR: "Trial BR",
  trialUSA: "Trial USA",
  daysSuffix: "dias",
  brMonthly: "BR mensal",
  brAnnual: "BR anual",
  usaMonthly: "USA mensal",
  usaAnnual: "USA anual",
  primaryLabel: "Principal",
  refundLabel: "Refund",
  planNote:
    "Preco, pagamentos, mudanca de planos, cancelamento e reembolso ficam somente no Google Play. Quem assina pelo app recebe acesso ao website com login e senha e tambem ao Telegram. Apple Store em breve.",
  shortcutsTitle: "Atalhos",
  shortcutsSubtitle: "Se quiser validar a plataforma publica, o dominio oficial abre daqui.",
  openSite: "Abrir site oficial",
  forgotPassword: "Esqueci minha senha",
  needEmailFirst: "Digite seu email primeiro.",
  codeSentMsg: "Se o email existir, enviamos um codigo de acesso. Confirme abaixo.",
  brAnnualDiscount: "BR anual desconto",
  usaAnnualDiscount: "USA anual desconto",
  // tabs
  tabHome: "Home",
  tabMarket: "Mercado",
  tabSocial: "Social",
  tabPolls: "Polls",
  tabProfile: "Perfil",
  // home
  homeTitle: "Painel rapido, com leitura institucional e acesso ao ecossistema.",
  userFallback: "Usuario",
  overviewTitle: "Visao geral",
  overviewSubtitle: "Um resumo da saude do motor, do snapshot e da sessao ativa.",
  stratTitle: "Painel Estrategico",
  stratSubtitle: "Leitura unica do Score Mestre, Auditor e Risk IA.",
  stratRiskFallback: "Risco indisponivel",
  stratDirectionFallback: "Neutra",
  stratSummaryFallback: "Resumo estrategico ainda indisponivel.",
  stratChangeQ: "O que mudaria minha opiniao?",
  stratEmptyTitle: "Painel indisponivel",
  stratEmptyDesc: "O snapshot ainda nao trouxe o contrato estrategico.",
  quickTickerTitle: "Ticker rapido",
  quickTickerSubtitle: "Abre o detalhe completo do ativo com grafico, news, feed e poll.",
  openBtn: "Abrir",
  spotlightTitle: "Spotlight",
  spotlightSubtitle: "A melhor oportunidade ou o que mais merece atencao agora.",
  spotlightNoSummary: "Sem resumo adicional.",
  spotlightEmptyTitle: "Sem spotlight",
  spotlightEmptyDesc: "O backend ainda nao trouxe uma oportunidade destacada agora.",
  topSignalsTitle: "Top signals",
  topSignalsSubtitle: "Sinais mais fortes do snapshot atual.",
  topSignalsEmptyTitle: "Sem top signals",
  topSignalsEmptyDesc: "O snapshot ainda nao entregou linhas suficientes para destaque.",
  rankingTitle: "Ranking",
  rankingSubtitle: "Os papeis mais bem colocados na leitura atual.",
  rankingEmptyTitle: "Sem ranking",
  rankingEmptyDesc: "A fila do ranking nao foi carregada ainda.",
  feedRecentTitle: "Feed recente",
  feedRecentSubtitle: "Posts trazidos do workspace para dar contexto social.",
  feedRecentEmptyTitle: "Sem posts",
  feedRecentEmptyDesc: "Ainda nao ha feed recente para destacar.",
  productShortcutsTitle: "Atalhos do produto",
  productShortcutsSubtitle: "O que mais vale abrir agora no ecossistema.",
  // market
  marketPill: "Mercado",
  marketTitle: "Leitura de fluxo, calor, radar e narrativa institucional.",
  marketSubtitle: "A tela concentra o que o app sabe do mercado em um toque rapido.",
  snapshotTitle: "Snapshot",
  snapshotSubtitle: "Sinaliza a saude da memoria de mercado.",
  narrativeTitle: "Narrativa",
  narrativeSubtitle: "O texto de contexto que ajuda a ler o dia sem caçar sinal solto.",
  narrativeHeader: "Narrativa de mercado",
  narrativeEmptyTitle: "Sem narrativa",
  narrativeEmptyDesc: "O backend nao retornou narrativa agora.",
  heatmapTitle: "Heatmap",
  heatmapSubtitle: "O que esta quente, o que esta fraco e os nomes com pressao real.",
  strengthLabel: "Forca",
  sectorsLabel: "Setores",
  heatmapEmptyTitle: "Heatmap vazio",
  heatmapEmptyDesc: "A leitura quente/fria ainda nao veio do servidor.",
  radarTitle: "Radar",
  radarSubtitle: "Movimentos com evento, gatilho ou aceleracao relevante.",
  eventsSuffix: "eventos",
  noEvents: "sem eventos",
  radarEmptyTitle: "Radar vazio",
  radarEmptyDesc: "Sem alvos de radar no momento.",
  moversTitle: "Top movers",
  moversSubtitle: "Ativos com maior tracao no recorte atual.",
  moversNote: "Top mover atual no ranking",
  moversEmptyTitle: "Sem movers",
  moversEmptyDesc: "A fila de top movers ainda nao voltou do backend.",
  // social
  socialPill: "Social por ticker",
  socialTitle: "Feed, post e contexto em uma tela so.",
  socialSubtitle: "Publique, leia comentarios e navegue direto para o detalhe do ativo.",
  tickerCardTitle: "Ticker",
  socialTickerSubtitle: "Troque o ativo e a tela recarrega o feed associado.",
  openTicker: "Abrir ticker",
  refreshBtn: "Atualizar",
  newPostTitle: "Novo post",
  newPostSubtitle: "Conte algo do ativo ou do fluxo que voce esta vendo agora.",
  draftPh: "Escreva sua leitura...",
  publishFeedBtn: "Publicar no feed",
  postSuccess: "Post publicado com sucesso.",
  feedCardTitle: "Feed",
  postsLoadedSuffix: "posts carregados",
  feedNoneYet: "Sem posts carregados ainda",
  socialFeedEmptyTitle: "Sem feed",
  socialFeedEmptyDesc: "Ainda nao ha posts para este ticker.",
  telegramLinkedSubtitle: "O acesso do Telegram ja esta conectado na conta.",
  // polls
  pollsPill: "Polls IA",
  pollsTitle: "Enquetes semanais por ticker.",
  pollsSubtitle: "Leitura simples, votacao rapida e historico para comparar a evolucao da tese.",
  pollsTickerSubtitle: "Troque o papel para ver a enquete ativa e o historico.",
  updatePoll: "Atualizar poll",
  currentPollTitle: "Enquete atual",
  currentPollNone: "Nenhuma enquete carregada.",
  votesSuffix: "votos",
  loginToVote: "Faça login para votar.",
  voteOk: "Voto registrado.",
  noOptionsTitle: "Sem opcoes",
  noOptionsDesc: "O backend ainda nao retornou opcoes para esta enquete.",
  historyTitle: "Historico",
  historySubtitle: "As ultimas enquetes do ativo.",
  historyEmptyTitle: "Sem historico",
  historyEmptyDesc: "Nenhuma enquete antiga encontrada para esse ticker.",
  // profile
  profilePill: "Perfil e acesso",
  profileTitle: "Conta, acesso, Telegram e legal em um so lugar.",
  profileSubtitle: "Aqui a pessoa confirma o plano, ajusta os dados e sai sem risco.",
  accountTitle: "Conta",
  accountSubtitle: "Resumo do usuario autenticado.",
  nameLabel: "Nome",
  emailLabel: "Email",
  planLabel: "Plano",
  otpLabel: "OTP",
  otpActive: "ativo",
  otpOff: "off",
  sessionPolicyPrefix: "Session policy:",
  noSessionPolicy: "Sem politica de sessao carregada.",
  editProfileTitle: "Editar perfil",
  editProfileSubtitle: "Atualizacao rapida do nome, email e avatar.",
  displayNamePh: "Display name",
  avatarPh: "Avatar URL",
  saveChanges: "Salvar alteracoes",
  profileSaved: "Perfil atualizado.",
  telegramTitle: "Telegram",
  telegramSubtitle: "Gera o link seguro para o canal oficial e abre o bot, se existir.",
  telegramBtn: "Gerar link do Telegram",
  telegramCodePrefix: "Codigo",
  telegramLinkOk: "Link gerado.",
  commercialTitle: "Resumo comercial",
  commercialSubtitle: "Plano carregado do backend e pronto para Google Play.",
  currentTrialLabel: "Trial atual",
  domainLabel: "Dominio",
  commercialNote:
    "Produto Android usa IDs de plano do backend: BR mensal/anual e USA mensal/anual. Cancelamento dentro de 7 dias respeita a janela de refund; depois disso o acesso segue ate o fim do periodo pago.",
  logoutTitle: "Encerrar sessao",
  logoutSubtitle: "Sai do app localmente e revoga a sessao quando possível.",
  logoutBtn: "Logout",
  // ticker screen
  backBtn: "Voltar",
  tickerScreenTitle: "Painel mobile do ativo.",
  tickerScreenSubtitle: "Preco, grafico, news, feed e poll no mesmo fluxo para abrir o ativo sem depender do desktop.",
  panelTitle: "Painel do ticker",
  panelSubtitle: "Leitura mais recente do ativo e estado real dos dados.",
  priceLabel: "Preco",
  noCandles: "sem candles validos",
  candlesSuffix: "candles",
  chartCardTitle: "Grafico mobile",
  chartCardSubtitle: "Candles, zonas, marcadores e ranges principais.",
  noSyntheticSignal: "Sem sinal sintetico ainda",
  chartSummaryFallback: "O backend pode estar sem candles suficientes neste momento.",
  publishTitle: "Compartilhe sua ideia em {ticker}",
  publishSubtitle: "Dica: cite gatilho, timeframe e o ponto em que sua tese invalida.",
  draftTickerPh: "Escreva sua tese em {ticker}",
  publishBtn: "Post",
  postOk: "Post publicado.",
  bullLabel: "Touro",
  bearLabel: "Urso",
  addImagePh: "URL da imagem ou GIF",
  predictionTemplate: "Previsao: alvo R$ ___ | gatilho: ___ | invalida se: ___",
  pollCardTitle: "Poll",
  pollNone: "Sem enquete ativa",
  pollEmptyTitle: "Sem poll",
  pollEmptyDesc: "O ticker ainda nao tem enquete ativa.",
  newsTitle: "News",
  newsSubtitle: "Manchetes filtradas e classificadas para o ticker.",
  newsEmptyTitle: "Sem noticias",
  newsEmptyDesc: "Nao ha manchetes carregadas para este ticker.",
  tickerFeedTitle: "Feed do ticker",
  tickerFeedSubtitle: "Posts, likes, comentarios e reposts associados ao ativo.",
  tickerFeedEmptyTitle: "Feed vazio",
  tickerFeedEmptyDesc: "Ainda nao ha posts para esse ticker.",
  pollHistoryTitle: "Historico da poll",
  pollHistorySubtitle: "Comparar as enquetes anteriores ajuda a entender drift de tese.",
  pollHistoryEmptyTitle: "Sem historico",
  pollHistoryEmptyDesc: "Nao ha historico para comparar ainda.",
  // chart component
  chartEmptyTitle: "Grafico indisponivel",
  chartEmptyText: "Faltam candles com preco real para {ticker}. Atualize quando o cache do worker entregar OHLC valido.",
  zoneFallback: "zona",
  lastMarkerPrefix: "Ultimo marcador:",
  triggerLabel: "Trigger:",
  triggerFallback: "aguardar confirmacao de preco/volume",
  invalidationLabel: "Invalidacao:",
  invalidationFallback: "perda do nivel/fluxo contrario",
  riskLabel: "Risco:",
  riskFallback: "monitorar liquidez, spread e regime",
};

const en: Record<MessageKey, string> = {
  // login
  appTag: "StockNewsBR Mobile",
  loginTitle: "The project's complete hub on your phone.",
  loginSubtitle: "Login, market, social, polls and telegram in a single fast, crash-free flow.",
  accessTitle: "Access",
  accessSubtitle: "Use your product account. Trial signs in directly; Premium may ask for an email OTP.",
  emailPh: "Email",
  passwordPh: "Password",
  signIn: "Enter the app",
  otpFallbackPill: "email otp",
  otpHelp: "Confirm the code received by email to finish the Premium login.",
  otpPh: "6-digit code",
  otpValidate: "Validate code",
  otpLocalCode: "Local code:",
  msgOtpRequired: "Premium accounts require email confirmation.",
  msgSessionOk: "Session unlocked successfully.",
  planTitle: "Plans and launch",
  planSubtitle: "Trial, Premium and refund rules synced with the backend.",
  trialBR: "Trial BR",
  trialUSA: "Trial USA",
  daysSuffix: "days",
  brMonthly: "BR monthly",
  brAnnual: "BR annual",
  usaMonthly: "USA monthly",
  usaAnnual: "USA annual",
  primaryLabel: "Primary",
  refundLabel: "Refund",
  planNote:
    "Pricing, payments, plan changes, cancellation and refunds happen only on Google Play. App subscribers also get website access with login and password, plus Telegram. Apple Store coming soon.",
  shortcutsTitle: "Shortcuts",
  shortcutsSubtitle: "To check the public platform, the official domain opens from here.",
  openSite: "Open official site",
  forgotPassword: "Forgot my password",
  needEmailFirst: "Enter your email first.",
  codeSentMsg: "If the email exists, we sent an access code. Confirm it below.",
  brAnnualDiscount: "BR annual discount",
  usaAnnualDiscount: "USA annual discount",
  // tabs
  tabHome: "Home",
  tabMarket: "Market",
  tabSocial: "Social",
  tabPolls: "Polls",
  tabProfile: "Profile",
  // home
  homeTitle: "Fast panel with institutional reading and ecosystem access.",
  userFallback: "User",
  overviewTitle: "Overview",
  overviewSubtitle: "A summary of engine health, snapshot state and the active session.",
  stratTitle: "Strategic Panel",
  stratSubtitle: "Single view of the Master Score, Auditor and Risk AI.",
  stratRiskFallback: "Risk unavailable",
  stratDirectionFallback: "Neutral",
  stratSummaryFallback: "Strategic summary not available yet.",
  stratChangeQ: "What would change my view?",
  stratEmptyTitle: "Panel unavailable",
  stratEmptyDesc: "The snapshot has not delivered the strategic contract yet.",
  quickTickerTitle: "Quick ticker",
  quickTickerSubtitle: "Opens the full asset detail with chart, news, feed and poll.",
  openBtn: "Open",
  spotlightTitle: "Spotlight",
  spotlightSubtitle: "The best opportunity or what deserves attention right now.",
  spotlightNoSummary: "No extra summary.",
  spotlightEmptyTitle: "No spotlight",
  spotlightEmptyDesc: "The backend has not surfaced a highlighted opportunity yet.",
  topSignalsTitle: "Top signals",
  topSignalsSubtitle: "Strongest signals in the current snapshot.",
  topSignalsEmptyTitle: "No top signals",
  topSignalsEmptyDesc: "The snapshot has not delivered enough rows to highlight.",
  rankingTitle: "Ranking",
  rankingSubtitle: "Best-ranked symbols in the current reading.",
  rankingEmptyTitle: "No ranking",
  rankingEmptyDesc: "The ranking queue has not been loaded yet.",
  feedRecentTitle: "Recent feed",
  feedRecentSubtitle: "Posts pulled from the workspace for social context.",
  feedRecentEmptyTitle: "No posts",
  feedRecentEmptyDesc: "There is no recent feed to highlight yet.",
  productShortcutsTitle: "Product shortcuts",
  productShortcutsSubtitle: "What is most worth opening in the ecosystem now.",
  // market
  marketPill: "Market",
  marketTitle: "Flow, heat, radar and institutional narrative reading.",
  marketSubtitle: "This screen concentrates what the app knows about the market in one quick tap.",
  snapshotTitle: "Snapshot",
  snapshotSubtitle: "Signals the health of the market memory.",
  narrativeTitle: "Narrative",
  narrativeSubtitle: "Context text that helps read the day without chasing loose signals.",
  narrativeHeader: "Market narrative",
  narrativeEmptyTitle: "No narrative",
  narrativeEmptyDesc: "The backend returned no narrative right now.",
  heatmapTitle: "Heatmap",
  heatmapSubtitle: "What is hot, what is weak and the names under real pressure.",
  strengthLabel: "Strength",
  sectorsLabel: "Sectors",
  heatmapEmptyTitle: "Empty heatmap",
  heatmapEmptyDesc: "The hot/cold reading has not arrived from the server yet.",
  radarTitle: "Radar",
  radarSubtitle: "Moves with a relevant event, trigger or acceleration.",
  eventsSuffix: "events",
  noEvents: "no events",
  radarEmptyTitle: "Empty radar",
  radarEmptyDesc: "No radar targets at the moment.",
  moversTitle: "Top movers",
  moversSubtitle: "Assets with the most traction in the current cut.",
  moversNote: "Current top mover in the ranking",
  moversEmptyTitle: "No movers",
  moversEmptyDesc: "The top movers queue has not returned from the backend yet.",
  // social
  socialPill: "Social by ticker",
  socialTitle: "Feed, posts and context on a single screen.",
  socialSubtitle: "Publish, read comments and jump straight to the asset detail.",
  tickerCardTitle: "Ticker",
  socialTickerSubtitle: "Switch the asset and the screen reloads the related feed.",
  openTicker: "Open ticker",
  refreshBtn: "Refresh",
  newPostTitle: "New post",
  newPostSubtitle: "Share something about the asset or the flow you are watching now.",
  draftPh: "Write your take...",
  publishFeedBtn: "Publish to feed",
  postSuccess: "Post published successfully.",
  feedCardTitle: "Feed",
  postsLoadedSuffix: "posts loaded",
  feedNoneYet: "No posts loaded yet",
  socialFeedEmptyTitle: "No feed",
  socialFeedEmptyDesc: "There are no posts for this ticker yet.",
  telegramLinkedSubtitle: "Telegram access is already linked to this account.",
  // polls
  pollsPill: "AI Polls",
  pollsTitle: "Weekly polls by ticker.",
  pollsSubtitle: "Simple reading, quick voting and history to compare how the thesis evolves.",
  pollsTickerSubtitle: "Switch the symbol to see the active poll and its history.",
  updatePoll: "Refresh poll",
  currentPollTitle: "Current poll",
  currentPollNone: "No poll loaded.",
  votesSuffix: "votes",
  loginToVote: "Sign in to vote.",
  voteOk: "Vote recorded.",
  noOptionsTitle: "No options",
  noOptionsDesc: "The backend has not returned options for this poll yet.",
  historyTitle: "History",
  historySubtitle: "The asset's latest polls.",
  historyEmptyTitle: "No history",
  historyEmptyDesc: "No previous polls found for this ticker.",
  // profile
  profilePill: "Profile & access",
  profileTitle: "Account, access, Telegram and legal in one place.",
  profileSubtitle: "Here you confirm the plan, adjust your data and leave without risk.",
  accountTitle: "Account",
  accountSubtitle: "Authenticated user summary.",
  nameLabel: "Name",
  emailLabel: "Email",
  planLabel: "Plan",
  otpLabel: "OTP",
  otpActive: "on",
  otpOff: "off",
  sessionPolicyPrefix: "Session policy:",
  noSessionPolicy: "No session policy loaded.",
  editProfileTitle: "Edit profile",
  editProfileSubtitle: "Quick update of name, email and avatar.",
  displayNamePh: "Display name",
  avatarPh: "Avatar URL",
  saveChanges: "Save changes",
  profileSaved: "Profile updated.",
  telegramTitle: "Telegram",
  telegramSubtitle: "Generates the secure link to the official channel and opens the bot if available.",
  telegramBtn: "Generate Telegram link",
  telegramCodePrefix: "Code",
  telegramLinkOk: "Link generated.",
  commercialTitle: "Billing summary",
  commercialSubtitle: "Plan loaded from the backend and ready for Google Play.",
  currentTrialLabel: "Current trial",
  domainLabel: "Domain",
  commercialNote:
    "The Android product uses backend plan IDs: BR monthly/annual and USA monthly/annual. Cancelling within 7 days honors the refund window; after that, access continues until the end of the paid period.",
  logoutTitle: "Sign out",
  logoutSubtitle: "Signs out locally and revokes the session when possible.",
  logoutBtn: "Logout",
  // ticker screen
  backBtn: "Back",
  tickerScreenTitle: "Mobile asset panel.",
  tickerScreenSubtitle: "Price, chart, news, feed and poll in the same flow to open the asset without a desktop.",
  panelTitle: "Ticker panel",
  panelSubtitle: "Latest asset reading and the true state of the data.",
  priceLabel: "Price",
  noCandles: "no valid candles",
  candlesSuffix: "candles",
  chartCardTitle: "Mobile chart",
  chartCardSubtitle: "Candles, zones, markers and main ranges.",
  noSyntheticSignal: "No synthetic signal yet",
  chartSummaryFallback: "The backend may not have enough candles right now.",
  publishTitle: "Share your idea on {ticker}",
  publishSubtitle: "Tip: mention the trigger, timeframe and the point where your thesis breaks.",
  draftTickerPh: "Write your thesis on {ticker}",
  publishBtn: "Post",
  postOk: "Post published.",
  bullLabel: "Bull",
  bearLabel: "Bear",
  addImagePh: "Image or GIF URL",
  predictionTemplate: "Prediction: target ___ | trigger: ___ | invalid if: ___",
  pollCardTitle: "Poll",
  pollNone: "No active poll",
  pollEmptyTitle: "No poll",
  pollEmptyDesc: "This ticker has no active poll yet.",
  newsTitle: "News",
  newsSubtitle: "Filtered, classified headlines for the ticker.",
  newsEmptyTitle: "No news",
  newsEmptyDesc: "No headlines loaded for this ticker.",
  tickerFeedTitle: "Ticker feed",
  tickerFeedSubtitle: "Posts, likes, comments and reposts tied to the asset.",
  tickerFeedEmptyTitle: "Empty feed",
  tickerFeedEmptyDesc: "There are no posts for this ticker yet.",
  pollHistoryTitle: "Poll history",
  pollHistorySubtitle: "Comparing previous polls helps understand thesis drift.",
  pollHistoryEmptyTitle: "No history",
  pollHistoryEmptyDesc: "There is no history to compare yet.",
  // chart component
  chartEmptyTitle: "Chart unavailable",
  chartEmptyText: "No real-price candles for {ticker}. Refresh when the worker cache delivers valid OHLC.",
  zoneFallback: "zone",
  lastMarkerPrefix: "Last marker:",
  triggerLabel: "Trigger:",
  triggerFallback: "wait for price/volume confirmation",
  invalidationLabel: "Invalidation:",
  invalidationFallback: "level loss / opposing flow",
  riskLabel: "Risk:",
  riskFallback: "monitor liquidity, spread and regime",
};

export type MessageKey = keyof typeof pt;

const MESSAGES: Record<Lang, Record<MessageKey, string>> = { pt, en };

type I18nContextValue = {
  lang: Lang;
  setLang: (next: Lang) => void;
  t: (key: MessageKey) => string;
  tf: (key: MessageKey, vars: Record<string, string>) => string;
};

const I18nContext = createContext<I18nContextValue | null>(null);

export function LanguageProvider({ children }: { children: ReactNode }) {
  const [lang, setLangState] = useState<Lang>("pt");

  useEffect(() => {
    let cancelled = false;
    SecureStore.getItemAsync(LANG_KEY)
      .then((stored) => {
        if (!cancelled && (stored === "pt" || stored === "en")) {
          setLangState(stored);
        }
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, []);

  function setLang(next: Lang) {
    setLangState(next);
    SecureStore.setItemAsync(LANG_KEY, next).catch(() => {});
  }

  function t(key: MessageKey) {
    return MESSAGES[lang][key] ?? MESSAGES.pt[key] ?? key;
  }

  function tf(key: MessageKey, vars: Record<string, string>) {
    return Object.entries(vars).reduce(
      (text, [name, value]) => text.split(`{${name}}`).join(value),
      t(key),
    );
  }

  return <I18nContext.Provider value={{ lang, setLang, t, tf }}>{children}</I18nContext.Provider>;
}

export function useI18n() {
  const value = useContext(I18nContext);
  if (!value) {
    throw new Error("useI18n must be used within LanguageProvider");
  }
  return value;
}

const LANG_OPTIONS: Array<{ lang: Lang; flag: string; label: string }> = [
  { lang: "pt", flag: "\u{1F1E7}\u{1F1F7}", label: "PT" },
  { lang: "en", flag: "\u{1F1FA}\u{1F1F8}", label: "EN" },
];

export function LanguageToggle() {
  const { lang, setLang } = useI18n();

  return (
    <View style={{ flexDirection: "row", gap: 8 }}>
      {LANG_OPTIONS.map((option) => {
        const active = lang === option.lang;
        return (
          <Pressable
            key={option.lang}
            accessibilityRole="button"
            accessibilityLabel={option.lang === "pt" ? "Portugues (Brasil)" : "English (USA)"}
            accessibilityState={{ selected: active }}
            onPress={() => setLang(option.lang)}
            style={{
              flexDirection: "row",
              alignItems: "center",
              gap: 6,
              minHeight: 38,
              paddingHorizontal: 12,
              borderRadius: 999,
              borderWidth: 1,
              borderColor: active ? theme.colors.accent : theme.colors.line,
              backgroundColor: active ? theme.colors.accentSoft : theme.colors.surfaceSoft,
            }}
          >
            <Text style={{ fontSize: 16 }}>{option.flag}</Text>
            <Text style={{ color: active ? theme.colors.accent : theme.colors.muted, fontWeight: "800", fontSize: 12 }}>
              {option.label}
            </Text>
          </Pressable>
        );
      })}
    </View>
  );
}
