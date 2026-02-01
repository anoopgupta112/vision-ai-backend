from flask import Blueprint, request, jsonify
from app.core.middleware import auth_required, get_current_user
from app.core.exceptions import ValidationError, AuthenticationError
from app.auth import models, services

bp = Blueprint('auth', __name__, url_prefix='/api/auth')

@bp.route('/register', methods=['POST'])
def register():
    data = request.get_json()
    if not data:
        return jsonify({'error': 'No data provided'}), 400
    
    email = data.get('email', '').strip().lower()
    password = data.get('password', '')
    
    if not email or not password:
        return jsonify({'error': 'Email and password are required'}), 400
    
    if len(password) < 6:
        return jsonify({'error': 'Password must be at least 6 characters'}), 400
    
    try:
        result = services.register_user(email, password)
        return jsonify(result), 201
    except ValidationError as e:
        return jsonify({'error': e.message}), e.status_code

@bp.route('/login', methods=['POST'])
def login():
    data = request.get_json()
    if not data:
        return jsonify({'error': 'No data provided'}), 400
    
    email = data.get('email', '').strip().lower()
    password = data.get('password', '')
    
    if not email or not password:
        return jsonify({'error': 'Email and password are required'}), 400
    
    try:
        result = services.login_user(email, password)
        return jsonify(result), 200
    except AuthenticationError as e:
        return jsonify({'error': e.message}), e.status_code

@bp.route('/me', methods=['GET'])
@auth_required
def get_me():
    user = get_current_user()
    return jsonify({'user': models.to_response(user)}), 200

@bp.route('/profile', methods=['GET'])
@auth_required
def get_profile():
    user = get_current_user()
    return jsonify({'user': models.to_response(user)}), 200

@bp.route('/profile', methods=['PUT'])
@auth_required
def update_profile():
    data = request.get_json()
    if not data:
        return jsonify({'error': 'No data provided'}), 400
    
    user = get_current_user()
    user_id = str(user['_id'])
    
    allowed_fields = ['email']
    update_fields = {k: v for k, v in data.items() if k in allowed_fields}
    
    if not update_fields:
        return jsonify({'error': 'No valid fields to update'}), 400
    
    if 'email' in update_fields:
        existing = models.find_user_by_email(update_fields['email'])
        if existing and str(existing['_id']) != user_id:
            return jsonify({'error': 'Email already in use'}), 400
    
    models.update_user(user_id, update_fields)
    updated_user = models.find_user_by_id(user_id)
    
    return jsonify({'user': models.to_response(updated_user)}), 200
