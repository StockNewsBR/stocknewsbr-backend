from __future__ import annotations

import copy
import hashlib
import logging
import os
import re
import threading
import time
import unicodedata
from collections import Counter
from datetime import datetime, timezone
from difflib import SequenceMatcher
from functools import lru_cache
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from app.core.atomic_io import interprocess_file_lock, read_json_file_consistent, write_json_file_atomic
from app.services.symbol_registry import canonical_symbol, canonical_symbol_aliases, provider_symbol
from app.system.system_metrics import record_cache_access, record_cache_lookup, record_external_provider_call, record_worker_stage_duration

logger = logging.getLogger("stocknewsbr.news")
_YFINANCE = None

_CACHE_LOCK = threading.Lock()
_PERSIST_LOCK = threading.Lock()
_REQUEST_LOCKS_LOCK = threading.Lock()
_CACHE_TTL_SECONDS = 300
# Public alias: callers outside this module need the same freshness threshold to decide
# when a cached entry must be refreshed instead of served as-is.
NEWS_CACHE_TTL_SECONDS = _CACHE_TTL_SECONDS
_NEWS_MAX_INPUT_ITEMS = 80
_NEWS_MAX_CLUSTER_CANDIDATES = 12
_NEWS_CACHE: dict[str, dict[str, Any]] = {}
_NEWS_PROVIDER_STATUS: dict[str, dict[str, Any]] = {}
_REQUEST_LOCKS: dict[str, threading.Lock] = {}
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_TICKER_NEWS_ALIASES = {
    "F": ("ford", "ford motor", "ford motor company"),
    "AAPL": ("apple", "apple inc"),
    "NVDA": ("nvidia", "nvidia corp", "nvidia corporation"),
    "TSLA": ("tesla", "tesla inc"),
    "MSFT": ("microsoft", "microsoft corp", "microsoft corporation"),
    "AMD": ("advanced micro devices",),
    "AMZN": ("amazon", "amazon.com", "amazon com", "amazon.com inc"),
    "META": ("meta", "meta platforms", "facebook"),
    "NFLX": ("netflix",),
    "GOOGL": ("google", "alphabet", "alphabet inc"),
    "INTC": ("intel", "intel corp", "intel corporation"),
    "AVGO": ("broadcom", "broadcom inc"),
    "BA": ("boeing", "boeing co", "boeing company"),
    "BAC": ("bank of america", "bofa", "merrill lynch"),
    "BNY": ("bank of new york mellon", "bny mellon"),
    "JPM": ("jpmorgan", "jp morgan", "jpmorgan chase"),
    "COST": ("costco", "costco wholesale"),
    "CRM": ("salesforce", "salesforce inc"),
    "CVX": ("chevron", "chevron corp", "chevron corporation"),
    "DIS": ("disney", "walt disney"),
    "AAL": ("american airlines",),
    "BULL": ("webull", "webull corp", "webull corporation"),
    "BYDDY": ("byd", "byd co", "byd company", "byd co ltd", "byd company limited"),
    "PETR4": ("petrobras", "petróleo brasileiro"),
    "PETR3": ("petrobras", "petróleo brasileiro"),
    "VALE3": ("vale", "vale s.a", "vale sa"),
    "ITUB4": ("itau", "itaú", "itau unibanco", "itaú unibanco"),
    "BBDC4": ("bradesco", "banco bradesco"),
    "BBAS3": ("banco do brasil",),
    "SANB11": ("santander brasil", "banco santander"),
    "BPAC11": ("btg pactual",),
    "BTCUSD": ("bitcoin", "btc"),
    "ETHUSD": ("ethereum", "ether", "eth"),
    "BNBUSD": ("bnb", "binance coin", "bnb chain"),
}
_NEWS_LOCAL_TZ = ZoneInfo("America/Sao_Paulo")


def _project_runtime_path(env_name: str, default_relative: str) -> Path:
    configured = os.getenv(env_name)
    if configured:
        configured_path = Path(configured)
        return configured_path if configured_path.is_absolute() else _PROJECT_ROOT / configured_path
    return _PROJECT_ROOT / default_relative


_NEWS_CACHE_FILE = _project_runtime_path("NEWS_CACHE_FILE", "runtime/cache/news_cache.json")
_NEWS_CACHE_LOADED = False
_NEWS_CACHE_FILE_MTIME: float | None = None

DEFAULT_NEWS_LOCALE = "pt-BR"
SUPPORTED_NEWS_LOCALES = ("pt-BR", "en-US")


def normalize_news_locale(locale: str | None) -> str:
    value = str(locale or "").strip().replace("_", "-").lower()
    if value in {"en", "en-us", "us", "usa"} or value.startswith("en-"):
        return "en-US"
    if value in {"pt", "pt-br", "br", "bra", "brasil"} or value.startswith("pt-"):
        return "pt-BR"
    return DEFAULT_NEWS_LOCALE


def _cache_entry_locale(entry: dict[str, Any]) -> str:
    explicit = entry.get("locale")
    if explicit:
        return normalize_news_locale(str(explicit))
    items = entry.get("items")
    if isinstance(items, list):
        for item in items:
            if isinstance(item, dict) and item.get("content_locale"):
                return normalize_news_locale(str(item.get("content_locale")))
    return DEFAULT_NEWS_LOCALE


