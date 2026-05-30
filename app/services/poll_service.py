import json
import logging
import threading
import time
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from hashlib import blake2b
from pathlib import Path
from typing import Any, Dict, List

from app.cache.snapshot_cache import get_snapshot_by_ticker
from app.config import CRYPTO_SYMBOLS

logger = logging.getLogger("stocknewsbr.polls")

POLL_STORE_PATH = Path("runtime/polls/weekly_polls.json")
MAX_POLLS = 2000
MAX_POLL_VARIANTS = 3
POLL_SCHEMA_VERSION = 2
_lock = threading.RLock()
_store_cache: Dict[str, Any] = {"path": "", "mtime": 0.0, "data": {"polls": {}}}
_crypto_symbols = {str(symbol).upper().strip() for symbol in CRYPTO_SYMBOLS}


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _week_key(now: datetime | None = None) -> str:
    current = now or _utc_now()
    iso = current.isocalendar()
    return f"{iso.year}-W{iso.week:02d}"


def _week_expiration(week_key: str) -> str:
    try:
        year_part, week_part = week_key.split("-W", 1)
        start = datetime.fromisocalendar(int(year_part), int(week_part), 1).replace(tzinfo=UTC)
        return (start + timedelta(days=7)).isoformat()
    except Exception:
        return _utc_now().isoformat()


def _poll_id(symbol: str, week_key: str) -> str:
    return f"{week_key}:{symbol.upper()}"


def _ensure_store_path():
    POLL_STORE_PATH.parent.mkdir(parents=True, exist_ok=True)


def _normalize_symbol(symbol: str | None) -> str:
    return str(symbol or "").upper().strip()


def _normalize_store(store: Any) -> Dict[str, Any]:
    if not isinstance(store, dict):
        return {"polls": {}}

    normalized = dict(store)
    polls = normalized.get("polls")

    if not isinstance(polls, dict):
        polls = {}

    normalized["polls"] = polls
    return normalized


def _poll_symbol_from_key(poll_key: str, poll: Dict[str, Any]) -> str:
    symbol = _normalize_symbol(poll.get("symbol") or poll.get("ticker"))
    if symbol:
        return symbol

    if isinstance(poll_key, str) and ":" in poll_key:
        return _normalize_symbol(poll_key.split(":", 1)[-1])

    return _normalize_symbol(poll_key)


def _migrate_legacy_store(store: Dict[str, Any]) -> tuple[Dict[str, Any], bool]:
    store = _normalize_store(store)
    polls = store.get("polls", {})
    migrated = False

    if not isinstance(polls, dict):
        return {"polls": {}}, False

    for poll_key, poll in list(polls.items()):
        if not isinstance(poll, dict):
            continue

        schema_version = int(poll.get("schema_version") or 0)
        needs_upgrade = schema_version < POLL_SCHEMA_VERSION
        needs_upgrade = needs_upgrade or not isinstance(poll.get("report"), dict)
        needs_upgrade = needs_upgrade or not isinstance(poll.get("context"), dict)
        needs_upgrade = needs_upgrade or not isinstance(poll.get("question_variants"), list)

        if not needs_upgrade:
            continue

        upgraded = _upgrade_poll_record_with_touch(
            poll,
            _poll_symbol_from_key(poll_key, poll),
            signal=None,
            touch_updated_at=False,
        )

        if not isinstance(upgraded.get("quality"), dict):
            context = upgraded.get("context") or {}
            upgraded["quality"] = {
                "score": int(context.get("quality_score") or 0),
                "reason": context.get("insight") or "",
            }

        if upgraded != poll:
            polls[poll_key] = upgraded
            migrated = True

    if migrated:
        store["polls"] = polls

    return store, migrated


def _load_store() -> Dict[str, Any]:
    _ensure_store_path()

    if not POLL_STORE_PATH.exists():
        return {"polls": {}}

    try:
        mtime = POLL_STORE_PATH.stat().st_mtime
    except OSError:
        return {"polls": {}}

    with _lock:
        cache_path = str(POLL_STORE_PATH)
        cached_path = str(_store_cache.get("path") or "")
        cached_mtime = float(_store_cache.get("mtime") or 0.0)
        cached_data = _store_cache.get("data")
        if cached_path == cache_path and cached_mtime == mtime and isinstance(cached_data, dict):
            store, migrated = _migrate_legacy_store(deepcopy(cached_data))
            if migrated:
                _save_store(store)
            return deepcopy(store)

    try:
        store = _normalize_store(json.loads(POLL_STORE_PATH.read_text(encoding="utf-8")))
    except Exception as exc:
        logger.warning("Poll store load error: %s", exc)
        store = {"polls": {}}

    store, migrated = _migrate_legacy_store(store)
    if migrated:
        try:
            _save_store(store)
            try:
                mtime = POLL_STORE_PATH.stat().st_mtime
            except OSError:
                mtime = time.time()
        except Exception as exc:
            logger.warning("Poll store migration save error: %s", exc)

    with _lock:
        _store_cache["path"] = str(POLL_STORE_PATH)
        _store_cache["mtime"] = mtime
        _store_cache["data"] = deepcopy(store)

    return deepcopy(store)


def _save_store(store: Dict[str, Any]):
    _ensure_store_path()
    normalized = _normalize_store(store)
    payload = json.dumps(normalized, ensure_ascii=False, indent=2)
    POLL_STORE_PATH.write_text(payload, encoding="utf-8")

    try:
        mtime = POLL_STORE_PATH.stat().st_mtime
    except OSError:
        mtime = time.time()  # type: ignore[name-defined]

    with _lock:
        _store_cache["path"] = str(POLL_STORE_PATH)
        _store_cache["mtime"] = mtime
        _store_cache["data"] = deepcopy(normalized)


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except Exception:
        return default


def _is_crypto_symbol(symbol: str, signal: Dict[str, Any] | None = None) -> bool:
    normalized = _normalize_symbol(symbol)
    if normalized in _crypto_symbols or normalized.endswith("-USD"):
        return True

    if signal:
        asset_class = str(signal.get("asset_class") or signal.get("market_type") or "").lower()
        if asset_class == "crypto":
            return True

    return False


