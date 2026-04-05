from app.projects.lead_gen.credits import model


def get_user_balance(user_id):
    return model.get_balance(user_id)

def get_user_history(user_id, limit=50, skip=0):
    return model.get_history(user_id, limit, skip)

def add_credits(user_id, amount, reason=model.REASON_ADMIN, note=None):
    return model.add(user_id, amount, reason, note)

def deduct_credits(user_id, amount, job_id=None, note=None):
    return model.deduct(user_id, amount, job_id=job_id, note=note)
