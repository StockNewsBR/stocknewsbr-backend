# ==========================================================
# STOCKNEWSBR SCHEMAS
# ==========================================================

from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class UserBase(BaseModel):
    email: EmailStr


class UserRegister(UserBase):
    password: str = Field(..., min_length=6, max_length=128)
    display_name: str | None = Field(default=None, max_length=120)
    phone: str | None = Field(default=None, max_length=32)
    referral_code: str | None = Field(default=None, max_length=32)
    channel: str | None = Field(default="app", max_length=32)
    device_id: str | None = Field(default=None, max_length=120)
    device_label: str | None = Field(default=None, max_length=120)
    accepted_terms: bool = True
    accepted_privacy: bool = True
    accepted_risk_notice: bool = True


class UserLogin(UserBase):
    password: str
    channel: str | None = Field(default="web", max_length=32)
    device_id: str | None = Field(default=None, max_length=120)
    device_label: str | None = Field(default=None, max_length=120)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class TokenData(BaseModel):
    user_id: int | None = None


class AccessMatrix(BaseModel):
    app: bool
    web: bool
    telegram: bool


class UserAccessResponse(BaseModel):
    id: int
    email: EmailStr
    display_name: str | None = None
    phone: str | None = None
    avatar_url: str | None = None
    plan: str
    plan_status: str
    subscription_provider: str | None = None
    subscription_origin: str | None = None
    subscription_product_id: str | None = None
    trial_expires_at: datetime | None = None
    plan_expires_at: datetime | None = None
    telegram_linked: bool
    telegram_username: str | None = None
    referral_code: str | None = None
    legal_notice_version: str | None = None
    accepted_terms_at: datetime | None = None
    accepted_privacy_at: datetime | None = None
    accepted_risk_notice_at: datetime | None = None
    session_policy: str | None = None
    otp_required_on_login: bool = False
    access: AccessMatrix


class SubscriptionSyncRequest(BaseModel):
    provider: str = "google_play"
    product_id: str
    origin: str = "android_app"
    external_subscription_id: str | None = None
    purchase_token: str | None = None
    started_at: datetime | None = None
    renewal_at: datetime | None = None
    activate: bool = True


class TelegramLinkRequest(BaseModel):
    telegram_id: str = Field(..., min_length=3, max_length=64)
    telegram_username: str | None = Field(default=None, max_length=64)


class TelegramLinkSessionRequest(BaseModel):
    origin_channel: str = Field(default="app", max_length=32)


class TelegramLinkSessionResponse(BaseModel):
    link_code: str
    deep_link: str | None = None
    bot_username: str | None = None
    expires_at: datetime
    status: str = "pending"


class LegalAcceptanceRequest(BaseModel):
    accepted_terms: bool = True
    accepted_privacy: bool = True
    accepted_risk_notice: bool = True


class LoginOtpVerifyRequest(BaseModel):
    login_token: str = Field(..., min_length=8, max_length=128)
    code: str = Field(..., min_length=4, max_length=12)


class AuthFlowResponse(BaseModel):
    access_token: str | None = None
    token_type: str = "bearer"
    otp_required: bool = False
    login_token: str | None = None
    otp_expires_at: datetime | None = None
    debug_otp_code: str | None = None
    session_policy: str | None = None
    channel: str | None = None
    detail: str | None = None


class UserProfileUpdateRequest(BaseModel):
    display_name: str | None = Field(default=None, max_length=120)
    email: EmailStr | None = None
    avatar_url: str | None = Field(default=None, max_length=2048)


class LogoutResponse(BaseModel):
    ok: bool = True
