from flask import Blueprint, request, jsonify
from app.core.middleware import auth_required, get_current_user
from app.lead_gen.credits import model, pipeline
from app.lead_gen import credit_requests

bp = Blueprint('lead_gen_credits', __name__, url_prefix='/api/lead_gen/credits')

@bp.route('', methods=['GET'])
@auth_required
def get_balance():
    user = get_current_user()
    balance = pipeline.get_user_balance(str(user['_id']))
    return jsonify({'balance': balance}), 200

@bp.route('/history', methods=['GET'])
@auth_required
def get_history():
    user = get_current_user()
    limit = request.args.get('limit', 50, type=int)
    skip = request.args.get('skip', 0, type=int)
    
    history = pipeline.get_user_history(str(user['_id']), limit, skip)
    return jsonify({
        'history': [model.to_response(c) for c in history],
        'count': len(history)
    }), 200

@bp.route('/request', methods=['POST'])
@auth_required
def request_credits():
    """Request free credits (requires admin approval)"""
    user = get_current_user()
    data = request.get_json() or {}
    
    reason = data.get('reason', 'First-time credit request')
    
    # Create credit request
    req = credit_requests.create_request(
        user_id=str(user['_id']),
        amount=credit_requests.DEFAULT_CREDIT_AMOUNT,
        reason=reason
    )
    
    if not req:
        return jsonify({'error': 'You already have a pending credit request'}), 400
    
    return jsonify({
        'message': f'Credit request for {credit_requests.DEFAULT_CREDIT_AMOUNT} credits submitted',
        'request': credit_requests.to_response(req, user['email'])
    }), 201

@bp.route('/requests', methods=['GET'])
@auth_required
def get_my_requests():
    """Get user's credit requests"""
    user = get_current_user()
    requests_list = credit_requests.get_user_requests(str(user['_id']))
    
    return jsonify({
        'requests': [credit_requests.to_response(r, user['email']) for r in requests_list]
    }), 200

