"use client";

import type { ReactNode, RefObject } from "react";

import type { FeedPost, PollPayload, UserAccess } from "@/lib/types";

import type { WorkspaceNewsRow, WorkspaceHelpSection } from "@/components/workspace-sections";

function cx(...values: Array<string | false | null | undefined>) {
  return values.filter(Boolean).join(" ");
}

type AppLocale = "pt-BR" | "en-US";
type WatchCategory = "Todos" | "B3" | "BDR" | "Crypto" | "USA";

function socialText(value: string | null | undefined, locale: AppLocale) {
  const text = String(value || "").trim();
  if (locale !== "en-US" || !text) return text;
  return text
    .replace(/preço/g, "price")
    .replace(/Preço/g, "Price")
    .replace(/mercado/g, "market")
    .replace(/Mercado/g, "Market")
    .replace(/notícia/g, "news")
    .replace(/Notícia/g, "News")
    .replace(/compra/g, "buy")
    .replace(/Compra/g, "Buy")
    .replace(/venda/g, "sell")
    .replace(/Venda/g, "Sell")
    .replace(/alta/g, "uptrend")
    .replace(/Alta/g, "Uptrend")
    .replace(/baixa/g, "downtrend")
    .replace(/Baixa/g, "Downtrend")
    .replace(/risco/g, "risk")
    .replace(/Risco/g, "Risk")
    .replace(/fluxo/g, "flow")
    .replace(/Fluxo/g, "Flow");
}

type LeftRailProps = {
  locale: AppLocale;
  railRef?: RefObject<HTMLElement | null>;
  mobileWatchlistOpen: boolean;
  onToggleMobileWatchlist: () => void;
  watchlistQuery: string;
  onWatchlistQueryChange: (value: string) => void;
  onWatchlistQueryEnter: () => void;
  onApplyTicker: () => void;
  onAddTicker: () => void;
  onRemoveTicker: () => void;
  watchCategory: WatchCategory;
  onSetWatchCategory: (value: WatchCategory) => void;
  activeWatchCount: number;
  accessCard: ReactNode;
  authCard: ReactNode;
  notificationCard: ReactNode;
  toolsCard: ReactNode;
  watchlistContent: ReactNode;
  institutionalSections: WorkspaceHelpSection[];
  onOpenInstitutionalSection: (id: string) => void;
};

