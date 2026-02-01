from flask import Blueprint, request, jsonify
from app.core.middleware import auth_required, admin_required, get_current_user
from app.core.database import get_collection
from app.core.exceptions import NotFoundError, ValidationError
from app.auth import models as auth_models
from app.lead_gen.credits import model as credits_model, pipeline as credits_pipeline

bp = Blueprint('admin', __name__, url_prefix='/api/admin')

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
    total_jobs = get_collection('jobs').count_documents({})
    total_leads = get_collection('leads').count_documents({})
    
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
    
    jobs_coll = get_collection('jobs')
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
