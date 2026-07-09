# ==========================================================
# STOCKNEWSBR AUTH ROUTES
# ==========================================================

import json
import logging
import secrets
from datetime import timedelta
from typing import NoReturn
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, Response
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.settings import (
    login_code_expiry_seconds,
    session_cookie_name,
    session_cookie_samesite,
    session_cookie_secure,
)
from app.database import SessionLocal, get_db
from app.models import User
from app.schemas import (
    AuthFlowResponse,
    EmailChangeRequest,
    EmailChangeRequestResponse,
    EmailChangeVerifyRequest,
    LegalAcceptanceRequest,
    LoginCodeRequest,
    LoginCodeRequestResponse,
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
    ACCESS_TOKEN_EXPIRE_MINUTES,
    decode_access_token_payload,
    get_current_user,
    get_request_token,
    hash_password,
    verify_password,
)
from app.services import auth_audit_service as auth_audit
from app.services.auth_session_service import (
    CHALLENGE_PURPOSE_EMAIL_CHANGE,
    DELIVERY_FAILED,
    DELIVERY_SENT,
    TELEGRAM_BOT_USERNAME,
    challenge_expiry_minutes,
    consume_email_change_challenge,
    consume_login_challenge,
    create_telegram_link_token,
    invalidate_open_challenges,
    issue_access_token_for_user,
    login_code_rate_limit_state,
    login_requires_email_otp,
    mark_challenge_delivery,
    normalize_channel,
    normalize_email,
    request_login_code,
    revoke_all_sessions,
    revoke_session,
    session_policy_for_user,
    start_login_challenge,
    utcnow,
)
from app.services.access_service import (
    accept_legal_documents,
    downgrade_to_free,
    ensure_referral_code,
    grant_trial_access,
    link_telegram_account,
    log_subscription_event,
    refresh_user_access,
    serialize_user_access,
)
from app.services.email_service import (
    send_email_change_code_email,
    send_email_change_notice_email,
    send_login_code_email,
)
from app.services.legal_service import get_public_bootstrap
from app.services.referrals import register_referral

logger = logging.getLogger("stocknewsbr.auth")

router = APIRouter(prefix="/auth", tags=["Auth"])

PROVIDER_VERIFICATION_BLOCKED_DETAIL = "subscription_provider_verification_unavailable"
GENERIC_LOGIN_CODE_DETAIL = "Se o e-mail estiver apto, enviaremos um código de acesso."
GENERIC_EMAIL_CHANGE_DETAIL = "Se o e-mail informado estiver apto, enviaremos um código de confirmação."
RATE_LIMITED_DETAIL = "Muitas tentativas. Aguarde antes de tentar novamente."

OTP_ERROR_AUDIT_EVENTS = {
    "otp_invalid": ("login_code_invalid", None),
    "otp_already_used": ("login_code_invalid", "already_used"),
    "otp_expired": ("login_code_expired", None),
    "otp_too_many_attempts": ("login_code_rate_limited", "attempts_exceeded"),
}


# ==========================================================
# REQUEST CONTEXT HELPERS
# ==========================================================

def _correlation_id(request: Request | None) -> str:
    if request is not None:
        header_value = str(request.headers.get("x-request-id") or "").strip()
        if header_value:
            return header_value[:64]
    return uuid4().hex


def _client_ip_hash(request: Request | None) -> str | None:
    if request is None or request.client is None:
        return None
    return auth_audit.hash_ip(request.client.host)


def _user_agent(request: Request | None) -> str | None:
    if request is None:
        return None
    return auth_audit.summarize_user_agent(request.headers.get("user-agent"))


def _set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=session_cookie_name(),
        value=token,
        max_age=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        path="/",
        httponly=True,
        secure=session_cookie_secure(),
        samesite=session_cookie_samesite(),
    )


def _clear_session_cookie(response: Response) -> None:
    response.delete_cookie(
        key=session_cookie_name(),
        path="/",
        httponly=True,
        secure=session_cookie_secure(),
        samesite=session_cookie_samesite(),
    )


# ==========================================================
# EMAIL DELIVERY (outside the request transaction)
# ==========================================================

