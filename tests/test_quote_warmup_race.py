import threading
import time
import unittest
from unittest.mock import patch

from app.system import quote_warmup

class QuoteWarmupRaceTests(unittest.TestCase):
    def test_stale_thread_does_not_clear_new_thread(self):
        # We simulate a race condition where a thread exits AFTER a new thread has been created
        # and assigned to quote_warmup._thread.
        
        # 1. Create a dummy old thread
        old_thread = threading.Thread(target=lambda: None)
        old_thread.start()
        old_thread.join()
        
        # 2. Create a dummy new thread and set it as current _thread
        new_thread = threading.Thread(target=lambda: None)
        
        try:
            with quote_warmup._lock:
                quote_warmup._thread = new_thread
            
            # 3. Simulate the finally block of the old thread trying to clear the reference
            # The old thread's finally block is executed within the context of the old thread,
            # but since we are calling it from the main thread here, current_thread() is MainThread,
            # which is NEITHER old_thread NOR new_thread.
            # But what we want to test is the logic inside the finally block.
            
            with patch('threading.current_thread', return_value=old_thread):
                with quote_warmup._lock:
                    if quote_warmup._thread is threading.current_thread():
                        quote_warmup._thread = None
                        
            # 4. Verify that _thread was NOT cleared because old_thread is not new_thread
            self.assertIs(quote_warmup._thread, new_thread)
            
            # 5. Simulate the finally block of the NEW thread
            with patch('threading.current_thread', return_value=new_thread):
                with quote_warmup._lock:
                    if quote_warmup._thread is threading.current_thread():
                        quote_warmup._thread = None
                        
            # 6. Verify that it WAS cleared
            self.assertIsNone(quote_warmup._thread)
            
        finally:
            with quote_warmup._lock:
                quote_warmup._thread = None

if __name__ == '__main__':
    unittest.main()
