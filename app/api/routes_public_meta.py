from fastapi import APIRouter

from app.services.help_center_service import get_help_center_blueprint
from app.services.legal_service import (
    AI_MODULES,
    DISCLOSURE_TEXT,
    EDUCATION_DESCRIPTION,
    GOOGLE_PLAY_DESCRIPTION,
    HELP_CENTER_MODULES,
    LEGAL_NOTICE_TEXT,
    LAUNCH_ROADMAP,
    OFFICIAL_CHANNELS,
    PRICING,
    SOCIAL_FEATURES,
    SUBSCRIPTION_TERMS_TEXT,
    WEEKLY_AI_POLLS,
    get_public_bootstrap,
)
from app.services.video_library_service import get_help_video_library

router = APIRouter(prefix="/public", tags=["Public"])


@router.get("/bootstrap")
def bootstrap():
    return get_public_bootstrap()


@router.get("/legal-notice")
def legal_notice():
    return {"legal_notice": LEGAL_NOTICE_TEXT}


@router.get("/google-play-description")
def google_play_description():
    return {
        "description": GOOGLE_PLAY_DESCRIPTION,
        "education": EDUCATION_DESCRIPTION,
    }


@router.get("/subscription-terms")
def subscription_terms():
    return {"terms": SUBSCRIPTION_TERMS_TEXT}


@router.get("/pricing")
def pricing():
    return {"pricing": PRICING}


@router.get("/disclosure")
def disclosure():
    return {"disclosure": DISCLOSURE_TEXT}


@router.get("/help-center")
def help_center():
    blueprint = get_help_center_blueprint()

    return {
        "launch_roadmap": LAUNCH_ROADMAP,
        "ai_modules": AI_MODULES,
        "help_center_modules": blueprint["guides"] or HELP_CENTER_MODULES,
        "video_status": blueprint["video_status"],
        "social_features": SOCIAL_FEATURES,
        "weekly_ai_polls": WEEKLY_AI_POLLS,
        "official_channels": OFFICIAL_CHANNELS,
    }


@router.get("/help-videos")
def help_videos():
    return get_help_video_library()
