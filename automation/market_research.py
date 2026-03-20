from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional

import requests
from bs4 import BeautifulSoup

from automation.discovery import discover_project_templates


DEFAULT_TIMEOUT_SECONDS = 10
DEFAULT_MAX_SOURCES = 5


def get_live_project_research(
    project_id: str,
    include_project_exploratory: bool = False,
    project_search_depth: int = 1,
) -> Dict[str, Any]:
    project = _find_project(
        project_id,
        include_project_exploratory=include_project_exploratory,
        project_search_depth=project_search_depth,
    )
    if not project:
        raise ValueError("Project not found")

    sources = []
    for source in (project.get("research_sources") or [])[:DEFAULT_MAX_SOURCES]:
        url = (source or {}).get("url")
        if not url:
            continue
        sources.append(_fetch_source_snapshot(source))

    return {
        "project_id": project_id,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "sources": sources,
        "summary": _build_live_summary(project, sources),
        "competitor_snapshot": _build_competitor_snapshot(project, sources),
    }


def _find_project(
    project_id: str,
    include_project_exploratory: bool,
    project_search_depth: int,
) -> Optional[Dict[str, Any]]:
    for project in discover_project_templates(
        include_exploratory=include_project_exploratory,
        limit=None,
        search_depth=project_search_depth,
    ):
        if project.get("id") == project_id:
            return project
    return None


def _fetch_source_snapshot(source: Dict[str, Any]) -> Dict[str, Any]:
    url = source.get("url", "")
    label = source.get("label") or url
    try:
        response = requests.get(
            url,
            timeout=DEFAULT_TIMEOUT_SECONDS,
            headers={
                "User-Agent": "main-dashboard-market-research/1.0",
                "Accept-Language": "en-US,en;q=0.9",
            },
        )
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        title = (soup.title.string or "").strip() if soup.title and soup.title.string else label
        snippets = _extract_snippets(soup)
        return {
            "label": label,
            "url": url,
            "status": "ok",
            "title": title,
            "snippets": snippets,
        }
    except Exception as exc:
        return {
            "label": label,
            "url": url,
            "status": "error",
            "title": label,
            "snippets": [],
            "error": str(exc),
        }


def _extract_snippets(soup: BeautifulSoup) -> list[str]:
    snippets: list[str] = []
    for node in soup.find_all(["h1", "h2", "p", "li"]):
        text = " ".join(node.get_text(" ", strip=True).split())
        if len(text) < 40:
            continue
        snippets.append(text)
        if len(snippets) >= 4:
            break
    return snippets


def _build_live_summary(project: Dict[str, Any], sources: list[Dict[str, Any]]) -> Dict[str, Any]:
    available = [source for source in sources if source.get("status") == "ok"]
    market_signals: list[str] = []
    for source in available[:3]:
        if source.get("snippets"):
            market_signals.append(source["snippets"][0])

    return {
        "why_this_project": project.get("why_now") or "",
        "market_value": project.get("market_value") or "",
        "market_signals": market_signals,
        "sources_checked": len(sources),
        "sources_available": len(available),
    }


def _build_competitor_snapshot(project: Dict[str, Any], sources: list[Dict[str, Any]]) -> list[Dict[str, Any]]:
    by_url = {source.get("url"): source for source in sources}
    snapshot = []
    for competitor in project.get("competitors") or []:
        matched_source = None
        website = competitor.get("website", "")
        for source_url, source in by_url.items():
            if website and website in (source_url or ""):
                matched_source = source
                break
        snapshot.append(
            {
                "name": competitor.get("name"),
                "website": website,
                "fit": competitor.get("fit"),
                "stored_pricing_summary": competitor.get("pricing_summary"),
                "live_source_title": matched_source.get("title") if matched_source else None,
                "live_snippets": matched_source.get("snippets", []) if matched_source else [],
                "live_status": matched_source.get("status") if matched_source else "unmatched",
            }
        )
    return snapshot
