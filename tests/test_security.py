import os
import unittest
import importlib

class SecuritySettingsTests(unittest.TestCase):
    def setUp(self):
        # Save the current environment to restore after tests
        self.original_env = dict(os.environ)

    def tearDown(self):
        # Restore environment
        os.environ.clear()
        os.environ.update(self.original_env)

        # Ensure we always end with a valid app.security module for subsequent tests
        import app.security
        importlib.reload(app.security)

    def test_security_raises_value_error_on_missing_secret(self):
        # Remove SECRET_KEY from environment
        if "SECRET_KEY" in os.environ:
            del os.environ["SECRET_KEY"]

        import app.security
        with self.assertRaisesRegex(ValueError, "SECRET_KEY environment variable is not set"):
            importlib.reload(app.security)

    def test_security_raises_value_error_on_weak_default_secret(self):
        # Set SECRET_KEY to the weak default
        os.environ["SECRET_KEY"] = "CHANGE_THIS_SECRET"

        import app.security
        with self.assertRaisesRegex(ValueError, "SECRET_KEY environment variable is not set"):
            importlib.reload(app.security)

    def test_security_loads_with_valid_secret(self):
        # Set SECRET_KEY to a strong valid key
        os.environ["SECRET_KEY"] = "this_is_a_strong_and_valid_secret_key"

        # This should not raise an exception
        import app.security
        importlib.reload(app.security)

        self.assertEqual(app.security.SECRET_KEY, "this_is_a_strong_and_valid_secret_key")

if __name__ == "__main__":
    unittest.main()
