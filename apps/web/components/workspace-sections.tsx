"use client";

import type { HelpGuide } from "@/lib/types";

function cx(...values: Array<string | false | null | undefined>) {
  return values.filter(Boolean).join(" ");
}

type AppLocale = "pt-BR" | "en-US";

function normalizeText(value?: string | null) {
  return String(value || "")
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/\s+/g, " ")
    .trim()
    .toLowerCase();
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

function uniqueNewsLines(title: string, values: string[]) {
  const seen = new Set([normalizeText(title)]);
  return values.filter((value) => {
    const normalized = normalizeText(value);
    if (!normalized) return false;
    if (Array.from(seen).some((current) => current && (current === normalized || current.includes(normalized) || normalized.includes(current)))) {
      return false;
    }
    seen.add(normalized);
    return true;
  });
}

function newsSentimentVisual(sentiment?: string | null, locale: AppLocale = "pt-BR") {
  const normalized = normalizeText(sentiment);
  if (normalized.includes("bull") || normalized.includes("alta") || normalized.includes("positivo")) {
    return { label: locale === "en-US" ? "Bullish" : "Alta", tone: "bullish", icon: "🟢" };
  }
  if (normalized.includes("bear") || normalized.includes("baixa") || normalized.includes("negativo")) {
    return { label: locale === "en-US" ? "Bearish" : "Baixa", tone: "bearish", icon: "🔴" };
  }
  return { label: locale === "en-US" ? "Neutral" : "Neutra", tone: "neutral", icon: "⚪" };
}

function helpTextEn(value?: string | null) {
  const text = String(value || "").trim();
  if (!text) return "";
  const normalized = normalizeText(text);
  if (normalized.includes("ajuda educacional")) return "Trader Educational Help";
  if (normalized.includes("nossa plataforma usa modelos quantitativos")) {
    return "The platform uses quantitative models, AI and institutional-desk tools to turn complex reads into a simple trader screen.";
  }
  return text
    .replace(/Ajuda Educacional para o Trader/g, "Trader Educational Help")
    .replace(/Inteligência Artificial/g, "Artificial Intelligence")
    .replace(/Inteligência/g, "Intelligence")
    .replace(/inteligência/g, "intelligence")
    .replace(/mercado/g, "market")
    .replace(/Mercado/g, "Market")
    .replace(/trader/g, "trader")
    .replace(/ativos/g, "assets")
    .replace(/ativo/g, "asset")
    .replace(/notícia/g, "news")
    .replace(/preço/g, "price")
    .replace(/compra/g, "buy")
    .replace(/venda/g, "sell")
    .replace(/risco/g, "risk");
}

export type WorkspaceSearchResult = {
  symbol: string;
  label: string;
  priceText: string;
  movementText: string;
  movementClass: string;
};

export type WorkspaceNewsRow = {
  id: string;
  symbol: string;
  headline: string;
  title: string;
  source: string;
  sourceName?: string | null;
  sourceUrl?: string | null;
  age: string;
  publishedTime: string;
  publishedAtIso?: string | null;
  fetchedAt?: string | null;
  ageMinutes?: number | null;
  isToday?: boolean | null;
  isStale?: boolean | null;
  freshnessBucket?: string | null;
  freshnessLabel?: string | null;
  matchedSymbol?: string | null;
  language?: string | null;
  publicationStatus?: string | null;
  isIncomplete?: boolean | null;
  sector: string;
  industry: string;
  labels: string[];
  entities: string[];
  impact: string;
  sentiment?: "bullish" | "bearish" | "neutral" | string | null;
  quality: string;
  useful: boolean;
  relevanceScore?: number | null;
  rankingScore?: number | null;
  confidenceScore?: number | null;
  sameStoryCount: number;
  sourceCount?: number | null;
  ambiguityScore?: number | null;
  ambiguityFlags?: string[];
  traderTakeaway?: string;
  cardSummary: string;
  whyItMatters: string;
  editorial: string;
  marketContext: string;
  impactReason: string;
  url?: string | null;
};

