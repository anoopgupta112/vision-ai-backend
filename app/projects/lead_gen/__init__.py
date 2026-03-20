from app.projects.lead_gen.jobs import bp as jobs_bp
from app.projects.lead_gen.leads import bp as leads_bp
from app.projects.lead_gen.credits import bp as credits_bp
from app.projects.lead_gen.saved_searches import bp as saved_searches_bp

blueprints = [jobs_bp, leads_bp, credits_bp, saved_searches_bp]

__all__ = ['blueprints']
