"use client";

import type { ReactNode } from "react";

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
  age: string;
  publishedTime: string;
  sector: string;
  industry: string;
  labels: string[];
  entities: string[];
  impact: string;
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

export type WorkspaceHelpSection = {
  id?: string;
  label?: string;
  title: string;
  body: string[];
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
  featuredDiscussion: ReactNode;
  newsStateText?: string | null;
  discussionStateText?: string | null;
};

export function WorkspaceNewsPanel({
  locale = "pt-BR",
  selectedTicker,
  newsRows,
  featuredDiscussion,
  newsStateText,
  discussionStateText,
}: NewsPanelProps) {
  const isEnglish = locale === "en-US";
  return (
    <section id="panel-news" className="snbr-two-column">
      <div className="snbr-plain-panel">
        <div className="snbr-section-head">
          <div>
            <h3>{isEnglish ? "News for" : "Notícias de"} {selectedTicker}</h3>
            <p>{isEnglish ? "Relevant ticker news, cleaned, deduplicated and prioritized for a quick read." : "Notícias relevantes do ativo, limpadas, deduplicadas e priorizadas para leitura rápida."}</p>
          </div>
        </div>
        <p className="snbr-assistive-copy" aria-live="polite">
          {newsRows.length
            ? `${newsRows.length} ${isEnglish ? `useful news items prepared for ${selectedTicker}.` : `notícias úteis preparadas para ${selectedTicker}.`}`
            : newsStateText || (isEnglish ? `No relevant news available for ${selectedTicker} right now.` : `Sem notícias relevantes disponíveis para ${selectedTicker} agora.`)}
        </p>
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

            return (
            <article key={item.id} className={cx("snbr-headline-row", "snbr-news-row", !item.useful && "noise")}>
              <div className="snbr-news-copy">
                <div className="snbr-news-headline">
                  <strong>{item.headline}</strong>
                  <div className="snbr-news-impact-stack">
                    <span className={cx("snbr-news-impact", impactTone)}>
                      {item.impact} • {item.quality}
                    </span>
                    <small>{item.publishedTime}</small>
                  </div>
                </div>
                {detailLines.map((line) => (
                  <div key={`${item.id}-${line}`} className="snbr-news-why">{line}</div>
                ))}
                <div className="snbr-news-meta-row">
                  <span>{item.source} • {item.age}</span>
                  {item.sector ? <span>{item.sector}</span> : null}
                  {item.industry ? <span>{item.industry}</span> : null}
                  {item.sameStoryCount > 1 ? <span>{item.sameStoryCount} {isEnglish ? "versions" : "versoes"}</span> : null}
                  {item.sourceCount && item.sourceCount > 1 ? <span>{item.sourceCount} {isEnglish ? "sources" : "fontes"}</span> : null}
                  {item.relevanceScore != null ? <span>{Math.round(item.relevanceScore)} {isEnglish ? "rel." : "relev."}</span> : null}
                  {item.confidenceScore != null ? <span>{Math.round(item.confidenceScore)} conf.</span> : null}
                  {item.ambiguityScore != null && item.ambiguityScore >= 45 ? <span>{isEnglish ? "Ambiguous read" : "Leitura ambigua"}</span> : null}
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
              {item.url ? (
                <a
                  className="snbr-headline-symbol"
                  href={item.url}
                  rel="noreferrer"
                  target="_blank"
                  aria-label={isEnglish ? `Open external news: ${item.headline}` : `Abrir notícia externa: ${item.headline}`}
                >
                  {isEnglish ? "Open" : "Abrir"}
                </a>
              ) : (
                <span className="snbr-headline-symbol">{item.symbol}</span>
              )}
            </article>
            );
          })}
          {!newsRows.length ? (
            <div className="snbr-empty-thread">
              <strong>{isEnglish ? "No real news available right now." : "Sem notícias reais disponíveis agora."}</strong>
              <p>{newsStateText || (isEnglish ? "As soon as the ticker feed brings a useful headline, it appears here with a trader-ready read." : "Assim que o feed do ticker trouxer uma manchete útil, ela aparece aqui com leitura pronta para trader.")}</p>
            </div>
          ) : null}
        </div>
      </div>

      <div className="snbr-plain-panel">
        <div className="snbr-section-head">
          <div>
            <h3>{isEnglish ? "Featured Discussions" : "Discussões em destaque"}</h3>
            <p>{isEnglish ? "The most active ticker conversations and posts driving screen sentiment." : "As conversas mais ativas do ticker e os posts que mais puxam o sentimento da tela."}</p>
          </div>
        </div>
        {discussionStateText ? <p className="snbr-assistive-copy" aria-live="polite">{discussionStateText}</p> : null}
        {featuredDiscussion}
      </div>
    </section>
  );
}

type EducationPanelProps = {
  locale?: AppLocale;
  helpManualItems: string[];
  institutionalSections: WorkspaceHelpSection[];
  educationalSections: WorkspaceHelpSection[];
  guides: HelpGuide[];
  activeInstitutionalSectionId?: string | null;
};

export function WorkspaceEducationPanel({
  locale = "pt-BR",
  helpManualItems,
  institutionalSections,
  educationalSections,
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
          <h3>{isEnglish ? "Trader Help" : "Ajuda Educacional para o Trader"}</h3>
          <p>{isEnglish ? "Clear explanation of each platform module, focused on real daily trader use." : "Explicacao clara de cada modulo da plataforma, com foco no uso real no dia a dia do trader."}</p>
        </div>
      </div>
      <div className="snbr-help-stack">
        <article className="snbr-guide-card">
          <h4>{isEnglish ? "🚀 Main Platform Modules" : "🚀 Principais Módulos da Plataforma"}</h4>
          <ul className="snbr-bullet-list">
            {helpManualItems.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </article>

        {visibleInstitutionalSections.map((section) => (
          <article id={section.id} key={section.id || section.title} className="snbr-guide-card snbr-help-section">
            <h4>{section.title}</h4>
            <div className="snbr-help-body">
              {section.body.map((line) => (
                <p key={line}>{line}</p>
              ))}
            </div>
          </article>
        ))}

        {!visibleInstitutionalSections.length ? (
          <article className="snbr-guide-card snbr-help-section">
            <h4>{isEnglish ? "Choose an institutional section" : "Escolha uma seção institucional"}</h4>
            <div className="snbr-help-body">
              <p>{isEnglish ? "Click a numbered item in the left rail to open only that subject box." : "Clique em um item numerado na lateral esquerda para abrir somente a caixa daquele assunto."}</p>
            </div>
          </article>
        ) : null}

        {educationalSections.map((section) => (
          <article key={section.title} className="snbr-guide-card snbr-help-section">
            <h4>{section.title}</h4>
            <div className="snbr-help-body">
              {section.body.map((line) => (
                <p key={line}>{line}</p>
              ))}
            </div>
          </article>
        ))}

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
