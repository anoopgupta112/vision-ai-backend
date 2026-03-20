from app.core.exceptions import NotFoundError
from app.projects.lead_gen.saved_searches import model


def create_saved_search(user_id, query, limit, name=None, keyword=None, location=None):
    return model.create(user_id, query, limit, name=name, keyword=keyword, location=location)


def list_saved_searches(user_id, limit=25):
    return model.list_by_user(user_id, limit=limit)


def delete_saved_search(saved_search_id, user_id):
    result = model.delete_for_user(saved_search_id, user_id)
    deleted_count = getattr(result, "deleted_count", 0)
    if deleted_count == 0:
        raise NotFoundError("Saved search not found")
    return {"message": "Saved search deleted"}
