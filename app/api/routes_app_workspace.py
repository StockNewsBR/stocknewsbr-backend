from fastapi import APIRouter, Depends

from app.dependencies import require_channel_access
from app.models import User
from app.services.workspace_service import get_workspace_data


router = APIRouter(prefix="/app", tags=["app"])


@router.get("/workspace/data")
def app_workspace_data(current_user: User = Depends(require_channel_access("app"))):
    return get_workspace_data(user_id=current_user.id, channel="app")
