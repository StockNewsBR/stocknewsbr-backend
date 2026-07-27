import unittest
from unittest.mock import MagicMock

from fastapi import HTTPException

from app.auth import register
from app.schemas import UserRegister
from app.models import User

class AuthRouteTests(unittest.TestCase):
    def test_register_existing_email_returns_400(self):
        # Create a mocked database session
        mock_db = MagicMock()

        # Setup the mock query to return an existing user
        mock_query = mock_db.query.return_value
        mock_filter = mock_query.filter.return_value
        mock_filter.first.return_value = User(email="test@example.com")

        # Prepare the user data input
        user_data = UserRegister(
            email="test@example.com",
            password="password123",
            display_name="Test User",
            accepted_terms=True,
            accepted_privacy=True,
            accepted_risk_notice=True
        )

        # Call the register function and expect an HTTPException
        with self.assertRaises(HTTPException) as context:
            register(user_data, db=mock_db)

        # Verify that it is a 400 error and the detail matches
        self.assertEqual(context.exception.status_code, 400)
        self.assertEqual(context.exception.detail, "email_already_registered")

        # Ensure that the database was queried correctly
        mock_db.query.assert_called_once_with(User)

if __name__ == "__main__":
    unittest.main()
