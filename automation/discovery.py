import argparse
import json
from pathlib import Path
from typing import Any, Dict, Optional

from automation.feature_store import FEATURES_DIR, load_feature_manifests, save_feature_manifest


BACKEND_DEFAULT = "/Users/anoopchandra/repositories/main_dashboard"
FRONTEND_DEFAULT = "/Users/anoopchandra/repositories/main_dashboard_frontend"
DISCOVERY_SKILL_FILE = Path(__file__).resolve().parent / "discovery_skill.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Discover suggested features from backend and frontend repos")
    parser.add_argument("--backend-repo", type=Path, default=Path(BACKEND_DEFAULT))
    parser.add_argument("--frontend-repo", type=Path, default=Path(FRONTEND_DEFAULT))
    parser.add_argument("--features-dir", type=Path, default=FEATURES_DIR)
    parser.add_argument("--write", action="store_true")
    return parser.parse_args()


def load_discovery_skill(skill_file: Path = DISCOVERY_SKILL_FILE) -> Dict[str, Any]:
    if not skill_file.exists():
        return {
            "project_name": "",
            "project_summary": "",
            "discovery_goals": [],
            "backend_context": [],
            "frontend_context": [],
            "feature_templates": [],
            "project_templates": [],
        }
    return json.loads(skill_file.read_text())


def discover_features(
    backend_repo: Path,
    frontend_repo: Path,
    features_dir: Path = FEATURES_DIR,
    write: bool = False,
    include_exploratory: bool = False,
) -> list[dict[str, Any]]:
    backend_files = {path.relative_to(backend_repo).as_posix() for path in backend_repo.rglob("*") if path.is_file()}
    frontend_files = {path.relative_to(frontend_repo).as_posix() for path in frontend_repo.rglob("*") if path.is_file()}
    backend_text = _read_repo_text(backend_repo)
    frontend_text = _read_repo_text(frontend_repo)
    existing_ids = {manifest.id for manifest in load_feature_manifests(features_dir)}
    discovery_skill = load_discovery_skill()

    suggestions = [
        suggestion
        for suggestion in _build_suggestions(
            backend_files,
            frontend_files,
            backend_text,
            frontend_text,
            backend_repo,
            frontend_repo,
            discovery_skill,
            include_exploratory=include_exploratory,
        )
        if suggestion["id"] not in existing_ids
    ]

    if write:
        for suggestion in suggestions:
            save_feature_manifest(suggestion, features_dir)

    return suggestions


def _build_suggestions(
    backend_files: set[str],
    frontend_files: set[str],
    backend_text: str,
    frontend_text: str,
    backend_repo: Path,
    frontend_repo: Path,
    discovery_skill: Dict[str, Any],
    include_exploratory: bool,
) -> list[dict[str, Any]]:
    suggestions: list[dict[str, Any]] = []

    for template in discovery_skill.get("feature_templates", []):
        if template.get("tier") == "exploratory" and not include_exploratory:
            continue
        required_backend = set(template.get("required_backend_files", []))
        required_frontend = set(template.get("required_frontend_files", []))
        if not required_backend.issubset(backend_files):
            continue
        if not required_frontend.issubset(frontend_files):
            continue

        suggestions.append(
            _feature_manifest(
                feature_id=template["id"],
                title=template["title"],
                priority=int(template.get("priority", 100)),
                acceptance_criteria=template.get("acceptance_criteria", []),
                api_contract=template.get("api_contract", []),
                backend_repo=backend_repo,
                frontend_repo=frontend_repo,
                category=template.get("category", "product_workflow"),
            )
        )

    suggestions.extend(
        _field_driven_feature_suggestions(
            backend_text=backend_text,
            frontend_text=frontend_text,
            backend_repo=backend_repo,
            frontend_repo=frontend_repo,
        )
    )
    suggestions.extend(
        _website_improvement_suggestions(
            backend_text=backend_text,
            frontend_text=frontend_text,
            backend_repo=backend_repo,
            frontend_repo=frontend_repo,
            include_exploratory=include_exploratory,
        )
    )
    return _dedupe_projects(suggestions)


