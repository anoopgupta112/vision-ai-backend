import unittest
from unittest.mock import patch

from app.core.exceptions import JobStatusError, NotFoundError
from app.lead_gen.jobs import model as jobs_model
from app.lead_gen.jobs import pipeline


class JobRetryPipelineTestCase(unittest.TestCase):
    @patch("app.lead_gen.jobs.pipeline.model.find_by_id")
    def test_retry_user_job_rejects_non_failed_jobs(self, find_by_id):
        find_by_id.return_value = {
            "_id": "job-1",
            "user_id": "user-1",
            "status": jobs_model.STATUS_RUNNING,
        }

        with self.assertRaises(JobStatusError) as error:
            pipeline.retry_user_job("job-1", "user-1")

        self.assertEqual(str(error.exception), "Cannot retry job in current status")

    @patch("app.lead_gen.jobs.pipeline.model.find_by_id")
    def test_retry_job_raises_not_found_for_missing_job(self, find_by_id):
        find_by_id.return_value = None

        with self.assertRaises(NotFoundError) as error:
            pipeline.retry_job("missing-job")

        self.assertEqual(str(error.exception), "Job not found")

    @patch("app.lead_gen.jobs.pipeline.queue.enqueue")
    @patch("app.lead_gen.jobs.pipeline.model.find_by_id")
    @patch("app.lead_gen.jobs.pipeline.model.reset_for_retry")
    @patch("app.lead_gen.jobs.pipeline.leads_model.delete_by_job")
    @patch("worker.process_extraction_job")
    def test_retry_job_resets_failed_job_and_requeues_worker(
        self,
        process_extraction_job,
        delete_by_job,
        reset_for_retry,
        find_by_id,
        enqueue,
    ):
        failed_job = {
            "_id": "job-1",
            "user_id": "user-1",
            "status": jobs_model.STATUS_FAILED,
        }
        queued_job = {
            "_id": "job-1",
            "user_id": "user-1",
            "status": jobs_model.STATUS_QUEUED,
            "leads_delivered": 0,
            "error_message": None,
        }
        find_by_id.side_effect = [failed_job, queued_job]

        result = pipeline.retry_job("job-1")

        self.assertEqual(result["status"], jobs_model.STATUS_QUEUED)
        delete_by_job.assert_called_once_with("job-1")
        reset_for_retry.assert_called_once_with("job-1")
        enqueue.assert_called_once_with(process_extraction_job, "job-1")


if __name__ == "__main__":
    unittest.main()
