import json
import os
import threading
import time
from pathlib import Path

from app.database import SessionLocal
from app.models import User
from app.services.push_service import get_push_token_store, send_push_notification


PUSH_DISPATCH_STATE_PATH = Path("data/push_dispatch_state.json")
PUSH_SCORE_THRESHOLD = float(os.getenv("PUSH_SIGNAL_SCORE_THRESHOLD", "85"))
PUSH_MAX_SIGNALS_PER_CYCLE = max(1, int(os.getenv("PUSH_MAX_SIGNALS_PER_CYCLE", "2")))
PUSH_SIGNAL_COOLDOWN_SECONDS = max(300, int(os.getenv("PUSH_SIGNAL_COOLDOWN_SECONDS", "1800")))
_lock = threading.RLock()


def _load_state():
    with _lock:
        if not PUSH_DISPATCH_STATE_PATH.exists():
            return {}

        try:
            return json.loads(PUSH_DISPATCH_STATE_PATH.read_text(encoding="utf-8"))
        except Exception:
            return {}


def _save_state(state):
    with _lock:
        PUSH_DISPATCH_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        PUSH_DISPATCH_STATE_PATH.write_text(
            json.dumps(state, ensure_ascii=True, indent=2),
            encoding="utf-8",
        )


def _eligible_signals(signals):
    ranked = []

    for item in signals or []:
        if not isinstance(item, dict):
            continue

        try:
            score = float(item.get("score", 0) or 0)
        except Exception:
            score = 0.0

        if score < PUSH_SCORE_THRESHOLD:
            continue

        ticker = item.get("ticker") or item.get("symbol")

        if not ticker:
            continue

        ranked.append((score, item))

    ranked.sort(key=lambda row: row[0], reverse=True)
    return [item for _, item in ranked[:PUSH_MAX_SIGNALS_PER_CYCLE]]


def dispatch_signal_pushes(signals):
    candidates = _eligible_signals(signals)

    if not candidates:
        return {"sent": 0, "signals": 0}

    now = int(time.time())
    state = _load_state()
    token_store = get_push_token_store()
    token_user_ids = []

    for key, tokens in token_store.items():
        if not tokens:
            continue
        try:
            token_user_ids.append(int(key))
        except Exception:
            continue

    token_user_ids = sorted(set(token_user_ids))

    if not token_user_ids:
        return {"sent": 0, "signals": len(candidates)}

    dispatched = 0
    db = SessionLocal()

    try:
        users = (
            db.query(User)
            .filter(User.is_active == True, User.access_app == True)  # noqa: E712
            .filter(User.id.in_(token_user_ids))
            .all()
        )

        for signal in candidates:
            ticker = str(signal.get("ticker") or signal.get("symbol"))
            last_sent = int(state.get(ticker, 0) or 0)

            if now - last_sent < PUSH_SIGNAL_COOLDOWN_SECONDS:
                continue

            title = f"Alerta SNBR: {ticker}"
            body = (
                f"Score {round(float(signal.get('score', 0) or 0), 2)} | "
                f"Trend {signal.get('trend') or 'n/a'}"
            )

            signal_sent = 0

            for user in users:
                tokens = token_store.get(str(user.id), [])
                if not tokens:
                    continue

                result = send_push_notification(
                    user_id=user.id,
                    title=title,
                    body=body,
                    data={
                        "ticker": ticker,
                        "score": str(signal.get("score", "")),
                        "trend": str(signal.get("trend", "")),
                    },
                    tokens=tokens,
                )
                signal_sent += int(result.get("sent", 0) or 0)

            if signal_sent > 0:
                state[ticker] = now
                dispatched += signal_sent

        _save_state(state)
        return {"sent": dispatched, "signals": len(candidates)}
    finally:
        db.close()
