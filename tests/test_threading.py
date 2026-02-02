import unittest
from unittest.mock import MagicMock, patch
import time
import sys
import os
import sys
import os
from unittest.mock import MagicMock

# Create mocks for external dependencies
mock_bson = MagicMock()
mock_bson.ObjectId = MagicMock(return_value="dummy_id")
sys.modules['bson'] = mock_bson

mock_playwright = MagicMock()
sys.modules['playwright'] = mock_playwright
sys.modules['playwright.sync_api'] = mock_playwright

sys.modules['pymongo'] = MagicMock()
sys.modules['redis'] = MagicMock()
sys.modules['flask'] = MagicMock()
sys.modules['rq'] = MagicMock()

# Add root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.lead_gen.jobs.scraping.maps import MapsScraper
from app.lead_gen.jobs.scraping.concurrency import LeadProcessor

class TestThreading(unittest.TestCase):
    @patch('app.lead_gen.jobs.scraping.maps.sync_playwright')
    @patch('app.lead_gen.jobs.scraping.maps.jobs_model')
    @patch('app.lead_gen.jobs.scraping.maps.leads_model')
    def test_concurrency_speed(self, mock_leads, mock_jobs, mock_playwright):
        # Setup mocks
        mock_job = {
            '_id': 'dummy_id',
            'user_id': 'dummy_user',
            'query_text': 'test',
            'leads_requested': 5,
            'leads_delivered': 0
        }
        mock_jobs.find_by_id.return_value = mock_job
        
        # Mock EmailExtractor to be slow
        with patch('app.lead_gen.jobs.scraping.maps.EmailExtractor') as MockEmailExtractor:
            mock_extractor = MockEmailExtractor.return_value
            
            def slow_extract(url):
                time.sleep(0.5) # Simulate 0.5s network delay
                return "test@example.com"
            
            mock_extractor.extract.side_effect = slow_extract
            
            # Initialize scraper
            scraper = MapsScraper('dummy_id')
            
            # Manually invoke process_lead_background multiple times concurrently
            # We are verifying LeadProcessor works as expected, using the Scraper's method
            
            start_time = time.time()
            
            # Create a processor just for this test to control it directly
            # The scraper initializes one internally in run(), but we want to unit test the throughput
            # using the scraper's worker method.
            
            processor = LeadProcessor(use_threads=True, max_threads=5)
            
            data = {
                'name': 'Test',
                'phone': '1234567890', 
                'website': 'http://example.com',
                'address': '123 St',
                'google_url': 'http://maps.google.com'
            }
            
            # Submit 5 tasks
            num_tasks = 5
            for _ in range(num_tasks):
                processor.submit_lead(data, scraper.process_lead_background)
                
            processor.shutdown()
            
            end_time = time.time()
            duration = end_time - start_time
            
            print(f"Processed {num_tasks} tasks in {duration:.2f} seconds")
            
            # With 5 threads, 5 tasks of 0.5s should take approx 0.5s (plus overhead), not 2.5s
            self.assertLess(duration, 1.5, "Threading is not working effectively")
            self.assertEqual(mock_leads.create.call_count, num_tasks)

if __name__ == '__main__':
    unittest.main()
