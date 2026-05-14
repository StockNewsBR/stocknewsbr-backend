import json
import os

import stripe
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from app.database import SessionLocal, get_db
from app.models import User
from app.security import get_current_user
from app.services.access_service import (
    activate_subscription,
    downgrade_to_free,
    log_subscription_event,
    pricing_catalog,
)
from app.services.referrals import referral_leaderboard, referral_summary, validate_referrals

router = APIRouter(prefix="/billing", tags=["Billing"])

stripe.api_key = os.getenv("STRIPE_SECRET_KEY", "")
WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "")


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


def _resolve_user(db: Session, data: dict):
    metadata = data.get("metadata", {}) or {}
    user_id = metadata.get("user_id")
    customer_id = data.get("customer")
    subscription_id = data.get("subscription")

    query = db.query(User)

    if user_id:
        user = query.filter(User.id == int(user_id)).first()
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
    payload = await request.body()
    signature = request.headers.get("stripe-signature")

    try:
        if WEBHOOK_SECRET and signature:
            event = stripe.Webhook.construct_event(payload, signature, WEBHOOK_SECRET)
        else:
            event = json.loads(payload.decode("utf-8"))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"invalid_webhook: {exc}")

    event_type = event.get("type", "")
    data = event.get("data", {}).get("object", {}) or {}

    db: Session = SessionLocal()

    try:
        user = _resolve_user(db, data)

        if event_type in {"invoice.payment_succeeded", "checkout.session.completed"} and user:
            activate_subscription(
                user,
                provider="stripe",
                product_id=data.get("metadata", {}).get("product_id", "stripe_plan"),
                origin="website",
                external_subscription_id=str(data.get("subscription") or ""),
            )
            user.stripe_customer_id = str(data.get("customer") or user.stripe_customer_id or "")
            user.stripe_subscription_id = str(data.get("subscription") or user.stripe_subscription_id or "")

        if event_type in {"customer.subscription.deleted", "invoice.payment_failed"} and user:
            downgrade_to_free(user, reason="premium_inactive")

        log_subscription_event(
            db,
            user,
            provider="stripe",
            event_type=event_type,
            product_id=data.get("metadata", {}).get("product_id"),
            origin="website",
            external_subscription_id=str(data.get("subscription") or ""),
            status=user.plan_status if user else "unresolved",
            payload_excerpt=json.dumps(event)[:4000],
        )

        if user:
            db.add(user)
            if event_type in {"invoice.payment_succeeded", "checkout.session.completed"}:
                validate_referrals(db)

        db.commit()
        return {"status": "ok"}

    finally:
        db.close()
