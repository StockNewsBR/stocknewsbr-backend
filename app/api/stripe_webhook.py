import json
import logging
import os
import threading

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app.database import SessionLocal, get_db
from app.models import SubscriptionAuditLog, User
from app.security import get_current_user
from app.services.access_service import (
    activate_subscription,
    downgrade_to_free,
    log_subscription_event,
    pricing_catalog,
)
from app.services.referrals import apply_referral_validation, referral_leaderboard, referral_summary

router = APIRouter(prefix="/billing", tags=["Billing"])
logger = logging.getLogger("stocknewsbr.stripe_webhook")

_STRIPE = None
_STRIPE_WEBHOOK_LOCK = threading.RLock()
_STRIPE_ACTIVATION_EVENTS = {"invoice.payment_succeeded", "checkout.session.completed"}
_STRIPE_STATE_CHANGING_EVENTS = _STRIPE_ACTIVATION_EVENTS | {
    "customer.subscription.deleted",
    "invoice.payment_failed",
}
_STRIPE_ALLOWED_SUBSCRIPTION_STATUSES = {"active", "trialing"}

def _positive_int_from_env(name: str, default: int) -> int:
    try:
        value = int(os.getenv(name, str(default)).strip())
    except (AttributeError, ValueError):
        return default
    return value if value > 0 else default


_STRIPE_WEBHOOK_MAX_BYTES = _positive_int_from_env("STRIPE_WEBHOOK_MAX_BYTES", 262144)


def _webhook_secret() -> str:
    return os.getenv("STRIPE_WEBHOOK_SECRET", "").strip()


def _get_stripe():
    global _STRIPE
    if _STRIPE is None:
        import stripe as stripe_module

        stripe_module.api_key = os.getenv("STRIPE_SECRET_KEY", "")
        _STRIPE = stripe_module
    return _STRIPE


def _construct_verified_event(payload: bytes, signature: str | None) -> dict:
    secret = _webhook_secret()
    if not secret:
        raise HTTPException(status_code=503, detail="stripe_webhook_secret_not_configured")
    if not signature or not str(signature).strip():
        raise HTTPException(status_code=400, detail="stripe_signature_missing")

    try:
        event = _get_stripe().Webhook.construct_event(payload, signature, secret)
    except Exception as exc:
        raise HTTPException(status_code=400, detail="invalid_webhook_signature") from exc

    if not hasattr(event, "get"):
        raise HTTPException(status_code=400, detail="invalid_webhook_event")
    return event


async def _read_limited_body(request: Request, max_bytes: int) -> bytes:
    chunks: list[bytes] = []
    total = 0
    async for chunk in request.stream():
        total += len(chunk)
        if total > max_bytes:
            raise HTTPException(status_code=413, detail="stripe_webhook_payload_too_large")
        chunks.append(chunk)
    return b"".join(chunks)


def _event_identifier(event: dict) -> str:
    event_id = str(event.get("id") or "").strip()
    if not event_id:
        raise HTTPException(status_code=400, detail="stripe_event_id_missing")
    return event_id


def _event_type(event: dict) -> str:
    value = str(event.get("type") or "").strip()
    if not value:
        raise HTTPException(status_code=400, detail="stripe_event_type_missing")
    return value


def _stripe_audit_payload(event_id: str, event_type: str) -> str:
    return json.dumps(
        {
            "provider": "stripe",
            "event_id": event_id,
            "event_type": event_type,
        },
        sort_keys=True,
        separators=(",", ":"),
    )


def _metadata(data: dict) -> dict:
    metadata = data.get("metadata") or {}
    return metadata if isinstance(metadata, dict) else {}


def _required_stripe_id(data: dict, key: str, error_detail: str) -> str:
    value = data.get(key)
    if isinstance(value, dict):
        value = value.get("id")
    normalized = str(value or "").strip()
    if not normalized:
        raise HTTPException(status_code=422, detail=error_detail)
    return normalized


def _optional_stripe_id(data: dict, key: str) -> str | None:
    value = data.get(key)
    if isinstance(value, dict):
        value = value.get("id")
    normalized = str(value or "").strip()
    return normalized or None