def _cache_record_locales(record: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(record, dict):
        return {}
    locales = record.get("locales")
    if isinstance(locales, dict):
        return {
            normalize_news_locale(str(locale)): entry
            for locale, entry in locales.items()
            if isinstance(entry, dict) and isinstance(entry.get("items"), list)
        }
    if isinstance(record.get("items"), list):
        return {_cache_entry_locale(record): record}
    return {}


def _merge_news_cache_records(existing: Any, incoming: Any) -> dict[str, Any]:
    merged: dict[str, dict[str, Any]] = {
        locale: copy.deepcopy(entry) for locale, entry in _cache_record_locales(existing).items()
    }
    for locale, entry in _cache_record_locales(incoming).items():
        current = merged.get(locale)
        incoming_version = (
            float(entry.get("timestamp", 0.0) or 0.0),
            float(entry.get("checked_at", 0.0) or 0.0),
        )
        current_version = (
            float(current.get("timestamp", 0.0) or 0.0),
            float(current.get("checked_at", 0.0) or 0.0),
        ) if isinstance(current, dict) else (0.0, 0.0)
        if current is None or incoming_version > current_version:
            localized_entry = copy.deepcopy(entry)
            localized_entry["locale"] = locale
            merged[locale] = localized_entry
    return {"locales": merged}


def _get_news_cache_entry_locked(ticker: str, locale: str) -> dict[str, Any] | None:
    return _cache_record_locales(_NEWS_CACHE.get(ticker)).get(locale)


def _set_news_cache_entry_locked(ticker: str, locale: str, entry: dict[str, Any]) -> None:
    normalized_locale = normalize_news_locale(locale)
    locales = {
        key: copy.deepcopy(value)
        for key, value in _cache_record_locales(_NEWS_CACHE.get(ticker)).items()
    }
    localized_entry = copy.deepcopy(entry)
    localized_entry["locale"] = normalized_locale
    locales[normalized_locale] = localized_entry
    _NEWS_CACHE[ticker] = {"locales": locales}


def _available_news_cache_locales_locked(ticker: str) -> list[str]:
    locales = _cache_record_locales(_NEWS_CACHE.get(ticker))
    return [locale for locale in SUPPORTED_NEWS_LOCALES if locale in locales]


def _latest_news_cache_entry_locked(ticker: str, *, exclude_locale: str | None = None) -> dict[str, Any] | None:
    entries = [
        entry
        for locale, entry in _cache_record_locales(_NEWS_CACHE.get(ticker)).items()
        if locale != exclude_locale and isinstance(entry.get("items"), list)
    ]
    if not entries:
        return None
    return max(entries, key=lambda entry: float(entry.get("timestamp", 0.0) or 0.0))


def _get_yfinance():
    global _YFINANCE
    if _YFINANCE is None:
        try:  # pragma: no cover - optional dependency.
            import yfinance as yf_module
        except Exception:  # pragma: no cover - optional dependency.
            yf_module = False
        _YFINANCE = yf_module
    return _YFINANCE or None


def _load_news_cache_once() -> None:
    global _NEWS_CACHE_FILE_MTIME, _NEWS_CACHE_LOADED
    try:
        lock_path = _NEWS_CACHE_FILE.with_suffix(_NEWS_CACHE_FILE.suffix + ".lock")
        with _PERSIST_LOCK, interprocess_file_lock(lock_path):
            payload, cache_mtime, _ = read_json_file_consistent(_NEWS_CACHE_FILE, dict, max_attempts=3)
    except Exception as exc:
        logger.warning("News cache load failed: %s", exc)
        return

    with _CACHE_LOCK:
        if _NEWS_CACHE_LOADED and _NEWS_CACHE_FILE_MTIME == (cache_mtime or None):
            return
        cached = payload.get("news_cache") if isinstance(payload, dict) else None
        if isinstance(cached, dict):
            for key, value in cached.items():
                normalized_record = _merge_news_cache_records(None, value)
                if normalized_record["locales"]:
                    normalized_key = str(key).upper()
                    _NEWS_CACHE[normalized_key] = _merge_news_cache_records(
                        _NEWS_CACHE.get(normalized_key), normalized_record,
                    )

        provider_status = payload.get("provider_status") if isinstance(payload, dict) else None
        if isinstance(provider_status, dict):
            for key, value in provider_status.items():
                if not isinstance(value, dict):
                    continue
                normalized_key = str(key).upper()
                existing = _NEWS_PROVIDER_STATUS.get(normalized_key)
                disk_checked_at = float(value.get("checked_at", 0.0) or 0.0)
                existing_checked_at = float(existing.get("checked_at", 0.0) or 0.0) if isinstance(existing, dict) else -1.0
                if existing is None or disk_checked_at > existing_checked_at:
                    _NEWS_PROVIDER_STATUS[normalized_key] = copy.deepcopy(value)

        _NEWS_CACHE_FILE_MTIME = cache_mtime or None
        _NEWS_CACHE_LOADED = True


def _persist_news_cache() -> None:
    global _NEWS_CACHE_FILE_MTIME, _NEWS_CACHE_LOADED
    with _CACHE_LOCK:
        cache_snapshot = copy.deepcopy(_NEWS_CACHE)
        provider_snapshot = copy.deepcopy(_NEWS_PROVIDER_STATUS)

    try:
        lock_path = _NEWS_CACHE_FILE.with_suffix(_NEWS_CACHE_FILE.suffix + ".lock")
        with _PERSIST_LOCK, interprocess_file_lock(lock_path):
            disk_payload, _, _ = read_json_file_consistent(_NEWS_CACHE_FILE, dict, max_attempts=3)
            disk_cache = disk_payload.get("news_cache") if isinstance(disk_payload, dict) else None
            if isinstance(disk_cache, dict):
                for key, value in disk_cache.items():
                    normalized_key = str(key).upper()
                    if _cache_record_locales(value):
                        cache_snapshot[normalized_key] = _merge_news_cache_records(
                            cache_snapshot.get(normalized_key), value,
                        )

            disk_provider_status = disk_payload.get("provider_status") if isinstance(disk_payload, dict) else None
            if isinstance(disk_provider_status, dict):
                for key, value in disk_provider_status.items():
                    if not isinstance(value, dict):
                        continue
                    normalized_key = str(key).upper()
                    existing = provider_snapshot.get(normalized_key)
                    disk_checked_at = float(value.get("checked_at", 0.0) or 0.0)
                    existing_checked_at = float(existing.get("checked_at", 0.0) or 0.0) if isinstance(existing, dict) else -1.0
                    if existing is None or disk_checked_at > existing_checked_at:
                        provider_snapshot[normalized_key] = copy.deepcopy(value)

            write_json_file_atomic(_NEWS_CACHE_FILE, {
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "schema_version": 2,
                "news_cache": cache_snapshot,
                "provider_status": provider_snapshot,
            })
            persisted_mtime = _NEWS_CACHE_FILE.stat().st_mtime

        with _CACHE_LOCK:
            for key, value in cache_snapshot.items():
                _NEWS_CACHE[key] = _merge_news_cache_records(value, _NEWS_CACHE.get(key))
            for key, value in provider_snapshot.items():
                current = _NEWS_PROVIDER_STATUS.get(key)
                snapshot_checked_at = float(value.get("checked_at", 0.0) or 0.0)
                current_checked_at = float(current.get("checked_at", 0.0) or 0.0) if isinstance(current, dict) else -1.0
                if current is None or snapshot_checked_at > current_checked_at:
                    _NEWS_PROVIDER_STATUS[key] = copy.deepcopy(value)
            _NEWS_CACHE_FILE_MTIME = persisted_mtime
            _NEWS_CACHE_LOADED = True
    except Exception as exc:
        logger.warning("News cache persist failed: %s", exc)


def _remember_news_provider_status(
    ticker: str,
    status: str,
    *,
    error: str | None = None,
    raw_count: int = 0,
) -> None:
    normalized = _normalize_ticker(ticker)
    if not normalized:
        return
    payload = {
        "provider": "yfinance",
        "ticker": normalized,
        "status": status,
        "error": error,
        "raw_count": int(raw_count or 0),
        "checked_at": _now_ts(),
    }
    with _CACHE_LOCK:
        _NEWS_PROVIDER_STATUS[normalized] = payload


def _latest_news_provider_status(ticker: str) -> dict[str, Any]:
    normalized = _normalize_ticker(ticker)
    if not normalized:
        return {"provider": "yfinance", "ticker": "", "status": "invalid_ticker", "error": "invalid_ticker", "raw_count": 0, "checked_at": None}
    with _CACHE_LOCK:
        payload = _NEWS_PROVIDER_STATUS.get(normalized)
        if isinstance(payload, dict):
            return dict(payload)
    return {"provider": "yfinance", "ticker": normalized, "status": "not_checked", "error": None, "raw_count": 0, "checked_at": None}

_PORTUGUESE_STOPWORDS = {
    "a",
    "ao",
    "aos",
    "as",
    "de",
    "da",
    "das",
    "do",
    "dos",
    "e",
    "em",
    "na",
    "nas",
    "no",
    "nos",
    "o",
    "os",
    "para",
    "por",
    "que",
    "se",
    "um",
    "uma",
    "sobre",
    "com",
}

_GENERIC_NEWS_STOPWORDS = {
    "inc",
    "corp",
    "company",
    "companies",
    "stock",
    "stocks",
    "shares",
    "share",
    "markets",
    "market",
    "finance",
    "financial",
    "news",
    "latest",
    "update",
    "updates",
    "press",
    "release",
    "financeiro",
    "mercado",
}

_RESULT_KEYWORDS = {
    "resultado",
    "earnings",
    "revenue",
    "receita",
    "lucro",
    "profit",
    "eps",
    "balanco",
    "balanço",
    "quarter",
    "quarterly",
    "trimestre",
    "results",
}
_MA_KEYWORDS = {
    "m&a",
    "merger",
    "acquire",
    "acquisition",
    "deal",
    "buyout",
    "takeover",
    "fusa",
    "fusão",
    "fusao",
    "merge",
}
_REGULATION_KEYWORDS = {
    "regulation",
    "regulatory",
    "sec",
    "cvm",
    "antitrust",
    "lawsuit",
    "processo",
    "investigation",
    "fine",
    "fined",
    "ban",
    "compliance",
    "approval",
    "approved",
    "cleared",
}
_GUIDANCE_KEYWORDS = {
    "guidance",
    "outlook",
    "forecast",
    "projection",
    "estimate",
    "estimates",
    "revises",
    "raise guidance",
    "cut guidance",
    "raises forecast",
    "cuts forecast",
}
_MACRO_KEYWORDS = {
    "macro",
    "fed",
    "fomc",
    "inflation",
    "cpi",
    "ppi",
    "jobs",
    "payroll",
    "rates",
    "rate",
    "tariff",
    "tariffs",
    "dollar",
    "oil",
    "gdp",
    "yields",
    "bond",
    "treasury",
    "recession",
    "economy",
}
_FACT_KEYWORDS = {
    "fato relevante",
    "8-k",
    "press release",
    "announces",
    "announced",
    "discloses",
    "filed",
    "files",
    "notice",
    "comunicado",
    "dividend",
    "buyback",
    "split",
}

_POSITIVE_HINTS = {
    "beat",
    "beats",
    "above",
    "strong",
    "higher",
    "raises",
    "raise",
    "up",
    "growth",
    "record",
    "approval",
    "approved",
    "cleared",
    "win",
    "wins",
    "expand",
    "expands",
    "acceleration",
    "surge",
}
_NEGATIVE_HINTS = {
    "miss",
    "misses",
    "below",
    "lower",
    "lowers",
    "cut",
    "cuts",
    "warns",
    "warning",
    "probe",
    "investigation",
    "lawsuit",
    "fined",
    "drop",
    "drops",
    "slump",
    "weak",
    "decline",
    "down",
    "delay",
    "delayed",
}

_AMBIGUITY_HINTS = {
    "may",
    "might",
    "could",
    "unclear",
    "mixed",
    "uncertain",
    "rumor",
    "reportedly",
    "considering",
    "talks",
    "seeks",
    "explores",
    "potential",
    "possible",
}

_NOISE_HINTS = {
    "watch",
    "opinion",
    "podcast",
    "video",
    "live blog",
    "market wrap",
    "opening bell",
    "closing bell",
}

_TICKER_SECTOR_MAP = {
    # B3
    "PETR3": ("Energia / Petróleo", "Petroleo e gás"),
    "PETR4": ("Energia / Petróleo", "Petroleo e gás"),
    "VALE3": ("Materiais / Mineração", "Mineração"),
    "ITUB4": ("Financeiro / Bancos", "Bancos"),
    "BBDC4": ("Financeiro / Bancos", "Bancos"),
    "BBAS3": ("Financeiro / Bancos", "Bancos"),
    "SANB11": ("Financeiro / Bancos", "Bancos"),
    "BPAC11": ("Financeiro / Bancos", "Bancos de investimento"),
    "SUZB3": ("Materiais / Papel e Celulose", "Papel e celulose"),
    "KLBN11": ("Materiais / Papel e Celulose", "Papel e celulose"),
    "AXIA3": ("Utilidades / Energia", "Energia elétrica"),
    "AXIA7": ("Utilidades / Energia", "Energia elétrica"),
    "CPFE3": ("Utilidades / Energia", "Energia elétrica"),
    "EQTL3": ("Utilidades / Energia", "Energia elétrica"),
    "ENBR3": ("Utilidades / Energia", "Energia elétrica"),
    "MGLU3": ("Consumo / Varejo", "Varejo"),
    "LREN3": ("Consumo / Varejo", "Varejo"),
    "AMER3": ("Consumo / Varejo", "Varejo"),
    "VIIA3": ("Consumo / Varejo", "Varejo"),
    "ASAI3": ("Consumo / Varejo", "Varejo"),
    "WEGE3": ("Industriais", "Bens de capital"),
    "GGBR4": ("Materiais / Aço", "Siderurgia"),
    "CSNA3": ("Materiais / Aço", "Siderurgia"),
    "USIM5": ("Materiais / Aço", "Siderurgia"),
    "TOTS3": ("Tecnologia", "Software"),
    "POSI3": ("Tecnologia", "Hardware"),
    "RAIL3": ("Industriais / Logística", "Logística"),
    "CCRO3": ("Industriais / Infraestrutura", "Infraestrutura"),
    "NTCO3": ("Consumo / Beleza", "Bens de consumo"),
    "MBRF3": ("Consumo / Alimentos", "Alimentos"),
    "JBSS32": ("Consumo / Alimentos", "Alimentos"),
    # BDR
    "AAPL34": ("Tecnologia / EUA", "Hardware"),
    "MSFT34": ("Tecnologia / EUA", "Software"),
    "GOGL34": ("Tecnologia / EUA", "Internet"),
    "AMZN34": ("Consumo / EUA", "E-commerce"),
    "NVDC34": ("Tecnologia / EUA", "Semicondutores"),
    "TSLA34": ("Consumo / EUA", "Mobilidade"),
    "META34": ("Tecnologia / EUA", "Mídia social"),
    "NFLX34": ("Comunicação / EUA", "Streaming"),
    "INTC34": ("Tecnologia / EUA", "Semicondutores"),
    "AMD34": ("Tecnologia / EUA", "Semicondutores"),
    "QCOM34": ("Tecnologia / EUA", "Semicondutores"),
    "IVVB11": ("ETF / Índice", "Índice S&P 500"),
    # USA
    "AAPL": ("Tecnologia", "Hardware"),
    "MSFT": ("Tecnologia", "Software"),
    "GOOGL": ("Tecnologia", "Internet"),
    "AMZN": ("Consumo", "E-commerce"),
    "META": ("Tecnologia", "Mídia social"),
    "NVDA": ("Tecnologia", "Semicondutores"),
    "TSLA": ("Consumo", "Mobilidade"),
    "AMD": ("Tecnologia", "Semicondutores"),
    "INTC": ("Tecnologia", "Semicondutores"),
    "AVGO": ("Tecnologia", "Semicondutores"),
    "TSM": ("Tecnologia", "Semicondutores"),
    "JPM": ("Financeiro", "Bancos"),
    "BAC": ("Financeiro", "Bancos"),
    "GS": ("Financeiro", "Bancos de investimento"),
    "XOM": ("Energia", "Petroleo e gás"),
    "CVX": ("Energia", "Petroleo e gás"),
    "COST": ("Consumo", "Varejo"),
    "WMT": ("Consumo", "Varejo"),
    "DIS": ("Comunicação", "Mídia e entretenimento"),
    "CRM": ("Tecnologia", "Software"),
    "SNOW": ("Tecnologia", "Software"),
    "PLTR": ("Tecnologia", "Software"),
}

_ENTITY_PATTERNS = [
    re.compile(r"\$?[A-Z]{2,6}(?:\.[A-Z]{2})?(?:-USD|-USDT|-BTC)?"),
    re.compile(r"\b(?:SEC|CVM|FED|FOMC|CPI|PPI|GDP|IPO|M&A|MNA|MERGER|BUYBACK|DIVIDEND|OPEC|DOJ|FTC|ECB)\b"),
]


def _now_ts() -> float:
    return time.time()


@lru_cache(maxsize=2048)
def _strip_accents(value: str) -> str:
    value = unicodedata.normalize("NFKD", value)
    return "".join(ch for ch in value if not unicodedata.combining(ch))


def _clean_whitespace(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "").strip())


@lru_cache(maxsize=4096)
def _normalize_ticker(ticker: str) -> str:
    return canonical_symbol(ticker) or _clean_whitespace(str(ticker or "")).upper().replace(" ", "")


@lru_cache(maxsize=4096)
def _slugify(value: str) -> str:
    value = _strip_accents(value.lower())
    value = re.sub(r"[^a-z0-9]+", " ", value)
    tokens = [token for token in value.split() if token and token not in _PORTUGUESE_STOPWORDS]
    return " ".join(tokens)


def _first_sentence(value: str) -> str:
    cleaned = _clean_whitespace(value)
    if not cleaned:
        return ""
    parts = re.split(r"(?<=[.!?])\s+", cleaned)
    return _clean_whitespace(parts[0] if parts else cleaned)


def _shorten(value: str, limit: int = 160) -> str:
    cleaned = _clean_whitespace(value)
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: max(0, limit - 1)].rstrip() + "…"


@lru_cache(maxsize=8192)
def _safe_lower(value: str) -> str:
    return _strip_accents((value or "").lower())


def _contains_any(text: str, keywords: set[str]) -> bool:
    for keyword in keywords:
        if _safe_lower(keyword) in text:
            return True
    return False


def _nested_value(raw_item: dict[str, Any], *path: str) -> Any:
    current: Any = raw_item
    for key in path:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def _parse_published_at(raw_item: dict[str, Any]) -> datetime | None:
    values = [
        raw_item.get("providerPublishTime"),
        raw_item.get("published_at"),
        raw_item.get("pubDate"),
        raw_item.get("publishedAt"),
        raw_item.get("displayTime"),
        _nested_value(raw_item, "content", "providerPublishTime"),
        _nested_value(raw_item, "content", "pubDate"),
        _nested_value(raw_item, "content", "publishedAt"),
        _nested_value(raw_item, "content", "displayTime"),
    ]
    for value in values:
        if not value:
            continue
        try:
            if isinstance(value, (int, float)):
                timestamp = float(value)
                if timestamp > 1_000_000_000_000:
                    timestamp = timestamp / 1000.0
                return datetime.fromtimestamp(timestamp, tz=timezone.utc)
            if isinstance(value, str):
                if value.isdigit():
                    timestamp = float(value)
                    if timestamp > 1_000_000_000_000:
                        timestamp = timestamp / 1000.0
                    return datetime.fromtimestamp(timestamp, tz=timezone.utc)
                parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
                return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        except Exception:
            continue
    return None


