import jwt
from datetime import datetime, timedelta
from functools import wraps
from flask import request, jsonify, current_app, g
from app.core.exceptions import AuthenticationError, AuthorizationError

def generate_token(user_id, expires_hours=24):
    payload = {
        'user_id': str(user_id),
        'exp': datetime.utcnow() + timedelta(hours=expires_hours),
        'iat': datetime.utcnow()
    }
    return jwt.encode(payload, current_app.config['SECRET_KEY'], algorithm='HS256')

def decode_token(token):
    try:
        payload = jwt.decode(token, current_app.config['SECRET_KEY'], algorithms=['HS256'])
        return payload
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None

def get_current_user():
    return getattr(g, 'current_user', None)

def auth_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        from app.auth.models import find_user_by_id
        
        token = None
        auth_header = request.headers.get('Authorization')
        if auth_header and auth_header.startswith('Bearer '):
            token = auth_header.split(' ')[1]
        
        if not token:
            return jsonify({'error': 'Authorization required'}), 401
        
        payload = decode_token(token)
        if not payload:
            return jsonify({'error': 'Invalid or expired token'}), 401
        
        user_doc = find_user_by_id(payload['user_id'])
        if not user_doc:
            return jsonify({'error': 'User not found'}), 401
        
        if not user_doc.get('is_active', True):
            return jsonify({'error': 'Account is disabled'}), 403
        
        g.current_user = user_doc
        return f(*args, **kwargs)
    
    return decorated

def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not g.current_user.get('is_admin', False):
            return jsonify({'error': 'Admin access required'}), 403
        return f(*args, **kwargs)
    return decorated