function newsFreshnessStatus(item: WorkspaceNewsRow, isEnglish: boolean) {
  const bucket = String(item.freshnessBucket || "").toLowerCase();
  if (bucket === "today") return isEnglish ? "News from today" : "Notícia de hoje";
  if (bucket === "yesterday") return isEnglish ? "Previous news / Yesterday" : "Notícia anterior / Ontem";
  if (bucket === "2_7_days") return isEnglish ? "Previous news / 2-7 days" : "Notícia anterior / 2-7 dias";
  if (bucket === "older_7_days") return isEnglish ? "Old news / 7+ days" : "Notícia antiga / 7+ dias";
  if (typeof item.ageMinutes === "number" && Number.isFinite(item.ageMinutes)) {
    if (item.ageMinutes < 24 * 60) return isEnglish ? "News from today" : "Notícia de hoje";
    if (item.ageMinutes < 48 * 60) return isEnglish ? "Previous news / Yesterday" : "Notícia anterior / Ontem";
    if (item.ageMinutes <= 7 * 24 * 60) return isEnglish ? "Previous news / 2-7 days" : "Notícia anterior / 2-7 dias";
    return isEnglish ? "Old news / 7+ days" : "Notícia antiga / 7+ dias";
  }
  return item.isStale
    ? (isEnglish ? "Previous news" : "Notícia anterior")
    : (isEnglish ? "News from today" : "Notícia de hoje");
}

export type WorkspaceHelpSection = {
  id?: string;
  label?: string;
  title: string;
  body: string[];
  rows?: Array<{
    item: string;
    explanation: string;
  }>;
};

type SearchPanelProps = {
  locale?: AppLocale;
  selectedTicker: string;
  searchResults: WorkspaceSearchResult[];
  onSelectTicker: (symbol: string) => void;
};

export function WorkspaceSearchPanel({
  locale = "pt-BR",
  selectedTicker,
  searchResults,
  onSelectTicker,
}: SearchPanelProps) {
  const isEnglish = locale === "en-US";
  return (
    <section id="panel-busca" className="snbr-plain-panel" aria-labelledby="snbr-search-panel-title">
      <div className="snbr-section-head">
        <div>
          <h3 id="snbr-search-panel-title">{isEnglish ? "Search" : "Busca"}</h3>
          <p>{isEnglish ? "Search web assets to open, compare or add to your active list." : "Busque ativos da internet para abrir, comparar ou adicionar a sua lista ativa."}</p>
        </div>
      </div>
      <p className="snbr-assistive-copy" aria-live="polite">
        {searchResults.length
          ? `${searchResults.length} ${isEnglish ? "assets ready to open on screen." : "ativos prontos para abrir na tela."}`
          : (isEnglish ? `No loaded result for ${selectedTicker} yet.` : `Nenhum resultado carregado para ${selectedTicker} ainda.`)}
      </p>
      <div className="snbr-search-results">
        {searchResults.length ? (
          searchResults.map((item) => (
            <button
              key={item.symbol}
              className="snbr-search-result"
              onClick={() => onSelectTicker(item.symbol)}
              type="button"
              aria-label={isEnglish ? `Open ${item.symbol} on chart` : `Abrir ${item.symbol} no gráfico`}
            >
              <div>
                <strong>{item.symbol}</strong>
                <span>{item.label}</span>
              </div>
              <div className="snbr-watch-side">
                <span>{item.priceText}</span>
                <span className={cx("snbr-watch-change", item.movementClass)}>{item.movementText}</span>
              </div>
            </button>
          ))
        ) : (
          <div className="snbr-empty-thread">
            <strong>{isEnglish ? "No ticker found." : "Nenhum ticker encontrado."}</strong>
            <p>{isEnglish ? "Type a symbol or name in the left search to open results here." : "Digite símbolo ou nome na busca da esquerda para abrir resultados aqui."}</p>
          </div>
        )}
      </div>
    </section>
  );
}

type NewsPanelProps = {
  locale?: AppLocale;
  selectedTicker: string;
  newsRows: WorkspaceNewsRow[];
  newsStateText?: string | null;
  /** Backend news payload status ("ok" | "empty" | "error"); inferred from newsStateText when absent. */
  newsStatus?: string | null;
  onRetry?: () => void;
};

/**
 * loading = no payload for this ticker yet, or the backend only scheduled the real fetch
 * error   = the fetch failed
 * empty   = the backend answered for this ticker and there is genuinely nothing
 * ready   = at least one row to render
 */
