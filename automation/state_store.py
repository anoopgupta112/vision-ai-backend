import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict


STATE_FILE = Path(__file__).resolve().parent / "state.json"


def load_state(state_file: Path = STATE_FILE) -> Dict[str, Any]:
    if not state_file.exists():
        return {"features": {}}

    return json.loads(state_file.read_text())


def save_state(state: Dict[str, Any], state_file: Path = STATE_FILE) -> None:
    state_file.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n")


def mark_feature_in_progress(feature_id: str, state_file: Path = STATE_FILE) -> Dict[str, Any]:
    state = load_state(state_file)
    features = state.setdefault("features", {})
    record = features.setdefault(feature_id, {})
    record["status"] = "in_progress"
    record["updated_at"] = _utc_now()
    save_state(state, state_file)
    return state


def append_stage_result(feature_id: str, stage_name: str, status: str, detail: str, state_file: Path = STATE_FILE) -> Dict[str, Any]:
    state = load_state(state_file)
    features = state.setdefault("features", {})
    record = features.setdefault(feature_id, {})
    record.setdefault("stages", []).append(
        {
            "name": stage_name,
            "status": status,
            "detail": detail,
            "updated_at": _utc_now(),
        }
    )
    record["updated_at"] = _utc_now()
    save_state(state, state_file)
    return state


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
