from redis import Redis
from rq import Queue
from app.core.config import Config
from app.projects.lead_gen.jobs import model
from app.projects.lead_gen.leads import model as leads_model
from app.projects.lead_gen.credits import model as credits_model, pipeline as credits_pipeline
from app.core.exceptions import InsufficientCreditsError, NotFoundError, AuthorizationError, JobStatusError

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
    
    model.delete(job_id)
    leads_model.delete_by_job(job_id)
    return {'message': 'Job cancelled'}

def _ensure_retryable(job):
    if job['status'] != model.STATUS_FAILED:
        raise JobStatusError('Cannot retry job in current status')

def retry_job(job_id):
    job = model.find_by_id(job_id)
    if not job:
        raise NotFoundError('Job not found')

    _ensure_retryable(job)

    leads_model.delete_by_job(job_id)
    model.reset_for_retry(job_id)

    from worker import process_extraction_job
    queue.enqueue(process_extraction_job, str(job_id))

    return model.find_by_id(job_id)

def retry_user_job(job_id, user_id):
    job = get_user_job(job_id, user_id)
    _ensure_retryable(job)
    return retry_job(job_id)