export function newsPanelPhase(rowCount: number, newsStateText?: string | null, newsStatus?: string | null) {
  if (rowCount > 0) return "ready" as const;
  const status = normalizeText(newsStatus || "");
  const state = normalizeText(newsStateText || "");
  if (status === "error" || state.includes("falha") || state.includes("failed")) return "error" as const;
  if (status === "loading" || status === "pending") return "loading" as const;
  // The backend always ships a message with a real answer, so no message means the
  // payload for this ticker has not landed yet. "BUSCANDO NOTÍCIAS"/"searching" means
  // the real fetch was just scheduled — still loading, not empty.
  if (!state || state.includes("buscando") || state.includes("agendada") || state.includes("searching")) return "loading" as const;
  return "empty" as const;
}

export function WorkspaceNewsPanel({
  locale = "pt-BR",
  selectedTicker,
  newsRows,
  newsStateText,
  newsStatus,
  onRetry,
}: NewsPanelProps) {
  const isEnglish = locale === "en-US";
  const normalizedNewsState = normalizeText(newsStateText || "");
  const phase = newsPanelPhase(newsRows.length, newsStateText, newsStatus);
  const localizedNewsStateText =
    isEnglish && normalizedNewsState.includes("sem noticia") && normalizedNewsState.includes("reaproveitada")
      ? `No real news for ${selectedTicker} right now; no other ticker news was reused.`
      // Some backend states are still Portuguese-only; never leak them into the English path.
      : isEnglish && /[áâãàéêíóôõúüç]/i.test(String(newsStateText || ""))
        ? ""
        : newsStateText;
  const emptyNewsText = isEnglish
    ? `No news for ${selectedTicker} right now. Try refreshing later.`
    : `Sem notícia para ${selectedTicker} agora. Tente atualizar mais tarde.`;
  const loadingNewsText = isEnglish
    ? `Loading news for ${selectedTicker}...`
    : `Carregando notícias de ${selectedTicker}...`;
  const errorNewsText = isEnglish
    ? `Could not load the news for ${selectedTicker}.`
    : `Não foi possível carregar as notícias de ${selectedTicker}.`;
  const assistiveText = phase === "ready"
    ? `${newsRows.length} ${isEnglish ? `useful news items prepared for ${selectedTicker}.` : `notícias úteis preparadas para ${selectedTicker}.`}`
    : phase === "loading"
      ? loadingNewsText
      : phase === "error"
        ? errorNewsText
        : emptyNewsText;
  const retryButton = (
    <button
      type="button"
      className="snbr-button secondary"
      onClick={() => (onRetry ? onRetry() : window.location.reload())}
    >
      {isEnglish ? "Try again" : "Tentar novamente"}
    </button>
  );
  return (
    <section
      id="panel-news"
      className="snbr-news-panel"
      data-news-symbol={selectedTicker}
      data-news-state-count={newsRows.length}
      data-news-phase={phase}
      aria-busy={phase === "loading"}
    >
      <div className="snbr-plain-panel">
        <div className="snbr-section-head">
          <div>
            <h3>{isEnglish ? "News for" : "Notícias de"} {selectedTicker}</h3>
            <p>{isEnglish ? "Relevant ticker news, cleaned, deduplicated and prioritized for a quick read." : "Notícias relevantes do ativo, limpadas, deduplicadas e priorizadas para leitura rápida."}</p>
          </div>
        </div>
        <p className="snbr-assistive-copy" aria-live="polite">{assistiveText}</p>
        <div className="snbr-headline-list">
          {newsRows.map((item) => {
            const detailLines = uniqueNewsLines(item.headline, [
              item.title,
              item.cardSummary,
              item.traderTakeaway || "",
              item.whyItMatters || "",
              item.marketContext || "",
            ]);
            const impactTone = normalizeText(item.impact).includes("positive") || normalizeText(item.impact).includes("positivo")
              ? "positive"
              : normalizeText(item.impact).includes("negative") || normalizeText(item.impact).includes("negativo")
                ? "negative"
                : "neutral";
            const sentimentVisual = newsSentimentVisual(item.sentiment, locale);
            const sourceName = item.sourceName || item.source || (isEnglish ? "Unknown source" : "Fonte não informada");
            const sourceUrl = validExternalNewsUrl(item.sourceUrl || item.url || "");
            const itemUrl = validExternalNewsUrl(item.url || item.sourceUrl || "");
            const matchedSymbol = item.matchedSymbol || item.symbol;
            const staleStatus = newsFreshnessStatus(item, isEnglish);
            const incompleteStatus = item.isIncomplete
              ? (isEnglish ? "Incomplete news: source time missing" : "Notícia incompleta: sem hora da fonte")
              : null;

            return (
            <article
              key={item.id}
              className={cx("snbr-headline-row", "snbr-news-row", !item.useful && "noise")}
              data-news-card="true"
              data-news-symbol={item.symbol}
              data-news-source={sourceName}
              data-news-url={sourceUrl}
              data-news-published-source={item.publishedAtIso || ""}
              data-news-age-minutes={item.ageMinutes == null ? "" : String(item.ageMinutes)}
              data-news-freshness-bucket={item.freshnessBucket || ""}
              data-news-matched-symbol={matchedSymbol}
              data-news-stale={item.isStale ? "true" : "false"}
              data-news-incomplete={item.isIncomplete ? "true" : "false"}
            >
              <div className="snbr-news-copy">
                <div className="snbr-news-headline">
                  <strong>{item.headline}</strong>
                  <div className="snbr-news-impact-stack">
                    <span className={cx("snbr-news-impact", impactTone)}>
                      {item.impact} • {item.quality}
                    </span>
                    <span className={cx("snbr-news-sentiment", sentimentVisual.tone)}>
                      {sentimentVisual.icon} {sentimentVisual.label}
                    </span>
                    <small>{isEnglish ? "Published at" : "Publicado às"}: {item.publishedTime}</small>
                  </div>
                </div>
                {detailLines.map((line) => (
                  <div key={`${item.id}-${line}`} className="snbr-news-why">{line}</div>
                ))}
                <div className="snbr-news-meta-row">
                  <span>{isEnglish ? "Source" : "Fonte"}: {sourceName}</span>
                  <span>{isEnglish ? "Original URL" : "URL original"}: {sourceUrl || (isEnglish ? "real URL unavailable" : "URL real indisponível")}</span>
                  <span>{isEnglish ? "Published at source" : "Publicado em"}: {item.publishedTime}</span>
                  <span>{isEnglish ? "Age" : "Idade"}: {item.age}</span>
                  <span>Ticker: {matchedSymbol}</span>
                  {item.language ? <span>{isEnglish ? "Language" : "Idioma"}: {item.language}</span> : null}
                  <span>{staleStatus}</span>
                  {incompleteStatus ? <span>{incompleteStatus}</span> : null}
                  <span>{isEnglish ? "Sentiment" : "Sentimento"}: {sentimentVisual.icon} {sentimentVisual.label}</span>
                  {item.sector ? <span>{item.sector}</span> : null}
                  {item.industry ? <span>{item.industry}</span> : null}
                  {item.sameStoryCount > 1 ? <span>{item.sameStoryCount} {isEnglish ? "versions" : "versões"}</span> : null}
                  {item.sourceCount && item.sourceCount > 1 ? <span>{item.sourceCount} {isEnglish ? "sources" : "fontes"}</span> : null}
                  {item.relevanceScore != null ? <span>{Math.round(item.relevanceScore)} {isEnglish ? "rel." : "relev."}</span> : null}
                  {item.confidenceScore != null ? <span>{Math.round(item.confidenceScore)} conf.</span> : null}
                  {item.ambiguityScore != null && item.ambiguityScore >= 45 ? <span>{isEnglish ? "Ambiguous read" : "Leitura ambígua"}</span> : null}
                </div>
                {item.labels.length ? (
                  <div className="snbr-news-chip-row">
                    {item.labels.slice(0, 4).map((label) => (
                      <span key={`${item.id}-${label}`} className="snbr-news-chip">
                        {label}
                      </span>
                    ))}
                  </div>
                ) : null}
                {item.entities.length ? (
                  <div className="snbr-news-entity-row">
                    <span>{isEnglish ? "Entities" : "Entidades"}</span>
                    {item.entities.slice(0, 4).map((entity) => (
                      <span key={`${item.id}-${entity}`} className="snbr-news-entity-chip">
                        {entity}
                      </span>
                    ))}
                  </div>
                ) : null}
              </div>
              {itemUrl ? (
                <a
                  className="snbr-headline-symbol"
                  href={itemUrl}
                  rel="noreferrer"
                  target="_blank"
                  aria-label={isEnglish ? `Open external news: ${item.headline}` : `Abrir notícia externa: ${item.headline}`}
                >
                  {isEnglish ? "Open" : "Abrir"}
                </a>
              ) : (
                <span className="snbr-headline-symbol disabled">{isEnglish ? "Real URL unavailable" : "URL real indisponível"}</span>
              )}
            </article>
            );
          })}
          {phase === "loading" ? (
            <div className="snbr-empty-thread" data-news-skeleton="true">
              <strong>{loadingNewsText}</strong>
              {[0, 1, 2].map((row) => (
                <div key={`news-skeleton-${row}`} style={{ display: "grid", gap: 6, opacity: 0.5 }}>
                  <span style={{ display: "block", height: 12, width: "82%", borderRadius: 6, background: "var(--line)" }} />
                  <span style={{ display: "block", height: 10, width: "46%", borderRadius: 6, background: "var(--line)" }} />
                </div>
              ))}
              {retryButton}
            </div>
          ) : null}
          {phase === "error" ? (
            <div className="snbr-empty-thread" data-news-error="true">
              <strong>{errorNewsText}</strong>
              <p>{localizedNewsStateText || (isEnglish ? "The news feed did not answer. Try again in a moment." : "O feed de notícias não respondeu. Tente novamente em instantes.")}</p>
              {retryButton}
            </div>
          ) : null}
          {phase === "empty" ? (
            <div className="snbr-empty-thread">
              <strong>{emptyNewsText}</strong>
              <p>{localizedNewsStateText || (isEnglish ? "As soon as the ticker feed brings a useful headline, it appears here with source, original time and sentiment." : "Assim que o feed do ticker trouxer uma manchete útil, ela aparece aqui com fonte, horário original e sentimento.")}</p>
              {retryButton}
            </div>
          ) : null}
        </div>
      </div>

    </section>
  );
}

