import os
import sys
import time
import unittest
from unittest.mock import MagicMock, patch


ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class TestThreading(unittest.TestCase):
    @patch.dict(
        sys.modules,
        {
            "bson": MagicMock(ObjectId=MagicMock(return_value="dummy_id")),
            "playwright": MagicMock(),
            "playwright.sync_api": MagicMock(),
            "pymongo": MagicMock(),
            "redis": MagicMock(),
            "rq": MagicMock(),
        },
        clear=False,
    )
    @patch("app.projects.lead_gen.jobs.scraping.maps.sync_playwright")
    @patch("app.projects.lead_gen.jobs.scraping.maps.jobs_model")
    @patch("app.projects.lead_gen.jobs.scraping.maps.leads_model")
    @patch("app.projects.lead_gen.jobs.scraping.maps.get_collection")
    def test_concurrency_speed(self, mock_get_collection, mock_leads, mock_jobs, mock_playwright):
        if ROOT_DIR not in sys.path:
            sys.path.insert(0, ROOT_DIR)

        from app.projects.lead_gen.jobs.scraping.concurrency import LeadProcessor
        from app.projects.lead_gen.jobs.scraping.maps import MapsScraper

        mock_job = {
            "_id": "dummy_id",
            "user_id": "dummy_user",
            "query_text": "test",
            "leads_requested": 5,
            "leads_delivered": 0,
        }
        mock_jobs.find_by_id.return_value = mock_job
        mock_get_collection.return_value.find_one.return_value = None

        with patch("app.projects.lead_gen.jobs.scraping.maps.EmailExtractor") as mock_email_extractor:
            mock_extractor = mock_email_extractor.return_value

            def slow_extract(url):
                time.sleep(0.5)
                return "test@example.com"

            mock_extractor.extract.side_effect = slow_extract

            scraper = MapsScraper("dummy_id")
            processor = LeadProcessor(use_threads=True, max_threads=5)

            start_time = time.time()
            num_tasks = 5
            for index in range(num_tasks):
                data = {
                    "name": f"Test {index}",
                    "phone": f"123456789{index}",
                    "website": f"http://example{index}.com",
                    "address": "123 St",
                    "google_url": "http://maps.google.com",
                }
                processor.submit_lead(data, scraper.process_lead_background)

            processor.shutdown()
            duration = time.time() - start_time

            self.assertLess(duration, 1.5, "Threading is not working effectively")
            self.assertEqual(mock_leads.create.call_count, num_tasks)


if __name__ == "__main__":
    unittest.main()
