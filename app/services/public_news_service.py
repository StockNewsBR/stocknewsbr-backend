import re
from datetime import datetime, timezone
from typing import Any
from urllib.parse import unquote, urlparse
from zoneinfo import ZoneInfo

from app.services.symbol_registry import canonical_symbol, symbol_category
from app.services.news_service import (
    _TICKER_NEWS_ALIASES as _SYMBOL_NEWS_ALIASES,
    NEWS_CACHE_TTL_SECONDS,
    get_cached_symbol_news,
    get_news_cache_info,
    get_news_cached_report,
    get_symbol_news,
    normalize_news_locale,
)

_NEWS_LOCAL_TZ = ZoneInfo("America/Sao_Paulo")
_TITLE_TOKEN_STOPWORDS = {"AI", "CEO", "CFO", "IPO", "ETF", "EV", "US", "UK", "F1", "S&P", "DJIA"}
_FORBIDDEN_NEWS_HOSTS = {
    "example.com",
    "www.example.com",
    "localhost",
    "127.0.0.1",
    "0.0.0.0",
}
_FORBIDDEN_NEWS_URL_MARKERS = ("mock", "fake", "placeholder")


def _normalize_symbol(symbol: str | None) -> str:
    return canonical_symbol(symbol)


def _news_item_symbol(item: dict[str, Any]) -> str:
    return _normalize_symbol(str(item.get("ticker") or item.get("symbol") or ""))


def _symbol_news_aliases(symbol: str) -> set[str]:
    normalized = _normalize_symbol(symbol)
    aliases = {normalized}
    aliases.update(_SYMBOL_NEWS_ALIASES.get(normalized, ()))
    return {_normalize_news_text(alias) for alias in aliases if alias}


def _text_has_news_alias(text: str, alias: str) -> bool:
    normalized_alias = _normalize_news_text(alias)
    if not normalized_alias:
        return False
    return bool(re.search(rf"\b{re.escape(normalized_alias)}\b", text))


def _title_has_symbol_alias(item: dict[str, Any], symbol: str) -> bool:
    title = _normalize_news_text(item.get("title") or item.get("headline") or "")
    return any(_text_has_news_alias(title, alias) for alias in _symbol_news_aliases(symbol))


def _title_mentions_other_symbol_without_requested_alias(item: dict[str, Any], symbol: str) -> bool:
    raw_title = str(item.get("title") or item.get("headline") or "")
    title = _normalize_news_text(raw_title)
    if not title or _title_has_symbol_alias(item, symbol):
        return False
    normalized = _normalize_symbol(symbol)
    for token in re.findall(r"\b[A-Z]{2,6}\d{0,2}\b", raw_title):
        if token in _TITLE_TOKEN_STOPWORDS:
            continue
        token_symbol = _normalize_symbol(token)
        if token_symbol and token_symbol != normalized and _normalize_news_text(token_symbol) not in _symbol_news_aliases(normalized):
            return True
    for candidate, aliases in _SYMBOL_NEWS_ALIASES.items():
        if candidate == normalized:
            continue
        # Only company names here: the bare ticker is already covered by the uppercase
        # token scan above, and matching it as free text blocks unrelated headlines
        # (COST -> "cost", BULL -> "bull market").
        if any(_text_has_news_alias(title, alias) for alias in aliases):
            return True
    return False


