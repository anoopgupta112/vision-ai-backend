from app.projects.analyzer.api.routes import bp


def get_router(_templates=None):
    return bp


__all__ = ["bp", "get_router"]
