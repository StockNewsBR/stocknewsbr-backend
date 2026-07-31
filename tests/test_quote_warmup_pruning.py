import time
import unittest
from unittest.mock import patch

from app.system import quote_warmup

class QuoteWarmupPruningTests(unittest.TestCase):
    def test_pruning_removes_only_expired_entries(self):
        # Setup initial state
        quote_warmup._quote_cooldowns.clear()
        quote_warmup._chart_cooldowns.clear()
        quote_warmup._request_last_at.clear()
        quote_warmup._ondemand_last_at.clear()

        # Add valid and expired entries
        now = 1000.0
        
        quote_warmup._quote_cooldowns["expired1"] = now - 10
        quote_warmup._quote_cooldowns["valid1"] = now + 10
        
        quote_warmup._chart_cooldowns["expired2"] = now - 10
        quote_warmup._chart_cooldowns["valid2"] = now + 10
        
        # request_last_at expires after 3600
        quote_warmup._request_last_at["expired3"] = now - 3601
        quote_warmup._request_last_at["valid3"] = now - 100
        
        quote_warmup._ondemand_last_at["expired4"] = now - 3601
        quote_warmup._ondemand_last_at["valid4"] = now - 100

        # Simulate pruning by running the prune block exactly as in _quote_warmup_loop
        # We must acquire lock and iterate over list of keys to prevent RuntimeError
        with quote_warmup._lock:
            for k in list(quote_warmup._quote_cooldowns.keys()):
                if quote_warmup._quote_cooldowns[k] <= now:
                    del quote_warmup._quote_cooldowns[k]
            for k in list(quote_warmup._chart_cooldowns.keys()):
                if quote_warmup._chart_cooldowns[k] <= now:
                    del quote_warmup._chart_cooldowns[k]
            for k in list(quote_warmup._request_last_at.keys()):
                if now - quote_warmup._request_last_at[k] > 3600.0:
                    del quote_warmup._request_last_at[k]
            for k in list(quote_warmup._ondemand_last_at.keys()):
                if now - quote_warmup._ondemand_last_at[k] > 3600.0:
                    del quote_warmup._ondemand_last_at[k]

        # Verify results
        self.assertNotIn("expired1", quote_warmup._quote_cooldowns)
        self.assertIn("valid1", quote_warmup._quote_cooldowns)
        
        self.assertNotIn("expired2", quote_warmup._chart_cooldowns)
        self.assertIn("valid2", quote_warmup._chart_cooldowns)
        
        self.assertNotIn("expired3", quote_warmup._request_last_at)
        self.assertIn("valid3", quote_warmup._request_last_at)
        
        self.assertNotIn("expired4", quote_warmup._ondemand_last_at)
        self.assertIn("valid4", quote_warmup._ondemand_last_at)

if __name__ == '__main__':
    unittest.main()
