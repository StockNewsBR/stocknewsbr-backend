# =====================================================
# PLAN SERVICE
# Fast + Crash Safe
# =====================================================

import logging
from typing import Tuple

from app.services.access_service import has_channel_access, refresh_user_access

logger = logging.getLogger("stocknewsbr.plan_service")


def check_user_plan(user) -> Tuple[bool, str]:
    try:
        if user is None:
            return False, "Usuario invalido"

        refresh_user_access(user)

        if not getattr(user, "is_active", False):
            return False, "Usuario inativo"

        if not has_channel_access(user):
            return False, "Assinatura inativa"

        return True, "Acesso liberado"

    except Exception as exc:
        logger.error("Plan check error: %s", exc)
        return False, "Erro ao verificar plano"
