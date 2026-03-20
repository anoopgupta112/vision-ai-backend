from functools import wraps
from pathlib import Path
import subprocess
import sys

from flask import Blueprint, current_app, jsonify, request, send_from_directory
from app.core.middleware import auth_required, admin_required, get_current_user
from app.core.database import get_collection
from app.core.exceptions import AppException
from app.auth import models as auth_models
from app.projects.lead_gen import credit_requests
from app.projects.lead_gen.credits import model as credits_model, pipeline as credits_pipeline
from app.projects.lead_gen.jobs import model as jobs_model, pipeline as jobs_pipeline
from automation.discovery import discover_features, discover_project_templates, load_discovery_skill
from automation.feature_store import find_feature_by_id, load_feature_manifests, save_feature_manifest, update_feature_manifest_status
from automation.log_store import feature_log_path, read_log_tail
from automation.market_research import get_live_project_research
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
    include_exploratory = _truthy(request.args.get('include_exploratory'))
    feature_category = (request.args.get('feature_category') or '').strip()
    include_project_exploratory = _truthy(request.args.get('include_project_exploratory'))
    project_limit = request.args.get('project_limit', default=3, type=int)
    project_search_depth = request.args.get('project_search_depth', default=1, type=int)
    all_candidates = _automation_candidate_payload(
        backend_repo,
        frontend_repo,
        include_exploratory=include_exploratory,
    )
    filtered_candidates = [
        item for item in all_candidates
        if not feature_category or item.get('category') == feature_category
    ]
    all_project_candidates = discover_project_templates(
        include_exploratory=include_project_exploratory,
        limit=None,
        search_depth=project_search_depth,
    )
    payload = {
        'features': _automation_features_payload(),
        'candidates': filtered_candidates,
        'candidate_categories': _candidate_categories(all_candidates),
        'project_candidates': all_project_candidates[:max(project_limit, 0)],
        'project': {
            'backend_repo': str(backend_repo),
            'frontend_repo': str(frontend_repo),
            'include_exploratory': include_exploratory,
            'feature_category': feature_category,
            'include_project_exploratory': include_project_exploratory,
            'project_limit': project_limit,
            'project_search_depth': project_search_depth,
            'project_total_available': len(all_project_candidates),
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


@bp.route('/automation/context', methods=['GET'])
@dashboard_key_required
def get_automation_context():
    return jsonify({'context': load_discovery_skill()}), 200


@bp.route('/automation/projects/<project_id>', methods=['GET'])
@dashboard_key_required
def get_automation_project(project_id):
    include_project_exploratory = _truthy(request.args.get('include_project_exploratory'))
    project_search_depth = request.args.get('project_search_depth', default=3, type=int)
    project = _find_project_candidate_payload(
        project_id,
        include_project_exploratory=include_project_exploratory,
        project_search_depth=project_search_depth,
    )
    if not project:
        return jsonify({'error': 'Project not found'}), 404
    return jsonify({'project': project}), 200


@bp.route('/automation/projects/<project_id>/live-research', methods=['GET'])
@dashboard_key_required
def get_automation_project_live_research(project_id):
    include_project_exploratory = _truthy(request.args.get('include_project_exploratory'))
    project_search_depth = request.args.get('project_search_depth', default=3, type=int)
    try:
        research = get_live_project_research(
            project_id,
            include_project_exploratory=include_project_exploratory,
            project_search_depth=project_search_depth,
        )
    except ValueError:
        return jsonify({'error': 'Project not found'}), 404
    except Exception as exc:
        return jsonify({'error': f'Live research failed: {exc}'}), 502
    return jsonify({'research': research}), 200


@bp.route('/automation/dashboard', methods=['GET'])
@dashboard_key_required
def automation_dashboard():
    static_dir = Path(current_app.root_path).parent / 'static'
    return send_from_directory(static_dir, 'automation-dashboard.html')


@bp.route('/automation/projects/<project_id>/dashboard', methods=['GET'])
@dashboard_key_required
def automation_project_dashboard(project_id):
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


def _automation_features_payload():
    manifests = load_feature_manifests()
    state = load_state()
    features_state = state.get('features', {})
    payload = []

    for manifest in sorted(manifests, key=lambda item: (item.priority, item.id)):
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


def _automation_candidate_payload(backend_repo: Path, frontend_repo: Path, include_exploratory: bool = False):
    candidates = discover_features(
        backend_repo=backend_repo,
        frontend_repo=frontend_repo,
        write=False,
        include_exploratory=include_exploratory,
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
    for candidate in _automation_candidate_payload(backend_repo, frontend_repo, include_exploratory=include_exploratory):
        if candidate['id'] == feature_id:
            return candidate
    return None


def _find_project_candidate_payload(
    project_id,
    include_project_exploratory: bool = False,
    project_search_depth: int = 1,
):
    for candidate in discover_project_templates(
        include_exploratory=include_project_exploratory,
        limit=None,
        search_depth=project_search_depth,
    ):
        if candidate.get('id') == project_id:
            return candidate
    return None


def _requested_repo_paths():
    backend_default = Path(current_app.config.get('BACKEND_REPO_PATH', Path(current_app.root_path).parent))
    frontend_default = Path(current_app.config.get('FRONTEND_REPO_PATH', '/Users/anoopchandra/repositories/main_dashboard_frontend'))

    payload = request.get_json(silent=True) or {}
    backend_value = (payload.get('backend_repo') or request.args.get('backend_repo') or str(backend_default)).strip()
    frontend_value = (payload.get('frontend_repo') or request.args.get('frontend_repo') or str(frontend_default)).strip()

    return Path(backend_value), Path(frontend_value)


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
