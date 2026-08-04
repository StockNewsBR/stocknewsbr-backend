"""Weekly poll service — event-driven policy.

A weekly poll may ONLY be:
  (a) EARNINGS poll — the symbol has a quarterly earnings announcement inside
      the current poll window (Sunday 00:00 -> Thursday 24:00, UTC);
  (b) ECONOMIC CALENDAR poll — a major US economic event falls in the window
      (applies to all symbols).

When neither exists there is NO poll (routes return an empty/none payload;
the frontend already renders the absence). Generic "sobe ou desce" polls are
never generated.
"""

import logging
import threading
import time
from copy import deepcopy
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List

from app.cache.snapshot_cache import get_snapshot_by_ticker
from app.config import CRYPTO_SYMBOLS
from app.core.atomic_io import interprocess_file_lock, read_json_file, write_json_file_atomic
from app.data.us_economic_calendar_2026 import events_in_window

logger = logging.getLogger("stocknewsbr.polls")

POLL_STORE_PATH = Path("runtime/polls/weekly_polls.json")
MAX_POLLS = 2000
POLL_SCHEMA_VERSION = 3
POLL_WINDOW_DAYS = 5  # Sunday 00:00 -> Thursday 24:00
ALLOWED_EVENT_TYPES = {"earnings", "economic_calendar"}
EARNINGS_CACHE_TTL_SECONDS = 6 * 3600.0

_lock = threading.RLock()
_store_cache: Dict[str, Any] = {"path": "", "mtime": 0.0, "data": {"polls": {}}}
_crypto_symbols = {str(symbol).upper().strip() for symbol in CRYPTO_SYMBOLS}
_earnings_cache: Dict[str, tuple[float, datetime | None]] = {}


# --------------------------------------------------------------------------- #
# Time / keys
# --------------------------------------------------------------------------- #
def _utc_now() -> datetime:
    return datetime.now(UTC)


