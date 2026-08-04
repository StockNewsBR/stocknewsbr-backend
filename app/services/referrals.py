import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.models import Referral, ReferralStats, SubscriptionAuditLog, User
from app.services.access_service import PAID_PLANS, REFUND_WINDOW_DAYS

logger = logging.getLogger("stocknewsbr.referrals")

VALID_REFERRAL_STATUS = "validated"
PENDING_REFERRAL_STATUS = "pending"
ACTIVE_REFERRAL_STATUS = "active"
REFERRAL_REWARD_EVERY = 3
REFERRAL_REWARD_DAYS = 31
REFERRER_LOCK_BATCH_SIZE = 250
VIP_BADGE_AT = 10
LEADERBOARD_BADGE_AT = 100
PAYMENT_EVENTS = {"invoice.payment_succeeded", "checkout.session.completed", "subscription_sync"}


def _utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _as_naive_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is not None:
        return value.astimezone(timezone.utc).replace(tzinfo=None)
    return value


def _masked_name(user: User | None) -> str:
    if not user:
        return "Trader"

    raw_name = (user.display_name or "").strip()
    if not raw_name and user.email:
        raw_name = user.email.split("@", 1)[0].replace(".", " ").replace("_", " ")

    parts = [part for part in raw_name.split() if part]
    if not parts:
        return "Trader"

    first = parts[0].capitalize()
    if len(parts) == 1:
        return first

    return f"{first} {parts[-1][0].upper()}."


def referral_badge(total_validated: int) -> str | None:
    if total_validated >= LEADERBOARD_BADGE_AT:
        return "Leaderboard King"
    if total_validated >= VIP_BADGE_AT:
        return "Badge Vip"
    return None


def register_referral(db: Session, referrer_id: int, new_user_id: int):
    if not referrer_id or not new_user_id or referrer_id == new_user_id:
        return False

    try:
        existing = db.query(Referral).filter(Referral.referred_user_id == new_user_id).first()
        if existing:
            return False

        referrer = db.query(User).filter(User.id == referrer_id).first()
        referred = db.query(User).filter(User.id == new_user_id).first()
        if not referrer or not referred:
            return False
        if referrer.email and referred.email and referrer.email.strip().lower() == referred.email.strip().lower():
            return False

        db.add(
            Referral(
                referrer_id=referrer_id,
                referred_user_id=new_user_id,
                status=PENDING_REFERRAL_STATUS,
                created_at=_utcnow(),
            )
        )
        _ensure_stats(db, referrer_id)
        db.commit()
        return True

    except SQLAlchemyError as exc:
        db.rollback()
        logger.error("Referral register error: %s", exc)
        return False


def _ensure_stats(db: Session, user_id: int) -> ReferralStats:
    stats = db.query(ReferralStats).filter(ReferralStats.user_id == user_id).first()
    if stats:
        return stats

    stats = ReferralStats(
        user_id=user_id,
        total_validated=0,
        total_active=0,
        benefit_level=0,
        reward_balance_months=0,
    )
    db.add(stats)
    return stats


def _first_paid_at(db: Session, user_id: int) -> datetime | None:
    event = (
        db.query(SubscriptionAuditLog)
        .filter(
            SubscriptionAuditLog.user_id == user_id,
            SubscriptionAuditLog.status.in_(["active", "paid", "succeeded"]),
            SubscriptionAuditLog.event_type.in_(PAYMENT_EVENTS),
        )
        .order_by(SubscriptionAuditLog.created_at.asc())
        .first()
    )
    return _as_naive_utc(event.created_at) if event else None


def _is_paid_active(user: User | None, now: datetime) -> bool:
    if not user or str(user.plan or "").lower() not in PAID_PLANS:
        return False
    if str(user.plan_status or "").lower() not in {"active", "paid", "trialing"}:
        return False
    expires_at = _as_naive_utc(user.plan_expires_at)
    return expires_at is None or expires_at > now


def _qualifies_for_validation(db: Session, referral: Referral, now: datetime) -> bool:
    referred = referral.referred_user
    if not _is_paid_active(referred, now):
        return False

    paid_at = _first_paid_at(db, referral.referred_user_id)
    if not paid_at:
        return False

    return now - paid_at >= timedelta(days=REFUND_WINDOW_DAYS + 1)


def _apply_reward_months(user: User | None, stats: ReferralStats, months: int, now: datetime):
    if months <= 0:
        return False

    if not _is_paid_active(user, now):
        return False

    stats.reward_balance_months = (stats.reward_balance_months or 0) + months
    extension = timedelta(days=REFERRAL_REWARD_DAYS * months)
    expires_at = _as_naive_utc(user.plan_expires_at) or now
    user.plan_expires_at = max(expires_at, now) + extension
    return True


def _sync_referrer_stats(db: Session, referrer_id: int, now: datetime):
    stats = _ensure_stats(db, referrer_id)
    validated_refs = (
        db.query(Referral)
        .filter(
            Referral.referrer_id == referrer_id,
            Referral.status == VALID_REFERRAL_STATUS,
        )
        .all()
    )
    active_count = sum(1 for ref in validated_refs if _is_paid_active(ref.referred_user, now))
    total_validated = len(validated_refs)

    stats.total_validated = total_validated
    stats.total_active = active_count

    earned_reward_months = total_validated // REFERRAL_REWARD_EVERY
    processed_months = stats.benefit_level or 0
    new_months = max(0, earned_reward_months - processed_months)
    if new_months:
        applied = _apply_reward_months(db.query(User).filter(User.id == referrer_id).first(), stats, new_months, now)
        if applied:
            stats.benefit_level = earned_reward_months

    return stats