def _metadata_user_id(data: dict) -> int | None:
    raw_value = _metadata(data).get("user_id")
    if raw_value in (None, ""):
        return None
    try:
        user_id = int(raw_value)
    except (TypeError, ValueError):
        raise HTTPException(status_code=422, detail="stripe_metadata_user_id_invalid")
    if user_id <= 0:
        raise HTTPException(status_code=422, detail="stripe_metadata_user_id_invalid")
    return user_id


def _allowed_billing_product_ids() -> set[str]:
    catalog = pricing_catalog().get("plans", {})
    allowed = {
        str(value)
        for plan in catalog.values()
        for key, value in plan.items()
        if key.endswith("_product_id") and value
    }
    allowed.update(
        item.strip()
        for item in os.getenv("STRIPE_ALLOWED_PRODUCT_IDS", "").split(",")
        if item.strip()
    )
    return allowed


def _add_candidate(candidates: list[str], value) -> None:
    if isinstance(value, str) and value.strip():
        candidates.append(value.strip())


def _product_candidates(value) -> list[str]:
    candidates: list[str] = []
    if isinstance(value, str):
        _add_candidate(candidates, value)
    elif isinstance(value, dict):
        _add_candidate(candidates, value.get("id"))
    return candidates


def _stripe_product_candidates(data: dict) -> list[str]:
    candidates: list[str] = []
    _add_candidate(candidates, data.get("product_id"))

    candidates.extend(_product_candidates(data.get("product")))

    for key in ("price", "plan"):
        value = data.get(key)
        if isinstance(value, dict):
            _add_candidate(candidates, value.get("product"))

    line_data = data.get("lines")
    if isinstance(line_data, dict):
        line_data = line_data.get("data")
    if isinstance(line_data, list):
        for item in line_data:
            if not isinstance(item, dict):
                continue
            _add_candidate(candidates, item.get("product_id"))
            price = item.get("price")
            if isinstance(price, dict):
                _add_candidate(candidates, price.get("product"))
            plan = item.get("plan")
            if isinstance(plan, dict):
                _add_candidate(candidates, plan.get("product"))
    return candidates


def _validated_product_id(data: dict) -> str:
    allowed = _allowed_billing_product_ids()
    concrete_candidates = _stripe_product_candidates(data)
    if not concrete_candidates or any(candidate not in allowed for candidate in concrete_candidates):
        raise HTTPException(status_code=422, detail="stripe_product_not_allowed")
    for candidate in concrete_candidates:
        if candidate in allowed:
            return candidate
    raise HTTPException(status_code=422, detail="stripe_product_not_allowed")


def _expected_livemode() -> bool:
    return os.getenv("STRIPE_LIVEMODE", "false").strip().lower() in {"1", "true", "yes", "live"}


def _validate_livemode(event: dict) -> None:
    actual = bool(event.get("livemode", False))
    if actual != _expected_livemode():
        raise HTTPException(status_code=422, detail="stripe_livemode_mismatch")


def _subscription_status_from_value(subscription) -> str | None:
    if hasattr(subscription, "get"):
        status = str(subscription.get("status") or "").strip().lower()
        return status or None
    return None


async def _retrieve_subscription_status(subscription_id: str) -> str | None:
    subscription_api = getattr(_get_stripe(), "Subscription", None)
    retrieve_async = getattr(subscription_api, "retrieve_async", None)
    if callable(retrieve_async):
        try:
            subscription = await retrieve_async(subscription_id)
        except Exception as exc:
            raise HTTPException(status_code=503, detail="stripe_subscription_verification_unavailable") from exc
        return _subscription_status_from_value(subscription)

    retrieve = getattr(subscription_api, "retrieve", None)
    if not callable(retrieve):
        raise HTTPException(status_code=503, detail="stripe_subscription_verification_unavailable")
    try:
        subscription = await run_in_threadpool(retrieve, subscription_id)
    except Exception as exc:
        raise HTTPException(status_code=503, detail="stripe_subscription_verification_unavailable") from exc
    return _subscription_status_from_value(subscription)


async def _ensure_subscription_state(data: dict, subscription_id: str) -> str:
    subscription_payload = data.get("subscription")
    status = _subscription_status_from_value(subscription_payload)
    if not status and not hasattr(subscription_payload, "get"):
        status = await _retrieve_subscription_status(subscription_id)
    if not status:
        raise HTTPException(status_code=422, detail="stripe_subscription_status_missing")
    if status not in _STRIPE_ALLOWED_SUBSCRIPTION_STATUSES:
        raise HTTPException(status_code=422, detail="stripe_subscription_not_active")
    return status