def discover_project_templates(
    skill_file: Path = DISCOVERY_SKILL_FILE,
    include_exploratory: bool = False,
    limit: Optional[int] = None,
    search_depth: int = 1,
) -> list[dict[str, Any]]:
    discovery_skill = load_discovery_skill(skill_file)
    projects = sorted(
        [
            item
            for item in discovery_skill.get("project_templates", [])
            if item.get("tier") != "exploratory" or include_exploratory
        ],
        key=lambda item: (item.get("priority", 100), item.get("id", "")),
    )
    projects.extend(_generated_project_templates(discovery_skill, include_exploratory, search_depth))
    projects = _dedupe_projects(projects)
    if limit is None:
        return projects
    return projects[:max(limit, 0)]


def _generated_project_templates(
    discovery_skill: Dict[str, Any],
    include_exploratory: bool,
    search_depth: int,
) -> list[dict[str, Any]]:
    depth = max(1, int(search_depth or 1))
    themes = [
        {
            "id": "ai-lead-qa-lab",
            "title": "AI Lead Quality Lab",
            "summary": "A workspace for reviewing lead quality, finding weak result sets, and improving export readiness.",
            "why_now": "Existing jobs, leads, and exports already create the raw workflow for a quality-focused product.",
            "project_features": [
                "Lead quality scoring workspace",
                "Bad-result detection before export",
                "Operator review queues for weak lead sets",
            ],
            "suggested_pages": [
                "Quality dashboard",
                "Lead review queue",
                "Export readiness report",
            ],
        },
        {
            "id": "ai-saved-search-copilot",
            "title": "AI Saved Search Copilot",
            "summary": "A focused product for query tuning, saved-search reuse, and AI recommendations on search strategy.",
            "why_now": "Saved searches are already a core workflow and are a strong anchor for AI-assisted product expansion.",
            "project_features": [
                "Saved-search rewrite suggestions",
                "Location and keyword expansion help",
                "Search performance comparison across saved searches",
            ],
            "suggested_pages": [
                "Search strategy home",
                "Saved-search optimizer",
                "Recommendation history",
            ],
        },
        {
            "id": "revenue-recovery-copilot",
            "title": "Revenue Recovery Copilot",
            "summary": "A recovery-focused project for failed payments, retries, invoice follow-up, and support actions.",
            "why_now": "Payment history and payment-status workflows already exist, so recovery tooling can be carved into a dedicated product.",
            "project_features": [
                "Retry prioritization",
                "Recovery task queues",
                "Customer payment issue summaries",
            ],
            "suggested_pages": [
                "Recovery dashboard",
                "Failed payment queue",
                "Customer issue workspace",
            ],
        },
        {
            "id": "ai-export-advisor",
            "title": "AI Export Advisor",
            "summary": "A project centered on deciding what to export, when to export, and how to package results for clients or teams.",
            "why_now": "The current system already supports jobs, leads, credits, and export-friendly workflows.",
            "project_features": [
                "Export package recommendations",
                "Duplicate and low-signal result warnings",
                "Client-ready delivery summaries",
            ],
            "suggested_pages": [
                "Export planning home",
                "Delivery package builder",
                "Client summary preview",
            ],
        },
        {
            "id": "operator-automation-console",
            "title": "Operator Automation Console",
            "summary": "An operations product for batching retries, reviewing queues, and managing repetitive lead-generation tasks.",
            "why_now": "Admin and retry controls already exist, which makes this a natural ops-focused extension.",
            "project_features": [
                "Queue-based retry control",
                "Batch job review and prioritization",
                "Operational exception tracking",
            ],
            "suggested_pages": [
                "Operations queue",
                "Job triage board",
                "Exception review",
            ],
        },
        {
            "id": "client-intent-insights",
            "title": "Client Intent Insights",
            "summary": "A reporting and insight project that turns job outputs into client-facing explanations and follow-up suggestions.",
            "why_now": "Current job history and export flows can be reframed into a higher-value insight product.",
            "project_features": [
                "Result trend summaries",
                "Client-facing insight reports",
                "Recommended next searches and follow-ups",
            ],
            "suggested_pages": [
                "Insight overview",
                "Client trend reports",
                "Recommended actions",
            ],
        },
        {
            "id": "ai-prospect-workbench",
            "title": "AI Prospect Workbench",
            "summary": "A workspace for evaluating prospect batches, sorting promising groups, and deciding follow-up actions.",
            "why_now": "Lead tables and job details already provide the data surfaces needed for a workbench experience.",
            "project_features": [
                "Prospect group scoring",
                "Follow-up batch recommendations",
                "Lead set summarization",
            ],
            "suggested_pages": [
                "Prospect workbench",
                "Batch insights",
                "Follow-up plan builder",
            ],
        },
        {
            "id": "vertical-search-launchpad",
            "title": "Vertical Search Launchpad",
            "summary": "A product for creating niche or industry-specific search workflows and packaging them as reusable playbooks.",
            "why_now": "The platform already supports search, saved search, and export concepts that can be tailored by vertical.",
            "project_features": [
                "Industry-specific search presets",
                "Reusable saved-search playbooks",
                "Vertical outcome tracking",
            ],
            "suggested_pages": [
                "Vertical library",
                "Preset builder",
                "Outcome comparisons",
            ],
        },
        {
            "id": "ai-growth-funnel-studio",
            "title": "AI Growth Funnel Studio",
            "summary": "A project connecting marketing entry, package comparison, and AI-guided conversion flows into one product.",
            "why_now": "Package purchase and landing-page ideas can become a stronger acquisition product when tied together.",
            "project_features": [
                "Audience-aware page variants",
                "AI-guided package recommendation",
                "Conversion funnel experiments",
            ],
            "suggested_pages": [
                "Audience landing builder",
                "Package recommendation page",
                "Funnel experiment dashboard",
            ],
        },
        {
            "id": "search-delivery-command-center",
            "title": "Search Delivery Command Center",
            "summary": "A project for monitoring search delivery, exports, retries, and handoffs across teams.",
            "why_now": "The existing operational surface is already close to a command center, but not packaged as one product.",
            "project_features": [
                "Delivery timeline views",
                "Retry and export coordination",
                "Hand-off notes and ownership",
            ],
            "suggested_pages": [
                "Delivery overview",
                "Search handoff board",
                "Export timeline",
            ],
        },
        {
            "id": "ai-pricing-optimizer",
            "title": "AI Pricing Optimizer",
            "summary": "A billing and packaging project that experiments with plans, package framing, and AI-guided pricing recommendations.",
            "why_now": "Payments and package workflows are already present, which creates a base for pricing experimentation.",
            "project_features": [
                "Package comparison experiments",
                "Suggested pricing bundles",
                "Revenue signal summaries",
            ],
            "suggested_pages": [
                "Pricing lab",
                "Bundle experiments",
                "Revenue signal dashboard",
            ],
        },
        {
            "id": "support-resolution-studio",
            "title": "Support Resolution Studio",
            "summary": "A support-oriented project for summarizing user issues, payment problems, and workflow blockers with AI help.",
            "why_now": "The product already touches auth, payments, credits, and jobs, which often create support volume.",
            "project_features": [
                "Issue triage summaries",
                "Workflow blocker diagnosis",
                "Suggested support actions",
            ],
            "suggested_pages": [
                "Support queue",
                "Issue summary board",
                "Resolution playbooks",
            ],
        },
    ]

    if not include_exploratory:
        themes = themes[:4]

    batch_size = min(len(themes), max(4, depth * 3))
    generated = []
    for index, theme in enumerate(themes[:batch_size], start=1):
        generated.append(
            {
                "id": theme["id"],
                "title": theme["title"],
                "priority": 100 + index,
                "tier": "exploratory",
                "summary": theme["summary"],
                "why_now": theme["why_now"],
                "market_value": "This idea extends an existing operational workflow into a clearer product surface with stronger monetization potential.",
                "market_research": [
                    "The current repo already contains enough workflow surface to justify this as a focused product idea.",
                    "Narrow products around search operations, billing support, or delivery coordination are often easier to position than one broad all-in-one UI.",
                    "AI is most useful here when attached to concrete operator decisions rather than generic chat.",
                ],
                "growth_chances": [
                    "Can start as a narrow workflow product and expand into team plans",
                    "Can reuse current backend data and UI patterns for faster delivery",
                    "Can later add deeper AI assistance once the workflow proves useful",
                ],
                "benefits": [
                    "Clearer positioning than a generic dashboard expansion",
                    "Uses existing product capabilities as leverage",
                    "Keeps AI attached to real user actions",
                ],
                "future_scope_ai": [
                    "AI summaries tied to workflow context",
                    "AI recommendations for next best actions",
                    "AI scoring or ranking where users already make decisions",
                ],
                "build_requirements": [
                    "Reuse current Flask and React app structure for MVP delivery",
                    "Background jobs for any AI-heavy analysis",
                    "Basic prompt and output logging if AI workflows are added",
                ],
                "ai_tools": [
                    "OpenAI Responses API for summaries and suggestions",
                    "Simple prompt templates per workflow surface",
                ],
                "example_user": {
                    "persona": "Solo operator or small internal operations team",
                    "scenario": f"You use {theme['title']} to review current workflow signals and decide the next best step faster than manually scanning every page.",
                },
                "competitors": [],
                "market_pricing": {
                    "competitor_range": "Depends on whether the product is positioned as a narrow workflow tool or a broader sales/ops suite.",
                    "our_offer": "A focused workflow product built around the existing operational surface in this codebase.",
                    "our_starting_price": "Position after validating which workflow creates the strongest repeat usage.",
                },
                "cost_estimate": {
                    "build_cost": "Usually lower than a greenfield product because core backend and UI patterns already exist.",
                    "monthly_run_cost": "Mostly engineering maintenance, hosting, and any optional AI inference cost.",
                    "cost_drivers": [
                        "How much AI assistance is used",
                        "Whether extra data providers are added",
                        "How many background jobs are required",
                    ],
                },
                "what_extra_we_give": [
                    "A narrower, cleaner workflow than broad platforms",
                    "Better use of current internal context and data model",
                    "A more practical AI layer tied to operations",
                ],
                "research_sources": discovery_skill.get("research_sources", []),
                "project_features": theme["project_features"],
                "suggested_pages": theme["suggested_pages"],
            }
        )
    return generated