def _poll_window(now: datetime | None = None) -> tuple[datetime, datetime]:
    """[Sunday 00:00, Friday 00:00) of the week containing `now` (UTC).

    ponytail: window uses UTC, not exchange-local time; add tz handling only
    if the owner asks for local-time windows.
    """
    current = now or _utc_now()
    if current.tzinfo is None:
        current = current.replace(tzinfo=UTC)
    current = current.astimezone(UTC)
    start = (current - timedelta(days=(current.weekday() + 1) % 7)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    return start, start + timedelta(days=POLL_WINDOW_DAYS)


def _week_key(now: datetime | None = None) -> str:
    # Shift +1 day so Sunday keys together with the Mon-Thu that follows it
    # (poll weeks start on Sunday, ISO weeks start on Monday).
    current = now or _utc_now()
    iso = (current + timedelta(days=1)).isocalendar()
    return f"{iso.year}-W{iso.week:02d}"


def _poll_id(symbol: str, week_key: str) -> str:
    return f"{week_key}:{symbol.upper()}"


def _normalize_symbol(symbol: str | None) -> str:
    return str(symbol or "").upper().strip()


# --------------------------------------------------------------------------- #
# Store I/O
# --------------------------------------------------------------------------- #
def _ensure_store_path():
    POLL_STORE_PATH.parent.mkdir(parents=True, exist_ok=True)


def _normalize_store(store: Any) -> Dict[str, Any]:
    if not isinstance(store, dict):
        return {"polls": {}}

    normalized = dict(store)
    polls = normalized.get("polls")

    if not isinstance(polls, dict):
        polls = {}

    normalized["polls"] = polls
    return normalized


def _load_store(use_cache: bool = True) -> Dict[str, Any]:
    _ensure_store_path()

    if not POLL_STORE_PATH.exists():
        return {"polls": {}}

    try:
        mtime = POLL_STORE_PATH.stat().st_mtime
    except OSError:
        return {"polls": {}}

    if use_cache:
        with _lock:
            cached_path = str(_store_cache.get("path") or "")
            cached_mtime = float(_store_cache.get("mtime") or 0.0)
            cached_data = _store_cache.get("data")
            if cached_path == str(POLL_STORE_PATH) and cached_mtime == mtime and isinstance(cached_data, dict):
                return deepcopy(cached_data)

    try:
        store = _normalize_store(read_json_file(POLL_STORE_PATH, lambda: {"polls": {}}))
    except Exception as exc:
        logger.warning("Poll store load error: %s", exc)
        store = {"polls": {}}

    with _lock:
        _store_cache["path"] = str(POLL_STORE_PATH)
        _store_cache["mtime"] = mtime
        _store_cache["data"] = deepcopy(store)

    return deepcopy(store)


def _save_store(store: Dict[str, Any]):
    _ensure_store_path()
    normalized = _normalize_store(store)
    write_json_file_atomic(POLL_STORE_PATH, normalized, ensure_ascii=False)

    try:
        mtime = POLL_STORE_PATH.stat().st_mtime
    except OSError:
        mtime = time.time()

    with _lock:
        _store_cache["path"] = str(POLL_STORE_PATH)
        _store_cache["mtime"] = mtime
        _store_cache["data"] = deepcopy(normalized)


def _mutate_store(mutator):
    with _lock, interprocess_file_lock(POLL_STORE_PATH.with_suffix(".json.lock")):
        store = _load_store()
        result = mutator(store)
        _save_store(store)
        return result


def _prune_polls(polls: Dict[str, Any], keep_id: str):
    if len(polls) <= MAX_POLLS:
        return
    ordered = sorted(
        polls.items(),
        key=lambda item: (
            str(item[1].get("created_at", "")),
            str(item[0]),
        ),
    )
    # Mission 31F: o poll recém-armazenado nunca pode ser podado,
    # mesmo que seja o mais antigo por created_at.
    removable = [key for key, _value in ordered if key != keep_id]
    for key in removable[: len(polls) - MAX_POLLS]:
        polls.pop(key, None)


def _store_poll(poll: Dict[str, Any]) -> Dict[str, Any]:
    def mutator(store):
        polls = store.setdefault("polls", {})
        polls[poll["id"]] = poll
        _prune_polls(polls, poll["id"])
        return poll

    return _mutate_store(mutator)


# --------------------------------------------------------------------------- #
# Symbol classification / signal lookup
# --------------------------------------------------------------------------- #
def _is_crypto_symbol(symbol: str, signal: Dict[str, Any] | None = None) -> bool:
    normalized = _normalize_symbol(symbol)
    if normalized in _crypto_symbols or normalized.endswith("-USD") or normalized.endswith("USDT"):
        return True

    if signal:
        asset_class = str(signal.get("asset_class") or signal.get("market_type") or "").lower()
        if asset_class == "crypto":
            return True

    return False


def _classify_market_type(symbol: str, signal: Dict[str, Any] | None = None) -> str:
    return "crypto" if _is_crypto_symbol(symbol, signal=signal) else "stock"


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


# --------------------------------------------------------------------------- #
# Earnings date resolution
# --------------------------------------------------------------------------- #
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
    elif isinstance(value, date):
        parsed = datetime(value.year, value.month, value.day, tzinfo=UTC)
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


def _fetch_earnings_date(symbol: str) -> datetime | None:
    """Minimal yfinance earnings-calendar lookup with an in-process cache.

    Fail-quiet by design: any error (network, dependency, payload shape)
    yields None and therefore no earnings poll — never a fake date.
    """
    normalized = _normalize_symbol(symbol)
    if not normalized:
        return None

    now = time.time()
    cached = _earnings_cache.get(normalized)
    if cached and now - cached[0] < EARNINGS_CACHE_TTL_SECONDS:
        return cached[1]

    result: datetime | None = None
    try:
        import yfinance

        calendar = yfinance.Ticker(normalized).calendar or {}
        raw = calendar.get("Earnings Date") if isinstance(calendar, dict) else None
        candidates = raw if isinstance(raw, (list, tuple)) else [raw]
        parsed_dates = sorted(
            parsed for parsed in (_parse_event_datetime(item) for item in candidates) if parsed
        )
        if parsed_dates:
            result = parsed_dates[0]
    except Exception as exc:
        logger.debug("Earnings calendar lookup failed for %s: %s", normalized, exc)

    _earnings_cache[normalized] = (now, result)
    return result


def _earnings_date_for(symbol: str, signal: Dict[str, Any] | None) -> tuple[datetime | None, str | None]:
    parsed, source = _find_earnings_date(signal)
    if parsed:
        return parsed, source or "signal"

    if _is_crypto_symbol(symbol, signal=signal):
        return None, None

    fetched = _fetch_earnings_date(symbol)
    if fetched:
        return fetched, "yfinance_calendar"

    return None, None


# --------------------------------------------------------------------------- #
# Event-driven poll policy
# --------------------------------------------------------------------------- #
def _format_date_br(value: datetime) -> str:
    return value.strftime("%d/%m/%Y")


def _resolve_poll_event(
    symbol: str,
    signal: Dict[str, Any] | None,
    window: tuple[datetime, datetime],
) -> Dict[str, Any] | None:
    """Earnings inside the window wins; else a US economic-calendar event; else None."""
    start, end = window

    earnings_dt, source = _earnings_date_for(symbol, signal)
    if earnings_dt and start <= earnings_dt < end:
        return {
            "event_type": "earnings",
            "event_name": "Resultado trimestral",
            "event_date": earnings_dt.date().isoformat(),
            "event_source": source or "signal",
            "question": f"Anúncio do trimestre em {_format_date_br(earnings_dt)}",
            "option_a": "Vai bater os números e subir",
            "option_b": "Não vai bater e cair",
            "why_it_matters": "Resultado trimestral e guidance costumam definir a reação do papel na semana.",
        }

    events = events_in_window(start, end)
    if events:
        event = events[0]
        event_dt = _parse_event_datetime(event["date"])
        date_label = _format_date_br(event_dt) if event_dt else str(event["date"])
        return {
            "event_type": "economic_calendar",
            "event_name": event["name"],
            "event_date": str(event["date"]),
            "event_source": "us_economic_calendar_2026",
            "question": f"{event['name']} em {date_label}: como vem o dado?",
            "option_a": "Acima do esperado",
            "option_b": "Abaixo do esperado",
            "why_it_matters": f"{event['name']} é um evento macro que mexe com o mercado inteiro.",
        }

    return None


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
        "event_type": poll.get("event_type"),
        "event_name": poll.get("event_name"),
        "event_date": poll.get("event_date"),
        "event_source": poll.get("event_source"),
        "market_context": {
            "market_label": context.get("market_label"),
            "sector": context.get("sector"),
            "earnings_week": context.get("earnings_week"),
            "earnings_date": context.get("earnings_date"),
            "earnings_source": context.get("earnings_source"),
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


def _build_poll(
    symbol: str,
    market_type: str,
    week_key: str,
    window: tuple[datetime, datetime],
    event: Dict[str, Any],
) -> Dict[str, Any]:
    start, end = window
    now_iso = _utc_now().isoformat()
    is_earnings = event["event_type"] == "earnings"

    context = {
        "symbol": symbol,
        "market_type": market_type,
        "market_label": "cripto" if market_type == "crypto" else "acoes",
        "sector": "",
        "earnings_week": is_earnings,
        "earnings_date": event["event_date"] if is_earnings else None,
        "earnings_source": event["event_source"] if is_earnings else None,
        "event_type": event["event_type"],
        "event_name": event["event_name"],
        "event_date": event["event_date"],
        "event_source": event["event_source"],
        "why_it_matters": event["why_it_matters"],
        "insight": "Poll ancorada em evento verificável (resultado ou calendário econômico).",
        "quality_score": 90,
    }

    poll = {
        "id": _poll_id(symbol, week_key),
        "symbol": symbol,
        "market_type": market_type,
        "week_key": week_key,
        "expires_at": end.isoformat(),
        "earnings_week": is_earnings,
        "timing_bucket": "earnings_week" if is_earnings else "economic_calendar",
        "schema_version": POLL_SCHEMA_VERSION,
        "status": "active",
        "created_by": "ai_worker",
        "created_at": now_iso,
        "updated_at": now_iso,
        "template_id": event["event_type"],
        "question": event["question"],
        "question_variants": [event["question"]],
        "options": [
            {"key": "A", "label": event["option_a"], "votes": 0},
            {"key": "B", "label": event["option_b"], "votes": 0},
        ],
        "voters": {},
        "total_votes": 0,
        "event_type": event["event_type"],
        "event_name": event["event_name"],
        "event_date": event["event_date"],
        "event_source": event["event_source"],
        "valid_from": start.isoformat(),
        "valid_until": end.isoformat(),
        "context": context,
    }
    poll["quality"] = {"score": context["quality_score"], "reason": context["insight"]}
    poll["report"] = _build_poll_report(poll)
    return poll


def _is_active_event_poll(poll: Any, now: datetime) -> bool:
    if not isinstance(poll, dict):
        return False
    if poll.get("event_type") not in ALLOWED_EVENT_TYPES:
        return False
    valid_until = _parse_event_datetime(poll.get("valid_until"))
    return bool(valid_until and now < valid_until)


def _empty_poll_payload(symbol: str, reason: str = "no_event_in_window") -> Dict[str, Any]:
    # Frontend treats a payload without question/options as "no poll".
    return {
        "symbol": symbol,
        "status": "none",
        "question": "",
        "options": [],
        "total_votes": 0,
        "event_type": None,
        "event_date": None,
        "reason": reason,
    }


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #
def ensure_weekly_poll(
    symbol: str,
    market_type: str | None = None,
    earnings_week: bool | None = None,
    signal: Dict[str, Any] | None = None,
) -> Dict[str, Any] | None:
    """Create/return the weekly poll for `symbol` under the event-only policy.

    Returns None when no earnings announcement nor US economic event falls in
    the current Sunday->Thursday window (including Friday/Saturday, when no
    window is active). `earnings_week` is accepted for signature compatibility
    but the poll is only created from a verifiable event date.
    """
    symbol = _normalize_symbol(symbol)

    if not symbol:
        raise ValueError("invalid_symbol")

    now = _utc_now()
    if now.weekday() in (4, 5):  # Friday/Saturday: outside the Sun->Thu window
        return None

    window = _poll_window(now)
    event = _resolve_poll_event(symbol, signal, window)
    if event is None:
        return None

    market_type = market_type or _classify_market_type(symbol, signal=signal)
    week_key = _week_key(now)
    poll_key = _poll_id(symbol, week_key)

    def mutator(store):
        polls = store.setdefault("polls", {})
        existing = polls.get(poll_key)

        if (
            isinstance(existing, dict)
            and existing.get("event_type") == event["event_type"]
            and existing.get("event_date") == event["event_date"]
        ):
            return existing

        poll = _build_poll(symbol, market_type, week_key, window, event)
        polls[poll_key] = poll
        _prune_polls(polls, poll["id"])
        return poll

    return _mutate_store(mutator)


def get_weekly_poll(symbol: str) -> Dict[str, Any]:
    symbol = _normalize_symbol(symbol)
    now = _utc_now()
    poll_key = _poll_id(symbol, _week_key(now))

    with _lock:
        store = _load_store()
        poll = store.get("polls", {}).get(poll_key)

    if _is_active_event_poll(poll, now):
        return poll

    created = ensure_weekly_poll(symbol=symbol, signal=_lookup_signal_for_symbol(symbol))
    if created is not None:
        return created

    return _empty_poll_payload(symbol)


def get_poll_report(symbol: str) -> Dict[str, Any]:
    poll = get_weekly_poll(symbol)

    report = poll.get("report")
    if isinstance(report, dict):
        return report

    return {
        "version": POLL_SCHEMA_VERSION,
        "status": poll.get("status", "none"),
        "reason": poll.get("reason"),
        "options": [],
        "question_variants": [],
    }


def vote_poll(symbol: str, option_key: str, user_id: int) -> Dict[str, Any]:
    symbol = _normalize_symbol(symbol)
    option_key = str(option_key or "").upper().strip()

    if not symbol:
        raise ValueError("invalid_symbol")
    if option_key not in {"A", "B"}:
        raise ValueError("invalid_option")

    poll = get_weekly_poll(symbol)
    if not poll.get("id"):
        raise ValueError("no_active_poll")

    def mutator(store):
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
        return stored_poll

    return _mutate_store(mutator)


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


def generate_weekly_polls_for_top_symbols(limit: int = 20) -> List[Dict[str, Any]]:
    """Create event-driven polls for the top-ranked snapshot symbols.

    With no earnings and no economic event in the window this returns [] —
    that is the intended "no poll this week" state, not a failure.
    """
    limit = max(1, int(limit or 1))
    ranked = list(get_snapshot_by_ticker().values())
    ranked.sort(key=lambda item: float(item.get("score", 0) or 0), reverse=True)

    created: List[Dict[str, Any]] = []
    seen_symbols: set[str] = set()

    for signal in ranked:
        if len(created) >= limit:
            break

        symbol = _normalize_symbol(signal.get("ticker") or signal.get("symbol"))
        if not symbol or symbol in seen_symbols:
            continue
        seen_symbols.add(symbol)

        poll = ensure_weekly_poll(symbol=symbol, signal=signal)
        if poll is not None:
            created.append(poll)

    return created
