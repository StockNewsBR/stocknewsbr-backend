import json
import logging
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Dict, List

from app.cache.snapshot_cache import get_snapshot_by_ticker
from app.config import CRYPTO_SYMBOLS

logger = logging.getLogger("stocknewsbr.polls")

POLL_STORE_PATH = Path("runtime/polls/weekly_polls.json")
MAX_POLLS = 2000
_lock = threading.RLock()


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _week_key(now: datetime | None = None) -> str:
    current = now or _utc_now()
    iso = current.isocalendar()
    return f"{iso.year}-W{iso.week:02d}"


def _poll_id(symbol: str, week_key: str) -> str:
    return f"{week_key}:{symbol.upper()}"


def _ensure_store_path():
    POLL_STORE_PATH.parent.mkdir(parents=True, exist_ok=True)


def _load_store() -> Dict[str, Any]:
    _ensure_store_path()

    if not POLL_STORE_PATH.exists():
        return {"polls": {}}

    try:
        return json.loads(POLL_STORE_PATH.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("Poll store load error: %s", exc)
        return {"polls": {}}


def _save_store(store: Dict[str, Any]):
    _ensure_store_path()
    POLL_STORE_PATH.write_text(
        json.dumps(store, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _classify_market_type(symbol: str) -> str:
    return "crypto" if symbol.upper() in set(CRYPTO_SYMBOLS) else "stock"


def _infer_earnings_week(signal: Dict[str, Any] | None) -> bool:
    if not signal:
        return False

    haystack_parts = [str(signal.get("signal", ""))]
    haystack_parts.extend(str(item) for item in signal.get("events", []))
    haystack = " ".join(haystack_parts).lower()
    return "earn" in haystack or "resultado" in haystack or "trimestre" in haystack


def _build_question_payload(
    symbol: str,
    market_type: str,
    earnings_week: bool,
) -> Dict[str, str]:
    if market_type == "crypto":
        return {
            "question": f"{symbol}: como a IA enxerga a tendencia desta semana?",
            "option_a": "Tendencia de alta baseada no fluxo e no mercado",
            "option_b": "Tendencia de baixa ou indecisao baseada no fluxo e no mercado",
        }

    if earnings_week:
        return {
            "question": f"{symbol}: a empresa vai bater o trimestre e reagir bem no mercado?",
            "option_a": "Vai bater o trimestre e o ativo tende a subir",
            "option_b": "Nao vai bater o trimestre ou o mercado pode reagir mal",
        }

    return {
        "question": f"{symbol}: qual o cenario mais provavel para esta semana?",
        "option_a": "Semana com tendencia de alta para este ativo",
        "option_b": "Semana sem tendencia aparente ou com viés de baixa",
    }


def ensure_weekly_poll(
    symbol: str,
    market_type: str | None = None,
    earnings_week: bool | None = None,
    signal: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    symbol = symbol.upper().strip()

    if not symbol:
        raise ValueError("invalid_symbol")

    market_type = market_type or _classify_market_type(symbol)
    earnings_week = _infer_earnings_week(signal) if earnings_week is None else earnings_week
    week_key = _week_key()
    poll_key = _poll_id(symbol, week_key)

    with _lock:
        store = _load_store()
        polls = store.setdefault("polls", {})

        if poll_key in polls:
            return polls[poll_key]

        question_payload = _build_question_payload(
            symbol=symbol,
            market_type=market_type,
            earnings_week=earnings_week,
        )

        poll = {
            "id": poll_key,
            "symbol": symbol,
            "market_type": market_type,
            "week_key": week_key,
            "earnings_week": bool(earnings_week),
            "created_by": "ai_worker",
            "created_at": _utc_now().isoformat(),
            "question": question_payload["question"],
            "options": [
                {"key": "A", "label": question_payload["option_a"], "votes": 0},
                {"key": "B", "label": question_payload["option_b"], "votes": 0},
            ],
            "voters": {},
        }

        polls[poll_key] = poll

        if len(polls) > MAX_POLLS:
            ordered_keys = sorted(polls.keys())
            for old_key in ordered_keys[: len(polls) - MAX_POLLS]:
                polls.pop(old_key, None)

        _save_store(store)
        return poll


def get_weekly_poll(symbol: str) -> Dict[str, Any]:
    symbol = symbol.upper().strip()
    week_key = _week_key()
    poll_key = _poll_id(symbol, week_key)

    with _lock:
        store = _load_store()
        poll = store.get("polls", {}).get(poll_key)

    if poll:
        return poll

    signal = get_snapshot_by_ticker().get(symbol)
    return ensure_weekly_poll(symbol=symbol, signal=signal)


def vote_poll(symbol: str, option_key: str, user_id: int) -> Dict[str, Any]:
    option_key = str(option_key or "").upper().strip()

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
        _save_store(store)
        return stored_poll


def get_poll_history(symbol: str, limit: int = 8) -> List[Dict[str, Any]]:
    symbol = symbol.upper().strip()

    with _lock:
        store = _load_store()
        polls = [
            poll
            for poll in store.get("polls", {}).values()
            if poll.get("symbol") == symbol
        ]

    polls.sort(key=lambda item: item.get("created_at", ""), reverse=True)
    return polls[:limit]


def generate_weekly_polls_for_top_symbols(limit: int = 20) -> List[Dict[str, Any]]:
    by_ticker = get_snapshot_by_ticker()
    ranked = list(by_ticker.values())
    ranked.sort(key=lambda item: float(item.get("score", 0) or 0), reverse=True)

    created: List[Dict[str, Any]] = []

    for signal in ranked[:limit]:
        symbol = signal.get("ticker") or signal.get("symbol")

        if not symbol:
            continue

        created.append(ensure_weekly_poll(symbol=symbol, signal=signal))

    for symbol in CRYPTO_SYMBOLS[:4]:
        created.append(ensure_weekly_poll(symbol=symbol, market_type="crypto"))

    return created