def _lock_referrers_for_update(db: Session, referrer_ids: set[int]) -> None:
    ordered_ids = sorted(referrer_id for referrer_id in referrer_ids if referrer_id)
    for index in range(0, len(ordered_ids), REFERRER_LOCK_BATCH_SIZE):
        batch = ordered_ids[index : index + REFERRER_LOCK_BATCH_SIZE]
        (
            db.query(User)
            .filter(User.id.in_(batch))
            .order_by(User.id.asc())
            .populate_existing()
            .with_for_update(of=User)
            .all()
        )


def apply_referral_validation(db: Session, now: datetime | None = None) -> dict:
    """
    Executa a validação e mutação de referrals na sessão fornecida.

    NÃO executa commit nem rollback.
    Propaga exceções não tratadas ao caller.
    O caller é responsável pelo commit/rollback atômico.

    Retorna: {"validated": int, "processed_referrers": int}
    """
    now = _as_naive_utc(now) or _utcnow()
    changed = 0

    touched_referrers: set[int] = set()
    last_referral_id = 0
    while True:
        referrals = (
            db.query(Referral)
            .filter(
                Referral.status.in_([PENDING_REFERRAL_STATUS, ACTIVE_REFERRAL_STATUS]),
                Referral.id > last_referral_id,
            )
            .order_by(Referral.id.asc())
            .limit(500)
            .with_for_update(of=Referral, skip_locked=True)
            .all()
        )
        if not referrals:
            break

        last_referral_id = referrals[-1].id or last_referral_id
        for referral in referrals:
            if not _qualifies_for_validation(db, referral, now):
                continue
            referral.status = VALID_REFERRAL_STATUS
            referral.validated_at = referral.validated_at or now
            referral.reward_processed = True
            touched_referrers.add(referral.referrer_id)
            changed += 1

    _lock_referrers_for_update(db, touched_referrers)
    for referrer_id in sorted(touched_referrers):
        _sync_referrer_stats(db, referrer_id, now)

    return {"validated": changed, "processed_referrers": len(touched_referrers)}


def validate_referrals(db: Session, now: datetime | None = None) -> dict:
    """
    Wrapper legado compatível: executa apply_referral_validation
    e gerencia commit/rollback internamente.

    Mantido para referral_worker e testes legados.
    """
    try:
        result = apply_referral_validation(db, now)
        db.commit()
        return result
    except SQLAlchemyError as exc:
        db.rollback()
        logger.error("Referral validation error: %s", exc.__class__.__name__)
        return {"validated": 0, "processed_referrers": 0, "error": "database_error"}
    except Exception:
        db.rollback()
        raise


def referral_summary(db: Session, user_id: int):
    stats = db.query(ReferralStats).filter(ReferralStats.user_id == user_id).first()
    paid_refs = (
        db.query(Referral)
        .filter(Referral.referrer_id == user_id, Referral.status == VALID_REFERRAL_STATUS)
        .order_by(Referral.validated_at.desc())
        .all()
    )
    return {
        "user_id": user_id,
        "total_validated": (stats.total_validated or 0) if stats else 0,
        "total_active": (stats.total_active or 0) if stats else 0,
        "reward_balance_months": (stats.reward_balance_months or 0) if stats else 0,
        "earned_reward_months": ((stats.total_validated or 0) if stats else 0) // REFERRAL_REWARD_EVERY,
        "badge": referral_badge((stats.total_validated or 0) if stats else 0),
        "paid_referrals": [_masked_name(ref.referred_user) for ref in paid_refs],
        "rules": {
            "valid_after_days": REFUND_WINDOW_DAYS + 1,
            "reward_every_paid_referrals": REFERRAL_REWARD_EVERY,
            "reward_months": 1,
            "cashback": False,
        },
    }


def referral_leaderboard(db: Session, limit: int = 50):
    stats_rows = (
        db.query(ReferralStats)
        .filter(ReferralStats.total_validated > 0)
        .order_by(ReferralStats.total_validated.desc(), ReferralStats.total_active.desc())
        .limit(max(1, min(limit, 100)))
        .all()
    )

    rows = []
    for position, stats in enumerate(stats_rows, start=1):
        validated_refs = (
            db.query(Referral)
            .filter(Referral.referrer_id == stats.user_id, Referral.status == VALID_REFERRAL_STATUS)
            .order_by(Referral.validated_at.desc())
            .limit(10)
            .all()
        )
        total = stats.total_validated or 0
        rows.append(
            {
                "position": position,
                "name": _masked_name(stats.user),
                "badge": referral_badge(total),
                "total_validated": total,
                "total_active": stats.total_active or 0,
                "paid_referrals": [_masked_name(ref.referred_user) for ref in validated_refs],
            }
        )

    return {
        "items": rows,
        "rules": {
            "valid_after_days": REFUND_WINDOW_DAYS + 1,
            "reward": "1 free month after each 3 paid referrals; 10 adds Badge Vip; 100+ adds Leaderboard King",
            "vip_badge_at": VIP_BADGE_AT,
            "leaderboard_badge_at": LEADERBOARD_BADGE_AT,
        },
    }
