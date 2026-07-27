import unittest

from app.security import hash_password, verify_password


class SecurityTests(unittest.TestCase):
    def test_hash_password_returns_string(self):
        password = "my_secure_password"
        hashed = hash_password(password)
        self.assertIsInstance(hashed, str)

    def test_hash_password_differs_from_plain(self):
        password = "my_secure_password"
        hashed = hash_password(password)
        self.assertNotEqual(hashed, password)

    def test_hash_password_can_be_verified(self):
        password = "my_secure_password"
        hashed = hash_password(password)
        self.assertTrue(verify_password(password, hashed))

    def test_hash_password_different_inputs_different_hashes(self):
        hash1 = hash_password("password123")
        hash2 = hash_password("password456")
        self.assertNotEqual(hash1, hash2)

    def test_verify_password_fails_for_wrong_password(self):
        password = "my_secure_password"
        hashed = hash_password(password)
        self.assertFalse(verify_password("wrong_password", hashed))

if __name__ == "__main__":
    unittest.main()
