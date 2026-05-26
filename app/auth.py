# ==========================================================
# STOCKNEWSBR AUTH ROUTES
# ==========================================================

import logging
import secrets

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User
from app.schemas import (
    AuthFlowResponse,
    LegalAcceptanceRequest,
    LoginOtpVerifyRequest,
    LogoutResponse,
    SubscriptionSyncRequest,
    TelegramLinkRequest,
    TelegramLinkSessionRequest,
    TelegramLinkSessionResponse,
    TokenResponse,
    UserAccessResponse,
    UserLogin,
    UserProfileUpdateRequest,
    UserRegister,
)
from app.security import (
    create_access_token,
    decode_access_token_payload,
    get_current_user,
    hash_password,
    oauth2_scheme,
    verify_password,
)
from app.services.auth_session_service import (
    TELEGRAM_BOT_USERNAME,
    consume_login_challenge,
    create_telegram_link_token,
    issue_access_token_for_user,
    login_requires_email_otp,
    normalize_channel,
    revoke_session,
    session_policy_for_user,
    should_return_debug_otp,
    start_login_challenge,
)
from app.services.access_service import (
    accept_legal_documents,
    activate_subscription,
    downgrade_to_free,
    ensure_referral_code,
    grant_trial_access,
    link_telegram_account,
    log_subscription_event,
    refresh_user_access,
    serialize_user_access,
)
from app.services.email_service import send_login_code_email
from app.services.legal_service import get_public_bootstrap
from app.services.referrals import register_referral, validate_referrals

logger = logging.getLogger("stocknewsbr.auth")

router = APIRouter(prefix="/auth", tags=["Auth"])


def _build_session_token(
    db: Session,
    user: User,
    channel: str = "web",
    device_id: str | None = None,
    device_label: str | None = None,
) -> TokenResponse:
    access_token, _session = issue_access_token_for_user(
        db=db,
        user=user,
        channel=channel,
        device_id=device_id,
        device_label=device_label,
    )
    return TokenResponse(access_token=access_token)


def _serialize_access(user: User) -> UserAccessResponse:
    return UserAccessResponse(**serialize_user_access(user))


def _require_legal_acceptance(user_data: UserRegister):
    if not (user_data.accepted_terms and user_data.accepted_privacy and user_data.accepted_risk_notice):
        raise HTTPException(status_code=400, detail="legal_acceptance_required")


