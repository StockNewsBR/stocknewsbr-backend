from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import apply_rls_context, get_db
from app.models import User
from app.security import get_current_user
from app.services.promo_codes import redeem_promo_code

router = APIRouter(prefix="/promo", tags=["Promo"])


@router.post("/redeem")
def redeem(
    code: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # Mission 36: share the canonical get_db so authentication and this endpoint
    # use the SAME Session (no local get_db). get_current_user already queried
    # the DB on this Session, so a transaction is active; bind the RLS context to
    # the authenticated user BEFORE the first PromoCode/PromoRedemption query.
    # No artificial query and no early commit are introduced; the existing
    # atomic redeem transaction (lock -> dedup -> increment -> insert -> commit)
    # is preserved. Failure to apply the context propagates (no redeem).
    apply_rls_context(
        db,
        current_user_id=int(current_user.id),
        current_actor_id=int(current_user.id),
        current_role="user",
        request_id=None,
    )
    return redeem_promo_code(db, current_user.id, code)
