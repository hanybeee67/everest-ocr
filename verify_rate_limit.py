
import unittest
import time
from app import create_app

class TestRateLimiting(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.app.config['TESTING'] = True
        # Enable rate limit even in testing (usually disabled by default in Flask-Limiter testing)
        self.app.config['RATELIMIT_ENABLED'] = True 
        self.app.config['RATELIMIT_STORAGE_URL'] = "memory://"
        self.client = self.app.test_client()

    def test_check_limit(self):
        """Test /check limit (5 per minute)"""
        # Make 5 allowed requests
        for i in range(5):
            rv = self.client.post('/check', data={'phone': '01012345678'})
            # It might return logic error (no DB etc) but shouldn't be 429
            self.assertNotEqual(rv.status_code, 429, f"Request {i+1} blocked unexpectedly")
        
        # Make the 6th request - should be blocked
        rv = self.client.post('/check', data={'phone': '01012345678'})
        self.assertEqual(rv.status_code, 429, "6th request should be rate limited")

if __name__ == '__main__':
    unittest.main()
