from fastapi import APIRouter
from app.ai.radar_crypto import scan_crypto_market

router = APIRouter()


@router.get("/crypto/radar")
def crypto_radar():

    return scan_crypto_market()