def _item_belongs_to_symbol(item: dict[str, Any], symbol: str) -> bool:
    normalized = _normalize_symbol(symbol)
    if _title_mentions_other_symbol_without_requested_alias(item, normalized):
        return False
    item_symbol = _news_item_symbol(item)
    if item_symbol and item_symbol == normalized:
        return True

    # "entities" is seeded upstream with the ticker the item was filed under, so it can
    # never prove relatedness -- using it here made this whole filter a no-op and let the
    # generic provider feed render as per-symbol news. Only provider-supplied related
    # tickers count.
    related = item.get("related_tickers") or item.get("relatedTickers") or []
    if isinstance(related, list):
        normalized_related: set[str] = set()
        for value in related:
            if isinstance(value, dict):
                normalized_related.add(_normalize_symbol(value.get("ticker") or value.get("symbol") or value.get("name")))
            else:
                normalized_related.add(_normalize_symbol(str(value)))
        if normalized in normalized_related:
            return True

    # Last resort: the article itself must name the ticker or the company. Generated
    # commentary fields are excluded -- they always mention the requested ticker.
    parts = (
        item.get("title"),
        item.get("original_title"),
        item.get("headline"),
        item.get("summary"),
        item.get("original_summary"),
        item.get("card_summary"),
    )
    text = _normalize_news_text(" ".join(str(part or "") for part in parts))
    return any(_text_has_news_alias(text, alias) for alias in _symbol_news_aliases(normalized))