export function WorkspaceLeftRail({
  locale,
  railRef,
  mobileWatchlistOpen,
  onToggleMobileWatchlist,
  watchlistQuery,
  onWatchlistQueryChange,
  onWatchlistQueryEnter,
  onApplyTicker,
  onAddTicker,
  onRemoveTicker,
  watchCategory,
  onSetWatchCategory,
  activeWatchCount,
  accessCard,
  authCard,
  notificationCard,
  toolsCard,
  watchlistContent,
  institutionalSections,
  onOpenInstitutionalSection,
}: LeftRailProps) {
  const isEnglish = locale === "en-US";
  const categoryLabels: Record<WatchCategory, string> = {
    Todos: isEnglish ? "All" : "Todos",
    B3: "B3",
    BDR: "BDR",
    Crypto: "Crypto",
    USA: "USA",
  };

  return (
    <aside className="snbr-left-rail" ref={railRef}>
      <div className="snbr-left-header">
        <div>
          <h1>StockNewsBR</h1>
          <p>{isEnglish ? "AI Market Intelligence" : "Inteligencia de Mercado com IA"}</p>
        </div>
        <button
          aria-expanded={mobileWatchlistOpen}
          className="snbr-mobile-rail-toggle"
          onClick={onToggleMobileWatchlist}
          type="button"
        >
          {mobileWatchlistOpen ? (isEnglish ? "Close" : "Fechar") : (isEnglish ? "Open" : "Abrir")}
        </button>
      </div>

      <div className={cx("snbr-collapsible-panel", "snbr-left-panel-stack", mobileWatchlistOpen && "open")}>
        {accessCard}
        {authCard}
        {notificationCard}

        <div className="snbr-search-block">
          <div className="snbr-section-head compact">
            <div>
              <h3>{isEnglish ? "Asset Search" : "Busca de ativos"}</h3>
              <p>{isEnglish ? "Open B3, BDR, crypto or USA assets on screen without adding them automatically." : "Use para abrir B3, BDR, cripto ou ação dos EUA na tela, sem adicionar automaticamente."}</p>
            </div>
          </div>
          <input
            aria-label={isEnglish ? "Search asset to open or add" : "Buscar ativo para abrir ou adicionar"}
            className="snbr-input"
            value={watchlistQuery}
            onChange={(event) => onWatchlistQueryChange(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter") onWatchlistQueryEnter();
            }}
            placeholder={isEnglish ? "Search asset, like F, AAPL, PETR4 or BTCUSD" : "Buscar ativo, como PETR4, F, AAPL ou BTCUSD"}
          />
          <p className="snbr-assistive-copy">
            {isEnglish ? "Search opens the asset on screen. Add puts it in your active list. Nothing is added by itself." : "Buscar abre o ativo na tela. Adicionar coloca o ativo na sua lista ativa. Nada entra sozinho."}
          </p>
          <div className="snbr-watch-actions">
            <button className="snbr-button primary" onClick={onApplyTicker} type="button" aria-label={isEnglish ? "Open asset on screen" : "Abrir ativo na tela"}>
              {isEnglish ? "Open" : "Abrir na tela"}
            </button>
            <button className="snbr-button secondary" onClick={onAddTicker} type="button" aria-label={isEnglish ? "Add current asset to active list" : "Adicionar acao atual a lista ativa"}>
              {isEnglish ? "Add to list" : "Adicionar a lista"}
            </button>
            <button className="snbr-button secondary" onClick={onRemoveTicker} type="button" aria-label={isEnglish ? "Remove current asset from active list" : "Excluir acao atual da lista ativa"}>
              {isEnglish ? "Remove" : "Excluir"}
            </button>
          </div>
        </div>

        {toolsCard}

        <div className="snbr-side-card snbr-active-list-shell">
          <div className="snbr-watch-toolbar snbr-watch-toolbar-inline">
            <div>
              <strong>{isEnglish ? "My Active List" : "Minha Lista Ativa"}</strong>
              <p>{isEnglish ? "Preloaded assets by category + any asset added from search." : "Ativos preloaded por categoria + qualquer ativo adicionado pela busca."}</p>
            </div>
            <span className="snbr-chip">{activeWatchCount} {isEnglish ? "assets" : "ativos"}</span>
          </div>
          <div className="snbr-active-filter-row" aria-label={isEnglish ? "Active list filters" : "Filtros da lista ativa"}>
            {(["Todos", "B3", "BDR", "Crypto", "USA"] as const).map((category) => (
              <button
                key={category}
                className={cx("snbr-filter-chip", watchCategory === category && "active")}
                onClick={() => onSetWatchCategory(category)}
                type="button"
                aria-pressed={watchCategory === category}
              >
                {categoryLabels[category]}
              </button>
            ))}
          </div>

          <div className="snbr-active-list-scroll">{watchlistContent}</div>
        </div>

        <div className="snbr-left-footer">
          <span className="snbr-left-footer-title">{isEnglish ? "🏛 StockNewsBR institutional structure - AI Market Intelligence" : "🏛 Estrutura institucional StockNewsBR – Inteligência de Mercado com IA"}</span>
          {institutionalSections.slice(0, 8).map((section) => (
            <button
              key={section.id}
              onClick={() => section.id && onOpenInstitutionalSection(section.id)}
              type="button"
              aria-label={`${isEnglish ? "Open institutional section" : "Abrir secao institucional"} ${section.label || section.title}`}
            >
              {section.label || section.title}
            </button>
          ))}
        </div>
      </div>
    </aside>
  );
}

type RightRailProps = {
  locale: AppLocale;
  mobileInsightsOpen: boolean;
  onToggleMobileInsights: () => void;
  stats: Array<{ label: string; value: string }>;
  newsRows: WorkspaceNewsRow[];
  discussionPosts: FeedPost[];
  activePoll: PollPayload;
  selectedTicker: string;
  token: string;
  access: UserAccess | null;
  mediaProvider: string;
  onSelectTicker: (symbol: string) => void;
};

