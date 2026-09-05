from flask import Blueprint, request, jsonify
from app.core.middleware import auth_required, get_current_user
from app.core.email_classifier import is_company_email
from app.projects.lead_gen.credits import model, pipeline
from app.projects.lead_gen import credit_requests

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
    """
    Request free credits:
    - Automatically approved immediately for verified company/business email domains.
    - Requires admin approval for public/consumer/disposable email domains.
    """
    user = get_current_user()
    data = request.get_json() or {}
    
    reason = data.get('reason', 'First-time credit request')
    user_id_str = str(user['_id'])
    user_email = user.get('email', '')
    
    # 1. Prevent duplicate pending requests
    if credit_requests.has_pending_request(user_id_str):
        return jsonify({'error': 'You already have a pending credit request awaiting approval.'}), 400
    
    # 2. Prevent claiming free credits multiple times
    if credit_requests.has_approved_request(user_id_str):
        return jsonify({'error': 'You have already received your initial free credits.'}), 400
    
    is_company, domain = is_company_email(user_email)
    
    if is_company:
        # Auto-approve for company domain
        req = credit_requests.create_auto_approved_request(
            user_id=user_id_str,
            amount=credit_requests.DEFAULT_CREDIT_AMOUNT,
            reason=reason,
            domain=domain
        )
        
        # Credit user's ledger immediately
        pipeline.add_credits(
            user_id=user_id_str,
            amount=credit_requests.DEFAULT_CREDIT_AMOUNT,
            reason=model.REASON_ADMIN,
            note=f"Auto-approved free credits for company domain: {domain}"
        )
        new_balance = pipeline.get_user_balance(user_id_str)
        
        return jsonify({
            'message': f'Credit request for {credit_requests.DEFAULT_CREDIT_AMOUNT} credits was automatically approved for your company account ({domain})!',
            'auto_approved': True,
            'balance': new_balance,
            'request': credit_requests.to_response(req, user_email)
        }), 201
    else:
        # Public/consumer email -> create pending request for admin approval
        req = credit_requests.create_request(
            user_id=user_id_str,
            amount=credit_requests.DEFAULT_CREDIT_AMOUNT,
            reason=reason
        )
        
        if not req:
            return jsonify({'error': 'You already have a pending credit request'}), 400
        
        return jsonify({
            'message': f'Credit request for {credit_requests.DEFAULT_CREDIT_AMOUNT} credits submitted. Awaiting admin approval.',
            'auto_approved': False,
            'request': credit_requests.to_response(req, user_email)
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

