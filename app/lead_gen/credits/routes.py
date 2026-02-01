from flask import Blueprint, request, jsonify
from app.core.middleware import auth_required, get_current_user
from app.lead_gen.credits import model, pipeline

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
