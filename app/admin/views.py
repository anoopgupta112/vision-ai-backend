from functools import wraps
from pathlib import Path
import subprocess
import sys
from datetime import datetime, timezone
from typing import Optional

from flask import Blueprint, current_app, jsonify, request, send_from_directory
from app.core.middleware import auth_required, admin_required, get_current_user
from app.core.database import get_collection
from app.core.exceptions import AppException
from app.auth import models as auth_models
from app.projects.lead_gen import credit_requests
from app.projects.lead_gen.credits import model as credits_model, pipeline as credits_pipeline
from app.projects.lead_gen.jobs import model as jobs_model, pipeline as jobs_pipeline
from automation.discovery import discover_features, load_discovery_skill
from automation.custom_feature import expand_feature_description
from automation.feature_store import find_feature_by_id, load_feature_manifests, save_feature_manifest, update_feature_manifest_status
from automation.log_store import feature_log_path, read_log_tail
from automation.state_store import append_stage_result, load_state, mark_feature_in_progress

bp = Blueprint('admin', __name__, url_prefix='/api/admin')


def dashboard_key_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        expected = current_app.config.get('CODING_DASHBOARD', '').strip()
        if not expected:
            return jsonify({'error': 'Coding dashboard is disabled'}), 404

        provided = (
            request.headers.get('X-Coding-Dashboard-Key', '').strip()
            or request.args.get('key', '').strip()
        )
        if provided != expected:
            return jsonify({'error': 'Invalid dashboard key'}), 403

        return f(*args, **kwargs)

    return decorated

@bp.route('/users', methods=['GET'])
@auth_required
@admin_required
def list_users():
    limit = request.args.get('limit', 100, type=int)
    skip = request.args.get('skip', 0, type=int)
    
    users = auth_models.list_users(limit, skip)
    total = auth_models.count_users()
    
    return jsonify({
        'users': [auth_models.to_response(u) for u in users],
        'total': total
    }), 200

@bp.route('/users/<user_id>', methods=['GET'])
@auth_required
@admin_required
def get_user(user_id):
    user = auth_models.find_user_by_id(user_id)
    if not user:
        return jsonify({'error': 'User not found'}), 404
    return jsonify({'user': auth_models.to_response(user)}), 200

@bp.route('/users/<user_id>', methods=['PUT'])
@auth_required
@admin_required
def update_user(user_id):
    data = request.get_json()
    if not data:
        return jsonify({'error': 'No data provided'}), 400
    
    user = auth_models.find_user_by_id(user_id)
    if not user:
        return jsonify({'error': 'User not found'}), 404
    
    allowed_fields = ['is_admin', 'is_active']
    update_fields = {k: v for k, v in data.items() if k in allowed_fields}
    
    if update_fields:
        auth_models.update_user(user_id, update_fields)
    
    updated_user = auth_models.find_user_by_id(user_id)
    return jsonify({'user': auth_models.to_response(updated_user)}), 200

@bp.route('/users/<user_id>', methods=['DELETE'])
@auth_required
@admin_required
def delete_user(user_id):
    current_user = get_current_user()
    if str(current_user['_id']) == user_id:
        return jsonify({'error': 'Cannot delete yourself'}), 400
    
    user = auth_models.find_user_by_id(user_id)
    if not user:
        return jsonify({'error': 'User not found'}), 404
    
    auth_models.delete_user(user_id)
    return jsonify({'message': 'User deleted'}), 200

@bp.route('/users/<user_id>/credits', methods=['POST'])
@auth_required
@admin_required
def adjust_credits(user_id):
    data = request.get_json()
    if not data:
        return jsonify({'error': 'No data provided'}), 400
    
    user = auth_models.find_user_by_id(user_id)
    if not user:
        return jsonify({'error': 'User not found'}), 404
    
    amount = data.get('amount')
    note = data.get('note', 'Admin adjustment')
    
    if not isinstance(amount, int) or amount == 0:
        return jsonify({'error': 'Amount must be a non-zero integer'}), 400
    
    try:
        if amount > 0:
            credit = credits_pipeline.add_credits(user_id, amount, note=note)
        else:
            # Use deduct pipeline if amount is negative (pass positive value to deduct)
            credit = credits_pipeline.deduct_credits(user_id, abs(amount), job_id=None)
            
        new_balance = credits_model.get_balance(user_id)
        
        return jsonify({
            'credit': credits_model.to_response(credit),
            'new_balance': new_balance
        }), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 400

