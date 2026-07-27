import unittest
from app.Frontend.trader_terminal import get_terminal
import json

class TestTraderTerminal(unittest.TestCase):
    def test_get_terminal_returns_html(self):
        html = get_terminal(focused_tab="grafico", token="12345")
        self.assertIn("<!DOCTYPE html>", html)
        self.assertIn('const FOCUSED_TAB = "grafico";', html)
        self.assertIn('const AUTH_TOKEN = "12345";', html)
        self.assertIn('const FALLBACK_TABS =', html)

if __name__ == "__main__":
    unittest.main()
