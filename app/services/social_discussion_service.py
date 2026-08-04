from __future__ import annotations

import time
from typing import Any


_DISCUSSION_TERMS = (
    "suporte",
    "resistencia",
    "resistência",
    "vwap",
    "volume",
    "fluxo",
    "liquidez",
    "rompimento",
    "pullback",
    "rejeicao",
    "rejeição",
    "absorção",
    "absorcao",
    "risco",
    "trigger",
    "gatilho",
    "invalidacao",
    "invalidação",
    "earnings",
    "resultado",
    "guidance",
    "short",
    "long",
    "compra",
    "venda",
)


def _normalize_symbol(symbol: Any) -> str:
    value = str(symbol or "").upper().strip()
    if value.endswith(".SA"):
        value = value[:-3]
    return value


def _comment_count(post: dict[str, Any]) -> int:
    comments = post.get("comments")
    if isinstance(comments, list):
        return len(comments)
    return 0


def _post_timestamp(post: dict[str, Any]) -> float | None:
    value = post.get("timestamp")
    try:
        if value is None:
            return None
        return float(value)
    except Exception:
        return None


def score_discussion_post(symbol: str, post: dict[str, Any], now_ts: float | None = None) -> dict[str, Any]:
    normalized = _normalize_symbol(symbol)
    post_symbol = _normalize_symbol(post.get("ticker"))
    text = str(post.get("text") or "")
    lowered = text.lower()
    now_ts = float(now_ts if now_ts is not None else time.time())

    score = 0.0
    reasons: list[str] = []

    if post_symbol == normalized:
        score += 28.0
        reasons.append("ticker_match")
    else:
        reasons.append("ticker_mismatch")

    if normalized and (normalized.lower() in lowered or f"${normalized.lower()}" in lowered):
        score += 8.0
        reasons.append("symbol_mentioned")

    term_hits = [term for term in _DISCUSSION_TERMS if term in lowered]
    if term_hits:
        score += min(24.0, len(set(term_hits)) * 4.0)
        reasons.append("operational_terms")

    likes = max(0, int(post.get("likes") or 0))
    reposts = max(0, int(post.get("reposts") or 0))
    comments_count = _comment_count(post)
    score += min(30.0, likes * 3.0 + reposts * 5.0 + comments_count * 4.0)
    if likes or reposts or comments_count:
        reasons.append("engagement")

    if post.get("is_followed_by_me"):
        score += 3.0
        reasons.append("followed_author")

    timestamp = _post_timestamp(post)
    if timestamp:
        age_hours = max(0.0, (now_ts - timestamp) / 3600.0)
        recency_score = max(0.0, 10.0 - min(10.0, age_hours / 3.0))
        score += recency_score
        if recency_score >= 6.0:
            reasons.append("recent")

    if len(text.strip()) >= 40:
        score += 4.0
        reasons.append("substantive_text")

    return {
        "score": round(score, 2),
        "reasons": reasons,
    }


def rank_featured_discussions(
    symbol: str,
    posts: list[dict[str, Any]] | None,
    limit: int = 4,
    now_ts: float | None = None,
) -> list[dict[str, Any]]:
    normalized = _normalize_symbol(symbol)
    limit = max(1, min(int(limit or 4), 12))
    ranked: list[dict[str, Any]] = []

    for post in posts or []:
        if not isinstance(post, dict):
            continue
        if _normalize_symbol(post.get("ticker")) != normalized:
            continue
        relevance = score_discussion_post(normalized, post, now_ts=now_ts)
        enriched = dict(post)
        enriched["discussion_relevance_score"] = relevance["score"]
        enriched["discussion_relevance_reason"] = relevance["reasons"]
        ranked.append(enriched)

    ranked.sort(
        key=lambda item: (
            float(item.get("discussion_relevance_score") or 0.0),
            float(item.get("timestamp") or 0.0),
            int(item.get("id") or 0),
        ),
        reverse=True,
    )
    return ranked[:limit]


def build_discussion_state(
    symbol: str,
    posts: list[dict[str, Any]] | None,
    featured_posts: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    normalized = _normalize_symbol(symbol)
    post_count = len(posts or [])
    featured_count = len(featured_posts or [])

    if post_count <= 0:
        return {
            "symbol": normalized,
            "status": "empty",
            "message": f"Sem discussao real para {normalized} agora.",
            "count": 0,
            "featured_count": 0,
        }

    if featured_count <= 0:
        return {
            "symbol": normalized,
            "status": "no_relevant_discussion",
            "message": f"Ha posts em {normalized}, mas nenhum com leitura operacional suficiente.",
            "count": post_count,
            "featured_count": 0,
        }

    return {
        "symbol": normalized,
        "status": "ok",
        "message": f"{featured_count} discussoes de {normalized} priorizadas por relevancia operacional.",
        "count": post_count,
        "featured_count": featured_count,
    }