export function WorkspaceRightRail({
  locale,
  mobileInsightsOpen,
  onToggleMobileInsights,
  stats,
  newsRows,
  discussionPosts,
  activePoll,
  selectedTicker,
  token,
  access,
  mediaProvider,
  onSelectTicker,
}: RightRailProps) {
  const isEnglish = locale === "en-US";

  return (
    <aside className="snbr-right-rail">
      <div className="snbr-mobile-rail-header">
        <div>
          <h2>{isEnglish ? "Quick Summary" : "Resumo rapido"}</h2>
          <p>{isEnglish ? "News, conversations and access in a short read." : "Noticias, conversas e acesso em leitura curta."}</p>
        </div>
        <button
          aria-expanded={mobileInsightsOpen}
          className="snbr-mobile-rail-toggle"
          onClick={onToggleMobileInsights}
          type="button"
        >
          {mobileInsightsOpen ? (isEnglish ? "Close" : "Fechar") : (isEnglish ? "Open" : "Abrir")}
        </button>
      </div>

      <div className={cx("snbr-collapsible-panel", mobileInsightsOpen && "open")}>
        <div className="snbr-side-card snbr-side-card-highlight">
          <div className="snbr-section-head compact">
            <div>
              <h3>{isEnglish ? "Asset in Focus" : "Ativo em foco"}</h3>
              <p>{isEnglish ? "Price, score and quick read next to the feed." : "Preco, score e leitura rapida ao lado do feed."}</p>
            </div>
          </div>
          <div className="snbr-side-summary-grid">
            {stats.map((item) => (
              <div key={item.label} className="snbr-mini-stat">
                <span>{item.label}</span>
                <strong>{item.value}</strong>
              </div>
            ))}
          </div>
        </div>

        <div className="snbr-side-card">
          <div className="snbr-section-head compact">
            <div>
              <h3>{isEnglish ? "Recent News" : "Noticias recentes"}</h3>
              <p>{isEnglish ? "Real ticker news with cache for a quick workspace read." : "Noticias reais do ativo com cache para leitura rapida no workspace."}</p>
            </div>
          </div>
          <div className="snbr-headline-list compact">
            {newsRows.slice(0, 3).map((item) => (
              <button
                key={item.id}
                className={cx("snbr-headline-row", "side", !item.useful && "noise")}
                onClick={() => item.url ? window.open(item.url, "_blank", "noopener,noreferrer") : onSelectTicker(item.symbol)}
                type="button"
              >
                <div className="snbr-news-copy">
                  <strong>{item.title}</strong>
                  <p>{item.source} • {item.age}</p>
                  <span>{item.cardSummary}</span>
                  <div className="snbr-news-meta-row compact">
                    {item.impact ? <span className="snbr-news-impact compact">{item.impact}</span> : null}
                    <span className="snbr-news-impact compact">{item.quality}</span>
                    {item.sameStoryCount > 1 ? <span>{item.sameStoryCount} {isEnglish ? "versions" : "versoes"}</span> : null}
                    {item.relevanceScore != null ? <span>{Math.round(item.relevanceScore)} {isEnglish ? "rel." : "relev."}</span> : null}
                  </div>
                </div>
                <span className="snbr-headline-symbol">{item.symbol}</span>
              </button>
            ))}
          </div>
        </div>

        <div className="snbr-side-card">
          <div className="snbr-section-head compact">
            <div>
              <h3>{isEnglish ? "Featured Discussions" : "Discussoes em destaque"}</h3>
              <p>{isEnglish ? "Conversations driving reactions and engagement right now." : "Conversas que estao puxando reacao e engajamento agora."}</p>
            </div>
          </div>
          <div className="snbr-discussion-mini-list">
            {discussionPosts.slice(0, 4).map((post) => (
              <article key={post.id} className="snbr-mini-post">
                <strong>{post.user}</strong>
                <p>{socialText(post.text, locale)}</p>
                <div className="snbr-mini-post-meta">
                  <span>{post.ticker || selectedTicker}</span>
                  <span>{post.likes || 0} likes</span>
                </div>
              </article>
            ))}
            {!discussionPosts.length ? <div className="snbr-empty">{isEnglish ? "No featured discussions yet." : "Sem conversas em destaque ainda."}</div> : null}
          </div>
        </div>

        <div className="snbr-side-card">
          <div className="snbr-section-head compact">
            <div>
              <h3>{isEnglish ? "Poll/Vote" : "Poll/Votar"}</h3>
              <p>{isEnglish ? "Weekly vote open for the ticker community." : "Votação semanal aberta para a comunidade do ticker."}</p>
            </div>
          </div>
          <div className="snbr-poll-mini">
            <strong>{activePoll.question || `${isEnglish ? "Poll/Vote for" : "Poll/Votar de"} ${selectedTicker}`}</strong>
            <div className="snbr-poll-mini-meta">
              <span>{activePoll.total_votes || 0} {isEnglish ? "votes" : "votos"}</span>
              <span>{activePoll.status || (isEnglish ? "open" : "aberta")}</span>
            </div>
            {(activePoll.options || []).slice(0, 2).map((option) => (
              <div key={option.key} className="snbr-account-line snbr-poll-mini-row">
                <span>{option.label}</span>
                <strong>{option.votes}</strong>
              </div>
            ))}
            <p className="snbr-poll-mini-note">{isEnglish ? "AI and community complement each other: read the context, vote on the thesis and confirm with price." : "IA e comunidade se complementam: leia o contexto, vote na tese e confirme no preço."}</p>
          </div>
        </div>

        {token ? (
          <div className="snbr-side-card">
            <div className="snbr-section-head compact">
              <div>
                <h3>{isEnglish ? "Account and Access" : "Conta e acesso"}</h3>
                <p>{isEnglish ? "Your plan and currently unlocked channels." : "Seu plano e os canais liberados agora."}</p>
              </div>
            </div>
            <div className="snbr-account-line"><span>{isEnglish ? "Plan" : "Plano"}</span><strong>{access?.plan || "guest"}</strong></div>
            <div className="snbr-account-line"><span>Web</span><strong>{access?.access?.web ? (isEnglish ? "active" : "ativo") : (isEnglish ? "blocked" : "bloqueado")}</strong></div>
            <div className="snbr-account-line"><span>Telegram</span><strong>{access?.access?.telegram ? (isEnglish ? "active" : "ativo") : (isEnglish ? "blocked" : "bloqueado")}</strong></div>
            <div className="snbr-account-line"><span>Storage</span><strong>{mediaProvider}</strong></div>
          </div>
        ) : null}
      </div>
    </aside>
  );
}
