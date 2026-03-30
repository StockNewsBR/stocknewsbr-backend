import unittest
from datetime import datetime, timedelta, timezone

try:
    from app.services.promo_codes import redeem_promo_code
    from app.models import PromoCode, PromoRedemption
    IMPORT_ERROR = None
except ModuleNotFoundError as exc:
    IMPORT_ERROR = exc


class DummyPromo:
    def __init__(self, code="FREE30", free_year=False, free_months=1):
        self.id = 1
        self.code = code
        self.free_year = free_year
        self.free_months = free_months
        self.max_uses = 10
        self.current_uses = 0
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        self.starts_at = now - timedelta(days=1)
        self.expires_at = now + timedelta(days=1)


class FakeQuery:
    def __init__(self, result):
        self.result = result

    def filter(self, *_args, **_kwargs):
        return self

    def with_for_update(self):
        return self

    def first(self):
        return self.result


class FakeSession:
    def __init__(self, promo, existing_redemption=None):
        self.promo = promo
        self.existing_redemption = existing_redemption
        self.added = []
        self.committed = False
        self.rolled_back = False

    def query(self, model, *_args, **_kwargs):
        if model is PromoCode:
            return FakeQuery(self.promo)

        if model is PromoRedemption:
            return FakeQuery(self.existing_redemption)

        return FakeQuery(None)

    def add(self, item):
        self.added.append(item)

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True


@unittest.skipIf(IMPORT_ERROR is not None, f"runtime dependency unavailable: {IMPORT_ERROR}")
class PromoCodeTests(unittest.TestCase):
    def test_redeem_promo_code_increments_usage_and_returns_months(self):
        promo = DummyPromo()
        session = FakeSession(promo)

        result = redeem_promo_code(session, user_id=123, code="free30")

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["code"], "FREE30")
        self.assertEqual(result["free_months"], 1)
        self.assertEqual(promo.current_uses, 1)
        self.assertTrue(session.committed)
        self.assertEqual(len(session.added), 1)

    def test_redeem_promo_code_blocks_duplicate_user_redemption(self):
        promo = DummyPromo()
        session = FakeSession(promo, existing_redemption=object())

        result = redeem_promo_code(session, user_id=123, code="free30")

        self.assertEqual(result["error"], "Promo code already redeemed")
        self.assertEqual(promo.current_uses, 0)
        self.assertFalse(session.committed)


if __name__ == "__main__":
    unittest.main()
