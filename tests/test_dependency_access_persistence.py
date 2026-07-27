from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from app.dependencies import (
    _should_update_last_access,
    require_active_plan,
    require_any_channel_access,
    require_channel_access,
)
from app.models import User
from app.services.access_service import utcnow


def _make_mock_user(
    *,
    user_id: int = 1,
    is_active: bool = True,
    plan: str = "premium",
    plan_status: str = "active",
    access_app: bool = True,
    access_web: bool = True,
    access_telegram: bool = True,
    last_access_at: datetime | None = None,
    trial_expires_at: datetime | None = None,
    plan_expires_at: datetime | None = None,
) -> User:
    user = User()
    user.id = user_id
    user.is_active = is_active
    user.plan = plan
    user.plan_status = plan_status
    user.access_app = access_app
    user.access_web = access_web
    user.access_telegram = access_telegram
    user.last_access_at = last_access_at
    user.trial_expires_at = trial_expires_at
    user.plan_expires_at = plan_expires_at
    return user


def _make_mock_db() -> MagicMock:
    db = MagicMock()
    db.add = MagicMock()
    db.commit = MagicMock()
    db.refresh = MagicMock()
    return db


def test_first_request_populates_last_access_and_commits():
    """Teste 1 — Primeira requisição com last_access_at=None preenche atividade e executa 1 commit."""
    user = _make_mock_user(last_access_at=None)
    db = _make_mock_db()

    result = require_active_plan(current_user=user, db=db)

    assert result is user
    assert user.last_access_at is not None
    db.add.assert_called_once_with(user)
    db.commit.assert_called_once()
    db.refresh.assert_called_once_with(user)


def test_consecutive_requests_within_throttle_do_not_commit():
    """Teste 2 — Requisições consecutivas dentro de 5min sem alteração de plano NÃO chamam db.commit."""
    now = utcnow()
    initial_last_access = now - timedelta(minutes=1)  # 1 minute ago (within 5 min)
    user = _make_mock_user(last_access_at=initial_last_access)
    db = _make_mock_db()

    result = require_active_plan(current_user=user, db=db)

    assert result is user
    assert user.last_access_at == initial_last_access
    db.add.assert_not_called()
    db.commit.assert_not_called()
    db.refresh.assert_not_called()


def test_expired_throttle_updates_last_access_and_commits():
    """Teste 3 — Requisição após 6min (> 5min) atualiza atividade e executa 1 commit."""
    now = utcnow()
    old_last_access = now - timedelta(minutes=6)
    user = _make_mock_user(last_access_at=old_last_access)
    db = _make_mock_db()

    result = require_active_plan(current_user=user, db=db)

    assert result is user
    assert user.last_access_at > old_last_access
    db.add.assert_called_once_with(user)
    db.commit.assert_called_once()
    db.refresh.assert_called_once_with(user)


def test_real_access_change_persists_immediately_before_403():
    """Teste 4 — Expiração de trial rebaixa acesso, faz 1 commit e lança HTTPException 403."""
    now = utcnow()
    recent_last_access = now - timedelta(minutes=1)
    past_trial_expiry = now - timedelta(hours=1)

    user = _make_mock_user(
        plan="trial",
        plan_status="trialing",
        access_app=True,
        access_web=True,
        access_telegram=True,
        last_access_at=recent_last_access,
        trial_expires_at=past_trial_expiry,
    )
    db = _make_mock_db()

    web_dep = require_channel_access("web")
    with pytest.raises(HTTPException) as exc_info:
        web_dep(current_user=user, db=db)

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == "web_access_required"
    assert user.plan == "free"
    assert user.access_web is False
    assert user.access_telegram is False

    # Verifies the plan change was committed to DB before raising 403
    db.commit.assert_called_once()


def test_inactive_user_remains_blocked():
    """Teste 5 — Usuário inativo permanece bloqueado com HTTPException 403 detail=user_inactive."""
    user = _make_mock_user(is_active=False, last_access_at=utcnow() - timedelta(minutes=1))
    db = _make_mock_db()

    with pytest.raises(HTTPException) as exc_info:
        require_active_plan(current_user=user, db=db)

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == "user_inactive"