@bp.route('/stats', methods=['GET'])
@auth_required
@admin_required
def get_stats():
    total_users = auth_models.count_users()
    total_jobs = get_collection('lead_jobs').count_documents({})
    total_leads = get_collection('lead_leads').count_documents({})
    
    return jsonify({
        'stats': {
            'total_users': total_users,
            'total_jobs': total_jobs,
            'total_leads': total_leads
        }
    }), 200

@bp.route('/jobs', methods=['GET'])
@auth_required
@admin_required
def list_all_jobs():
    """Get all jobs from all users with user email and error logs"""
    limit = request.args.get('limit', 100, type=int)
    skip = request.args.get('skip', 0, type=int)
    
    jobs_coll = get_collection('lead_jobs')
    users_coll = get_collection('users')
    
    # Get jobs with pagination
    jobs = list(jobs_coll.find({}).sort('created_at', -1).skip(skip).limit(limit))
    
    # Enrich jobs with user email
    result = []
    for job in jobs:
        user = users_coll.find_one({'_id': job['user_id']})
        result.append({
            'id': str(job['_id']),
            'user_email': user['email'] if user else 'Unknown',
            'query_text': job['query_text'],
            'leads_requested': job['leads_requested'],
            'leads_delivered': job['leads_delivered'],
            'status': job['status'],
            'error_message': job.get('error_message'),
            'created_at': job['created_at'].isoformat() if job.get('created_at') else None,
            'started_at': job.get('started_at').isoformat() if job.get('started_at') else None,
            'finished_at': job.get('finished_at').isoformat() if job.get('finished_at') else None
        })
    
    total = jobs_coll.count_documents({})
    
    return jsonify({
        'jobs': result,
        'total': total
    }), 200

@bp.route('/jobs/<job_id>/retry', methods=['POST'])
@auth_required
@admin_required
def retry_job(job_id):
    try:
        job = jobs_pipeline.retry_job(job_id)
        return jsonify({'job': jobs_model.to_response(job)}), 200
    except AppException as e:
        return jsonify({'error': e.message}), e.status_code


@bp.route('/automation/features', methods=['GET'])
@dashboard_key_required
def list_automation_features():
    backend_repo, frontend_repo = _requested_repo_paths()
    project = _requested_project()
    include_exploratory = _truthy(request.args.get('include_exploratory'))
    feature_category = (request.args.get('feature_category') or '').strip()
    all_candidates = _automation_candidate_payload(
        backend_repo,
        frontend_repo,
        include_exploratory=include_exploratory,
        discovery_skill_file=_project_discovery_skill_file(project),
    )
    filtered_candidates = [
        item for item in all_candidates
        if not feature_category or item.get('category') == feature_category
    ]
    payload = {
        'features': _automation_features_payload(backend_repo=backend_repo, frontend_repo=frontend_repo),
        'candidates': filtered_candidates,
        'candidate_categories': _candidate_categories(all_candidates),
        'project': {
            'key': project.get('key', ''),
            'label': project.get('label', ''),
            'backend_repo': str(backend_repo),
            'frontend_repo': str(frontend_repo),
            'include_exploratory': include_exploratory,
            'feature_category': feature_category,
        },
    }
    return jsonify(payload), 200


@bp.route('/automation/features/<feature_id>/approve', methods=['POST'])
@dashboard_key_required
def approve_automation_feature(feature_id):
    manifests = load_feature_manifests()
    backend_repo, frontend_repo = _requested_repo_paths()
    try:
        feature = find_feature_by_id(manifests, feature_id)
    except ValueError:
        include_exploratory = _truthy((request.get_json(silent=True) or {}).get('include_exploratory'))
        candidate = _find_candidate_payload(feature_id, backend_repo, frontend_repo, include_exploratory=include_exploratory)
        if not candidate:
            return jsonify({'error': 'Feature not found'}), 404

        save_feature_manifest(candidate)
        manifests = load_feature_manifests()
        feature = find_feature_by_id(manifests, feature_id)

    if feature.status == 'suggested':
        update_feature_manifest_status(feature, 'approved')
    elif feature.status not in {'approved', 'in_progress', 'pr_opened', 'merged'}:
        return jsonify({'error': f"Feature cannot be approved from status '{feature.status}'"}), 400

    refreshed = _find_feature_payload(feature_id)
    return jsonify({'feature': refreshed, 'message': f'Feature {feature_id} approved'}), 200


