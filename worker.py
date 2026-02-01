import os
import sys

# Fix for macOS fork safety issue with Playwright
os.environ['OBJC_DISABLE_INITIALIZE_FORK_SAFETY'] = 'YES'

from redis import Redis
from rq import Queue, Worker, SimpleWorker

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.core.config import Config
from app.core.exceptions import ExtractionError
from app.lead_gen.jobs import model as jobs_model
from app.lead_gen.leads import model as leads_model
from app.lead_gen.credits import pipeline as credits_pipeline

redis_conn = Redis.from_url(Config.REDIS_URL)
queue = Queue('lead_gen', connection=redis_conn)

def process_extraction_job(job_id):
    """Process a lead extraction job using MapsScraper"""
    job = jobs_model.find_by_id(job_id)
    if not job:
        return {'error': 'Job not found'}
    
    jobs_model.update_status(job_id, jobs_model.STATUS_RUNNING)
    
    try:
        # Use the real scraper instead of dummy data
        from app.lead_gen.jobs.scraping.maps import MapsScraper
        scraper = MapsScraper(job_id)
        scraper.run()
        
        # Update job status to done
        jobs_model.update_status(job_id, jobs_model.STATUS_DONE)
        
        # Get final count
        job = jobs_model.find_by_id(job_id)
        return {'leads_delivered': job['leads_delivered']}
        
    except Exception as e:
        error_msg = str(e)
        print(f"Job {job_id} failed: {error_msg}")
        jobs_model.update_status(job_id, jobs_model.STATUS_FAILED, error_msg)
        return {'error': error_msg}

if __name__ == '__main__':
    print('Starting Lead Gen worker...')
    
    # Use SimpleWorker on macOS to avoid fork issues with Playwright
    is_macos = sys.platform == 'darwin'
    
    if is_macos:
        print("🍎 Detected macOS - using SimpleWorker (no fork)")
        worker = SimpleWorker([queue], connection=redis_conn)
    else:
        print("🐧 Using standard Worker with fork")
        worker = Worker([queue], connection=redis_conn)
    
    worker.work()