def _to_iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()


def _news_age_minutes(published_at: datetime | None, now_ts: float | None = None) -> int | None:
    if published_at is None:
        return None
    current_ts = _now_ts() if now_ts is None else now_ts
    try:
        return max(0, int((current_ts - published_at.timestamp()) // 60))
    except Exception:
        return None


def _is_news_today(published_at: datetime | None, now_dt: datetime | None = None) -> bool:
    if published_at is None:
        return False
    current = now_dt or datetime.fromtimestamp(_now_ts(), tz=timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    if published_at.tzinfo is None:
        published_at = published_at.replace(tzinfo=timezone.utc)
    return published_at.astimezone(_NEWS_LOCAL_TZ).date() == current.astimezone(_NEWS_LOCAL_TZ).date()


def _detect_news_language(title: str, summary: str) -> str:
    text = _safe_lower(f"{title} {summary}")
    if re.search(r"\b(acao|acoes|noticia|mercado|lucro|receita|resultado|banco|petroleo|juros|empresa)\b", text):
        return "pt-BR"
    return "en-US"


def _extract_title(raw_item: dict[str, Any]) -> str:
    title = raw_item.get("title")
    if isinstance(title, str) and title.strip():
        return _clean_whitespace(title)
    content = raw_item.get("content")
    if isinstance(content, dict):
        nested_title = content.get("title")
        if isinstance(nested_title, str) and nested_title.strip():
            return _clean_whitespace(nested_title)
    return ""


def _extract_summary(raw_item: dict[str, Any]) -> str:
    summary = raw_item.get("summary")
    if isinstance(summary, str) and summary.strip():
        return _clean_whitespace(summary)
    content = raw_item.get("content")
    if isinstance(content, dict):
        nested_summary = content.get("summary") or content.get("description")
        if isinstance(nested_summary, str) and nested_summary.strip():
            return _clean_whitespace(nested_summary)
    description = raw_item.get("description")
    if isinstance(description, str) and description.strip():
        return _clean_whitespace(description)
    return ""


def _extract_source(raw_item: dict[str, Any]) -> str:
    for key in ("publisher", "source", "provider", "publisherName"):
        value = raw_item.get(key)
        if isinstance(value, str) and value.strip():
            return _clean_whitespace(value)
        if isinstance(value, dict):
            nested = value.get("displayName") or value.get("name")
            if isinstance(nested, str) and nested.strip():
                return _clean_whitespace(nested)
    for value in (
        _nested_value(raw_item, "content", "provider", "displayName"),
        _nested_value(raw_item, "content", "provider", "name"),
        _nested_value(raw_item, "content", "publisher"),
        _nested_value(raw_item, "content", "source"),
    ):
        if isinstance(value, str) and value.strip():
            return _clean_whitespace(value)
    return "Yahoo Finance"


def _extract_url(raw_item: dict[str, Any]) -> str | None:
    for key in ("link", "url", "canonicalUrl", "clickThroughUrl"):
        value = raw_item.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
        if isinstance(value, dict):
            nested = value.get("url")
            if isinstance(nested, str) and nested.strip():
                return nested.strip()
    for value in (
        _nested_value(raw_item, "content", "canonicalUrl", "url"),
        _nested_value(raw_item, "content", "clickThroughUrl", "url"),
        _nested_value(raw_item, "content", "url"),
        _nested_value(raw_item, "content", "link"),
    ):
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _extract_related_tickers(raw_item: dict[str, Any]) -> list[str]:
    related_sources = [
        raw_item.get("relatedTickers"),
        _nested_value(raw_item, "content", "finance", "stockTickers"),
        _nested_value(raw_item, "content", "finance", "companyTickers"),
        _nested_value(raw_item, "content", "finance", "relatedTickers"),
        _nested_value(raw_item, "content", "relatedTickers"),
    ]
    result: list[str] = []
    for related in related_sources:
        if not isinstance(related, list):
            continue
        for item in related:
            if isinstance(item, dict):
                raw_symbol = item.get("symbol") or item.get("ticker") or item.get("name")
            else:
                raw_symbol = item
            symbol = _normalize_ticker(str(raw_symbol or ""))
            if symbol:
                result.append(symbol)
    return list(dict.fromkeys(result))


def _news_aliases(ticker: str) -> set[str]:
    normalized = _normalize_ticker(ticker).replace(".SA", "")
    aliases = {
        normalized,
        normalized.replace("34", ""),
        normalized.replace(".SA", ""),
    }
    aliases.update(canonical_symbol_aliases(normalized))
    aliases.update(_TICKER_NEWS_ALIASES.get(normalized, ()))
    return {alias.lower().strip() for alias in aliases if alias}


def _text_has_alias(text: str, alias: str) -> bool:
    if not alias:
        return False
    if len(alias) <= 2:
        return bool(re.search(rf"\b{re.escape(alias)}\b", text))
    return alias in text


def _sector_from_keywords(text: str) -> tuple[str, str]:
    lower = _safe_lower(text)
    if any(keyword in lower for keyword in ("bank", "banco", "credit", "loan", "financial", "finance")):
        return ("Financeiro", "Bancos")
    if any(keyword in lower for keyword in ("oil", "petrole", "petroleo", "gas", "energy", "refinery")):
        return ("Energia", "Petróleo e gás")
    if any(keyword in lower for keyword in ("semiconductor", "chip", "gpu", "cpu", "foundry", "nand")):
        return ("Tecnologia", "Semicondutores")
    if any(keyword in lower for keyword in ("software", "cloud", "saas", "app", "platform")):
        return ("Tecnologia", "Software")
    if any(keyword in lower for keyword in ("retail", "consumer", "store", "shop", "e-commerce", "ecommerce")):
        return ("Consumo", "Varejo")
    if any(keyword in lower for keyword in ("regulation", "sec", "cvm", "law", "legal", "antitrust", "lawsuit")):
        return ("Regulação", "Jurídico")
    if any(keyword in lower for keyword in ("cpi", "fed", "fomc", "inflation", "rate", "tariff", "macro")):
        return ("Macro / Mercado", "Macro")
    if any(keyword in lower for keyword in ("bitcoin", "ethereum", "crypto", "solana", "bnb", "blockchain")):
        return ("Crypto", "Ativos digitais")
    return ("Mercado", "Geral")


def _asset_sector(ticker: str, text: str) -> tuple[str, str]:
    normalized = _normalize_ticker(ticker).replace(".SA", "")
    if normalized in _TICKER_SECTOR_MAP:
        return _TICKER_SECTOR_MAP[normalized]
    if ticker.upper().endswith("-USD") or ticker.upper().endswith("USD"):
        return ("Crypto", "Ativos digitais")
    if ticker.upper().endswith(".SA"):
        return _sector_from_keywords(text)
    return _sector_from_keywords(f"{ticker} {text}")


def _classify_labels(text: str) -> list[str]:
    lower = _safe_lower(text)
    labels: list[str] = []
    if _contains_any(lower, _RESULT_KEYWORDS):
        labels.append("resultado")
    if _contains_any(lower, _MA_KEYWORDS):
        labels.append("M&A")
    if _contains_any(lower, _REGULATION_KEYWORDS):
        labels.append("regulação")
    if _contains_any(lower, _GUIDANCE_KEYWORDS):
        labels.append("guidance")
    if _contains_any(lower, _MACRO_KEYWORDS):
        labels.append("macro")
    if _contains_any(lower, _FACT_KEYWORDS):
        labels.append("fato relevante")
    return list(dict.fromkeys(labels))


def _extract_entities(ticker: str, title: str, summary: str, related_tickers: list[str], labels: list[str]) -> list[str]:
    text = f"{ticker} {title} {summary}"
    raw_entities: list[str] = [ticker]
    raw_entities.extend(related_tickers)

    for pattern in _ENTITY_PATTERNS:
        for match in pattern.findall(text):
            match_value = _normalize_ticker(match)
            if not match_value:
                continue
            if match_value in _GENERIC_NEWS_STOPWORDS or match_value in _PORTUGUESE_STOPWORDS:
                continue
            raw_entities.append(match_value)

    if labels:
        raw_entities.extend(label.upper() for label in labels)

    result: list[str] = []
    for entity in raw_entities:
        cleaned = _clean_whitespace(str(entity)).strip(".,;:()[]{}")
        if not cleaned:
            continue
        if cleaned.lower() in _GENERIC_NEWS_STOPWORDS or cleaned.lower() in _PORTUGUESE_STOPWORDS:
            continue
        if cleaned not in result:
            result.append(cleaned)
    return result[:8]


def _ticker_directness(ticker: str, title: str, summary: str, related_tickers: list[str]) -> tuple[bool, float]:
    normalized_ticker = _normalize_ticker(ticker).replace(".SA", "")
    text = _safe_lower(f"{title} {summary}")
    aliases = _news_aliases(ticker)
    related = {_normalize_ticker(item).replace(".SA", "") for item in related_tickers}

    if any(_text_has_alias(text, _safe_lower(alias)) for alias in aliases):
        return True, 100.0
    if normalized_ticker in related:
        return True, 88.0
    if related & aliases:
        return True, 80.0
    return False, 40.0


def _story_signature(ticker: str, title: str, labels: list[str], entities: list[str]) -> str:
    core = " ".join([ticker, title, " ".join(labels), " ".join(entities)])
    slug = _slugify(core)
    return hashlib.sha1(slug.encode("utf-8")).hexdigest()[:16] if slug else hashlib.sha1(ticker.encode("utf-8")).hexdigest()[:16]


@lru_cache(maxsize=4096)
def _token_set(value: str) -> tuple[str, ...]:
    tokens = {token for token in _slugify(value).split() if token}
    filtered = sorted(token for token in tokens if token not in _GENERIC_NEWS_STOPWORDS and token not in _PORTUGUESE_STOPWORDS)
    return tuple(filtered)


def _cluster_key_tokens(item: dict[str, Any]) -> tuple[str, ...]:
    title = str(item.get("title") or "")
    if not title:
        return ()
    tokens = _token_set(title)
    if not tokens:
        return ()
    return tuple(tokens[: min(5, len(tokens))])


@lru_cache(maxsize=4096)
def _headline_similarity(left: str, right: str) -> float:
    if not left or not right:
        return 0.0
    return SequenceMatcher(None, _slugify(left), _slugify(right)).ratio()


def _impact_hint_balance(text: str, labels: list[str]) -> tuple[int, int]:
    lower = _safe_lower(text)

    bullish_score = sum(1 for hint in _POSITIVE_HINTS if _safe_lower(hint) in lower)
    bearish_score = sum(1 for hint in _NEGATIVE_HINTS if _safe_lower(hint) in lower)

    if "resultado" in labels:
        if _contains_any(lower, {"beat", "above", "surge", "record", "strong", "raises"}):
            bullish_score += 2
        if _contains_any(lower, {"miss", "below", "weak", "cuts", "lower"}):
            bearish_score += 2

    if "guidance" in labels:
        if _contains_any(lower, {"raises", "higher", "improves", "beats", "lift"}):
            bullish_score += 3
        if _contains_any(lower, {"cuts", "lower", "warns", "weak", "down"}):
            bearish_score += 3

    if "regulação" in labels:
        if _contains_any(lower, {"approved", "cleared", "approval", "wins"}):
            bullish_score += 2
        if _contains_any(lower, {"fine", "fined", "probe", "investigation", "lawsuit", "ban"}):
            bearish_score += 3

    if "M&A" in labels:
        if _contains_any(lower, {"acquires", "acquisition", "buyout", "premium", "merger"}):
            bullish_score += 2
        if _contains_any(lower, {"blocked", "fails", "collapse", "terminated"}):
            bearish_score += 2

    if "macro" in labels:
        if _contains_any(lower, {"lower rates", "cuts rates", "cooling inflation", "dovish"}):
            bullish_score += 1
        if _contains_any(lower, {"higher rates", "higher for longer", "tariffs", "inflation", "hawkish", "restrictive"}):
            bearish_score += 1

    return bullish_score, bearish_score


def _canonical_impact_reason(impact: str, locale: str, *, ambiguous_indirect: bool = False) -> str:
    content_locale = normalize_news_locale(locale)
    if ambiguous_indirect:
        return (
            "The headline is relevant but still ambiguous or indirect for the asset; confirmation is required."
            if content_locale == "en-US"
            else "Manchete relevante, mas ainda ambígua ou indireta para o papel; precisa de confirmação."
        )
    if content_locale == "en-US":
        return {
            "bullish": "Favorable short-term read for the asset.",
            "bearish": "The headline pressures the asset in the short term.",
            "neutral": "Impact remains ambiguous and needs context confirmation.",
        }.get(impact, "Impact remains ambiguous and needs context confirmation.")
    return {
        "bullish": "Leitura favorável ao ativo no curto prazo.",
        "bearish": "Leitura pressionando o ativo no curto prazo.",
        "neutral": "Impacto ainda ambíguo e pede confirmação de contexto.",
    }.get(impact, "Impacto ainda ambíguo e pede confirmação de contexto.")


def _impact_from_keywords(text: str, labels: list[str], locale: str = DEFAULT_NEWS_LOCALE) -> tuple[str, str]:
    bullish_score, bearish_score = _impact_hint_balance(text, labels)

    if bullish_score > bearish_score:
        return "bullish", _canonical_impact_reason("bullish", locale)
    if bearish_score > bullish_score:
        return "bearish", _canonical_impact_reason("bearish", locale)
    return "neutral", _canonical_impact_reason("neutral", locale)


def _ambiguity_analysis(
    text: str,
    labels: list[str],
    bullish_impact: bool,
    bearish_impact: bool,
    direct_match: bool,
) -> tuple[float, list[str]]:
    lower = _safe_lower(text)
    flags: list[str] = []
    score = 0.0

    if _contains_any(lower, _AMBIGUITY_HINTS):
        flags.append("linguagem_incerta")
        score += 22.0
    if "?" in text:
        flags.append("headline_interrogativa")
        score += 10.0
    if bullish_impact and bearish_impact:
        flags.append("sinal_conflitante")
        score += 28.0
    if "macro" in labels and not direct_match:
        flags.append("macro_indireta")
        score += 14.0
    if not direct_match:
        flags.append("impacto_indireto")
        score += 14.0
    if _contains_any(lower, _NOISE_HINTS):
        flags.append("baixo_sinal_editorial")
        score += 12.0

    return max(0.0, min(score, 100.0)), flags


def _impact_label(impact: str, locale: str = DEFAULT_NEWS_LOCALE) -> str:
    labels = {
        "bullish": "Positivo",
        "bearish": "Negativo",
        "neutral": "Neutro",
    }
    if normalize_news_locale(locale) == "en-US":
        labels = {"bullish": "Positive", "bearish": "Negative", "neutral": "Neutral"}
    return labels.get(impact, labels["neutral"])


def _localized_news_label(label: str, locale: str) -> str:
    if normalize_news_locale(locale) != "en-US":
        return label
    return {
        "resultado": "earnings",
        "guidance": "guidance",
        "M&A": "M&A",
        "regulação": "regulation",
        "macro": "macro",
        "fato relevante": "material event",
    }.get(label, label)


def _build_card_summary(
    title: str,
    summary: str,
    labels: list[str],
    impact: str,
    locale: str = DEFAULT_NEWS_LOCALE,
) -> str:
    content_locale = normalize_news_locale(locale)
    base = _first_sentence(summary) or _first_sentence(title)
    if not base:
        base = title
    if labels:
        label_tail = " • ".join(_localized_news_label(label, content_locale) for label in labels[:2])
        base = f"{base} ({label_tail})"
    if content_locale == "en-US":
        if impact == "bullish":
            suffix = " The read is constructive for the asset."
        elif impact == "bearish":
            suffix = " It may pressure the asset."
        else:
            suffix = " Context confirmation is still required."
    else:
        if impact == "bullish":
            suffix = " Tendência positiva para o ativo."
        elif impact == "bearish":
            suffix = " Pode pressionar o papel."
        else:
            suffix = " Exige confirmação do contexto."
    return _shorten(f"{base}{suffix}", 170)


def _build_editorial(
    ticker: str,
    labels: list[str],
    impact: str,
    confidence: float,
    sector: str,
    locale: str = DEFAULT_NEWS_LOCALE,
) -> str:
    if normalize_news_locale(locale) == "en-US":
        confidence_word = "strong" if confidence >= 70 else "moderate" if confidence >= 45 else "weak"
        tone = "supports upside" if impact == "bullish" else "supports downside" if impact == "bearish" else "remains neutral"
        if labels:
            lead = ", ".join(_localized_news_label(label, locale) for label in labels[:2])
            return _shorten(f"{lead.capitalize()} for {ticker} {tone}; {confidence_word} read for the sector.", 180)
        return _shorten(f"News for {ticker} {tone}; {confidence_word} sector read.", 180)

    confidence_word = "forte" if confidence >= 70 else "moderada" if confidence >= 45 else "fraca"
    if impact == "bullish":
        tone = "favorece alta"
    elif impact == "bearish":
        tone = "favorece queda"
    else:
        tone = "fica em zona neutra"
    if labels:
        lead = ", ".join(labels[:2])
        return _shorten(f"{lead.capitalize()} em {ticker} {tone}; leitura {confidence_word} para {sector.lower()}.", 180)
    return _shorten(f"Notícia para {ticker} {tone}; leitura {confidence_word} para {sector.lower()}.", 180)


def _build_editorial_final(
    ticker: str,
    labels: list[str],
    impact: str,
    confidence: float,
    sector: str,
    ambiguity_score: float,
    source_count: int,
    direct_match: bool,
    locale: str = DEFAULT_NEWS_LOCALE,
) -> str:
    content_locale = normalize_news_locale(locale)
    base = _build_editorial(ticker, labels, impact, confidence, sector, content_locale)
    if content_locale == "en-US":
        if ambiguity_score >= 45:
            return _shorten(f"{base} Mixed signal: wait for price confirmation before treating the headline as a trigger.", 220)
        if source_count >= 2:
            return _shorten(f"{base} The same event was confirmed by {source_count} related sources.", 220)
        if not direct_match:
            return _shorten(f"{base} The impact appears more sector-wide than asset-specific.", 220)
        return base
    if ambiguity_score >= 45:
        return _shorten(f"{base} Sinal misto: espere confirmação no preço antes de tratar a manchete como gatilho.", 220)
    if source_count >= 2:
        return _shorten(f"{base} História confirmada em {source_count} fontes ligadas ao mesmo evento.", 220)
    if not direct_match:
        return _shorten(f"{base} O impacto parece mais setorial do que específico do papel.", 220)
    return base


def _build_why_it_matters(
    ticker: str,
    labels: list[str],
    impact: str,
    sector: str,
    locale: str = DEFAULT_NEWS_LOCALE,
) -> str:
    if normalize_news_locale(locale) == "en-US":
        if "resultado" in labels:
            return _shorten(f"It may move {ticker} by changing earnings expectations and sector pricing.", 180)
        if "guidance" in labels:
            return _shorten(f"It may move {ticker} by changing expectations for execution and margins.", 180)
        if "M&A" in labels:
            return _shorten(f"It may cause rapid repricing in {ticker} through event premium and strategic positioning.", 180)
        if "regulação" in labels:
            return _shorten(f"It may change perceived risk for {ticker} and its sector.", 180)
        if "macro" in labels:
            return _shorten("The macro backdrop may change sector flow and risk appetite.", 180)
        if "fato relevante" in labels:
            return _shorten(f"The market may adjust price and flow in {ticker} after the disclosure.", 180)
        return _shorten(f"It adds flow and context that may affect {ticker} in the short term.", 180)

    if "resultado" in labels:
        return _shorten(f"Pode mover {ticker} porque altera expectativa de lucro e precificação do papel no setor {sector.lower()}.", 180)
    if "guidance" in labels:
        return _shorten(f"Pode mover {ticker} porque muda a expectativa futura do mercado sobre execução e margem.", 180)
    if "M&A" in labels:
        return _shorten(f"Pode gerar reprecificação rápida em {ticker} por prêmio de evento e leitura estratégica.", 180)
    if "regulação" in labels:
        return _shorten(f"Pode mexer com o risco percebido de {ticker} e com a leitura do setor {sector.lower()}.", 180)
    if "macro" in labels:
        return _shorten(f"Importa porque o pano de fundo macro pode alterar o fluxo para {sector.lower()} e o apetite ao risco.", 180)
    if "fato relevante" in labels:
        return _shorten(f"Importa porque o mercado pode ajustar preço e fluxo em {ticker} logo após a divulgação.", 180)
    return _shorten(f"Ajuda a entender o fluxo e o contexto que podem afetar {ticker} no curto prazo.", 180)


def _build_trader_takeaway_en(
    ticker: str,
    title: str,
    summary: str,
    impact: str,
    labels: list[str],
    ambiguity_score: float,
    direct_match: bool,
) -> str:
    text = _safe_lower(f"{title} {summary} {' '.join(labels)}")
    seed = sum(ord(char) for char in f"{ticker}|{title}|{summary}") % 3

    def pick(options: list[str]) -> str:
        return _shorten(options[seed % len(options)], 190)

    if ambiguity_score >= 45:
        return pick([
            f"Trader note: treat the {ticker} headline as context until price confirms direction.",
            f"Trader note: the read for {ticker} is ambiguous; wait for price and volume reaction.",
            f"Trader note: use this as an alert for {ticker}, not a standalone trigger.",
        ])
    if "M&A" in labels or "merger" in text or "acquisition" in text or "fusão" in text or "aquis" in text:
        return pick([
            f"Trader note: event risk may reprice {ticker}; wait for price, spread and volume confirmation.",
            f"Trader note: M&A may create a premium in {ticker}, but flow must confirm the timing.",
            f"Trader note: turn this corporate event into a trade only if {ticker} shows real flow.",
        ])
    if "dividend" in text or "dividendo" in text or "yield" in text:
        return pick([
            f"Trader note: do not buy {ticker} on yield alone; confirm cash quality, trend and volume.",
            f"Trader note: income appeal supports context, but {ticker} must hold price structure.",
            f"Trader note: weak volume keeps the dividend read for {ticker} as an alert only.",
        ])
    if "resultado" in labels or "guidance" in labels or "earnings" in text:
        return pick([
            f"Trader note: monitor price and volume reaction in {ticker} before acting.",
            f"Trader note: earnings or guidance in {ticker} requires margin, flow and candle confirmation.",
            f"Trader note: separate the headline from execution; {ticker} price must validate the read.",
        ])
    if "regulação" in labels or "regulation" in text or "regulatory" in text:
        return pick([
            f"Trader note: regulatory news may raise volatility in {ticker}; wait for direction confirmation.",
            f"Trader note: regulation changes perceived risk in {ticker}; let the market show the dominant side.",
            f"Trader note: treat regulation in {ticker} as event risk and validate support or resistance.",
        ])
    if "macro" in labels and not direct_match:
        return pick([
            f"Trader note: read the index and sector impact before its transmission to {ticker}.",
            f"Trader note: macro affects {ticker} through risk appetite; act only if the asset confirms its own flow.",
            f"Trader note: use price and volume as the final filter for this macro context in {ticker}.",
        ])
    if impact == "bullish":
        return pick([
            f"Trader note: favor upside continuation only if {ticker} sustains flow and holds the breakout.",
            f"Trader note: the constructive read in {ticker} still needs price and volume confirmation.",
            f"Trader note: consider the positive context only after {ticker} defends support or breaks out cleanly.",
        ])
    if impact == "bearish":
        return pick([
            f"Trader note: favor protection only if {ticker} confirms weakness with volume.",
            f"Trader note: the negative read in {ticker} still needs support loss or rejection confirmation.",
            f"Trader note: wait for {ticker} to confirm direction before turning the headline into a trade.",
        ])
    return pick([
        f"Trader note: use the headline as context and wait for market confirmation in {ticker}.",
        f"Trader note: keep {ticker} on watch until the news appears in real flow.",
        f"Trader note: confirm the new context on the chart before acting in {ticker}.",
    ])


def _build_trader_takeaway(
    ticker: str,
    title: str,
    summary: str,
    impact: str,
    labels: list[str],
    ambiguity_score: float,
    direct_match: bool,
    locale: str = DEFAULT_NEWS_LOCALE,
) -> str:
    if normalize_news_locale(locale) == "en-US":
        return _build_trader_takeaway_en(
            ticker,
            title,
            summary,
            impact,
            labels,
            ambiguity_score,
            direct_match,
        )
    text = _safe_lower(f"{title} {summary} {' '.join(labels)}")
    label_set = {str(label).lower() for label in labels}
    seed = sum(ord(char) for char in f"{ticker}|{title}|{summary}") % 3
    def pick(options: list[str]) -> str:
        return _shorten(options[seed % len(options)], 190)

    if ambiguity_score >= 45:
        return pick([
            f"Para trader: trate a notícia de {ticker} como contexto, não como gatilho isolado, até o preço confirmar direção.",
            f"Para trader: leitura ambígua em {ticker}; espere reação de preço e volume antes de agir.",
            f"Para trader: use a manchete como alerta em {ticker}, mas só opere com confirmação no gráfico.",
        ])
    if "M&A" in labels or "m&a" in label_set or "merger" in text or "acquisition" in text or "fusão" in text or "aquis" in text:
        return pick([
            f"Para trader: evento de fusões e aquisições em {ticker} pode gerar reprecificação; espere preço, spread e volume confirmarem.",
            f"Para trader: M&A pode criar prêmio em {ticker}, mas o timing depende de VWAP, volume e reação do mercado.",
            f"Para trader: notícia corporativa em {ticker} só vira operação se houver fluxo real confirmando o lado.",
        ])
    if "dividend" in text or "dividendo" in text or "yield" in text:
        return pick([
            f"Para trader: não compre {ticker} só pelo dividendo; valide caixa, tendência e reação de volume antes da entrada.",
            f"Para trader: yield em {ticker} é contexto de renda; entrada exige preço sustentando suporte e fluxo.",
            f"Para trader: dividendo pode atrair comprador em {ticker}, mas volume fraco mantém a leitura só como alerta.",
        ])
    if "battery" in text or "bateria" in text or " ev" in text or "electric vehicle" in text or "veículo elétrico" in text:
        return pick([
            f"Para trader: tema de EV/baterias muda expectativa em {ticker}; deixe a reação do preço confirmar o timing.",
            f"Para trader: notícia estratégica em {ticker} precisa virar fluxo comprador antes de justificar entrada.",
            f"Para trader: EV pode mexer em margem e crescimento de {ticker}; opere só após rompimento ou defesa clara.",
        ])
    if "mover" in text or "destaque" in text:
        return pick([
            f"Para trader: lista de destaques é filtro relativo; opere {ticker} só se força e volume confirmarem no gráfico.",
            f"Para trader: destaque de mercado não é entrada; compare {ticker} com o setor e espere gatilho real.",
            f"Para trader: use o mover como triagem em {ticker}; execução depende de tendência e liquidez.",
        ])
    if "resultado" in labels or "guidance" in labels or "earnings" in text:
        return pick([
            f"Para trader: monitore reação de preço e volume em {ticker} porque a leitura pode virar tendência intraday.",
            f"Para trader: resultado/guidance em {ticker} exige confirmação em margem, fluxo e direção do candle.",
            f"Para trader: separe manchete de execução em {ticker}; o preço precisa validar a leitura.",
        ])
    if "regulação" in labels or "regulation" in text or "regulatory" in text:
        return pick([
            f"Para trader: notícia regulatória pode aumentar volatilidade em {ticker}; reduza tamanho até confirmar direção.",
            f"Para trader: regulação muda risco percebido em {ticker}; espere o mercado mostrar o lado dominante.",
            f"Para trader: trate regulação em {ticker} como evento de risco; proteja tamanho e valide suporte/resistência.",
        ])
    if "macro" in labels and not direct_match:
        return pick([
            f"Para trader: leia primeiro o impacto no índice/setor e só depois a transmissão para {ticker}.",
            f"Para trader: macro afeta {ticker} por apetite a risco; só aja se o papel confirmar fluxo próprio.",
            f"Para trader: contexto macro em {ticker} pede cautela; use preço e volume como filtro final.",
        ])
    if impact == "bullish":
        return pick([
            f"Para trader: priorize continuação compradora só se {ticker} sustentar fluxo e não devolver o rompimento.",
            f"Para trader: viés positivo em {ticker} exige compradores defendendo VWAP e volume acompanhando.",
            f"Para trader: a leitura favorece alta em {ticker}, mas entrada só com suporte defendido ou rompimento limpo.",
        ])
    if impact == "bearish":
        return pick([
            f"Para trader: priorize proteção ou venda só se {ticker} confirmar fraqueza e perder suporte com volume.",
            f"Para trader: viés negativo em {ticker} pede defesa; short só com rejeição ou perda de suporte.",
            f"Para trader: evite compra impulsiva em {ticker}; aguarde preço recuperar estrutura antes de virar o lado.",
        ])
    return pick([
        f"Para trader: use a manchete como leitura complementar e espere confirmação do mercado em {ticker}.",
        f"Para trader: mantenha {ticker} em observação; a notícia precisa aparecer no fluxo antes de virar trade.",
        f"Para trader: contexto novo em {ticker}; confirme no gráfico antes de comprar, vender ou encerrar.",
    ])


def _market_context(
    ticker: str,
    labels: list[str],
    sector: str,
    industry: str,
    locale: str = DEFAULT_NEWS_LOCALE,
) -> str:
    if normalize_news_locale(locale) == "en-US":
        if "macro" in labels:
            return "Macro news tends to affect broad market sentiment before the specific sector."
        if "regulação" in labels:
            return "Regulatory news usually raises volatility and changes sector risk."
        if "M&A" in labels:
            return "M&A events may create an event premium and accelerate repricing."
        if "guidance" in labels or "resultado" in labels:
            return "Earnings and guidance usually affect valuation and sector flow."
        return "The context is tied to the asset's industry and short-term flow."
    if "macro" in labels:
        return "Notícia macro tende a afetar primeiro o humor do mercado e depois o setor específico."
    if "regulação" in labels:
        return f"Notícia regulatória costuma aumentar volatilidade e afetar {sector.lower()}."
    if "M&A" in labels:
        return "Evento de M&A pode criar prêmio de evento e acelerar reprecificação."
    if "guidance" in labels or "resultado" in labels:
        return f"Leitura de resultado/guidance costuma mexer com valuation e fluxo do setor {sector.lower()}."
    return f"Contexto mais ligado a {industry.lower()} e ao fluxo do papel no curto prazo."


def _safe_market_context(
    ticker: str,
    labels: list[str],
    sector: str,
    industry: str,
    direct_match: bool,
    ambiguity_score: float,
    locale: str = DEFAULT_NEWS_LOCALE,
) -> str:
    content_locale = normalize_news_locale(locale)
    context = _market_context(ticker, labels, sector, industry, content_locale)
    if content_locale == "en-US":
        if ambiguity_score >= 45:
            return _shorten(f"{context} The headline still has mixed signals and needs price confirmation.", 190)
        if not direct_match:
            return _shorten(f"{context} The effect may reach the sector before {ticker} specifically.", 190)
        return context
    if ambiguity_score >= 45:
        return _shorten(f"{context} Ainda assim, a manchete traz sinais mistos e precisa de confirmação no preço.", 190)
    if not direct_match:
        return _shorten(f"{context} O efeito tende a ser primeiro no setor/mercado e só depois em {ticker}.", 190)
    return context


def _confidence_score(
    ticker: str,
    title: str,
    summary: str,
    source: str,
    related_tickers: list[str],
    labels: list[str],
    entities: list[str],
) -> float:
    score = 30.0
    text = f"{title} {summary}"

    if ticker in text.upper():
        score += 20.0
    if related_tickers:
        score += 10.0
    if labels:
        score += min(20.0, len(labels) * 6.0)
    if len(entities) >= 2:
        score += 10.0
    if source:
        score += 5.0
    if len(title.split()) >= 4:
        score += 5.0
    return max(0.0, min(score, 100.0))


def _adjust_quality_scores(
    confidence: float,
    relevance_score: float,
    directness_score: float,
    ambiguity_score: float,
    same_story_count: int = 1,
) -> tuple[float, float]:
    confidence_adjusted = confidence + ((directness_score - 50.0) * 0.22) - (ambiguity_score * 0.18)
    relevance_adjusted = relevance_score + ((directness_score - 50.0) * 0.16) - (ambiguity_score * 0.24)
    if same_story_count >= 2:
        confidence_adjusted += min(10.0, (same_story_count - 1) * 3.0)
        relevance_adjusted += min(8.0, (same_story_count - 1) * 2.0)
    return (
        round(max(0.0, min(confidence_adjusted, 100.0)), 2),
        round(max(0.0, min(relevance_adjusted, 100.0)), 2),
    )


def _recency_score(published_at: datetime | None) -> float:
    if published_at is None:
        return 40.0
    age_hours = max(0.0, (_now_ts() - published_at.timestamp()) / 3600.0)
    decay = max(0.0, 100.0 - (age_hours * 8.0))
    return min(100.0, max(20.0, decay))


def _relevance_score(labels: list[str], confidence: float, title: str, summary: str, sector: str, ticker: str) -> float:
    base = 10.0
    if labels:
        label_weight = {
            "resultado": 20.0,
            "guidance": 18.0,
            "M&A": 20.0,
            "regulação": 18.0,
            "macro": 14.0,
            "fato relevante": 16.0,
        }
        base += sum(label_weight.get(label, 8.0) for label in labels[:3])
    text = _safe_lower(f"{title} {summary}")
    if any(_text_has_alias(text, alias) for alias in _news_aliases(ticker)):
        base += 18.0
    if sector and sector != "Mercado":
        base += 8.0
    if len(summary.split()) >= 10:
        base += 5.0
    return max(0.0, min((base * 0.6) + (confidence * 0.4), 100.0))

def _should_keep_item(
    relevance_score: float,
    labels: list[str],
    title: str,
    summary: str,
    direct_match: bool,
    ambiguity_score: float,
) -> bool:
    if labels:
        if ambiguity_score >= 70 and not direct_match:
            return False
        return True
    if ambiguity_score >= 60 and not direct_match:
        return False
    if relevance_score >= 55.0:
        return True
    combined = _safe_lower(f"{title} {summary}")
    if any(keyword in combined for keyword in ("announce", "announces", "report", "update", "dividend", "buyback")):
        return True
    return relevance_score >= 35.0


def _normalize_raw_item(
    raw_item: dict[str, Any],
    ticker: str,
    locale: str = DEFAULT_NEWS_LOCALE,
) -> dict[str, Any] | None:
    content_locale = normalize_news_locale(locale)
    title = _extract_title(raw_item)
    summary = _extract_summary(raw_item)

    if not title:
        return None

    source = _extract_source(raw_item)
    url = _extract_url(raw_item)
    related_tickers = _extract_related_tickers(raw_item)
    published_at = _parse_published_at(raw_item)
    detected_ts = _now_ts()
    detected_at = datetime.fromtimestamp(detected_ts, tz=timezone.utc)
    sector, industry = _asset_sector(ticker, f"{title} {summary}")
    labels = _classify_labels(f"{title} {summary}")
    entities = _extract_entities(ticker, title, summary, related_tickers, labels)
    story_key = _story_signature(ticker, title, labels, entities)
    direct_match, directness_score = _ticker_directness(ticker, title, summary, related_tickers)
    bullish_hints, bearish_hints = _impact_hint_balance(f"{title} {summary}", labels)
    impact, impact_reason = _impact_from_keywords(f"{title} {summary}", labels, content_locale)
    ambiguity_score, ambiguity_flags = _ambiguity_analysis(
        f"{title} {summary}",
        labels,
        bullish_hints > 0,
        bearish_hints > 0,
        direct_match,
    )
    confidence = _confidence_score(ticker, title, summary, source, related_tickers, labels, entities)
    relevance_score = _relevance_score(labels, confidence, title, summary, sector, ticker)
    confidence, relevance_score = _adjust_quality_scores(confidence, relevance_score, directness_score, ambiguity_score)
    if ambiguity_score >= 55.0 and not direct_match and impact != "neutral":
        impact = "neutral"
        impact_reason = _canonical_impact_reason(impact, content_locale, ambiguous_indirect=True)
    ranking_score = round((0.38 * _recency_score(published_at)) + (0.42 * relevance_score) + (0.20 * confidence), 2)

    useful = _should_keep_item(relevance_score, labels, title, summary, direct_match, ambiguity_score)

    published_at_source = _to_iso(published_at)
    fetched_at = _to_iso(detected_at)
    source_url = url
    age_minutes = _news_age_minutes(published_at, detected_ts)
    is_today = _is_news_today(published_at, detected_at)
    is_incomplete = published_at is None or not source or not source_url

    return {
        "id": raw_item.get("id") or story_key,
        "ticker": ticker,
        "title": title,
        "original_title": title,
        "summary": summary or title,
        "original_summary": summary or title,
        "content_locale": content_locale,
        "card_summary": _build_card_summary(title, summary, labels, impact, content_locale),
        "source": source,
        "source_name": source,
        "source_domain": _extract_domain(url),
        "url": url,
        "source_url": source_url,
        "published_at": published_at_source,
        "published_at_source": published_at_source,
        "detected_at": fetched_at,
        "fetched_at": fetched_at,
        "age_minutes": age_minutes,
        "is_today": is_today,
        "is_stale": not is_today,
        "source_published_at": bool(published_at),
        "matched_symbol": ticker,
        "language": _detect_news_language(title, summary),
        "publication_status": "ok" if published_at else "missing_source_time",
        "is_incomplete": is_incomplete,
        "sector": sector,
        "industry": industry,
        "labels": labels,
        "entities": entities,
        "related_tickers": related_tickers,
        "impact": impact,
        "impact_label": _impact_label(impact, content_locale),
        "impact_reason": impact_reason,
        "why_it_matters": _build_why_it_matters(ticker, labels, impact, sector, content_locale),
        "editorial": _build_editorial_final(
            ticker,
            labels,
            impact,
            confidence,
            sector,
            ambiguity_score,
            1,
            direct_match,
            content_locale,
        ),
        "market_context": _safe_market_context(
            ticker,
            labels,
            sector,
            industry,
            direct_match,
            ambiguity_score,
            content_locale,
        ),
        "trader_takeaway": _build_trader_takeaway(
            ticker,
            title,
            summary,
            impact,
            labels,
            ambiguity_score,
            direct_match,
            content_locale,
        ),
        "relevance_score": round(relevance_score, 2),
        "relevance": round(relevance_score, 2),
        "ranking_score": ranking_score,
        "confidence_score": round(confidence, 2),
        "direct_ticker_match": direct_match,
        "directness_score": round(directness_score, 2),
        "ambiguity_score": round(ambiguity_score, 2),
        "ambiguity_flags": ambiguity_flags,
        "useful": useful,
        "story_key": story_key,
        "same_story_count": 1,
        "source_count": 1,
        "sources": [source] if source else [],
    }


def _extract_domain(url: str | None) -> str | None:
    if not url:
        return None
    match = re.search(r"https?://([^/]+)/?", url)
    if not match:
        return None
    return match.group(1).lower()


def _sanitize_limit(limit: int) -> int:
    try:
        return max(1, min(int(limit), 20))
    except Exception:
        return 6


def _news_ticker_candidates(ticker: str) -> list[str]:
    normalized = _normalize_ticker(ticker)
    if not normalized:
        return []

    candidates = [normalized]
    provider_candidate = provider_symbol(normalized)
    if provider_candidate and provider_candidate != normalized:
        candidates.append(provider_candidate)
    if "." not in normalized and "-" not in normalized and normalized[-1:].isdigit():
        candidates.append(f"{normalized}.SA")
    if normalized.endswith(".SA"):
        candidates.append(normalized.removesuffix(".SA"))

    unique_candidates: list[str] = []
    for candidate in candidates:
        candidate = _clean_whitespace(str(candidate or "")).upper().replace(" ", "")
        if candidate and candidate not in unique_candidates:
            unique_candidates.append(candidate)
    return unique_candidates


def _raw_item_signature(raw_item: dict[str, Any]) -> str:
    title = _extract_title(raw_item)
    summary = _extract_summary(raw_item)
    url = _extract_url(raw_item) or ""
    source = _extract_source(raw_item)
    published_at = _parse_published_at(raw_item)
    published_key = _to_iso(published_at) or ""
    core = "|".join(
        [
            _slugify(title),
            _slugify(summary),
            _normalize_ticker(source),
            url,
            published_key,
        ]
    )
    return hashlib.sha1(core.encode("utf-8")).hexdigest()


def _prepare_raw_items(raw_items: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    if not isinstance(raw_items, list) or not raw_items:
        return []

    cap = min(len(raw_items), _NEWS_MAX_INPUT_ITEMS, max(limit * 8, 40))
    prepared: list[dict[str, Any]] = []
    seen_signatures: set[str] = set()

    for raw_item in raw_items[:cap]:
        if not isinstance(raw_item, dict):
            continue

        title = _extract_title(raw_item)
        summary = _extract_summary(raw_item)
        if not title and not summary:
            continue

        signature = _raw_item_signature(raw_item)
        if signature in seen_signatures:
            continue
        seen_signatures.add(signature)
        prepared.append(raw_item)

    return prepared


def _fetch_yfinance_news(ticker: str) -> list[dict[str, Any]]:
    if str(os.getenv("MARKET_PROVIDER_NETWORK_DISABLED") or "").strip().lower() in {"1", "true", "yes", "on"}:
        _remember_news_provider_status(ticker, "network_disabled")
        return []
    yf = _get_yfinance()
    if yf is None:
        _remember_news_provider_status(ticker, "dependency_unavailable", error="dependency_unavailable")
        record_external_provider_call("yfinance", "news", success=False, symbol=ticker, error="dependency_unavailable")
        return []

    start = time.perf_counter()
    try:
        ticker_obj = yf.Ticker(ticker)
        raw_items = getattr(ticker_obj, "news", None) or []
        if not isinstance(raw_items, list):
            duration = time.perf_counter() - start
            _remember_news_provider_status(ticker, "invalid_payload", error="invalid_payload")
            record_external_provider_call("yfinance", "news", duration_seconds=duration, success=False, symbol=ticker, error="invalid_payload")
            record_worker_stage_duration("news", duration, success=False)
            return []
        items = [item for item in raw_items if isinstance(item, dict)]
        duration = time.perf_counter() - start
        _remember_news_provider_status(ticker, "ok" if items else "empty_response", raw_count=len(items))
        record_external_provider_call("yfinance", "news", duration_seconds=duration, success=True, symbol=ticker)
        record_worker_stage_duration("news", duration, success=True)
        return items
    except Exception as exc:  # pragma: no cover - provider instability.
        duration = time.perf_counter() - start
        _remember_news_provider_status(ticker, "provider_error", error=str(exc))
        record_external_provider_call("yfinance", "news", duration_seconds=duration, success=False, symbol=ticker, error=str(exc))
        record_worker_stage_duration("news", duration, success=False)
        logger.warning("Yahoo news fetch failed for %s: %s", ticker, exc)
        return []


def _cluster_news(
    items: list[dict[str, Any]],
    locale: str = DEFAULT_NEWS_LOCALE,
) -> list[dict[str, Any]]:
    content_locale = normalize_news_locale(locale)
    clusters: list[dict[str, Any]] = []
    story_index: dict[str, dict[str, Any]] = {}
    token_index: dict[str, list[dict[str, Any]]] = {}

    for item in items:
        if not item.get("useful", True):
            cluster = {
                "cluster_id": len(clusters),
                "canonical": item,
                "items": [item],
                "score": item.get("ranking_score", 0.0),
                "token_keys": set(),
            }
            clusters.append(cluster)
            continue

        story_key = str(item.get("story_key") or "")
        candidate_clusters: list[dict[str, Any]] = []
        candidate_ids: set[int] = set()

        if story_key and story_key in story_index:
            matched = story_index[story_key]
            candidate_clusters.append(matched)
            candidate_ids.add(int(matched["cluster_id"]))

        token_keys = _cluster_key_tokens(item)
        for token in token_keys:
            for cluster in token_index.get(token, []):
                cluster_id = int(cluster["cluster_id"])
                if cluster_id in candidate_ids:
                    continue
                candidate_ids.add(cluster_id)
                candidate_clusters.append(cluster)
                if len(candidate_clusters) >= _NEWS_MAX_CLUSTER_CANDIDATES:
                    break
            if len(candidate_clusters) >= _NEWS_MAX_CLUSTER_CANDIDATES:
                break

        matched_cluster = None
        for cluster in candidate_clusters:
            canonical = cluster["canonical"]
            same_story = item["story_key"] == canonical["story_key"]
            similarity = _headline_similarity(item["title"], canonical["title"])
            token_overlap = 0.0
            if item["title"] and canonical["title"]:
                left_tokens = set(_token_set(item["title"]))
                right_tokens = set(_token_set(canonical["title"]))
                if left_tokens and right_tokens:
                    token_overlap = len(left_tokens & right_tokens) / max(1, min(len(left_tokens), len(right_tokens)))
            if same_story or similarity >= 0.86 or token_overlap >= 0.7:
                matched_cluster = cluster
                break

        if matched_cluster is None:
            cluster = {
                "cluster_id": len(clusters),
                "canonical": item,
                "items": [item],
                "score": item.get("ranking_score", 0.0),
                "token_keys": set(token_keys),
            }
            clusters.append(cluster)
            if story_key:
                story_index[story_key] = cluster
            for token in token_keys:
                token_index.setdefault(token, []).append(cluster)
            continue

        matched_cluster["items"].append(item)
        if item.get("ranking_score", 0.0) > matched_cluster["canonical"].get("ranking_score", 0.0):
            matched_cluster["canonical"] = item
        if story_key:
            story_index[story_key] = matched_cluster
        new_tokens = set(token_keys) - set(matched_cluster.get("token_keys", set()))
        if new_tokens:
            matched_cluster.setdefault("token_keys", set()).update(new_tokens)
            for token in new_tokens:
                token_index.setdefault(token, []).append(matched_cluster)

    results: list[dict[str, Any]] = []

    for cluster in clusters:
        canonical = dict(cluster["canonical"])
        sources = [str(entry.get("source") or "").strip() for entry in cluster["items"] if str(entry.get("source") or "").strip()]
        unique_sources = list(dict.fromkeys(sources))
        canonical["same_story_count"] = len(cluster["items"])
        canonical["source_count"] = len(unique_sources) or 1
        canonical["sources"] = unique_sources
        canonical["duplicate_titles"] = [entry["title"] for entry in cluster["items"] if entry["title"] != canonical["title"]]
        confidence, relevance_score = _adjust_quality_scores(
            float(canonical.get("confidence_score", 0.0) or 0.0),
            float(canonical.get("relevance_score", 0.0) or 0.0),
            float(canonical.get("directness_score", 50.0) or 50.0),
            float(canonical.get("ambiguity_score", 0.0) or 0.0),
            same_story_count=len(cluster["items"]),
        )
        canonical["confidence_score"] = confidence
        canonical["relevance_score"] = relevance_score
        canonical["ranking_score"] = round(
            (0.38 * _recency_score(_parse_published_at(canonical))) + (0.42 * relevance_score) + (0.20 * confidence),
            2,
        )
        canonical["editorial"] = _build_editorial_final(
            str(canonical.get("ticker") or ""),
            list(canonical.get("labels") or []),
            str(canonical.get("impact") or "neutral"),
            confidence,
            str(canonical.get("sector") or "Mercado"),
            float(canonical.get("ambiguity_score", 0.0) or 0.0),
            canonical["source_count"],
            bool(canonical.get("direct_ticker_match")),
            content_locale,
        )
        canonical["trader_takeaway"] = _build_trader_takeaway(
            str(canonical.get("ticker") or ""),
            str(canonical.get("title") or ""),
            str(canonical.get("summary") or ""),
            str(canonical.get("impact") or "neutral"),
            list(canonical.get("labels") or []),
            float(canonical.get("ambiguity_score", 0.0) or 0.0),
            bool(canonical.get("direct_ticker_match")),
            content_locale,
        )
        canonical["content_locale"] = content_locale
        results.append(canonical)

    return results


def build_symbol_news(
    ticker: str,
    raw_items: list[dict[str, Any]],
    limit: int = 6,
    locale: str = DEFAULT_NEWS_LOCALE,
) -> list[dict[str, Any]]:
    items, _report = build_symbol_news_with_report(ticker, raw_items, limit=limit, locale=locale)
    return items


def build_symbol_news_with_report(
    ticker: str,
    raw_items: list[dict[str, Any]],
    limit: int = 6,
    locale: str = DEFAULT_NEWS_LOCALE,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    normalized_ticker = _normalize_ticker(ticker)
    content_locale = normalize_news_locale(locale)
    limit = _sanitize_limit(limit)
    original_raw_count = len(raw_items) if isinstance(raw_items, list) else 0
    reason_counts: Counter[str] = Counter()
    if isinstance(raw_items, list):
        for raw_item in raw_items[: min(len(raw_items), _NEWS_MAX_INPUT_ITEMS, max(limit * 8, 40))]:
            if not isinstance(raw_item, dict):
                reason_counts["provider_invalid"] += 1
                continue
            if not _extract_title(raw_item) and not _extract_summary(raw_item):
                reason_counts["missing_title"] += 1
    raw_items = _prepare_raw_items(raw_items, limit)
    prepared_count = len(raw_items)
    if original_raw_count > prepared_count:
        explained = sum(reason_counts.values())
        duplicate_count = max(0, original_raw_count - prepared_count - explained)
        if duplicate_count:
            reason_counts["duplicate"] += duplicate_count
    normalized_items = []

    for raw_item in raw_items or []:
        if not isinstance(raw_item, dict):
            reason_counts["provider_invalid"] += 1
            continue
        candidate = _normalize_raw_item(raw_item, normalized_ticker, content_locale)
        if candidate is None:
            reason_counts["missing_title"] += 1
            continue
        normalized_items.append(candidate)

    if not normalized_items:
        reason = reason_counts.most_common(1)[0][0] if reason_counts else ("provider_invalid" if original_raw_count else "no_raw_news")
        return [], {
            "ticker": normalized_ticker,
            "locale": content_locale,
            "status": "empty",
            "reason": reason,
            "raw_count": original_raw_count,
            "prepared_count": prepared_count,
            "normalized_count": 0,
            "output_count": 0,
            "discard_reasons": dict(reason_counts),
        }

    normalized_items.sort(
        key=lambda item: (
            item.get("published_at") or "",
            float(item.get("ranking_score", 0.0) or 0.0),
        ),
        reverse=True,
    )

    clustered = _cluster_news(normalized_items, content_locale)

    ordered = list(clustered)
    def _priority_key(item: dict[str, Any]) -> tuple[Any, ...]:
        labels = {str(label).lower() for label in item.get("labels", []) if label}
        direct_match = 1 if item.get("direct_ticker_match") else 0
        editorial_priority = 0
        if labels.intersection({"resultado", "guidance", "fato relevante", "regulacao", "m&a"}):
            editorial_priority += 2
        if labels.intersection({"macro", "juros", "inflacao"}) and not direct_match:
            editorial_priority -= 1
        return (
            1 if item.get("useful", True) else 0,
            direct_match,
            editorial_priority,
            float(item.get("relevance_score", 0.0) or 0.0),
            float(item.get("confidence_score", 0.0) or 0.0),
            float(item.get("ranking_score", 0.0) or 0.0),
            item.get("published_at") or "",
        )

    ordered.sort(
        key=_priority_key,
        reverse=True,
    )

    output: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for item in ordered:
        item_id = str(item.get("id") or item.get("story_key") or "")
        if not item_id:
            continue
        if item_id in seen_ids:
            continue
        seen_ids.add(item_id)
        output.append(item)
        if len(output) >= limit:
            break

    # _priority_key decides WHICH stories make the cut (editorial value); the feed itself
    # must be chronological, newest first, and must not inherit the provider's order.
    # published_at is always _to_iso() UTC, so the string sort is the chronological sort;
    # items without a source publication time sort last instead of masquerading as new.
    output.sort(
        key=lambda item: (
            item.get("published_at") or "",
            float(item.get("ranking_score", 0.0) or 0.0),
        ),
        reverse=True,
    )

    report_status = "ok" if output else "empty"
    reason = None if output else (reason_counts.most_common(1)[0][0] if reason_counts else "filtered_by_quality")
    return output, {
        "ticker": normalized_ticker,
        "locale": content_locale,
        "status": report_status,
        "reason": reason,
        "raw_count": original_raw_count,
        "prepared_count": prepared_count,
        "normalized_count": len(normalized_items),
        "output_count": len(output),
        "discard_reasons": dict(reason_counts),
    }


def _localized_impact_reason(item: dict[str, Any], locale: str) -> str:
    impact = str(item.get("impact") or "neutral")
    ambiguity_score = float(item.get("ambiguity_score", 0.0) or 0.0)
    direct_match = bool(item.get("direct_ticker_match"))
    if ambiguity_score >= 55.0 and not direct_match:
        return _canonical_impact_reason(impact, locale, ambiguous_indirect=True)
    return _canonical_impact_reason(impact, locale)


def _localize_cached_news_item(item: dict[str, Any], locale: str) -> dict[str, Any]:
    content_locale = normalize_news_locale(locale)
    localized = copy.deepcopy(item)
    original_title = str(localized.get("original_title") or localized.get("title") or localized.get("headline") or "").strip()
    original_summary = str(localized.get("original_summary") or localized.get("summary") or original_title).strip()
    ticker = str(localized.get("ticker") or localized.get("matched_symbol") or "")
    labels = list(localized.get("labels") or [])
    impact = str(localized.get("impact") or "neutral")
    sector = str(localized.get("sector") or "Mercado")
    industry = str(localized.get("industry") or "Geral")
    confidence = float(localized.get("confidence_score", 0.0) or 0.0)
    ambiguity_score = float(localized.get("ambiguity_score", 0.0) or 0.0)
    direct_match = bool(localized.get("direct_ticker_match"))
    source_count = max(1, int(localized.get("source_count", 1) or 1))

    localized["title"] = original_title
    if "headline" in localized:
        localized["headline"] = original_title
    localized["original_title"] = original_title
    localized["summary"] = original_summary or original_title
    localized["original_summary"] = original_summary or original_title
    localized["language"] = localized.get("language") or _detect_news_language(original_title, original_summary)
    localized["content_locale"] = content_locale
    localized["card_summary"] = _build_card_summary(original_title, original_summary, labels, impact, content_locale)
    localized["impact_label"] = _impact_label(impact, content_locale)
    localized["impact_reason"] = _localized_impact_reason(localized, content_locale)
    localized["why_it_matters"] = _build_why_it_matters(ticker, labels, impact, sector, content_locale)
    localized["editorial"] = _build_editorial_final(
        ticker,
        labels,
        impact,
        confidence,
        sector,
        ambiguity_score,
        source_count,
        direct_match,
        content_locale,
    )
    localized["market_context"] = _safe_market_context(
        ticker,
        labels,
        sector,
        industry,
        direct_match,
        ambiguity_score,
        content_locale,
    )
    localized["trader_takeaway"] = _build_trader_takeaway(
        ticker,
        original_title,
        original_summary,
        impact,
        labels,
        ambiguity_score,
        direct_match,
        content_locale,
    )
    return localized


def _localize_cached_news_items(items: list[dict[str, Any]], locale: str) -> list[dict[str, Any]]:
    return [
        _localize_cached_news_item(item, locale)
        for item in items
        if isinstance(item, dict)
    ]


def _localized_cache_entry(source_entry: dict[str, Any], ticker: str, locale: str) -> dict[str, Any]:
    content_locale = normalize_news_locale(locale)
    localized_entry = copy.deepcopy(source_entry)
    localized_items = _localize_cached_news_items(list(source_entry.get("items") or []), content_locale)
    localized_entry["locale"] = content_locale
    localized_entry["items"] = localized_items
    localized_entry["report"] = build_news_intelligence_report(
        ticker,
        localized_items,
        locale=content_locale,
    )
    return localized_entry


def get_symbol_news(
    ticker: str,
    limit: int = 6,
    locale: str = DEFAULT_NEWS_LOCALE,
) -> list[dict[str, Any]]:
    _load_news_cache_once()
    normalized_ticker = _normalize_ticker(ticker)
    if not normalized_ticker:
        return []

    content_locale = normalize_news_locale(locale)
    limit = _sanitize_limit(limit)
    now = _now_ts()

    def is_fresh(entry: dict[str, Any] | None) -> bool:
        return bool(
            entry
            and entry.get("items")
            and now - float(entry.get("timestamp", 0.0) or 0.0) < _CACHE_TTL_SECONDS
        )

    with _CACHE_LOCK:
        cached = _get_news_cache_entry_locked(normalized_ticker, content_locale)
        if is_fresh(cached):
            return copy.deepcopy(list(cached.get("items", []))[:limit])
        alternate = _latest_news_cache_entry_locked(normalized_ticker, exclude_locale=content_locale)
        if is_fresh(alternate):
            localized_entry = _localized_cache_entry(alternate, normalized_ticker, content_locale)
            _set_news_cache_entry_locked(normalized_ticker, content_locale, localized_entry)
            return copy.deepcopy(localized_entry["items"][:limit])

    request_lock = _get_request_lock(normalized_ticker)
    with request_lock:
        with _CACHE_LOCK:
            cached = _get_news_cache_entry_locked(normalized_ticker, content_locale)
            if is_fresh(cached):
                return copy.deepcopy(list(cached.get("items", []))[:limit])
            alternate = _latest_news_cache_entry_locked(normalized_ticker, exclude_locale=content_locale)
            if is_fresh(alternate):
                localized_entry = _localized_cache_entry(alternate, normalized_ticker, content_locale)
                _set_news_cache_entry_locked(normalized_ticker, content_locale, localized_entry)
                return copy.deepcopy(localized_entry["items"][:limit])

        raw_items: list[dict[str, Any]] = []
        fetched_from = normalized_ticker
        attempted_candidates = _news_ticker_candidates(normalized_ticker)
        for candidate in attempted_candidates:
            raw_items = _fetch_yfinance_news(candidate)
            if raw_items:
                fetched_from = candidate
                if candidate != normalized_ticker:
                    logger.info("News service resolved %s via candidate %s", normalized_ticker, candidate)
                break
        items, filter_report = build_symbol_news_with_report(
            normalized_ticker,
            raw_items,
            limit=limit,
            locale=content_locale,
        )
        provider_meta = _latest_news_provider_status(
            fetched_from if raw_items else (attempted_candidates[-1] if attempted_candidates else normalized_ticker)
        )
        cache_status = "ok"
        fallback_used = False

        if not items:
            stale_items: list[dict[str, Any]] | None = None
            with _CACHE_LOCK:
                cached = _get_news_cache_entry_locked(normalized_ticker, content_locale)
                if not cached or not cached.get("items"):
                    alternate = _latest_news_cache_entry_locked(normalized_ticker, exclude_locale=content_locale)
                    cached = _localized_cache_entry(alternate, normalized_ticker, content_locale) if alternate and alternate.get("items") else None
                if cached and cached.get("items"):
                    logger.info("News service using stale cache for %s after empty provider response", normalized_ticker)
                    fallback_used = True
                    cache_status = "stale_fallback"
                    fallback_entry = copy.deepcopy(cached)
                    fallback_entry["checked_at"] = now
                    fallback_entry["status"] = cache_status
                    fallback_entry["fallback_used"] = True
                    fallback_entry["fetched_from"] = "stale_cache"
                    fallback_entry["provider"] = "yfinance"
                    fallback_entry["provider_status"] = provider_meta.get("status")
                    fallback_entry["provider_error"] = provider_meta.get("error")
                    fallback_entry["attempted_candidates"] = attempted_candidates
                    _set_news_cache_entry_locked(normalized_ticker, content_locale, fallback_entry)
                    stale_items = copy.deepcopy(list(fallback_entry.get("items", []))[:limit])
            if stale_items is not None:
                _persist_news_cache()
                return stale_items
            cache_status = "empty"

        intelligence_report = build_news_intelligence_report(normalized_ticker, items, locale=content_locale)

        with _CACHE_LOCK:
            cache_entry = {
                "timestamp": now,
                "checked_at": now,
                "locale": content_locale,
                "items": copy.deepcopy(items),
                "raw_count": len(raw_items),
                "status": cache_status,
                "fallback_used": fallback_used,
                "fetched_from": fetched_from if raw_items else "cache_or_empty",
                "provider": "yfinance",
                "provider_status": provider_meta.get("status"),
                "provider_error": provider_meta.get("error"),
                "attempted_candidates": attempted_candidates,
                "filter_report": filter_report,
                "discard_reasons": filter_report.get("discard_reasons", {}),
                "discard_reason": filter_report.get("reason"),
                "report": intelligence_report,
            }
            _set_news_cache_entry_locked(normalized_ticker, content_locale, cache_entry)

        _persist_news_cache()

        return copy.deepcopy(items)


def get_cached_symbol_news(
    ticker: str,
    limit: int = 6,
    locale: str = DEFAULT_NEWS_LOCALE,
) -> list[dict[str, Any]]:
    _load_news_cache_once()
    start = time.perf_counter()
    normalized_ticker = _normalize_ticker(ticker)
    if not normalized_ticker:
        record_cache_lookup("news", time.perf_counter() - start, len(_NEWS_CACHE))
        return []

    content_locale = normalize_news_locale(locale)
    limit = _sanitize_limit(limit)
    with _CACHE_LOCK:
        cached = _get_news_cache_entry_locked(normalized_ticker, content_locale)
        if cached is None:
            alternate = _latest_news_cache_entry_locked(normalized_ticker, exclude_locale=content_locale)
            if alternate is not None:
                cached = _localized_cache_entry(alternate, normalized_ticker, content_locale)
                _set_news_cache_entry_locked(normalized_ticker, content_locale, cached)

        items = cached.get("items") if isinstance(cached, dict) else None
        if not isinstance(items, list):
            record_cache_access("news", False, "memory")
            record_cache_lookup("news", time.perf_counter() - start, len(_NEWS_CACHE))
            return []

        record_cache_access("news", bool(items), "memory")
        record_cache_lookup("news", time.perf_counter() - start, len(_NEWS_CACHE))
        return copy.deepcopy(list(items)[:limit])


def get_news_cached_report(
    ticker: str,
    items: list[dict[str, Any]] | None = None,
    locale: str = DEFAULT_NEWS_LOCALE,
) -> dict[str, Any]:
    normalized_ticker = _normalize_ticker(ticker)
    content_locale = normalize_news_locale(locale)
    with _CACHE_LOCK:
        cached = _get_news_cache_entry_locked(normalized_ticker, content_locale)
        report = cached.get("report") if isinstance(cached, dict) else None
        if isinstance(report, dict):
            return copy.deepcopy(report)
    _load_news_cache_once()
    with _CACHE_LOCK:
        cached = _get_news_cache_entry_locked(normalized_ticker, content_locale)
        if cached is None:
            alternate = _latest_news_cache_entry_locked(normalized_ticker, exclude_locale=content_locale)
            if alternate is not None:
                cached = _localized_cache_entry(alternate, normalized_ticker, content_locale)
                _set_news_cache_entry_locked(normalized_ticker, content_locale, cached)
        report = cached.get("report") if isinstance(cached, dict) else None
        if isinstance(report, dict):
            return copy.deepcopy(report)
    return build_news_intelligence_report(normalized_ticker, items or [], locale=content_locale)


def build_news_quality_report(ticker: str, items: list[dict[str, Any]]) -> dict[str, Any]:
    normalized_ticker = _normalize_ticker(ticker)
    label_counter: Counter[str] = Counter()
    useful_count = 0
    ambiguous_count = 0
    direct_count = 0

    for item in items or []:
        label_counter.update(str(label) for label in item.get("labels", []) if label)
        if item.get("useful", True):
            useful_count += 1
        if float(item.get("ambiguity_score", 0.0) or 0.0) >= 45.0:
            ambiguous_count += 1
        if item.get("direct_ticker_match"):
            direct_count += 1

    avg_ranking = round(
        sum(float(item.get("ranking_score", 0.0) or 0.0) for item in items or []) / max(1, len(items or [])),
        2,
    )
    avg_confidence = round(
        sum(float(item.get("confidence_score", 0.0) or 0.0) for item in items or []) / max(1, len(items or [])),
        2,
    )

    return {
        "ticker": normalized_ticker,
        "count": len(items or []),
        "useful_count": useful_count,
        "ambiguous_count": ambiguous_count,
        "direct_count": direct_count,
        "avg_ranking_score": avg_ranking,
        "avg_confidence_score": avg_confidence,
        "top_labels": [label for label, _ in label_counter.most_common(5)],
    }


def build_news_intelligence_report(
    ticker: str,
    items: list[dict[str, Any]],
    locale: str = DEFAULT_NEWS_LOCALE,
) -> dict[str, Any]:
    content_locale = normalize_news_locale(locale)
    quality = build_news_quality_report(ticker, items)
    normalized_ticker = quality["ticker"]

    if not items:
        return {
            **quality,
            "locale": content_locale,
            "status": "empty",
            "dominant_labels": [],
            "dominant_sector": "Market" if content_locale == "en-US" else "Mercado",
            "dominant_industry": "General" if content_locale == "en-US" else "Geral",
            "dominant_impact": "neutral",
            "top_story_key": None,
            "top_story_title": "",
            "editorial_summary": "",
            "why_it_matters": "",
            "market_context": "",
            "trader_takeaway": "",
            "alert_level": "low",
            "story_count": 0,
            "unique_story_count": 0,
            "source_count": 0,
        }

    label_counter: Counter[str] = Counter()
    sector_counter: Counter[str] = Counter()
    industry_counter: Counter[str] = Counter()
    impact_counter: Counter[str] = Counter()
    story_counter: Counter[str] = Counter()
    source_counter: Counter[str] = Counter()
    direct_count = 0
    ambiguous_count = 0

    for item in items:
        label_counter.update(str(label) for label in item.get("labels", []) if label)
        sector_counter.update([str(item.get("sector") or "Mercado")])
        industry_counter.update([str(item.get("industry") or "Geral")])
        impact_counter.update([str(item.get("impact") or "neutral")])
        story_key = str(item.get("story_key") or item.get("id") or "")
        if story_key:
            story_counter.update([story_key])
        source_counter.update(str(source) for source in item.get("sources", []) if source)
        if item.get("direct_ticker_match"):
            direct_count += 1
        if float(item.get("ambiguity_score", 0.0) or 0.0) >= 45.0:
            ambiguous_count += 1

    top_item = max(items, key=lambda item: float(item.get("ranking_score", 0.0) or 0.0))
    total = max(1, len(items))
    dominant_labels = [label for label, _ in label_counter.most_common(4)]
    dominant_sector = sector_counter.most_common(1)[0][0] if sector_counter else "Mercado"
    dominant_industry = industry_counter.most_common(1)[0][0] if industry_counter else "Geral"
    dominant_impact = impact_counter.most_common(1)[0][0] if impact_counter else "neutral"
    unique_story_count = len(story_counter)
    repeated_story_count = sum(count - 1 for count in story_counter.values() if count > 1)
    source_total = sum(source_counter.values()) or len(items)
    alert_level = "low"
    if ambiguous_count / total >= 0.5 or quality["avg_confidence_score"] < 45:
        alert_level = "high"
    elif quality["avg_confidence_score"] < 60 or repeated_story_count > 0:
        alert_level = "medium"

    return {
        **quality,
        "ticker": normalized_ticker,
        "locale": content_locale,
        "status": "ok",
        "dominant_labels": dominant_labels,
        "dominant_sector": dominant_sector,
        "dominant_industry": dominant_industry,
        "dominant_impact": dominant_impact,
        "top_story_key": str(top_item.get("story_key") or top_item.get("id") or ""),
        "top_story_title": str(top_item.get("title") or ""),
        "top_story_editorial": str(top_item.get("editorial") or ""),
        "editorial_summary": str(top_item.get("card_summary") or top_item.get("summary") or ""),
        "why_it_matters": str(top_item.get("why_it_matters") or ""),
        "market_context": str(top_item.get("market_context") or ""),
        "trader_takeaway": str(top_item.get("trader_takeaway") or ""),
        "alert_level": alert_level,
        "story_count": len(items),
        "unique_story_count": unique_story_count,
        "repeated_story_count": repeated_story_count,
        "source_count": source_total,
        "direct_count": direct_count,
        "direct_ratio": round(direct_count / total, 2),
        "ambiguous_ratio": round(ambiguous_count / total, 2),
        "source_mix": [source for source, _ in source_counter.most_common(4)],
    }


def _get_request_lock(ticker: str) -> threading.Lock:
    normalized_ticker = _normalize_ticker(ticker)
    with _REQUEST_LOCKS_LOCK:
        lock = _REQUEST_LOCKS.get(normalized_ticker)
        if lock is None:
            lock = threading.Lock()
            _REQUEST_LOCKS[normalized_ticker] = lock
        return lock


def get_news_cache_info(
    ticker: str,
    locale: str = DEFAULT_NEWS_LOCALE,
) -> dict[str, Any]:
    _load_news_cache_once()
    normalized_ticker = _normalize_ticker(ticker)
    content_locale = normalize_news_locale(locale)
    now = _now_ts()
    provider_meta = _latest_news_provider_status(normalized_ticker)
    with _CACHE_LOCK:
        cached = _get_news_cache_entry_locked(normalized_ticker, content_locale)
        if cached is None:
            alternate = _latest_news_cache_entry_locked(normalized_ticker, exclude_locale=content_locale)
            if alternate is not None:
                cached = _localized_cache_entry(alternate, normalized_ticker, content_locale)
                _set_news_cache_entry_locked(normalized_ticker, content_locale, cached)
        available_locales = _available_news_cache_locales_locked(normalized_ticker)
        if not cached:
            provider_raw_count = int(provider_meta.get("raw_count", 0) or 0)
            return {
                "ticker": normalized_ticker,
                "locale": content_locale,
                "available_locales": available_locales,
                "status": "cold",
                "timestamp": None,
                "checked_at": provider_meta.get("checked_at"),
                "age_seconds": None,
                "items": 0,
                "raw_count": provider_raw_count,
                "provider": "yfinance",
                "provider_status": provider_meta.get("status"),
                "provider_error": provider_meta.get("error"),
                "attempted_candidates": [],
                "discard_reason": "cache_missing_after_provider_raw" if provider_raw_count > 0 else None,
                "discard_reasons": {"cache_missing_after_provider_raw": provider_raw_count} if provider_raw_count > 0 else {},
            }

        timestamp = float(cached.get("timestamp", 0.0) or 0.0)
        age_seconds = max(0, int(now - timestamp)) if timestamp else None
        return {
            "ticker": normalized_ticker,
            "locale": content_locale,
            "available_locales": available_locales,
            "status": str(cached.get("status") or ("stale" if age_seconds and age_seconds >= _CACHE_TTL_SECONDS else "warm")),
            "timestamp": timestamp or None,
            "checked_at": cached.get("checked_at") or provider_meta.get("checked_at"),
            "age_seconds": age_seconds,
            "items": len(cached.get("items", [])),
            "raw_count": int(cached.get("raw_count", 0) or 0),
            "fetched_from": cached.get("fetched_from"),
            "fallback_used": bool(cached.get("fallback_used")),
            "provider": cached.get("provider") or "yfinance",
            "provider_status": cached.get("provider_status") or "not_checked",
            "provider_error": cached.get("provider_error"),
            "attempted_candidates": list(cached.get("attempted_candidates") or []),
            "filter_report": cached.get("filter_report") if isinstance(cached.get("filter_report"), dict) else {},
            "discard_reason": cached.get("discard_reason"),
            "discard_reasons": cached.get("discard_reasons") if isinstance(cached.get("discard_reasons"), dict) else {},
        }


def compare_news_runs(previous_items: list[dict[str, Any]], current_items: list[dict[str, Any]]) -> dict[str, Any]:
    previous_map = {str(item.get("story_key") or item.get("id") or ""): item for item in previous_items or [] if str(item.get("story_key") or item.get("id") or "")}
    current_map = {str(item.get("story_key") or item.get("id") or ""): item for item in current_items or [] if str(item.get("story_key") or item.get("id") or "")}

    previous_keys = set(previous_map)
    current_keys = set(current_map)
    common_keys = previous_keys & current_keys

    ranking_moves: list[dict[str, Any]] = []
    for key in common_keys:
        previous_score = float(previous_map[key].get("ranking_score", 0.0) or 0.0)
        current_score = float(current_map[key].get("ranking_score", 0.0) or 0.0)
        delta = round(current_score - previous_score, 2)
        if abs(delta) >= 5.0:
            ranking_moves.append(
                {
                    "story_key": key,
                    "title": current_map[key].get("title") or previous_map[key].get("title") or "",
                    "delta": delta,
                }
            )

    ranking_moves.sort(key=lambda item: abs(float(item.get("delta", 0.0) or 0.0)), reverse=True)

    return {
        "added_story_keys": sorted(current_keys - previous_keys),
        "removed_story_keys": sorted(previous_keys - current_keys),
        "ranking_moves": ranking_moves[:10],
        "same_story_count": len(common_keys),
    }