def _deliver_challenge_email(
    challenge_id: int,
    *,
    email: str,
    code: str,
    purpose: str,
    plan: str,
    channel: str,
    expires_minutes: int,
    correlation_id: str | None,
) -> None:
    db = SessionLocal()

    try:
        auth_audit.record_auth_event(
            db,
            "login_code_delivery_started",
            email=email,
            correlation_id=correlation_id,
        )
        db.commit()

        try:
            if purpose == CHALLENGE_PURPOSE_EMAIL_CHANGE:
                result = send_email_change_code_email(
                    email=email,
                    code=code,
                    expires_minutes=expires_minutes,
                )
            else:
                result = send_login_code_email(
                    email=email,
                    code=code,
                    plan=plan,
                    channel=channel,
                    expires_minutes=expires_minutes,
                )
            delivered = bool(result.get("delivered"))
        except Exception:
            logger.exception("Login code delivery failed")
            delivered = False

        mark_challenge_delivery(
            db,
            challenge_id,
            DELIVERY_SENT if delivered else DELIVERY_FAILED,
            correlation_id=correlation_id,
            email=email,
        )
    finally:
        db.close()


def _decoy_login_code_response() -> LoginCodeRequestResponse:
    return LoginCodeRequestResponse(
        detail=GENERIC_LOGIN_CODE_DETAIL,
        login_token=secrets.token_urlsafe(24),
        otp_expires_at=utcnow() + timedelta(seconds=login_code_expiry_seconds()),
    )


# ==========================================================
# SESSION ISSUANCE
# ==========================================================

def _issue_session(
    db: Session,
    response: Response | None,
    user: User,
    channel: str,
    device_id: str | None = None,
    device_label: str | None = None,
    *,
    request: Request | None = None,
    correlation_id: str | None = None,
) -> AuthFlowResponse:
    normalized_channel = normalize_channel(channel)
    resolved_correlation = correlation_id or _correlation_id(request)

    access_token, session = issue_access_token_for_user(
        db=db,
        user=user,
        channel=normalized_channel,
        device_id=device_id,
        device_label=device_label,
        created_ip_hash=_client_ip_hash(request),
        user_agent=_user_agent(request),
        correlation_id=resolved_correlation,
    )

    auth_audit.record_auth_event(
        db,
        "session_created",
        user_id=user.id,
        email=user.email,
        ip_hash_value=_client_ip_hash(request),
        user_agent=_user_agent(request),
        session_id=session.session_id,
        correlation_id=resolved_correlation,
    )
    auth_audit.record_auth_event(
        db,
        "login_success",
        user_id=user.id,
        email=user.email,
        ip_hash_value=_client_ip_hash(request),
        user_agent=_user_agent(request),
        session_id=session.session_id,
        correlation_id=resolved_correlation,
    )
    db.commit()

    if normalized_channel == "web" and response is not None:
        # Web transport: httpOnly cookie only — the sensitive token is not
        # repeated in the JSON payload.
        _set_session_cookie(response, access_token)
        return AuthFlowResponse(
            session_policy=session_policy_for_user(user),
            channel=normalized_channel,
            detail="session_created",
        )

    return AuthFlowResponse(
        access_token=access_token,
        session_policy=session_policy_for_user(user),
        channel=normalized_channel,
    )


def _serialize_access(user: User) -> UserAccessResponse:
    return UserAccessResponse(**serialize_user_access(user))


def _subscription_sync_audit_payload(payload: SubscriptionSyncRequest, status: str) -> str:
    return json.dumps(
        {
            "provider": payload.provider,
            "event_type": "subscription_sync",
            "product_id": payload.product_id,
            "origin": payload.origin,
            "status": status,
        },
        sort_keys=True,
        separators=(",", ":"),
    )


def _reject_unverified_subscription_activation() -> NoReturn:
    raise HTTPException(
        status_code=503,
        detail=PROVIDER_VERIFICATION_BLOCKED_DETAIL,
    )


def _require_legal_acceptance(user_data: UserRegister):
    if not (user_data.accepted_terms and user_data.accepted_privacy and user_data.accepted_risk_notice):
        raise HTTPException(status_code=400, detail="legal_acceptance_required")