def test_channel_access_enforcement():
    """Teste 6 — Validação de canais: require_channel_access e require_any_channel_access."""
    recent = utcnow() - timedelta(minutes=1)

    # Web allowed user
    web_user = _make_mock_user(plan="premium", access_web=True, access_app=True, last_access_at=recent)
    db = _make_mock_db()
    web_dep = require_channel_access("web")
    assert web_dep(current_user=web_user, db=db) is web_user
    db.commit.assert_not_called()

    # Free user without web access
    free_user = _make_mock_user(plan="free", plan_status="active", access_app=True, access_web=False, access_telegram=False, last_access_at=recent)
    db_free = _make_mock_db()
    with pytest.raises(HTTPException) as exc_info:
        web_dep(current_user=free_user, db=db_free)

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == "web_access_required"

    # require_any_channel_access test
    any_dep = require_any_channel_access("web", "app")
    db_any = _make_mock_db()
    assert any_dep(current_user=free_user, db=db_any) is free_user  # free_user has access_app=True


def test_max_one_commit_per_dependency_call():
    """Teste 7 — Garantir commit_count <= 1 em qualquer caminho de execução."""
    now = utcnow()
    user_expired_throttle = _make_mock_user(last_access_at=now - timedelta(minutes=10))
    db = _make_mock_db()

    require_active_plan(current_user=user_expired_throttle, db=db)

    assert db.commit.call_count == 1


def test_throttle_boundary_limits():
    """Teste 8 — Limites exatos do throttle: 4m59s (False), 5m00s (True), 6m00s (True)."""
    now = utcnow()
    user_4m59s = _make_mock_user(last_access_at=now - timedelta(minutes=4, seconds=59))
    user_5m00s = _make_mock_user(last_access_at=now - timedelta(minutes=5))
    user_6m00s = _make_mock_user(last_access_at=now - timedelta(minutes=6))

    assert _should_update_last_access(user_4m59s, now) is False
    assert _should_update_last_access(user_5m00s, now) is True
    assert _should_update_last_access(user_6m00s, now) is True

def test_db_commit_failure_triggers_rollback():
    """Teste 9 — Falha no db.commit() aciona db.rollback() exatamente uma vez e propaga exceção."""
    now = utcnow()
    user = _make_mock_user(last_access_at=now - timedelta(minutes=10))
    db = _make_mock_db()
    db.commit.side_effect = Exception("DB timeout")
    db.rollback = MagicMock()

    with pytest.raises(Exception, match="DB timeout"):
        require_active_plan(current_user=user, db=db)

    db.commit.assert_called_once()
    db.rollback.assert_called_once()
    db.refresh.assert_not_called()


from app.dependencies import resolve_premium_entitlement  # noqa: E402
from unittest.mock import patch  # noqa: E402

def test_resolve_premium_entitlement_token_none():
    db = _make_mock_db()
    assert resolve_premium_entitlement(token=None, db=db) is False

@patch("app.dependencies.resolve_token_user")
def test_resolve_premium_entitlement_http_401(mock_resolve):
    mock_resolve.side_effect = HTTPException(status_code=401, detail="invalid_token")
    db = _make_mock_db()
    assert resolve_premium_entitlement(token="bad_token", db=db) is False

@patch("app.dependencies.resolve_token_user")
def test_resolve_premium_entitlement_http_500(mock_resolve):
    mock_resolve.side_effect = HTTPException(status_code=500, detail="auth_service_down")
    db = _make_mock_db()
    with pytest.raises(HTTPException) as exc_info:
        resolve_premium_entitlement(token="some_token", db=db)
    assert exc_info.value.status_code == 500

@patch("app.dependencies.resolve_token_user")
def test_resolve_premium_entitlement_db_error(mock_resolve):
    mock_resolve.side_effect = Exception("OperationalError")
    db = _make_mock_db()
    with pytest.raises(Exception, match="OperationalError"):
        resolve_premium_entitlement(token="some_token", db=db)

@patch("app.dependencies.resolve_token_user")
def test_resolve_premium_entitlement_valid_premium(mock_resolve):
    user = _make_mock_user(plan="premium")
    mock_resolve.return_value = user
    db = _make_mock_db()
    assert resolve_premium_entitlement(token="good_token", db=db) is True