def _classify_market_type(symbol: str, signal: Dict[str, Any] | None = None) -> str:
    return "crypto" if _is_crypto_symbol(symbol, signal=signal) else "stock"


def _coerce_list(value: Any) -> List[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if value:
        return [str(value).strip()]
    return []


def _signal_text(signal: Dict[str, Any] | None) -> str:
    if not signal:
        return ""

    parts: List[str] = []
    for key in (
        "signal",
        "title",
        "headline",
        "summary",
        "description",
        "reason",
        "rationale",
        "thesis",
        "narrative",
        "context",
        "label",
        "sector",
        "asset_class",
        "trend",
    ):
        value = signal.get(key)
        if value:
            parts.append(str(value))

    parts.extend(_coerce_list(signal.get("events")))
    parts.extend(_coerce_list(signal.get("tags")))
    return " ".join(parts).lower()


def _signal_metrics(signal: Dict[str, Any] | None) -> Dict[str, float]:
    signal = signal or {}
    return {
        "score": _safe_float(signal.get("score"), 0.0),
        "trend": _safe_float(signal.get("trend"), 0.0),
        "change_pct": _safe_float(signal.get("change_pct"), 0.0),
        "rsi": _safe_float(signal.get("rsi"), 50.0),
        "adx": _safe_float(signal.get("adx"), 0.0),
        "rel_volume": _safe_float(signal.get("rel_volume"), 0.0),
        "volume": _safe_float(signal.get("volume"), 0.0),
    }


def _sector_from_signal(signal: Dict[str, Any] | None) -> str:
    if not signal:
        return ""

    for key in ("sector", "industry", "category", "group"):
        value = signal.get(key)
        if value:
            return str(value).strip()

    return ""


_EARNINGS_DATE_KEYS = {
    "earnings_date",
    "earnings_at",
    "next_earnings_date",
    "next_earnings_at",
    "report_date",
    "result_date",
    "results_date",
    "release_date",
}


def _parse_event_datetime(value: Any) -> datetime | None:
    if value is None or value == "":
        return None

    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, (int, float)):
        timestamp = float(value)
        if timestamp > 10_000_000_000:
            timestamp = timestamp / 1000.0
        try:
            parsed = datetime.fromtimestamp(timestamp, UTC)
        except Exception:
            return None
    else:
        text = str(value).strip()
        if not text:
            return None
        if text.isdigit():
            return _parse_event_datetime(float(text))
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except Exception:
            return None

    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _current_week_bounds(now: datetime | None = None) -> tuple[datetime, datetime]:
    current = now or _utc_now()
    if current.tzinfo is None:
        current = current.replace(tzinfo=UTC)
    current = current.astimezone(UTC)
    start = (current - timedelta(days=current.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
    return start, start + timedelta(days=7)


def _find_earnings_date(value: Any, source: str = "signal") -> tuple[datetime | None, str | None]:
    if isinstance(value, dict):
        for key, item in value.items():
            key_text = str(key or "").lower()
            if key_text in _EARNINGS_DATE_KEYS:
                parsed = _parse_event_datetime(item)
                if parsed:
                    return parsed, key_text
            if key_text in {"calendar", "earnings", "events", "corporate_events", "event"}:
                parsed, parsed_source = _find_earnings_date(item, key_text)
                if parsed:
                    return parsed, parsed_source or key_text
        return None, None

    if isinstance(value, list):
        for item in value:
            parsed, parsed_source = _find_earnings_date(item, source)
            if parsed:
                return parsed, parsed_source or source

    return None, None


def _has_earnings_text(signal: Dict[str, Any] | None) -> bool:
    if not signal:
        return False

    haystack = _signal_text(signal)
    terms = (
        "earn",
        "earning",
        "resultado",
        "resultados",
        "trimestre",
        "guidance",
        "balanco",
        "balanço",
        "quarter",
    )
    return any(term in haystack for term in terms)


def _earnings_context(
    symbol: str,
    signal: Dict[str, Any] | None,
    explicit: bool | None = None,
) -> Dict[str, Any]:
    if explicit is not None:
        return {
            "symbol": _normalize_symbol(symbol),
            "is_earnings_week": bool(explicit),
            "date": None,
            "source": "explicit_argument",
            "reason": "earnings_week informado pela chamada",
        }

    parsed, source = _find_earnings_date(signal)
    if parsed:
        start, end = _current_week_bounds()
        in_week = start <= parsed < end
        return {
            "symbol": _normalize_symbol(symbol),
            "is_earnings_week": in_week,
            "date": parsed.date().isoformat(),
            "source": source or "structured_date",
            "reason": "data de resultado dentro da semana corrente" if in_week else "data de resultado fora da semana corrente",
        }

    if _has_earnings_text(signal):
        return {
            "symbol": _normalize_symbol(symbol),
            "is_earnings_week": True,
            "date": None,
            "source": "signal_text",
            "reason": "sinal/evento menciona resultado, earnings ou guidance",
        }

    return {
        "symbol": _normalize_symbol(symbol),
        "is_earnings_week": False,
        "date": None,
        "source": "none",
        "reason": "sem evidencia de resultado nesta semana",
    }


def _infer_earnings_week(signal: Dict[str, Any] | None) -> bool:
    return bool(_earnings_context("", signal).get("is_earnings_week"))


def _detect_timing_bucket(symbol: str, market_type: str, earnings_week: bool, signal: Dict[str, Any] | None) -> str:
    metrics = _signal_metrics(signal)
    text = _signal_text(signal)

    if earnings_week:
        return "earnings_week"

    if market_type == "crypto":
        if metrics["rel_volume"] >= 1.5 or abs(metrics["change_pct"]) >= 4.0 or metrics["adx"] >= 28.0:
            if metrics["change_pct"] >= 0 or metrics["trend"] >= 0:
                return "crypto_momentum"
            return "crypto_volatility"
        if metrics["rsi"] >= 70:
            return "crypto_overheated"
        if metrics["rsi"] <= 35:
            return "crypto_reset"
        return "crypto_range"

    if metrics["adx"] >= 30.0 and abs(metrics["change_pct"]) >= 2.5:
        if metrics["trend"] >= 0 or metrics["score"] >= 60:
            return "trend_following"
        return "trend_breakdown"

    if metrics["rsi"] >= 70:
        return "overextended"
    if metrics["rsi"] <= 35:
        return "mean_reversion"

    event_terms = ("cpi", "fed", "rate", "tariff", "macro", "policy", "dividend", "split", "merger", "upgrade", "downgrade")
    if any(term in text for term in event_terms):
        return "event_driven"

    if abs(metrics["change_pct"]) >= 4.0 or metrics["rel_volume"] >= 1.6:
        return "volatility_event"

    if metrics["trend"] >= 0 and metrics["score"] >= 55:
        return "trend_following"

    if metrics["trend"] < 0 and metrics["score"] <= 45:
        return "trend_breakdown"

    return "weekly_direction"


def _stable_index(seed: str, size: int) -> int:
    if size <= 0:
        return 0

    digest = blake2b(seed.encode("utf-8"), digest_size=8).digest()
    return int.from_bytes(digest, "big") % size


def _question_quality_score(question: str) -> int:
    score = 100
    lowered = question.lower()
    penalties = (
        ("vai subir", 25),
        ("vai cair", 25),
        ("sim ou nao", 20),
        ("sim ou não", 20),
        ("alta ou baixa", 20),
        ("compra ou vende", 20),
        ("o cenario favorece", 20),
        ("o cenário favorece", 20),
        ("vai bater", 30),
        ("obvio", 18),
        ("óbvio", 18),
        ("vai dar certo", 16),
    )

    for needle, penalty in penalties:
        if needle in lowered:
            score -= penalty

    if "?" not in question:
        score -= 10
    if len(question) < 20:
        score -= 15
    if len(question) > 140:
        score -= 5

    return max(0, min(100, score))


def _question_is_valid(question: str) -> bool:
    return _question_quality_score(question) >= 60


def _is_stale_generic_question(question: Any) -> bool:
    lowered = str(question or "").lower()
    stale_terms = (
        "vai bater o anúncio",
        "vai bater o anuncio",
        "qual o cenário mais provável",
        "qual o cenario mais provavel",
        "o cenario favorece",
        "o cenário favorece",
    )
    return any(term in lowered for term in stale_terms)


def _template_bank(symbol: str, market_type: str, timing_bucket: str, signal: Dict[str, Any] | None) -> List[Dict[str, str]]:
    sector = _sector_from_signal(signal)
    sector_clause = f" no setor {sector}" if sector else ""

    if market_type == "crypto":
        if timing_bucket == "crypto_momentum":
            return [
                {
                    "template_id": "crypto_momentum_1",
                    "question": f"{symbol}: o fluxo desta semana ainda favorece continuação ou já começa a cansar?",
                    "option_a": "Continuação com volume e fluxo sustentado",
                    "option_b": "Exaustao do movimento e correção curta",
                },
                {
                    "template_id": "crypto_momentum_2",
                    "question": f"{symbol}: o mercado ainda enxerga perna para a tendência ou a força já foi precificada?",
                    "option_a": "Ainda existe perna para seguir a tendência",
                    "option_b": "A força já parece ter sido precificada",
                },
                {
                    "template_id": "crypto_momentum_3",
                    "question": f"{symbol}: a volatilidade da semana aponta expansão ou armadilha de continuidade?",
                    "option_a": "Expansão de volatilidade com direção",
                    "option_b": "Movimento esticado e risco de reversão",
                },
            ]

        if timing_bucket in {"crypto_overheated", "crypto_reset"}:
            return [
                {
                    "template_id": "crypto_reset_1",
                    "question": f"{symbol}: depois da extensão recente, o ativo está mais perto de repique ou de mais pressão?",
                    "option_a": "Repique técnico com recuperação",
                    "option_b": "Pressao continua dominando a leitura",
                },
                {
                    "template_id": "crypto_reset_2",
                    "question": f"{symbol}: a faixa atual parece mais compressão para rompimento ou exaustão do impulso?",
                    "option_a": "Compressao para um rompimento",
                    "option_b": "Exaustao do impulso e lateralizacao",
                },
            ]

        return [
            {
                "template_id": "crypto_range_1",
                "question": f"{symbol}: a estrutura desta semana sugere rompimento ou compressão lateral{sector_clause}?",
                "option_a": "Rompimento com direcao mais forte",
                "option_b": "Compressao lateral ainda manda no preco",
            },
            {
                "template_id": "crypto_range_2",
                "question": f"{symbol}: o fluxo parece mais de acumulação ou de distribuição nesta janela?",
                "option_a": "Acumulacao com compra gradual",
                "option_b": "Distribuicao e perda de forca",
            },
        ]

    if timing_bucket == "earnings_week":
        return [
            {
                "template_id": "earnings_1",
                "question": f"{symbol}: na semana de resultado, o mercado deve reagir mais ao guidance ou ao fluxo pos-evento?",
                "option_a": "Guidance muda a tese do ativo",
                "option_b": "Fluxo pos-resultado manda no preço",
            },
            {
                "template_id": "earnings_2",
                "question": f"{symbol}{sector_clause}: o resultado confirma a tese atual ou exige reduzir risco?",
                "option_a": "Confirma a tese e sustenta fluxo",
                "option_b": "Exige reduzir risco apos o evento",
            },
            {
                "template_id": "earnings_3",
                "question": f"{symbol}: depois do resultado, o risco maior e gap com continuidade ou realizacao no fluxo?",
                "option_a": "Gap com continuidade e volume",
                "option_b": "Realizacao se fluxo falhar",
            },
        ]

    if timing_bucket in {"trend_following", "trend_breakdown"}:
        return [
            {
                "template_id": "trend_1",
                "question": f"{symbol}{sector_clause}: a tendencia semanal ainda tem perna ou ja mostra exaustao?",
                "option_a": "Continuidade com fluxo comprador",
                "option_b": "Exaustao e retorno a media",
            },
            {
                "template_id": "trend_2",
                "question": f"{symbol}: o fluxo institucional ainda sustenta a direcao atual ou a forca foi embora?",
                "option_a": "Fluxo ainda sustenta a continuidade",
                "option_b": "A forca perdeu tracao relevante",
            },
            {
                "template_id": "trend_3",
                "question": f"{symbol}: o movimento atual parece impulso de tendencia ou apenas extensao exagerada?",
                "option_a": "Impulso com continuidade",
                "option_b": "Extensao exagerada e fragil",
            },
        ]

    if timing_bucket in {"mean_reversion", "overextended", "volatility_event"}:
        return [
            {
                "template_id": "mean_reversion_1",
                "question": f"{symbol}{sector_clause}: a faixa atual abre mais espaco para repique tecnico ou para pressao adicional?",
                "option_a": "Repique tecnico tem mais espaco",
                "option_b": "Pressao adicional ainda domina",
            },
            {
                "template_id": "mean_reversion_2",
                "question": f"{symbol}: o excesso recente ja parece uma oportunidade de reversao ou so pausa no fluxo?",
                "option_a": "Reversao tecnica ganha forca",
                "option_b": "So uma pausa antes de continuar",
            },
            {
                "template_id": "mean_reversion_3",
                "question": f"{symbol}: a leitura institucional sugere retorno a media ou continuidade da distorcao?",
                "option_a": "Retorno a media mais provavel",
                "option_b": "Distorcao ainda pode se expandir",
            },
        ]

    if timing_bucket == "event_driven":
        return [
            {
                "template_id": "event_1",
                "question": f"{symbol}{sector_clause}: o proximo movimento depende mais de fluxo ou de nova informacao?",
                "option_a": "Fluxo local continua mandando",
                "option_b": "Nova informacao deve redefinir o preco",
            },
            {
                "template_id": "event_2",
                "question": f"{symbol}: o mercado esta precificando catalisador real ou apenas ruido de curto prazo?",
                "option_a": "Catalisador real ainda domina",
                "option_b": "Ruido curto ja pesa mais",
            },
            {
                "template_id": "event_3",
                "question": f"{symbol}: a reação semanal tende a ser mais de preço ou de narrativa?",
                "option_a": "Preco responde ao catalisador real",
                "option_b": "Narrativa esfria o movimento",
            },
        ]

    return [
        {
            "template_id": "weekly_1",
            "question": f"{symbol}{sector_clause}: nesta semana, a confirmacao mais importante vem de volume no rompimento ou defesa de faixa?",
            "option_a": "Volume confirma rompimento da faixa",
            "option_b": "Defesa de faixa ainda manda",
        },
        {
            "template_id": "weekly_2",
            "question": f"{symbol}: sem evento dominante, o mercado precisa confirmar fluxo comprador ou rejeicao de risco?",
            "option_a": "Fluxo comprador precisa aparecer",
            "option_b": "Rejeicao de risco ainda pesa",
        },
        {
            "template_id": "weekly_3",
            "question": f"{symbol}: a tese semanal fica valida acima de nivel com volume ou perde força sem liquidez?",
            "option_a": "Valida acima de nivel com volume",
            "option_b": "Perde força sem liquidez",
        },
    ]


def _build_signal_snapshot(signal: Dict[str, Any] | None) -> Dict[str, Any]:
    signal = signal or {}
    metrics = _signal_metrics(signal)
    return {
        "ticker": _normalize_symbol(signal.get("ticker") or signal.get("symbol")),
        "sector": _sector_from_signal(signal),
        "score": round(metrics["score"], 2),
        "trend": round(metrics["trend"], 4),
        "change_pct": round(metrics["change_pct"], 4),
        "rsi": round(metrics["rsi"], 4),
        "adx": round(metrics["adx"], 4),
        "rel_volume": round(metrics["rel_volume"], 4),
        "volume": int(metrics["volume"]),
        "signal": str(signal.get("signal") or signal.get("title") or signal.get("headline") or ""),
        "events": _coerce_list(signal.get("events"))[:4],
        "tags": _coerce_list(signal.get("tags"))[:4],
    }


def _build_poll_context(
    symbol: str,
    market_type: str,
    earnings_week: bool,
    timing_bucket: str,
    signal: Dict[str, Any] | None,
    earnings_meta: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    signal_snapshot = _build_signal_snapshot(signal)
    metrics = _signal_metrics(signal)
    earnings_meta = earnings_meta or _earnings_context(symbol, signal, explicit=earnings_week if earnings_week else None)
    sector = signal_snapshot.get("sector", "")
    trend_label = "alta" if metrics["trend"] >= 0 else "baixa"
    market_phrase = "cripto" if market_type == "crypto" else "acoes"

    if timing_bucket == "earnings_week":
        why_it_matters = "Resultado e guidance podem mudar a precificacao mais do que o headline."
        insight = "A pergunta foca na reacao de mercado, nao no numero isolado."
    elif market_type == "crypto":
        if timing_bucket == "crypto_momentum":
            why_it_matters = "Em crypto, fluxo e volatilidade costumam definir a direcao semanal."
            insight = "A pergunta evita sim/nao e testa se o momentum ainda tem combustivel."
        elif timing_bucket in {"crypto_overheated", "crypto_reset"}:
            why_it_matters = "Extensao demais em crypto costuma abrir espaco para reversao ou consolidacao."
            insight = "A pergunta mede se o preco ainda acompanha o impulso ou ja cansou."
        else:
            why_it_matters = "Crypto alterna rapido entre compressao e rompimento, entao contexto importa."
            insight = "A pergunta captura se o mercado quer acumular, distribuir ou romper faixa."
    elif timing_bucket in {"trend_following", "trend_breakdown"}:
        why_it_matters = "Tendencia precisa confirmar fluxo e estrutura para continuar."
        insight = "A pergunta mede se a tendencia ainda tem perna ou se o movimento esgotou."
    elif timing_bucket in {"mean_reversion", "overextended", "volatility_event"}:
        why_it_matters = "Movimentos esticados podem voltar para a media mais rapido do que o consenso espera."
        insight = "A pergunta testa se o mercado ainda quer empurrar o preco ou corrigir."
    elif timing_bucket == "event_driven":
        why_it_matters = "Catalisadores mudam o preco quando o mercado ancora a narrativa correta."
        insight = "A pergunta separa fluxo verdadeiro de ruido de curto prazo."
    else:
        why_it_matters = "Sem catalisador forte, o mercado costuma alternar entre continuidade e faixa lateral."
        insight = "A pergunta captura a leitura mais plausivel da janela semanal."

    quality_score = 70
    if signal:
        quality_score += 10
    if sector:
        quality_score += 5
    if earnings_week:
        quality_score += 5
    if metrics["score"] >= 60 or metrics["score"] <= 40:
        quality_score += 5
    if market_type == "crypto":
        quality_score += 3

    quality_score = max(0, min(100, quality_score))
    return {
        "symbol": symbol,
        "market_type": market_type,
        "market_label": market_phrase,
        "sector": sector,
        "earnings_week": bool(earnings_week),
        "earnings": earnings_meta,
        "earnings_date": earnings_meta.get("date"),
        "earnings_source": earnings_meta.get("source"),
        "earnings_reason": earnings_meta.get("reason"),
        "timing_bucket": timing_bucket,
        "why_it_matters": why_it_matters,
        "insight": insight,
        "quality_score": quality_score,
        "trend_label": trend_label,
        "signal": signal_snapshot,
    }


def _pick_template(
    symbol: str,
    week_key: str,
    templates: List[Dict[str, str]],
) -> Dict[str, str]:
    valid_templates = [template for template in templates if _question_is_valid(template.get("question", ""))]

    if not valid_templates:
        valid_templates = templates[:1] if templates else []

    if not valid_templates:
        return {
            "template_id": "fallback",
            "question": f"{symbol}: qual leitura semanal parece mais consistente?",
            "option_a": "Cenario construtivo com continuidade",
            "option_b": "Cenario fraco ou lateral",
        }

    if len(valid_templates) == 1:
        return valid_templates[0]

    index = _stable_index(f"{week_key}:{symbol}", len(valid_templates))
    return valid_templates[index]


def _build_poll_report(poll: Dict[str, Any]) -> Dict[str, Any]:
    context = dict(poll.get("context") or {})
    options = list(poll.get("options") or [])

    return {
        "version": poll.get("schema_version", POLL_SCHEMA_VERSION),
        "market_type": poll.get("market_type"),
        "timing_bucket": poll.get("timing_bucket"),
        "status": poll.get("status", "active"),
        "total_votes": int(poll.get("total_votes") or 0),
        "quality_score": poll.get("quality", {}).get("score"),
        "why_it_matters": context.get("why_it_matters"),
        "insight": context.get("insight"),
        "market_context": {
            "market_label": context.get("market_label"),
            "sector": context.get("sector"),
            "earnings_week": context.get("earnings_week"),
            "earnings_date": context.get("earnings_date"),
            "earnings_source": context.get("earnings_source"),
            "earnings_reason": context.get("earnings_reason"),
            "trend_label": context.get("trend_label"),
        },
        "question_variants": list(poll.get("question_variants") or []),
        "options": [
            {
                "key": option.get("key"),
                "label": option.get("label"),
                "votes": option.get("votes", 0),
            }
            for option in options
        ],
    }


def _select_question_variants(
    symbol: str,
    week_key: str,
    market_type: str,
    earnings_week: bool,
    timing_bucket: str,
    signal: Dict[str, Any] | None,
) -> Dict[str, Any]:
    templates = _template_bank(symbol, market_type, timing_bucket, signal)
    selected = _pick_template(symbol, week_key, templates)
    return {
        "template_id": selected.get("template_id", "fallback"),
        "question": selected["question"],
        "options": [
            {"key": "A", "label": selected["option_a"], "votes": 0},
            {"key": "B", "label": selected["option_b"], "votes": 0},
        ],
        "question_variants": [template["question"] for template in templates[:MAX_POLL_VARIANTS]],
    }


def _upgrade_poll_record(poll: Dict[str, Any], symbol: str, signal: Dict[str, Any] | None = None) -> Dict[str, Any]:
    return _upgrade_poll_record_with_touch(poll, symbol, signal=signal, touch_updated_at=False)


def _upgrade_poll_record_with_touch(
    poll: Dict[str, Any],
    symbol: str,
    signal: Dict[str, Any] | None = None,
    touch_updated_at: bool = False,
) -> Dict[str, Any]:
    upgraded = dict(poll)
    week_key = str(upgraded.get("week_key") or _week_key())
    stored_market_type = str(upgraded.get("market_type") or "").strip()
    stored_earnings_week = bool(upgraded.get("earnings_week")) if "earnings_week" in upgraded else None
    stored_timing_bucket = str(upgraded.get("timing_bucket") or "").strip()

    market_type = _classify_market_type(symbol, signal=signal) if signal else (stored_market_type or _classify_market_type(symbol, signal=signal))
    earnings_meta = _earnings_context(symbol, signal) if signal else {
        "symbol": _normalize_symbol(symbol),
        "is_earnings_week": bool(stored_earnings_week),
        "date": (upgraded.get("context") or {}).get("earnings_date") if isinstance(upgraded.get("context"), dict) else None,
        "source": (upgraded.get("context") or {}).get("earnings_source") if isinstance(upgraded.get("context"), dict) else "stored",
        "reason": (upgraded.get("context") or {}).get("earnings_reason") if isinstance(upgraded.get("context"), dict) else "valor preservado do poll",
    }
    earnings_week = bool(earnings_meta.get("is_earnings_week"))
    timing_bucket = (
        _detect_timing_bucket(symbol, market_type, earnings_week, signal)
        if signal
        else (stored_timing_bucket or _detect_timing_bucket(symbol, market_type, earnings_week, signal))
    )

    context = upgraded.get("context")
    if not isinstance(context, dict) or signal:
        context = _build_poll_context(symbol, market_type, earnings_week, timing_bucket, signal, earnings_meta=earnings_meta)

    should_refresh_question = _is_stale_generic_question(upgraded.get("question"))
    if signal and (
        market_type != stored_market_type
        or stored_earnings_week is None
        or earnings_week != stored_earnings_week
        or timing_bucket != stored_timing_bucket
        or not upgraded.get("question_variants")
        or _is_stale_generic_question(upgraded.get("question"))
    ):
        should_refresh_question = True

    if should_refresh_question:
        selection = _select_question_variants(
            symbol=symbol,
            week_key=week_key,
            market_type=market_type,
            earnings_week=earnings_week,
            timing_bucket=timing_bucket,
            signal=signal,
        )
        upgraded["template_id"] = selection["template_id"]
        upgraded["question"] = selection["question"]
        upgraded["question_variants"] = selection["question_variants"]
        existing_votes = {
            str(option.get("key")): int(option.get("votes", 0) or 0)
            for option in upgraded.get("options", [])
            if isinstance(option, dict)
        }
        upgraded["options"] = selection["options"]
        for option in upgraded["options"]:
            option["votes"] = existing_votes.get(str(option.get("key")), 0)
    elif not upgraded.get("question_variants"):
        selection = _select_question_variants(
            symbol=symbol,
            week_key=week_key,
            market_type=market_type,
            earnings_week=earnings_week,
            timing_bucket=timing_bucket,
            signal=signal,
        )
        upgraded["template_id"] = upgraded.get("template_id") or selection["template_id"]
        upgraded["question_variants"] = selection["question_variants"]
        upgraded["question"] = upgraded.get("question") or selection["question"]
        upgraded["options"] = upgraded.get("options") or selection["options"]

    upgraded["schema_version"] = POLL_SCHEMA_VERSION
    upgraded.setdefault("status", "active")
    upgraded["total_votes"] = sum(
        int(option.get("votes", 0) or 0)
        for option in upgraded.get("options", [])
        if isinstance(option, dict)
    )
    upgraded.setdefault("created_by", "ai_worker")
    upgraded.setdefault("created_at", _utc_now().isoformat())
    if touch_updated_at:
        upgraded["updated_at"] = _utc_now().isoformat()
    else:
        upgraded["updated_at"] = upgraded.get("updated_at") or upgraded.get("created_at") or _utc_now().isoformat()
    upgraded["week_key"] = week_key
    upgraded["market_type"] = market_type
    upgraded["earnings_week"] = earnings_week
    upgraded["timing_bucket"] = timing_bucket
    upgraded["context"] = context
    upgraded["report"] = _build_poll_report(upgraded)
    if not isinstance(upgraded.get("quality"), dict):
        upgraded["quality"] = {
            "score": int(context.get("quality_score") or 0),
            "reason": context.get("insight") or "",
        }
    return upgraded


def _store_poll(poll: Dict[str, Any]) -> Dict[str, Any]:
    store = _load_store()
    polls = store.setdefault("polls", {})
    polls[poll["id"]] = poll

    if len(polls) > MAX_POLLS:
        ordered = sorted(
            polls.items(),
            key=lambda item: (
                str(item[1].get("created_at", "")),
                str(item[0]),
            ),
        )
        for key, _value in ordered[: len(polls) - MAX_POLLS]:
            polls.pop(key, None)

    _save_store(store)
    return poll


def _lookup_signal_for_symbol(symbol: str, snapshot: Dict[str, Dict[str, Any]] | None = None) -> Dict[str, Any] | None:
    symbol = _normalize_symbol(symbol)
    if not symbol:
        return None

    candidates = [symbol]

    if symbol.endswith(".SA"):
        candidates.append(symbol[:-3])
    elif symbol.endswith(("3", "4", "5", "6", "11", "34")):
        candidates.append(f"{symbol}.SA")

    if symbol.endswith("USDT"):
        candidates.append(symbol.replace("USDT", "-USD"))

    if symbol.endswith("-USD"):
        candidates.append(symbol.replace("-USD", "USDT"))

    snapshot = snapshot or get_snapshot_by_ticker()

    for candidate in candidates:
        if candidate in snapshot:
            return snapshot[candidate]

    return None


def ensure_weekly_poll(
    symbol: str,
    market_type: str | None = None,
    earnings_week: bool | None = None,
    signal: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    symbol = _normalize_symbol(symbol)

    if not symbol:
        raise ValueError("invalid_symbol")

    market_type = market_type or _classify_market_type(symbol, signal=signal)
    earnings_meta = _earnings_context(symbol, signal, explicit=earnings_week)
    earnings_week = bool(earnings_meta.get("is_earnings_week"))
    timing_bucket = _detect_timing_bucket(symbol, market_type, earnings_week, signal)
    week_key = _week_key()
    poll_key = _poll_id(symbol, week_key)

    with _lock:
        store = _load_store()
        polls = store.setdefault("polls", {})
        poll = polls.get(poll_key)

        if isinstance(poll, dict):
            upgraded = _upgrade_poll_record_with_touch(poll, symbol, signal=signal, touch_updated_at=False)
            polls[poll_key] = upgraded
            if upgraded != poll:
                _save_store(store)
            return upgraded

        report_context = _build_poll_context(symbol, market_type, earnings_week, timing_bucket, signal, earnings_meta=earnings_meta)
        selection = _select_question_variants(
            symbol=symbol,
            week_key=week_key,
            market_type=market_type,
            earnings_week=earnings_week,
            timing_bucket=timing_bucket,
            signal=signal,
        )

        poll = {
            "id": poll_key,
            "symbol": symbol,
            "market_type": market_type,
            "week_key": week_key,
            "expires_at": _week_expiration(week_key),
            "earnings_week": bool(earnings_week),
            "timing_bucket": timing_bucket,
            "schema_version": POLL_SCHEMA_VERSION,
            "status": "active",
            "created_by": "ai_worker",
            "created_at": _utc_now().isoformat(),
            "updated_at": _utc_now().isoformat(),
            "template_id": selection["template_id"],
            "question": selection["question"],
            "question_variants": selection["question_variants"],
            "options": selection["options"],
            "voters": {},
            "total_votes": 0,
            "context": report_context,
        }
        poll["quality"] = {
            "score": report_context["quality_score"],
            "reason": report_context["insight"],
        }
        poll["report"] = _build_poll_report(poll)
        return _store_poll(poll)


def get_weekly_poll(symbol: str) -> Dict[str, Any]:
    symbol = _normalize_symbol(symbol)
    week_key = _week_key()
    poll_key = _poll_id(symbol, week_key)

    with _lock:
        store = _load_store()
        poll = store.get("polls", {}).get(poll_key)

    if isinstance(poll, dict):
        upgraded = _upgrade_poll_record_with_touch(
            poll,
            symbol,
            signal=_lookup_signal_for_symbol(symbol),
            touch_updated_at=False,
        )
        if upgraded != poll:
            with _lock:
                store = _load_store()
                store.setdefault("polls", {})[poll_key] = upgraded
                _save_store(store)
        return upgraded

    signal = _lookup_signal_for_symbol(symbol)
    return ensure_weekly_poll(symbol=symbol, signal=signal)


def get_poll_report(symbol: str) -> Dict[str, Any]:
    symbol = _normalize_symbol(symbol)
    week_key = _week_key()
    poll_key = _poll_id(symbol, week_key)

    with _lock:
        store = _load_store()
        poll = store.get("polls", {}).get(poll_key)

    if not isinstance(poll, dict):
        signal = _lookup_signal_for_symbol(symbol)
        market_type = _classify_market_type(symbol, signal=signal)
        earnings_meta = _earnings_context(symbol, signal)
        earnings_week = bool(earnings_meta.get("is_earnings_week"))
        timing_bucket = _detect_timing_bucket(symbol, market_type, earnings_week, signal)
        context = _build_poll_context(symbol, market_type, earnings_week, timing_bucket, signal, earnings_meta=earnings_meta)
        selection = _select_question_variants(
            symbol=symbol,
            week_key=week_key,
            market_type=market_type,
            earnings_week=earnings_week,
            timing_bucket=timing_bucket,
            signal=signal,
        )
        return {
            "version": POLL_SCHEMA_VERSION,
            "market_type": market_type,
            "timing_bucket": timing_bucket,
            "quality_score": context.get("quality_score"),
            "why_it_matters": context.get("why_it_matters"),
            "insight": context.get("insight"),
            "market_context": {
                "market_label": context.get("market_label"),
                "sector": context.get("sector"),
                "earnings_week": context.get("earnings_week"),
                "earnings_date": context.get("earnings_date"),
                "earnings_source": context.get("earnings_source"),
                "earnings_reason": context.get("earnings_reason"),
                "trend_label": context.get("trend_label"),
            },
            "question_variants": selection["question_variants"],
            "options": selection["options"],
        }

    report = poll.get("report")
    if isinstance(report, dict):
        return report
    return _build_poll_report(poll)


def vote_poll(symbol: str, option_key: str, user_id: int) -> Dict[str, Any]:
    symbol = _normalize_symbol(symbol)
    option_key = str(option_key or "").upper().strip()

    if not symbol:
        raise ValueError("invalid_symbol")
    if option_key not in {"A", "B"}:
        raise ValueError("invalid_option")

    with _lock:
        poll = get_weekly_poll(symbol)
        store = _load_store()
        stored_poll = store.setdefault("polls", {}).get(poll["id"], poll)
        voters = stored_poll.setdefault("voters", {})
        previous_vote = voters.get(str(user_id))

        if previous_vote == option_key:
            return stored_poll

        if previous_vote:
            for option in stored_poll["options"]:
                if option["key"] == previous_vote and option["votes"] > 0:
                    option["votes"] -= 1

        matched = False
        for option in stored_poll["options"]:
            if option["key"] == option_key:
                option["votes"] += 1
                matched = True
                break

        if not matched:
            raise ValueError("invalid_option")

        voters[str(user_id)] = option_key
        stored_poll["updated_at"] = _utc_now().isoformat()
        stored_poll["total_votes"] = sum(int(option.get("votes", 0) or 0) for option in stored_poll.get("options", []))
        stored_poll["report"] = _build_poll_report(stored_poll)
        store["polls"][stored_poll["id"]] = stored_poll
        _save_store(store)
        return stored_poll


def get_poll_history(symbol: str, limit: int = 8) -> List[Dict[str, Any]]:
    symbol = _normalize_symbol(symbol)
    limit = max(1, int(limit or 1))

    with _lock:
        store = _load_store()
        polls = [
            poll
            for poll in store.get("polls", {}).values()
            if poll.get("symbol") == symbol
        ]

    polls.sort(
        key=lambda item: (
            str(item.get("created_at", "")),
            str(item.get("week_key", "")),
        ),
        reverse=True,
    )
    return polls[:limit]


def get_poll_store_summary() -> Dict[str, Any]:
    with _lock:
        store = _load_store()
        polls = store.get("polls", {})

    if not isinstance(polls, dict):
        polls = {}

    symbols = {
        _normalize_symbol(poll.get("symbol") or poll.get("ticker"))
        for poll in polls.values()
        if isinstance(poll, dict)
    }
    symbols.discard("")

    week_key = _week_key()
    current_week_polls = [
        poll
        for poll in polls.values()
        if isinstance(poll, dict) and str(poll.get("week_key") or "") == week_key
    ]

    return {
        "polls": len(polls),
        "symbols": len(symbols),
        "current_week_polls": len(current_week_polls),
        "week_key": week_key,
        "store_path": str(POLL_STORE_PATH),
    }


def _select_top_stock_signals(signals: List[Dict[str, Any]], limit: int) -> List[Dict[str, Any]]:
    selected: List[Dict[str, Any]] = []
    seen_symbols: set[str] = set()
    sector_counts: Dict[str, int] = {}

    for signal in signals:
        symbol = _normalize_symbol(signal.get("ticker") or signal.get("symbol"))
        if not symbol or symbol in seen_symbols:
            continue

        if _classify_market_type(symbol, signal=signal) == "crypto":
            continue

        sector = _sector_from_signal(signal)
        if sector and sector_counts.get(sector, 0) >= 2:
            continue

        selected.append(signal)
        seen_symbols.add(symbol)
        if sector:
            sector_counts[sector] = sector_counts.get(sector, 0) + 1

        if len(selected) >= limit:
            break

    return selected


def _select_earnings_week_signals(signals: List[Dict[str, Any]], limit: int) -> List[Dict[str, Any]]:
    selected: List[Dict[str, Any]] = []
    seen_symbols: set[str] = set()
    limit = max(0, int(limit or 0))

    if limit <= 0:
        return selected

    for signal in signals:
        symbol = _normalize_symbol(signal.get("ticker") or signal.get("symbol"))
        if not symbol or symbol in seen_symbols:
            continue
        if _classify_market_type(symbol, signal=signal) == "crypto":
            continue
        if not _earnings_context(symbol, signal).get("is_earnings_week"):
            continue
        selected.append(signal)
        seen_symbols.add(symbol)
        if len(selected) >= limit:
            break

    return selected


def _merge_priority_signals(
    priority: List[Dict[str, Any]],
    selected: List[Dict[str, Any]],
    limit: int,
) -> List[Dict[str, Any]]:
    merged: List[Dict[str, Any]] = []
    seen_symbols: set[str] = set()
    limit = max(0, int(limit or 0))

    for signal in [*priority, *selected]:
        if len(merged) >= limit:
            break
        symbol = _normalize_symbol(signal.get("ticker") or signal.get("symbol"))
        if not symbol or symbol in seen_symbols:
            continue
        merged.append(signal)
        seen_symbols.add(symbol)

    return merged


def _select_top_crypto_signals(signals: List[Dict[str, Any]], limit: int) -> List[Dict[str, Any]]:
    selected: List[Dict[str, Any]] = []
    seen_symbols: set[str] = set()

    for signal in signals:
        symbol = _normalize_symbol(signal.get("ticker") or signal.get("symbol"))
        if not symbol or symbol in seen_symbols:
            continue

        if _classify_market_type(symbol, signal=signal) != "crypto":
            continue

        selected.append(signal)
        seen_symbols.add(symbol)

        if len(selected) >= limit:
            break

    return selected


def _fill_remaining_stock_signals(
    signals: List[Dict[str, Any]],
    selected: List[Dict[str, Any]],
    limit: int,
) -> List[Dict[str, Any]]:
    if len(selected) >= limit:
        return selected[:limit]

    seen_symbols = {
        _normalize_symbol(item.get("ticker") or item.get("symbol"))
        for item in selected
        if isinstance(item, dict)
    }

    for signal in signals:
        symbol = _normalize_symbol(signal.get("ticker") or signal.get("symbol"))
        if not symbol or symbol in seen_symbols:
            continue
        if _classify_market_type(symbol, signal=signal) == "crypto":
            continue
        selected.append(signal)
        seen_symbols.add(symbol)
        if len(selected) >= limit:
            break

    return selected[:limit]


def generate_weekly_polls_for_top_symbols(limit: int = 20) -> List[Dict[str, Any]]:
    limit = max(1, int(limit or 1))
    by_ticker = get_snapshot_by_ticker()
    ranked = list(by_ticker.values())
    ranked.sort(key=lambda item: float(item.get("score", 0) or 0), reverse=True)

    crypto_quota = min(4, max(1, limit // 3))
    crypto_quota = min(crypto_quota, limit)
    stock_quota = max(0, limit - crypto_quota)

    if limit > 1 and stock_quota == 0:
        stock_quota = 1
        crypto_quota = max(0, limit - stock_quota)

    earnings_candidates = _select_earnings_week_signals(ranked, limit)
    if earnings_candidates and stock_quota == 0:
        stock_quota = 1
        crypto_quota = max(0, limit - stock_quota)

    stock_signals = _select_top_stock_signals(ranked, stock_quota)
    crypto_signals = _select_top_crypto_signals(ranked, crypto_quota)

    missing_stock_slots = max(0, stock_quota - len(stock_signals))
    if missing_stock_slots > 0:
        crypto_quota = min(limit, crypto_quota + missing_stock_slots)

    missing_crypto_slots = max(0, crypto_quota - len(crypto_signals))
    if missing_crypto_slots > 0:
        stock_quota = min(limit, stock_quota + missing_crypto_slots)

    if len(crypto_signals) < crypto_quota:
        for symbol in CRYPTO_SYMBOLS:
            if len(crypto_signals) >= crypto_quota:
                break
            if any(_normalize_symbol(item.get("ticker") or item.get("symbol")) == _normalize_symbol(symbol) for item in crypto_signals):
                continue
            crypto_signals.append({"ticker": symbol, "symbol": symbol, "score": 0})

    stock_signals = _merge_priority_signals(earnings_candidates, stock_signals, stock_quota)
    stock_signals = _fill_remaining_stock_signals(ranked, stock_signals, stock_quota)

    created: List[Dict[str, Any]] = []

    for signal in stock_signals[:stock_quota]:
        if len(created) >= limit:
            break
        symbol = signal.get("ticker") or signal.get("symbol")
        if not symbol:
            continue
        created.append(ensure_weekly_poll(symbol=symbol, signal=signal))

    for signal in crypto_signals[:crypto_quota]:
        if len(created) >= limit:
            break
        symbol = signal.get("ticker") or signal.get("symbol")
        if not symbol:
            continue
        created.append(ensure_weekly_poll(symbol=symbol, market_type="crypto", signal=signal))

    if len(created) < limit:
        seen_symbols = {
            _normalize_symbol(item.get("symbol"))
            for item in created
            if isinstance(item, dict)
        }

        for signal in ranked:
            if len(created) >= limit:
                break

            symbol = _normalize_symbol(signal.get("ticker") or signal.get("symbol"))
            if not symbol or symbol in seen_symbols:
                continue

            created.append(
                ensure_weekly_poll(
                    symbol=symbol,
                    market_type=_classify_market_type(symbol, signal=signal),
                    signal=signal,
                )
            )
            seen_symbols.add(symbol)

    return created
