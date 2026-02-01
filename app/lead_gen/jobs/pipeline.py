from redis import Redis
from rq import Queue
from app.core.config import Config
from app.lead_gen.jobs import model
from app.lead_gen.credits import model as credits_model, pipeline as credits_pipeline
from app.core.exceptions import InsufficientCreditsError, NotFoundError, AuthorizationError, JobStatusError, ExtractionError

# Initialize Redis queue
redis_conn = Redis.from_url(Config.REDIS_URL)
queue = Queue('lead_gen', connection=redis_conn)

def create_job(user_id, query_text, leads_requested):
    balance = credits_model.get_balance(user_id)
    if balance < leads_requested:
        raise InsufficientCreditsError(balance, leads_requested)
    
    # Deduct credits upfront before creating the job
    credits_pipeline.deduct_credits(user_id, leads_requested, job_id=None)
    
    job = model.create(user_id, query_text, leads_requested)
    
    # Enqueue the job to Redis for processing
    from worker import process_extraction_job
    queue.enqueue(process_extraction_job, str(job['_id']))
    
    return job

def get_user_job(job_id, user_id):
    job = model.find_by_id(job_id)
    if not job:
        raise NotFoundError('Job not found')
    if str(job['user_id']) != str(user_id):
        raise AuthorizationError('Access denied')
    return job

def cancel_job(job_id, user_id):
    job = get_user_job(job_id, user_id)
    
    if job['status'] != model.STATUS_QUEUED:
        raise JobStatusError('Cannot cancel job in current status')
    
    from app.lead_gen.leads import model as leads_model
    model.delete(job_id)
    leads_model.delete_by_job(job_id)
    return {'message': 'Job cancelled'}

