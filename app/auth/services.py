from app.auth import models
from app.core.middleware import generate_token
from app.core.exceptions import ValidationError, AuthenticationError

def register_user(email, password):
    if models.find_user_by_email(email):
        raise ValidationError('Email already registered')
    
    user_doc = models.create_user(email, password)
    token = generate_token(user_doc['_id'])
    
    return {
        'token': token,
        'user': models.to_response(user_doc)
    }

def login_user(email, password):
    user_doc = models.find_user_by_email(email)
    if not user_doc:
        raise AuthenticationError('Invalid email or password')
    
    if not models.verify_password(user_doc, password):
        raise AuthenticationError('Invalid email or password')
    
    if not user_doc.get('is_active', True):
        raise AuthenticationError('Account is disabled')
    
    token = generate_token(user_doc['_id'])
    return {
        'token': token,
        'user': models.to_response(user_doc)
    }
