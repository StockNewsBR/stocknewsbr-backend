import os

def pytest_configure(config):
    """
    Set dummy environment variables needed for tests.
    This prevents test collection failures and errors during local execution.
    """
    os.environ["SECRET_KEY"] = "test_secure_secret_key_1234567890"
