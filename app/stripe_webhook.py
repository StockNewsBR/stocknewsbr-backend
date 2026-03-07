import stripe
from fastapi import APIRouter, Request
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import Referral


router = APIRouter()

stripe.api_key = "YOUR_STRIPE_SECRET_KEY"


@router.post("/stripe/webhook")
async def stripe_webhook(request: Request):

    payload = await request.json()

    event_type = payload["type"]

    if event_type == "invoice.payment_succeeded":

        data = payload["data"]["object"]

        user_id = data["metadata"]["user_id"]

        db: Session = SessionLocal()

        referral = db.query(Referral).filter(
            Referral.referred_user_id == user_id
        ).first()

        if referral:

            referral.status = "active"

            referral.validated_at = None

            db.commit()

    return {"status": "ok"}