def _complete_login(
    db: Session,
    user: User,
    channel: str,
    device_id: str | None = None,
    device_label: str | None = None,
) -> AuthFlowResponse:
    normalized_channel = normalize_channel(channel)

    if not user.is_active:
        raise HTTPException(status_code=403, detail="user_inactive")

    if login_requires_email_otp(user):
        challenge, code = start_login_challenge(
            db,
            user,
            channel=normalized_channel,
            device_id=device_id,
            device_label=device_label,
        )
        send_login_code_email(
            email=user.email,
            code=code,
            plan=user.plan,
            channel=normalized_channel,
            expires_minutes=max(1, int((challenge.expires_at - challenge.created_at).total_seconds() // 60)),
        )
        return AuthFlowResponse(
            otp_required=True,
            login_token=challenge.login_token,
            otp_expires_at=challenge.expires_at,
            debug_otp_code=code if should_return_debug_otp() else None,
            session_policy=session_policy_for_user(user),
            channel=normalized_channel,
            detail="premium_email_code_required",
        )

    access_token, _session = issue_access_token_for_user(
        db=db,
        user=user,
        channel=normalized_channel,
        device_id=device_id,
        device_label=device_label,
    )
    return AuthFlowResponse(
        access_token=access_token,
        session_policy=session_policy_for_user(user),
        channel=normalized_channel,
    )


@router.get("/bootstrap")
def auth_bootstrap():
    return get_public_bootstrap()


@router.post("/register", response_model=TokenResponse)
def register(user_data: UserRegister, db: Session = Depends(get_db)):
    _require_legal_acceptance(user_data)

    existing_user = db.query(User).filter(User.email == user_data.email).first()

    if existing_user:
        raise HTTPException(status_code=400, detail="email_already_registered")

    new_user = User(
        email=user_data.email,
        password_hash=hash_password(user_data.password),
        display_name=user_data.display_name,
        phone=user_data.phone,
        is_active=True,
        is_verified=True,
        referral_code=secrets.token_hex(4).upper(),
    )

    grant_trial_access(new_user)
    accept_legal_documents(
        new_user,
        accepted_terms=user_data.accepted_terms,
        accepted_privacy=user_data.accepted_privacy,
        accepted_risk_notice=user_data.accepted_risk_notice,
    )

    try:
        db.add(new_user)
        db.flush()
        ensure_referral_code(db, new_user)

        if user_data.referral_code:
            referrer = db.query(User).filter(User.referral_code == user_data.referral_code).first()

            if referrer:
                register_referral(db, referrer.id, new_user.id)

        db.commit()
        db.refresh(new_user)

    except HTTPException:
        db.rollback()
        raise
    except Exception as exc:
        db.rollback()
        logger.exception("Register error: %s", exc)
        raise HTTPException(status_code=500, detail="user_creation_failed")

    token_response = _build_session_token(
        db=db,
        user=new_user,
        channel=user_data.channel or "app",
        device_id=user_data.device_id,
        device_label=user_data.device_label,
    )
    db.commit()
    return token_response


@router.post("/login", response_model=AuthFlowResponse)
def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.email == form_data.username).first()

    if not user or not verify_password(form_data.password, user.password_hash):
        raise HTTPException(status_code=400, detail="invalid_credentials")

    refresh_user_access(user)
    db.add(user)
    response = _complete_login(
        db=db,
        user=user,
        channel="web",
        device_label="oauth_form_login",
    )
    db.commit()
    return response


@router.post("/login-json", response_model=AuthFlowResponse)
def login_json(user_data: UserLogin, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == user_data.email).first()

    if not user or not verify_password(user_data.password, user.password_hash):
        raise HTTPException(status_code=400, detail="invalid_credentials")

    refresh_user_access(user)
    db.add(user)
    response = _complete_login(
        db=db,
        user=user,
        channel=user_data.channel or "web",
        device_id=user_data.device_id,
        device_label=user_data.device_label,
    )
    db.commit()
    return response


@router.post("/login/verify-otp", response_model=AuthFlowResponse)
def verify_login_otp(payload: LoginOtpVerifyRequest, db: Session = Depends(get_db)):
    try:
        user, channel, device_id, device_label, _expires_at = consume_login_challenge(
            db,
            login_token=payload.login_token,
            code=payload.code,
        )
    except ValueError as exc:
        db.commit()
        raise HTTPException(status_code=400, detail=str(exc))

    refresh_user_access(user)
    db.add(user)

    if not user.is_active:
        raise HTTPException(status_code=403, detail="user_inactive")

    access_token, _session = issue_access_token_for_user(
        db=db,
        user=user,
        channel=channel,
        device_id=device_id,
        device_label=device_label,
    )
    db.commit()
    return AuthFlowResponse(
        access_token=access_token,
        session_policy=session_policy_for_user(user),
        channel=channel,
    )


@router.get("/me", response_model=UserAccessResponse)
def get_me(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    refresh_user_access(current_user)
    db.add(current_user)
    db.commit()
    db.refresh(current_user)
    return _serialize_access(current_user)


@router.get("/access", response_model=UserAccessResponse)
def get_access(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    refresh_user_access(current_user)
    db.add(current_user)
    db.commit()
    db.refresh(current_user)
    return _serialize_access(current_user)


@router.patch("/profile", response_model=UserAccessResponse)
def update_profile(
    payload: UserProfileUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if payload.email and payload.email != current_user.email:
        existing = db.query(User).filter(User.email == payload.email).first()
        if existing and existing.id != current_user.id:
            raise HTTPException(status_code=400, detail="email_already_registered")
        current_user.email = payload.email

    if payload.display_name is not None:
        current_user.display_name = payload.display_name.strip() or None

    if payload.avatar_url is not None:
        current_user.avatar_url = payload.avatar_url.strip() or None

    refresh_user_access(current_user)
    db.add(current_user)
    db.commit()
    db.refresh(current_user)
    return _serialize_access(current_user)


@router.post("/legal/accept", response_model=UserAccessResponse)
def accept_legal(
    payload: LegalAcceptanceRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    accept_legal_documents(
        current_user,
        accepted_terms=payload.accepted_terms,
        accepted_privacy=payload.accepted_privacy,
        accepted_risk_notice=payload.accepted_risk_notice,
    )
    db.add(current_user)
    db.commit()
    db.refresh(current_user)
    return _serialize_access(current_user)


@router.post("/subscription/sync", response_model=UserAccessResponse)
def subscription_sync(
    payload: SubscriptionSyncRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not payload.activate:
        downgrade_to_free(current_user, reason="premium_inactive")
    else:
        activate_subscription(
            current_user,
            provider=payload.provider,
            product_id=payload.product_id,
            origin=payload.origin,
            external_subscription_id=payload.external_subscription_id,
            purchase_token=payload.purchase_token,
            renewal_at=payload.renewal_at,
            started_at=payload.started_at,
        )

    log_subscription_event(
        db,
        current_user,
        provider=payload.provider,
        event_type="subscription_sync",
        product_id=payload.product_id,
        origin=payload.origin,
        external_subscription_id=payload.external_subscription_id,
        status=current_user.plan_status,
        payload_excerpt=str(payload.model_dump()),
    )
    if payload.activate:
        validate_referrals(db)

    db.add(current_user)
    db.commit()
    db.refresh(current_user)

    return _serialize_access(current_user)


@router.post("/telegram/link", response_model=UserAccessResponse)
def telegram_link(
    payload: TelegramLinkRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        link_telegram_account(
            db,
            current_user,
            telegram_id=payload.telegram_id,
            telegram_username=payload.telegram_username,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    db.add(current_user)
    db.commit()
    db.refresh(current_user)

    return _serialize_access(current_user)


@router.post("/telegram/link/request", response_model=TelegramLinkSessionResponse)
def telegram_link_request(
    payload: TelegramLinkSessionRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    refresh_user_access(current_user)

    try:
        link_token, deep_link = create_telegram_link_token(
            db,
            current_user,
            origin_channel=payload.origin_channel,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    db.add(current_user)
    db.commit()

    return TelegramLinkSessionResponse(
        link_code=link_token.link_code,
        deep_link=deep_link,
        bot_username=TELEGRAM_BOT_USERNAME or None,
        expires_at=link_token.expires_at,
        status="pending",
    )


@router.post("/logout", response_model=LogoutResponse)
def logout(
    token: str = Depends(oauth2_scheme),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    payload = decode_access_token_payload(token)
    revoke_session(
        db=db,
        user_id=current_user.id,
        session_id=str(payload.get("sid") or ""),
        reason="logout",
    )
    db.commit()
    return LogoutResponse(ok=True)
