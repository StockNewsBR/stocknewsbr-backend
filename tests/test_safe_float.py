import math
import unittest
from app.ai.feature_hub import safe_float as feature_safe_float
from app.ai.ai_common import safe_float as common_safe_float
from app.services.snapshot_contract import safe_float as snapshot_safe_float


class SafeFloatTests(unittest.TestCase):
    def test_all_implementations_against_twelve_cases(self):
        functions = [feature_safe_float, common_safe_float, snapshot_safe_float]
        for fn in functions:
            with self.subTest(fn=fn.__module__):
                # 1. NaN retorna default
                self.assertEqual(fn(float("nan")), 0.0)
                # 2. +inf retorna default
                self.assertEqual(fn(float("inf")), 0.0)
                # 3. -inf retorna default
                self.assertEqual(fn(float("-inf")), 0.0)
                # 4. "nan" retorna default
                self.assertEqual(fn("nan"), 0.0)
                # 5. "inf" retorna default
                self.assertEqual(fn("inf"), 0.0)
                # 6. None retorna default
                self.assertEqual(fn(None), 0.0)
                # 7. string inválida retorna default
                self.assertEqual(fn("invalid_string"), 0.0)
                # 8. zero permanece zero
                self.assertEqual(fn(0), 0.0)
                self.assertEqual(fn(0.0), 0.0)
                # 9. número negativo permanece válido
                self.assertEqual(fn(-42.5), -42.5)
                # 10. número positivo permanece válido
                self.assertEqual(fn(100.25), 100.25)
                # 11. default=None permanece None
                self.assertIsNone(fn(float("nan"), default=None))
                self.assertIsNone(fn(float("inf"), default=None))
                self.assertIsNone(fn(None, default=None))
                # 12. default numérico é preservado
                self.assertEqual(fn("bad", default=55.0), 55.0)
                self.assertEqual(fn(float("inf"), default=-1.0), -1.0)


if __name__ == "__main__":
    unittest.main()