async def _validate_activation_event(event: dict, event_type: str, data: dict) -> tuple[str, str, str]:
    _validate_livemode(event)
    customer_id = _required_stripe_id(data, "customer", "stripe_customer_missing")
    subscription_id = _required_stripe_id(data, "subscription", "stripe_subscription_missing")
    subscription_status = await _ensure_subscription_state(data, subscription_id)
    product_id = _validated_product_id(data)

    if event_type == "checkout.session.completed":
        if str(data.get("mode") or "").strip().lower() != "subscription":
            raise HTTPException(status_code=422, detail="stripe_checkout_mode_invalid")
        payment_status = str(data.get("payment_status") or "").strip().lower()
        if payment_status == "no_payment_required" and subscription_status == "trialing":
            pass
        elif payment_status != "paid":
            raise HTTPException(status_code=422, detail="stripe_checkout_payment_not_paid")
        session_status = str(data.get("status") or "complete").strip().lower()
        if session_status not in {"complete", "completed"}:
            raise HTTPException(status_code=422, detail="stripe_checkout_status_invalid")

    if event_type == "invoice.payment_succeeded":
        if data.get("paid") is not True:
            raise HTTPException(status_code=422, detail="stripe_invoice_not_paid")
        if str(data.get("status") or "").strip().lower() != "paid":
            raise HTTPException(status_code=422, detail="stripe_invoice_status_invalid")

    return customer_id, subscription_id, product_id


def _ensure_customer_ownership(db: Session, user: User, customer_id: str, subscription_id: str) -> None:
    linked_customer = (
        db.query(User)
        .filter(User.stripe_customer_id == customer_id, User.id != user.id)
        .first()
    )
    if linked_customer:
        raise HTTPException(status_code=409, detail="stripe_customer_already_linked")

    if user.stripe_customer_id and user.stripe_customer_id != customer_id:
        raise HTTPException(status_code=409, detail="stripe_customer_mismatch")

    linked_subscription = (
        db.query(User)
        .filter(User.stripe_subscription_id == subscription_id, User.id != user.id)
        .first()
    )
    if linked_subscription:
        raise HTTPException(status_code=409, detail="stripe_subscription_already_linked")

    if user.stripe_subscription_id and user.stripe_subscription_id != subscription_id:
        raise HTTPException(status_code=409, detail="stripe_subscription_mismatch")


def _ensure_downgrade_event_ownership(user: User, data: dict, event_type: str) -> None:
    customer_id = _optional_stripe_id(data, "customer")
    subscription_id = _subscription_id_for_event(data, event_type)

    if customer_id and user.stripe_customer_id:
        if user.stripe_customer_id != customer_id:
            raise HTTPException(status_code=409, detail="stripe_customer_mismatch")

    if not subscription_id or not user.stripe_subscription_id:
        raise HTTPException(status_code=409, detail="stripe_event_ownership_mismatch")
    if user.stripe_subscription_id != subscription_id:
        raise HTTPException(status_code=409, detail="stripe_subscription_mismatch")


def _stripe_event_already_processed(db: Session, event_id: str, event_type: str) -> bool:
    return (
        db.query(SubscriptionAuditLog)
        .filter(
            SubscriptionAuditLog.provider == "stripe",
            SubscriptionAuditLog.provider_event_id == event_id,
        )
        .first()
        is not None
    )


@router.get("/pricing")
def billing_pricing(market: str = Query(default="BR", max_length=16)):
    return pricing_catalog(market)


@router.get("/referrals/leaderboard")
def billing_referral_leaderboard(
    limit: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db),
):
    result = referral_leaderboard(db, limit=limit)
    db.commit()
    return result


