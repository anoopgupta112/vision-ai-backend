import unittest
from datetime import datetime

from app.auth import models as auth_models
from app.lead_gen.jobs import model as jobs_model
from app.lead_gen.saved_searches import model as saved_searches_model


class DomainModelTestCase(unittest.TestCase):
    def test_create_user_doc_sets_expected_defaults(self):
        doc = auth_models.create_user_doc(
            "person@example.com",
            "hashed-password",
            phone="1234567890",
        )

        self.assertEqual(doc["email"], "person@example.com")
        self.assertEqual(doc["password_hash"], "hashed-password")
        self.assertEqual(doc["phone"], "1234567890")
        self.assertFalse(doc["email_verified"])
        self.assertFalse(doc["phone_verified"])
        self.assertFalse(doc["is_admin"])
        self.assertTrue(doc["is_active"])
        self.assertIsInstance(doc["created_at"], datetime)
        self.assertIsInstance(doc["updated_at"], datetime)

    def test_create_job_doc_queues_new_jobs(self):
        doc = jobs_model.create_doc(
            "507f1f77bcf86cd799439011",
            "restaurants in mumbai",
            25,
        )

        self.assertEqual(doc["query_text"], "restaurants in mumbai")
        self.assertEqual(doc["leads_requested"], 25)
        self.assertEqual(doc["leads_delivered"], 0)
        self.assertEqual(doc["status"], jobs_model.STATUS_QUEUED)
        self.assertIsNone(doc["started_at"])
        self.assertIsNone(doc["finished_at"])
        self.assertIsNone(doc["error_message"])

    def test_create_saved_search_doc_uses_query_for_launching(self):
        doc = saved_searches_model.create_doc(
            "507f1f77bcf86cd799439011",
            "plumbers in mumbai",
            25,
        )

        self.assertEqual(doc["name"], "plumbers in mumbai")
        self.assertEqual(doc["query"], "plumbers in mumbai")
        self.assertEqual(doc["query_preview"], "plumbers in mumbai")
        self.assertEqual(doc["limit"], 25)
        self.assertIsNone(doc.get("keyword"))
        self.assertIsNone(doc.get("location"))
        self.assertIsInstance(doc["created_at"], datetime)


if __name__ == "__main__":
    unittest.main()
