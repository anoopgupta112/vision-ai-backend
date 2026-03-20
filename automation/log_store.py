from pathlib import Path


LOGS_DIR = Path(__file__).resolve().parent / "logs"


def feature_log_path(feature_id: str) -> Path:
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    safe_name = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in feature_id).strip("_")
    return LOGS_DIR / f"{safe_name}.log"


def read_log_tail(feature_id: str, max_lines: int = 40) -> list[str]:
    path = feature_log_path(feature_id)
    if not path.exists():
        return []
    lines = path.read_text(errors="ignore").splitlines()
    return lines[-max(max_lines, 1):]
