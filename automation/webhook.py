import json
from typing import Any

import requests

from automation.models import StageResult


def send_run_webhook(webhook_url: str, payload: dict[str, Any]) -> StageResult:
    try:
        response = requests.post(
            webhook_url,
            json=payload,
            timeout=15,
            headers={"Content-Type": "application/json"},
        )
    except Exception as exc:
        return StageResult("webhook", "failed", f"Webhook request failed: {exc}")

    if response.status_code >= 400:
        body = response.text.strip()
        return StageResult(
            "webhook",
            "failed",
            f"Webhook returned {response.status_code}: {body[:500]}",
        )

    return StageResult(
        "webhook",
        "done",
        f"Webhook delivered to {webhook_url} with status {response.status_code}.",
    )
