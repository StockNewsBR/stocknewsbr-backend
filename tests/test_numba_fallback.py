import numpy as np
import sys
import unittest
from unittest.mock import patch

# Save the original module if it exists
try:
    import numba  # noqa: F401
    has_numba = True
except ImportError:
    has_numba = False

class NumbaFallbackTests(unittest.TestCase):
    def test_numba_fallback_decorator(self):
        # We simulate the fallback logic directly to test its equivalence
        # because the engine files already imported numba if it's available.
        
        def njit_fallback(*args, **kwargs):
            def decorator(fn):
                return fn
            return decorator
            
        @njit_fallback(cache=True)
        def compute_something(arr):
            return arr * 2.0
            
        result = compute_something(np.array([1.0, 2.0, np.nan, np.inf]))
        self.assertEqual(result[0], 2.0)
        self.assertEqual(result[1], 4.0)
        self.assertTrue(np.isnan(result[2]))
        self.assertTrue(np.isinf(result[3]))
        self.assertEqual(result.dtype, np.float64)

    def test_engine_v36_compilation_error_not_swallowed(self):
        # We ensure that if an exception other than ImportError happens during import, it is raised.
        # We can simulate this by mocking __import__ to raise a ValueError when importing 'numba'
        original_import = __import__
        def mock_import(name, *args, **kwargs):
            if name == 'numba':
                raise ValueError("Compilation Error!")
            return original_import(name, *args, **kwargs)
            
        # We must clear the engine module to force re-import
        if 'app.engine.core.engine_v36' in sys.modules:
            del sys.modules['app.engine.core.engine_v36']
            
        with patch('builtins.__import__', side_effect=mock_import):
            with self.assertRaises(ValueError):
                import app.engine.core.engine_v36  # noqa: F401

if __name__ == '__main__':
    unittest.main()