def _complete_login(
    db: Session,
    user: User,
    channel: str,
    device_id: str | None = None,
    device_label: str | None = None,
    *,
    request: Request | None = None,
    response: Response | None = None,
    background_tasks: BackgroundTasks | None = None,
) -> AuthFlowResponse:
    normalized_channel = normalize_channel(channel)
    correlation_id = _correlation_id(request)

    if not user.is_active:
        raise HTTPException(status_code=403, detail="user_inactive")

    if login_requires_email_otp(user):
        challenge, code = start_login_challenge(
            db,
            user,
            channel=normalized_channel,
            device_id=device_id,
            device_label=device_label,
            request_ip_hash=_client_ip_hash(request),
            correlation_id=correlation_id,
        )
        db.commit()

        expires_minutes = challenge_expiry_minutes(challenge)

        if background_tasks is not None:
            background_tasks.add_task(
                _deliver_challenge_email,
                challenge.id,
                email=user.email,
                code=code,
                purpose=challenge.purpose,
                plan=user.plan,
                channel=normalized_channel,
                expires_minutes=expires_minutes,
                correlation_id=correlation_id,
            )
        else:
            _deliver_challenge_email(
                challenge.id,
                email=user.email,
                code=code,
                purpose=challenge.purpose,
                plan=user.plan,
                channel=normalized_channel,
                expires_minutes=expires_minutes,
                correlation_id=correlation_id,
            )

        return AuthFlowResponse(
            otp_required=True,
            login_token=challenge.login_token,
            otp_expires_at=challenge.expires_at,
            session_policy=session_policy_for_user(user),
            channel=normalized_channel,
            detail="premium_email_code_required",
        )

    return _issue_session(
        db=db,
        response=response,
        user=user,
        channel=normalized_channel,
        device_id=device_id,
        device_label=device_label,
        request=request,
        correlation_id=correlation_id,
    )


@router.get("/bootstrap")
def auth_bootstrap():
    return get_public_bootstrap()


