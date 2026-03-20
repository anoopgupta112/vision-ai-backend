from app.projects.analyzer.services import storage


def get_form_submissions(form_id: str):
    return storage.get_form_submissions(form_id)