def _normalize_news_text(value: Any) -> str:
    text = str(value or "").lower().strip()
    text = re.sub(r"https?://\S+", "", text)
    text = re.sub(r"[^a-z0-9\u00c0-\u024f]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _valid_external_news_url(value: Any) -> bool:
    text = str(value or "").strip()
    if not text:
        return False
    try:
        parsed = urlparse(text)
    except Exception:
        return False
    if parsed.scheme not in {"http", "https"}:
        return False
    host = str(parsed.netloc or "").split("@")[-1].split(":")[0].lower().strip()
    if not host or "." not in host or host in _FORBIDDEN_NEWS_HOSTS:
        return False
    normalized = text.lower()
    return not any(marker in normalized for marker in _FORBIDDEN_NEWS_URL_MARKERS)


def _sanitize_news_url(value: Any) -> str | None:
    text = str(value or "").strip()
    return text if _valid_external_news_url(text) else None


def _iso_from_news_epoch(epoch: float) -> str | None:
    if not epoch:
        return None
    try:
        return datetime.fromtimestamp(float(epoch), tz=timezone.utc).isoformat()
    except Exception:
        return None


def _local_iso_from_news_epoch(epoch: float) -> str | None:
    if not epoch:
        return None
    try:
        return datetime.fromtimestamp(float(epoch), tz=timezone.utc).astimezone(_NEWS_LOCAL_TZ).isoformat()
    except Exception:
        return None


def _public_news_age_minutes(epoch: float) -> int | None:
    if not epoch:
        return None
    try:
        now = datetime.now(timezone.utc).timestamp()
        return max(0, int((now - float(epoch)) // 60))
    except Exception:
        return None


def _public_news_is_today(epoch: float) -> bool:
    if not epoch:
        return False
    try:
        published = datetime.fromtimestamp(float(epoch), tz=timezone.utc).astimezone(_NEWS_LOCAL_TZ)
        current = datetime.now(timezone.utc).astimezone(_NEWS_LOCAL_TZ)
        return published.date() == current.date()
    except Exception:
        return False


def _public_news_freshness_bucket(epoch: float, age_minutes: int | None, is_today: bool) -> tuple[str, str]:
    if is_today:
        return "today", "Notícia de hoje"
    if age_minutes is None and epoch:
        age_minutes = _public_news_age_minutes(epoch)
    if age_minutes is None:
        return "unknown", "Data da fonte indisponível"
    if age_minutes < 48 * 60:
        return "yesterday", "Notícia anterior / Ontem"
    if age_minutes <= 7 * 24 * 60:
        return "2_7_days", "Notícia anterior / 2-7 dias"
    return "older_7_days", "Notícia antiga / 7+ dias"


def _public_news_language(item: dict[str, Any]) -> str:
    text = _normalize_news_text(" ".join(str(item.get(field) or "") for field in ("title", "headline", "summary", "card_summary")))
    if re.search(r"\b(acao|acoes|noticia|mercado|lucro|receita|resultado|banco|petroleo|juros|empresa)\b", text):
        return "pt-BR"
    return "en-US"


def _is_generic_news_title(title: Any, ticker: str) -> bool:
    normalized = _normalize_news_text(title)
    symbol = _normalize_news_text(ticker)
    return normalized in {
        f"manchete internacional sobre {symbol}",
        f"international headline about {symbol}",
        f"headline about {symbol}",
        f"noticia sobre {symbol}",
        f"news about {symbol}",
    }


def _headline_from_url(url: Any) -> str:
    text = str(url or "").strip()
    if not text:
        return ""
    try:
        slug = text.split("?", 1)[0].split("#", 1)[0].rstrip("/").rsplit("/", 1)[-1]
        slug = re.sub(r"\.(html?|php)$", "", slug, flags=re.IGNORECASE)
        slug = unquote(slug)
        slug = re.sub(r"[-_]+", " ", slug)
        slug = re.sub(r"\s+", " ", slug).strip()
        if not slug or re.fullmatch(r"\d+", slug):
            return ""
        return slug[:1].upper() + slug[1:]
    except Exception:
        return ""


def _fix_portuguese_news_text(value: Any) -> Any:
    if not isinstance(value, str) or not value:
        return value
    replacements = {
        "ambigua": "ambígua",
        "Ambigua": "Ambígua",
        "confirmacao": "confirmação",
        "Confirmacao": "Confirmação",
        "nao ": "não ",
        "Nao ": "Não ",
        "noticia": "notícia",
        "Noticia": "Notícia",
        "Petroleo": "Petróleo",
        "petroleo": "petróleo",
    }
    text = value
    for source, target in replacements.items():
        text = text.replace(source, target)
    return text


# Frequent English words with no Portuguese homograph. Used to detect leftovers AFTER the
# replacement table ran: if any survives, the table only translated part of the sentence and
# the result would be franken-text ("Why the mercado Dipped But Petrobras Gained Today").
# Deliberately excludes PT homographs ("a", "o", "e", "as", "no", "da", "de", "do").
_ENGLISH_RESIDUE_RE = re.compile(
    r"\b("
    r"the|of|to|in|is|are|was|were|be|been|being|has|have|had|will|would|should|could|"
    r"it|its|but|not|and|for|from|with|by|that|this|these|those|there|their|they|"
    r"why|how|what|when|where|which|who|whose|after|before|amid|about|against|between|"
    r"today|yesterday|tomorrow|week|month|year|quarter|day|days|"
    r"said|says|say|report|reports|reported|expects?|expected|sees?|seen|"
    r"up|down|higher|lower|gain|gains|gained|dip|dips|dipped|rise|rises|rose|risen|"
    r"fall|falls|fell|fallen|jump|jumps|jumped|drop|drops|dropped|beat|beats|"
    r"miss|misses|missed|deal|deals|plan|plans|new|top|best|worst|more|less|than"
    r")\b"
)


def _has_english_residue(value: str) -> bool:
    return bool(_ENGLISH_RESIDUE_RE.search(_normalize_news_text(value)))


def _looks_like_english_news(value: str) -> bool:
    normalized = _normalize_news_text(value)
    return bool(
        normalized
        and re.search(
            r"\b(results?|improves?|benefits?|stronger|pricing|earnings?|shares?|stocks?|market|reads?|supportive|variant|live|guidance|revenue|profit|oil|trader|wait|price|volume|confirmation|from|with|as)\b",
            normalized,
        )
    )


# Fields whose text is the article's own words (the summary falls back to the headline when
# the provider sends none). They are never rewritten into generic copy and never half-swapped
# -- the reader either gets the publisher's sentence or nothing invented in its place.
_ARTICLE_TEXT_FIELDS = frozenset({"summary", "card_summary"})


def _translate_english_news_text(value: Any, ticker: str, field: str) -> Any:
    if not isinstance(value, str) or not value.strip():
        return value

    text = _fix_portuguese_news_text(value.strip())
    if not _looks_like_english_news(text):
        return text

    # Article text (summary/card_summary) is the publisher's own sentence. The word-by-word
    # regex table below only half-translates a proper-noun-heavy headline ("Goldman Sachs and
    # Other" -> "Goldman Sachs e Other") and _has_english_residue misses hybrids like that. Per
    # this field's contract, return it as published; language/content_locale mark it for the UI.
    if field in _ARTICLE_TEXT_FIELDS:
        return text

    normalized = re.sub(r"\s+", " ", text.replace("’", "'")).strip()
    oil_result = re.match(r"^(.+?)\s+results?\s+improves?\s+as\s+(.+?)\s+benefits?\s+from\s+stronger\s+oil\s+pricing$", normalized, flags=re.IGNORECASE)
    if oil_result:
        return f"Resultados de {oil_result.group(1)} melhoram com {oil_result.group(2)} beneficiada por petróleo mais forte"

    replacements = [
        (r"\bresults?\s+improves?\b", "resultados melhoram"),
        (r"\bbenefits?\s+from\b", "se beneficia de"),
        (r"\bstronger\s+oil\s+pricing\b", "petróleo mais forte"),
        (r"\boil\s+pricing\b", "preços do petróleo"),
        (r"\bmarket\s+reads?\b", "mercado lê"),
        (r"\breads?\b", "lê"),
        (r"\bsupportive\b", "favorável"),
        (r"\bthe\s+B3\s+variant\b", "a versão B3"),
        (r"\bB3\s+variant\b", "versão B3"),
        (r"\blive\b", "dado ao vivo"),
        (r"\bearnings?\b", "resultados"),
        (r"\bguidance\b", "projeções"),
        (r"\brevenue\b", "receita"),
        (r"\bprofit\b", "lucro"),
        (r"\btrader\s+note:?\b", "Para trader:"),
        (r"\bwait\b", "aguarde"),
        (r"\bprice\b", "preço"),
        (r"\bvolume\b", "volume"),
        (r"\bconfirmation\b", "confirmação"),
        (r"\bshares?\b", "ações"),
        (r"\bstocks?\b", "ações"),
        (r"\bmarket\b", "mercado"),
        (r"\bpricing\b", "precificação"),
        (r"\bstronger\b", "mais forte"),
        (r"\bfrom\b", "de"),
        (r"\bwith\b", "com"),
        (r"\bas\b", "com"),
        (r"\band\b", "e"),
    ]
    translated = normalized
    for source, target in replacements:
        translated = re.sub(source, target, translated, flags=re.IGNORECASE)

    translated = _fix_portuguese_news_text(translated)
    if _has_english_residue(translated):
        # The table only covers a handful of finance phrases, so a sentence it cannot render
        # end-to-end comes out as the hybrid the feed was shipping ("Why the mercado Dipped
        # But Petrobras Gained Today"). Article text keeps the publisher's original wording
        # -- `language` on the item tells the UI it is not in the requested locale. Our own
        # generated commentary can safely fall back to generic localized copy instead.
        if field in _ARTICLE_TEXT_FIELDS:
            return text
        return f"Leitura relevante para {ticker}; confirme impacto em preço, volume e contexto setorial antes de agir."

    return translated[:1].upper() + translated[1:]


def _normalize_public_news_item(item: dict[str, Any], ticker: str, locale: str) -> dict[str, Any]:
    normalized = dict(item)
    title = normalized.get("title") or normalized.get("headline")
    normalized["original_title"] = normalized.get("original_title") or title
    normalized["content_locale"] = normalize_news_locale(locale)
    if _is_generic_news_title(title, ticker):
        url_title = _headline_from_url(normalized.get("url"))
        if url_title:
            normalized["title"] = url_title
            normalized["headline"] = url_title
    # Headline fields are absent on purpose: a headline is either shown as published or not
    # at all. Everything here is generated commentary that the table can render end-to-end.
    for field in ("summary", "card_summary", "impact_reason", "why_it_matters", "editorial", "market_context", "trader_takeaway", "sector", "industry"):
        if field in normalized and normalized["content_locale"] == "pt-BR":
            normalized[field] = _translate_english_news_text(normalized.get(field), ticker, field)
    return normalized


def _news_dedupe_key(item: dict[str, Any]) -> str:
    story_key = _normalize_news_text(item.get("story_key"))
    if story_key:
        return f"story:{story_key}"

    url = str(item.get("url") or "").strip().lower()
    if url:
        return f"url:{url.split('#', 1)[0].split('?', 1)[0].rstrip('/')}"

    for field in ("title", "trader_takeaway", "card_summary", "summary"):
        text = _normalize_news_text(item.get(field))
        if text:
            return f"text:{text[:180]}"

    return f"id:{item.get('id') or id(item)}"


def _dedupe_news_items(items: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    unique_items: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in items:
        key = _news_dedupe_key(item)
        if key in seen:
            continue
        seen.add(key)
        unique_items.append(item)
        if len(unique_items) >= limit:
            break
    return unique_items


def _news_timestamp_epoch(item: dict[str, Any]) -> float:
    candidates = (
        item.get("published_at_source"),
        item.get("published_at"),
        item.get("provider_publish_time"),
        item.get("providerPublishTime"),
        item.get("pubDate"),
        item.get("publishedAt"),
        item.get("displayTime"),
        (item.get("content") or {}).get("providerPublishTime") if isinstance(item.get("content"), dict) else None,
        (item.get("content") or {}).get("pubDate") if isinstance(item.get("content"), dict) else None,
        (item.get("content") or {}).get("publishedAt") if isinstance(item.get("content"), dict) else None,
        (item.get("content") or {}).get("displayTime") if isinstance(item.get("content"), dict) else None,
    )
    for value in candidates:
        if value in (None, ""):
            continue
        try:
            if isinstance(value, (int, float)):
                timestamp = float(value)
                if timestamp > 10_000_000_000:
                    timestamp /= 1000.0
                return timestamp
            text = str(value).strip()
            if not text:
                continue
            numeric = float(text) if re.fullmatch(r"\d+(\.\d+)?", text) else None
            if numeric is not None:
                if numeric > 10_000_000_000:
                    numeric /= 1000.0
                return numeric
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.timestamp()
        except Exception:
            continue
    return 0.0


def _enrich_public_news_item(item: dict[str, Any], ticker: str) -> dict[str, Any]:
    normalized = dict(item)
    epoch = _news_timestamp_epoch(normalized)
    published_at_source = normalized.get("published_at_source") or _iso_from_news_epoch(epoch)
    source_name = normalized.get("source_name") or normalized.get("source") or "Yahoo Finance"
    source_url = _sanitize_news_url(normalized.get("source_url") or normalized.get("url"))
    fetched_at = normalized.get("fetched_at") or normalized.get("detected_at")
    # Always recomputed from the article's own publication time. These are derived from
    # now(), so the values frozen into the cache at ingestion made day-old items keep
    # reporting "Notícia de hoje" and their original age forever.
    age_minutes = _public_news_age_minutes(epoch)
    is_today = _public_news_is_today(epoch)
    is_stale = not is_today
    freshness_bucket, freshness_label = _public_news_freshness_bucket(epoch, age_minutes, is_today)

    normalized["source"] = source_name
    normalized["source_name"] = source_name
    normalized["source_url"] = source_url
    normalized["url"] = source_url
    normalized["published_at_source"] = published_at_source
    normalized["published_at"] = normalized.get("published_at") or published_at_source
    # Same instant in the app's display timezone, offset included, so the UI renders the
    # article's own publication time without re-deriving it from a bare UTC string.
    local_published = _local_iso_from_news_epoch(epoch)
    normalized["published_at_local"] = local_published
    normalized["published_at_tz"] = str(_NEWS_LOCAL_TZ) if local_published else None
    normalized["fetched_at"] = fetched_at
    normalized["age_minutes"] = age_minutes
    normalized["is_today"] = bool(is_today)
    normalized["is_stale"] = bool(is_stale)
    normalized["freshness_bucket"] = freshness_bucket
    normalized["freshness_label"] = freshness_label
    normalized["matched_symbol"] = _normalize_symbol(normalized.get("matched_symbol") or ticker)
    normalized["language"] = normalized.get("language") or _public_news_language(normalized)
    normalized["publication_status"] = (
        "missing_source_url"
        if not source_url
        else "missing_source_time"
        if not published_at_source
        else normalized.get("publication_status") or "ok"
    )
    normalized["is_incomplete"] = bool(normalized.get("is_incomplete") or not published_at_source or not source_name or not source_url)
    normalized["relevance"] = normalized.get("relevance") if normalized.get("relevance") is not None else normalized.get("relevance_score")
    return normalized


def _request_news_warmup_safe(symbol: str, limit: int, locale: str = "pt-BR") -> bool:
    try:
        from app.system.news_warmup import request_news_warmup

        request_news_warmup(symbol, limit=limit, locale=locale)
        return True
    except Exception:
        return False


def _build_news_state(
    symbol: str,
    items: list[dict[str, Any]],
    cache: dict[str, Any],
    report: dict[str, Any],
    *,
    warmup_requested: bool = False,
    locale: str = "pt-BR",
) -> dict[str, Any]:
    is_english = normalize_news_locale(locale) == "en-US"
    cache_status = str(cache.get("status") or "cold")
    provider_status = str(cache.get("provider_status") or "not_checked")
    provider_error = cache.get("provider_error")
    raw_count = int(cache.get("raw_count", 0) or 0)
    filter_report = cache.get("filter_report") if isinstance(cache.get("filter_report"), dict) else {}
    discard_reason = cache.get("discard_reason") or filter_report.get("reason")
    is_crypto = symbol_category(symbol) == "Crypto"
    fresh_items = [item for item in items if isinstance(item, dict) and not bool(item.get("is_stale"))]
    state_reason = discard_reason

    if items:
        status = "ok"
        message = f"NEWS FOUND: {len(items)} validated item(s) for {symbol}." if is_english else f"NOTÍCIAS ENCONTRADAS: {len(items)} notícia(s) real(is) validada(s) para {symbol}."
        if cache_status == "stale_fallback":
            status = "stale_fallback"
            message = f"CACHE ANTIGO: usando notícia anterior de {symbol}; provider atual não entregou item novo."
        if not fresh_items:
            status = "historical"
            state_reason = "no_fresh_crypto_news" if is_crypto else "no_fresh_news"
            message = (
                f"HISTORICAL NEWS: no current validated item for {symbol}."
                if is_english
                else f"HISTÓRICO: nenhuma notícia atual validada para {symbol}."
            )
    else:
        status = "empty"
        message = f"NO VERIFIED NEWS NOW: no item from another ticker was reused for {symbol}." if is_english else f"SEM NOTÍCIA REAL AGORA: Sem notícia real para {symbol} agora; nenhuma notícia de outro ticker foi reaproveitada."
        if provider_error:
            status = "provider_error"
            message = f"PROVIDER INDISPONÍVEL: provider de news falhou para {symbol}: {provider_error}."
        elif is_crypto and provider_status in {"empty", "empty_response", "no_news", "unsupported"}:
            status = "unsupported"
            state_reason = "crypto_news_provider_unavailable"
            message = (
                f"RECENT NEWS UNAVAILABLE: the provider has no current coverage for {symbol}."
                if is_english
                else f"NOTÍCIAS RECENTES INDISPONÍVEIS: o provider não possui cobertura atual para {symbol}."
            )
        elif raw_count > 0 and discard_reason:
            status = "empty"
            message = f"FILTROS REMOVERAM TODAS AS NOTÍCIAS: {raw_count} notícia(s) bruta(s) para {symbol}; motivo: {discard_reason}."
        elif provider_status in {"empty", "no_news", "error"}:
            message = f"TICKER SEM COBERTURA: provider retornou {provider_status} para {symbol}; tela deve mostrar estado vazio explícito."
        elif warmup_requested:
            message = f"BUSCANDO NOTÍCIAS: busca real para {symbol} foi agendada; tente atualizar em instantes."

    return {
        "symbol": symbol,
        "status": status,
        "message": message,
        "cache_status": cache_status,
        "provider": cache.get("provider") or "yfinance",
        "provider_status": provider_status,
        "provider_error": provider_error,
        "raw_count": raw_count,
        "reason": state_reason,
        "discard_reasons": cache.get("discard_reasons") if isinstance(cache.get("discard_reasons"), dict) else {},
        "report_status": report.get("status") or ("ok" if items else "empty"),
        "items": len(items),
        "fresh_items": len(fresh_items),
        "warmup_requested": warmup_requested,
    }


def build_public_news_payload(
    symbol: str,
    limit: int = 6,
    source: str | None = None,
    allow_fetch: bool = False,
    schedule_warmup: bool = False,
    locale: str = "pt-BR",
) -> dict:
    ticker = _normalize_symbol(symbol)
    content_locale = normalize_news_locale(locale)
    safe_limit = max(1, min(int(limit or 6), 20))
    cached_items = get_cached_symbol_news(ticker, limit=safe_limit, locale=content_locale)
    # A full cache is not a fresh cache. Refreshing only when the cache was SHORT meant a
    # symbol that once returned `limit` items never asked for new ones again, so the feed
    # froze on whatever was fetched first. get_symbol_news() is itself TTL-guarded, so this
    # costs at most one provider call per symbol per NEWS_CACHE_TTL_SECONDS.
    cache_age_seconds = get_news_cache_info(ticker, locale=content_locale).get("age_seconds")
    needs_refresh = len(cached_items) < safe_limit or (
        cache_age_seconds is not None and cache_age_seconds >= NEWS_CACHE_TTL_SECONDS
    )
    fetched_items = cached_items
    if allow_fetch and needs_refresh:
        fetched_items = get_symbol_news(ticker, limit=safe_limit, locale=content_locale)
    warmup_requested = False
    if not allow_fetch and schedule_warmup and needs_refresh:
        warmup_requested = (
            _request_news_warmup_safe(ticker, safe_limit)
            if content_locale == "pt-BR"
            else _request_news_warmup_safe(ticker, safe_limit, content_locale)
        )
    normalized_items = [
        _enrich_public_news_item(_normalize_public_news_item(item, ticker, content_locale), ticker)
        for item in fetched_items
        if isinstance(item, dict)
    ]
    scoped_items = [item for item in normalized_items if _item_belongs_to_symbol(item, ticker)]
    scoped_items = sorted(scoped_items, key=_news_timestamp_epoch, reverse=True)
    items = _dedupe_news_items(scoped_items, safe_limit)
    report = get_news_cached_report(ticker, items, locale=content_locale)
    cache = get_news_cache_info(ticker, locale=content_locale)
    state = _build_news_state(ticker, items, cache, report, warmup_requested=warmup_requested, locale=content_locale)
    payload = {
        "symbol": ticker,
        "locale": content_locale,
        "requested_symbol": str(symbol or "").upper().strip(),
        "items": items,
        "count": len(items),
        "status": state["status"],
        "reason": state.get("reason"),
        "state": state,
        "message": state["message"],
        "scope": {
            "type": "ticker",
            "symbol": ticker,
            "mixed_ticker_allowed": False,
            "filtered_out": max(0, len(fetched_items) - len(scoped_items)),
            "duplicates_removed": max(0, len(scoped_items) - len(items)),
        },
        "report": report,
        "cache": cache,
        "cache_only": not allow_fetch,
        "warmup_requested": warmup_requested,
        "data_status": (
            "READY" if state["status"] == "ok" else
            "HISTORICAL" if state["status"] == "historical" else
            "STALE" if state["status"] == "stale_fallback" else
            "UNSUPPORTED" if state["status"] == "unsupported" else
            "PROVIDER_ERROR" if state["status"] == "provider_error" else
            "REFRESHING" if warmup_requested else
            "EMPTY"
        ),
    }
    if source:
        payload["source"] = source
    return payload