type EducationPanelProps = {
  locale?: AppLocale;
  institutionalSections: WorkspaceHelpSection[];
  guides: HelpGuide[];
  activeInstitutionalSectionId?: string | null;
};

export function WorkspaceEducationPanel({
  locale = "pt-BR",
  institutionalSections,
  guides,
  activeInstitutionalSectionId,
}: EducationPanelProps) {
  const isEnglish = locale === "en-US";
  const visibleInstitutionalSections = activeInstitutionalSectionId
    ? institutionalSections.filter((section) => section.id === activeInstitutionalSectionId)
    : [];

  return (
    <section id="panel-education" className="snbr-plain-panel">
      <div className="snbr-section-head">
        <div>
          <h3>{isEnglish ? "Trader Educational Help" : "Ajuda Educacional para o Trader"}</h3>
          <p>{isEnglish ? "Clear explanation of each platform module, focused on real daily trader use." : "Explicação clara de cada módulo da plataforma, com foco no uso real no dia a dia do trader."}</p>
        </div>
      </div>
      <div className="snbr-help-stack">
        {visibleInstitutionalSections.map((section) => (
          <article id={section.id} key={section.id || section.title} className="snbr-guide-card snbr-help-section">
            <h4>{section.title}</h4>
            <div className="snbr-help-body">
              {section.body.map((line) => (
                <p key={line}>{line}</p>
              ))}
            </div>
            {section.rows?.length ? (
              <div className="snbr-help-table-wrap">
                <table className="snbr-help-table">
                  <thead>
                    <tr>
                      <th>{isEnglish ? "Item" : "Item"}</th>
                      <th>{isEnglish ? "Easy explanation" : "Explicação Fácil"}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {section.rows.map((row) => (
                      <tr key={row.item}>
                        <td>{row.item}</td>
                        <td>{row.explanation}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : null}
          </article>
        ))}

        {!activeInstitutionalSectionId && !visibleInstitutionalSections.length ? (
          <article className="snbr-guide-card snbr-help-section">
            <h4>{isEnglish ? "Choose an institutional section" : "Escolha uma seção institucional"}</h4>
            <div className="snbr-help-body">
              <p>{isEnglish ? "Click a numbered item in the left rail to open only that subject box." : "Clique em um item numerado na lateral esquerda para abrir somente a caixa daquele assunto."}</p>
            </div>
          </article>
        ) : null}

        {guides.map((guide) => (
          <article key={guide.slug} className="snbr-guide-card snbr-help-section">
            <h4>{isEnglish ? helpTextEn(guide.title) : guide.title}</h4>
            <div className="snbr-help-body">
              <p>{isEnglish ? helpTextEn(guide.tagline || guide.description) : (guide.tagline || guide.description)}</p>
            </div>
            <div className="snbr-guide-meta">
              <span>Video: {guide.video_status || "preview"}</span>
              <span>{guide.mp4_url ? (isEnglish ? "MP4 ready" : "MP4 pronto") : (isEnglish ? "Script ready" : "Roteiro pronto")}</span>
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}
