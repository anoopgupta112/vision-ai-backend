from flask import Blueprint, request, jsonify
from app.core.middleware import auth_required, get_current_user
from app.core.exceptions import AppException
from app.lead_gen.jobs import model, pipeline

bp = Blueprint('lead_gen_jobs', __name__, url_prefix='/api/lead_gen/jobs')

@bp.route('', methods=['POST'])
@auth_required
def create():
    data = request.get_json()
    if not data:
        return jsonify({'error': 'No data provided'}), 400
    
    query_text = data.get('query', '').strip()
    leads_requested = data.get('limit', 50)
    
    if not query_text:
        return jsonify({'error': 'Query is required'}), 400
    
    if not isinstance(leads_requested, int) or leads_requested < 1:
        return jsonify({'error': 'Limit must be a positive integer'}), 400
    
    if leads_requested > 500:
        return jsonify({'error': 'Maximum 500 leads per job'}), 400
    
    user = get_current_user()
    try:
        job = pipeline.create_job(str(user['_id']), query_text, leads_requested)
        return jsonify({'job': model.to_response(job)}), 201
    except AppException as e:
        return jsonify({'error': e.message}), e.status_code

@bp.route('', methods=['GET'])
@auth_required
def list_all():
    user = get_current_user()
    limit = request.args.get('limit', 50, type=int)
    skip = request.args.get('skip', 0, type=int)
    
    jobs = model.find_by_user(str(user['_id']), limit, skip)
    return jsonify({
        'jobs': [model.to_response(j) for j in jobs],
        'count': len(jobs)
    }), 200

@bp.route('/<job_id>', methods=['GET'])
@auth_required
def get_one(job_id):
    user = get_current_user()
    try:
        job = pipeline.get_user_job(job_id, str(user['_id']))
        return jsonify({'job': model.to_response(job)}), 200
    except AppException as e:
        return jsonify({'error': e.message}), e.status_code

@bp.route('/<job_id>', methods=['DELETE'])
@auth_required
def cancel(job_id):
    user = get_current_user()
    try:
        result = pipeline.cancel_job(job_id, str(user['_id']))
        return jsonify(result), 200
    except AppException as e:
        return jsonify({'error': e.message}), e.status_code

@bp.route('/<job_id>/retry', methods=['POST'])
@auth_required
def retry(job_id):
    user = get_current_user()
    try:
        job = pipeline.retry_user_job(job_id, str(user['_id']))
        return jsonify({'job': model.to_response(job)}), 200
    except AppException as e:
        return jsonify({'error': e.message}), e.status_code
