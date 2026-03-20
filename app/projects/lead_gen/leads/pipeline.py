from app.projects.lead_gen.leads import model
from app.projects.lead_gen.jobs import pipeline as jobs_pipeline

def get_leads_for_job(job_id, user_id, limit=1000, skip=0):
    jobs_pipeline.get_user_job(job_id, user_id)
    return model.find_by_job(job_id, limit, skip)