@router.post("/register", response_model=TokenResponse)
def register(user_data: UserRegister, db: Session = Depends(get_db)):
    _require_legal_acceptance(user_data)

    existing_user = db.query(User).filter(User.email == normalize_email(user_data.email)).first()

    if existing_user:
        raise HTTPException(status_code=400, detail="email_already_registered")

    new_user = User(
        email=normalize_email(user_data.email),
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

    access_token, _session = issue_access_token_for_user(
        db=db,
        user=new_user,
        channel=normalize_channel(user_data.channel or "app"),
        device_id=user_data.device_id,
        device_label=user_data.device_label,
    )
    db.commit()
    return TokenResponse(access_token=access_token)


@router.post("/request-code", response_model=LoginCodeRequestResponse)
def request_code(
    payload: LoginCodeRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """Mission 31B passwordless REQUEST_CODE flow (existing accounts only).

    Public response is always generic: it never reveals whether the account
    exists, is banned or is premium. Unknown e-mails receive a decoy token.
    """
    correlation_id = _correlation_id(request)
    outcome = request_login_code(
        db,
        payload.email,
        channel=payload.channel or "web",
        device_id=payload.device_id,
        device_label=payload.device_label,
        request_ip_hash=_client_ip_hash(request),
        user_agent=_user_agent(request),
        correlation_id=correlation_id,
    )

    if outcome["status"] == "rate_limited":
        raise HTTPException(status_code=429, detail=RATE_LIMITED_DETAIL)

    if outcome["status"] != "accepted":
        return _decoy_login_code_response()

    challenge = outcome["challenge"]
    user = outcome["user"]

    background_tasks.add_task(
        _deliver_challenge_email,
        challenge.id,
        email=user.email,
        code=outcome["code"],
        purpose=challenge.purpose,
        plan=user.plan,
        channel=challenge.channel,
        expires_minutes=challenge_expiry_minutes(challenge),
        correlation_id=correlation_id,
    )

    return LoginCodeRequestResponse(
        detail=GENERIC_LOGIN_CODE_DETAIL,
        login_token=challenge.login_token,
        otp_expires_at=challenge.expires_at,
    )


@router.post("/login", response_model=AuthFlowResponse)
def login(
    request: Request,
    response: Response,
    background_tasks: BackgroundTasks,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.email == normalize_email(form_data.username)).first()

    if not user or not verify_password(form_data.password, user.password_hash):
        auth_audit.record_auth_event(
            db,
            "login_failed",
            email=form_data.username,
            ip_hash_value=_client_ip_hash(request),
            user_agent=_user_agent(request),
            reason="invalid_credentials",
            correlation_id=_correlation_id(request),
        )
        db.commit()
        raise HTTPException(status_code=400, detail="invalid_credentials")

    refresh_user_access(user)
    db.add(user)
    result = _complete_login(
        db=db,
        user=user,
        channel="web",
        device_label="oauth_form_login",
        request=request,
        response=response,
        background_tasks=background_tasks,
    )
    db.commit()
    return result


@router.post("/login-json", response_model=AuthFlowResponse)
def login_json(
    user_data: UserLogin,
    request: Request,
    response: Response,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.email == normalize_email(user_data.email)).first()

    if not user or not verify_password(user_data.password, user.password_hash):
        auth_audit.record_auth_event(
            db,
            "login_failed",
            email=user_data.email,
            ip_hash_value=_client_ip_hash(request),
            user_agent=_user_agent(request),
            reason="invalid_credentials",
            correlation_id=_correlation_id(request),
        )
        db.commit()
        raise HTTPException(status_code=400, detail="invalid_credentials")

    refresh_user_access(user)
    db.add(user)
    result = _complete_login(
        db=db,
        user=user,
        channel=user_data.channel or "web",
        device_id=user_data.device_id,
        device_label=user_data.device_label,
        request=request,
        response=response,
        background_tasks=background_tasks,
    )
    db.commit()
    return result


@router.post("/login/verify-otp", response_model=AuthFlowResponse)
def verify_login_otp(
    payload: LoginOtpVerifyRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    correlation_id = _correlation_id(request)

    try:
        user, channel, device_id, device_label, _expires_at = consume_login_challenge(
            db,
            login_token=payload.login_token,
            code=payload.code,
        )
    except ValueError as exc:
        detail = str(exc)
        event, reason = OTP_ERROR_AUDIT_EVENTS.get(detail, ("login_code_invalid", detail))
        auth_audit.record_auth_event(
            db,
            event,
            ip_hash_value=_client_ip_hash(request),
            user_agent=_user_agent(request),
            reason=reason,
            correlation_id=correlation_id,
        )
        db.commit()
        raise HTTPException(status_code=400, detail=detail)

    refresh_user_access(user)
    db.add(user)

    if not user.is_active:
        db.commit()
        raise HTTPException(status_code=403, detail="user_inactive")

    auth_audit.record_auth_event(
        db,
        "login_code_verified",
        user_id=user.id,
        email=user.email,
        ip_hash_value=_client_ip_hash(request),
        user_agent=_user_agent(request),
        correlation_id=correlation_id,
    )

    # Session creation shares the transaction that consumed the challenge:
    # exactly one concurrent verification wins and yields one active session.
    return _issue_session(
        db=db,
        response=response,
        user=user,
        channel=payload.channel or channel,
        device_id=device_id,
        device_label=device_label,
        request=request,
        correlation_id=correlation_id,
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
    # Mission 31B: e-mail is NOT editable here — use the verified
    # /auth/email-change flow. Unknown fields are rejected by the schema.
    if payload.display_name is not None:
        current_user.display_name = payload.display_name.strip() or None

    if payload.avatar_url is not None:
        current_user.avatar_url = payload.avatar_url.strip() or None

    if payload.phone is not None:
        current_user.phone = payload.phone.strip() or None

    refresh_user_access(current_user)
    db.add(current_user)
    db.commit()
    db.refresh(current_user)
    return _serialize_access(current_user)


@router.post("/email-change/request", response_model=EmailChangeRequestResponse)
def request_email_change(
    payload: EmailChangeRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    correlation_id = _correlation_id(request)
    new_email = normalize_email(payload.new_email)

    if not new_email or new_email == normalize_email(current_user.email):
        raise HTTPException(status_code=400, detail="email_change_same_email")

    violated = login_code_rate_limit_state(
        db,
        email=new_email,
        request_ip_hash=_client_ip_hash(request),
    )

    if violated:
        auth_audit.record_auth_event(
            db,
            "login_code_rate_limited",
            user_id=current_user.id,
            email=new_email,
            ip_hash_value=_client_ip_hash(request),
            user_agent=_user_agent(request),
            reason=f"email_change_{violated}",
            correlation_id=correlation_id,
        )
        db.commit()
        raise HTTPException(status_code=429, detail=RATE_LIMITED_DETAIL)

    challenge, code = start_login_challenge(
        db,
        current_user,
        channel="web",
        purpose=CHALLENGE_PURPOSE_EMAIL_CHANGE,
        target_email=new_email,
        request_ip_hash=_client_ip_hash(request),
        correlation_id=correlation_id,
    )
    auth_audit.record_auth_event(
        db,
        "email_change_requested",
        user_id=current_user.id,
        email=new_email,
        ip_hash_value=_client_ip_hash(request),
        user_agent=_user_agent(request),
        correlation_id=correlation_id,
    )
    # Feeds the shared send-rate ledger for the target e-mail.
    auth_audit.record_auth_event(
        db,
        "login_code_requested",
        user_id=current_user.id,
        email=new_email,
        ip_hash_value=_client_ip_hash(request),
        user_agent=_user_agent(request),
        status="email_change",
        correlation_id=correlation_id,
    )
    db.commit()

    background_tasks.add_task(
        _deliver_challenge_email,
        challenge.id,
        email=new_email,
        code=code,
        purpose=CHALLENGE_PURPOSE_EMAIL_CHANGE,
        plan=current_user.plan,
        channel="web",
        expires_minutes=challenge_expiry_minutes(challenge),
        correlation_id=correlation_id,
    )

    return EmailChangeRequestResponse(
        detail=GENERIC_EMAIL_CHANGE_DETAIL,
        login_token=challenge.login_token,
        otp_expires_at=challenge.expires_at,
    )


@router.post("/email-change/verify", response_model=UserAccessResponse)
def verify_email_change(
    payload: EmailChangeVerifyRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    token: str | None = Depends(get_request_token),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    correlation_id = _correlation_id(request)

    try:
        challenge = consume_email_change_challenge(
            db,
            login_token=payload.login_token,
            code=payload.code,
            expected_user_id=current_user.id,
        )
    except ValueError as exc:
        detail = str(exc)
        event, reason = OTP_ERROR_AUDIT_EVENTS.get(detail, ("login_code_invalid", detail))
        auth_audit.record_auth_event(
            db,
            event,
            user_id=current_user.id,
            ip_hash_value=_client_ip_hash(request),
            user_agent=_user_agent(request),
            reason=reason or "email_change",
            correlation_id=correlation_id,
        )
        auth_audit.record_auth_event(
            db,
            "email_change_failed",
            user_id=current_user.id,
            ip_hash_value=_client_ip_hash(request),
            user_agent=_user_agent(request),
            reason=detail,
            correlation_id=correlation_id,
        )
        db.commit()
        raise HTTPException(status_code=400, detail=detail)

    target_email = normalize_email(challenge.target_email)

    if not target_email:
        db.commit()
        raise HTTPException(status_code=400, detail="email_change_failed")

    old_email = normalize_email(current_user.email)

    duplicate = (
        db.query(User)
        .filter(User.email == target_email)
        .filter(User.id != current_user.id)
        .first()
    )

    if duplicate is not None:
        auth_audit.record_auth_event(
            db,
            "email_change_failed",
            user_id=current_user.id,
            email=target_email,
            ip_hash_value=_client_ip_hash(request),
            user_agent=_user_agent(request),
            reason="email_taken",
            correlation_id=correlation_id,
        )
        db.commit()
        raise HTTPException(status_code=400, detail="email_change_failed")

    current_session_id = None
    if token:
        try:
            current_session_id = str(decode_access_token_payload(token).get("sid") or "") or None
        except HTTPException:
            current_session_id = None

    current_user.email = target_email
    current_user.updated_at = utcnow()
    db.add(current_user)

    invalidate_open_challenges(db, current_user.id, CHALLENGE_PURPOSE_EMAIL_CHANGE)
    revoke_all_sessions(
        db,
        current_user.id,
        reason="email_changed",
        except_session_id=current_session_id,
    )

    auth_audit.record_auth_event(
        db,
        "email_change_verified",
        user_id=current_user.id,
        email=target_email,
        ip_hash_value=_client_ip_hash(request),
        user_agent=_user_agent(request),
        correlation_id=correlation_id,
    )
    auth_audit.record_auth_event(
        db,
        "email_changed",
        user_id=current_user.id,
        email=target_email,
        ip_hash_value=_client_ip_hash(request),
        user_agent=_user_agent(request),
        correlation_id=correlation_id,
    )

    try:
        db.commit()
    except IntegrityError:
        # Concurrent registration/change won the unique e-mail constraint.
        db.rollback()
        auth_audit.record_auth_event(
            db,
            "email_change_failed",
            user_id=current_user.id,
            email=target_email,
            ip_hash_value=_client_ip_hash(request),
            user_agent=_user_agent(request),
            reason="email_unique_conflict",
            correlation_id=correlation_id,
        )
        db.commit()
        raise HTTPException(status_code=400, detail="email_change_failed")

    if old_email:
        background_tasks.add_task(
            send_email_change_notice_email,
            old_email,
            auth_audit.mask_email(target_email),
        )

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
    if payload.activate:
        _reject_unverified_subscription_activation()

    downgrade_to_free(current_user, reason="premium_inactive")

    log_subscription_event(
        db,
        current_user,
        provider=payload.provider,
        event_type="subscription_sync",
        product_id=payload.product_id,
        origin=payload.origin,
        external_subscription_id=payload.external_subscription_id,
        status=current_user.plan_status,
        payload_excerpt=_subscription_sync_audit_payload(payload, current_user.plan_status),
    )

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
    request: Request,
    response: Response,
    token: str | None = Depends(get_request_token),
    db: Session = Depends(get_db),
):
    """Idempotent logout: revokes the current session when the token is still
    resolvable and always clears the session cookie."""
    correlation_id = _correlation_id(request)

    if token:
        try:
            payload = decode_access_token_payload(token)
            session_id = str(payload.get("sid") or "")
            user_id = int(payload.get("sub"))
        except (HTTPException, TypeError, ValueError):
            session_id = ""
            user_id = None

        if session_id and user_id is not None:
            revoked = revoke_session(
                db=db,
                user_id=user_id,
                session_id=session_id,
                reason="logout",
            )

            if revoked:
                auth_audit.record_auth_event(
                    db,
                    "session_revoked",
                    user_id=user_id,
                    session_id=session_id,
                    reason="logout",
                    ip_hash_value=_client_ip_hash(request),
                    user_agent=_user_agent(request),
                    correlation_id=correlation_id,
                )
                auth_audit.record_auth_event(
                    db,
                    "logout",
                    user_id=user_id,
                    session_id=session_id,
                    ip_hash_value=_client_ip_hash(request),
                    user_agent=_user_agent(request),
                    correlation_id=correlation_id,
                )

            db.commit()

    _clear_session_cookie(response)
    return LogoutResponse(ok=True)


@router.post("/logout-all", response_model=LogoutResponse)
def logout_all(
    request: Request,
    response: Response,
    token: str | None = Depends(get_request_token),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    correlation_id = _correlation_id(request)
    session_id = None

    if token:
        try:
            session_id = str(decode_access_token_payload(token).get("sid") or "") or None
        except HTTPException:
            session_id = None

    revoked = revoke_all_sessions(db, current_user.id, reason="logout_all")

    auth_audit.record_auth_event(
        db,
        "logout_all",
        user_id=current_user.id,
        session_id=session_id,
        ip_hash_value=_client_ip_hash(request),
        user_agent=_user_agent(request),
        status=str(revoked),
        correlation_id=correlation_id,
    )
    db.commit()

    _clear_session_cookie(response)
    return LogoutResponse(ok=True, revoked_sessions=revoked)
