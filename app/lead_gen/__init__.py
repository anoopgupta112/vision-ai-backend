from app.lead_gen.jobs import bp as jobs_bp
from app.lead_gen.leads import bp as leads_bp
from app.lead_gen.credits import bp as credits_bp

blueprints = [jobs_bp, leads_bp, credits_bp]

__all__ = ['blueprints']