@bp.route('/automation/features/<feature_id>/run', methods=['POST'])
@dashboard_key_required
def run_automation_feature(feature_id):
    manifests = load_feature_manifests()
    try:
        feature = find_feature_by_id(manifests, feature_id)
    except ValueError:
        return jsonify({'error': 'Feature not found'}), 404

    if feature.status not in {'approved', 'in_progress'}:
        return jsonify({'error': f"Feature cannot be run from status '{feature.status}'"}), 400

    if _is_feature_running():
        return jsonify({'error': 'Another automation run is already active'}), 409

    command = [
        sys.executable,
        '-u',
        '-m',
        'automation.orchestrator',
        '--feature-id',
        feature_id,
        '--execute-branches',
        '--execute-codex',
        '--execute-validation',
        '--execute-pushes',
        '--execute-prs',
    ]
    log_handle = feature_log_path(feature_id).open('w', buffering=1)
    process = subprocess.Popen(
        command,
        cwd=str(Path(current_app.root_path).parent),
        stdout=log_handle,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    log_handle.close()
    mark_feature_in_progress(feature_id)
    append_stage_result(feature_id, 'run_requested', 'done', f'Automation triggered from dashboard. pid={process.pid}')
    return jsonify({
        'message': f'Automation started for {feature_id}',
        'feature_id': feature_id,
        'pid': process.pid,
    }), 202


import json as _json

_PROJECTS_FILE = Path(__file__).resolve().parents[2] / 'automation' / 'projects.json'


@bp.route('/automation/projects', methods=['GET'])
@dashboard_key_required
def list_automation_projects():
    """Return the list of projects from automation/projects.json."""
    try:
        data = _json.loads(_PROJECTS_FILE.read_text())
        return jsonify({'projects': data.get('projects', [])}), 200
    except Exception as exc:
        return jsonify({'error': str(exc), 'projects': []}), 200


@bp.route('/automation/context', methods=['GET'])
@dashboard_key_required
def get_automation_context():
    backend_repo, frontend_repo = _requested_repo_paths()
    project = _requested_project()
    return jsonify({'context': _automation_context_payload(project, backend_repo, frontend_repo)}), 200


@bp.route('/automation/features/custom', methods=['POST'])
@dashboard_key_required
def generate_custom_feature():
    """Expand a plain-language description into a structured feature candidate."""
    body = request.get_json(silent=True) or {}
    description = (body.get('description') or '').strip()
    if not description:
        return jsonify({'error': 'description is required'}), 400

    backend_repo = (body.get('backend_repo') or '').strip()
    frontend_repo = (body.get('frontend_repo') or '').strip()
    project_name = (body.get('project_name') or '').strip()
    project = _find_project(project_name) if project_name else {}

    try:
        candidate = expand_feature_description(
            description=description,
            backend_repo=backend_repo,
            frontend_repo=frontend_repo,
            project_name=(project.get('label') or project_name),
            skill_file=_project_discovery_skill_file(project),
        )
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400
    except Exception as exc:
        return jsonify({'error': f'Feature generation failed: {exc}'}), 500

    return jsonify({'candidate': candidate}), 200


@bp.route('/automation/features/custom/save', methods=['POST'])
@dashboard_key_required
def save_custom_feature():
    """Persist a custom feature candidate as a manifest JSON file."""
    body = request.get_json(silent=True) or {}
    candidate = body.get('candidate') or {}

    required_fields = ['id', 'title', 'backend_repo', 'frontend_repo', 'branches',
                       'acceptance_criteria', 'api_contract']
    for field in required_fields:
        if not candidate.get(field):
            return jsonify({'error': f"Missing required field: {field}"}), 400

    # Build a proper manifest-compatible dict
    manifest_data = {
        'id': candidate['id'],
        'title': candidate['title'],
        'status': 'suggested',
        'priority': int(candidate.get('priority') or 50),
        'backend_repo': candidate['backend_repo'],
        'frontend_repo': candidate['frontend_repo'] or candidate['backend_repo'],
        'branches': {
            'backend': candidate['branches'].get('backend', f"agent/{candidate['id']}-backend"),
            'frontend': candidate['branches'].get('frontend', f"agent/{candidate['id']}-frontend"),
        },
        'acceptance_criteria': candidate.get('acceptance_criteria') or [],
        'api_contract': candidate.get('api_contract') or [],
        'summary': candidate.get('summary', ''),
        'implementation_notes': candidate.get('implementation_notes', ''),
        'category': candidate.get('category', 'core_platform'),
        '_source': candidate.get('_source', 'custom'),
    }

    try:
        path = save_feature_manifest(manifest_data)
    except Exception as exc:
        return jsonify({'error': f'Failed to save manifest: {exc}'}), 500

    return jsonify({'saved': True, 'path': str(path), 'id': manifest_data['id']}), 201


@bp.route('/automation/dashboard', methods=['GET'])
@dashboard_key_required
def automation_dashboard():
    static_dir = Path(current_app.root_path).parent / 'static'
    return send_from_directory(static_dir, 'automation-dashboard.html')


@bp.route('/automation/projects/<project_id>', methods=['GET'])
@dashboard_key_required
def get_automation_project(project_id):
    project = _find_project(project_id)
    if not project:
        return jsonify({'error': 'Project not found'}), 404
    include_exploratory = _truthy(request.args.get('include_project_exploratory'))
    search_depth = request.args.get('project_search_depth', 3, type=int)
    return jsonify({
        'project': _project_detail_payload(
            project,
            include_exploratory=include_exploratory,
            search_depth=search_depth,
        )
    }), 200


@bp.route('/automation/projects/<project_id>/live-research', methods=['GET'])
@dashboard_key_required
def get_automation_project_live_research(project_id):
    project = _find_project(project_id)
    if not project:
        return jsonify({'error': 'Project not found'}), 404
    include_exploratory = _truthy(request.args.get('include_project_exploratory'))
    search_depth = request.args.get('project_search_depth', 3, type=int)
    return jsonify({
        'research': _project_live_research_payload(
            project,
            include_exploratory=include_exploratory,
            search_depth=search_depth,
        )
    }), 200


@bp.route('/automation/projects/<project_id>/dashboard', methods=['GET'])
@dashboard_key_required
def automation_project_dashboard(project_id):
    if not _find_project(project_id):
        return jsonify({'error': 'Project not found'}), 404
    static_dir = Path(current_app.root_path).parent / 'static'
    return send_from_directory(static_dir, 'automation-project.html')


# Credit Request Management
@bp.route('/credit-requests', methods=['GET'])
@auth_required
@admin_required
def list_credit_requests():
    """Get all pending credit requests"""
    limit = request.args.get('limit', 100, type=int)
    skip = request.args.get('skip', 0, type=int)
    
    requests = credit_requests.get_pending_requests(limit, skip)
    pending_count = credit_requests.count_pending()
    
    # Get user emails
    users_coll = get_collection('users')
    result = []
    for req in requests:
        user = users_coll.find_one({'_id': req['user_id']})
        result.append(credit_requests.to_response(req, user['email'] if user else 'Unknown'))
    
    return jsonify({
        'requests': result,
        'pending_count': pending_count
    }), 200

@bp.route('/credit-requests/<request_id>/approve', methods=['POST'])
@auth_required
@admin_required
def approve_credit_request(request_id):
    """Approve a credit request and add credits to user"""
    admin = get_current_user()
    data = request.get_json() or {}
    admin_note = data.get('note', 'Approved by admin')
    
    # Get request first
    req = credit_requests.get_request_by_id(request_id)
    if not req:
        return jsonify({'error': 'Credit request not found'}), 404
    
    if req['status'] != credit_requests.STATUS_PENDING:
        return jsonify({'error': 'Request already processed'}), 400
    
    # Approve request
    updated = credit_requests.approve_request(request_id, str(admin['_id']), admin_note)
    
    # Add credits to user
    credits_pipeline.add_credits(
        str(req['user_id']),
        req['amount'],
        note=f"Credit request approved: {admin_note}"
    )
    
    # Get user email for response
    user = auth_models.find_user_by_id(req['user_id'])
    
    return jsonify({
        'message': f"{req['amount']} credits added to user",
        'request': credit_requests.to_response(updated, user['email'] if user else None)
    }), 200

@bp.route('/credit-requests/<request_id>/reject', methods=['POST'])
@auth_required
@admin_required
def reject_credit_request(request_id):
    """Reject a credit request"""
    admin = get_current_user()
    data = request.get_json() or {}
    admin_note = data.get('note', 'Rejected by admin')
    
    req = credit_requests.get_request_by_id(request_id)
    if not req:
        return jsonify({'error': 'Credit request not found'}), 404
    
    if req['status'] != credit_requests.STATUS_PENDING:
        return jsonify({'error': 'Request already processed'}), 400
    
    updated = credit_requests.reject_request(request_id, str(admin['_id']), admin_note)
    
    user = auth_models.find_user_by_id(req['user_id'])
    
    return jsonify({
        'message': 'Credit request rejected',
        'request': credit_requests.to_response(updated, user['email'] if user else None)
    }), 200


def _automation_features_payload(backend_repo: Optional[Path] = None, frontend_repo: Optional[Path] = None):
    manifests = load_feature_manifests()
    state = load_state()
    features_state = state.get('features', {})
    payload = []

    for manifest in sorted(manifests, key=lambda item: (item.priority, item.id)):
        if not _manifest_matches_project(manifest, backend_repo=backend_repo, frontend_repo=frontend_repo):
            continue
        record = features_state.get(manifest.id, {})
        stages = record.get('stages', [])
        payload.append({
            'id': manifest.id,
            'title': manifest.title,
            'status': manifest.status,
            'priority': manifest.priority,
            'backend_branch': manifest.backend_branch,
            'frontend_branch': manifest.frontend_branch,
            'acceptance_criteria': manifest.acceptance_criteria,
            'api_contract': manifest.api_contract,
            'source_file': manifest.source_file,
            'run_status': record.get('status'),
            'run_updated_at': record.get('updated_at'),
            'latest_stage': stages[-1] if stages else None,
            'stages': stages[-10:],
            'recent_logs': read_log_tail(manifest.id, max_lines=25),
            'can_approve': manifest.status == 'suggested',
        })

    return payload


def _find_feature_payload(feature_id):
    for feature in _automation_features_payload():
        if feature['id'] == feature_id:
            return feature
    return None


def _automation_candidate_payload(
    backend_repo: Path,
    frontend_repo: Path,
    include_exploratory: bool = False,
    discovery_skill_file: Optional[Path] = None,
):
    candidates = discover_features(
        backend_repo=backend_repo,
        frontend_repo=frontend_repo,
        write=False,
        include_exploratory=include_exploratory,
        discovery_skill_file=discovery_skill_file,
    )
    return sorted(candidates, key=lambda item: (item.get('priority', 100), item.get('id', '')))


def _candidate_categories(candidates):
    labels = {
        'website_improvement': 'Website Improvements',
        'data_features': 'Data-Based Features',
        'ai_support': 'AI Support Features',
        'product_workflow': 'Product Workflow Features',
    }
    categories = []
    seen = set()
    for candidate in candidates:
        key = candidate.get('category') or 'product_workflow'
        if key in seen:
            continue
        seen.add(key)
        categories.append({'key': key, 'label': labels.get(key, key.replace('_', ' ').title())})
    categories.sort(key=lambda item: item['label'])
    return categories


def _find_candidate_payload(feature_id, backend_repo: Path, frontend_repo: Path, include_exploratory: bool = False):
    project = _requested_project()
    for candidate in _automation_candidate_payload(
        backend_repo,
        frontend_repo,
        include_exploratory=include_exploratory,
        discovery_skill_file=_project_discovery_skill_file(project),
    ):
        if candidate['id'] == feature_id:
            return candidate
    return None




def _requested_repo_paths():
    requested_project = _requested_project()
    backend_default = Path(current_app.config.get('BACKEND_REPO_PATH', Path(current_app.root_path).parent))
    frontend_default = Path(current_app.config.get('FRONTEND_REPO_PATH', '/Users/anoopchandra/repositories/main_dashboard_frontend'))
    if requested_project:
        backend_default = Path(requested_project.get('backend_repo') or backend_default)
        frontend_default = Path(requested_project.get('frontend_repo') or frontend_default)

    payload = request.get_json(silent=True) or {}
    backend_value = (payload.get('backend_repo') or request.args.get('backend_repo') or str(backend_default)).strip()
    frontend_value = (payload.get('frontend_repo') or request.args.get('frontend_repo') or str(frontend_default)).strip()

    return Path(backend_value), Path(frontend_value)


def _load_projects():
    try:
        data = _json.loads(_PROJECTS_FILE.read_text())
    except Exception:
        return []
    return data.get('projects', [])


def _find_project(project_id: str):
    for project in _load_projects():
        if project.get('key') == project_id:
            return project
    return None


def _requested_project():
    payload = request.get_json(silent=True) or {}
    project_id = (payload.get('project') or request.args.get('project') or '').strip()
    if not project_id:
        return {}
    return _find_project(project_id) or {}


def _automation_context_payload(project: dict, backend_repo: Path, frontend_repo: Path):
    context = load_discovery_skill(_project_discovery_skill_file(project))
    project_label = (project or {}).get('label', '').strip()
    project_key = (project or {}).get('key', '').strip()
    repo_summary = f"Backend repo: {backend_repo} | Frontend repo: {frontend_repo}"

    if project_label:
        context['project_name'] = project_label
        if not context.get('project_summary'):
            context['project_summary'] = (
                f"Automation scope for {project_label}. Use the selected repositories when discovering or running features."
            )
    elif not context.get('project_summary'):
        context['project_summary'] = repo_summary

    backend_context = list(context.get('backend_context') or [])
    frontend_context = list(context.get('frontend_context') or [])
    backend_line = f"Selected backend repo: {backend_repo}"
    frontend_line = f"Selected frontend repo: {frontend_repo}"
    if backend_line not in backend_context:
        backend_context.insert(0, backend_line)
    if frontend_line not in frontend_context:
        frontend_context.insert(0, frontend_line)
    context['backend_context'] = backend_context
    context['frontend_context'] = frontend_context
    context['project_key'] = project_key
    return context


def _norm_path(path) -> Optional[Path]:
    if not path:
        return None
    return Path(path).expanduser().resolve()


def _paths_overlap(left, right) -> bool:
    left_path = _norm_path(left)
    right_path = _norm_path(right)
    if not left_path or not right_path:
        return False
    return left_path == right_path or right_path in left_path.parents


def _manifest_matches_project(manifest, backend_repo: Optional[Path] = None, frontend_repo: Optional[Path] = None):
    if backend_repo:
        return _paths_overlap(manifest.backend_repo, backend_repo)
    if frontend_repo:
        return _paths_overlap(manifest.frontend_repo, frontend_repo)
    return True


def _project_feature_data(project: dict, include_exploratory: bool = False):
    backend_repo = Path(project['backend_repo'])
    frontend_repo = Path(project['frontend_repo'])
    features = _automation_features_payload(backend_repo=backend_repo, frontend_repo=frontend_repo)
    candidates = _automation_candidate_payload(
        backend_repo,
        frontend_repo,
        include_exploratory=include_exploratory,
        discovery_skill_file=_project_discovery_skill_file(project),
    )
    return features, candidates


def _project_discovery_skill_file(project: dict) -> Optional[Path]:
    value = (project or {}).get('discovery_skill_file')
    if not value:
        return None
    return Path(value)


def _project_detail_payload(project: dict, include_exploratory: bool = False, search_depth: int = 3):
    features, candidates = _project_feature_data(project, include_exploratory=include_exploratory)
    candidate_titles = [item.get('title') for item in candidates[:max(search_depth, 1)] if item.get('title')]
    feature_titles = [item.get('title') for item in features[:max(search_depth, 1)] if item.get('title')]
    scoped_features = feature_titles or candidate_titles or ['No automation opportunities discovered yet']
    project_label = project.get('label') or project.get('key') or 'Project'

    return {
        'id': project.get('key'),
        'title': project_label,
        'summary': f"Automation scope for {project_label} using the configured backend and frontend repositories.",
        'why_now': f"{len(candidates)} candidate feature(s) and {len(features)} tracked feature(s) are available for this project.",
        'market_value': 'Internal delivery acceleration and clearer automation visibility for this project area.',
        'priority': max(10, 100 - min(len(candidates) * 10 + len(features) * 5, 80)),
        'market_research': [
            'Current view is generated from local repository analysis.',
            f"Backend repo: {project.get('backend_repo')}",
            f"Frontend repo: {project.get('frontend_repo')}",
        ],
        'growth_chances': [
            'Add more project-specific discovery templates to increase suggestion quality.',
            'Keep manifests scoped to their project repos so the dashboard stays accurate.',
        ],
        'benefits': [
            'Project selection now scopes context and tracked features.',
            'Feature discovery can focus on the chosen backend/frontend pair.',
        ],
        'future_scope_ai': [
            'Use LLM-assisted project-specific feature planning.',
            'Add live external market research when network-backed research is reintroduced.',
        ],
        'project_features': scoped_features,
        'suggested_pages': ['Automation dashboard', 'Project detail dashboard'],
        'build_requirements': [
            'Maintain project registry entries with backend/frontend repo paths.',
            'Keep feature manifests aligned with the project they target.',
        ],
        'ai_tools': ['Codex automation orchestrator', 'Repository-based discovery rules'],
        'example_user': {
            'persona': 'Internal operator or admin',
            'scenario': f"Reviews {project_label} opportunities, approves candidates, and runs automation from the dashboard.",
        },
        'competitors': [
            {
                'name': 'Current manual process',
                'website': '',
                'pricing_summary': 'Engineer time and coordination overhead',
                'fit': 'Baseline alternative before dashboard automation',
            }
        ],
        'market_pricing': {
            'competitor_range': 'Not available from local-only analysis',
            'our_offer': 'Project-scoped automation planning and execution',
            'our_starting_price': 'Internal tooling',
        },
        'what_extra_we_give': [
            'Project-scoped context',
            'Tracked feature state',
            'Candidate generation from repository structure',
        ],
        'cost_estimate': {
            'build_cost': 'Low incremental cost within the current automation system',
            'monthly_run_cost': 'Depends on Codex/validation usage',
            'cost_drivers': ['Repository scan size', 'Automation run frequency', 'Validation depth'],
        },
        'research_sources': [],
    }


def _project_live_research_payload(project: dict, include_exploratory: bool = False, search_depth: int = 3):
    features, candidates = _project_feature_data(project, include_exploratory=include_exploratory)
    checked = max(len(features) + len(candidates), 1)
    return {
        'fetched_at': datetime.now(timezone.utc).isoformat(),
        'summary': {
            'sources_checked': checked,
            'sources_available': checked,
            'why_this_project': f"Repository analysis found {len(candidates)} candidate(s) and {len(features)} tracked feature(s) for {project.get('label') or project.get('key')}.",
            'market_value': 'Live web research is not configured here; this summary is based on current repository signals.',
            'market_signals': [
                f"Search depth requested: {max(search_depth, 1)}",
                f"Exploratory discovery: {'enabled' if include_exploratory else 'disabled'}",
            ],
        },
        'sources': [
            {
                'label': 'Local repository analysis',
                'url': '',
            }
        ],
    }


def _truthy(value):
    return str(value or '').strip().lower() in {'1', 'true', 'yes', 'on'}


def _is_feature_running():
    try:
        result = subprocess.run(
            ['pgrep', '-f', 'python -m automation.orchestrator'],
            capture_output=True,
            text=True,
            check=False,
        )
        return bool(result.stdout.strip())
    except Exception:
        return False