@router.get("/referrals/me")
def billing_referral_summary(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    result = referral_summary(db, current_user.id)
    db.commit()
    return result


def _subscription_id_for_event(data: dict, event_type: str) -> str | None:
    if event_type == "customer.subscription.deleted":
        return _optional_stripe_id(data, "id")
    return _optional_stripe_id(data, "subscription")


def _resolve_user(db: Session, data: dict, event_type: str):
    user_id = _metadata_user_id(data)
    customer_id = _optional_stripe_id(data, "customer")
    subscription_id = _subscription_id_for_event(data, event_type)

    query = db.query(User)

    if event_type in {"customer.subscription.deleted", "invoice.payment_failed"}:
        if subscription_id:
            user = query.filter(User.stripe_subscription_id == str(subscription_id)).first()
            if user:
                return user
        if customer_id:
            user = query.filter(User.stripe_customer_id == str(customer_id)).first()
            if user:
                return user
        if user_id is not None:
            return query.filter(User.id == user_id).first()
        return None

    if user_id is not None:
        user = query.filter(User.id == user_id).first()
        if user:
            return user

    if subscription_id:
        user = query.filter(User.stripe_subscription_id == str(subscription_id)).first()
        if user:
            return user

    if customer_id:
        return query.filter(User.stripe_customer_id == str(customer_id)).first()

    return None


@router.post("/stripe/webhook")
async def stripe_webhook(request: Request):
    content_length = request.headers.get("content-length")
    if content_length:
        try:
            if int(content_length) > _STRIPE_WEBHOOK_MAX_BYTES:
                raise HTTPException(status_code=413, detail="stripe_webhook_payload_too_large")
        except ValueError:
            raise HTTPException(status_code=400, detail="stripe_webhook_content_length_invalid")

    payload = await _read_limited_body(request, _STRIPE_WEBHOOK_MAX_BYTES)
    signature = request.headers.get("stripe-signature")

    event = _construct_verified_event(payload, signature)

    event_id = _event_identifier(event)
    event_type = _event_type(event)
    data = event.get("data", {}).get("object", {}) or {}
    payload_excerpt = _stripe_audit_payload(event_id, event_type)

    db: Session = SessionLocal()

    try:
        with _STRIPE_WEBHOOK_LOCK:
            if _stripe_event_already_processed(db, event_id, event_type):
                return {"status": "ok", "duplicate": True}

        activation_context = None
        if event_type in (_STRIPE_STATE_CHANGING_EVENTS - _STRIPE_ACTIVATION_EVENTS):
            _validate_livemode(event)
        if event_type in _STRIPE_ACTIVATION_EVENTS:
            activation_context = await _validate_activation_event(event, event_type, data)

        with _STRIPE_WEBHOOK_LOCK:
            if _stripe_event_already_processed(db, event_id, event_type):
                return {"status": "ok", "duplicate": True}

            user = _resolve_user(db, data, event_type)
            activated_subscription = False
            product_id = _metadata(data).get("product_id")
            customer_id = None
            subscription_id = _subscription_id_for_event(data, event_type) or ""

            if activation_context is not None:
                customer_id, subscription_id, product_id = activation_context

            if event_type in _STRIPE_STATE_CHANGING_EVENTS and not user:
                raise HTTPException(status_code=422, detail="stripe_user_not_resolved")

            if event_type in _STRIPE_ACTIVATION_EVENTS and user:
                _ensure_customer_ownership(db, user, customer_id, subscription_id)
                activate_subscription(
                    user,
                    provider="stripe",
                    product_id=product_id,
                    origin="website",
                    external_subscription_id=subscription_id,
                )
                user.stripe_customer_id = customer_id
                user.stripe_subscription_id = subscription_id
                activated_subscription = True

            if event_type in {"customer.subscription.deleted", "invoice.payment_failed"} and user:
                _ensure_downgrade_event_ownership(user, data, event_type)
                downgrade_to_free(user, reason="premium_inactive")

            log_subscription_event(
                db,
                user,
                provider="stripe",
                provider_event_id=event_id,
                event_type=event_type,
                product_id=product_id,
                origin="website",
                external_subscription_id=subscription_id,
                status=user.plan_status if user else "unresolved",
                payload_excerpt=payload_excerpt,
            )

            if user:
                db.add(user)
                if activated_subscription:
                    apply_referral_validation(db)

            db.commit()
            return {"status": "ok"}

    except IntegrityError:
        db.rollback()
        if _stripe_event_already_processed(db, event_id, event_type):
            return {"status": "ok", "duplicate": True}
        raise
    except HTTPException:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        logger.exception(
            "stripe_webhook_unexpected_error event_id=%s event_type=%s",
            event_id,
            event_type,
        )
        raise
    finally:
        db.close()
