from datetime import datetime

def check_user_plan(user):
    if not user.is_active:
        return False, "Usuário inativo"

    # Verificação de trial
    if user.plan == "trial":
        if user.trial_expires_at and datetime.utcnow() > user.trial_expires_at:
            user.plan = "expired"
            return False, "Trial expirado"

    if user.plan == "expired":
        return False, "Plano expirado"

    return True, "Acesso liberado"