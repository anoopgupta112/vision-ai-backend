from app.core.database import get_collection


def init_db():
    return {
        "forms": get_collection("hr_forms"),
        "submissions": get_collection("hr_submissions"),
    }
