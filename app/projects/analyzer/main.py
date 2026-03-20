from app.projects.analyzer.api.routes import bp


def get_blueprint():
    return bp


__all__ = ["bp", "get_blueprint"]