def _dedupe_projects(projects: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    result: list[dict[str, Any]] = []
    for project in projects:
        project_id = project.get("id")
        if not project_id or project_id in seen:
            continue
        seen.add(project_id)
        result.append(project)
    return sorted(result, key=lambda item: (item.get("priority", 100), item.get("id", "")))


def _feature_manifest(
    feature_id: str,
    title: str,
    priority: int,
    acceptance_criteria: list[str],
    api_contract: list[str],
    backend_repo: Path,
    frontend_repo: Path,
    category: str = "product_workflow",
) -> dict[str, Any]:
    return {
        "id": feature_id,
        "title": title,
        "status": "suggested",
        "priority": priority,
        "category": category,
        "backend_repo": str(backend_repo),
        "frontend_repo": str(frontend_repo),
        "branches": {
            "backend": f"agent/{feature_id}-backend",
            "frontend": f"agent/{feature_id}-frontend",
        },
        "acceptance_criteria": acceptance_criteria,
        "api_contract": api_contract,
    }


def _read_repo_text(repo: Path) -> str:
    chunks: list[str] = []
    for path in repo.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix.lower() not in {".py", ".tsx", ".ts", ".js", ".jsx", ".json", ".md"}:
            continue
        try:
            chunks.append(path.read_text(errors="ignore"))
        except Exception:
            continue
    return "\n".join(chunks)


def _field_driven_feature_suggestions(
    backend_text: str,
    frontend_text: str,
    backend_repo: Path,
    frontend_repo: Path,
) -> list[dict[str, Any]]:
    combined = f"{backend_text}\n{frontend_text}".lower()
    suggestions: list[dict[str, Any]] = []

    if "website" in combined:
        suggestions.append(
            _feature_manifest(
                feature_id="lead-website-actions",
                title="Add lead website preview and quick actions",
                priority=85,
                acceptance_criteria=[
                    "Users can open or preview lead websites directly from lead workflows",
                    "Website-related actions are accessible from lead rows or lead details",
                    "Lead and export workflows remain green",
                ],
                api_contract=["GET /api/lead_gen/leads/job/:id"],
                backend_repo=backend_repo,
                frontend_repo=frontend_repo,
                category="data_features",
            )
        )

    if "phone" in combined:
        suggestions.append(
            _feature_manifest(
                feature_id="lead-phone-actions",
                title="Add phone actions and outreach shortcuts",
                priority=86,
                acceptance_criteria=[
                    "Users can trigger direct phone-oriented actions from lead records",
                    "Phone values are formatted and handled safely in the UI",
                    "Lead workflows remain green",
                ],
                api_contract=["GET /api/lead_gen/leads/job/:id"],
                backend_repo=backend_repo,
                frontend_repo=frontend_repo,
                category="data_features",
            )
        )

    if "address" in combined:
        suggestions.append(
            _feature_manifest(
                feature_id="lead-address-map-actions",
                title="Add address map and location quick actions",
                priority=87,
                acceptance_criteria=[
                    "Users can open lead addresses in maps or location actions",
                    "Address visibility is improved in lead workflows",
                    "Lead workflows remain green",
                ],
                api_contract=["GET /api/lead_gen/leads/job/:id"],
                backend_repo=backend_repo,
                frontend_repo=frontend_repo,
                category="data_features",
            )
        )

    if "phone" in combined or "website" in combined or "address" in combined:
        suggestions.append(
            _feature_manifest(
                feature_id="ai-lead-contact-assistant",
                title="Add AI contact assistant for lead records",
                priority=88,
                acceptance_criteria=[
                    "AI suggests practical next actions from lead contact fields",
                    "Suggestions stay tied to real lead workflows like call, visit site, or review address quality",
                    "AI assistance remains optional and non-blocking",
                ],
                api_contract=[
                    "GET /api/lead_gen/leads/job/:id",
                    "POST /api/lead_gen/leads/job/:id/contact-assistant",
                ],
                backend_repo=backend_repo,
                frontend_repo=frontend_repo,
                category="ai_support",
            )
        )

    return suggestions


def _website_improvement_suggestions(
    backend_text: str,
    frontend_text: str,
    backend_repo: Path,
    frontend_repo: Path,
    include_exploratory: bool,
) -> list[dict[str, Any]]:
    combined = f"{backend_text}\n{frontend_text}".lower()
    suggestions: list[dict[str, Any]] = []

    if "payment" in combined:
        suggestions.append(
            _feature_manifest(
                feature_id="payment-page-upgrade",
                title="Improve payment page trust and conversion flow",
                priority=95,
                acceptance_criteria=[
                    "Payment page communicates package value and trust signals more clearly",
                    "Existing payment creation flow remains intact",
                    "Payment regression suites remain green",
                ],
                api_contract=[
                    "GET /api/payments/packages",
                    "POST /api/payments/create-order",
                ],
                backend_repo=backend_repo,
                frontend_repo=frontend_repo,
                category="website_improvement",
            )
        )

    if include_exploratory and ("login" in combined or "dashboard" in combined):
        suggestions.append(
            _feature_manifest(
                feature_id="landing-page-conversion-upgrade",
                title="Improve landing page and entry conversion experience",
                priority=96,
                acceptance_criteria=[
                    "Landing and entry surfaces communicate product value more clearly",
                    "Existing auth and dashboard routes continue to work",
                    "Frontend regression suites remain green",
                ],
                api_contract=["GET /", "GET /health"],
                backend_repo=backend_repo,
                frontend_repo=frontend_repo,
                category="website_improvement",
            )
        )

    return suggestions


def main() -> int:
    args = parse_args()
    suggestions = discover_features(
        backend_repo=args.backend_repo,
        frontend_repo=args.frontend_repo,
        features_dir=args.features_dir,
        write=args.write,
        include_exploratory=False,
    )
    print(json.dumps({"discovered_features": suggestions}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
